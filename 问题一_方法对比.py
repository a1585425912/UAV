"""问题一：把"完整枚举+位掩码DP"与其它求解方法放在同一口径下对比。

同一物理口径（统一航段缓存、题面等效航程与能耗换算假设）和同一目标顺序
（架次数 -> 总能耗 -> 累计作业时间）下并列比较：

  枚举DP    仓库基线：2^n 子集扫描 + 锚点位掩码 DP，精确
  指派MILP  逐箱直接指派 + 自适应能耗切平面，不生成子集，精确
  贪心BFD   最佳适应递减构造 + 消箱局部搜索，启发式（只有可行解，无最优性保证）
  LP下界    集合划分（集合覆盖）LP 松弛，给出架次数下界
  装箱下界  质量/体积解析下界

用法：
  python 问题一_方法对比.py            # 真实算例逐区对比
  python 问题一_方法对比.py --scaling  # 规模实验（合成同分布实例）
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from 问题一_直接指派整数规划 import solve_area as milp_solve
from 问题一_统一航段精确组批 import load_inputs, operation_time, safe_payload, solve_area as enumeration_solve, trip

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题一_方法对比"
EPS = 1e-9
NAMES = ("A", "B", "C")


def energy_limit(drone):
    return (1 - drone["reserve"] / 100) * drone["energy"]


def enumerate_candidates(boxes, drones, route, deadline=None):
    """逐区完整枚举可行货箱子集：2^n 扫描，每个子集保留 (能耗, 时间) 最优机型。"""
    n = len(boxes)
    total = 1 << n
    mass = [0.0] * total
    volume = [0.0] * total
    best = {}
    rows = 0
    for mask in range(1, total):
        if deadline is not None and not (mask & 0x3FFFF) and time.perf_counter() > deadline:
            raise TimeoutError(f"候选枚举超过时限（已完成 {mask}/{total}）")
        low = mask & -mask
        j = low.bit_length() - 1
        prev = mask ^ low
        m = mass[prev] + boxes[j]["mass"]
        v = volume[prev] + boxes[j]["volume"]
        mass[mask] = m
        volume[mask] = v
        for name in NAMES:
            drone = drones[name]
            if m > drone["payload"] + EPS or v > drone["volume"] + EPS:
                continue
            energy = trip(drone, route, m)
            if energy["total_kwh"] > energy_limit(drone) + EPS:
                continue
            rows += 1
            score = (energy["total_kwh"], operation_time(drone, route, mask.bit_count()), name)
            if mask not in best or score < best[mask][0]:
                best[mask] = (score, name, m, v)
    return best, rows


def anchored_dp(best, n, deadline=None, step_cap=None):
    """锚点位掩码 DP：对每个可达 mask 枚举含其最低位的子集，复杂度 O(3^n) 上界。"""
    memo = {}
    steps = 0

    def solve(remaining):
        nonlocal steps
        if remaining == 0:
            return (0, 0.0, 0.0), ()
        hit = memo.get(remaining, "miss")
        if hit != "miss":
            return hit
        anchor = remaining & -remaining
        chosen = None
        sub = remaining
        while sub:
            steps += 1
            if step_cap is not None and steps > step_cap:
                raise TimeoutError(f"DP 超过步数上限 {step_cap}")
            if deadline is not None and not (steps & 0xFFFF) and time.perf_counter() > deadline:
                raise TimeoutError(f"DP 超过时限（已迭代 {steps} 步）")
            if sub & anchor and sub in best:
                tail = solve(remaining ^ sub)
                if tail is not None:
                    score = (tail[0][0] + 1, tail[0][1] + best[sub][0][0], tail[0][2] + best[sub][0][1])
                    if chosen is None or score < chosen[0]:
                        chosen = score, (sub,) + tail[1]
            sub = (sub - 1) & remaining
        memo[remaining] = chosen
        return chosen

    optimum = solve((1 << n) - 1)
    if optimum is None:
        raise RuntimeError("存在无法运输的货箱")
    return optimum, len(memo), steps


def _placement_key(drone, mass, volume):
    slack = (drone["payload"] - mass) / drone["payload"] + (drone["volume"] - volume) / drone["volume"]
    return slack


def _insert_backtrack(items, groups, drones, route, budget):
    """把 items 全部塞进已有 groups（不允许开新架次），成功返回 True。"""
    if not items:
        return True
    box = items[0]
    for gi, group in enumerate(groups):
        for name in NAMES:
            drone = drones[name]
            m = group["mass"] + box["mass"]
            v = group["volume"] + box["volume"]
            if m > drone["payload"] + EPS or v > drone["volume"] + EPS:
                continue
            if trip(drone, route, m)["total_kwh"] > energy_limit(drone) + EPS:
                continue
            budget[0] -= 1
            if budget[0] < 0:
                raise TimeoutError("消箱搜索超过预算")
            saved = (group["model"], group["mass"], group["volume"])
            group["model"], group["mass"], group["volume"] = name, m, v
            group["boxes"].append(box)
            if _insert_backtrack(items[1:], groups, drones, route, budget):
                return True
            group["boxes"].pop()
            group["model"], group["mass"], group["volume"] = saved
    return False


def greedy_bfd(boxes, drones, route, budget=200000):
    """最佳适应递减构造 + 反复消箱。返回逐架次明细。"""
    groups = []
    for box in sorted(boxes, key=lambda b: (-b["mass"], -b["volume"], b["id"])):
        pick = None
        for gi, group in enumerate(groups):
            for name in NAMES:
                drone = drones[name]
                m = group["mass"] + box["mass"]
                v = group["volume"] + box["volume"]
                if m > drone["payload"] + EPS or v > drone["volume"] + EPS:
                    continue
                energy = trip(drone, route, m)
                if energy["total_kwh"] > energy_limit(drone) + EPS:
                    continue
                key = (_placement_key(drone, m, v), energy["total_kwh"], name)
                if pick is None or key < pick[0]:
                    pick = (key, gi, name, m, v)
        if pick is None:
            name = min(NAMES, key=lambda g: trip(drones[g], route, box["mass"])["total_kwh"])
            groups.append({"model": name, "boxes": [box], "mass": box["mass"], "volume": box["volume"]})
        else:
            _, gi, name, m, v = pick
            group = groups[gi]
            group["model"], group["mass"], group["volume"] = name, m, v
            group["boxes"].append(box)

    remaining_budget = [budget]
    improved = True
    while improved:
        improved = False
        for gi in sorted(range(len(groups)), key=lambda i: groups[i]["mass"]):
            trial = [dict(group, boxes=list(group["boxes"])) for k, group in enumerate(groups) if k != gi]
            if not trial:
                continue
            items = sorted(groups[gi]["boxes"], key=lambda b: (-b["mass"], -b["volume"]))
            try:
                placed = _insert_backtrack(items, trial, drones, route, remaining_budget)
            except TimeoutError:
                placed = False
                improved = False
            if placed:
                groups = trial
                improved = True
                break
            if remaining_budget[0] < 0:
                improved = False
                break

    rows = []
    for k, group in enumerate(groups, 1):
        drone = drones[group["model"]]
        ids = [b["id"] for b in group["boxes"]]
        detail = trip(drone, route, group["mass"])
        rows.append({"服务区": None, "架次": k, "机型": group["model"], "货箱编号列表": ",".join(ids),
                     "箱数": len(ids), "质量_kg": group["mass"], "体积_m3": group["volume"],
                     "能耗_kwh": detail["total_kwh"],
                     "作业时间_s": operation_time(drone, route, len(ids)), "返航SOC": detail["return_soc"]})
    return rows


def maximal_columns(masks, n):
    """只保留极大可行子集：若 C 真含于另一个可行子集 C'，则 C 在集合覆盖 LP 中被支配。"""
    present = set(masks)
    return [mask for mask in masks
            if not any(not (mask >> j & 1) and (mask | 1 << j) in present for j in range(n))]


