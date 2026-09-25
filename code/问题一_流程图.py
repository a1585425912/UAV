"""按科研可视化 Skill 的「建模流程图规范」重绘问题一子问题流程图。

规范要点（tools/figure/references/chart-types/flowchart.md）：
- 节点形状按语义固定：圆角矩形=起止，矩形=处理，菱形=判断，平行四边形=数据读写；
- 实线有向箭头表示控制流/数据流；必要时用浅色底纹分区，灰度下仍可辨；
- 节点标签简短、术语与正文一致；每个节点与连线都能对应真实模型或代码；
- 输出 SVG（文本可编辑）+ ≥300 DPI PNG，命名 flow_q1_model.*。

流程图内容来自 `问题一_直接指派整数规划.py`、`问题一_基础计算.py`
与 `问题一_直接指派审计.py` 的实际实现，不画代码里没有的模块。

运行：python 问题一_流程图.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
from matplotlib.textpath import TextPath

ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = Path(r"C:\Users\mika\.claude\skills\math-modeling")
sys.path.insert(0, str(SKILL_ROOT / "tools" / "figure" / "scripts"))
from export_figure import export_figure  # noqa: E402
from check_figure import check_figure, print_report  # noqa: E402

TARGET = ROOT / "figures" / "问题一_非枚举整数规划"
NAME = "flow_q1_model"

# ---------------------------------------------------------------- 样式
plt.rcParams.update({
    "font.family": ["Times New Roman", "SimSun"],
    "font.size": 8,
    "svg.fonttype": "none",          # SVG 文本可编辑
    "pdf.fonttype": 42,
    "axes.unicode_minus": False,
})

INK = "#1A1A1A"        # 主线条/文字：近黑
PAPER = "#FFFFFF"      # 节点填充：纯白
BAND = "#F1F1F1"       # 阶段底纹：浅灰，灰度下仍可与白底区分
LOOP = "#9E4A00"       # 反馈边：单一强调色（非红绿对比）
EDGE_LW = 0.85
TXT_MAIN = 7.6
TXT_SUB = 6.4

FIG_W_IN = 7.2
UNIT_IN = 0.44                          # 数据坐标 1 单位对应的英寸数
TITLE = "图 1  问题一求解流程：最大安全载荷筛选与逐箱直接指派 MILP 能耗切平面"
CAPTION = ("注：节点形状——平行四边形为数据读写，矩形为计算/建模，菱形为判断，圆角矩形为起止；"
           "橙色虚线回边为切平面迭代（否分支新增切平面后重解）。\n"
           "流程对应 flow_q1_model.* 的生成脚本 问题一_流程图.py；求解与审计实现见 "
           "问题一_直接指派整数规划.py、问题一_直接指派审计.py。")

# ---------------------------------------------------------------- 坐标骨架
XL, XC, XR = 0.92, 3.45, 5.98          # 顶部三列输入节点中心
BXC = XC                                # 流程节点中心（与中列对齐）
BAND_L, BAND_R = 0.15, 6.90
SPINE_L, SPINE_R = 0.55, 6.45           # 反馈边绕行竖线（位于节点与分区边框之间）
TITLE_PAD = 0.85                        # 画布顶部到第一个输入节点的距离
CUR = [-TITLE_PAD]                      # 自上而下的行游标（数据坐标 y，越大越靠上）
GAP = 0.14
ROWS: dict[str, tuple[float, float]] = {}
BANDS: list[dict] = []
CAPTION_PAD = 0.95                      # 最后一个节点到画布底部的距离


def band(title: str) -> None:
    """开启一个阶段分区：分区顶边 = 当前游标，标题占一条标题带。"""
    CUR[0] -= 0.30                       # 分区间距
    BANDS.append({"title": title, "y0_top": CUR[0], "y1": CUR[0]})
    CUR[0] -= 0.50                       # 标题带 + 首个节点的上边距


def row(key: str, h: float = 0.54) -> tuple[float, float]:
    """分配一行（返回该行的 y0/y1），行序自上而下。"""
    CUR[0] -= h
    ROWS[key] = (CUR[0], CUR[0] + h)
    if BANDS:
        BANDS[-1]["y0"] = CUR[0] - 0.20      # 分区底边始终跟随最后一个节点
    CUR[0] -= GAP
    return ROWS[key]


def y_gap(extra: float = 0.10) -> None:
    CUR[0] -= extra


# ---------------------------------------------------------------- 节点定义
NODES: list[dict] = []
EDGES: list[dict] = []


def node(key: str, shape: str, col: float, label: str, *, sub: str | None = None,
         w: float = 2.40, h: float = 0.56):
    y0, y1 = row(key, h)
    NODES.append({"key": key, "shape": shape, "cx": col, "y0": y0, "y1": y1,
                  "label": label, "sub": sub, "w": w, "h": h})
    return key


def edge(src: str, dst: str, *, kind: str = "flow", tag: str | None = None,
         route_x: float | None = None):
    EDGES.append({"src": src, "dst": dst, "kind": kind, "tag": tag, "route_x": route_x})


# —— 输入（平行四边形：数据读写） ——
node("in_geo", "io", XL, "镇龙乡 DEM", sub="与 15 个服务区", w=2.07)
node("in_uav", "io", XC, "运输无人机参数", sub="A/B/C 三型", w=2.07)
node("in_box", "io", XR, "80 个货箱", sub="质量/体积/服务区", w=2.07)
y_gap(0.10)
node("prepare", "rect", BXC, "航段几何与能耗/时间模型", sub="式(1.2)–(1.8)", w=4.60, h=0.62)
node("capacity", "rect", BXC, "逐区最大安全载荷 q*", sub="二分求根，式(2.9)", w=3.10)
node("check_box", "diamond", BXC, "单箱可运输?", sub="质量/体积/能量", w=3.30, h=1.00)
y_gap(0.12)
node("fix_data", "rect", BXC, "修正数据口径", sub="不得默认已配送", w=2.70)
node("abort", "round", BXC, "报错退出", sub="该服务区无可行解", w=2.70)

# —— 阶段 1：最小化架次数 ——
band("阶段 1  最少架次：先定架次数")
node("s1_build", "rect", BXC, "构造逐箱直接指派 0-1 模型", sub="式(2.10)–(2.13)", w=4.80, h=0.62)
node("s1_opt", "rect", BXC, "MILP 求最少架次", sub="贪心上界 + 零载荷初始切点", w=4.30)
node("s1_ok", "diamond", BXC, "实际能耗满足能量约束?", sub="逐架次真实能耗复核", w=3.60, h=1.00)
y_gap(0.12)
node("s1_add", "rect", BXC, "新增能耗切平面", sub="在解的质量点上取切线", w=3.30)
node("s1_lock", "round", BXC, "记录最少架次 N*", sub="固定架次数进入阶段 2", w=3.30)

# —— 阶段 2：最小化总能耗 ——
band("阶段 2  最少能耗：架次数固定")
node("s2_build", "rect", BXC, "MILP 最小化总能耗（架次数固定）", sub="目标 E，式(2.13)", w=4.80, h=0.62)
node("s2_ok", "diamond", BXC, "能耗下界闭合?", sub="真实能耗 − 下界 ≤ 1e-6 kWh", w=3.90, h=1.00)
y_gap(0.12)
node("s2_add", "rect", BXC, "新增能耗切平面", sub="下界随切点抬高", w=3.30)
node("s2_lock", "round", BXC, "锁定最优能耗 E*", sub="进入阶段 3 比较", w=3.30)

# —— 阶段 3：最小化累计作业时间 ——
band("阶段 3  累计作业时间：前两目标固定")
node("s3_build", "rect", BXC, "MILP 最小化累计作业时间", sub="E ≤ E*+1e-6，式(2.13)", w=4.80, h=0.62)
node("s3_ok", "diamond", BXC, "能耗仍在容差内?", sub="真实能耗复核 + 切平面", w=3.90, h=1.00)
y_gap(0.12)
node("s3_add", "rect", BXC, "新增能耗切平面", sub="保持能耗不越限", w=3.30)
node("s3_lock", "round", BXC, "得到词典序最优组批", sub="架次 → 能耗 → 时间", w=3.30)

# —— 输出与验证 ——
band("输出与验证")
node("out_audit", "rect", BXC, "最优组批逐架次表", sub="机型/箱号/质量/体积/能耗/SOC", w=4.40)
node("out_verify", "rect", BXC, "独立审计复核", sub="80 箱恰好覆盖一次", w=4.40)
node("out_sens", "rect", BXC, "返航余量敏感性重算", sub="10% / 20% / 25% / 30%", w=4.40)
y_gap(0.10)
node("out_files", "round", BXC, "输出结果文件", sub="xlsx / csv / json", w=3.60)

if BANDS:
    BANDS[-1]["y0"] = ROWS["out_files"][0] - 0.20

# ---------------------------------------------------------------- 连线
edge("in_geo", "prepare")
edge("in_uav", "prepare")
edge("in_box", "prepare")
edge("prepare", "capacity")
edge("capacity", "check_box")
edge("check_box", "s1_build", tag="是")
edge("check_box", "fix_data", kind="no", route_x=XL + 0.02, tag="否")
edge("fix_data", "abort")
edge("s1_build", "s1_opt")
edge("s1_opt", "s1_ok")
edge("s1_ok", "s1_lock", tag="是")
edge("s1_ok", "s1_add", kind="no", route_x=SPINE_R, tag="否：加切平面")
edge("s1_add", "s1_build", kind="loop", route_x=SPINE_L, tag="重解")
edge("s1_lock", "s2_build")
edge("s2_build", "s2_ok")
edge("s2_ok", "s2_lock", tag="是")
edge("s2_ok", "s2_add", kind="no", route_x=SPINE_R, tag="否：加切平面")
edge("s2_add", "s2_build", kind="loop", route_x=SPINE_L, tag="重解")
edge("s2_lock", "s3_build")
edge("s3_build", "s3_ok")
edge("s3_ok", "s3_lock", tag="是")
edge("s3_ok", "s3_add", kind="no", route_x=SPINE_R, tag="否：加切平面")
edge("s3_add", "s3_build", kind="loop", route_x=SPINE_L, tag="重解")
edge("s3_lock", "out_audit")
edge("out_audit", "out_verify")
edge("out_verify", "out_sens")
edge("out_sens", "out_files")


# ---------------------------------------------------------------- 绘制
def _shape_patch(n: dict, fill: str = PAPER):
    cx, y0, y1, w, h = n["cx"], n["y0"], n["y1"], n["w"], n["h"]
    if n["shape"] == "rect":
        return FancyBboxPatch((cx - w / 2, y0), w, h, boxstyle="square,pad=0",
                              linewidth=EDGE_LW, edgecolor=INK, facecolor=fill)
    if n["shape"] == "round":
        return FancyBboxPatch((cx - w / 2, y0), w, h,
                              boxstyle="round,pad=0,rounding_size=0.14",
                              linewidth=EDGE_LW, edgecolor=INK, facecolor=fill)
    if n["shape"] == "diamond":
        return Polygon([(cx, y0), (cx + w / 2, (y0 + y1) / 2), (cx, y1),
                        (cx - w / 2, (y0 + y1) / 2)],
                       closed=True, linewidth=EDGE_LW, edgecolor=INK, facecolor=fill)
    if n["shape"] == "io":
        lean = 0.16
        return Polygon([(cx - w / 2 + lean, y0), (cx + w / 2, y0),
                        (cx + w / 2 - lean, y1), (cx - w / 2, y1)],
                       closed=True, linewidth=EDGE_LW, edgecolor=INK, facecolor=fill)
    raise ValueError(n["shape"])


def _texts(ax, n: dict) -> list:
    made = []
    cy = (n["y0"] + n["y1"]) / 2
    if n["sub"]:
        made.append(ax.text(n["cx"], cy + 0.13, n["label"], ha="center", va="center",
                            fontsize=TXT_MAIN, color=INK))
        made.append(ax.text(n["cx"], cy - 0.15, n["sub"], ha="center", va="center",
                            fontsize=TXT_SUB, color="#3D3D3D"))
    else:
        made.append(ax.text(n["cx"], cy, n["label"], ha="center", va="center",
                            fontsize=TXT_MAIN, color=INK))
    return made


def _poly_arrow(ax, pts, *, colour: str, style, width: float = EDGE_LW) -> None:
    for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
        last = i == len(pts) - 2
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>" if last else "-",
                                     mutation_scale=8.5, linewidth=width, color=colour,
                                     linestyle=style, shrinkA=0, shrinkB=0,
                                     joinstyle="miter", capstyle="butt"))


def _tag_x(s: dict, y: float) -> float:
    """分支标签的横向位置：默认贴近连线；若会压到阶段标题带则右移让位。"""
    x = s["cx"] + 0.14
    for b in BANDS:
        if b["title"] == "输出与验证":
            continue
        strip = (b["y1"] - 0.52, b["y1"])
        if strip[0] <= y <= strip[1]:
            return BXC + 0.72
    return x


def draw_edges(ax) -> list:
    by_key = {n["key"]: n for n in NODES}
    made: list = []
    for e in EDGES:
        s, d = by_key[e["src"]], by_key[e["dst"]]
        # ① 同列上下相接：竖直线
        if e["kind"] == "flow" and abs(s["cx"] - d["cx"]) < 1e-6 and d["y1"] < s["y0"]:
            _poly_arrow(ax, [(s["cx"], s["y0"]), (d["cx"], d["y1"])], colour=INK, style="-")
            if e.get("tag"):
                if s["key"] == "check_box" and e["tag"] == "是":
                    # 该判断的“否”出口在左下方，为避免“是”与异常分支压字，贴右顶点标注
                    made.append(ax.text(s["cx"] + s["w"] / 2 + 0.10, (s["y0"] + s["y1"]) / 2,
                                        e["tag"], ha="left", va="center",
                                        fontsize=TXT_SUB, color=INK))
                else:
                    cands = ((s["y0"] + d["y1"]) / 2, (s["y1"] + d["y0"]) / 2)
                    ty = min(cands, key=lambda v: abs(v - (s["y0"] + s["y1"]) / 2))
                    made.append(ax.text(_tag_x(s, ty), ty, e["tag"], ha="left",
                                        va="center", fontsize=TXT_SUB, color=INK))
            continue
        # ② 顶部三条输入汇入预处理
        if e["kind"] == "flow":
            _poly_arrow(ax, [(s["cx"], s["y0"]), (d["cx"], d["y1"])], colour=INK, style="-")
            continue
        # ③ 反馈边：水平引出 → 竖直绕行 → 水平进入
        rx = e["route_x"]
        if rx is None:
            raise ValueError(f"{e['src']}→{e['dst']} 缺少 route_x")
        colour = LOOP
        style = "-" if e["kind"] == "no" else (0, (3.4, 1.9))
        sy = (s["y0"] + s["y1"]) / 2
        dy = (d["y0"] + d["y1"]) / 2
        if rx > s["cx"]:
            pts = [(s["cx"] + s["w"] / 2, sy), (rx, sy), (rx, dy), (d["cx"] + d["w"] / 2, dy)]
            ha, tx = "left", rx + 0.07
        else:
            pts = [(s["cx"] - s["w"] / 2, sy), (rx, sy), (rx, dy), (d["cx"] - d["w"] / 2, dy)]
            ha, tx = "right", rx - 0.07
        _poly_arrow(ax, pts, colour=colour, style=style)
        if e.get("tag"):
            made.append(ax.text(tx, (sy + dy) / 2, e["tag"], ha=ha, va="center",
                                fontsize=TXT_SUB, color=colour, rotation=90))
    return made


def build_figure():
    top = 0.10                                        # 数据坐标画布上界
    bottom = ROWS["out_files"][0] - CAPTION_PAD       # 数据坐标画布下界
    span = top - bottom
    height_in = span * UNIT_IN
    fig = plt.figure(figsize=(FIG_W_IN, height_in))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 7.2)
    ax.set_ylim(bottom, top)
    ax.axis("off")

    texts: list = []
    for b in BANDS:
        if b["title"] == "输出与验证":
            continue
        top_edge, bottom_edge = b["y1"], b["y0"]
        ax.add_patch(Rectangle((BAND_L, bottom_edge), BAND_R - BAND_L, top_edge - bottom_edge,
                               facecolor=BAND, edgecolor="#B8B8B8", linewidth=0.6, zorder=0))
        texts.append(ax.text(BXC, top_edge - 0.22, b["title"], ha="center", va="center",
                             fontsize=TXT_SUB, color="#333333", zorder=1))

    texts.extend(draw_edges(ax))

    for n in NODES:
        ax.add_patch(_shape_patch(n))
        texts.extend(_texts(ax, n))

    texts.append(ax.text(3.6, top - 0.32, TITLE, ha="center", va="center",
                         fontsize=8.4, color=INK))
    texts.append(ax.text(0.02, bottom + 0.18, CAPTION, ha="left", va="bottom",
                         fontsize=TXT_SUB, color="#3D3D3D", linespacing=1.6))
    return fig, ax, texts


# ---------------------------------------------------------------- 程序自检
def audit(fig, ax, texts) -> list[str]:
    """渲染前自检：字形缺字、文字越界、文字互相压盖。"""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    problems: list[str] = []

    boxes = []
    for t in texts:
        bb = t.get_window_extent(renderer=renderer)
        (x0, y0), (x1, y1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        boxes.append((t.get_text(), min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)))

    x_lo, x_hi = ax.get_xlim()
    y_lo, y_hi = min(ax.get_ylim()), max(ax.get_ylim())
    for txt, x0, x1, y0, y1 in boxes:
        if x0 < x_lo + 0.01 or x1 > x_hi - 0.01 or y0 < y_lo + 0.01 or y1 > y_hi - 0.01:
            problems.append(f"越界: 「{txt}」 x[{x0:.2f},{x1:.2f}] y[{y0:.2f},{y1:.2f}]")

    short = ("是", "否")
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ta, ax0, ax1, ay0, ay1 = boxes[i]
            tb, bx0, bx1, by0, by1 = boxes[j]
            limit = 0.10 if (ta.strip() in short or tb.strip() in short) else 0.02
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 0.02 and oy > limit:
                problems.append(f"文字重叠: 「{ta}」×「{tb}」 ({ox:.2f}×{oy:.2f})")

    fp = FontProperties(family=plt.rcParams["font.family"], size=TXT_MAIN)
    for txt, *_ in boxes:
        for ch in txt:
            if ch.strip() == "":
                continue
            try:
                w = TextPath((0, 0), ch, prop=fp, usetex=False).get_extents().width
            except Exception:
                continue
            if w <= 0:
                problems.append(f"疑似缺字: 「{ch}」（{txt}）")
    return problems


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    fig, ax, texts = build_figure()
    problems = audit(fig, ax, texts)
    print("== 渲染前程序自检 ==")
    if problems:
        for p in problems:
            print("  [FAIL]", p)
    else:
        print("  [PASS] 无缺字、无越界、无文字重叠")

    paths = export_figure(fig, str(TARGET / NAME), formats=["svg", "png"],
                          dpi=400, grayscale_preview=True, tight=True)
    print("\n== 导出 ==")
    for p in paths:
        print("  ", p)
    plt.close(fig)

    print("\n== check_figure.py 合规审计 ==")
    worst = 0
    for extra in ("", "_grayscale"):
        target = str(TARGET / f"{NAME}{extra}.png")
        issues, info = check_figure(target, min_dpi=300)
        print_report(target, issues, info)
        worst = max(worst, max([{"INFO": 0, "WARN": 1, "FAIL": 2}[s] for s, _ in issues] or [0]))
    target = str(TARGET / f"{NAME}.svg")
    issues, info = check_figure(target)
    print_report(target, issues, info)
    worst = max(worst, max([{"INFO": 0, "WARN": 1, "FAIL": 2}[s] for s, _ in issues] or [0]))
    return 2 if worst >= 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
