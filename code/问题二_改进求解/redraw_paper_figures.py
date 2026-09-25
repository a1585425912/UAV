"""按问题二改进方案已发布的 CSV 重绘中文论文图。

运行：python 问题二_改进求解/redraw_paper_figures.py
输出：figures/问题二_论文重绘/*.png|*.svg|*_grayscale.png
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "问题二_改进方案"
OUT = ROOT / "figures" / "问题二_论文重绘"
sys.path.insert(0, str(Path.home() / ".codex/skills/math-modeling/tools/figure/scripts"))
from export_figure import export_figure  # noqa: E402

BLUE, ORANGE, GREEN, VERMILION = "#0072B2", "#E69F00", "#009E73", "#D55E00"
MODEL_COLOR = {"A": BLUE, "B": ORANGE, "C": GREEN}
MODEL_STYLE = {"A": "-", "B": "--", "C": ":"}
SCHEMES = ["时间优先(主方案)", "均衡", "能耗优先", "架次优先"]
plt.rcParams.update({
    "font.family": "Microsoft YaHei", "font.size": 9, "axes.unicode_minus": False,
    "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
    "savefig.facecolor": "white",
})


def read(name: str) -> list[dict[str, str]]:
    with (SRC / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


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


def hour(value: str | float) -> float:
    return float(value) / 3600


nodes = {r["编号"]: r for r in read("节点坐标与作业海拔.csv")}
LON = {k: float(v["经度"]) for k, v in nodes.items()}
LAT = {k: float(v["纬度"]) for k, v in nodes.items()}
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
    ax.annotate("O01", (LON["O01"], LAT["O01"]), xytext=(5, 5),
                textcoords="offset points", fontsize=8, zorder=9)
    xs, ys = list(LON.values()), list(LAT.values())
    ax.set_xlim(min(xs) - .13 * np.ptp(xs), max(xs) + .13 * np.ptp(xs))
    ax.set_ylim(min(ys) - .13 * np.ptp(ys), max(ys) + .13 * np.ptp(ys))
    ax.set_xlabel("经度（°E）")
    ax.set_ylabel("纬度（°N）")
    ax.tick_params(labelsize=8)


def route_maps() -> None:
    for scheme in SCHEMES:
        sorties = read(f"方案_{scheme}_逐架次.csv")
        fig, ax = plt.subplots(figsize=(7.2, 5.5))
        map_base(ax)
        for r in sorties:
            seq = ["O01", *r["访问服务区顺序"].split("-"), "O01"]
            ax.plot([LON[n] for n in seq], [LAT[n] for n in seq],
                    color=MODEL_COLOR[r["机型编号"]], ls=MODEL_STYLE[r["机型编号"]],
                    lw=1.45, alpha=.72, zorder=3)
        handles = [Line2D([], [], color=MODEL_COLOR[k], ls=MODEL_STYLE[k], lw=2, label=f"{k} 型")
                   for k in "ABC"]
        ax.legend(handles=handles, ncol=3, loc="lower center", bbox_to_anchor=(.5, 1.01),
                  frameon=False, fontsize=8)
        ax.set_title(f"{scheme}：{len(sorties)} 架次访问顺序（站点连线示意）", fontsize=10.5, pad=28)
        save(fig, f"result_q2_route_map_{scheme}", (7.2, 5.5))


def tradeoff() -> None:
    rows = read("方案对比_四个口径.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    colors = [VERMILION, BLUE, GREEN, ORANGE]
    offsets = [(-16, 10), (8, 10), (-18, -27), (8, 10)]
    for r, color, offset in zip(rows, colors, offsets):
        x, y = hour(r["完成时间_s"]), float(r["总能耗_kWh"])
        ax.scatter(x, y, s=95, color=color, edgecolor="white", linewidth=1.1, zorder=3)
        ax.annotate(f'{r["方案"]}\n{r["架次数"]} 架次', (x, y), xytext=offset,
                    textcoords="offset points", fontsize=8, ha="right" if offset[0] < 0 else "left")
    ax.set_xlim(1.45, 2.5)
    ax.set_ylim(57, 69)
    ax.set_xlabel("任务完成时间（h）")
    ax.set_ylabel("总能耗（kWh）")
    ax.set_title("问题二：四种目标偏好的时间—能耗权衡", fontsize=11)
    ax.grid(color="#DCE1E6", lw=.6)
    save(fig, "result_q2_scheme_tradeoff", (7.2, 4.5))


def gantts() -> None:
    sorties = read("方案_时间优先(主方案)_逐架次.csv")
    uavs = [f"U{i:02d}" for i in range(1, 9)]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for r in sorties:
        y = uavs.index(r["无人机编号"])
        start, end = hour(r["开始时刻_s"]), hour(r["返回O01时刻_s"])
        ax.barh(y, end-start, left=start, height=.64, color=MODEL_COLOR[r["机型编号"]],
                edgecolor="white", linewidth=.6, zorder=3)
        ax.text((start+end)/2, y, r["架次编号"], ha="center", va="center",
                color="white", fontsize=6.7, fontweight="bold", zorder=4)
    ax.set_yticks(range(8), uavs)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.75)
    ax.set_xlabel("任务开始后的时间（h）")
    ax.set_ylabel("无人机")
    ax.set_title("时间优先主方案：8 架无人机执行 24 架次", fontsize=11)
    ax.grid(axis="x", color="#DCE1E6", lw=.6)
    ax.set_axisbelow(True)
    ax.legend(handles=[Line2D([], [], color=MODEL_COLOR[k], lw=5, label=f"{k} 型") for k in "ABC"],
              ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(.5, -.18), fontsize=8)
    save(fig, "result_q2_uav_gantt", (7.2, 4.2))

    batteries = [f"{k}-B{i}" for k, count in (("A", 6), ("B", 4), ("C", 4))
                 for i in range(1, count+1)]
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    for r in sorties:
        y = batteries.index(r["电池编号"])
        start, end, charged = map(hour, (r["开始时刻_s"], r["返回O01时刻_s"], r["电池充满时刻_s"]))
        ax.barh(y, end-start, left=start, height=.58, color=MODEL_COLOR[r["机型编号"]], zorder=3)
        ax.barh(y, charged-end, left=end, height=.58, color="#A7AFB8", hatch="///", zorder=3)
    ax.set_yticks(range(len(batteries)), batteries, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("任务开始后的时间（h）")
    ax.set_ylabel("电池")
    ax.set_title("时间优先主方案：电池飞行占用与充满时刻", fontsize=11)
    ax.grid(axis="x", color="#DCE1E6", lw=.6)
    ax.set_axisbelow(True)
    handles = [Line2D([], [], color=MODEL_COLOR[k], lw=5, label=f"{k} 型飞行") for k in "ABC"]
    handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="#A7AFB8", hatch="///", label="返航后充电"))
    ax.legend(handles=handles, ncol=4, frameon=False, loc="upper center",
              bbox_to_anchor=(.5, -.11), fontsize=7.5)
    save(fig, "result_q2_battery_gantt", (7.2, 5.4))


def hard_margin() -> None:
    boxes = [r for r in read("方案_时间优先(主方案)_逐箱交付.csv") if r["硬截止时间_s"]]
    margins = [(r["货箱编号"], float(r["硬截止时间_s"])-float(r["交付完成时刻_s"])) for r in boxes]
    margins.sort(key=lambda item: item[1])
    assert len(margins) == 31 and all(value >= 0 for _, value in margins)
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    ys = np.arange(len(margins))
    vals = [value / 60 for _, value in margins]
    ax.hlines(ys, 0, vals, color="#CDD3D9", lw=1)
    tightest = min(vals)
    ax.scatter(vals, ys, c=[VERMILION if abs(v-tightest) < 1e-6 else BLUE for v in vals],
               s=25, zorder=3)
    ax.set_yticks(ys, [name for name, _ in margins], fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlabel("硬截止前的送达余量（min）")
    ax.set_title(f"主方案：31 箱硬时限物资全部按时送达（最紧 {min(vals):.1f} min）", fontsize=10.5)
    ax.grid(axis="x", color="#DCE1E6", lw=.6)
    ax.set_axisbelow(True)
    save(fig, "result_q2_hard_margin", (7.2, 6.4))


if __name__ == "__main__":
    route_maps()
    tradeoff()
    gantts()
    hard_margin()
