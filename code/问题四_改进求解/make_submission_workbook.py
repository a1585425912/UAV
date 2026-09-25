# -*- coding: utf-8 -*-
"""把 UAV/结果提交模板.xlsx 的 6 张表按现有结果填满，另加一张来源说明表。

数据来源（全部为磁盘上已有结果，脚本不改动任何结果文件）：
  Q1_单点组批   ← results/问题一_非枚举整数规划/最优组批_逐架次.csv（20% 返航余量基准，18 架次）
  Q2_运输架次   ← code/问题三_改进求解/plan_windows_opt.json（第三问已认证方案的运输部分，22 架次）
  Q2_逐箱交付   ← 同上，按 stops[].ids 与 deliveries 得到逐箱交付完成时刻
  Q3_中继架次   ← 同上 relays[]（4 个中继架次）
  Q3_通信保障   ← 同上 communications[]（250 段连续通信区间）
  Q4_分区配置   ← results/问题四_改进求解/K{2,3}_缺口优先.json（每组所需 8 类资源）
  Z_来源说明    ← 本脚本生成，记录每个来源文件路径与 SHA-256
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "结果提交模板.xlsx"
OUT_PATH = ROOT / "结果提交_完整方案.xlsx"

Q1_CSV = ROOT / "results" / "问题一_非枚举整数规划" / "最优组批_逐架次.csv"
Q3_PLAN = ROOT / "code" / "问题三_改进求解" / "plan_windows_opt.json"
Q4_DIR = ROOT / "results" / "问题四_改进求解"
CATS = ("U_A", "U_B", "U_C", "B_A", "B_B", "B_C", "R", "RB")
CAT_NAME = {"U_A": "A型运输无人机", "U_B": "B型运输无人机", "U_C": "C型运输无人机",
            "B_A": "A型共享电池", "B_B": "B型共享电池", "B_C": "C型共享电池",
            "R": "中继无人机", "RB": "中继能源组件"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fill(sheet, rows) -> None:
    """从第 2 行开始写数据，全部按模板既有列顺序。"""
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            sheet.cell(row=r, column=c, value=value)


def main() -> None:
    plan = json.loads(Q3_PLAN.read_text(encoding="utf-8"))
    trips = {t["id"]: t for t in plan["transport"]}
    wb = load_workbook(TEMPLATE)
    used = {}

    # ---------------------------------------------------------------- Q1_单点组批
    q1_rows = []
    with io.open(Q1_CSV, encoding="utf-8-sig") as fh:
        for i, rec in enumerate(csv.DictReader(fh), start=1):
            q1_rows.append([
                "Q1-%02d" % i, rec["服务区"], rec["机型"], rec["货箱编号列表"],
                float(rec["质量_kg"]), float(rec["体积_m3"]), float(rec["作业时间_s"]),
                float(rec["能耗_kwh"]), round(float(rec["返航SOC"]) * 100, 6),
            ])
    fill(wb["Q1_单点组批"], q1_rows)
    used["Q1_单点组批"] = {"来源": Q1_CSV, "行数": len(q1_rows)}

    # ---------------------------------------------------------------- Q2_运输架次
    q2_rows = []
    for tid in sorted(trips):
        t = trips[tid]
        order = "→".join(s["area"] for s in t["stops"])
        q2_rows.append([tid, t["uav"], t["model"], t["battery"],
                        t["start_s"], order, t["return_s"], t["energy_kwh"]])
    fill(wb["Q2_运输架次"], q2_rows)
    used["Q2_运输架次"] = {"来源": Q3_PLAN, "行数": len(q2_rows)}

    # ---------------------------------------------------------------- Q2_逐箱交付
    q2_boxes = []
    for tid in sorted(trips):
        t = trips[tid]
        for stop in t["stops"]:
            for box in stop["ids"]:
                q2_boxes.append([box, tid, stop["area"], plan["deliveries"][box]])
    fill(wb["Q2_逐箱交付"], q2_boxes)
    used["Q2_逐箱交付"] = {"来源": Q3_PLAN, "行数": len(q2_boxes), "箱数校验": len(plan["deliveries"])}

    # ---------------------------------------------------------------- Q3_中继架次
    q3_relay = []
    for r in sorted(plan["relays"], key=lambda x: x["id"]):
        q3_relay.append([r["id"], r["relay_id"], r["energy_id"], r["depart_s"],
                         r["lon"], r["lat"], r["hover_alt_m"], r["link_ready_s"],
                         r["service_end_s"], r["return_s"], r["energy_kwh"]])
    fill(wb["Q3_中继架次"], q3_relay)
    used["Q3_中继架次"] = {"来源": Q3_PLAN, "行数": len(q3_relay)}

    # ---------------------------------------------------------------- Q3_通信保障
    q3_comm = [[c["trip"], c["phase"], c["start_s"], c["end_s"],
                c["status"], c["relay_id"] or ""] for c in plan["communications"]]
    fill(wb["Q3_通信保障"], q3_comm)
    used["Q3_通信保障"] = {"来源": Q3_PLAN, "行数": len(q3_comm),
                           "直连段": sum(1 for c in plan["communications"] if c["status"] == "直连"),
                           "中继段": sum(1 for c in plan["communications"] if c["status"] == "中继")}

    # ---------------------------------------------------------------- Q4_分区配置
    q4_rows = []
    for k in (2, 3):
        rec = json.loads((Q4_DIR / ("K%d_缺口优先.json" % k)).read_text(encoding="utf-8"))
        groups = rec["任务组（服务区）"]
        for gi, areas in enumerate(groups):
            q4_rows.append([k, "G%d" % (gi + 1), "、".join(areas),
                            *[rec["各组资源需求"][CAT_NAME[c]][gi] for c in CATS]])
    fill(wb["Q4_分区配置"], q4_rows)
    used["Q4_分区配置"] = {"来源": Q4_DIR / "K2_缺口优先.json 与 K3_缺口优先.json",
                           "行数": len(q4_rows)}

    # ---------------------------------------------------------------- 来源说明
    ws = wb.create_sheet("Z_来源说明")
    ws.append(["模板工作表", "填写内容", "来源文件", "SHA-256", "记录数"])
    sources = [
        ("Q1_单点组批", "20% 返航余量基准组批：18 架次 / 80 箱", Q1_CSV),
        ("Q2_运输架次", "第三问已认证方案的运输架次（22 条）", Q3_PLAN),
        ("Q2_逐箱交付", "同一方案的逐箱交付完成时刻（80 箱）", Q3_PLAN),
        ("Q3_中继架次", "同一方案的 4 个中继架次", Q3_PLAN),
        ("Q3_通信保障", "同一方案的 250 段连续通信区间", Q3_PLAN),
        ("Q4_分区配置", "K=2 与 K=3 缺口优先方案的分区与各组资源需求（7 行）",
         Q4_DIR / "K3_缺口优先.json"),
    ]
    for name, desc, path in sources:
        ws.append([name, desc, str(path.relative_to(ROOT)).replace("\\", "/"),
                   sha256_of(path), used.get(name, {}).get("行数", "")])
    ws.append([])
    ws.append(["说明", "本工作簿由 结果提交模板.xlsx 复制后填表生成，模板表头与表序未改动；"
                       "Q2/Q3 同源于第三问唯一输入 计划文件，Q1 为问题一基准组批结果，"
                       "Q4 取缺口优先（主方案）档位。", "", "", ""])
    ws.append(["第三问指标", "联合完成时间 %.6f s；运输架次 %d；中继架次 %d；通信缺口 %.1f s；货箱 %d 个" % (
        plan["metrics"]["makespan_s"], plan["metrics"]["transport_sorties"],
        plan["metrics"]["relay_sorties"], plan["metrics"]["communication_gap_s"],
        plan["metrics"]["boxes"]), "", str(Q3_PLAN.relative_to(ROOT)).replace("\\", "/"),
        sha256_of(Q3_PLAN), ""])
    ws.append(["Q4 缺口说明", "K=2 缺口 2（B 型运输无人机 1 架、中继无人机 1 架）、配置 30；"
                              "K=3 缺口 4（B 型运输无人机 2 架、中继无人机 2 架）、配置 33；"
                              "其余 6 类资源均不缺，原因见 results/问题四_改进求解/第四问总结报告.md",
               "", "", "", ""])

    for sheet in wb.worksheets:
        for cell in sheet[1]:
            if cell.value:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", start_color="DDEBF7")
                cell.alignment = Alignment(horizontal="center")
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = max((len(str(c.value)) if c.value is not None else 0) for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 58)

    wb.save(OUT_PATH)
    print("已写出：", OUT_PATH)
    for name, info in used.items():
        print("  %-12s %d 行  <- %s" % (name, info["行数"], info["来源"]))


if __name__ == "__main__":
    main()
