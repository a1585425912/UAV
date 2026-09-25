# -*- coding: utf-8 -*-
"""【已弃用·保留备查】第四问（窗口优化版）早期实现。

⚠️ 本脚本的中继复制判定已过时：它把中继架次计入“只要保障到本组任一单元”的组，
   会把跨组中继架次在每个被触及的组都复制一套，从而高估中继缺口。
   当前口径请使用同一目录下的新流水线：
       q4_partition.py → q4_baseline.py → q4_compare_export.py
       → q4_verify.py / q4_independent_check.py → q4_report.py
   新流水线输出到 results/问题四_改进求解/，本脚本输出仍为 results/问题四_窗口优化版/。
   运行本脚本会覆盖该旧目录内容，非必要请勿执行。

输入：code/问题三_改进求解/plan_windows_opt.json
输出：results/问题四_窗口优化版/（独立目录，不覆盖旧方案与旧提交工作簿）
"""
from __future__ import annotations

import csv, hashlib, json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "code" / "问题三_改进求解" / "plan_windows_opt.json"
OUT = ROOT / "results" / "问题四_窗口优化版"
CATEGORIES = ("U_A", "U_B", "U_C", "B_A", "B_B", "B_C", "R", "RB")
CAT_NAME = {"U_A": "A型运输机", "U_B": "B型运输机", "U_C": "C型运输机",
            "B_A": "A型电池", "B_B": "B型电池", "B_C": "C型电池",
            "R": "中继机", "RB": "中继能源组件"}
STOCK = {"U_A": 4, "U_B": 2, "U_C": 2, "B_A": 6, "B_B": 4, "B_C": 4, "R": 2, "RB": 6}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def components(plan):
    areas = sorted({stop["area"] for trip in plan["transport"] for stop in trip["stops"]})
    parent = {a: a for a in areas}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for trip in plan["transport"]:
        first = find(trip["stops"][0]["area"])
        for stop in trip["stops"][1:]:
            parent[find(stop["area"])] = first
    groups = defaultdict(list)
    for a in areas:
        groups[find(a)].append(a)
    result = sorted((tuple(sorted(v)) for v in groups.values()), key=lambda x: x[0])
    assert len(areas) == 15 and sum(map(len, result)) == 15
    return result


def prepare(plan):
    comp = components(plan)
    locate = {area: ci for ci, group in enumerate(comp) for area in group}
    relay_ids = sorted(r["id"] for r in plan["relays"])
    uses = defaultdict(set)
    for row in plan["communications"]:
        if row.get("relay_id"):
            uses[row["trip"]].add(row["relay_id"])
    trip_comp = {t["id"]: locate[t["stops"][0]["area"]] for t in plan["transport"]}
    relay_comp = {rid: set() for rid in relay_ids}
    for trip_id, assigned in uses.items():
        for rid in assigned:
            relay_comp[rid].add(trip_comp[trip_id])
    intervals = {cat: [] for cat in CATEGORIES}
    work = np.zeros(len(comp))
    for trip in plan["transport"]:
        ci, model = trip_comp[trip["id"]], trip["model"]
        intervals["U_" + model].append((trip["start_s"], trip["return_s"], "x", ci))
        intervals["B_" + model].append((trip["start_s"], trip["charge_end_s"], "x", ci))
        work[ci] += trip["return_s"] - trip["start_s"]
    for relay in plan["relays"]:
        rid = relay["id"]
        intervals["R"].append((relay["depart_s"], relay["relay_free_s"], "y", rid))
        intervals["RB"].append((relay["depart_s"], relay["energy_free_s"], "y", rid))
    return comp, relay_ids, relay_comp, intervals, work


def peak(items):
    """半开区间最大并发：同刻 end(-1) 先于 start(+1)。"""
    events = sorted([(s, 1) for s, e in items] + [(e, -1) for s, e in items],
                    key=lambda x: (x[0], x[1]))
    cur = best = 0
    for _, delta in events:
        cur += delta; best = max(best, cur)
    return best


