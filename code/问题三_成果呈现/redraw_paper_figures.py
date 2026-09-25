"""仅使用问题三已发布主方案重绘中文论文图。

运行：python 问题三_成果呈现/redraw_paper_figures.py
输出：figures/问题三_论文重绘/*.png|*.svg|*_grayscale.png
"""
from __future__ import annotations

import csv
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "问题三_参考口径"
OUT = ROOT / "figures" / "问题三_论文重绘"
sys.path.insert(0, str(Path.home() / ".codex/skills/math-modeling/tools/figure/scripts"))
from export_figure import export_figure  # noqa: E402

BLUE, ORANGE, GREEN, VERMILION = "#0072B2", "#E69F00", "#009E73", "#D55E00"
MODEL_COLOR = {"A": BLUE, "B": ORANGE, "C": GREEN}
MODEL_STYLE = {"A": "-", "B": "--", "C": ":"}
SITE_COLOR = {"西": VERMILION, "东": BLUE, "北": GREEN}
SITE_MARK = {"西": "s", "东": "D", "北": "P"}
plt.rcParams.update({
    "font.family": "Microsoft YaHei", "font.size": 9, "axes.unicode_minus": False,
    "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
    "savefig.facecolor": "white",
})


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def hour(value: str | float) -> float:
    return float(value) / 3600


def save(fig, name: str, size: tuple[float, float]) -> None:
    fig.set_size_inches(*size)
    fig.tight_layout(pad=1.0)
    export_figure(fig, str(OUT / name), formats=("svg", "png"),
                  size_inches=size, dpi=320, grayscale_preview=True)
    svg_path = OUT / f"{name}.svg"
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
                        encoding="utf-8")
    qa_dir = OUT / "_qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(OUT / f"{name}_grayscale.png"), str(qa_dir / f"{name}_grayscale.png"))
    plt.close(fig)


nodes = {r["编号"]: r for r in read(ROOT / "results" / "航路节点坐标与作业高度.csv")}
LON = {k: float(v["经度（度）"]) for k, v in nodes.items()}
LAT = {k: float(v["纬度（度）"]) for k, v in nodes.items()}
transport = read(SRC / "主方案_运输架次.csv")
relays = read(SRC / "主方案_中继架次.csv")
communication = read(SRC / "主方案_通信保障.csv")
boxes = read(SRC / "主方案_逐箱交付.csv")
assert (len(transport), len(relays), len(communication), len(boxes)) == (22, 4, 250, 80)

mat = loadmat(ROOT / "数据" / "镇龙乡及周边30米DEM.mat")
dem = mat["dem"].astype(float)
dem[dem == float(mat["nodata"][0, 0])] = np.nan
lon = mat["longitude"][0]
lat = mat["latitude"][:, 0]
extent = (lon[0], lon[-1], lat[-1], lat[0])
shade = LightSource(azdeg=315, altdeg=45).hillshade(
    np.nan_to_num(dem, nan=np.nanmin(dem)), vert_exag=1.6, dx=1, dy=1)


def map_base(ax) -> None:
    ax.imshow(shade, extent=extent, cmap="gray", origin="upper", alpha=.65, zorder=0)
    for name in nodes:
        if name == "O01":
            continue
        ax.scatter(LON[name], LAT[name], s=26, facecolors="white",
                   edgecolors="#30343B", linewidths=.8, zorder=6)
        ax.annotate(name, (LON[name], LAT[name]), xytext=(3, 2),
                    textcoords="offset points", fontsize=6.5, zorder=7)
    ax.scatter(LON["O01"], LAT["O01"], marker="^", s=105,
               color="#20242A", edgecolor="white", linewidth=1, zorder=8)
    ax.annotate("O01 / G01", (LON["O01"], LAT["O01"]), xytext=(5, 5),
                textcoords="offset points", fontsize=8, zorder=9)
    xs, ys = list(LON.values()), list(LAT.values())
    ax.set_xlim(min(xs) - .13 * np.ptp(xs), max(xs) + .13 * np.ptp(xs))
    ax.set_ylim(min(ys) - .13 * np.ptp(ys), max(ys) + .13 * np.ptp(ys))
    ax.set_xlabel("经度（°E）")
    ax.set_ylabel("纬度（°N）")
    ax.tick_params(labelsize=8)


def relay_map() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.5))
    map_base(ax)
    for r in transport:
        seq = ["O01", *r["访问服务区顺序"].split("-"), "O01"]
        ax.plot([LON[n] for n in seq], [LAT[n] for n in seq],
                color="#7E8993", alpha=.27, lw=.85, zorder=2)
    seen = set()
    for r in relays:
        key = (float(r["悬停经度"]), float(r["悬停纬度"]))
        if key in seen:
            continue
        seen.add(key)
        site = min(SITE_COLOR, key=lambda s: abs(key[0] - {"西": 109.2036, "东": 109.2728, "北": 109.2417}[s]))
        ax.plot([LON["O01"], key[0]], [LAT["O01"], key[1]],
                color="#4B5563", ls="--", lw=1.4, zorder=3)
        ax.scatter(*key, marker=SITE_MARK[site], s=130,
                   color=SITE_COLOR[site], edgecolor="white", lw=1.2, zorder=9)
        ax.annotate(f"{site}侧中继点", key, xytext=(7, 6),
                    textcoords="offset points", fontsize=8, zorder=10)
    ax.legend(handles=[Line2D([], [], color="#7E8993", lw=1.5, label="运输航线"),
                       Line2D([], [], color="#4B5563", ls="--", lw=1.5, label="网关—中继回传链路")],
              frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(.5, 1.01), fontsize=8)
    ax.set_title("问题三：3 个中继悬停点的位置", fontsize=11, pad=28)
    save(fig, "result_q3_relay_sites", (7.2, 5.5))


