r"""生成 figures/问题二_改进方案 下的全部图件（路线图、四口径对比、甘特图、硬时限余量）。

用法：python 问题二_改进求解\make_figures.py
数据源：results/问题二_改进方案/方案_*_完整方案.json 与 方案_*_逐架次.csv / _逐箱交付.csv / 节点坐标与作业海拔.csv
"""
from __future__ import annotations
import csv, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from scipy.io import loadmat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "results", "问题二_改进方案")
OUT = os.path.join(ROOT, "figures", "问题二_改进方案")
os.makedirs(OUT, exist_ok=True)
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
plt.rcParams["font.family"] = FONT.get_name(); plt.rcParams["axes.unicode_minus"] = False; plt.rcParams["svg.fonttype"] = "none"
BLUE, ORANGE, GREEN, RED = "#0072B2", "#E69F00", "#009E73", "#D55E00"
MODELS = {"A": BLUE, "B": ORANGE, "C": GREEN}


def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save(fig, name):
    fig.tight_layout(pad=1.0)
    fig.savefig(os.path.join(OUT, name + ".png"), dpi=320, bbox_inches="tight")
    fig.savefig(os.path.join(OUT, name + ".svg"), bbox_inches="tight")
    plt.close(fig); print("saved", name)


nodes = {r["编号"]: r for r in rd(os.path.join(SRC, "节点坐标与作业海拔.csv"))}
LON = {k: float(v["经度"]) for k, v in nodes.items()}
LAT = {k: float(v["纬度"]) for k, v in nodes.items()}
m = loadmat(os.path.join(ROOT, "数据", "镇龙乡及周边30米DEM.mat"))
dem = m["dem"].astype(float); dem[dem == float(m["nodata"][0, 0])] = np.nan
lat = m["latitude"][:, 0]; lon = m["longitude"][0]
extent = [lon[0], lon[-1], lat[-1], lat[0]]
ls = LightSource(azdeg=315, altdeg=45)

SCHEMES = ["时间优先(主方案)", "均衡", "能耗优先", "架次优先"]
TITLES = {"时间优先(主方案)": "时间优先主方案（24 架次 / 5903 s / 65.89 kWh）路线",
          "均衡": "均衡方案（20 架次 / 7300 s / 61.71 kWh）路线",
          "能耗优先": "能耗优先方案（18 架次 / 8238 s / 59.47 kWh）路线",
          "架次优先": "架次优先方案（18 架次 / 8172 s / 60.44 kWh）路线"}

for tag in SCHEMES:
    rows = rd(os.path.join(SRC, "方案_%s_逐架次.csv" % tag))
    fig, ax = plt.subplots(figsize=(7.6, 6.4))
    hs = ls.hillshade(np.nan_to_num(dem, nan=np.nanmin(dem)), vert_exag=1.6, dx=1, dy=1)
    ax.imshow(hs, extent=extent, cmap="gray", origin="upper", alpha=.85)
    for r in rows:
        seq = ["O01"] + r["访问服务区顺序"].split("-") + ["O01"]
        xs = [LON[n] for n in seq]; ys = [LAT[n] for n in seq]
        ax.plot(xs, ys, color=MODELS[r["机型编号"]], lw=1.15, alpha=.72)
        ax.annotate("", xy=(xs[-1], ys[-1]), xytext=(xs[-2], ys[-2]),
                    arrowprops=dict(arrowstyle="-|>", color=MODELS[r["机型编号"]], lw=1.0, alpha=.8))
    ax.scatter([LON["O01"]], [LAT["O01"]], marker="^", s=140, color="black", zorder=6, ec="white", lw=1.2)
    ax.annotate("O01", (LON["O01"], LAT["O01"]), xytext=(6, 6), textcoords="offset points", fontproperties=FONT, fontsize=9, zorder=7)
    for name in nodes:
        if name == "O01": continue
        ax.scatter([LON[name]], [LAT[name]], s=32, facecolor="white", edgecolor="#333333", zorder=5)
        ax.annotate(name, (LON[name], LAT[name]), xytext=(4, 3), textcoords="offset points", fontproperties=FONT, fontsize=6.2, zorder=7)
    handles = [Line2D([], [], color=MODELS[g], lw=2, label="%s 型" % g) for g in "ABC"]
    handles.append(Line2D([], [], marker="^", color="none", markerfacecolor="black", markersize=8, label="调度中心 O01"))
    ax.legend(handles=handles, prop=FONT, frameon=False, loc="lower right", fontsize=8)
    xs = [LON[n] for n in nodes]; ys = [LAT[n] for n in nodes]
    mx = (max(xs) - min(xs)) * .18; my = (max(ys) - min(ys)) * .18
    ax.set_xlim(min(xs) - mx, max(xs) + mx); ax.set_ylim(min(ys) - my, max(ys) + my)
    ax.set_xlabel("经度（°E）", fontproperties=FONT, fontsize=9); ax.set_ylabel("纬度（°N）", fontproperties=FONT, fontsize=9)
    ax.set_title(TITLES[tag], fontproperties=FONT, fontsize=11, pad=9); ax.tick_params(labelsize=8)
    save(fig, "result_q2_route_map_%s" % tag)