def assess(assignment, prepared):
    comp, relay_ids, relay_comp, intervals, work = prepared
    needs, works = [], []
    for group in assignment:
        gs = set(group)
        works.append(float(sum(work[ci] for ci in gs)))
        row = {}
        for cat in CATEGORIES:
            taken = [(a, b) for a, b, kind, ident in intervals[cat]
                     if (ident in gs if kind == "x" else bool(relay_comp[ident] & gs))]
            row[cat] = peak(taken)
        needs.append(row)
    total = {c: sum(r[c] for r in needs) for c in CATEGORIES}
    gaps = {c: max(0, total[c] - STOCK[c]) for c in CATEGORIES}
    mean = sum(works) / len(works)
    cv = (sum((v - mean) ** 2 for v in works) / len(works)) ** .5 / mean
    return {"needs": needs, "total": total, "shortfall": gaps, "shortfall_total": sum(gaps.values()),
            "work_s": works, "cv": cv}


def solve_milp(k, prepared, gap_allowance=0):
    comp, relay_ids, relay_comp, intervals, work = prepared
    nc = len(comp); names = []
    def var(name):
        names.append(name); return len(names) - 1
    x = {(ci, g): var(("x", ci, g)) for ci in range(nc) for g in range(k)}
    y = {(rid, g): var(("y", rid, g)) for rid in relay_ids for g in range(k)}
    n = {(c, g): var(("n", c, g)) for c in CATEGORIES for g in range(k)}
    delta = {c: var(("delta", c)) for c in CATEGORIES}
    z = {g: var(("z", g)) for g in range(k)}
    count = len(names)
    integrality = np.zeros(count); lower = np.zeros(count); upper = np.full(count, np.inf)
    for idx in list(x.values()) + list(y.values()): integrality[idx] = 1; upper[idx] = 1
    for idx in list(n.values()) + list(delta.values()): integrality[idx] = 1; upper[idx] = 50
    rows, cols, vals, lows, highs = [], [], [], [], []
    def add(coef, lo=-np.inf, hi=np.inf):
        ri = len(lows)
        for col, v in coef.items():
            if v: rows.append(ri); cols.append(col); vals.append(v)
        lows.append(lo); highs.append(hi)
    for ci in range(nc): add({x[ci, g]: 1 for g in range(k)}, 1, 1)
    for g in range(k): add({x[ci, g]: 1 for ci in range(nc)}, 1)
    for rid in relay_ids:
        for g in range(k):
            for ci in relay_comp[rid]: add({y[rid, g]: 1, x[ci, g]: -1}, 0)
            add({y[rid, g]: 1, **{x[ci, g]: -1 for ci in relay_comp[rid]}}, hi=0)
    for cat in CATEGORIES:
        times = sorted({s for s, _, _, _ in intervals[cat]})
        for g in range(k):
            for t in times:
                coef = {n[cat, g]: 1}
                for s, e, kind, ident in intervals[cat]:
                    if s <= t < e:
                        col = x[ident, g] if kind == "x" else y[ident, g]
                        coef[col] = coef.get(col, 0) - 1
                add(coef, 0)
    for cat in CATEGORIES:
        add({delta[cat]: 1, **{n[cat, g]: -1 for g in range(k)}}, -STOCK[cat])
    hours = work / 3600
    possible = {0.0}
    for v in hours: possible |= {old + float(v) for old in list(possible)}
    for g in range(k):
        for w0 in possible:
            add({z[g]: 1, **{x[ci, g]: -2 * w0 * hours[ci] for ci in range(nc)}}, -w0 * w0)
    A = coo_matrix((vals, (rows, cols)), shape=(len(lows), count)).tocsr()
    base = LinearConstraint(A, lows, highs); bounds = Bounds(lower, upper)
    def run(c, extra=()):
        res = milp(np.asarray(c, dtype=float), integrality=integrality, bounds=bounds,
                   constraints=[base, *extra], options={"time_limit": 180, "mip_rel_gap": 1e-8})
        if res.x is None or res.status != 0:
            raise RuntimeError("K=%d MILP 失败: %s" % (k, res.message))
        return res
    def fix(indices, value):
        row = coo_matrix((np.ones(len(indices)), (np.zeros(len(indices)), indices)), shape=(1, count)).tocsr()
        return LinearConstraint(row, value - 1e-6, value + 1e-6)
    dc = list(delta.values()); rc = list(n.values())
    c = np.zeros(count); c[dc] = 1
    first = run(c); min_gap = round(sum(first.x[i] for i in dc))
    if gap_allowance == 0:
        gap_bound = fix(dc, min_gap)
    else:
        row = coo_matrix((np.ones(len(dc)), (np.zeros(len(dc)), dc)), shape=(1, count)).tocsr()
        gap_bound = LinearConstraint(row, 0, min_gap + gap_allowance + 1e-6)
    c = np.zeros(count); c[rc] = 1
    second = run(c, [gap_bound]); min_res = round(sum(second.x[i] for i in rc))
    c = np.zeros(count); c[list(z.values())] = 1
    extra = [gap_bound] + ([fix(rc, min_res)] if gap_allowance == 0 else [])
    final = run(c, extra)
    assignment = [tuple(sorted(ci for ci in range(nc) if final.x[x[ci, g]] > .5)) for g in range(k)]
    facts = assess(assignment, prepared)
    meta = {"milp_status": int(final.status), "mip_gap": float(final.mip_gap),
            "minimum_shortfall": min_gap, "minimum_resources_given_shortfall": min_res,
            "binary_components": nc, "constraint_rows": len(lows)}
    return assignment, facts, meta


