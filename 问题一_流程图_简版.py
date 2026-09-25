"""问题一「关键流程」简版流程图：只保留主干，合并迭代环节，供正文单栏使用。

与 `问题一_流程图.py`（完整版）配套，遵循同一规范
（tools/figure/references/chart-types/flowchart.md）：
- 节点形状按语义固定：平行四边形=数据读写，矩形=建模/计算，菱形=判断，圆角矩形=起止；
- 把三阶段 MILP 与切平面收敛合并为一个「迭代求解」节，只用一条主干 + 一处回边；
- 输出 flow_q1_model_simple.svg（文本可编辑）+ ≥300 DPI PNG，并做缺字/越界/压字自检。

运行：python 问题一_流程图_简版.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon
from matplotlib.textpath import TextPath

ROOT = Path(__file__).resolve().parent
SKILL_ROOT = Path(r"C:\Users\mika\.claude\skills\math-modeling")
sys.path.insert(0, str(SKILL_ROOT / "tools" / "figure" / "scripts"))
from export_figure import export_figure  # noqa: E402
from check_figure import check_figure, print_report  # noqa: E402

TARGET = ROOT / "figures" / "问题一_非枚举整数规划"
NAME = "flow_q1_model_simple"

# ---------------------------------------------------------------- 样式
plt.rcParams.update({
    "font.family": ["Times New Roman", "SimSun"],
    "font.size": 8,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "axes.unicode_minus": False,
})

INK = "#1A1A1A"
PAPER = "#FFFFFF"
LOOP = "#9E4A00"
EDGE_LW = 0.85
TXT_MAIN = 7.4
TXT_SUB = 6.2

X_SPAN, FIG_W_IN = 3.9, 3.5             # 单栏宽 3.5 in
CX = 1.90                               # 主干中心
X_IN = 1.05                             # 输入节点中心
BW = 2.70                               # 主干节点宽度
RX = 3.03                               # 切平面回边绕行竖线（节点右缘 3.25 之外）
GAP = 0.16
CUR = [-0.45]                           # 行游标（y 越大越靠上）
TITLE = "图 1  问题一关键流程"

ROWS: dict[str, tuple[float, float]] = {}
NODES: list[dict] = []
EDGES: list[dict] = []


def row(key: str, h: float) -> tuple[float, float]:
    CUR[0] -= h
    ROWS[key] = (CUR[0], CUR[0] + h)
    CUR[0] -= GAP
    return ROWS[key]


def node(key: str, shape: str, cx: float, label: str, *, sub: str | None = None,
         w: float = BW, h: float = 0.46) -> str:
    y0, y1 = row(key, h)
    NODES.append({"key": key, "shape": shape, "cx": cx, "y0": y0, "y1": y1,
                  "label": label, "sub": sub, "w": w, "h": h})
    return key


def edge(src: str, dst: str, *, tag: str | None = None, side: str = "auto") -> None:
    EDGES.append({"src": src, "dst": dst, "tag": tag, "side": side})


node("in_data", "io", X_IN, "DEM 航段 · 三机型 · 80 箱", sub="距离、海拔、能耗与时间参数",
     w=2.60, h=0.60)
node("cap", "rect", CX, "① 逐区最大安全载荷 q*", sub="式(2.9)", w=2.70, h=0.48)
node("check", "diamond", CX, "80 箱均可运输?", sub="质量/体积/能量", w=2.50, h=0.90)
node("iterate", "rect", CX, "② 逐箱直接指派 MILP 迭代求解", sub="架次 → 能耗 → 时间", w=2.90,
     h=0.48)
node("cut", "rect", CX, "能耗不足时新增切平面", sub="按当前解的质量点取切线", w=2.60, h=0.48)
node("out", "round", CX, "输出组批与复核结果", sub="18 架次 · 59.130290 kWh", w=2.70, h=0.50)

edge("in_data", "cap")
edge("cap", "check")
edge("check", "iterate", tag="是", side="left")
edge("check", "cut", tag="否")
edge("iterate", "cut", tag="否", side="left")
edge("cut", "iterate", side="right")
edge("iterate", "out", side="right")
_ = RX  # 切平面回边绕行竖线，见 draw_flow


# ---------------------------------------------------------------- 绘制
def shape_patch(n: dict):
    cx, y0, y1, w, h = n["cx"], n["y0"], n["y1"], n["w"], n["h"]
    if n["shape"] == "rect":
        return FancyBboxPatch((cx - w / 2, y0), w, h, boxstyle="square,pad=0",
                              linewidth=EDGE_LW, edgecolor=INK, facecolor=PAPER)
    if n["shape"] == "round":
        return FancyBboxPatch((cx - w / 2, y0), w, h,
                              boxstyle="round,pad=0,rounding_size=0.14",
                              linewidth=EDGE_LW, edgecolor=INK, facecolor=PAPER)
    if n["shape"] == "diamond":
        return Polygon([(cx, y0), (cx + w / 2, (y0 + y1) / 2), (cx, y1),
                        (cx - w / 2, (y0 + y1) / 2)],
                       closed=True, linewidth=EDGE_LW, edgecolor=INK, facecolor=PAPER)
    if n["shape"] == "io":
        lean = 0.20
        return Polygon([(cx - w / 2 + lean, y0), (cx + w / 2, y0),
                        (cx + w / 2 - lean, y1), (cx - w / 2, y1)],
                       closed=True, linewidth=EDGE_LW, edgecolor=INK, facecolor=PAPER)
    raise ValueError(n["shape"])


def node_texts(ax, n: dict) -> list:
    made = []
    cy = (n["y0"] + n["y1"]) / 2
    if n["sub"]:
        dy = 0.09 if n["h"] >= 0.52 else 0.07
        made.append(ax.text(n["cx"], cy + dy, n["label"], ha="center", va="center",
                            fontsize=TXT_MAIN, color=INK))
        made.append(ax.text(n["cx"], cy - dy - 0.02, n["sub"], ha="center", va="center",
                            fontsize=TXT_SUB, color="#3D3D3D"))
    else:
        made.append(ax.text(n["cx"], cy, n["label"], ha="center", va="center",
                            fontsize=TXT_MAIN, color=INK))
    return made


def draw_flow(ax) -> list:
    by_key = {n["key"]: n for n in NODES}
    made: list = []

    def line(pts, colour=INK, style="-"):
        for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
            last = i == len(pts) - 2
            ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>" if last else "-",
                                         mutation_scale=8.5, linewidth=EDGE_LW, color=colour,
                                         linestyle=style, shrinkA=0, shrinkB=0,
                                         joinstyle="miter", capstyle="butt"))

    def mid(n):
        return (n["y0"] + n["y1"]) / 2

    def tag_pos(s: dict, tag: str, side: str, ty: float) -> tuple[float, float]:
        """分支标签位置：默认贴主干竖线两侧；“否”出口贴菱形右顶点外侧。"""
        if side == "left":
            return CX - 0.36, ty
        if s["shape"] == "diamond":
            return s["cx"] + s["w"] / 2 + 0.14, ty
        return CX + 0.13, ty

    # 主干竖向连线 + 分支标签
    for e in EDGES:
        if e["src"] == "cut" and e["dst"] == "iterate":
            continue                          # 回边另画
        s, d = by_key[e["src"]], by_key[e["dst"]]
        if abs(s["cx"] - CX) < 1e-6 and abs(d["cx"] - CX) < 1e-6:
            line([(CX, s["y0"]), (CX, d["y1"])])
            if e["tag"]:
                ty = min((s["y0"] + d["y1"]) / 2, (s["y1"] + d["y0"]) / 2,
                         key=lambda v: abs(v - (s["y0"] + s["y1"]) / 2))
                tx, ty = tag_pos(s, e["tag"], e["side"], ty)
                ha = "left" if tx > CX else "right"
                ax.add_patch(Circle((tx, ty), 0.12, facecolor=PAPER,
                                    edgecolor="none", zorder=2))
                made.append(ax.text(tx, ty, e["tag"], ha=ha, va="center",
                                    fontsize=TXT_SUB, color=INK, zorder=3))
        else:                                 # 输入 → 载荷（横向）
            line([(s["cx"] + s["w"] / 2, mid(s)), (d["cx"] - d["w"] / 2, mid(d))])

    # 切平面回边：check 右侧绕行 → 沿 iterate 右缘进入其中部（与“否”分支错开）
    it, cut, chk = by_key["iterate"], by_key["cut"], by_key["check"]
    line([(chk["cx"] + chk["w"] / 2, mid(chk)), (RX, mid(chk)),
          (RX, mid(it) - 0.06), (it["cx"] + it["w"] / 2, mid(it) - 0.06)], colour=LOOP)
    return made


def build_figure():
    """画布按内容边界反推：横向固定单栏宽，纵向按内容比例伸展，不留空档。"""
    y_top = max(n["y1"] for n in NODES)
    y_bot = min(n["y0"] for n in NODES)
    x_lo = min(n["cx"] - n["w"] / 2 for n in NODES)
    x_hi = max(n["cx"] + n["w"] / 2 for n in NODES) + 0.78      # 右侧回边与注记
    pad = 0.12
    top_pad, bot_pad = 0.34, 0.62                                # 标题带 / 底部说明
    span_x = (x_hi - x_lo) + 2 * pad
    span_y = (y_top - y_bot) + top_pad + bot_pad
    fig = plt.figure(figsize=(FIG_W_IN, span_y * FIG_W_IN / span_x))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x_lo - pad, x_hi + pad)
    ax.set_ylim(y_bot - bot_pad, y_top + top_pad)
    ax.axis("off")

    texts = draw_flow(ax)
    for n in NODES:
        ax.add_patch(shape_patch(n))
        texts.extend(node_texts(ax, n))
    texts.append(ax.text((x_lo + x_hi) / 2, y_top + top_pad - 0.06, TITLE,
                         ha="center", va="top", fontsize=8.0, color=INK))
    texts.append(ax.text(x_lo - pad + 0.06, y_bot - bot_pad + 0.40,
                         "① 架次  ② 能耗  ③ 时间：词典序依次最小化",
                         ha="left", va="center", fontsize=TXT_SUB, color="#3D3D3D"))
    texts.append(ax.text(x_lo - pad + 0.06, y_bot - bot_pad + 0.14,
                         "橙色回边：能耗不足或下界未闭合时新增切平面后重解",
                         ha="left", va="center", fontsize=TXT_SUB, color=LOOP))
    return fig, ax, texts


# ---------------------------------------------------------------- 程序自检
def audit(fig, ax, texts) -> list[str]:
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
            limit = 0.12 if (ta.strip() in short or tb.strip() in short) else 0.02
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