def transport_map() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.5))
    map_base(ax)
    for r in transport:
        seq = ["O01", *r["访问服务区顺序"].split("-"), "O01"]
        ax.plot([LON[n] for n in seq], [LAT[n] for n in seq],
                color=MODEL_COLOR[r["机型编号"]], ls=MODEL_STYLE[r["机型编号"]],
                alpha=.72, lw=1.45, zorder=3)
    for r in relays:
        ax.scatter(float(r["悬停经度"]), float(r["悬停纬度"]), marker="D",
                   s=65, color=VERMILION, edgecolor="white", lw=.8, zorder=9)
    handles = [Line2D([], [], color=MODEL_COLOR[k], ls=MODEL_STYLE[k],
                      lw=2, label=f"{k} 型运输机") for k in "ABC"]
    handles.append(Line2D([], [], marker="D", color="none", markerfacecolor=VERMILION,
                          markersize=7, label="中继点"))
    ax.legend(handles=handles, frameon=False, ncol=4, loc="lower center",
              bbox_to_anchor=(.5, 1.01), fontsize=7.8)
    ax.set_title("问题三：22 架次访问顺序（站点连线示意）与中继点", fontsize=10.5, pad=28)
    save(fig, "result_q3_transport_routes", (7.2, 5.5))


def area_delivery() -> None:
    by_area: dict[str, list[float]] = defaultdict(list)
    for r in boxes:
        by_area[r["服务区编号"]].append(hour(r["交付完成时刻_s"]))
    areas = sorted(by_area)
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    for y, area in enumerate(areas):
        times = sorted(by_area[area])
        if len(set(times)) > 1:
            ax.plot([times[0], times[-1]], [y, y], color="#B4BCC5", lw=2, zorder=1)
        ax.scatter(times, [y]*len(times), s=19, color=ORANGE, edgecolor="white",
                   linewidth=.4, alpha=.85, zorder=3)
        ax.text(2.36, y, f"{len(times)} 箱", va="center", fontsize=7)
    ax.set_yticks(range(len(areas)), areas, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 2.55)
    ax.set_xlabel("任务开始后的时间（h）")
    ax.set_ylabel("服务区")
    ax.set_title("问题三：80 箱物资在 15 个服务区的实际交付时刻", fontsize=10.5)
    ax.grid(axis="x", color="#DCE1E6", lw=.6)
    ax.set_axisbelow(True)
    ax.text(.01, -.12, "同刻交付的箱子圆点重合；灰线仅连接最早与最晚交付时刻。",
            transform=ax.transAxes, fontsize=7.5, color="#59636E")
    save(fig, "result_q3_area_schedule", (7.2, 5.6))


def communication_timeline() -> None:
    ids = [r["架次编号"] for r in transport]
    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    color = {"直连": BLUE, "中继": ORANGE}
    for r in communication:
        y = ids.index(r["运输架次编号"])
        a, b = hour(r["开始时刻_s"]), hour(r["结束时刻_s"])
        ax.barh(y, b-a, left=a, height=.73, color=color[r["保障方式"]],
                edgecolor="none", zorder=3)
    ax.set_yticks(range(len(ids)), ids, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, 2.55)
    ax.set_xlabel("任务开始后的时间（h）")
    ax.set_ylabel("运输架次")
    ax.set_title("问题三：22 条运输架次需通信时段的保障方式", fontsize=10.5)
    ax.grid(axis="x", color="#DCE1E6", lw=.6)
    ax.set_axisbelow(True)
    ax.legend(handles=[Line2D([], [], color=color[k], lw=5, label=k) for k in ("直连", "中继")],
              frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(.5, -.09), fontsize=8)
    save(fig, "result_q3_communication_timeline", (7.2, 6.2))


def relay_windows() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    for y, r in enumerate(relays):
        a, b = hour(r["建链完成时刻_s"]), hour(r["服务结束时刻_s"])
        site = min(SITE_COLOR, key=lambda s: abs(float(r["悬停经度"]) -
                   {"西": 109.2036, "东": 109.2728, "北": 109.2417}[s]))
        ax.barh(y, b-a, left=a, height=.54, color=SITE_COLOR[site], zorder=3)
        ax.text((a+b)/2, y, f"{(b-a)*60:.0f} min", color="white", ha="center",
                va="center", fontsize=8, fontweight="bold")
    ax.set_yticks(range(4), [f'{r["中继架次编号"]} · {r["中继无人机编号"]}' for r in relays])
    ax.invert_yaxis()
    ax.set_xlim(0, 2.65)
    ax.set_xlabel("任务开始后的时间（h）")
    ax.set_ylabel("中继架次")
    ax.set_title("问题三：4 条中继架次的有效服务窗口", fontsize=11)
    ax.grid(axis="x", color="#DCE1E6", lw=.6)
    ax.set_axisbelow(True)
    save(fig, "result_q3_relay_windows", (7.2, 3.5))


if __name__ == "__main__":
    relay_map()
    transport_map()
    area_delivery()
    communication_timeline()
    relay_windows()
