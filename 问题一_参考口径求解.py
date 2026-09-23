"""按参考 PDF 的几何口径完成问题一，货箱用非枚举直接指派 MILP。

运行：python 问题一_参考口径几何.py
      python 问题一_参考口径求解.py [--smoke S001]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from 问题一_统一航段精确组批 import load_inputs, safe_payload
from 问题一_直接指派整数规划 import NAMES, solve_area, write_csv

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题一_参考口径"
RESERVES = (10.0, 15.0, 20.0, 25.0, 30.0, 35.0)
FRONTIER_EXTRA = 5


def read_routes():
    with (OUT / "单服务区往返几何参数.csv").open(encoding="utf-8-sig", newline="") as handle:
        return {row["服务区"]: row for row in csv.DictReader(handle)}


def add_roundtrip_time(rows, drones):
    enriched = []
    for row in rows:
        drone = drones[row["机型"]]
        seconds = row["作业时间_s"] - drone["prep"] - row["箱数"] * drone["load"]
        enriched.append({**row, "往返时间_含交接_s": seconds})
    return enriched


def total(rows):
    return (sum(row["能耗_kwh"] for row in rows),
            sum(row["作业时间_s"] for row in rows))


def solve_baseline(areas, boxes, drones, routes):
    caps, selected, stats = [], [], {}
    for area in areas:
        for model in NAMES:
            cap, state, empty, full = safe_payload(drones[model], routes[area])
            caps.append({"服务区": area, "机型": model, "最大安全载荷_kg": cap,
                         "状态": state, "空载能耗_kwh": empty, "满载能耗_kwh": full})
        rows, info = solve_area(area, boxes[area], drones, routes[area])
        selected.extend(rows)
        stats[area] = info
        print(f"{area}: {len(rows)} 架次，{total(rows)[0]:.9f} kWh", flush=True)
    return caps, selected, stats


def solve_sensitivity(areas, boxes, drones, routes, baseline):
    cap_rows, trip_rows, summary_rows = [], [], []
    for rho in RESERVES:
        sdrones = {g: {**drone, "reserve": rho} for g, drone in drones.items()}
        chosen = []
        for area in areas:
            for model in NAMES:
                cap, state, _, _ = safe_payload(sdrones[model], routes[area])
                cap_rows.append({"返航余量_百分比": rho, "服务区": area, "机型": model,
                                 "最大安全载荷_kg": cap, "状态": state})
            if rho == 20.0:
                area_rows = [row for row in baseline if row["服务区"] == area]
            else:
                area_rows, _ = solve_area(area, boxes[area], sdrones, routes[area])
            chosen.extend(area_rows)
        e, t = total(chosen)
        trips = Counter(row["机型"] for row in chosen)
        summary_rows.append({"返航余量_百分比": rho, "架次数": len(chosen),
                             "总能耗_kWh": e, "累计作业时间_s": t,
                             "A型架次": trips["A"], "B型架次": trips["B"], "C型架次": trips["C"],
                             "最低实际返航SOC": min(row["返航SOC"] for row in chosen)})
        trip_rows.extend({"返航余量_百分比": rho, **row} for row in add_roundtrip_time(chosen, sdrones))
        print(f"余量 {rho:.0f}%：{len(chosen)} 架次，{e:.9f} kWh", flush=True)
    return cap_rows, trip_rows, summary_rows


def solve_frontier(areas, boxes, drones, routes, baseline):
    """只对架次数做 DP 卷积；各区货箱仍由直接指派 MILP 求解。"""
    by_area = {}
    base_count = Counter(row["服务区"] for row in baseline)
    for area in areas:
        lo = base_count[area]
        hi = min(len(boxes[area]), lo + FRONTIER_EXTRA)
        by_area[area] = {}
        for k in range(lo, hi + 1):
            if k == lo:
                rows = [row for row in baseline if row["服务区"] == area]
            else:
                rows, _ = solve_area(area, boxes[area], drones, routes[area], required_trips=k)
            assert len(rows) == k and all(row["箱数"] > 0 for row in rows)
            by_area[area][k] = rows
        print(f"权衡 {area}: 计算 {lo}–{hi} 架次", flush=True)
    global_min = sum(base_count.values())
    max_total = global_min + FRONTIER_EXTRA
    dp = {0: (0.0, 0.0, [])}
    for area in areas:
        nxt = {}
        for used, (energy, seconds, plans) in dp.items():
            for k, rows in by_area[area].items():
                nk = used + k
                if nk > max_total:
                    continue
                ae, at = total(rows)
                score = (energy + ae, seconds + at)
                if nk not in nxt or score < nxt[nk][:2]:
                    nxt[nk] = (*score, plans + rows)
        dp = nxt
    records, arrangements = [], []
    for k in range(global_min, max_total + 1):
        e, t, rows = dp[k]
        assert len(rows) == k
        records.append({"总架次数": k, "最小总能耗_kWh": e, "对应累计作业时间_s": t})
        arrangements.extend({"总架次数": k, **row} for row in add_roundtrip_time(rows, drones))
    return records, arrangements


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", choices=[f"S{i:03d}" for i in range(1, 16)])
    args = parser.parse_args()
    drones, boxes, _ = load_inputs()
    routes = read_routes()
    areas = [args.smoke] if args.smoke else sorted(boxes)
    caps, selected, stats = solve_baseline(areas, boxes, drones, routes)
    if args.smoke:
        print(json.dumps({"安全载荷": caps, "逐架次": selected, "求解状态": stats}, ensure_ascii=False, indent=2))
        return
    assert len(caps) == 45 and len(selected) >= 15
    out_rows = add_roundtrip_time(selected, drones)
    write_csv(OUT / "最大安全载荷_45组.csv", caps)
    write_csv(OUT / "最优组批_逐架次.csv", out_rows)
    cap_rows, trip_rows, sensitivity = solve_sensitivity(areas, boxes, drones, routes, selected)
    write_csv(OUT / "返航余量载荷_270组.csv", cap_rows)
    write_csv(OUT / "返航余量组批_逐架次.csv", trip_rows)
    write_csv(OUT / "返航余量汇总.csv", sensitivity)
    frontier, frontier_rows = solve_frontier(areas, boxes, drones, routes, selected)
    write_csv(OUT / "架次能耗权衡.csv", frontier)
    write_csv(OUT / "架次能耗权衡_逐架次.csv", frontier_rows)
    e, t = total(selected)
    summary = {"几何口径": "WGS84 椭球测地距离、节点表地面海拔、既有 DEM 航段最高海拔+50 m",
               "组批方法": "逐箱直接指派 MILP 和自适应切平面，不枚举货箱子集",
               "载荷求解": "单调能耗二分法", "基准返航余量": 0.2,
               "箱数": sum(map(len, boxes.values())), "服务区数": len(areas), "最大安全载荷组数": len(caps),
               "架次数": len(selected), "总能耗_kWh": e, "累计作业时间_s": t,
               "往返时间含交接合计_s": sum(row["往返时间_含交接_s"] for row in out_rows),
               "最低返航SOC": min(row["返航SOC"] for row in selected),
               "机型架次": dict(Counter(row["机型"] for row in selected)),
               "切平面闭合差最大值_kWh": max(x["能耗最优性绝对间隙_kWh"] for x in stats.values()),
               "切平面闭合容差_kWh": 1e-6,
               "MILP相对最优间隙设置": 1e-9,
               "分区求解": stats}
    (OUT / "汇总.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "分区求解"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