def lp_trip_lower_bound(best, n, method="highs-ipm", pruned=True, time_limit=None):
    """集合覆盖 LP 松弛：min sum y_C, s.t. 每箱至少被覆盖一次，y >= 0。

    pruned=True 时只保留极大可行子集。被支配列总能换成其超集而不增加代价、
    也不减少覆盖，因此 LP 下界不变。
    """
    all_masks = sorted(best)
    if not all_masks:
        return None
    masks = maximal_columns(all_masks, n) if pruned else all_masks
    matrix = np.zeros((n, len(masks)))
    for j, mask in enumerate(masks):
        rest = mask
        while rest:
            low = rest & -rest
            matrix[low.bit_length() - 1, j] = 1.0
            rest ^= low
    options = {"time_limit": time_limit} if time_limit else None
    result = linprog(np.ones(len(masks)), A_ub=-matrix, b_ub=-np.ones(n), bounds=(0, None),
                     method=method, options=options)
    used = method
    if result.status != 0 and method != "highs":
        result = linprog(np.ones(len(masks)), A_ub=-matrix, b_ub=-np.ones(n), bounds=(0, None),
                         method="highs", options=options)
        used = "highs"
    return {"下界": float(result.fun) if result.status == 0 else None, "状态": int(result.status),
            "列数_全部": len(all_masks), "列数_极大": len(masks), "求解方法": used}


