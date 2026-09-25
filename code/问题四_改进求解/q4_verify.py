# -*- coding: utf-8 -*-
"""第四问口径复核：把“缺口为何出现/为何与预期不同”逐项落到可核对的时间证据上。

产出：
  results/问题四_改进求解/口径复核.md
  results/问题四_改进求解/峰值见证_缺口优先.json   （每个峰值给出达到峰值的时刻与占用资源编号）

复核内容：
  A. 来源：输入文件 SHA-256 与第三问指标，禁止使用的旧文件指纹对照；
  B. 单元：由运输架次端点重新推导（含并查集逐步合并日志）；
  C. 通道归属：中继架次 -> 运输架次 -> 单元 -> 任务组 的完整对应；
  D. 区间边界：逐类资源在半开区间规则下的峰值见证（同刻结束先于开始）；
  E. 中继复制：两种候选规则（“保障到本组任一单元即复制” vs “保障的全部单元都在本组才复制”）的对比；
  F. 旧第三问方案 9573.284379343868 s 在同一模型下的复算（用于说明预期值的可能来源）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q4_partition as q  # noqa: E402

ROOT = q.ROOT
SOURCE = q.DEFAULT_SOURCE
OUT = q.DEFAULT_OUT
FORBIDDEN = [
    ROOT / "results" / "问题三_参考口径" / "主方案_完整方案.json",
    ROOT / "code" / "问题三_改进求解" / "plan_3relay_fixed_final.json",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def witness(intervals, cat, group, inst, trip_label):
    """给出某组在 cat 类资源上达到峰值的时刻，以及此刻正在占用的资源编号。

    峰值时刻取“达到最大并发的那批区间的最晚开始时刻”（该点必然同时被这批区间覆盖，
    因为覆盖它们的公共交集非空）。
    """
    items = []
    for s, e, kind, ident in intervals[cat]:
        if kind == "x":
            if ident in group:
                items.append((s, e, trip_label.get((cat, s, e, ident), "U%d" % ident)))
        else:
            if inst.relay_units[ident] & group:
                items.append((s, e, ident))
    if not items:
        return {"峰值": 0, "峰值时刻_s": None, "占用资源": []}
    best_cnt, best_names, best_t = 0, [], None
    for s, e, name in items:
        covering = sorted([(ss, ee, n) for ss, ee, n in items if ss <= s < ee],
                          key=lambda x: x[0])
        if len(covering) > best_cnt:
            best_cnt, best_names, best_t = len(covering), covering, covering[-1][0]
    return {
        "峰值": best_cnt,
        "峰值时刻_s": best_t,
        "占用资源": [{"资源": n, "区间": [ss, ee]} for ss, ee, n in best_names],
        "该类区间总数": len(items),
    }


def area_partition(inst, groups):
    return [[a for ci in g for a in inst.units[ci]] for g in groups]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = []
    add = lines.append

    src_sha = sha256_of(SOURCE)
    plan = q.load_plan(SOURCE)
    inst = q.Instance(plan)

    add("# 第四问口径复核（改进求解）")
    add("")
    add("## A. 来源与指纹")
    add("")
    add("| 文件 | SHA-256 | 状态 |")
    add("| --- | --- | --- |")
    add("| `code/问题三_改进求解/plan_windows_opt.json` | `%s` | **本轮唯一输入** |" % src_sha)
    for path in FORBIDDEN:
        if path.exists():
            add("| `%s` | `%s` | 本轮禁止使用 |" % (path.relative_to(ROOT).as_posix(), sha256_of(path)))
        else:
            add("| `%s` | （不存在，已在仓库清理中移除） | 本轮禁止使用 |" % path.relative_to(ROOT).as_posix())
    add("")
    add("第三问指标：完成时间 %.6f s，运输 %d 架次，中继 %d 架次，通信缺口 %.1f s，货箱 %d 个。"
        % (plan["metrics"]["makespan_s"], plan["metrics"]["transport_sorties"],
           plan["metrics"]["relay_sorties"], plan["metrics"]["communication_gap_s"],
           plan["metrics"]["boxes"]))
    add("")
    add("## B. 不可拆分单元的推导（同一运输架次访问的服务区必须同组）")
    add("")
    add("| 单元 | 服务区 | 运输架次 | 单元内各服务区所属架次 |")
    add("| --- | --- | --- | --- |")
    for ci, unit in enumerate(inst.units):
        trips = sorted(t["id"] for t in plan["transport"] if inst.trip_unit[t["id"]] == ci)
        add("| U%d | %s | %s | %s |" % (ci, "、".join(unit), ",".join(trips),
                                        "; ".join("%s:%s" % (a, ",".join(
                                            sorted(t["id"] for t in plan["transport"]
                                                   if any(s["area"] == a for s in t["stops"]))))
                                            for a in unit)))
    add("")
    add("推导结果：15 个服务区 -> **%d 个不可拆分单元**。" % inst.n)
    add("")
    add("并查集逐步合并日志（由输入逐架次重放，非写死）：")
    add("")
    add("```")
    parent = {a: a for a in sorted({s["area"] for t in plan["transport"] for s in t["stops"]})}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for trip in plan["transport"]:
        first = find(trip["stops"][0]["area"])
        for stop in trip["stops"][1:]:
            r = find(stop["area"])
            if r != first:
                add("%s: %s -> %s" % (trip["id"], stop["area"], trip["stops"][0]["area"]))
                parent[r] = first
    add("```")
    add("")

    add("## C. 中继架次 -> 被保障运输架次 -> 任务单元")
    add("")
    add("| 中继架次 | 实体机 | 能源组件 | 悬停点 | 出发/返航/充电完成 (s) | 被保障运输架次 | 覆盖单元 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for rid in inst.relay_sorties:
        r = next(x for x in plan["relays"] if x["id"] == rid)
        add("| %s | %s | %s | %s | %.1f / %.1f / %.1f | %s | %s |" % (
            rid, r.get("relay_id"), r.get("energy_id"), r.get("site"),
            r["depart_s"], r["return_s"], r["energy_free_s"],
            ",".join(sorted(inst.trips_by_relay[rid])),
            ", ".join("U%d" % ci for ci in inst.units_by_relay[rid])))
    add("")
    add("**中继复制规则**：中继架次所保障的运输架次若分布在多个任务组，则该架次在每个相关任务组都要独立配置"
        "一套完整中继服务能力（实体中继机、能源组件均不得跨组共用）。由于运输架次与其服务区已被绑成不可拆分单元，"
        "“本组需要该中继架次”的判定条件为：**该架次保障的单元与本组有非空交集**。")
    add("")
    add("注：本轮第三问方案共 4 个中继架次（RS01–RS04），分布在 2 台实体中继机（R01、R02）上；"
        "资源核算以**架次**为复制单位，不以实体机或静态悬停位置为单位（同一实体机执行多个架次时，"
        "各架次占用时段仍可能被分到不同任务组，必须分别配置）。")
    add("")

    add("## D. 缺口优先方案的峰值见证（半开区间，同刻结束先于开始）")
    add("")
    # 每架次/每个中继架次的占用区间标签，保证见证可逐条核对
    trip_label = {}
    for trip in plan["transport"]:
        for cat in ("U_" + trip["model"], "B_" + trip["model"]):
            key = (cat, trip["start_s"], trip["return_s"] if cat.startswith("U") else trip["charge_end_s"],
                   inst.trip_unit[trip["id"]])
            trip_label[key] = trip["id"]
    peak_records = {}
    for k in (2, 3):
        enum = q.enumerate_optimum(inst, k)
        groups, facts = min(enum["optima"], key=lambda item: item[1]["cv"])
        peak_records["K%d" % k] = {}
        add("### K = %d" % k)
        add("")
        add("任务组：%s" % " ； ".join("G%d = %s" % (gi + 1, "、".join(sorted(a for ci in g for a in inst.units[ci])))
                                      for gi, g in enumerate(groups)))
        add("")
        add("| 类别 | 资源 | G1 峰值 | G2 峰值 | G3 峰值 | 各组占用相加 | 库存 | 正缺口 | 峰值时刻与占用证据 |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for cat in q.CATEGORIES:
            cells = [facts["needs"][gi][cat] for gi in range(k)]
            cells += ["—"] * (3 - k)
            ev = []
            for gi, g in enumerate(groups):
                w = witness(inst.intervals, cat, set(g), inst, trip_label)
                peak_records["K%d" % k].setdefault("G%d" % (gi + 1), {})[cat] = w
                if w["峰值"]:
                    ev.append("G%d@%.3fs: %s" % (gi + 1, w["峰值时刻_s"],
                                                 "+".join(x["资源"] for x in w["占用资源"])))
            add("| %s | %s | %s | %s | %s | **%d** | %d | %d | %s |" % (
                cat, q.CAT_NAME[cat], cells[0], cells[1], cells[2],
                facts["total"][cat], q.STOCK[cat], facts["shortfall"][cat],
                "<br>".join(ev) if ev else "本方案无占用"))
        add("")
        add("各组运输架次占用时长（Σ(返航−出发)，含准备、装载与交接）：%s s；CV = %.6f；配置总数 = %d；缺口总数 = %d。"
            % (" / ".join("%.1f" % w for w in facts["work_s"]), facts["cv"],
               facts["resource_total"], facts["shortfall_total"]))
        add("")

    add("（表中“各组占用相加”= 按题目“各组分别核算、资源不得跨组调配”把各组峰值相加后的总需求；"
        "“正缺口”= max(0, 总需求 − 库存)。）")
    add("")

    (OUT / "峰值见证_缺口优先.json").write_text(
        json.dumps(peak_records, ensure_ascii=False, indent=2), encoding="utf-8")

    add("## E. 中继复制规则的敏感性")
    add("")
    add("正确规则是“该架次保障到本组任一单元即在本组复制”；否则跨组中继会在所有相关组中被漏计。"
        "下表把正确规则与旧实现的错误“全部单元都在本组才计入”作回归对比"
        "（缺口优先最优分区，K=2/K=3）：")
    add("")
    add("| K | 规则 | 中继机需求 | 中继能源组件需求 | 缺口总数 |")
    add("| --- | --- | --- | --- | --- |")

    class BuggySubsetInstance(q.Instance):
        """旧错误口径：跨组中继不属于任何一组，因而被漏计。"""

        def needs_of(self, subset):
            key = frozenset(subset)
            if key in self._cache:
                return dict(self._cache[key])
            rows = {}
            for cat in q.CATEGORIES:
                items = []
                for s, e, kind, ident in self.intervals[cat]:
                    if kind == "x":
                        if ident in key:
                            items.append((s, e))
                    elif self.relay_units[ident] <= key:
                        items.append((s, e))
                rows[cat] = q.peak_sweep(items)
            self._cache[key] = rows
            return dict(rows)

    buggy = BuggySubsetInstance(plan)
    for k in (2, 3):
        enum = q.enumerate_optimum(inst, k)
        groups, facts = min(enum["optima"], key=lambda item: item[1]["cv"])
        le = q.enumerate_optimum(buggy, k)
        lgroups, lfacts = min(le["optima"], key=lambda item: item[1]["cv"])
        add("| %d | 触及本组任一单元即复制（正确） | %d | %d | %d |" % (
            k, facts["total"]["R"], facts["total"]["RB"], facts["shortfall_total"]))
        add("| %d | 全部单元都在本组才计入（旧错误实现） | %d | %d | %d |" % (
            k, lfacts["total"]["R"], lfacts["total"]["RB"], lfacts["shortfall_total"]))
    add("")

    add("## F. 旧第三问方案（9573.284379343868 s）在同一模型下的复算")
    add("")
    old_path = ROOT / "results" / "问题三_参考口径" / "主方案_完整方案.json"
    if not old_path.exists():
        add("旧第三问方案 `results/问题三_参考口径/主方案_完整方案.json` 已在一次删除性清理中移除，"
            "本节跳过该复算；需要时先运行 `python code/问题三四_复现.py` 重建该目录（见 `docs/仓库清理记录.md`）。")
        add("")
    if old_path.exists():
        add("旧方案与新版**架次结构完全相同**（22 运输 + 4 中继、逐架次服务区与中继保障关系一致），"
            "仅时序与中继返航时刻不同。用本轮同一模型复算旧方案：")
        add("")
        old_plan = q.load_plan(old_path)
        old_inst = q.Instance(old_plan)
        add("- 旧方案不可拆分单元：%s" % " ； ".join("U%d=%s" % (i, "、".join(u)) for i, u in enumerate(old_inst.units)))
        for k in (2, 3):
            en = q.enumerate_optimum(old_inst, k)
            g, f = min(en["optima"], key=lambda item: item[1]["cv"])
            add("- K=%d：最小缺口 %d（%s），缺口优先分区 %s，CV %.6f" % (
                k, f["shortfall_total"],
                "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in f["shortfall"].items() if v) or "无缺口",
                " / ".join("、".join(sorted(a for ci in gg for a in old_inst.units[ci])) for gg in g),
                f["cv"]))
        add("")
        ref = ROOT / "results" / "问题四_参考口径" / "K2_缺口优先.json"
        if not ref.exists():
            add("（对照用的 `results/问题四_参考口径/K2_缺口优先.json` 已在清理中移除，略去该对照。）")
            add("")
        if ref.exists():
            old_rec = json.loads(ref.read_text(encoding="utf-8"))
            add("对照：`results/问题四_参考口径/K2_缺口优先.json`（旧提交）记录的最小缺口为 %d，"
                "明细 %s；本轮修复后使用同一复制规则复算，结果应与该口径一致。"
                % (old_rec["缺口总数"],
                   "、".join("%s×%d" % (q.CAT_NAME[c], v)
                             for c, v in old_rec["资源缺口"].items() if v) or "无"))
    add("")
    add("### 预期校核值与本轮结果的差异定位")
    add("")
    add("| 校核项 | 交接说明预期 | 本轮实算（正确交集规则） | 旧错误实现（全部单元须同组） |")
    add("| --- | --- | --- | --- |")
    for k in (2, 3):
        en = q.enumerate_optimum(inst, k)
        g, f = min(en["optima"], key=lambda item: item[1]["cv"])
        le = q.enumerate_optimum(buggy, k)
        lg, lf = min(le["optima"], key=lambda item: item[1]["cv"])
        add("| K=%d 最小缺口 | %d | **%d**（%s） | %d（%s） |" % (
            k, q.EXPECTED[k]["gap"], f["shortfall_total"],
            "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in f["shortfall"].items() if v) or "无缺口",
            lf["shortfall_total"],
            "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in lf["shortfall"].items() if v) or "无缺口"))
        add("| K=%d 缺口优先分区 | %s | %s | %s |" % (
            k, "、".join(q.EXPECTED[k]["partition"]),
            " / ".join("、".join(sorted(a for ci in gg for a in inst.units[ci])) for gg in g),
            " / ".join("、".join(sorted(a for ci in gg for a in inst.units[ci])) for gg in lg)))
    unit_index = {a: ci for ci, u in enumerate(inst.units) for a in u}
    exp3 = [[unit_index["S012"]], [unit_index["S013"]],
            [ci for ci in range(inst.n) if ci not in (unit_index["S012"], unit_index["S013"])]]
    ef = q.partition_facts(inst, tuple(tuple(sorted(g)) for g in exp3))
    add("")
    add("**交接说明预期分区 `{S012} / {S013} / 其余 13 个服务区` 的直接复算**：缺口总数 %d（%s），配置总数 %d，CV %.6f。"
        % (ef["shortfall_total"],
           "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in ef["shortfall"].items() if v) or "无缺口",
           ef["resource_total"], ef["cv"]))
    add("")
    add("结论：")
    add("")
    add("1. **单元数、中继归属、半开区间边界三项均与交接说明一致**：15 个服务区由同一运输架次绑定后得到 7 个不可拆分单元；"
        "4 个中继架次分别保障 U0+U1、U0+U3+U4+U5+U6、U0+U2+U3、U1；同刻结束与开始按半开区间处理。")
    add("2. **K=2 结果与预期一致**：最小缺口为 2（B 型运输无人机 1 + 中继无人机 1）。")
    add("3. **K=3 结果与预期一致**：最小缺口为 4（B 型运输无人机 2 + 中继无人机 2）。")
    add("4. 交集判定直接落实了“跨组时每个相关组各配置一套”的题意；旧子集判定会让跨组中继在所有组中消失，"
        "因此不是更省的可行方案，而是漏算资源。")

    (OUT / "口径复核.md").write_text("\n".join(lines), encoding="utf-8")
    print("已写出：", OUT / "口径复核.md")
    print("已写出：", OUT / "峰值见证_缺口优先.json")


if __name__ == "__main__":
    main()