def all_partitions(n, k):
    """n 个单元分成恰好 k 个非空无序组的规范枚举。"""
    items = list(range(n))
    def rec(rest, k):
        if k == 1:
            yield [tuple(rest)]; return
        first = rest[0]
        for size in range(1, len(rest) - k + 2):
            for combo in combinations(rest[1:], size - 1):
                group = (first,) + combo
                remain = [x for x in rest if x not in group]
                for sub in rec(remain, k - 1):
                    yield [group] + sub
    yield from rec(items, k)


def enumerate_all(k, prepared):
    comp = prepared[0]
    rows = []
    for assignment in all_partitions(len(comp), k):
        f = assess(assignment, prepared)
        rows.append({"assignment": assignment, "shortfall_total": f["shortfall_total"],
                     "total": sum(f["total"].values()), "cv": f["cv"], "facts": f})
    best_gap = min(r["shortfall_total"] for r in rows)
    within = [r for r in rows if r["shortfall_total"] == best_gap]
    best_res = min(r["total"] for r in within)
    within2 = [r for r in within if r["total"] == best_res]
    best_cv = min(r["cv"] for r in within2)
    return rows, {"best_gap": best_gap, "best_res_given_gap": best_res,
                  "best_cv_given_gap_res": best_cv, "count": len(rows)}


def to_output(k, name, assignment, facts, meta, prepared, sha, q3_metrics):
    comp = prepared[0]
    groups = [sorted(a for ci in idxs for a in comp[ci]) for idxs in assignment]
    assert sorted(a for g in groups for a in g) == sorted(a for c in comp for a in c)
    return {"K": k, "方案": name, "输入": str(SOURCE.relative_to(ROOT)), "输入SHA256": sha,
            "第三问指标": {"完成时间_s": q3_metrics["makespan_s"], "运输架次": q3_metrics["transport_sorties"],
                        "中继架次": q3_metrics["relay_sorties"], "通信缺口_s": q3_metrics["communication_gap_s"]},
            "任务组": groups, "不可分单元": [list(c) for c in comp],
            "资源需求": facts["needs"], "资源总需求": facts["total"], "库存": STOCK,
            "资源缺口": facts["shortfall"], "缺口总数": facts["shortfall_total"],
            "库存剩余": {c: max(0, STOCK[c] - facts["total"][c]) for c in STOCK},
            "各组运输架次占用时长_s": facts["work_s"], "作业量CV": facts["cv"], "整数规划": meta}


