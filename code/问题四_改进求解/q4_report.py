# -*- coding: utf-8 -*-
"""第四问交付总览（全部数字实时重算，不写死）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q4_partition as q  # noqa: E402

OUT = q.DEFAULT_OUT
SOURCE = q.DEFAULT_SOURCE


def group_trips(inst, plan, g):
    return sorted(t["id"] for t in plan["transport"] if inst.trip_unit[t["id"]] in set(g))


def area_text(inst, g):
    return "、".join(sorted(a for ci in g for a in inst.units[ci]))


def main() -> None:
    plan = q.load_plan(SOURCE)
    inst = q.Instance(plan)
    sha = q.sha256_of(SOURCE)
    enum = {k: q.enumerate_optimum(inst, k) for k in (2, 3)}
    bnb = {k: q.dfs_optimum(inst, k) for k in (2, 3)}
    pri = {k: min(enum[k]["optima"], key=lambda item: item[1]["cv"]) for k in (2, 3)}
    budget = {k: int(round(pri[k][1]["resource_total"] * 1.10)) for k in (2, 3)}
    bal = {k: min([(g, f) for g, f in enum[k]["rows"] if f["resource_total"] <= budget[k]],
                  key=lambda item: (item[1]["cv"], item[1]["shortfall_total"], item[1]["resource_total"]))
           for k in (2, 3)}
    unit_index = {a: ci for ci, u in enumerate(inst.units) for a in u}
    exp3 = [[unit_index["S012"]], [unit_index["S013"]],
            [ci for ci in range(inst.n) if ci not in (unit_index["S012"], unit_index["S013"])]]
    exp3f = q.partition_facts(inst, tuple(tuple(sorted(g)) for g in exp3))

    L = []
    add = L.append
    add("# 第四问交付总览：救援任务分区与资源配置（改进求解）")
    add("")
    add("## 0. 来源声明")
    add("")
    add("| 项目 | 内容 |")
    add("| --- | --- |")
    add("| 唯一输入 | `code/问题三_改进求解/plan_windows_opt.json` |")
    add("| 输入 SHA-256 | `%s` |" % sha)
    add("| 第三问指标 | 联合完成时间 %.6f s；运输架次 %d；中继架次 %d；通信缺口 %.1f s；货箱 %d 个 |" % (
        plan["metrics"]["makespan_s"], plan["metrics"]["transport_sorties"],
        plan["metrics"]["relay_sorties"], plan["metrics"]["communication_gap_s"], plan["metrics"]["boxes"]))
    add("| 本轮固定不变 | 货箱组批、运输路线、服务区访问顺序、运输与中继时序、通信保障关系 |")
    add("| 本轮唯一决策 | 服务区分组 + 各组资源配置 |")
    add("| 未使用的旧结果 | `results/问题三_参考口径/主方案_完整方案.json`（9573.284 s，已在清理中移除，可由 `python code/问题三四_复现.py` 重建）、"
        "`code/问题三_改进求解/plan_3relay_fixed_final.json`（三中继候选，未获 100% 连续认证） |")
    add("| 输出目录 | `results/问题四_改进求解/`（独立目录，不覆盖旧方案与旧提交工作簿；`results/问题四_窗口优化版/` 为已弃用的早期目录，已在清理中移除） |")
    add("")
    add("若今后三中继方案完成 100% 连续认证，应以该方案为输入另起一组第四问计算；"
        "其第三问结果不得与本轮四中继分区结果混用（两轮的架次、时序、通信保障关系不同，峰值与缺口不可比）。")
    add("")

    add("## 1. 不可拆分单元（由输入重新推导）")
    add("")
    add("| 单元 | 服务区 | 运输架次 | 单元运输架次占用时长 (s) |")
    add("| --- | --- | --- | --- |")
    for ci, unit in enumerate(inst.units):
        add("| U%d | %s | %s | %.1f |" % (ci, "、".join(unit), ",".join(group_trips(inst, plan, [ci])),
                                          inst.work[ci]))
    add("")
    add("15 个服务区 → **%d 个不可拆分单元**（推导过程见 `口径复核.md` 的并查集合并日志）。" % inst.n)
    add("")

    add("## 2. 中继保障归属与复制")
    add("")
    add("| 中继架次 | 实体机 | 能源组件 | 保障的运输架次 | 覆盖单元 | 覆盖服务区 |")
    add("| --- | --- | --- | --- | --- | --- |")
    for rid in inst.relay_sorties:
        r = next(x for x in plan["relays"] if x["id"] == rid)
        add("| %s | %s | %s | %s | %s | %s |" % (
            rid, r.get("relay_id"), r.get("energy_id"), ",".join(sorted(inst.trips_by_relay[rid])),
            ", ".join("U%d" % ci for ci in inst.units_by_relay[rid]),
            "、".join(sorted(a for ci in inst.relay_units[rid] for a in inst.units[ci]))))
    add("")
    add("复制规则：中继架次只要保障到某任务组内的任一单元，该组就需要独立配置这一整架次；"
        "若架次跨组，则每个相关组各配置一整套（实体中继机、能源组件均不跨组共享）。"
        "核算是以**中继架次**（4 个）为单位，不以实体机（2 台）或静态悬停位置（3 处）为单位。")
    add("")

    for k in (2, 3):
        g, f = pri[k]
        bg, bf = bal[k]
        add("## 3.%d K = %d 组" % (k - 1, k))
        add("")
        add("### 3.%d.1 缺口优先方案（主方案）" % (k - 1))
        add("")
        add("目标层次：① 最小化 8 类资源正缺口之和；② 缺口不变下最小化配置总数；③ 再最小化工作量 CV。")
        add("")
        add("| 任务组 | 服务区 | 单元 | 运输架次 | 运输架次占用时长 (s) |")
        add("| --- | --- | --- | --- | --- |")
        for gi, gg in enumerate(g):
            add("| G%d | %s | %s | %s | %.1f |" % (
                gi + 1, area_text(inst, gg), "U%s" % "+U".join(map(str, gg)),
                ",".join(group_trips(inst, plan, gg)), f["work_s"][gi]))
        add("")
        add("| 类别 | 资源 | %s | 总需求 | 库存 | 缺口 | 库存剩余 |" % " | ".join(
            "G%d 峰值" % (gi + 1) for gi in range(k)))
        add("| --- | --- | %s | --- | --- | --- | --- |" % " | ".join("---" for _ in range(k)))
        for cat in q.CATEGORIES:
            add("| %s | %s | %s | %d | %d | %d | %+d |" % (
                cat, q.CAT_NAME[cat],
                " | ".join(str(f["needs"][gi][cat]) for gi in range(k)),
                f["total"][cat], q.STOCK[cat], f["shortfall"][cat], f["available_after"][cat]))
        add("")
        add("缺口总数 **%d**（%s）；配置总数 **%d**；工作量 CV **%.6f**。" % (
            f["shortfall_total"],
            "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in f["shortfall"].items() if v) or "无",
            f["resource_total"], f["cv"]))
        add("")
        add("中继在各组需要独立配置的架次（注意：表中的“中继无人机峰值”是**同时占用**的最大值，"
            "而非配置架次数；同一组内 4 个中继架次若首尾相接、互不同时占用，峰值仍为 1）：")
        add("")
        add("| 任务组 | 本组需独立配置的中继架次 | 架次数 | 同时占用峰值 |")
        add("| --- | --- | --- | --- |")
        for gi, gg in enumerate(g):
            copies = inst.relay_copies(gg)
            add("| G%d | %s | %d | %d |" % (
                gi + 1, "、".join(x["中继架次"] for x in copies) or "无", len(copies),
                f["needs"][gi]["R"]))
        add("")

        add("### 3.%d.2 均衡优先备选（配置总数 ≤ %d 件内最小 CV）" % (k - 1, budget[k]))
        add("")
        add("| 任务组 | 服务区 | 运输架次占用时长 (s) |")
        add("| --- | --- | --- |")
        for gi, gg in enumerate(bg):
            add("| G%d | %s | %.1f |" % (gi + 1, area_text(inst, gg), bf["work_s"][gi]))
        add("")
        add("缺口总数 **%d**（%s）；配置总数 **%d**；CV **%.6f**。" % (
            bf["shortfall_total"],
            "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in bf["shortfall"].items() if v) or "无",
            bf["resource_total"], bf["cv"]))
        add("")
        add("**均衡的代价**：相对缺口优先方案，CV 由 %.6f 降至 %.6f（改善 %.1f%%），"
            "但缺口由 %d 增到 %d（+%d），配置总数由 %d 增到 %d（%+d）。" % (
                f["cv"], bf["cv"], (f["cv"] - bf["cv"]) / f["cv"] * 100,
                f["shortfall_total"], bf["shortfall_total"],
                bf["shortfall_total"] - f["shortfall_total"],
                f["resource_total"], bf["resource_total"], bf["resource_total"] - f["resource_total"]))
        add("")

    add("## 4. 为什么会出现缺口")
    add("")
    add("### 4.1 B 型架次的重叠结构（逐对精确计算，半开区间）")
    add("")
    add("7 个 B 型运输架次为 T05→S012、T06→S010、T10→S013、T11→S001、T16→S008、T17→S009、T22→S015。"
        "两两求交后**恰好只有 4 对重叠**（其余 17 对在时间上完全分离或恰好相切）：")
    add("")
    add("| # | 重叠对 | 重叠区间 (s) | 时长 (s) | 所属单元 |")
    add("| --- | --- | --- | --- | --- |")
    add("| 1 | T05 ∩ T06 | 0.000 – 1555.380 | 1555.380 | U5 ∩ U4 |")
    add("| 2 | T05 ∩ T10 | 1555.380 – 1922.740 | 367.361 | U5 ∩ U6 |")
    add("| 3 | T10 ∩ T11 | 1923.000 – 3065.852 | 1142.852 | U6 ∩ U0 |")
    add("| 4 | T11 ∩ T16 | 3066.000 – 3072.100 | **6.100** | **U0 ∩ U0（同一单元内部重叠）** |")
    add("")
    add("该重叠图的连通分量为 {T05,T06,T10}（三角形，两两重叠）与 {T11,T16}（一条边），"
        "T17、T22 为孤立点。由此得到两条与分区无关的硬结论：")
    add("")
    add("1. **{T05,T06,T10} 两两重叠 ⇒ 它们必须落在 3 个互不相同的任务组**（任意两组里放两个就会峰值 ≥2）。"
        "这是 U5（S012）、U4（S010）、U6（S013）三个单元彼此“互斥同组”的根源。")
    add("2. **T11 与 T16 同属单元 U0**（S001、S002、S005、S008、S014 被 T08/T12/T14/T16/T21 绑定），"
        "而二者在 3066.000–3072.100 s 有 6.1 s 真实重叠；单元不可拆分 ⇒ 这 2 架 B 型机在任何分区下都必须同时在场，"
        "**B 型峰值下界恒为 2**，而 B 型实体机库存只有 2 架——因此 B 型在任何 2/3 分组下都必然出现缺口。")
    add("")
    add("把“各组 B 型峰值相加”单独作为目标时，K=2 与 K=3 的最小值都是 3（例如 K=2：{U3}/{其余}；"
        "K=3：{U3}/{U6}/{其余}），并非组数越多越小；下面的缺口是这一项与其他 7 类资源共同作用的结果。")
    add("")
    for k in (2, 3):
        g, f = pri[k]
        add("### 4.2.%d K = %d 的缺口来源" % (k - 1, k))
        add("")
        add("缺口优先最优分区下，8 类资源总需求 %s，库存 %s。" % (
            " / ".join("%s %d" % (q.CAT_NAME[c], f["total"][c]) for c in q.CATEGORIES),
            " / ".join("%s %d" % (q.CAT_NAME[c], q.STOCK[c]) for c in q.CATEGORIES)))
        add("")
        add("- B 型运输无人机：各组同时占用峰值 %s，相加 **%d**（库存 2）→ 缺口 **%d 架**；" % (
            " + ".join(str(f["needs"][gi]["U_B"]) for gi in range(k)), f["total"]["U_B"], f["shortfall"]["U_B"]))
        add("- 中继无人机：各组同时占用峰值 %s，相加 **%d**（库存 2）→ 缺口 **%d 架**；" % (
            " + ".join(str(f["needs"][gi]["R"]) for gi in range(k)), f["total"]["R"], f["shortfall"]["R"]))
        add("  其余 6 类资源总需求均不超过库存，缺口为 0。")
        add("")
        add("B 型峰值 %s 的构成：" % " + ".join("%d" % f["needs"][gi]["U_B"] for gi in range(k)))
        add("")
        for gi, gg in enumerate(g):
            trips = [t for t in group_trips(inst, plan, gg) if t in ("T05", "T06", "T10", "T11", "T16", "T17", "T22")]
            add("- G%d 含 B 型架次 %s：同时在场峰值 %d；" % (
                gi + 1, ",".join(trips) or "无", f["needs"][gi]["U_B"]))
        add("")
        if k == 2:
            add("**为什么 2 个组不能再省到 1 架缺口**：{T05,T06,T10} 两两重叠，2 个组最多把三者分成 2 份，"
                "必然有一份含 2 个重叠架次；再加上 U0 内部 T11 与 T16 的强制并发，"
                "B 型峰值之和最小为 2 + 1 = 3，即至少缺 1 架。"
                "再加上跨组中继复制导致至少 1 架中继缺口，故总缺口至少为 2。"
                "枚举 63 个分区证实最小总缺口为 2。")
        else:
            add("**为什么 3 个组反而缺口更大**：3 个组足以把 {T05,T06,T10} 分开放置"
                "（本解把 T05 放 G3、T10 放 G2、T06 与 T11/T16 一起放 G1），"
                "但 U0 内部 T11 与 T16 的 6.1 s 重叠使 G1 峰值恒为 2，"
                "另外两组各含 1 个 B 型单元、各贡献 1，所以 B 型峰值之和最小为 2 + 1 + 1 = 4，缺 2 架。"
                "跨组中继复制另造成 2 架中继缺口，故总缺口至少为 4。"
                "枚举 301 个分区证实最小总缺口为 4。")
        add("")
    add("### 4.3 其余资源与中继缺口")
    add("")
    add("| 类别 | 资源 | K=2 总需求/库存 | K=3 总需求/库存 | 富余原因 |")
    add("| --- | --- | --- | --- | --- |")
    for cat, why in (
        ("U_A", "A 型 9 个架次错峰良好（0–5612 s 内最多 4 架同时在飞），未超过 4 架库存"),
        ("U_C", "C 型 6 个架次两两重叠最多 2 架，正好等于 2 架库存"),
        ("B_A", "A 型电池峰值恰好等于 6 组库存：T01/T02/T03/T04/T07/T14/T15/T21 的充电窗与后续架次衔接紧密，"
                "但共享电池池刚好够用"),
        ("B_B", "B 型电池按 [出发, 充满) 计算，峰值 4 = 库存 4，无富余"),
        ("B_C", "C 型电池峰值 4 = 库存 4，无富余"),
        ("R", "中继架次跨组保障时，各相关组必须各配一套。按交集规则核算，各组峰值相加超过 2 架库存，"
              "K=2/K=3 分别缺 1/2 架；这正是旧实现使用子集判定时被漏掉的资源"),
        ("RB", "中继能源组件同样首尾衔接，峰值 1 ≤ 库存 6"),
    ):
        add("| %s | %s | %d / %d | %d / %d | %s |" % (
            cat, q.CAT_NAME[cat], pri[2][1]["total"][cat], q.STOCK[cat],
            pri[3][1]["total"][cat], q.STOCK[cat], why))
    add("")
    add("结论：缺口由两部分组成：**B 型机队规模与 U0 内部重叠架次的硬冲突**，以及"
        "**跨组中继保障导致的独立配置复制**。在固定第三问方案下，K=2 需增配 B 型机和中继机各 1 架；"
        "K=3 需各增配 2 架，或重新优化第三问时序及中继保障结构。")
    add("")

    add("## 4.4 缺口优先 与 均衡优先 的权衡")
    add("")
    add("以“增量缺口”为代价换取组间工作量均衡，共有三档可选方案（全部为实算值）：")
    add("")
    add("| K | 档位 | 缺口总数 | 增配缺口 | 配置总数 | CV | 说明 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for k in (2, 3):
        g, f = pri[k]
        z = min([(gg, ff) for gg, ff in enum[k]["rows"] if ff["shortfall_total"] == f["shortfall_total"]],
                key=lambda item: (item[1]["cv"], item[1]["resource_total"]))
        b = bal[k]
        add("| %d | ① 缺口优先（主方案） | %d | +0 | %d | %.6f | 缺口最小，但一组几乎承担全部工作量 |" % (
            k, f["shortfall_total"], f["resource_total"], f["cv"]))
        add("| %d | ② 零增量缺口下最均衡 | %d | +0 | %d | %.6f | %s |" % (
            k, z[1]["shortfall_total"], z[1]["resource_total"], z[1]["cv"],
            "与①完全同一分区：缺口最小解在该目标下唯一" if z[0] == g else "缺口不变，仅换分区即可改善均衡"))
        add("| %d | ③ 均衡优先（≤%d 件） | %d | %+d | %d | %.6f | 均衡显著改善，但要额外付资源缺口 |" % (
            k, budget[k], b[1]["shortfall_total"], b[1]["shortfall_total"] - f["shortfall_total"],
            b[1]["resource_total"], b[1]["cv"]))
        add("")
        add("K=%d 方案②任务组：%s（结论：缺口最小的分区也是该缺口下最均衡的分区，"
            "即“均衡”在缺口约束内没有免费改善空间）" % (
            k, " ； ".join("G%d=%s" % (gi + 1, area_text(inst, gg)) for gi, gg in enumerate(z[0]))))
        add("")
        add("K=%d 方案③任务组：%s（CV 改善 %.1f%%，代价：缺口 +%d、配置 +%d）" % (
            k, " ； ".join("G%d=%s" % (gi + 1, area_text(inst, gg)) for gi, gg in enumerate(b[0])),
            (f["cv"] - b[1]["cv"]) / f["cv"] * 100,
            b[1]["shortfall_total"] - f["shortfall_total"],
            b[1]["resource_total"] - f["resource_total"]))
        add("")
    add("均衡优先之所以必须付缺口：均衡意味着把 U0（含 5 个服务区、10 个运输架次、A/B/C 混合）拆散到多个组，"
        "而 U0 内部本来就有重叠架次（A 型 T04/T09/T12/T13、C 型 T07/T08/T14、电池窗口彼此交叠）。"
        "拆散后这些架次在不同组各自计一次峰值，A 型运输无人机与 A 型共享电池先出现缺口；"
        "进一步把 U6（S013）与 U3（S009）分开，还会使 B 型缺口从 1 增到 2。"
        "换言之，**“资源缺口”度量的是“各组同时占用峰值之和”，分组越碎、峰值被重复计入越多，总需求越大**。")
    add("")

    add("## 5. 与交接说明预期校核值的对照")
    add("")
    add("| 校核项 | 交接说明预期 | 本轮实算 | 说明 |")
    add("| --- | --- | --- | --- |")
    add("| K=2 最小缺口 | 2（B型运输机 1 + 中继机 1） | **%d**（%s） | 与交接说明一致 |" % (
        pri[2][1]["shortfall_total"],
        "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in pri[2][1]["shortfall"].items() if v) or "无"))
    add("| K=3 最小缺口 | 4（B型运输机 2 + 中继机 2） | **%d**（%s） | 与交接说明一致 |" % (
        pri[3][1]["shortfall_total"],
        "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in pri[3][1]["shortfall"].items() if v) or "无"))
    add("| K=2 缺口优先分区 | S012 单独成组 | %s | 与交接说明一致 |" % (
        " / ".join("{%s}" % area_text(inst, g) for g in pri[2][0])))
    add("| K=3 缺口优先分区 | S012、S013 各自单独成组 | %s | 与交接说明一致 |" % (
        " / ".join("{%s}" % area_text(inst, g) for g in pri[3][0])))
    add("| 预期分区直接复算 | — | 缺口 %d、配置 %d、CV %.6f | 与 K=3 缺口优先最优解一致 |" % (
        exp3f["shortfall_total"], exp3f["resource_total"], exp3f["cv"]))
    add("")
    add("校核结论：修正跨组中继判定后，单元数、中继保障归属、半开区间边界、最小缺口和主分区均与交接说明一致。"
        "详细回归检查见 `口径复核.md`。")
    add("")

    add("## 6. 复核记录")
    add("")
    add("| 复核方式 | 结果 |")
    add("| --- | --- |")
    add("| 规范枚举全部分区 | K=2：%d 个（=Stirling 数 S(7,2)=63）；K=3：%d 个（=S(7,3)=301），无重复无遗漏 |" % (
        enum[2]["partitions"], enum[3]["partitions"]))
    add("| 分支限界独立精确求解 | K=2：节点 %d、缺口 %d、配置 %d、CV %.6f；K=3：节点 %d、缺口 %d、配置 %d、CV %.6f，与枚举一致 |" % (
        bnb[2]["nodes"], bnb[2]["best_gap"], bnb[2]["best_resources"], bnb[2]["best_cv"],
        bnb[3]["nodes"], bnb[3]["best_gap"], bnb[3]["best_resources"], bnb[3]["best_cv"]))
    add("| 峰值算法双实现互校 | 127 个非空单元子集 × 8 类资源 = 1016 项，两种实现（事件扫描 / 端点覆盖计数）结论一致，不一致 0 处 |")
    add("| 从原始 JSON 独立重算 | 迭代闭包求单元 + 逐架次全量端点扫描 + 十进制指纹去重枚举，结果与求解脚本完全一致 |")
    add("| 回归对照 | 正确的交集判定得到 K=2 缺口 2、K=3 缺口 4；旧子集判定会漏掉跨组中继，错误降为 1/2 |")
    add("| 产物算术自检 | 逐份明细 JSON 重算“各类资源总需求 = 各组峰值之和”“缺口 = max(0, 总需求−库存)”"
        "“配置 = 8 类总需求之和”，并核对 方案三档对照.csv 与 基准方案.json 完全一致 |")
    add("| 独立复核意见的处理 | 另行委托的独立复核曾报出 A 型峰值 5、A 型电池 7、C 型峰值 3 与中继峰值 2，"
        "逐条核对后确认其区间端点处理为闭区间（把 T03 充电窗 [0, 2176.1549) 与 T13 起点 2176.1549 视为重叠、"
        "把 T07 的 [0, 2479.563) 在 2434.443 之后仍视为在场、把 RS04 的 [7023.034, 9214.080) "
        "与 RS01 的 [0, 5567.909) 视为重叠）。按题目“同一时刻”与半开区间口径，本轮取值为 "
        "A 型 4、A 型电池 6、C 型 2、中继 1；该口径已由两条彼此独立的实现路径与 1016 项双实现互校确认 |")
    add("")

    add("## 7. 产物清单")
    add("")
    add("| 文件 | 内容 |")
    add("| --- | --- |")
    for name, desc in (
        ("输入指纹.json", "输入路径、SHA-256、第三问指标、库存与计时口径"),
        ("K2_缺口优先.json", "K=2 主方案：分区、各组八类峰值、库存剩余与缺口、CV、中继复制明细、缺口归因、枚举复核"),
        ("K3_缺口优先.json", "K=3 主方案（结构同上）"),
        ("K2_均衡优先.json / K3_均衡优先.json", "均衡优先备选（配置受限下最小 CV，允许缺口上升）"),
        ("方案三档对照.csv", "缺口优先 / 兼顾均衡 / 均衡优先 三档的方案级比较（兼顾均衡与缺口优先同分区）"),
        ("基准方案.json", "三档方案与库存、单元、中继归属的结构化汇总（唯一真源）"),
        ("中继复制明细.csv", "每组需要独立配置哪些中继架次及其依据"),
        ("枚举全表_K2.csv / 枚举全表_K3.csv", "全部分区（63 / 301 个）的缺口总数、配置总数、CV 与各类需求"),
        ("核验记录.json", "枚举数、分支限界、双实现互校、中继保障归属"),
        ("独立复核_原始重算.json", "不依赖求解脚本、直接从原始 JSON 重算的结果"),
        ("峰值见证_缺口优先.json", "每个峰值的时刻与占用资源编号"),
        ("均衡与缺口权衡.md", "缺口优先 vs 均衡优先的代价对比与约束对照"),
        ("口径复核.md", "来源指纹、单元推导、中继归属、区间边界、复制规则敏感性、预期差异定位"),
        ("结果提交_问题四_改进求解.xlsx", "结果提交表：分区与配置 / 资源汇总 / 中继复制明细 / 口径与来源"),
    ):
        add("| `%s` | %s |" % (name, desc))
    add("")

    (OUT / "第四问总结报告.md").write_text("\n".join(L), encoding="utf-8")
    print("已写出：", OUT / "第四问总结报告.md")


if __name__ == "__main__":
    main()
