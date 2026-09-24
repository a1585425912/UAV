"""第三问成果图：中继UAV位置图 + 运输路线图（DEM 山体阴影底图）。"""
import csv, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from scipy.io import loadmat
ROOT = r"D:\git\math_modeling\UAV"
SRC = os.path.join(ROOT, "results", "问题三_参考口径")
PKG = os.path.join(ROOT, "results", "问题三_成果呈现")
OUT = os.path.join(ROOT, "figures", "问题三_成果呈现"); os.makedirs(OUT, exist_ok=True)
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
plt.rcParams["font.family"] = FONT.get_name(); plt.rcParams["axes.unicode_minus"] = False; plt.rcParams["svg.fonttype"] = "none"
BLUE, ORANGE, GREEN, RED, PURPLE, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#6B7280"
MODELS = {"A": BLUE, "B": ORANGE, "C": GREEN}
def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
def save(fig, name):
    fig.tight_layout(pad=1.0)
    fig.savefig(os.path.join(OUT, name + ".png"), dpi=320, bbox_inches="tight")
    fig.savefig(os.path.join(OUT, name + ".svg"), bbox_inches="tight"); plt.close(fig); print("saved", name)
nodes = {r["编号"]: r for r in rd(os.path.join(ROOT, "results", "航路节点坐标与作业高度.csv"))}
LON = {k: float(v["经度（度）"]) for k, v in nodes.items()}; LAT = {k: float(v["纬度（度）"]) for k, v in nodes.items()}
transport = rd(os.path.join(SRC, "主方案_运输架次.csv"))
relays = rd(os.path.join(SRC, "主方案_中继架次.csv"))
cover = {r["中继架次"]: r for r in rd(os.path.join(PKG, "中继覆盖关系.csv"))}
m = loadmat(os.path.join(ROOT, "数据", "镇龙乡及周边30米DEM.mat"))
dem = m["dem"].astype(float); dem[dem == float(m["nodata"][0, 0])] = np.nan
lat = m["latitude"][:, 0]; lon = m["longitude"][0]; extent = [lon[0], lon[-1], lat[-1], lat[0]]
ls = LightSource(azdeg=315, altdeg=45)
def terrain(ax):
    ax.imshow(ls.hillshade(np.nan_to_num(dem, nan=np.nanmin(dem)), vert_exag=1.6, dx=1, dy=1),
              extent=extent, cmap="gray", origin="upper", alpha=.85)
def bounds(ax):
    xs = [LON[n] for n in nodes]; ys = [LAT[n] for n in nodes]
    mx = (max(xs)-min(xs))*.14; my = (max(ys)-min(ys))*.14
    ax.set_xlim(min(xs)-mx, max(xs)+mx); ax.set_ylim(min(ys)-my, max(ys)+my)
    ax.set_xlabel("经度（°E）", fontproperties=FONT, fontsize=9); ax.set_ylabel("纬度（°N）", fontproperties=FONT, fontsize=9)

# 图1：中继 UAV 位置
fig, ax = plt.subplots(figsize=(7.8, 6.6)); terrain(ax)
for r in transport:
    seq = ["O01"] + r["访问服务区顺序"].split("-") + ["O01"]
    ax.plot([LON[n] for n in seq], [LAT[n] for n in seq], color="#9aa5b1", lw=.7, alpha=.45, zorder=2)
for name in nodes:
    ax.scatter([LON[name]], [LAT[name]], s=26, facecolor="white", edgecolor="#333333", zorder=4)
    if name != "O01": ax.annotate(name, (LON[name], LAT[name]), xytext=(4, 3), textcoords="offset points", fontproperties=FONT, fontsize=6.0, zorder=6)