rows = rd(os.path.join(SRC, "方案对比_四个口径.csv"))
fig, ax = plt.subplots(figsize=(7.4, 4.8))
cmap = {18: GREEN, 20: BLUE, 24: RED}
for r in rows:
    x = float(r["完成时间_s"]) / 3600; y = float(r["总能耗_kWh"]); n = int(r["架次数"])
    ax.scatter(x, y, s=110, color=cmap.get(n, ORANGE), alpha=.88, ec="white", lw=1.2, zorder=3)
    ax.annotate("%s\n%d 架次 / %.2f kWh" % (r["方案"], n, y), (x, y), xytext=(8, 7), textcoords="offset points", fontproperties=FONT, fontsize=8)
ax.set_xlabel("全部任务完成时间（h）", fontproperties=FONT, fontsize=9); ax.set_ylabel("运输总能耗（kWh）", fontproperties=FONT, fontsize=9)
ax.set_title("四个口径方案：架次数、完成时间与总能耗", fontproperties=FONT, fontsize=11, pad=9)
ax.grid(color="#dddddd", linewidth=.6); ax.tick_params(labelsize=8); save(fig, "result_q2_scheme_tradeoff")

s = rd(os.path.join(SRC, "方案_时间优先(主方案)_逐架次.csv"))
uavs = ["U%02d" % i for i in range(1, 9)]
bats = ["%s-B%d" % (g, i) for g, c in (("A", 6), ("B", 4), ("C", 4)) for i in range(1, c + 1)]
fig, ax = plt.subplots(figsize=(8.4, 4.4))
for r in s:
    y = uavs.index(r["无人机编号"]); a = float(r["开始时刻_s"]) / 3600; b = float(r["返回O01时刻_s"]) / 3600
    ax.barh(y, b - a, left=a, height=.58, color=MODELS[r["机型编号"]], ec="white")
    ax.text((a + b) / 2, y, r["架次编号"], ha="center", va="center", color="white", fontsize=7)
ax.set_yticks(range(8), uavs); ax.invert_yaxis()
ax.set_xlabel("任务开始后的时间（h）", fontproperties=FONT, fontsize=9); ax.set_ylabel("实体无人机", fontproperties=FONT, fontsize=9)
ax.set_title("主方案（时间优先，逐机型重排后）：8 架无人机 24 架次", fontproperties=FONT, fontsize=11, pad=9)
ax.grid(axis="x", color="#dddddd", linewidth=.6); ax.tick_params(labelsize=8); save(fig, "result_q2_uav_gantt")
fig, ax = plt.subplots(figsize=(8.4, 6.0))
for r in s:
    y = bats.index(r["电池编号"]); a = float(r["开始时刻_s"]) / 3600; b = float(r["返回O01时刻_s"]) / 3600; c = float(r["电池充满时刻_s"]) / 3600
    ax.barh(y, b - a, left=a, height=.58, color=MODELS[r["机型编号"]], ec="white")
    ax.barh(y, c - b, left=b, height=.58, color="#bbbbbb", ec="white", hatch="///")
ax.set_yticks(range(len(bats)), bats); ax.invert_yaxis()
ax.set_xlabel("任务开始后的时间（h）", fontproperties=FONT, fontsize=9); ax.set_ylabel("同型共享电池", fontproperties=FONT, fontsize=9)
ax.set_title("主方案（时间优先，逐机型重排后）：电池占用与充电", fontproperties=FONT, fontsize=11, pad=9)
ax.grid(axis="x", color="#dddddd", linewidth=.6); ax.tick_params(labelsize=8); save(fig, "result_q2_battery_gantt")
d = [r for r in rd(os.path.join(SRC, "方案_时间优先(主方案)_逐箱交付.csv")) if r["硬截止时间_s"]]
d.sort(key=lambda r: float(r["硬截止时间_s"]) - float(r["交付完成时刻_s"]))
vals = [float(r["硬截止时间_s"]) - float(r["交付完成时刻_s"]) for r in d]
fig, ax = plt.subplots(figsize=(7.2, 6.6))
ax.hlines(range(len(d)), 0, vals, color="#cccccc", lw=.9)
ax.scatter(vals, range(len(d)), c=[RED if v < 600 else BLUE for v in vals], s=22, zorder=3)
ax.set_yticks(range(len(d)), [r["货箱编号"] for r in d], fontsize=6.5); ax.invert_yaxis()
ax.axvline(0, color=RED, lw=1.2); ax.grid(axis="x", color="#dddddd", linewidth=.6)
ax.set_xlabel("硬截止 − 实际交付（s）", fontproperties=FONT, fontsize=9)
ax.set_title("主方案 31 个硬时限货箱的送达余量（最小 %.1f s）" % min(vals), fontproperties=FONT, fontsize=11, pad=9)
ax.tick_params(labelsize=8); save(fig, "result_q2_hard_margin")
print("all figures regenerated")