if __name__ == "__main__":
    sha = sha256(SOURCE)
    plan = json.loads(SOURCE.read_text(encoding="utf-8"))
    prepared = prepare(plan)
    comp = prepared[0]
    print("输入:", SOURCE.name, "SHA256:", sha)
    print("第三问:", plan["metrics"])
    print("不可分单元 %d 个:" % len(comp), [list(c) for c in comp])
    print("中继架次 -> 保障单元:", {rid: sorted(s) for rid, s in prepared[2].items()})
    OUT.mkdir(parents=True, exist_ok=True)
    answers = []
    for k in (2, 3):
        for name, allowance in (("缺口优先", 0), ("兼顾均衡", 4)):
            assignment, facts, meta = solve_milp(k, prepared, allowance)
            out = to_output(k, name, assignment, facts, meta, prepared, sha, plan["metrics"])
            (OUT / ("K%d_%s.json" % (k, name))).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            answers.append(out)
            print("K=%d %s: 缺口 %d %s | CV %.6f | 配置总数 %d | 组 %s" % (
                k, name, facts["shortfall_total"], {c: v for c, v in facts["shortfall"].items() if v},
                facts["cv"], sum(facts["total"].values()), out["任务组"]))
    enum_records = {}
    for k in (2, 3):
        rows, summary = enumerate_all(k, prepared)
        enum_records[str(k)] = summary
        with (OUT / ("枚举复核_K%d.csv" % k)).open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh); w.writerow(["K", "分组(单元下标)", "缺口总数", "配置总数", "作业量CV"])
            for r in rows:
                w.writerow([k, ";".join(",".join(map(str, gp)) for gp in r["assignment"]),
                            r["shortfall_total"], r["total"], round(r["cv"], 9)])
        print("枚举 K=%d: %d 种；最小缺口 %d；缺口下最小配置 %d；再最小 CV %.6f" % (
            k, summary["count"], summary["best_gap"], summary["best_res_given_gap"], summary["best_cv_given_gap_res"]))
    with (OUT / "问题四方案比较.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["K", "方案", "缺口总数", "配置总数", "作业量CV", "缺口明细", "任务组"])
        for row in answers:
            w.writerow([row["K"], row["方案"], row["缺口总数"], sum(row["资源总需求"].values()),
                        round(row["作业量CV"], 9),
                        "、".join("%s:%d" % (CAT_NAME[c], v) for c, v in row["资源缺口"].items() if v) or "无",
                        " / ".join("、".join(g) for g in row["任务组"])])
    detail = []
    for plan_row in [a for a in answers if a["方案"] == "缺口优先"]:
        for gi, (areas, need) in enumerate(zip(plan_row["任务组"], plan_row["资源需求"]), 1):
            row = {"K": plan_row["K"], "任务组编号": "G%d" % gi, "服务区列表": "、".join(areas)}
            for c in CATEGORIES: row[CAT_NAME[c]] = need[c]
            row["运输架次占用时长_s"] = plan_row["各组运输架次占用时长_s"][gi - 1]
            detail.append(row)
    with (OUT / "问题四主方案逐组资源.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detail[0])); w.writeheader(); w.writerows(detail)
    (OUT / "输入指纹.json").write_text(json.dumps({
        "输入文件": str(SOURCE), "输入SHA256": sha, "第三问指标": plan["metrics"],
        "不可分单元": [list(c) for c in comp], "中继架次": prepared[1],
        "中继架次保障的单元": {rid: sorted(s) for rid, s in prepared[2].items()},
        "资源库存": STOCK, "枚举复核": enum_records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("输出目录:", OUT)
