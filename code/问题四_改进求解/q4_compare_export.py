# -*- coding: utf-8 -*-
"""第四问结果提交与权衡说明：全部数字取自 q4_baseline.py 生成的基准方案.json（唯一真源）。

产出：
  results/问题四_改进求解/均衡与缺口权衡.md
  results/问题四_改进求解/结果提交_问题四_改进求解.xlsx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q4_partition as q  # noqa: E402

OUT = q.DEFAULT_OUT
CATS = q.CATEGORIES
TIERS = ("缺口优先", "兼顾均衡", "均衡优先")


def load_plans(out: Path) -> dict:
    """三档方案数字来源：缺口优先与均衡优先取自明细 JSON；兼顾均衡取自基准方案.json。

    兼顾均衡在本次输入上与缺口优先同分区，因此不单列明细文件。
    """
    base = json.loads((out / "基准方案.json").read_text(encoding="utf-8"))
    plans = {}
    for k in (2, 3):
        plans[k] = {}
        for tier in ("缺口优先", "均衡优先"):
            path = out / ("K%d_%s.json" % (k, tier))
            if not path.exists():
                raise SystemExit("缺少 %s，请先运行 q4_baseline.py" % path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            # 明细 JSON 以中文名记录各类资源；这里按内部代号重新索引，便于统一计算
            needs = {c: raw["各组资源需求"][q.CAT_NAME[c]] for c in CATS}
            plans[k][tier] = {
                "分区": raw["任务组（服务区）"],
                "缺口总数": raw["缺口总数"],
                "配置总数": raw["配置总数"],
                "配置预算": raw["配置总数预算"],
                "CV": raw["运输架次占用时长CV"],
                "各组运输架次占用时长_s": raw["各组运输架次占用时长_s"],
                "各组资源需求": needs,
                "各组资源缺口": {c: max(0, sum(needs[c]) - q.STOCK[c]) for c in CATS},
                "与缺口优先同分区": False,
            }
        zero = base["方案"][str(k)]["兼顾均衡"]
        plans[k]["兼顾均衡"] = {
            "分区": zero["分区"],
            "缺口总数": zero["缺口总数"],
            "配置总数": zero["配置总数"],
            "配置预算": plans[k]["缺口优先"]["配置预算"],
            "CV": zero["CV"],
            "各组运输架次占用时长_s": zero["各组运输架次占用时长_s"],
            "各组资源需求": plans[k]["缺口优先"]["各组资源需求"],
            "各组资源缺口": plans[k]["缺口优先"]["各组资源缺口"],
            "与缺口优先同分区": bool(zero["与缺口优先同分区"]),
        }
    return plans


def main() -> None:
    base = json.loads((OUT / "基准方案.json").read_text(encoding="utf-8"))
    plans = load_plans(OUT)
    stock = base["库存"]
    # 各档方案的“本组运输架次”取自基准方案.json 不可拆分单元上的架次归属
    plan_obj = q.load_plan(q.DEFAULT_SOURCE)
    units = q.build_units(plan_obj)
    locate = {a: ci for ci, u in enumerate(units) for a in u}
    trip_unit = {t["id"]: locate[t["stops"][0]["area"]] for t in plan_obj["transport"]}
    groups_trips = {}
    for k in (2, 3):
        groups_trips[k] = {}
        for tier in TIERS:
            rows = []
            for areas in plans[k][tier]["分区"]:
                idx = {locate[a] for a in areas}
                rows.append(sorted(t for t, ci in trip_unit.items() if ci in idx))
            groups_trips[k][tier] = rows
    lines = []
    add = lines.append
    add("# 第四问：三档方案的资源缺口与工作量均衡权衡")
    add("")
    add("输入：`%s`" % base["输入"].replace("\\", "/"))
    add("")
    add("输入 SHA-256：`%s`" % base["输入SHA256"])
    add("")
    add("第三问指标：联合完成时间 %.6f s，运输 %d 架次，中继 %d 架次，通信缺口 %.1f s。" % (
        base["第三问指标"]["makespan_s"], base["第三问指标"]["transport_sorties"],
        base["第三问指标"]["relay_sorties"], base["第三问指标"]["communication_gap_s"]))
    add("")
    add("三档定义：")
    add("")
    add("- **档位① 缺口优先**：最小化 8 类资源正缺口之和；缺口不变下最小化配置总数；再最小化工作量 CV。")
    add("- **档位② 兼顾均衡**：在缺口总数等于最小缺口的分区中最小化 CV（不牺牲缺口）。")
    add("- **档位③ 均衡优先**：在配置总数 ≤ round(①配置总数 × 1.10) 的规模内最小化 CV（允许缺口上升）。")
    add("")

    for k in (2, 3):
        add("## K = %d 组" % k)
        add("")
        add("| 档位 | 缺口总数 | 配置总数 | 运输架次占用时长 CV | 各组运输架次占用时长 (s) |")
        add("| --- | --- | --- | --- | --- |")
        for tier in TIERS:
            f = plans[k][tier]
            label = {"缺口优先": "① 缺口优先",
                     "兼顾均衡": "② 兼顾均衡",
                     "均衡优先": "③ 均衡优先"}[tier]
            if tier == "均衡优先":
                label += "（配置≤%d）" % f["配置预算"]
            add("| %s | %d | %d | %.6f | %s |" % (
                label, f["缺口总数"], f["配置总数"], f["CV"],
                " / ".join("%.1f" % w for w in f["各组运输架次占用时长_s"])))
        add("")
        add("任务组划分：")
        add("")
        for tier in TIERS:
            f = plans[k][tier]
            add("- %s：%s" % (tier, "；".join("G%d=%s" % (gi + 1, "、".join(g))
                                             for gi, g in enumerate(f["分区"]))))
        add("")
        add("逐类资源（%s）：" % " / ".join("%s=%d" % (q.CAT_NAME[c], stock[c]) for c in CATS))
        add("")
        add("| 类别 | 资源 | 库存 | %s |" % " | ".join(
            "%s 总需求/缺口" % t for t in ("①", "②", "③")))
        add("| --- | --- | --- | %s |" % " | ".join("---" for _ in range(3)))
        for c in CATS:
            cells = []
            for tier in TIERS:
                f = plans[k][tier]
                need = f["各组资源需求"][c]
                gap = max(0, sum(need) - stock[c])
                cells.append("%d / %+d" % (sum(need), stock[c] - sum(need)))
            add("| %s | %s | %d | %s |" % (c, q.CAT_NAME[c], stock[c], " | ".join(cells)))
        add("")
        pri, zero, bal = plans[k]["缺口优先"], plans[k]["兼顾均衡"], plans[k]["均衡优先"]
        add("**均衡收益与代价（相对档位①）**")
        add("")
        add("- 档位②（%s）：CV %.6f → %.6f（改善 %.1f%%），缺口 %d → %d（%+d），配置 %d → %d（%+d）。"
            % ("与①同一分区（缺口最小解在该层唯一）" if zero["与缺口优先同分区"] else "换分区",
               pri["CV"], zero["CV"], (pri["CV"] - zero["CV"]) / pri["CV"] * 100,
               pri["缺口总数"], zero["缺口总数"], zero["缺口总数"] - pri["缺口总数"],
               pri["配置总数"], zero["配置总数"], zero["配置总数"] - pri["配置总数"]))
        add("- 档位③：CV %.6f → %.6f（改善 %.1f%%），缺口 %d → %d（%+d），配置 %d → %d（%+d）。"
            % (pri["CV"], bal["CV"], (pri["CV"] - bal["CV"]) / pri["CV"] * 100,
               pri["缺口总数"], bal["缺口总数"], bal["缺口总数"] - pri["缺口总数"],
               pri["配置总数"], bal["配置总数"], bal["配置总数"] - pri["配置总数"]))
        add("")
        add("结论：本输入上“缺口最小”与“缺口层内最均衡”并不冲突（档位②＝档位①），"
            "因此任何真正的均衡改善都必须付出额外资源缺口：K=%d 时为 +%d 件缺口、+%d 件配置。"
            % (k, bal["缺口总数"] - pri["缺口总数"], bal["配置总数"] - pri["配置总数"]))
        add("")

    add("## 缺口为何出现（结论）")
    add("")
    add("全部正缺口都来自 **B 型运输无人机**：{T05,T06,T10} 两两重叠必须分置三组，"
        "且 T11 与 T16 同属不可拆分单元 U0 并在 3066.000–3072.100 s（6.1 s）真实重叠，"
        "使 B 型峰值下界恒为 2；B 型实体机库存只有 2 架，"
        "于是 K=2 时各组 B 型峰值之和最小为 3（缺 1 架），K=3 时最小为 4（缺 2 架）。"
        "其余 7 类资源（A/C 型运输机、A/B/C 型共享电池、中继机、中继能源组件）总需求均不超过库存。")
    add("")
    add("这也解释了“组数越多缺口越大”的反直觉现象：**缺口按各组同时占用峰值之和计算**，"
        "分组越碎，同一批重叠架次被重复计入的次数越多，总需求越高。")
    add("")

    # ------------------------------------------------------------ 结果提交工作簿
    book = Workbook()
    ws = book.active
    ws.title = "Q4_分区与配置"
    ws.append(["K", "档位", "任务组编号", "服务区列表", "本组运输架次",
               *[q.CAT_NAME[c] for c in CATS], "运输架次占用时长_s"])
    for k in (2, 3):
        for tier in TIERS:
            f = plans[k][tier]
            for gi, areas in enumerate(f["分区"]):
                trip_ids = groups_trips[k][tier][gi]
                ws.append([k, tier, "G%d" % (gi + 1), "、".join(areas), ",".join(trip_ids),
                           *[f["各组资源需求"][c][gi] for c in CATS],
                           round(f["各组运输架次占用时长_s"][gi], 6)])

    ws2 = book.create_sheet("Q4_资源汇总")
    ws2.append(["K", "档位", "缺口总数", "配置总数", "CV",
                *[q.CAT_NAME[c] for c in CATS], *["%s_缺口" % q.CAT_NAME[c] for c in CATS]])
    for k in (2, 3):
        for tier in TIERS:
            f = plans[k][tier]
            needs = [sum(f["各组资源需求"][c]) for c in CATS]
            ws2.append([k, tier, f["缺口总数"], f["配置总数"], round(f["CV"], 6),
                        *needs, *[max(0, n - stock[c]) for n, c in zip(needs, CATS)]])

    ws3 = book.create_sheet("Q4_中继复制明细")
    ws3.append(["K", "档位", "任务组编号", "中继架次", "实体机", "能源组件", "悬停点",
                "被保障运输架次", "该架次保障的全部单元", "覆盖服务区"])
    for k in (2, 3):
        detail = json.loads((OUT / ("K%d_缺口优先.json" % k)).read_text(encoding="utf-8"))
        for gname, rows in detail["中继复制明细"].items():
            for row in rows:
                ws3.append([k, "缺口优先", gname, row["中继架次"], row["实体机"], row["能源组件"],
                            row["悬停点"], ",".join(row["被保障运输架次"]),
                            "U%s" % "+U".join(map(str, row["本架次保障的全部单元"])),
                            "、".join(row["本组命中服务区"])])

    ws4 = book.create_sheet("口径与来源")
    ws4.append(["项目", "内容"])
    for key, value in (
        ("唯一输入", base["输入"]),
        ("输入SHA256", base["输入SHA256"]),
        ("第三问完成时间_s", base["第三问指标"]["makespan_s"]),
        ("运输架次 / 中继架次", "%d / %d" % (base["第三问指标"]["transport_sorties"],
                                             base["第三问指标"]["relay_sorties"])),
        ("通信缺口_s", base["第三问指标"]["communication_gap_s"]),
        ("不可拆分单元数", len(base["不可拆分单元"])),
        ("单元划分", " ； ".join("U%d=%s" % (i, "、".join(u)) for i, u in enumerate(base["不可拆分单元"]))),
        ("运输无人机占用", "[出发, 返航)"),
        ("同型共享电池占用", "[出发, 充满)"),
        ("中继无人机占用", "[出发, 返航+架次周转时间)"),
        ("中继能源组件占用", "[出发, 充满)"),
        ("区间口径", "半开区间，同刻结束先于开始"),
        ("中继复制规则", "中继架次保障的全部单元都落在同一任务组时，该组独立配置一整架次；跨组则每组各配一套"),
        ("工作量口径", "Σ(返航−出发) = 运输架次占用时长（含准备、装载与交接，非纯飞行时长）"),
        ("库存", json.dumps({q.CAT_NAME[c]: stock[c] for c in CATS}, ensure_ascii=False)),
        ("本轮固定不变", "货箱组批、运输路线、访问顺序、运输与中继时序、通信保障关系"),
        ("本轮唯一决策", "服务区分组 + 各组资源配置"),
        ("未使用的旧结果", "results/问题三_参考口径/主方案_完整方案.json（9573.284 s，已在清理中移除，可由 python code/问题三四_复现.py 重建）；"
                          "code/问题三_改进求解/plan_3relay_fixed_final.json（未获 100% 连续认证）"),
    ):
        ws4.append([key, value])

    for sheet in book.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", start_color="DDEBF7")
            cell.alignment = Alignment(horizontal="center")
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 64)

    book.save(OUT / "结果提交_问题四_改进求解.xlsx")
    (OUT / "均衡与缺口权衡.md").write_text("\n".join(lines), encoding="utf-8")
    print("已写出：", OUT / "结果提交_问题四_改进求解.xlsx")
    print("已写出：", OUT / "均衡与缺口权衡.md")


if __name__ == "__main__":
    main()