def analytic_lower_bound(boxes, drones, route):
    """质量/体积解析下界：ceil(总质量/单架次最大可载质量) 与体积下界取大。"""
    total_mass = sum(b["mass"] for b in boxes)
    total_volume = sum(b["volume"] for b in boxes)
    caps = [safe_payload(drones[g], route)[0] for g in NAMES]
    mass_cap = max(min(cap if cap is not None else 0.0, drones[g]["payload"]) for cap, g in zip(caps, NAMES))
    volume_cap = max(drones[g]["volume"] for g in NAMES)
    return max(math.ceil(total_mass / mass_cap - 1e-9), math.ceil(total_volume / volume_cap - 1e-9))


def summarize(rows):
    return {"架次": len(rows), "能耗_kWh": sum(r["能耗_kwh"] for r in rows),
            "作业时间_s": sum(r["作业时间_s"] for r in rows),
            "最低返航SOC": min(r["返航SOC"] for r in rows) if rows else None,
            "机型": dict(Counter(r["机型"] for r in rows))}


def compare_real(deadline_s=600.0):
    drones, boxes, routes = load_inputs()
    areas = sorted(boxes)
    per_area, staged = [], []
    for area in areas:
        route = routes[area]
        box_list = boxes[area]
        n = len(box_list)

        t0 = time.perf_counter()
        _, selected, states = enumeration_solve(area, box_list, drones, route)
        baseline_seconds = time.perf_counter() - t0
        baseline = summarize(selected)

        deadline = time.perf_counter() + deadline_s
        t0 = time.perf_counter()
        best, candidate_rows = enumerate_candidates(box_list, drones, route, deadline=deadline)
        scan_seconds = time.perf_counter() - t0
        t0 = time.perf_counter()
        optimum, dp_states, dp_steps = anchored_dp(best, n, deadline=deadline)
        dp_seconds = time.perf_counter() - t0
        staged_rows = [dict(服务区=area, 架次=k + 1, 机型=best[mask][1],
                           货箱编号列表=",".join(box_list[j]["id"] for j in range(n) if mask >> j & 1),
                           箱数=mask.bit_count(), 质量_kg=best[mask][2], 体积_m3=best[mask][3],
                           能耗_kwh=best[mask][0][0], 作业时间_s=best[mask][0][1],
                           返航SOC=trip(drones[best[mask][1]], route, best[mask][2])["return_soc"])
                       for k, mask in enumerate(optimum[1])]
        staged_result = summarize(staged_rows)
        assert staged_result["架次"] == baseline["架次"], area
        assert abs(staged_result["能耗_kWh"] - baseline["能耗_kWh"]) < 1e-9, area
        assert abs(staged_result["作业时间_s"] - baseline["作业时间_s"]) < 1e-9, area

        t0 = time.perf_counter()
        milp_rows, milp_info = milp_solve(area, box_list, drones, route)
        milp_seconds = time.perf_counter() - t0
        milp_result = summarize(milp_rows)

        t0 = time.perf_counter()
        greedy_rows = greedy_bfd(box_list, drones, route)
        greedy_seconds = time.perf_counter() - t0
        greedy_result = summarize(greedy_rows)

        t0 = time.perf_counter()
        lp_info = lp_trip_lower_bound(best, n)
        lp_seconds = time.perf_counter() - t0
        lp_bound = lp_info["下界"]
        analytic_bound = analytic_lower_bound(box_list, drones, route)
        tight = max(math.ceil(lp_bound - 1e-9), analytic_bound) == baseline["架次"]

        per_area.append({
            "服务区": area, "箱数": n,
            "枚举_架次": baseline["架次"], "枚举_能耗_kWh": baseline["能耗_kWh"],
            "枚举_作业时间_s": baseline["作业时间_s"], "枚举_耗时_s": baseline_seconds,
            "枚举_候选数": candidate_rows, "枚举_DP状态数": states,
            "MILP_架次": milp_result["架次"], "MILP_能耗_kWh": milp_result["能耗_kWh"],
            "MILP_作业时间_s": milp_result["作业时间_s"], "MILP_耗时_s": milp_seconds,
            "MILP_调用次数": milp_info["MILP调用次数"],
            "贪心_架次": greedy_result["架次"], "贪心_能耗_kWh": greedy_result["能耗_kWh"],
            "贪心_作业时间_s": greedy_result["作业时间_s"], "贪心_耗时_s": greedy_seconds,
            "LP下界_架次": lp_bound, "LP_耗时_s": lp_seconds,
            "LP列数_全部": lp_info["列数_全部"], "LP列数_极大": lp_info["列数_极大"],
            "解析下界_架次": analytic_bound,
            "上界等于下界": "是" if tight else "否",
        })
        staged.append({"服务区": area, "候选枚举耗时_s": scan_seconds, "DP耗时_s": dp_seconds,
                       "DP状态数": dp_states, "DP子集迭代数": dp_steps, "候选记录数": candidate_rows})
        print(f"{area}: 枚举 {baseline['架次']}架次/{baseline_seconds:.3f}s  "
              f"MILP {milp_result['架次']}架次/{milp_seconds:.3f}s  贪心 {greedy_result['架次']}架次  "
              f"LP下界 {lp_bound:.4f}（{lp_info['列数_全部']}→{lp_info['列数_极大']}列, {lp_seconds:.2f}s）", flush=True)

    totals = {}
    for key, label in (("枚举", "枚举DP"), ("MILP", "指派MILP"), ("贪心", "贪心BFD")):
        totals[label] = {
            "架次": sum(r[f"{key}_架次"] for r in per_area),
            "能耗_kWh": sum(r[f"{key}_能耗_kWh"] for r in per_area),
            "作业时间_s": sum(r[f"{key}_作业时间_s"] for r in per_area),
            "总耗时_s": sum(r[f"{key}_耗时_s"] for r in per_area),
        }
    lower = {"LP下界_架次": sum(r["LP下界_架次"] for r in per_area),
             "LP下界取整_架次": sum(math.ceil(r["LP下界_架次"] - 1e-9) for r in per_area),
             "解析下界_架次": sum(r["解析下界_架次"] for r in per_area),
             "LP总耗时_s": sum(r["LP_耗时_s"] for r in per_area)}
    summary = {
        "口径": "统一航段缓存 + 题面等效航程 + 20%返航余量",
        "目标顺序": "架次数 -> 总能耗 -> 累计作业时间",
        "求解器": {"枚举DP": "完整子集枚举 + 锚点位掩码DP（精确）",
                    "指派MILP": "逐箱直接指派 + 自适应能耗切平面（精确）",
                    "贪心BFD": "最佳适应递减 + 消箱局部搜索（启发式）",
                    "LP下界": "集合覆盖LP松弛 + 极大子集支配剪枝（架次数下界）",
                    "解析下界": "质量/体积装箱下界"},
        "总架次数": totals["枚举DP"]["架次"],
        "总能耗_kWh": totals["枚举DP"]["能耗_kWh"],
        "累计作业时间_s": totals["枚举DP"]["作业时间_s"],
        "方法汇总": totals,
        "下界汇总": lower,
        "精确方法一致": all(r["枚举_架次"] == r["MILP_架次"] and abs(r["枚举_能耗_kWh"] - r["MILP_能耗_kWh"]) < 1e-6
                            and abs(r["枚举_作业时间_s"] - r["MILP_作业时间_s"]) < 1e-6 for r in per_area),
        "贪心达到最优架次的服务区数": sum(1 for r in per_area if r["贪心_架次"] == r["枚举_架次"]),
        "下界紧的服务区数": sum(1 for r in per_area if r["上界等于下界"] == "是"),
        "分区": per_area,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "方法对比_分区.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_area[0]))
        writer.writeheader()
        writer.writerows(per_area)
    with (OUT / "枚举分阶段耗时.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(staged[0]))
        writer.writeheader()
        writer.writerows(staged)
    (OUT / "汇总.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "分区"}, ensure_ascii=False, indent=2))
    return summary


def synthetic_boxes(base_boxes, n):
    boxes = [dict(b) for b in base_boxes]
    i = 0
    while len(boxes) < n:
        src = base_boxes[i % len(base_boxes)]
        i += 1
        boxes.append({"id": f"S001-SYN-{i:02d}", "mass": src["mass"], "volume": src["volume"], "type": src["type"]})
    return boxes


def scaling(sizes=(15, 17, 19, 21), deadline_s=60.0, dp_step_cap=200_000_000):
    drones, boxes, routes = load_inputs()
    route = routes["S001"]
    base = boxes["S001"]
    rows = []
    for n in sizes:
        instance = synthetic_boxes(base, n)
        row = {"箱数": n, "理论子集数": 2 ** n}

        t0 = time.perf_counter()
        try:
            best, candidate_rows = enumerate_candidates(instance, drones, route,
                                                        deadline=time.perf_counter() + deadline_s)
            row["候选枚举_耗时_s"] = time.perf_counter() - t0
            row["候选记录数"] = candidate_rows
            row["可行子集数"] = len(best)
        except TimeoutError as exc:
            row["候选枚举_耗时_s"] = time.perf_counter() - t0
            row["候选记录数"] = None
            row["可行子集数"] = None
            row["候选枚举_状态"] = f"超时({exc})"
            best = None
        else:
            row["候选枚举_状态"] = "完成"

        if best is None:
            row["DP_耗时_s"] = None
            row["DP状态数"] = None
            row["DP子集迭代数"] = None
            row["DP_状态"] = "未运行"
            row["枚举架次"] = None
        else:
            t0 = time.perf_counter()
            try:
                optimum, states, steps = anchored_dp(best, n, deadline=time.perf_counter() + deadline_s,
                                                     step_cap=dp_step_cap)
                row["DP_耗时_s"] = time.perf_counter() - t0
                row["DP状态数"] = states
                row["DP子集迭代数"] = steps
                row["DP_状态"] = "完成"
                row["枚举架次"] = optimum[0][0]
            except TimeoutError as exc:
                row["DP_耗时_s"] = time.perf_counter() - t0
                row["DP状态数"] = None
                row["DP子集迭代数"] = None
                row["DP_状态"] = f"超时({exc})"
                row["枚举架次"] = None

        t0 = time.perf_counter()
        milp_rows, milp_info = milp_solve(f"S001@{n}", instance, drones, route, time_limit=deadline_s)
        row["MILP_耗时_s"] = time.perf_counter() - t0
        row["MILP架次"] = len(milp_rows)
        row["MILP能耗_kWh"] = sum(r["能耗_kwh"] for r in milp_rows)
        row["MILP调用次数"] = milp_info["MILP调用次数"]

        t0 = time.perf_counter()
        greedy_rows = greedy_bfd(instance, drones, route)
        row["贪心_耗时_s"] = time.perf_counter() - t0
        row["贪心架次"] = len(greedy_rows)
        row["贪心能耗_kWh"] = sum(r["能耗_kwh"] for r in greedy_rows)
        row["解析下界"] = analytic_lower_bound(instance, drones, route)

        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "规模实验.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "规模实验.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def full_lp_probe(area="S001", time_limit=300.0):
    """同一实例上比较“未剪枝 LP”和“极大子集支配剪枝 LP”的列数与耗时。"""
    drones, boxes, routes = load_inputs()
    best, candidate_rows = enumerate_candidates(boxes[area], drones, routes[area])
    result = {"服务区": area, "箱数": len(boxes[area]), "候选记录数": candidate_rows,
              "可行子集数": len(best), "LP时间上限_s": time_limit}
    for label, pruned in (("未剪枝", False), ("支配剪枝", True)):
        t0 = time.perf_counter()
        info = lp_trip_lower_bound(best, len(boxes[area]), pruned=pruned, time_limit=time_limit)
        info["耗时_s"] = time.perf_counter() - t0
        result[label] = info
        print(label, json.dumps(info, ensure_ascii=False), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "LP剪枝对照.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scaling", action="store_true", help="运行规模实验而不是真实算例对比")
    parser.add_argument("--full-lp", action="store_true", help="比较未剪枝 LP 与支配剪枝 LP")
    parser.add_argument("--sizes", default="15,17,19,21")
    parser.add_argument("--deadline", type=float, default=60.0)
    args = parser.parse_args()
    if args.scaling:
        scaling(tuple(int(x) for x in args.sizes.split(",")), deadline_s=args.deadline)
    elif args.full_lp:
        full_lp_probe(time_limit=max(args.deadline, 300.0))
    else:
        compare_real()


if __name__ == "__main__":
    main()
