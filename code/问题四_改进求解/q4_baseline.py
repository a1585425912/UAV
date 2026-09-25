# -*- coding: utf-8 -*-
"""第四问基准方案生成（唯一真源）：三档方案一次算清，供比较、报告与工作簿共同引用。

三档目标（全部为实算，不写死）：
  ① 缺口优先      ：最小化 8 类资源正缺口之和；缺口不变下最小化配置总数；再最小化工作量 CV。
  ② 零增量缺口最均衡：在缺口总数等于最小缺口的分区中最小化 CV（该档与①可能重合）。
  ③ 均衡优先      ：在配置总数 ≤ round(①的配置总数 × 1.10) 的规模内最小化 CV，
                    允许缺口上升，用于量化“均衡的代价”。

产出：
  results/问题四_改进求解/K{k}_缺口优先.json
  results/问题四_改进求解/K{k}_兼顾均衡.json        （档位②，缺口不变的最均衡解）
  results/问题四_改进求解/K{k}_均衡优先.json        （档位③，配置受限下最均衡解）
  results/问题四_改进求解/方案三档对照.csv
  results/问题四_改进求解/基准方案.json             （供报告与工作簿引用的精简结构）
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q4_partition as q  # noqa: E402

OUT = q.DEFAULT_OUT
SOURCE = q.DEFAULT_SOURCE


def groups_of(inst, g):
    return [sorted(a for ci in gg for a in inst.units[ci]) for gg in g]


def trips_of(inst, plan, gg):
    return sorted(t["id"] for t in plan["transport"] if inst.trip_unit[t["id"]] in set(gg))


def main() -> None:
    plan = q.load_plan(SOURCE)
    inst = q.Instance(plan)
    sha = q.sha256_of(SOURCE)
    enum = {k: q.enumerate_optimum(inst, k) for k in (2, 3)}

    summary = {}
    csv_rows = []
    for k in (2, 3):
        rows = enum[k]["rows"]
        pri = min([(g, f) for g, f in rows
                   if f["shortfall_total"] == enum[k]["best_gap"] and f["resource_total"] == enum[k]["best_resources"]],
                  key=lambda item: (item[1]["cv"], item[0]))
        budget = int(round(pri[1]["resource_total"] * 1.10))
        zero = min([(g, f) for g, f in rows if f["shortfall_total"] == enum[k]["best_gap"]],
                   key=lambda item: (item[1]["cv"], item[1]["resource_total"], item[0]))
        bal = min([(g, f) for g, f in rows if f["resource_total"] <= budget],
                  key=lambda item: (item[1]["cv"], item[1]["shortfall_total"], item[1]["resource_total"], item[0]))
        summary[k] = {"pri": pri, "zero": zero, "bal": bal, "budget": budget}

        for name, (g, f) in (("缺口优先", pri), ("均衡优先", bal)):
            payload = {
                "K": k, "方案": name, "输入": str(SOURCE.relative_to(q.ROOT)).replace("\\", "/"),
                "输入SHA256": sha, "第三问指标": plan["metrics"],
                "不可拆分单元": [list(u) for u in inst.units],
                "任务组（单元下标）": [list(gg) for gg in g],
                "任务组（服务区）": groups_of(inst, g),
                "各组资源需求": {q.CAT_NAME[c]: [f["needs"][gi][c] for gi in range(k)] for c in q.CATEGORIES},
                "资源总需求": {q.CAT_NAME[c]: f["total"][c] for c in q.CATEGORIES},
                "库存": {q.CAT_NAME[c]: q.STOCK[c] for c in q.CATEGORIES},
                "资源缺口": {q.CAT_NAME[c]: f["shortfall"][c] for c in q.CATEGORIES},
                "缺口总数": f["shortfall_total"],
                "库存剩余（可为负=缺口）": {q.CAT_NAME[c]: f["available_after"][c] for c in q.CATEGORIES},
                "各组运输架次占用时长_s": f["work_s"],
                "各组运输架次": {("G%d" % (gi + 1)): trips_of(inst, plan, gg) for gi, gg in enumerate(g)},
                "运输架次占用时长CV": f["cv"],
                "配置总数": f["resource_total"],
                "配置总数预算": budget,
                "中继复制明细": {("G%d" % (gi + 1)): inst.relay_copies(gg) for gi, gg in enumerate(g)},
                "口径": {
                    "运输无人机": "[出发, 返航)", "同型共享电池": "[出发, 充满)",
                    "中继无人机": "[出发, 返航+架次周转时间)", "中继能源组件": "[出发, 充满)",
                    "半开区间": "同刻结束先于开始",
                    "中继复制": "中继架次保障的全部单元都落在本组时，本组独立配置该架次",
                    "工作量": "Σ(返航−出发)=运输架次占用时长（含准备、装载与交接）",
                },
                "枚举复核": {
                    "规范枚举分区数": enum[k]["partitions"],
                    "理论分区数": q.count_partitions(inst.n, k),
                    "枚举最小缺口": enum[k]["best_gap"],
                    "缺口下最小配置": enum[k]["best_resources"],
                    "缺口下最均衡CV": zero[1]["cv"],
                },
            }
            (OUT / ("K%d_%s.json" % (k, name))).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            csv_rows.append({
                "K": k, "档位": name, "缺口总数": f["shortfall_total"], "配置总数": f["resource_total"],
                "运输架次占用时长CV": round(f["cv"], 9),
                "缺口明细": "、".join("%s×%d" % (q.CAT_NAME[c], v) for c, v in f["shortfall"].items() if v) or "无",
                "各组运输架次占用时长_s": " / ".join("%.1f" % w for w in f["work_s"]),
                "任务组": " / ".join("、".join(area) for area in groups_of(inst, g)),
            })

    with (OUT / "方案三档对照.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_rows[0]))
        w.writeheader()
        w.writerows(csv_rows)

    base = {
        "输入": str(SOURCE), "输入SHA256": sha, "第三问指标": plan["metrics"],
        "不可拆分单元": [list(u) for u in inst.units],
        "中继保障归属": {rid: {"运输架次": sorted(inst.trips_by_relay[rid]),
                               "单元": inst.units_by_relay[rid]} for rid in inst.relay_sorties},
        "库存": q.STOCK,
        "方案": {str(k): {
            "缺口优先": {"分区": groups_of(inst, summary[k]["pri"][0]),
                         "缺口总数": summary[k]["pri"][1]["shortfall_total"],
                         "配置总数": summary[k]["pri"][1]["resource_total"],
                         "CV": summary[k]["pri"][1]["cv"],
                         "各组资源需求": {q.CAT_NAME[c]: [summary[k]["pri"][1]["needs"][gi][c] for gi in range(k)]
                                          for c in q.CATEGORIES},
                         "各组运输架次占用时长_s": summary[k]["pri"][1]["work_s"]},
            "兼顾均衡": {"分区": groups_of(inst, summary[k]["zero"][0]),
                         "缺口总数": summary[k]["zero"][1]["shortfall_total"],
                         "配置总数": summary[k]["zero"][1]["resource_total"],
                         "CV": summary[k]["zero"][1]["cv"],
                         "与缺口优先同分区": summary[k]["zero"][0] == summary[k]["pri"][0],
                         "各组运输架次占用时长_s": summary[k]["zero"][1]["work_s"]},
            "均衡优先": {"分区": groups_of(inst, summary[k]["bal"][0]),
                         "缺口总数": summary[k]["bal"][1]["shortfall_total"],
                         "配置总数": summary[k]["bal"][1]["resource_total"],
                         "CV": summary[k]["bal"][1]["cv"],
                         "配置预算": summary[k]["budget"],
                         "各组资源需求": {q.CAT_NAME[c]: [summary[k]["bal"][1]["needs"][gi][c] for gi in range(k)]
                                          for c in q.CATEGORIES},
                         "各组运输架次占用时长_s": summary[k]["bal"][1]["work_s"]},
        } for k in (2, 3)},
    }
    (OUT / "基准方案.json").write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")

    for k in (2, 3):
        for name in ("缺口优先", "均衡优先"):
            f = json.loads((OUT / ("K%d_%s.json" % (k, name))).read_text(encoding="utf-8"))
            print("K=%d %-6s 缺口 %d | 配置 %d | CV %.6f | %s" % (
                k, name, f["缺口总数"], f["配置总数"], f["运输架次占用时长CV"],
                " / ".join("、".join(g) for g in f["任务组（服务区）"])))
    print("已写出 K2/K3 × 两档 JSON（兼顾均衡与缺口优先同分区、不单列文件）、方案三档对照.csv、基准方案.json")


if __name__ == "__main__":
    main()
