"""问题二可视化前的原始箱、机型和航段数据剖析。"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "问题二_参考口径"
SOURCE = ROOT / "数据" / "无人机应急物资运输基础数据"


def main():
    raw = list(load_workbook(SOURCE / "物资需求与配送时限.xlsx", read_only=True, data_only=True).worksheets[1].values)
    assert len(raw) == 81
    rows = []
    for item in raw[1:]:
        hard = []
        if item[5] == "是":
            hard.append(item[6])
        if item[2] == "医疗物资":
            hard.append(item[7])
        rows.append({"货箱编号": item[0], "服务区": item[1], "物资类型": item[2],
                     "质量_kg": item[3], "体积_m3": item[4], "是否首批": item[5],
                     "硬截止_s": min(hard) if hard else "", "期望送达_s": item[7],
                     "应急优先系数": item[8]})
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "原始逐箱输入_剖析.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    areas = defaultdict(lambda: {"箱数": 0, "总质量_kg": 0.0, "总体积_m3": 0.0, "硬时限箱数": 0})
    for row in rows:
        a = areas[row["服务区"]]
        a["箱数"] += 1
        a["总质量_kg"] += row["质量_kg"]
        a["总体积_m3"] += row["体积_m3"]
        a["硬时限箱数"] += bool(row["硬截止_s"])
    area_rows = [{"服务区": area, **value} for area, value in sorted(areas.items())]
    with (OUT / "原始服务区需求_剖析.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(area_rows[0]))
        writer.writeheader()
        writer.writerows(area_rows)
    stats = {"箱数": len(rows), "服务区": len(areas),
             "类别": dict(Counter(row["物资类型"] for row in rows)),
             "首批箱数": sum(row["是否首批"] == "是" for row in rows),
             "硬时限箱数": sum(bool(row["硬截止_s"]) for row in rows),
             "硬时限分布": dict(Counter(str(row["硬截止_s"]) for row in rows if row["硬截止_s"])),
             "总质量_kg": sum(row["质量_kg"] for row in rows),
             "总体积_m3": sum(row["体积_m3"] for row in rows),
             "质量范围_kg": [min(row["质量_kg"] for row in rows), max(row["质量_kg"] for row in rows)],
             "体积范围_m3": [min(row["体积_m3"] for row in rows), max(row["体积_m3"] for row in rows)]}
    (OUT / "原始输入剖析.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
