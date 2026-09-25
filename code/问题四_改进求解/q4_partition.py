# -*- coding: utf-8 -*-
"""第四问（改进求解）：固定第三问已连续通信认证的联合方案，只决定服务区分组与各组资源配置。

唯一输入（显式传入，默认见 DEFAULT_SOURCE）：
    code/问题三_改进求解/plan_windows_opt.json   （22 运输架次 + 4 中继架次，联合完成时间 8915.079576916525 s）
输出目录（显式传入，默认见 DEFAULT_OUT）：
    results/问题四_改进求解/                     （独立目录，不写旧方案与旧提交工作簿）

口径（本轮固定，不允许改动第三问任何调度）：
  1) 不可拆分单元：同一运输架次访问的多个服务区必须同组 -> 并查集连通分量（从输入重新推导）。
  2) 中继复制：中继架次 -> communications 中被其保障的运输架次 -> 运输架次所属单元 -> 单元所属任务组。
     同一中继架次服务了不同任务组时，每个组都独立配置一套完整的中继服务能力
     （实体中继机与能源组件均不跨组共享）。禁止用“静态悬停位置数”代替“中继架次”。
  3) 最大同时占用（半开区间 [start, end)，同刻 end 先于 start）：
       运输无人机 A/B/C : [出发, 返航)
       同型共享电池     : [出发, 充满)
       中继无人机       : [出发, 返航 + 题目架次周转时间)
       中继能源组件     : [出发, 充满)
     各组需求相加后与实际库存逐类比较。
  4) 目标层次：先最小化各类资源正缺口之和；再在缺口不变下最小化配置总数；
     最后比较工作量均衡（工作量 = Σ(返航−出发)，称“运输架次占用时长”，含准备/装载/交接）。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "code" / "问题三_改进求解" / "plan_windows_opt.json"
DEFAULT_OUT = ROOT / "results" / "问题四_改进求解"

CATEGORIES = ("U_A", "U_B", "U_C", "B_A", "B_B", "B_C", "R", "RB")
CAT_NAME = {
    "U_A": "A型运输无人机", "U_B": "B型运输无人机", "U_C": "C型运输无人机",
    "B_A": "A型共享电池", "B_B": "B型共享电池", "B_C": "C型共享电池",
    "R": "中继无人机", "RB": "中继能源组件",
}
# 附录1：共配置 8 架实体运输无人机、配套共享电池组、中继无人机、可更换能源组件。
# 库存取值与 数据/无人机应急物资运输基础数据 一致（沿用问题三/四既定口径）。
STOCK = {"U_A": 4, "U_B": 2, "U_C": 2, "B_A": 6, "B_B": 4, "B_C": 4, "R": 2, "RB": 6}
EXPECTED = {
    2: {"gap": 2, "detail": "B型运输机 1 + 中继机 1", "partition": ["S012", "其余 14 个服务区"]},
    3: {"gap": 4, "detail": "B型运输机 2 + 中继机 2", "partition": ["S012", "S013", "其余 13 个服务区"]},
}


# ---------------------------------------------------------------- 输入与基础结构
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    for key in ("transport", "relays", "communications", "metrics"):
        if key not in plan:
            raise SystemExit("输入缺少字段: %s" % key)
    return plan


def build_units(plan: dict) -> list[tuple[str, ...]]:
    """不可拆分单元 = 同一运输架次访问的服务区连通分量（并查集，从输入推导）。"""
    areas = sorted({stop["area"] for trip in plan["transport"] for stop in trip["stops"]})
    parent = {a: a for a in areas}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for trip in plan["transport"]:
        first = find(trip["stops"][0]["area"])
        for stop in trip["stops"][1:]:
            parent[find(stop["area"])] = first
    buckets = defaultdict(list)
    for a in areas:
        buckets[find(a)].append(a)
    units = [tuple(sorted(v)) for v in buckets.values()]
    units.sort(key=lambda u: u[0])
    assert sorted(a for u in units for a in u) == areas, "服务区未恰好覆盖一次"
    return units


def relay_coverage(plan: dict, units) -> tuple[list[str], dict[str, set[int]], dict[str, list[str]], dict[str, list[str]]]:
    """中继架次 -> 被保障运输架次 -> 任务单元；并给出数据结构用于核对。"""
    locate = {area: ci for ci, unit in enumerate(units) for area in unit}
    relay_sorties = [r["id"] for r in plan["relays"]]
    trips_by_relay = {rid: [] for rid in relay_sorties}
    for row in plan["communications"]:
        rid = row.get("relay_id") or ""
        if rid and row["trip"] not in trips_by_relay[rid]:
            trips_by_relay[rid].append(row["trip"])
    trip_unit = {t["id"]: locate[t["stops"][0]["area"]] for t in plan["transport"]}
    units_by_relay = {rid: [] for rid in relay_sorties}
    for rid in relay_sorties:
        units_by_relay[rid] = sorted({trip_unit[t] for t in trips_by_relay[rid]})
    coverage = {rid: set(units_by_relay[rid]) for rid in relay_sorties}
    for rid, us in coverage.items():
        assert us, "中继架次 %s 未保障任何运输架次" % rid
    return relay_sorties, coverage, trips_by_relay, units_by_relay


# ---------------------------------------------------------------- 资源占用区间
def build_intervals(plan: dict, units, locate, trip_unit):
    """返回 8 类资源的时间区间：kind='x' 按单元归属，kind='y' 按中继架次复制。"""
    intervals = {cat: [] for cat in CATEGORIES}
    work = [0.0] * len(units)
    for trip in plan["transport"]:
        ci, model = trip_unit[trip["id"]], trip["model"]
        intervals["U_" + model].append((trip["start_s"], trip["return_s"], "x", ci))
        intervals["B_" + model].append((trip["start_s"], trip["charge_end_s"], "x", ci))
        work[ci] += trip["return_s"] - trip["start_s"]
    for relay in plan["relays"]:
        rid = relay["id"]
        intervals["R"].append((relay["depart_s"], relay["relay_free_s"], "y", rid))
        intervals["RB"].append((relay["depart_s"], relay["energy_free_s"], "y", rid))
    return intervals, work


def peak_sweep(items) -> int:
    """半开区间 [s,e) 的最大并发：在同一时刻 t，t=e 的区间已释放，t=s 的区间已占用。

    排序键取 (时刻, 增量)，增量 -1（释放）排在 +1（占用）之前，等价于“同刻结束先于开始”。
    """
    events = []
    for s, e in items:
        events.append((float(s), 1))
        events.append((float(e), -1))
    events.sort(key=lambda ev: (ev[0], ev[1]))
    cur = best = 0
    for _, delta in events:
        cur += delta
        if cur > best:
            best = cur
    return best


# 独立核验用实现：把时间轴切成“段”，逐段统计覆盖区间数，不使用事件扫描
def peak_independent(items) -> int:
    """与 peak_sweep 不同的实现路径：端点排序后逐段(segment)求覆盖数。"""
    if not items:
        return 0
    cuts = sorted({float(s) for s, _ in items} | {float(e) for _, e in items})
    best = 0
    for left, right in zip(cuts, cuts[1:]):
        if right <= left:
            continue
        # 段 (left, right] 内覆盖数恒定（区间端点为全部切点）
        mid = 0.5 * (left + right)
        cnt = sum(1 for s, e in items if float(s) <= mid < float(e))
        if cnt > best:
            best = cnt
    return best


# ---------------------------------------------------------------- 单元层面预计算
class Instance:
    def __init__(self, plan: dict):
        self.plan = plan
        self.units = build_units(plan)
        self.locate = {a: ci for ci, u in enumerate(self.units) for a in u}
        self.trip_unit = {t["id"]: self.locate[t["stops"][0]["area"]] for t in plan["transport"]}
        self.relay_sorties, self.relay_units, self.trips_by_relay, self.units_by_relay = relay_coverage(plan, self.units)
        self.intervals, self.work = build_intervals(plan, self.units, self.locate, self.trip_unit)
        self.n = len(self.units)
        self._cache: dict[frozenset, dict] = {}
        self._relay_cache: dict[frozenset, dict] = {}

    # 单元集合 -> 各类资源峰值（中继按“每组独立复制”计）
    def needs_of(self, subset) -> dict:
        """subset: 作为矩阵列的任务组（由单元组成的可迭代对象，可含多个单元）。

        运输类资源：落在本组内的单元直接计入；
        中继类资源：中继架次只要保障到本组任一单元，本组就需要独立配置该架次。
        若该架次跨越多个任务组，则每个相关组各配置一整套，不做部分配置。
        """
        key = frozenset(subset)
        if key in self._cache:
            return dict(self._cache[key])
        rows = {}
        for cat in CATEGORIES:
            items = []
            for s, e, kind, ident in self.intervals[cat]:
                if kind == "x":
                    if ident in key:
                        items.append((s, e))
                else:
                    if self.relay_units[ident] & key:
                        items.append((s, e))
            rows[cat] = peak_sweep(items)
        self._cache[key] = rows
        return dict(rows)

    # 中继复制明细（用于核对“每个中继架次在每组各复制一份”）
    def relay_copies(self, subset) -> list[dict]:
        key = frozenset(subset)
        out = []
        for rid in self.relay_sorties:
            hit_units = self.relay_units[rid] & key
            if hit_units:
                relay = next(r for r in self.plan["relays"] if r["id"] == rid)
                out.append({
                    "中继架次": rid,
                    "实体机": relay.get("relay_id", ""),
                    "能源组件": relay.get("energy_id", ""),
                    "悬停点": relay.get("site", ""),
                    "被保障运输架次": sorted(self.trips_by_relay[rid]),
                    "本架次保障的全部单元": sorted(self.relay_units[rid]),
                    "本组命中服务区": sorted(a for ci in hit_units for a in self.units[ci]),
                })
        return out

    def relay_need(self, subset, cat) -> int:
        key = frozenset(subset)
        rows = self.needs_of(key)
        return rows[cat]


def gaps_of(needs: dict) -> dict:
    return {c: max(0, needs[c] - STOCK[c]) for c in CATEGORIES}


def partition_facts(inst: Instance, groups: tuple) -> dict:
    """groups: 以单元下标元组表示的任务组划分（无序）。"""
    needs, works = [], []
    for g in groups:
        needs.append(inst.needs_of(g))
        works.append(float(sum(inst.work[ci] for ci in g)))
    total = {c: sum(r[c] for r in needs) for c in CATEGORIES}
    gaps = gaps_of(total)
    k = len(groups)
    mean = sum(works) / k if k else 0.0
    if k and mean > 0:
        cv = (sum((w - mean) ** 2 for w in works) / k) ** 0.5 / mean
    else:
        cv = 0.0
    return {
        "needs": needs,
        "total": total,
        "shortfall": gaps,
        "shortfall_total": sum(gaps.values()),
        "available_after": {c: STOCK[c] - total[c] for c in CATEGORIES},
        "work_s": works,
        "cv": cv,
        "resource_total": sum(total.values()),
    }


# ---------------------------------------------------------------- 枚举求解
def canonical_partitions(n: int, k: int):
    """把 n 个单元分成恰好 k 个非空无序组（规范枚举，无重复无遗漏）。"""
    items = list(range(n))

    def rec(rest, k_left):
        if k_left == 1:
            yield [tuple(rest)]
            return
        first = rest[0]
        for size in range(1, len(rest) - k_left + 2):
            for combo in combinations(rest[1:], size - 1):
                group = (first,) + combo
                remain = [x for x in rest if x not in group]
                for sub in rec(remain, k_left - 1):
                    yield [group] + sub

    return rec(items, k)


def count_partitions(n: int, k: int) -> int:
    """第二类 Stirling 数 S(n,k)：n 个可区分单元分成恰好 k 个非空无序组。"""
    if k < 1 or n < k:
        return 0
    if k == 1 or n == k:
        return 1
    return k * count_partitions(n - 1, k) + count_partitions(n - 1, k - 1)


def enumerate_optimum(inst: Instance, k: int) -> dict:
    """方法A：规范枚举全部分区（K=2: 63/127，K=3: 301/966），三目标字典序最优。"""
    rows = []
    for groups in canonical_partitions(inst.n, k):
        facts = partition_facts(inst, tuple(groups))
        rows.append((tuple(tuple(g) for g in groups), facts))
    best_gap = min(f["shortfall_total"] for _, f in rows)
    stage1 = [(g, f) for g, f in rows if f["shortfall_total"] == best_gap]
    best_res = min(f["resource_total"] for _, f in stage1)
    stage2 = [(g, f) for g, f in stage1 if f["resource_total"] == best_res]
    best_cv = min(f["cv"] for _, f in stage2)
    stage3 = [(g, f) for g, f in stage2 if abs(f["cv"] - best_cv) < 1e-12]
    return {
        "method": "A_规范枚举",
        "partitions": len(rows),
        "best_gap": best_gap,
        "best_resources": best_res,
        "best_cv": best_cv,
        "optima": stage3,
        "rows": rows,
        "stage1_count": len(stage1),
        "stage2_count": len(stage2),
    }


def dfs_optimum(inst: Instance, k: int) -> dict:
    """方法B：逐单元指派的分支限界（对称性破缺 + 已封闭组固定缺口下界剪枝）。

    与规范枚举的实现路径完全不同：这里在“单元逐个落位”的搜索树上做深度优先，
    用已封闭任务组的确定峰值构造目标下界剪枝，不预先生成任何分区。
    """
    n = inst.n
    stack: list[set] = []          # 进入某组即压栈，离开该组即弹栈（第 i 组 = 第 i 层）
    best = {"obj": None, "groups": None, "leaves": 0, "nodes": 0, "pruned": 0}

    def gap_of(units) -> int:
        rows = inst.needs_of(tuple(units))
        return sum(max(0, rows[c] - STOCK[c]) for c in CATEGORIES)

    def rec(idx, used):
        best["nodes"] += 1
        if idx == n:
            best["leaves"] += 1
            groups = tuple(tuple(sorted(g)) for g in stack if g)
            if len(groups) != k:
                return
            ordered = tuple(sorted(groups))
            facts = partition_facts(inst, ordered)
            obj = (facts["shortfall_total"], facts["resource_total"], round(facts["cv"], 12))
            if best["obj"] is None or obj < best["obj"]:
                best["obj"], best["groups"] = obj, ordered
            return
        for g in range(min(used + 1, k)):
            start = g == used           # 进入一个全新的组
            if start:
                stack.append(set())
            stack[g].add(idx)
            bound = sum(gap_of(s) for s in stack)   # 封闭组 = 确定值；开放组 = 下界
            if best["obj"] is not None and bound >= best["obj"][0]:
                best["pruned"] += 1
            else:
                rec(idx + 1, used + 1 if start else used)
            stack[g].discard(idx)
            if start:
                stack.pop()

    stack.append({0})
    rec(1, 1)
    assert best["groups"] is not None, "分支限界未找到可行分区"
    facts = partition_facts(inst, best["groups"])
    return {
        "method": "B_分支限界",
        "partitions": best["leaves"],
        "nodes": best["nodes"],
        "pruned": best["pruned"],
        "best_gap": facts["shortfall_total"],
        "best_resources": facts["resource_total"],
        "best_cv": facts["cv"],
        "best_groups": [list(g) for g in best["groups"]],
    }


# ---------------------------------------------------------------- 输出
def unit_name(inst: Instance, ci: int) -> str:
    return "、".join(inst.units[ci])


def partition_to_areas(inst: Instance, groups) -> list[list[str]]:
    return [sorted(a for ci in g for a in inst.units[ci]) for g in groups]


def row_record(inst: Instance, k: int, name: str, groups, facts, gap_allowance) -> dict:
    return {
        "K": k,
        "方案": name,
        "缺口预算": gap_allowance,
        "不可拆分单元": [list(u) for u in inst.units],
        "任务组（单元下标）": [list(g) for g in groups],
        "任务组（服务区）": partition_to_areas(inst, groups),
        "各组资源需求": {CAT_NAME[c]: [facts["needs"][gi][c] for gi in range(k)] for c in CATEGORIES},
        "资源总需求": {CAT_NAME[c]: facts["total"][c] for c in CATEGORIES},
        "库存": {CAT_NAME[c]: STOCK[c] for c in CATEGORIES},
        "资源缺口": {CAT_NAME[c]: facts["shortfall"][c] for c in CATEGORIES},
        "缺口总数": facts["shortfall_total"],
        "库存剩余（可为负=缺口）": {CAT_NAME[c]: facts["available_after"][c] for c in CATEGORIES},
        "各组运输架次占用时长_s": facts["work_s"],
        "运输架次占用时长CV": facts["cv"],
        "配置总数": facts["resource_total"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="第四问：固定第三问方案求 2/3 组分区与资源配置")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE), help="第三问联合方案 JSON（唯一输入）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="独立输出目录")
    ap.add_argument("--balance-gap-budget", type=int, default=2, help="均衡备选允许的额外缺口")
    args = ap.parse_args()

    source = Path(args.source).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    # 目录内只保留本脚本产物；旧版遗留的同名中间文件一并清理（仅限本实验目录内）
    for stale in ("问题四方案比较.csv", "问题四逐组资源.csv"):
        target = out / stale
        if target.exists():
            target.unlink()
            print("已清理旧版遗留文件：", target)

    fingerprint = sha256_of(source)
    plan = load_plan(source)
    inst = Instance(plan)
    metrics = plan["metrics"]

    header = {
        "脚本": str(Path(__file__).resolve()),
        "唯一输入": str(source),
        "输入SHA256": fingerprint,
        "输入规模": {"运输架次": len(plan["transport"]), "中继架次": len(plan["relays"]),
                     "通信记录": len(plan["communications"]), "服务区": len(inst.locate)},
        "第三问指标": metrics,
        "资源库存": STOCK,
        "计时口径": {
            "运输无人机": "[出发, 返航)",
            "同型共享电池": "[出发, 充满)",
            "中继无人机": "[出发, 返航+架次周转时间)",
            "中继能源组件": "[出发, 充满)",
            "半开区间": "同刻结束先于开始",
            "工作量": "Σ(返航−出发)=运输架次占用时长（含准备、装载与交接）",
        },
    }

    print("=" * 100)
    print("唯一输入 :", source)
    print("SHA256   :", fingerprint)
    print("第三问    : 完成时间 %.6f s | 运输 %d 架次 | 中继 %d 架次 | 通信缺口 %.1f s"
          % (metrics["makespan_s"], metrics["transport_sorties"], metrics["relay_sorties"],
             metrics["communication_gap_s"]))
    print("不可拆分单元 %d 个（预期 7 个，本输入实际推导得到 %d 个）" % (inst.n, inst.n))
    for ci, u in enumerate(inst.units):
        trips = sorted(t["id"] for t in plan["transport"] if inst.trip_unit[t["id"]] == ci)
        print("   U%d: %-28s 运输架次 %s" % (ci, unit_name(inst, ci), ",".join(trips)))
    print("-" * 100)
    print("中继架次 -> 保障的运输架次 -> 单元：")
    for rid in inst.relay_sorties:
        relay = next(r for r in plan["relays"] if r["id"] == rid)
        print("   %s (实体机 %s / 能源 %s / 悬停 %s): 架次 %s -> 单元 %s"
              % (rid, relay.get("relay_id"), relay.get("energy_id"), relay.get("site"),
                 ",".join(sorted(inst.trips_by_relay[rid])), inst.units_by_relay[rid]))
    print("=" * 100)
    trip_map = {("U_" + t["model"], t["start_s"], t["return_s"], inst.trip_unit[t["id"]]): t["id"]
                for t in plan["transport"]}
    for cat in ("U_A", "U_B", "U_C", "B_A", "B_B", "B_C"):
        print("校准 %s：15 区合并执行峰值 = %d；逐架次区间 = %s" % (
            cat, inst.needs_of(frozenset(range(inst.n)))[cat],
            ", ".join("%s[%.2f,%.2f)" % (trip_map.get((cat, s, e, i), "U%d" % i), s, e)
                      for s, e, kind, i in sorted(inst.intervals[cat]) if kind == "x")))
    for k in (2, 3):
        exp = EXPECTED[k]
        print("预期校核 K=%d: 最小缺口 %d（%s），缺口优先分区 %s" % (k, exp["gap"], exp["detail"], exp["partition"]))

    results = []
    enumerations = {}
    for k in (2, 3):
        t0 = time.time()
        enum = enumerate_optimum(inst, k)
        t1 = time.time()
        bnb = dfs_optimum(inst, k)
        t2 = time.time()
        enumerations[k] = {"枚举": enum, "分支限界": bnb,
                           "枚举耗时_s": t1 - t0, "分支限界耗时_s": t2 - t1}
        print("-" * 100)
        print("K=%d 规范枚举：分区数 %d（理论上限 %d）| 最小缺口 %d | 缺口下最小配置 %d | 再最小 CV %.6f"
              % (k, enum["partitions"], count_partitions(inst.n, k), enum["best_gap"],
                 enum["best_resources"], enum["best_cv"]))
        print("K=%d 分支限界：枚举节点 %d | 最小缺口 %d | 配置 %d | CV %.6f  [%.2fs / %.2fs]"
              % (k, bnb["partitions"], bnb["best_gap"], bnb["best_resources"], bnb["best_cv"],
                 t1 - t0, t2 - t1))
        assert (enum["best_gap"], enum["best_resources"]) == (bnb["best_gap"], bnb["best_resources"]), \
            "K=%d 两种精确方法不一致" % k
        assert abs(enum["best_cv"] - bnb["best_cv"]) < 1e-9, (
            "K=%d CV 不一致 枚举=%.9f 分支限界=%.9f 分支限界分区=%s"
            % (k, enum["best_cv"], bnb["best_cv"], bnb.get("best_groups")))
        best_g, best_f = min(enum["optima"], key=lambda item: item[1]["cv"])
        print("K=%d 缺口优先最优分区数 %d：%s" % (k, len(enum["optima"]), " ; ".join(
            " / ".join("、".join(sorted(a for ci in g for a in inst.units[ci])) for g in gs)
            for gs, _ in enum["optima"][:6])))
        print("K=%d 缺口优先最优分区（单元）：%s" % (k, " / ".join("U{%s}" % ",".join(map(str, g)) for g in best_g)))
        print("K=%d 各类资源：%s" % (k, " ".join(
            "%s %d/%d%s" % (CAT_NAME[c], best_f["total"][c], STOCK[c],
                            ("(缺口%d)" % best_f["shortfall"][c]) if best_f["shortfall"][c] else "")
            for c in CATEGORIES)))
        print("K=%d 峰值下界（全部 15 个服务区合并执行）：%s" % (
            k, " ".join("%s %d" % (CAT_NAME[c], inst.needs_of(frozenset(range(inst.n)))[c]) for c in CATEGORIES)))
        print("K=%d 单单元自成一组的峰值：%s" % (k, "; ".join(
            "U%d(%s)=%s" % (ci, unit_name(inst, ci),
                            ",".join("%s%d" % (c, inst.needs_of(frozenset([ci]))[c]) for c in CATEGORIES))
            for ci in range(inst.n))))
        if enum["best_gap"] != EXPECTED[k]["gap"]:
            print("!! K=%d 最小缺口 %d 与预期 %d 相差 %d：见 口径复核.md 的来源/归属/边界/复制规则逐项检查"
                  % (k, enum["best_gap"], EXPECTED[k]["gap"], enum["best_gap"] - EXPECTED[k]["gap"]))

        # 只在本脚本内产出“缺口优先”主方案；均衡档位统一由 q4_baseline.py 定义并覆盖，
        # 避免同一目录出现两套“均衡”定义。
        for name, allowance in (("缺口优先", 0),):
            if allowance == 0:
                rows = enum["optima"]
                gap = enum["best_gap"]
                res = enum["best_resources"]
                cv = enum["best_cv"]
            else:
                cand = [(g, f) for g, f in enum["rows"]
                        if f["shortfall_total"] <= enum["best_gap"] + allowance]
                # 均衡优先：先在缺口预算内最小化 CV，再最小化缺口与配置
                cv = min(f["cv"] for _, f in cand)
                rows = [(g, f) for g, f in cand if abs(f["cv"] - cv) < 1e-12]
                gap = min(f["shortfall_total"] for _, f in rows)
                rows = [(g, f) for g, f in rows if f["shortfall_total"] == gap]
                res = min(f["resource_total"] for _, f in rows)
                rows = [(g, f) for g, f in rows if f["resource_total"] == res]
            for gi, (groups, facts) in enumerate(rows):
                rec = row_record(inst, k, name if len(rows) == 1 else "%s#%d" % (name, gi + 1),
                                 groups, facts, allowance)
                rec["输入SHA256"] = fingerprint
                rec["输入"] = str(source.relative_to(ROOT)) if str(source).startswith(str(ROOT)) else str(source)
                rec["平行最优解个数"] = len(rows)
                results.append((rec, groups, facts))
                print("   K=%d %-10s 缺口 %d | 配置 %d | CV %.6f | 组 %s"
                      % (k, rec["方案"], rec["缺口总数"], rec["配置总数"], rec["运输架次占用时长CV"],
                         " / ".join("、".join(g) for g in rec["任务组（服务区）"])))

    # ---- 缺口归因
    attribution = {}
    for rec, groups, facts in results:
        if rec["方案"].startswith("缺口优先"):
            for c in CATEGORIES:
                if facts["shortfall"][c] > 0:
                    occ = [(gi, facts["needs"][gi][c]) for gi in range(rec["K"])]
                    attribution.setdefault(rec["K"], {})[CAT_NAME[c]] = {
                        "缺口": facts["shortfall"][c], "库存": STOCK[c], "总需求": facts["total"][c],
                        "各组占用": {("G%d" % (gi + 1)): v for gi, v in occ},
                    }

    # ---- 落盘
    (out / "输入指纹.json").write_text(json.dumps(header, ensure_ascii=False, indent=2), encoding="utf-8")

    by_plan = defaultdict(list)
    for rec, groups, facts in results:
        by_plan[(rec["K"], rec["方案"].split("#")[0])].append((rec, groups, facts))

    written = []
    for (k, name), items in sorted(by_plan.items()):
        for rec, groups, facts in items:
            payload = dict(rec)
            if name == "缺口优先":
                payload["中继复制明细"] = {("G%d" % (gi + 1)): inst.relay_copies(g) for gi, g in enumerate(groups)}
                payload["缺口归因"] = attribution.get(k, {})
                payload["预期校核"] = EXPECTED[k]
                payload["枚举复核"] = {
                    "规范枚举分区数": enumerations[k]["枚举"]["partitions"],
                    "理论分区数": count_partitions(inst.n, k),
                    "分支限界节点数": enumerations[k]["分支限界"]["partitions"],
                    "枚举最小缺口": enumerations[k]["枚举"]["best_gap"],
                    "分支限界最小缺口": enumerations[k]["分支限界"]["best_gap"],
                    "枚举缺口下最小配置": enumerations[k]["枚举"]["best_resources"],
                    "分支限界缺口下配置": enumerations[k]["分支限界"]["best_resources"],
                    "枚举最优CV": enumerations[k]["枚举"]["best_cv"],
                    "分支限界最优CV": enumerations[k]["分支限界"]["best_cv"],
                    "缺口下并行的分区数": enumerations[k]["枚举"]["stage1_count"],
                    "缺口+配置下并行的分区数": enumerations[k]["枚举"]["stage2_count"],
                }
            path = out / ("K%d_%s.json" % (k, rec["方案"].replace("#", "_")))
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(path)

    # 枚举全表（含三目标），供独立复核
    for k in (2, 3):
        path = out / ("枚举全表_K%d.csv" % k)
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["K", "分区(单元下标)", "分区(服务区)", "缺口总数", "配置总数",
                        "运输架次占用时长CV", *["需求_%s" % CAT_NAME[c] for c in CATEGORIES]])
            for groups, facts in enumerations[k]["枚举"]["rows"]:
                w.writerow([k,
                            ";".join(",".join(map(str, g)) for g in groups),
                            " / ".join("、".join(sorted(a for ci in g for a in inst.units[ci])) for g in groups),
                            facts["shortfall_total"], facts["resource_total"], round(facts["cv"], 9),
                            *[facts["total"][c] for c in CATEGORIES]])
        written.append(path)

    # 方案比较 + 逐组资源（三档统一由 q4_baseline.py 写出，这里不再生成重复口径的文件）

    # 中继复制明细 CSV
    relay_path = out / "中继复制明细.csv"
    with relay_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["K", "任务组", "中继架次", "实体机", "能源组件", "悬停点",
                    "被保障运输架次", "本架次保障的全部单元", "本架次覆盖服务区"])
        for (k, name), items in sorted(by_plan.items()):
            if name != "缺口优先":
                continue
            for rec, groups, facts in items:
                for gi, g in enumerate(groups):
                    for row in inst.relay_copies(g):
                        w.writerow([k, "G%d" % (gi + 1), row["中继架次"], row["实体机"], row["能源组件"],
                                    row["悬停点"], ",".join(row["被保障运输架次"]),
                                    ",".join("U%d" % ci for ci in row["本架次保障的全部单元"]),
                                    "、".join(row["本组命中服务区"])])
    written.append(relay_path)

    # 核验记录
    verify = {
        "输入SHA256": fingerprint,
        "不可拆分单元数": inst.n,
        "单元": [list(u) for u in inst.units],
        "中继架次保障归属": {rid: {"运输架次": sorted(inst.trips_by_relay[rid]),
                                   "单元": inst.units_by_relay[rid],
                                   "服务区": sorted(a for ci in inst.relay_units[rid] for a in inst.units[ci])}
                             for rid in inst.relay_sorties},        "核验": {},
    }
    for k in (2, 3):
        en = enumerations[k]
        verify["核验"]["K=%d" % k] = {
            "规范枚举分区数": en["枚举"]["partitions"],
            "理论分区数": count_partitions(inst.n, k),
            "分支限界搜索节点数": en["分支限界"]["partitions"],
            "最小缺口_枚举": en["枚举"]["best_gap"],
            "最小缺口_分支限界": en["分支限界"]["best_gap"],
            "缺口下最小配置_枚举": en["枚举"]["best_resources"],
            "缺口下最小配置_分支限界": en["分支限界"]["best_resources"],
            "最优CV_枚举": en["枚举"]["best_cv"],
            "最优CV_分支限界": en["分支限界"]["best_cv"],
            "缺口下并行最优分区数": en["枚举"]["stage1_count"],
            "缺口+配置下并行最优分区数": en["枚举"]["stage2_count"],
            "预期最小缺口": EXPECTED[k]["gap"],
            "偏差": en["枚举"]["best_gap"] - EXPECTED[k]["gap"],
            "峰值算法互校": "逐组对每类资源同时用事件扫描与端点覆盖计数两种实现比对（见 口径复核.md）",
        }
    # 峰值算法互校（对全部非空单元子集 × 8 类资源，两种独立实现）
    mismatch = 0
    checked = 0
    for mask in range(1, 1 << inst.n):
        sub = frozenset(ci for ci in range(inst.n) if mask >> ci & 1)
        for cat in CATEGORIES:
            items = []
            for s, e, kind, ident in inst.intervals[cat]:
                if kind == "x":
                    if ident in sub:
                        items.append((s, e))
                elif inst.relay_units[ident] & sub:
                    items.append((s, e))
            sw, iv = peak_sweep(items), peak_independent(items)
            checked += 1
            if sw != iv:
                mismatch += 1
            assert sw == inst.needs_of(sub)[cat], "needs_of 与直算不一致"
    verify["核验"]["峰值互校项数"] = checked
    verify["核验"]["峰值双实现不一致次数"] = mismatch
    assert mismatch == 0
    verify_path = out / "核验记录.json"
    verify_path.write_text(json.dumps(verify, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append(verify_path)

    print("-" * 100)
    print("峰值双实现互校：%d 个子集 × %d 类资源，不一致 %d 处" % ((1 << inst.n) - 1, len(CATEGORIES), mismatch))
    print("输出目录：", out)
    for p in written:
        print("   ", p.name)


if __name__ == "__main__":
    main()
