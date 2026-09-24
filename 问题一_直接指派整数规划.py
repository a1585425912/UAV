"""问题一的非枚举组批：逐箱直接指派 MILP + 能耗外逼近切平面。

不生成货箱子集。每个服务区分别求架次、能耗、时间的严格词典序解。
运行：python 问题一_直接指派整数规划.py [--smoke S001]

单次 MILP 默认时间上限 120 s，可用 solve_area(..., time_limit=...) 覆盖。
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from 问题一_基础计算 import load_inputs, operation_time, safe_payload, trip

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题一_非枚举整数规划"
NAMES = ("A", "B", "C")
ENERGY_TOL = 1e-6


def energy_slope(drone, route, q):
    qmax = drone["payload"]
    l0, lf = drone["range0"], drone["range_full"]
    a = (l0 - lf) / qmax**1.5
    lq = l0 - a * q**1.5
    d = float(route["去程水平距离（m）"])
    dh = float(route["去程爬升（m）"])
    return drone["energy"] * d * (1.5 * a * q**0.5) / lq**2 + 9.81 * dh / (3.6e6 * drone["eta"])


def greedy_bound(boxes, drones, route):
    """只构造一个可行上界；最优方案由 MILP 决定。"""
    bins = []
    for box in sorted(boxes, key=lambda b: -b["mass"]):
        placed = False
        for group in bins:
            name = group["model"]
            drone = drones[name]
            mass = group["mass"] + box["mass"]
            volume = group["volume"] + box["volume"]
            if mass <= drone["payload"] + 1e-9 and volume <= drone["volume"] + 1e-9 and trip(drone, route, mass)["return_soc"] >= drone["reserve"] / 100 - 1e-10:
                group["mass"], group["volume"] = mass, volume
                placed = True
                break
        if not placed:
            viable = [name for name in NAMES if box["mass"] <= drones[name]["payload"] and box["volume"] <= drones[name]["volume"] and trip(drones[name], route, box["mass"])["return_soc"] >= drones[name]["reserve"] / 100 - 1e-10]
            if not viable:
                raise RuntimeError(f"单箱不可运输：{box['id']}")
            name = min(viable, key=lambda g: trip(drones[g], route, box["mass"])["total_kwh"])
            bins.append({"model": name, "mass": box["mass"], "volume": box["volume"]})
    return len(bins)


def solve_area(area, boxes, drones, route, time_limit=120, required_trips=None):
    n = len(boxes)
    feasible_bound = greedy_bound(boxes, drones, route)
    kmax = required_trips if required_trips is not None else feasible_bound
    if not (1 <= kmax <= n):
        raise ValueError(f"{area}: 架次数必须在 1 到 {n} 之间")
    caps = {g: safe_payload(drones[g], route)[0] for g in NAMES}
    x = {(b, t, g): len(NAMES) * (b * kmax + t) + j for b in range(n) for t in range(kmax) for j, g in enumerate(NAMES)}
    nx = len(x)
    y = {(t, g): nx + 3 * t + j for t in range(kmax) for j, g in enumerate(NAMES)}
    ny = len(y)
    e = {(t, g): nx + ny + 3 * t + j for t in range(kmax) for j, g in enumerate(NAMES)}
    nv = nx + ny + len(e)
    lower, upper = np.zeros(nv), np.ones(nv)
    upper[nx + ny:] = np.inf
    integrality = np.zeros(nv, dtype=int)
    integrality[:nx + ny] = 1
    trip_obj = np.zeros(nv)
    energy_obj = np.zeros(nv)
    time_obj = np.zeros(nv)
    for (t, g), iy in y.items():
        trip_obj[iy] = 1
        energy_obj[e[t, g]] = 1
        time_obj[iy] = operation_time(drones[g], route, 0)
        for b in range(n):
            time_obj[x[b, t, g]] = drones[g]["load"] + drones[g]["extra"]

    # 切点由 MILP 当前解自适应生成；初始点只取零载荷。
    cuts = {g: {0.0} for g in NAMES}
    stats = Counter()

    def optimize(objective, fixed_trips=None, energy_ceiling=None):
        rows, cols, vals, lows, highs = [], [], [], [], []

        def add(coeff, lo=-np.inf, hi=np.inf):
            rid = len(lows)
            for col, value in coeff.items():
                if value:
                    rows.append(rid)
                    cols.append(col)
                    vals.append(value)
            lows.append(lo)
            highs.append(hi)

        for b in range(n):
            add({x[b, t, g]: 1 for t in range(kmax) for g in NAMES}, 1, 1)
        for t in range(kmax):
            add({y[t, g]: 1 for g in NAMES}, hi=1)
            if t + 1 < kmax:
                add({**{y[t, g]: -1 for g in NAMES}, **{y[t + 1, g]: 1 for g in NAMES}}, hi=0)
            for g in NAMES:
                drone = drones[g]
                if caps[g] is None:
                    upper[y[t, g]] = 0
                    for b in range(n):
                        upper[x[b, t, g]] = 0
                    continue
                add({y[t, g]: 1, **{x[b, t, g]: -1 for b in range(n)}}, hi=0)
                add({**{x[b, t, g]: boxes[b]["mass"] for b in range(n)}, y[t, g]: -min(caps[g], drone["payload"])}, hi=0)
                add({**{x[b, t, g]: boxes[b]["volume"] for b in range(n)}, y[t, g]: -drone["volume"]}, hi=0)
                add({e[t, g]: 1, y[t, g]: -(1 - drone["reserve"] / 100) * drone["energy"]}, hi=0)
                for q0 in sorted(cuts[g]):
                    f = trip(drone, route, q0)["total_kwh"]
                    slope = energy_slope(drone, route, q0)
                    add({e[t, g]: -1, y[t, g]: f - slope * q0,
                         **{x[b, t, g]: slope * boxes[b]["mass"] for b in range(n)}}, hi=0)
        if fixed_trips is not None:
            add({idx: 1 for idx in y.values()}, fixed_trips, fixed_trips)
        if energy_ceiling is not None:
            add({idx: 1 for idx in e.values()}, hi=energy_ceiling)
        mat = coo_matrix((vals, (rows, cols)), shape=(len(lows), nv)).tocsr()
        result = milp(objective, integrality=integrality, bounds=Bounds(lower, upper),
                      constraints=LinearConstraint(mat, lows, highs),
                      options={"time_limit": time_limit, "mip_rel_gap": 1e-9})
        stats["milp_calls"] += 1
        if result.status != 0 or result.x is None:
            raise RuntimeError(f"{area}: MILP未证明最优: status={result.status}, {result.message}")
        return result

    def inspect(solution):
        active, actual = [], 0.0
        for t in range(kmax):
            for g in NAMES:
                if solution[y[t, g]] > 0.5:
                    chosen = [b for b in range(n) if solution[x[b, t, g]] > 0.5]
                    mass = sum(boxes[b]["mass"] for b in chosen)
                    real = trip(drones[g], route, mass)["total_kwh"]
                    active.append((t, g, chosen, mass, real))
                    actual += real
        return active, actual

    def refine(active):
        added = False
        for _, g, _, mass, _ in active:
            if all(abs(mass - old) > 1e-9 for old in cuts[g]):
                cuts[g].add(mass)
                added = True
        return added

    # 第一阶段：架次数最少，逐次排除因能耗低估而不可行的整数解。
    if required_trips is None:
        for _ in range(200):
            result = optimize(trip_obj)
            active, _ = inspect(result.x)
            if all(real <= (1 - drones[g]["reserve"] / 100) * drones[g]["energy"] + 1e-8 for _, g, _, _, real in active):
                break
            if not refine(active):
                raise RuntimeError(f"{area}: 能耗约束切平面停滞")
        else:
            raise RuntimeError(f"{area}: 架次阶段超过迭代上限")
        ntrips = len(active)
    else:
        ntrips = required_trips

    # 第二阶段：全局能耗下界由 MILP 给出；真实能耗与下界闭合后停止。
    for _ in range(300):
        result = optimize(energy_obj, fixed_trips=ntrips)
        active, actual = inspect(result.x)
        feasible = all(real <= (1 - drones[g]["reserve"] / 100) * drones[g]["energy"] + 1e-8 for _, g, _, _, real in active)
        if feasible and actual - result.fun <= ENERGY_TOL:
            break
        if not refine(active):
            raise RuntimeError(f"{area}: 能耗目标切平面停滞，gap={actual-result.fun}")
    else:
        raise RuntimeError(f"{area}: 能耗阶段超过迭代上限")
    optimum_energy = actual
    energy_gap = actual - result.fun

    # 第三阶段：仅在最小架次和最优能耗容差内比较累计作业时间。
    for _ in range(300):
        result = optimize(time_obj, fixed_trips=ntrips, energy_ceiling=optimum_energy + ENERGY_TOL)
        active, actual = inspect(result.x)
        feasible = all(real <= (1 - drones[g]["reserve"] / 100) * drones[g]["energy"] + 1e-8 for _, g, _, _, real in active)
        if feasible and actual <= optimum_energy + ENERGY_TOL + 1e-8:
            break
        if not refine(active):
            raise RuntimeError(f"{area}: 时间目标切平面停滞")
    else:
        raise RuntimeError(f"{area}: 时间阶段超过迭代上限")

    rows = []
    for t, g, chosen, mass, real in active:
        ids = [boxes[b]["id"] for b in chosen]
        detail = trip(drones[g], route, mass)
        rows.append({"服务区": area, "架次": t + 1, "机型": g, "货箱编号列表": ",".join(ids),
                     "箱数": len(ids), "质量_kg": mass,
                     "体积_m3": sum(boxes[b]["volume"] for b in chosen),
                     "能耗_kwh": real, "作业时间_s": operation_time(drones[g], route, len(ids)),
                     "返航SOC": detail["return_soc"]})
    assert Counter(bid for row in rows for bid in row["货箱编号列表"].split(",")) == Counter(b["id"] for b in boxes)
    return rows, {"货箱数": n, "架次数": ntrips, "贪心可行上界": feasible_bound,
                  "MILP调用次数": stats["milp_calls"], "能耗最优性绝对间隙_kWh": energy_gap,
                  "能耗切点数": {g: len(cuts[g]) for g in NAMES}}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", choices=[f"S{i:03d}" for i in range(1, 16)])
    parser.add_argument("--sensitivity", action="store_true", help="另算 10%、25%、30% 返航余量")
    args = parser.parse_args()
    drones, boxes, routes = load_inputs()
    areas = [args.smoke] if args.smoke else sorted(boxes)
    selected, stats = [], {}
    caps = []
    for area in areas:
        for g in NAMES:
            cap, status, empty, full = safe_payload(drones[g], routes[area])
            caps.append({"服务区": area, "机型": g, "最大安全载荷_kg": cap,
                         "状态": status, "空载能耗_kwh": empty, "满载能耗_kwh": full})
        rows, info = solve_area(area, boxes[area], drones, routes[area])
        selected.extend(rows)
        stats[area] = info
        print(f"{area}: {info['架次数']} 架次, {sum(r['能耗_kwh'] for r in rows):.9f} kWh, MILP {info['MILP调用次数']} 次", flush=True)
    if args.smoke:
        print(json.dumps({"载荷": caps, "组批": selected, "求解": stats}, ensure_ascii=False, indent=2))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "最大安全载荷_45组.csv", caps)
    write_csv(OUT / "最优组批_逐架次.csv", selected)
    summary = {"求解方法": "逐箱直接指派 MILP + 自适应能耗切平面，不生成货箱子集",
               "目标顺序": "架次数→总能耗→累计作业时间", "能耗收敛容差_kWh": ENERGY_TOL,
               "总架次数": len(selected), "总能耗_kWh": sum(r["能耗_kwh"] for r in selected),
               "累计作业时间_s": sum(r["作业时间_s"] for r in selected),
               "最低返航SOC": min(r["返航SOC"] for r in selected), "分区求解": stats}
    (OUT / "汇总.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    from 问题一_主方案模板 import main as write_main_template
    write_main_template()
    if args.sensitivity:
        sensitivity = []
        scenario_batches = []
        for reserve in (10.0, 20.0, 25.0, 30.0):
            scenario_drones = {g: {**drone, "reserve": reserve} for g, drone in drones.items()}
            scenario_caps = []
            scenario_rows = []
            for area in areas:
                for g in NAMES:
                    cap, status, _, _ = safe_payload(scenario_drones[g], routes[area])
                    scenario_caps.append({"返航余量_百分比": reserve, "服务区": area, "机型": g,
                                          "最大安全载荷_kg": cap, "状态": status})
                area_rows, _ = solve_area(area, boxes[area], scenario_drones, routes[area])
                scenario_rows.extend(area_rows)
            scenario_batches.extend({"返航余量_百分比": reserve, **row} for row in scenario_rows)
            sensitivity.extend(scenario_caps)
            for row in sensitivity[-45:]:
                row["全任务架次数"] = len(scenario_rows)
                row["全任务能耗_kWh"] = sum(r["能耗_kwh"] for r in scenario_rows)
                row["全任务累计时间_s"] = sum(r["作业时间_s"] for r in scenario_rows)
                row["最低实际返航SOC"] = min(r["返航SOC"] for r in scenario_rows)
            print(f"余量 {reserve:.0f}%: {len(scenario_rows)} 架次, {sum(r['能耗_kwh'] for r in scenario_rows):.6f} kWh", flush=True)
        write_csv(OUT / "返航余量敏感性.csv", sensitivity)
        write_csv(OUT / "返航余量组批_逐架次.csv", scenario_batches)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