ax.scatter([LON["O01"]], [LAT["O01"]], marker="^", s=150, color="black", zorder=7, ec="white", lw=1.2)
ax.annotate("O01 / G01 网关", (LON["O01"], LAT["O01"]), xytext=(8, -12), textcoords="offset points", fontproperties=FONT, fontsize=8.5, zorder=7)
SITE_COLOR = {"西": RED, "东": BLUE, "北": GREEN}
SITE_MARK = {"西": "s", "东": "D", "北": "P"}
seen = set()
for r in relays:
    site = cover[r["中继架次编号"]]["点位"]; lonr = float(r["悬停经度"]); latr = float(r["悬停纬度"])
    ax.plot([LON["O01"], lonr], [LAT["O01"], latr], color=SITE_COLOR[site], lw=1.3, ls="--", alpha=.85, zorder=3)
    if site not in seen:
        ax.scatter([lonr], [latr], marker=SITE_MARK[site], s=170, color=SITE_COLOR[site], ec="white", lw=1.4, zorder=8)
        ax.annotate("%s %s\n%.0f m" % (site, r["中继架次编号"], float(r["悬停海拔_m"])), (lonr, latr),
                    xytext=(9, 6), textcoords="offset points", fontproperties=FONT, fontsize=8, zorder=9)
        seen.add(site)
    else:
        ax.scatter([lonr], [latr], marker=SITE_MARK[site], s=90, facecolor="none", edgecolor=SITE_COLOR[site], lw=1.2, zorder=8)
        ax.annotate(r["中继架次编号"], (lonr, latr), xytext=(9, -12), textcoords="offset points", fontproperties=FONT, fontsize=7.5, color=SITE_COLOR[site], zorder=9)
handles = [Line2D([], [], marker="^", color="none", markerfacecolor="black", markersize=9, label="O01 / G01 网关"),
           Line2D([], [], color=RED, ls="--", lw=1.3, label="回传链路（网关→中继）"),
           Line2D([], [], color="#9aa5b1", lw=.9, label="运输航线（22 架次）"),
           Line2D([], [], marker="s", color="none", markerfacecolor=RED, markersize=8, label="西点位（RS01/RS04）"),
           Line2D([], [], marker="D", color="none", markerfacecolor=BLUE, markersize=8, label="东点位（RS02）"),
           Line2D([], [], marker="P", color="none", markerfacecolor=GREEN, markersize=8, label="北点位（RS03）")]
ax.legend(handles=handles, prop=FONT, frameon=False, loc="lower right", fontsize=7.5)
ax.set_title("第三问：中继 UAV 悬停点位置（3 个静态点位 / 4 条中继架次）", fontproperties=FONT, fontsize=11, pad=9)
ax.tick_params(labelsize=8); bounds(ax); save(fig, "result_q3_relay_sites")

# 图2：运输路线图
fig, ax = plt.subplots(figsize=(7.8, 6.6)); terrain(ax)
for r in transport:
    seq = ["O01"] + r["访问服务区顺序"].split("-") + ["O01"]
    xs = [LON[n] for n in seq]; ys = [LAT[n] for n in seq]
    ax.plot(xs, ys, color=MODELS[r["机型编号"]], lw=1.2, alpha=.72, zorder=3)
    ax.annotate("", xy=(xs[-1], ys[-1]), xytext=(xs[-2], ys[-2]), arrowprops=dict(arrowstyle="-|>", color=MODELS[r["机型编号"]], lw=1.0, alpha=.85), zorder=3)
for name in nodes:
    ax.scatter([LON[name]], [LAT[name]], s=28, facecolor="white", edgecolor="#333333", zorder=5)
    if name != "O01": ax.annotate(name, (LON[name], LAT[name]), xytext=(4, 3), textcoords="offset points", fontproperties=FONT, fontsize=6.2, zorder=7)
ax.scatter([LON["O01"]], [LAT["O01"]], marker="^", s=150, color="black", zorder=8, ec="white", lw=1.2)
for r in relays:
    site = cover[r["中继架次编号"]]["点位"]
    ax.scatter([float(r["悬停经度"])], [float(r["悬停纬度"])], marker=SITE_MARK[site], s=130, color=SITE_COLOR[site], ec="white", lw=1.3, zorder=7)
handles = [Line2D([], [], color=MODELS[g], lw=2, label="%s 型运输机" % g) for g in "ABC"]
handles += [Line2D([], [], marker="^", color="none", markerfacecolor="black", markersize=9, label="O01 / G01"),
            Line2D([], [], marker="s", color="none", markerfacecolor=RED, markersize=8, label="西中继点"),
            Line2D([], [], marker="D", color="none", markerfacecolor=BLUE, markersize=8, label="东中继点"),
            Line2D([], [], marker="P", color="none", markerfacecolor=GREEN, markersize=8, label="北中继点")]
ax.legend(handles=handles, prop=FONT, frameon=False, loc="lower right", fontsize=7.5)
ax.set_title("第三问：运输路线（22 架次）与中继点位", fontproperties=FONT, fontsize=11, pad=9)
ax.tick_params(labelsize=8); bounds(ax); save(fig, "result_q3_transport_routes")



