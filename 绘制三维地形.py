"""以 O01 为水平原点，把节点周边 DEM 绘制为三维地形曲面。

运行：python 绘制三维地形.py
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
from matplotlib.lines import Line2D
import numpy as np
from scipy.io import loadmat
from mpl_toolkits.mplot3d import proj3d


ROOT = Path(__file__).resolve().parent
SKILL_SCRIPTS = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure  # noqa: E402
from setup_style import setup_style  # noqa: E402
from visual_qa import audit_layout, print_report  # noqa: E402

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
VERTICAL_EXAGGERATION = 6
MARKER_LIFT_M = 120  # 仅为遮挡处的视觉定位，标记杆底端才是真实 DEM 地面海拔。


def local_xy_grid(lon_degrees: np.ndarray, lat_degrees: np.ndarray,
                  lon0_degrees: float, lat0_degrees: float) -> tuple[np.ndarray, np.ndarray]:
    """向量化 WGS84 地心坐标至 O01 东、北水平切平面投影，结果为 km。"""
    lon = np.radians(lon_degrees)
    lat = np.radians(lat_degrees)
    lon0, lat0 = math.radians(lon0_degrees), math.radians(lat0_degrees)
    n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
    x = n * np.cos(lat) * np.cos(lon)
    y = n * np.cos(lat) * np.sin(lon)
    z = n * (1 - WGS84_E2) * np.sin(lat)
    n0 = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat0) ** 2)
    x0 = n0 * math.cos(lat0) * math.cos(lon0)
    y0 = n0 * math.cos(lat0) * math.sin(lon0)
    z0 = n0 * (1 - WGS84_E2) * math.sin(lat0)
    dx, dy, dz = x - x0, y - y0, z - z0
    east = -math.sin(lon0) * dx + math.cos(lon0) * dy
    north = (-math.sin(lat0) * math.cos(lon0) * dx
             - math.sin(lat0) * math.sin(lon0) * dy + math.cos(lat0) * dz)
    return east / 1000, north / 1000


def main() -> None:
    with (ROOT / "results" / "航路节点坐标与作业高度.csv").open(
            encoding="utf-8-sig", newline="") as handle:
        nodes = list(csv.DictReader(handle))
    assert len(nodes) == 16 and nodes[0]["编号"] == "O01"
    lon0, lat0 = float(nodes[0]["经度（度）"]), float(nodes[0]["纬度（度）"])
    node_lon = np.array([float(node["经度（度）"]) for node in nodes])
    node_lat = np.array([float(node["纬度（度）"]) for node in nodes])
    mat = loadmat(next((ROOT / "数据").rglob("*DEM.mat")))
    dem = mat["dem"]
    longitudes = mat["longitude"][0]
    latitudes = mat["latitude"][:, 0]
    nodata = float(mat["nodata"][0, 0])
    assert int(mat["epsg_code"][0, 0]) == 4326

    # 与二维图相同的节点周边范围，并以最多约 170×170 个曲面网格控制文件大小。
    xlim = (float(node_lon.min() - 0.020), float(node_lon.max() + 0.020))
    ylim = (float(node_lat.min() - 0.018), float(node_lat.max() + 0.018))
    cols = np.flatnonzero((longitudes >= xlim[0]) & (longitudes <= xlim[1]))
    rows = np.flatnonzero((latitudes >= ylim[0]) & (latitudes <= ylim[1]))
    assert len(cols) > 10 and len(rows) > 10
    step = max(1, math.ceil(max(len(cols), len(rows)) / 170))
    col_ids, row_ids = cols[::step], rows[::step]
    lon_grid, lat_grid = np.meshgrid(longitudes[col_ids], latitudes[row_ids])
    east, north = local_xy_grid(lon_grid, lat_grid, lon0, lat0)
    height = dem[np.ix_(row_ids, col_ids)].astype(float)
    height[(height == nodata) | ~np.isfinite(height)] = np.nan
    assert np.isfinite(height).all()
    xmin, xmax = float(np.min(east)), float(np.max(east))
    ymin, ymax = float(np.min(north)), float(np.max(north))
    zmin = math.floor(float(np.min(height)) / 100) * 100
    zmax = math.ceil(float(np.max(height)) / 100) * 100

    cmap = LinearSegmentedColormap.from_list(
        "land_elevation", ["#16885C", "#76C979", "#E5DF79",
                           "#B59A69", "#77584A", "#F4F0E8"])
    setup_style(journal="general", lang="zh", use_sciplots=False,
                constrained_layout=False)
    fig = plt.figure(figsize=(10.6, 6.8))
    ax = fig.add_axes((0.02, 0.10, 0.76, 0.82), projection="3d")
    surface = ax.plot_surface(east, north, height, cmap=cmap, vmin=zmin, vmax=zmax,
                              rstride=1, cstride=1, linewidth=0, antialiased=False,
                              shade=False, alpha=0.98)
    node_x = np.array([float(node["东向x（m）"]) / 1000 for node in nodes])
    node_y = np.array([float(node["北向y（m）"]) / 1000 for node in nodes])
    node_z = np.array([float(node["DEM地面海拔（m）"]) for node in nodes])
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_zlim(zmin, zmax)
    ax.set_box_aspect((xmax - xmin, ymax - ymin,
                       (zmax - zmin) / 1000 * VERTICAL_EXAGGERATION), zoom=0.99)
    ax.view_init(elev=37, azim=-60)
    ax.set_xlabel("东向 x（km）", labelpad=10)
    ax.set_ylabel("北向 y（km）", labelpad=10)
    ax.set_zlabel("海拔（m）", labelpad=5)
    ax.tick_params(labelsize=8, pad=2)
    # mplot3d 会把处于表面后的 scatter 遮住。把地面点及其抬高显示标记投影到
    # 图面，再作为二维 artist 绘制在最上层；杆底仍对应真实地面位置。
    fig.canvas.draw()
    projection = ax.get_proj()
    for index, (px, py, pz) in enumerate(zip(node_x, node_y, node_z)):
        base_x, base_y, _ = proj3d.proj_transform(px, py, pz, projection)
        top_x, top_y, _ = proj3d.proj_transform(px, py, pz + MARKER_LIFT_M, projection)
        ax.add_artist(Line2D([base_x, top_x], [base_y, top_y],
                             color="#263841", linewidth=0.85,
                             transform=ax.transData, zorder=100, clip_on=False))
        ax.add_artist(Line2D([top_x], [top_y], marker="*" if index == 0 else "o",
                             markersize=10 if index == 0 else 5,
                             markerfacecolor="#D55E00" if index == 0 else "white",
                             markeredgecolor="white" if index == 0 else "#172735",
                             markeredgewidth=0.9, linestyle="None",
                             transform=ax.transData, zorder=101, clip_on=False))
        if index > 0:
            ax.annotate(nodes[index]["编号"], (top_x, top_y), xytext=(4, 3),
                        textcoords="offset points", fontsize=7.3, weight="bold",
                        color="#172735", zorder=102,
                        bbox={"boxstyle": "round,pad=0.08", "fc": "white",
                              "ec": "none", "alpha": 0.80})
    fig.legend(handles=[
        Line2D([], [], marker="o", markerfacecolor="white", markeredgecolor="#172735",
               linestyle="None", markersize=5, label="服务区"),
        Line2D([], [], marker="*", markerfacecolor="#D55E00", markeredgecolor="#D55E00",
               linestyle="None", markersize=9, label="O01 调度中心"),
    ], loc="upper right", bbox_to_anchor=(0.90, 0.90), frameon=False,
       fontsize=8, ncol=2)
    cax = fig.add_axes((0.88, 0.24, 0.025, 0.48))
    colorbar = fig.colorbar(surface, cax=cax)
    colorbar.set_label("地面海拔（m）", labelpad=7)
    fig.text(0.04, 0.95, "调度中心与服务区周边三维地形", fontsize=15, weight="bold")
    fig.text(0.04, 0.03,
             f"30 m DEM；O01 为水平原点；纵向放大 {VERTICAL_EXAGGERATION} 倍。节点标记杆底端为真实海拔，杆高仅用于定位。",
             fontsize=8.5, color="#5B6570")
    issues = audit_layout(fig)
    print_report(issues)
    if any(severity == "FAIL" for severity, _ in issues):
        raise RuntimeError(f"图表布局失败：{issues}")
    output = ROOT / "figures" / "raw_q1_dem_terrain_3d"
    export_figure(fig, basename=str(output), formats=["svg", "png"],
                  size_inches=(10.6, 6.8), dpi=300, grayscale_preview=True)
    plt.close(fig)
    print(f"曲面网格 {height.shape[0]}×{height.shape[1]}；海拔 {np.min(height):.1f}–{np.max(height):.1f} m")


if __name__ == "__main__":
    main()
