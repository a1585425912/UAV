# -*- coding: utf-8 -*-
"""第四问独立复核：不读 q4_partition 的中间结果，直接从第三问原始 JSON 逐架次重算。

复核链条（每一步都用与求解脚本不同的实现路径）：
  1. 单元：逐架次取服务区并集，反复迭代到不动点（不用并查集）；
  2. 通道归属：逐条 communications 记录取 (relay_id, trip) 再去重；
  3. 峰值：对 0..22 架次 与 0..4 中继架次 的事件端点做全量扫描（不预建区间表）；
  4. 目标：显式枚举全部分区（十进制指纹去重），核对最小缺口/配置/CV 与落盘 JSON 是否一致。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "code" / "问题三_改进求解" / "plan_windows_opt.json"
OUT = ROOT / "results" / "问题四_改进求解"
CATEGORIES = ("U_A", "U_B", "U_C", "B_A", "B_B", "B_C", "R", "RB")
STOCK = {"U_A": 4, "U_B": 2, "U_C": 2, "B_A": 6, "B_B": 4, "B_C": 4, "R": 2, "RB": 6}


# ---------------------------------------------------------------- 1. 单元（迭代闭包，非并查集）
def units_by_closure(plan):
    trips = [[s["area"] for s in t["stops"]] for t in plan["transport"]]
    groups = [sorted(set(a)) for a in trips]
    changed = True
    while changed:
        changed = False
        merged = []
        for g in groups:
            hit = None
            for m in merged:
                if set(g) & set(m):
                    hit = m
                    break
            if hit is None:
                merged.append(list(g))
            else:
                hit.extend(g)
                changed = True
        # 合并后可能又与更早的组相交，再扫一轮
        groups = [sorted(set(m)) for m in merged]
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if set(groups[i]) & set(groups[j]):
                    groups[i] = sorted(set(groups[i]) | set(groups[j]))
                    groups[j] = []
                    changed = True
        groups = [g for g in groups if g]
    return sorted(tuple(g) for g in groups)


def main() -> None:
    plan = json.loads(SOURCE.read_text(encoding="utf-8"))
    units = units_by_closure(plan)
    locate = {a: ci for ci, u in enumerate(units) for a in u}
    unit_of_trip = {t["id"]: locate[t["stops"][0]["area"]] for t in plan["transport"]}
    assert sum(len(u) for u in units) == 15, "服务区被重复或遗漏"

    # ------------------------------------------------------------ 2. 中继保障归属
    serve = {}
    for row in plan["communications"]:
        rid = row.get("relay_id") or ""
        if rid:
            serve.setdefault(rid, set()).add(row["trip"])
    relay_units = {rid: {unit_of_trip[t] for t in trips} for rid, trips in serve.items()}
    relays = {r["id"]: r for r in plan["relays"]}

    n = len(units)
    trip_work = [0.0] * n
    for t in plan["transport"]:
        trip_work[unit_of_trip[t["id"]]] += t["return_s"] - t["start_s"]

    def peaks(sel):
        """sel: 单元下标集合；返回 8 类资源的峰值（全量端点扫描，无预建区间表）。"""
        # 先逐架次收集属于 sel 的运输类区间
        pool = {c: [] for c in CATEGORIES}
        for t in plan["transport"]:
            if unit_of_trip[t["id"]] not in sel:
                continue
            pool["U_" + t["model"]].append((t["start_s"], t["return_s"]))
            pool["B_" + t["model"]].append((t["start_s"], t["charge_end_s"]))
        for rid, r in relays.items():
            if relay_units[rid] & sel:
                pool["R"].append((r["depart_s"], r["relay_free_s"]))
                pool["RB"].append((r["depart_s"], r["energy_free_s"]))
        out = {}
        for cat in CATEGORIES:
            items = pool[cat]
            if not items:
                out[cat] = 0
                continue
            points = sorted({s for s, _ in items} | {e for _, e in items})
            best = 0
            for tt in points:          # 半开区间 [s,e)：同刻结束不计入
                best = max(best, sum(1 for s, e in items if s <= tt < e))
            out[cat] = best
        return out

    # 峰值实现与求解脚本对比（逐单元 + 全量）
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import q4_partition as q  # noqa: E402

    inst = q.Instance(plan)
    assert [list(u) for u in units] == [list(u) for u in inst.units], "单元划分与求解脚本不一致"
    for mask in range(1, 1 << n):
        sel = {ci for ci in range(n) if mask >> ci & 1}
        a, b = peaks(sel), inst.needs_of(sel)
        for c in CATEGORIES:
            assert a[c] == b[c], "峰值不一致 %s %s %s" % (c, a, b)

    # ------------------------------------------------------------ 4. 分区枚举（十进制指纹去重）
    def all_assignments(n, k):
        for code in range(k ** n):
            digits = []
            x = code
            for _ in range(n):
                digits.append(x % k)
                x //= k
            if len(set(digits)) == k:
                yield digits

    def merge_labels(digits):
        mapping, nxt = {}, 0
        for d in digits:
            if d not in mapping:
                mapping[d] = nxt
                nxt += 1
        return tuple(mapping[d] for d in digits)

    summary = {}
    for k in (2, 3):
        seen, best = {}, None
        for digits in all_assignments(n, k):
            key = merge_labels(digits)
            if key in seen:
                continue
            seen[key] = True
            groups = defaultdict(list)
            for ci, g in enumerate(key):
                groups[g].append(ci)
            glist = sorted(tuple(sorted(v)) for v in groups.values())
            nd = {c: 0 for c in CATEGORIES}
            work = []
            for g in glist:
                p = peaks(set(g))
                for c in CATEGORIES:
                    nd[c] += p[c]
                work.append(sum(trip_work[ci] for ci in g))
            gap = sum(max(0, nd[c] - STOCK[c]) for c in CATEGORIES)
            res = sum(nd.values())
            mean = sum(work) / k
            cv = (sum((w - mean) ** 2 for w in work) / k) ** 0.5 / mean
            obj = (gap, res, round(cv, 12))
            if best is None or obj < best[0]:
                best = (obj, glist, nd)
        summary["K%d" % k] = {"分区数": len(seen), "最优目标": best[0],
                              "最优分区": ["U%d" % i for g in best[1] for i in g],
                              "总需求": best[2]}
        print("独立复核 K=%d：有效分区 %d 个（该数应等于第二类 Stirling 数）｜最小缺口 %d｜缺口下最小配置 %d｜最优 CV %.6f"
              % (k, len(seen), best[0][0], best[0][1], best[0][2]))
        print("        最优分区：", " / ".join(
            "、".join(a for ci in g for a in units[ci]) for g in best[1]))
        print("        总需求：", {c: best[2][c] for c in CATEGORIES})

    # 与落盘 JSON 对照
    for k in (2, 3):
        rec = json.loads((OUT / ("K%d_缺口优先.json" % k)).read_text(encoding="utf-8"))
        assert rec["缺口总数"] == summary["K%d" % k]["最优目标"][0], "缺口与落盘不一致 K=%d" % k
        assert rec["配置总数"] == summary["K%d" % k]["最优目标"][1], "配置数与落盘不一致 K=%d" % k
        assert abs(rec["运输架次占用时长CV"] - summary["K%d" % k]["最优目标"][2]) < 1e-9, "CV 与落盘不一致"
        assert rec["输入SHA256"] == q.sha256_of(SOURCE), "落盘输入指纹与当前输入不一致"
        print("落盘 JSON 校验通过：K=%d 缺口 %d / 配置 %d / CV %.6f"
              % (k, rec["缺口总数"], rec["配置总数"], rec["运输架次占用时长CV"]))

    (OUT / "独立复核_原始重算.json").write_text(json.dumps(
        {"单元": [list(u) for u in units],
         "中继保障单元": {r: sorted(v) for r, v in relay_units.items()},
         "重算": summary},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写出：", OUT / "独立复核_原始重算.json")


if __name__ == "__main__":
    main()
