# -*- coding: utf-8 -*-
"""问题四分组政策前沿：在精确枚举中加入最小服务区数约束。

借鉴公开同题仓库的“原子任务块 + 全分区枚举 + 资源峰值复核”框架，
但只读取本仓库已认证的第三问方案。该脚本不改写官方缺口优先解，
额外给出不含单服务区组的可解释备选方案。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import q4_partition as q  # noqa: E402

SOURCE = ROOT / "code" / "问题三_改进求解" / "plan_windows_opt.json"
OUT = ROOT / "results" / "问题四_改进求解"


def area_groups(inst, groups):
    return q.partition_to_areas(inst, groups)


def record(inst, k, min_areas, label, groups, facts, source_sha):
    row = q.row_record(inst, k, label, groups, facts, facts["shortfall_total"])
    row.update({
        "输入": str(SOURCE.relative_to(ROOT)),
        "输入SHA256": source_sha,
        "每组最少服务区": min_areas,
        "约束说明": "每组服务区数量不少于给定下限；同一运输架次涉及区域仍不可拆分",
    })
    return row


def solve_policy(inst, k, min_areas):
    rows = []
    for raw in q.canonical_partitions(inst.n, k):
        groups = tuple(tuple(g) for g in raw)
        areas = area_groups(inst, groups)
        if min(map(len, areas)) < min_areas:
            continue
        rows.append((groups, q.partition_facts(inst, groups)))
    if not rows:
        raise ValueError("K=%d、每组至少%d区时无可行分区" % (k, min_areas))
    # 政策主方案仍采用缺口→配置→CV 的字典序，确保含义与原主方案一致。
    lex = min(rows, key=lambda x: (
        x[1]["shortfall_total"], x[1]["resource_total"], x[1]["cv"]))
    # 另给出纯工作量最均衡端点，形成政策前沿，不冒充库存友好方案。
    balanced = min(rows, key=lambda x: (
        x[1]["cv"], x[1]["shortfall_total"], x[1]["resource_total"]))
    return rows, lex, balanced


def main():
    plan = q.load_plan(SOURCE)
    inst = q.Instance(plan)
    source_sha = q.sha256_of(SOURCE)
    policies = [(2, 2), (2, 3), (3, 2), (3, 3)]
    output = {
        "输入": str(SOURCE.relative_to(ROOT)),
        "输入SHA256": source_sha,
        "不可拆分单元": [list(u) for u in inst.units],
        "方案": [],
    }
    csv_rows = []
    for k, lower in policies:
        rows, lex, balanced = solve_policy(inst, k, lower)
        for label, picked in (("缺口优先_规模约束", lex), ("纯均衡端点_规模约束", balanced)):
            groups, facts = picked
            rec = record(inst, k, lower, label, groups, facts, source_sha)
            output["方案"].append(rec)
            csv_rows.append({
                "K": k, "每组最少服务区": lower, "方案": label,
                "合法分区数": len(rows), "缺口总数": facts["shortfall_total"],
                "配置总数": facts["resource_total"], "工作量CV": round(facts["cv"], 9),
                "任务组": " / ".join("、".join(g) for g in area_groups(inst, groups)),
                "各组工作量_s": " / ".join("%.3f" % x for x in facts["work_s"]),
            })
            print("K=%d 最少%d区 %-18s gap=%d scale=%d CV=%.6f %s" % (
                k, lower, label, facts["shortfall_total"], facts["resource_total"],
                facts["cv"], csv_rows[-1]["任务组"]))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "分组规模约束方案.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "分组规模约束方案.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print("saved", OUT / "分组规模约束方案.json")


if __name__ == "__main__":
    main()
