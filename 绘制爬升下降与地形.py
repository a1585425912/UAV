"""绘制去程爬升/下降高度比较图，以及 DEM 地形海拔图。

运行：python 绘制爬升下降与地形.py
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parent
SKILL_SCRIPTS = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure  # noqa: E402
from setup_style import setup_style  # noqa: E402
from visual_qa import audit_layout, print_report  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save_checked(fig: plt.Figure, basename: str, size: tuple[float, float]) -> None:
    issues = audit_layout(fig)
    print_report(issues)
    if any(severity == "FAIL" for severity, _ in issues):
        raise RuntimeError(f"图表布局失败：{issues}")
    export_figure(fig, basename=str(ROOT / "figures" / basename),
                  formats=["svg", "png"], size_inches=size, dpi=300,
                  grayscale_preview=True)
    plt.close(fig)


def draw_vertical_segments() -> None:
    """单程比较：返程沿原路飞行，爬升与下降两列对调。"""
    rows = sorted(read_csv(ROOT / "results" / "单服务区往返几何参数.csv"),
                  key=lambda row: row["服务区"])
    assert len(rows) == 15
    sites = [row["服务区"] for row in rows]
    climb = np.array([float(row["去程爬升（m）"]) for row in rows])
    descent = np.array([float(row["去程下降（m）"]) for row in rows])
    assert np.all(climb >= 0) and np.all(descent >= 0)
    assert all(math.isclose(float(row["返程爬升（m）"]), down, abs_tol=1e-7)
               and math.isclose(float(row["返程下降（m）"]), up, abs_tol=1e-7)
               for row, up, down in zip(rows, climb, descent))

    setup_style(journal="general", lang="zh", use_sciplots=False,
                constrained_layout=False)
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    fig.subplots_adjust(left=0.09, right=0.97, top=0.87, bottom=0.23)
    x = np.arange(len(sites))
    width = 0.38
    ax.bar(x - width / 2, climb, width, color="#0072B2", label="去程爬升")
    ax.bar(x + width / 2, descent, width, color="#E69F00", label="去程下降")
    ax.set_xticks(x, sites, rotation=45)
    ax.set_ylim(0, 520)
    ax.set_xlabel("服务区编号", labelpad=9)
    ax.set_ylabel("高度（m）", labelpad=8)
    ax.set_title("调度中心至各服务区的爬升与下降高度", loc="left", pad=14,
                 fontsize=14, weight="bold")
    ax.legend(loc="upper right", frameon=False, ncol=2)
    ax.grid(axis="y", color="#D9E2E8", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", length=0, pad=6)
    ax.tick_params(axis="y", length=0)
    fig.text(0.09, 0.035, "巡航海拔为航段 DEM 最高值加 50 m；返程沿原路，爬升与下降数值互换。",
             fontsize=8.5, color="#5B6570")
    save_checked(fig, "raw_q1_route_climb_descent", (10.5, 5.8))


def draw_terrain() -> None:
    nodes = read_csv(ROOT / "results" / "航路节点坐标与作业高度.csv")
    assert len(nodes) == 16 and nodes[0]["编号"] == "O01"
    lons = np.array([float(node["经度（度）"]) for node in nodes])
    lats = np.array([float(node["纬度（度）"]) for node in nodes])
    mat = loadmat(next((ROOT / "数据").rglob("*DEM.mat")))
    dem = mat["dem"]
    lat = mat["latitude"][:, 0]
    lon = mat["longitude"][0]
    nodata = float(mat["nodata"][0, 0])
    assert int(mat["epsg_code"][0, 0]) == 4326 and dem.shape == (len(lat), len(lon))
    # 用覆盖所有节点的区域展示地形，四周约留 2 km 作为上下文。
    xlim = (float(lons.min() - 0.020), float(lons.max() + 0.020))
    ylim = (float(lats.min() - 0.018), float(lats.max() + 0.018))
    col_idx = np.flatnonzero((lon >= xlim[0]) & (lon <= xlim[1]))
    row_idx = np.flatnonzero((lat >= ylim[0]) & (lat <= ylim[1]))
    assert len(col_idx) > 10 and len(row_idx) > 10
    c0, c1 = col_idx[0], col_idx[-1] + 1
    r0, r1 = row_idx[0], row_idx[-1] + 1
    region = dem[r0:r1, c0:c1].astype(float)
    region[(region == nodata) | ~np.isfinite(region)] = np.nan
    assert np.isfinite(region).any()
    dx, dy = float(lon[1] - lon[0]), float(lat[0] - lat[1])
    extent = (float(lon[c0] - dx / 2), float(lon[c1-1] + dx / 2),
              float(lat[r1-1] - dy / 2), float(lat[r0] + dy / 2))
    valid = region[np.isfinite(region)]
    zlo = math.floor(float(valid.min()) / 100) * 100
    zhi = math.ceil(float(valid.max()) / 100) * 100
    levels = np.arange(100, zhi, 100)
    elevation_cmap = LinearSegmentedColormap.from_list(
        "land_elevation",
        ["#16885C", "#76C979", "#E5DF79", "#B59A69", "#77584A", "#F4F0E8"],
    )

    setup_style(journal="general", lang="zh", use_sciplots=False,
                constrained_layout=False)
    fig, ax = plt.subplots(figsize=(9.2, 7.0))
    fig.subplots_adjust(left=0.10, right=0.84, top=0.88, bottom=0.15)
    image = ax.imshow(region, extent=extent, origin="upper", cmap=elevation_cmap,
                      vmin=zlo, vmax=zhi, interpolation="nearest")
    # 等高线作为颜色之外的冗余编码；标注只放在少数线条上，避免淹没节点。
    xx, yy = np.meshgrid(lon[c0:c1], lat[r0:r1])
    contours = ax.contour(xx, yy, region, levels=levels, colors="#2B3944",
                          linewidths=0.45, alpha=0.40)
    ax.clabel(contours, levels[::2], inline=True, fontsize=7, fmt="%d m")
    ax.scatter(lons[1:], lats[1:], s=44, facecolors="white", edgecolors="#182D3B",
               linewidths=1.2, zorder=4)
    ax.scatter(lons[0], lats[0], s=155, marker="*", color="#D55E00",
               edgecolor="white", linewidth=0.8, zorder=6)
    for node in nodes[1:]:
        ax.annotate(node["编号"], (float(node["经度（度）"]), float(node["纬度（度）"])),
                    xytext=(5, 5), textcoords="offset points", fontsize=7.4,
                    color="#172735", weight="bold", zorder=7,
                    path_effects=[])
    ax.annotate("O01 调度中心", (lons[0], lats[0]), xytext=(8, -14),
                textcoords="offset points", fontsize=9, weight="bold", color="#50210E")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect(1 / math.cos(math.radians(float(lats[0]))))
    ax.set_xlabel("经度（°E）")
    ax.set_ylabel("纬度（°N）")
    ax.set_title("调度中心与服务区周边地形海拔", loc="left", pad=12,
                 fontsize=14, weight="bold")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.045)
    colorbar.set_label("DEM 地面海拔（m）", rotation=90, labelpad=9)
    fig.text(0.10, 0.055, "底图：30 m DEM；白圈为服务区，橙色星形为 O01。颜色和等高线表示地面海拔。",
             fontsize=8.4, color="#5B6570")
    save_checked(fig, "raw_q1_dem_terrain_map", (9.2, 7.0))
    print(f"地形范围内有效 DEM：{len(valid)} 像元；海拔 {valid.min():.1f}–{valid.max():.1f} m")


if __name__ == "__main__":
    draw_vertical_segments()
    draw_terrain()
