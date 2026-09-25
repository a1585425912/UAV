# -*- coding: utf-8 -*-
"""以 O01 为水平原点，绘制调度中心与 15 个服务区周边的三维地形图，并自动优选观察视角。

方法
----
1. 只读原始 30 m DEM（``数据/镇龙乡及周边30米DEM.mat``）与
   ``results/航路节点坐标与作业高度.csv``，截取节点包围盒外扩约 2 km 的区域；
2. 用 WGS84 地心坐标在 O01 水平切平面上投影，得到东向 x、北向 y（km）
   与地面海拔 z（m）；
3. 三维图采用**正交投影**。设 mplot3d 的 ``elev``、``azim``、纵向放大倍数 EXAG，
   则数据空间（x,y 为 km、z 为 m）的视线方向为
   ``d ∝ (cosθ·cosA, cosθ·sinA, sinθ)``，其中 ``tanθ = tan(elev)/EXAG``，
   θ 才是真实仰角。沿 d 对地形做射线步进，即可算出每个节点地面锚点的最小视线余量；
4. 选角：在「被遮挡的服务区不超过 ``MAX_OCCLUDED`` 个」的前提下取**最斜**（elev 最小）
   的视角，同一 elev 内先取最小视线余量最大者、再取节点屏幕间距最大者；
   遮挡只用于选角，成图不再单独标注被遮挡的节点；
5. 抗遮挡绘制：曲面用山体阴影着色；节点标记杆、地面锚点与标记点用
   ``proj3d.proj_transform`` 投影到图面后以二维 artist 叠加绘制，不会被三维曲面的
   绘制顺序遮住；16 个节点一律同款实线标记杆 + 实心锚点。

运行：``python 绘制三维地形.py``
输出：``figures/地形与服务区分布/raw_dem_terrain_3d.{png,svg}``（主图）、
      ``figures/地形与服务区分布/raw_dem_terrain_plan.{png,svg}``（俯视对照）、
      ``figures/地形与服务区分布/视图角度筛选.csv``（视角筛选记录）、
      ``figures/地形与服务区分布/视线余量.csv``（逐节点遮挡余量）。
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LightSource, LinearSegmentedColormap, Normalize
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d import proj3d
from scipy.io import loadmat
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parent.parent
NODE_CSV = ROOT / "results" / "航路节点坐标与作业高度.csv"
OUT_DIR = ROOT / "figures" / "地形与服务区分布"

SKILL_SCRIPTS = Path(r"C:\Users\mika\.codex\skills\math-modeling\tools\figure\scripts")
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure  # noqa: E402
from setup_style import setup_style  # noqa: E402
from visual_qa import audit_layout, print_report  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)

EXAGGERATION = 3.0            # 纵向放大倍数（影响盒体高矮与真实仰角）
MARGIN_LON_DEG = 0.020        # 截取范围外扩（约 2.0 km）
MARGIN_LAT_DEG = 0.018        # 截取范围外扩（约 2.0 km）
SURFACE_MAX_COLS = 280        # 曲面几何仍取 DEM 高程，较细网格减少色块感
SURFACE_MAX_ROWS = 220
RAY_STEP_KM = 0.030           # 视线射线步长（≈ DEM 分辨率）
VIS_MARGIN_M = 2.0            # 判定「可见」时的最小视线余量（m）
MAX_OCCLUDED = 2              # 选角时允许被地形遮挡的服务区个数上限（成图不做标注）
ELEV_SEARCH = (26.0, 40.0)    # mplot3d elev 搜索范围：越小越斜、越不俯视
ELEV_STEP = 1.0
ELEV_PASS_RATIO = 0.08        # 选定 elev 至少有 8% 的方位角满足遮挡上限
AZIM_STEP = 3.0

# mplot3d 会把三维坐标区强制成正方形（Axes3D.apply_aspect），所以 rect 取物理正方形，
# 再用 BOX_ZOOM 微调整体大小。
FIG_SIZE = (8.8, 6.6)
AX3D_RECT = (0.055, 0.115, 0.600, 0.800)
BOX_ZOOM = 1.30
INSET_RECT = (0.670, 0.505, 0.275, 0.315)
CBAR_RECT = (0.752, 0.150, 0.020, 0.270)

TERRAIN_CMAP = LinearSegmentedColormap.from_list(
    "land_elevation",
    [(0.00, "#3D7775"), (0.20, "#75A398"), (0.40, "#B0C3AA"),
     (0.60, "#D4C8A8"), (0.80, "#BDA88F"), (1.00, "#EEE9E0")],
)
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
LABEL_FONTSIZE = 6.6
LABEL_CANDIDATES = (
    (6, 4, "left", "bottom"), (6, -4, "left", "top"),
    (-6, 4, "right", "bottom"), (-6, -4, "right", "top"),
    (0, 8, "center", "bottom"), (0, -8, "center", "top"),
    (9, 0, "left", "center"), (-9, 0, "right", "center"),
    (11, 11, "left", "bottom"), (-11, 11, "right", "bottom"),
    (11, -11, "left", "top"), (-11, -11, "right", "top"),
)


# ---------------------------------------------------------------------------
# 坐标与数据
# ---------------------------------------------------------------------------

def local_xy(lon_deg, lat_deg, lon0_deg, lat0_deg):
    """WGS84 地心坐标在 O01 水平切平面的东、北向投影，单位 km。"""
    lon, lat = np.radians(lon_deg), np.radians(lat_deg)
    lon0, lat0 = math.radians(lon0_deg), math.radians(lat0_deg)
    n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
    x, y = n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon)
    z = n * (1 - WGS84_E2) * np.sin(lat)
    n0 = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat0) ** 2)
    x0 = n0 * math.cos(lat0) * math.cos(lon0)
    y0 = n0 * math.cos(lat0) * math.sin(lon0)
    z0 = n0 * (1 - WGS84_E2) * math.sin(lat0)
    dx, dy, dz = x - x0, y - y0, z - z0
    east = -math.sin(lon0) * dx + math.cos(lon0) * dy
    north = (-math.sin(lat0) * math.cos(lon0) * dx
             - math.sin(lat0) * math.sin(lon0) * dy + math.cos(lat0) * dz)
    return east / 1000.0, north / 1000.0


def load_nodes(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.DictReader(handle))
    assert len(raw) == 16 and raw[0]["编号"] == "O01", "节点表应为 O01 + 15 个服务区"
    nodes = []
    for row in raw:
        nodes.append({
            "name": row["编号"],
            "lon": float(row["经度（度）"]),
            "lat": float(row["纬度（度）"]),
            "x": float(row["东向x（m）"]) / 1000.0,
            "y": float(row["北向y（m）"]) / 1000.0,
            "ground": float(row["DEM地面海拔（m）"]),
            "work": float(row["作业海拔（m）"]),
        })
    return nodes


class Scene:
    """节点包围盒内的 DEM 子区（行序自北向南，与原始栅格一致）。"""

    def __init__(self, nodes: list[dict]):
        mat = loadmat(next((ROOT / "数据").rglob("*DEM.mat")))
        assert int(mat["epsg_code"][0, 0]) == 4326
        dem = mat["dem"].astype(float)
        self.nodata = float(mat["nodata"][0, 0])
        longitudes, latitudes = mat["longitude"][0], mat["latitude"][:, 0]
        lon0, lat0 = nodes[0]["lon"], nodes[0]["lat"]
        node_lon = np.array([n["lon"] for n in nodes])
        node_lat = np.array([n["lat"] for n in nodes])
        cols = np.flatnonzero((longitudes >= node_lon.min() - MARGIN_LON_DEG)
                              & (longitudes <= node_lon.max() + MARGIN_LON_DEG))
        rows = np.flatnonzero((latitudes >= node_lat.min() - MARGIN_LAT_DEG)
                              & (latitudes <= node_lat.max() + MARGIN_LAT_DEG))
        self.crop = dem[np.ix_(rows, cols)]
        assert np.isfinite(self.crop).all() and (self.crop != self.nodata).all(), "DEM 子区含无效像元"
        lon_grid, lat_grid = np.meshgrid(longitudes[cols], latitudes[rows])
        self.gx, self.gy = local_xy(lon_grid, lat_grid, lon0, lat0)
        self.x_axis = self.gx[0, :]                     # 递增（东向）
        self.y_axis = self.gy[:, 0]                     # 递减（北→南）
        self.dx = float(self.x_axis[1] - self.x_axis[0])
        self.dy = float(self.y_axis[0] - self.y_axis[1])   # 行距，正值
        self.ny, self.nx = self.crop.shape
        self.z_min = float(self.crop.min())
        self.z_max = float(self.crop.max())
        self.vmin = math.floor(self.z_min / 50.0) * 50.0
        self.vmax = math.ceil(self.z_max / 50.0) * 50.0
        self.nodes = nodes
        self.node_x = np.array([n["x"] for n in nodes])
        self.node_y = np.array([n["y"] for n in nodes])
        self.node_ground = np.array([n["ground"] for n in nodes])
        self.node_work = np.array([n["work"] for n in nodes])

    # -- 采样与遮挡 ------------------------------------------------------
    def sample(self, x, y):
        """双线性采样地面海拔；子区外返回 -inf（子区外没有绘制的地形）。"""
        i = (np.asarray(x) - self.x_axis[0]) / self.dx
        j = (self.y_axis[0] - np.asarray(y)) / self.dy
        inside = (i >= 0) & (i <= self.nx - 1) & (j >= 0) & (j <= self.ny - 1)
        i0 = np.clip(np.floor(i).astype(int), 0, self.nx - 2)
        j0 = np.clip(np.floor(j).astype(int), 0, self.ny - 2)
        ti, tj = i - i0, j - j0
        z = (self.crop[j0, i0] * (1 - ti) * (1 - tj) + self.crop[j0, i0 + 1] * ti * (1 - tj)
             + self.crop[j0 + 1, i0] * (1 - ti) * tj + self.crop[j0 + 1, i0 + 1] * ti * tj)
        return np.where(inside, z, -np.inf)

    def sight_direction(self, theta_deg: float, azim_deg: float) -> np.ndarray:
        """数据空间单位视线方向（指向相机），x,y 单位 km，z 单位 km。"""
        theta, azim = math.radians(theta_deg), math.radians(azim_deg)
        return np.array([math.cos(theta) * math.cos(azim),
                         math.cos(theta) * math.sin(azim),
                         math.sin(theta)])

    def clearance(self, theta_deg: float, azim_deg: float, lift: np.ndarray | float = 0.0):
        """逐节点沿视线步进，返回视线高出地形的最小余量（m）；被遮挡时为负值。"""
        d = self.sight_direction(theta_deg, azim_deg)
        span = math.hypot(self.x_axis[-1] - self.x_axis[0], self.y_axis[0] - self.y_axis[-1])
        steps = int(span * 1.2 / RAY_STEP_KM) + 2
        t = np.arange(1, steps + 1) * RAY_STEP_KM
        px = self.node_x[:, None] + t[None, :] * d[0]
        py = self.node_y[:, None] + t[None, :] * d[1]
        line = (self.node_ground[:, None] + np.asarray(lift)
                + t[None, :] * (d[2] * 1000.0))
        margin = line - self.sample(px, py)
        margin[~np.isfinite(margin)] = np.inf      # 射线离开 DEM 子区后不再遮挡
        return margin.min(axis=1)

    def visible_mask(self, theta_deg: float, azim_deg: float, margin: float = 0.0):
        return self.clearance(theta_deg, azim_deg) > margin


def real_angle_from_elev(elev_deg: float) -> float:
    """mplot3d 的 elev → 数据空间（未放大）的真实仰角 θ：tanθ = tan(elev)/EXAG。"""
    return math.degrees(math.atan(math.tan(math.radians(elev_deg)) / EXAGGERATION))


def elev_from_real_angle(theta_deg: float) -> float:
    """真实仰角 θ → mplot3d 的 elev。"""
    return math.degrees(math.atan(math.tan(math.radians(theta_deg)) * EXAGGERATION))


# ---------------------------------------------------------------------------
# 视角筛选
# ---------------------------------------------------------------------------

def scan_views(scene: Scene):
    """扫描候选视角：返回（全部记录, elev → 满足遮挡上限的候选）。"""
    records: list[dict] = []
    candidates: dict[float, list[dict]] = {}
    azims = np.arange(-180.0, 180.0, AZIM_STEP)
    for elev in np.arange(ELEV_SEARCH[0], ELEV_SEARCH[1] + 1e-9, ELEV_STEP):
        theta = real_angle_from_elev(float(elev))
        passing: list[dict] = []
        for azim in azims:
            margin = scene.clearance(theta, azim)
            blocked = [scene.nodes[i]["name"] for i in range(16) if margin[i] <= 0.0]
            records.append({
                "mplot3d_elev（度）": round(float(elev), 2),
                "真实仰角θ（度）": round(theta, 2),
                "方位角（度）": round(float(azim), 2),
                "可见地面点数": int((margin > 0.0).sum()),
                "满足余量(≥"f"{VIS_MARGIN_M:.0f}m)的地面点数": int((margin > VIS_MARGIN_M).sum()),
                "最小视线余量（m）": round(float(margin.min()), 2),
                "被遮挡节点": "-".join(blocked) or "无",
            })
            if len(blocked) <= MAX_OCCLUDED and (margin > VIS_MARGIN_M).sum() >= 16 - MAX_OCCLUDED:
                passing.append({"elev": float(elev), "theta": theta, "azim": float(azim),
                                "min_margin_m": float(margin.min()),
                                "blocked": blocked})
        candidates[float(elev)] = passing
    return records, candidates


def screen_spacing(scene: Scene, fig, ax, elev: float, azim: float):
    """在给定视角下把节点标记点投到屏幕上，返回最小两两间距（px）与屏幕坐标。"""
    ax.view_init(elev=elev, azim=azim)
    fig.canvas.draw()
    matrix = np.asarray(ax.get_proj(), dtype=float)
    coords = []
    for index in range(16):
        x2, y2, _ = proj3d.proj_transform(scene.node_x[index], scene.node_y[index],
                                          scene.node_work[index], matrix)
        coords.append(ax.transData.transform((x2, y2)))
    coords = np.asarray(coords, dtype=float)
    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.hypot(diff[..., 0], diff[..., 1])
    np.fill_diagonal(dist, np.inf)
    return float(dist.min()), coords


def configure_3d_axes(ax, scene: Scene, elev: float, azim: float) -> None:
    ax.set_proj_type("ortho")
    x_range = float(scene.x_axis[-1] - scene.x_axis[0])
    y_range = float(scene.y_axis[0] - scene.y_axis[-1])
    z_range = scene.vmax - scene.vmin
    ax.set_box_aspect((x_range, y_range, z_range / 1000.0 * EXAGGERATION), zoom=BOX_ZOOM)
    ax.set_xlim(scene.x_axis[0], scene.x_axis[-1])
    ax.set_ylim(scene.y_axis[-1], scene.y_axis[0])
    ax.set_zlim(scene.vmin, scene.vmax)
    ax.view_init(elev=elev, azim=azim)


def choose_view(scene: Scene, candidates: dict[float, list[dict]]) -> dict:
    """取满足遮挡上限的最斜（elev 最小）视角，再在候选方位角中优选。"""
    counts = {elev: len(pool) for elev, pool in candidates.items()}
    total_azim = len(np.arange(-180.0, 180.0, AZIM_STEP))
    robust = sorted(elev for elev, count in counts.items()
                    if count >= ELEV_PASS_RATIO * total_azim)
    assert robust, "搜索范围内没有 elev 能满足遮挡上限"
    chosen_elev = robust[0]
    pool = candidates[chosen_elev]
    best_visible = max(16 - len(c["blocked"]) for c in pool)
    pool = [c for c in pool if 16 - len(c["blocked"]) == best_visible]
    fig = plt.figure(figsize=FIG_SIZE)
    ax = fig.add_axes(AX3D_RECT, projection="3d")
    configure_3d_axes(ax, scene, chosen_elev, pool[0]["azim"])
    scored = []
    for candidate in pool:
        spacing, coords = screen_spacing(scene, fig, ax, candidate["elev"], candidate["azim"])
        box = ax.bbox
        inside = ((coords[:, 0] > box.x0 + 6) & (coords[:, 0] < box.x1 - 6)
                  & (coords[:, 1] > box.y0 + 6) & (coords[:, 1] < box.y1 - 6)).all()
        if inside:
            scored.append({**candidate, "spacing_px": spacing})
    plt.close(fig)
    assert scored, "候选视角的节点均未落在坐标区内"
    scored.sort(key=lambda c: (-c["min_margin_m"], -c["spacing_px"]))
    return {**scored[0], "elev_pass_counts": counts, "elev_chosen_pass": counts[chosen_elev],
            "elev_visible": best_visible}


# ---------------------------------------------------------------------------
# 标签防重叠放置
# ---------------------------------------------------------------------------

def place_labels(ax, anchors, texts, *, fontsize, dpi, occupied, marker_px=5.0,
                 colors=None):
    """把标签放在锚点周围的候选偏移中：优先无重叠，其次重叠面积最小。"""
    renderer = ax.figure.canvas.get_renderer()
    scale = dpi / 72.0
    palette = list(colors) if colors is not None else ["#17252B"] * len(texts)
    annotations = [
        ax.annotate(text, xy=anchor, xytext=(0, 0), textcoords="offset points",
                    fontsize=fontsize, fontproperties=FONT, ha="left", va="bottom",
                    color=color, zorder=112, annotation_clip=False,
                    bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none",
                          "alpha": 0.78})
        for text, anchor, color in zip(texts, anchors, palette)
    ]
    ax.figure.canvas.draw()
    sizes = []
    for annotation in annotations:
        box = annotation.get_window_extent(renderer)
        sizes.append((box.width, box.height))
    canvas = ax.figure.bbox
    boxes = list(occupied)
    failures, clashes = [], []
    for annotation, (w, h), anchor in zip(annotations, sizes, anchors):
        point = ax.transData.transform(anchor)
        best = None
        for dx, dy, ha, va in LABEL_CANDIDATES:
            x0 = point[0] + dx * scale
            y0 = point[1] + dy * scale
            if ha == "left":
                bx0, bx1 = x0, x0 + w
            elif ha == "right":
                bx0, bx1 = x0 - w, x0
            else:
                bx0, bx1 = x0 - w / 2, x0 + w / 2
            if va == "bottom":
                by0, by1 = y0, y0 + h
            elif va == "top":
                by0, by1 = y0 - h, y0
            else:
                by0, by1 = y0 - h / 2, y0 + h / 2
            inside = (bx0 >= canvas.x0 + 2 and bx1 <= canvas.x1 - 2
                      and by0 >= canvas.y0 + 2 and by1 <= canvas.y1 - 2)
            overlap = sum(max(0.0, min(bx1, b[2]) - max(bx0, b[0]))
                          * max(0.0, min(by1, b[3]) - max(by0, b[1]))
                          for b in boxes)
            score = (0 if inside else 1, overlap)
            if best is None or score < best[0]:
                best = (score, dx, dy, ha, va, (bx0, by0, bx1, by1))
            if inside and overlap <= 0.0:
                break
        _, dx, dy, ha, va, box = best
        if box[0] < canvas.x0 or box[2] > canvas.x1 or box[1] < canvas.y0 or box[3] > canvas.y1:
            failures.append(annotation.get_text())
        if best[0][1] > 0.0:
            clashes.append(annotation.get_text())
        annotation.set_position((dx, dy))
        annotation.set_ha(ha)
        annotation.set_va(va)
        boxes.append((box[0], box[1], box[2], box[3], id(annotation)))
    return failures, clashes


def marker_boxes(anchors, ax, dpi=300, marker_px=5.0):
    occupied = []
    for anchor in anchors:
        point = ax.transData.transform(anchor)
        occupied.append((point[0] - marker_px, point[1] - marker_px,
                         point[0] + marker_px, point[1] + marker_px, None))
    return occupied


def verify_markers(fig, screen_px, colors, *, radius=10, tol=48):
    """在渲染缓冲中核验每个标记点附近确实出现了对应标记色（防标记被遮/错位）。"""
    fig.canvas.draw()
    buffer = np.asarray(fig.canvas.buffer_rgba())[..., :3].astype(int)
    height = buffer.shape[0]
    results = []
    for point, palette in zip(screen_px, colors):
        column, row = int(round(point[0])), int(round(height - 1 - point[1]))
        window = buffer[max(0, row - radius):row + radius + 1,
                        max(0, column - radius):column + radius + 1]
        counts = [int((np.abs(window - np.array(rgb)).max(axis=-1) <= tol).sum())
                  for rgb in palette]
        results.append((column, row, counts))
    return results


def audit_tick_labels(ax) -> list[str]:
    """检查三维坐标轴刻度标签两两是否重叠（mplot3d 视角下最容易「挤在一起」）。"""
    renderer = ax.figure.canvas.get_renderer()
    labels = [label for label in (*ax.get_xticklabels(), *ax.get_yticklabels(),
                                  *ax.get_zticklabels())
              if label.get_visible() and label.get_text().strip()]
    boxes = [label.get_window_extent(renderer) for label in labels]
    hits = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if (a.x0 < b.x1 - 1.0 and b.x0 < a.x1 - 1.0
                    and a.y0 < b.y1 - 1.0 and b.y0 < a.y1 - 1.0):
                hits.append(f"{labels[i].get_text()}×{labels[j].get_text()}")
    return hits


# ---------------------------------------------------------------------------
# 出图
# ---------------------------------------------------------------------------

def style_axis_labels(ax, scene: Scene) -> None:
    ax.set_xlabel("东西距离 x（km）", labelpad=14, fontproperties=FONT)
    ax.set_ylabel("南北距离 y（km）", labelpad=14, fontproperties=FONT)
    ax.set_zlabel("高程（m）", labelpad=8, fontproperties=FONT)
    ax.tick_params(labelsize=8, pad=3)
    ax.set_xticks([-8, -4, 0, 4])
    ax.set_yticks([0, 3, 6, 9])
    ax.set_zticks([100, 400, 700])
    for label in (*ax.get_xticklabels(), *ax.get_yticklabels(), *ax.get_zticklabels()):
        label.set_fontproperties(FONT)


def surface_grid(scene: Scene):
    step_cols = max(1, math.ceil(scene.nx / SURFACE_MAX_COLS))
    step_rows = max(1, math.ceil(scene.ny / SURFACE_MAX_ROWS))
    sub = (slice(None, None, step_rows), slice(None, None, step_cols))
    return scene.gx[sub], scene.gy[sub], scene.crop[sub]


def terrain_rgba(z: np.ndarray, light: LightSource, norm: Normalize,
                 dx_m: float, dy_m: float) -> np.ndarray:
    """高程决定色相；仅平滑光照法线，几何和高程数值保持原始 DEM。"""
    base = TERRAIN_CMAP(norm(z))
    normals = gaussian_filter(z, sigma=1.35, mode="nearest")
    shade = light.hillshade(normals, vert_exag=1.25, dx=dx_m, dy=dy_m)
    base[..., :3] = np.clip(base[..., :3] * (0.70 + 0.42 * shade[..., None]), 0, 1)
    base[..., 3] = 1.0
    return base


def build_3d_figure(scene: Scene, view: dict):
    fig = plt.figure(figsize=FIG_SIZE)
    ax = fig.add_axes(AX3D_RECT, projection="3d")
    configure_3d_axes(ax, scene, view["elev"], view["azim"])
    style_axis_labels(ax, scene)

    grid_x, grid_y, grid_z = surface_grid(scene)
    light = LightSource(azdeg=315, altdeg=45)
    norm = Normalize(scene.vmin, scene.vmax)
    rgba = terrain_rgba(grid_z, light, norm,
                        scene.dx * 1000.0 * max(1, math.ceil(scene.nx / SURFACE_MAX_COLS)),
                        scene.dy * 1000.0 * max(1, math.ceil(scene.ny / SURFACE_MAX_ROWS)))
    ax.plot_surface(grid_x, grid_y, grid_z, facecolors=rgba, rstride=1, cstride=1,
                    linewidth=0, antialiased=True, shade=False)

    cax = fig.add_axes(CBAR_RECT)
    colorbar = fig.colorbar(ScalarMappable(norm=norm, cmap=TERRAIN_CMAP), cax=cax)
    colorbar.set_label("高程（m）", labelpad=6, fontproperties=FONT)
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(FONT)
    colorbar.ax.tick_params(labelsize=8)

    # 遮挡判定：地面锚点余量 <= 0 即被山脊挡住。
    margins = scene.clearance(view["theta"], view["azim"])
    occluded = margins <= 0.0

    # 节点标记杆：投影到图面后用二维 artist 叠加，不会被曲面绘制顺序遮住。
    fig.canvas.draw()
    matrix = np.asarray(ax.get_proj(), dtype=float)

    def project(z_values):
        return [proj3d.proj_transform(scene.node_x[i], scene.node_y[i], z_values[i], matrix)[:2]
                for i in range(16)]

    ground_2d, work_2d = project(scene.node_ground), project(scene.node_work)
    for index in range(16):
        ax.add_artist(Line2D([ground_2d[index][0], work_2d[index][0]],
                             [ground_2d[index][1], work_2d[index][1]],
                             color="#1B2A32", linewidth=0.8, alpha=0.95,
                             transform=ax.transData, zorder=100, clip_on=False))
        ax.add_artist(Line2D([ground_2d[index][0]], [ground_2d[index][1]],
                             marker="o", markersize=2.4, markerfacecolor="#1B2A32",
                             markeredgecolor="none", linestyle="None",
                             transform=ax.transData, zorder=101, clip_on=False))
        if index == 0:
            ax.add_artist(Line2D([work_2d[index][0]], [work_2d[index][1]], marker="*",
                                 markersize=13, markerfacecolor="#D55E00",
                                 markeredgecolor="white", markeredgewidth=1.0,
                                 linestyle="None", transform=ax.transData,
                                 zorder=102, clip_on=False))
        else:
            ax.add_artist(Line2D([work_2d[index][0]], [work_2d[index][1]], marker="o",
                                 markersize=5.4, markerfacecolor="white",
                                 markeredgecolor="#B23A00", markeredgewidth=1.0,
                                 linestyle="None", transform=ax.transData,
                                 zorder=102, clip_on=False))

    legend_handles = [
        Line2D([], [], marker="o", linestyle="None", markersize=5.4,
               markerfacecolor="white", markeredgecolor="#B23A00",
               label="服务区（15 个）"),
        Line2D([], [], marker="*", linestyle="None", markersize=11,
               markerfacecolor="#D55E00", markeredgecolor="#D55E00",
               label="调度中心 O01"),
        Line2D([], [], color="#1B2A32", linewidth=0.9, label="地面锚点与标记杆"),
    ]
    fig.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(0.668, 0.975),
               frameon=False, fontsize=8.0, prop=FONT, handletextpad=0.6, labelspacing=0.5)

    # 俯视对照小图：消除透视歧义。
    inset = fig.add_axes(INSET_RECT)
    inset.imshow(terrain_rgba(scene.crop, light, norm, scene.dx * 1000.0,
                              scene.dy * 1000.0), origin="upper",
                 extent=[scene.x_axis[0], scene.x_axis[-1],
                         scene.y_axis[-1], scene.y_axis[0]])
    inset.scatter(scene.node_x[1:], scene.node_y[1:], s=13, facecolor="white",
                  edgecolor="#B23A00", linewidth=0.8, zorder=5)
    inset.scatter([scene.node_x[0]], [scene.node_y[0]], marker="*", s=95,
                  color="#D55E00", edgecolor="white", linewidth=0.8, zorder=6)
    inset.set_xlim(scene.x_axis[0], scene.x_axis[-1])
    inset.set_ylim(scene.y_axis[-1], scene.y_axis[0])
    inset.set_xticks([])
    inset.set_yticks([])
    inset.set_title("俯视位置对照（上为北）", fontproperties=FONT, fontsize=8, pad=3)
    for spine in inset.spines.values():
        spine.set_color("#8A949C")
        spine.set_linewidth(0.7)

    title = "镇龙乡任务区 DEM 三维地形与调度中心／服务区位置"
    fig.text(0.010, 0.950, title, fontsize=14.0, weight="bold", fontproperties=FONT)

    failing, clashes = place_labels(
        ax, work_2d, [node["name"] for node in scene.nodes],
        fontsize=LABEL_FONTSIZE, dpi=fig.dpi,
        occupied=marker_boxes(work_2d, ax, dpi=fig.dpi))

    # 叠加标记依赖「投影矩阵」在重绘间保持稳定，这里显式核验。
    fig.canvas.draw()
    matrix_after = np.asarray(ax.get_proj(), dtype=float)
    drift = float(np.abs(matrix_after - matrix).max())
    assert drift < 1e-9, f"重绘后正交投影矩阵发生变化（{drift:.3e}），标记杆会错位"
    screen = np.array([ax.transData.transform(tuple(work_2d[i])) for i in range(16)])
    assert ((screen[:, 0] > ax.bbox.x0) & (screen[:, 0] < ax.bbox.x1)
            & (screen[:, 1] > ax.bbox.y0) & (screen[:, 1] < ax.bbox.y1)).all(), \
        "有节点标记落在坐标区外"
    return fig, ax, {"label_failures": failing, "label_clashes": clashes,
                     "projection_drift": drift, "screen_px": screen,
                     "occluded": [scene.nodes[i]["name"] for i in range(16) if occluded[i]],
                     "margins": margins, "ground_2d": ground_2d, "work_2d": work_2d}


def build_plan_figure(scene: Scene) -> plt.Figure:
    fig = plt.figure(figsize=(7.6, 6.2))
    ax = fig.add_axes((0.085, 0.085, 0.815, 0.845))
    light = LightSource(azdeg=315, altdeg=45)
    norm = Normalize(scene.vmin, scene.vmax)
    rgba = terrain_rgba(scene.crop, light, norm, scene.dx * 1000.0, scene.dy * 1000.0)
    minor_levels = np.arange(scene.vmin, scene.vmax + 1, 50.0)
    major_levels = np.arange(math.ceil(scene.vmin / 100) * 100, scene.vmax + 1, 100.0)
    ax.contour(scene.gx, scene.gy, scene.crop, levels=minor_levels,
               colors="#263B45", linewidths=0.22, alpha=0.10, zorder=3)
    contour = ax.contour(scene.gx, scene.gy, scene.crop, levels=major_levels,
                         colors="#263B45", linewidths=0.52, alpha=0.38, zorder=4)
    ax.clabel(contour, fmt="%d", fontsize=5.5, inline=True, colors="#263B45",
              levels=major_levels[::2])
    ax.imshow(rgba, origin="upper", zorder=2,
              extent=[scene.x_axis[0], scene.x_axis[-1], scene.y_axis[-1], scene.y_axis[0]])
    ax.scatter(scene.node_x[1:], scene.node_y[1:], s=34, facecolor="white",
               edgecolor="#B23A00", linewidth=1.1, zorder=6)
    ax.scatter([scene.node_x[0]], [scene.node_y[0]], marker="*", s=190, color="#D55E00",
               edgecolor="white", linewidth=1.1, zorder=7)
    ax.set_xlim(scene.x_axis[0], scene.x_axis[-1])
    ax.set_ylim(scene.y_axis[-1], scene.y_axis[0])
    ax.set_aspect("equal")
    ax.set_xlabel("东西距离 x（km）", fontproperties=FONT)
    ax.set_ylabel("南北距离 y（km）", fontproperties=FONT)
    for label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        label.set_fontproperties(FONT)
    ax.annotate("N", xy=(0.975, 0.965), xycoords="axes fraction", ha="center", va="top",
                fontsize=11, weight="bold", fontproperties=FONT)
    ax.annotate("", xy=(0.975, 0.955), xytext=(0.975, 0.895), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color="#17252B", lw=1.0))
    ax.grid(color="#D5DBDF", linewidth=0.5, zorder=1)
    ax.set_title("镇龙乡任务区 DEM 俯视地形与服务区、调度中心位置",
                 fontproperties=FONT, fontsize=12, pad=8)
    fig.text(0.085, 0.018,
             f"30 m DEM 柔和山体阴影 + 每 100 m 主等高线（50 m 辅助线）；O01 为水平原点，+x 向东、+y 向北；"
             f"高程 {scene.z_min:.0f}~{scene.z_max:.0f} m。",
             fontsize=8.0, color="#5B6570", fontproperties=FONT)
    cax = fig.add_axes((0.915, 0.30, 0.020, 0.40))
    colorbar = fig.colorbar(ScalarMappable(norm=norm, cmap=TERRAIN_CMAP), cax=cax)
    colorbar.set_label("高程（m）", labelpad=6, fontproperties=FONT)
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(FONT)
    colorbar.ax.tick_params(labelsize=8)

    anchors = [(scene.node_x[i], scene.node_y[i]) for i in range(16)]
    texts = [f"{scene.nodes[i]['name']}  {scene.node_ground[i]:.0f} m" for i in range(16)]
    fig.canvas.draw()
    failing, clashes = place_labels(ax, anchors, texts, fontsize=LABEL_FONTSIZE, dpi=fig.dpi,
                                    occupied=marker_boxes(anchors, ax, dpi=fig.dpi,
                                                          marker_px=6.0))
    print(f"    俯视图标签：越界 {len(failing)} 个、无法避让重叠 {len(clashes)} 个 "
          f"{failing + clashes}")
    return fig


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def export_with_qa(fig, basename: Path, size_inches: tuple[float, float]) -> list[str]:
    """导出 PNG/SVG，并把灰度预览归入 _qa 子目录（与仓库既有图件约定一致）。"""
    written = export_figure(fig, basename=str(basename), formats=["svg", "png"],
                            size_inches=size_inches, dpi=300, grayscale_preview=True)
    moved = []
    for path in written:
        source = Path(path)
        if source.name.endswith("_grayscale.png"):
            target = source.parent / "_qa" / source.name
            target.parent.mkdir(exist_ok=True)
            source.replace(target)
            moved.append(str(target))
        else:
            moved.append(str(source))
    return moved


def main() -> int:
    setup_style(journal="general", lang="zh", use_sciplots=False, constrained_layout=False)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                                       "Source Han Sans SC", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False

    nodes = load_nodes(NODE_CSV)
    scene = Scene(nodes)
    print(f"DEM 子区 {scene.ny}×{scene.nx}（{scene.dx * 1000:.1f} m × {scene.dy * 1000:.1f} m）"
          f"  地面海拔 {scene.z_min:.0f}~{scene.z_max:.0f} m")
    print(f"节点范围 x {scene.node_x.min():.2f}~{scene.node_x.max():.2f} km、"
          f"y {scene.node_y.min():.2f}~{scene.node_y.max():.2f} km")

    records, candidates = scan_views(scene)
    total_azim = len(np.arange(-180.0, 180.0, AZIM_STEP))
    print(f"视角扫描 {len(records)} 个（elev {ELEV_SEARCH[0]:.0f}~{ELEV_SEARCH[1]:.0f}°"
          f" × 方位角 {total_azim} 个，纵向放大 {EXAGGERATION:.1f} 倍，"
          f"允许最多 {MAX_OCCLUDED} 个服务区被遮挡）")
    for elev in sorted(candidates):
        pool = candidates[elev]
        if not pool:
            continue
        best = max(16 - len(c["blocked"]) for c in pool)
        print(f"    elev={elev:4.0f}°（真实仰角 {real_angle_from_elev(elev):5.1f}°）："
              f"可用方位角 {len(pool):3d}/{total_azim}，最多可见 {best:2d}/16")
    view = choose_view(scene, candidates)
    print(f"选定视角：mplot3d elev={view['elev']:.0f}°、方位角 {view['azim']:.0f}°"
          f"（等效真实仰角 {view['theta']:.1f}°）：可见 {view['elev_visible']}/16，"
          f"最小视线余量 {view['min_margin_m']:.1f} m，被遮挡 {view['blocked'] or '无'}；"
          f"节点最小屏幕间距 {view['spacing_px']:.0f} px")

    print("    对照（不同真实仰角下最多可见的地面点数）：")
    for probe in (7.0, 12.0, 17.0, 22.0, 30.0):
        best = max(int(scene.visible_mask(probe, azim).sum())
                   for azim in np.arange(-180.0, 180.0, 4.0))
        print(f"        真实仰角 {probe:4.0f}°（放大 {EXAGGERATION:.1f} 倍时 elev="
              f"{elev_from_real_angle(probe):4.0f}°）：最多可见 {best:2d}/16")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "视图角度筛选.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    verdicts = {}
    fig3d, ax3d, info = build_3d_figure(scene, view)
    print(f"    三维图标签：越界 {len(info['label_failures'])} 个、无法避让重叠 "
          f"{len(info['label_clashes'])} 个 {info['label_failures'] + info['label_clashes']}")
    tick_hits = audit_tick_labels(ax3d)
    print(f"    三维刻度标签重叠 {len(tick_hits)} 对：{tick_hits}")
    palette = [[(213, 94, 0), (255, 255, 255)]] + [[(255, 255, 255), (178, 58, 0)]] * 15
    checked = verify_markers(fig3d, info["screen_px"], palette)
    weak = [scene.nodes[i]["name"] for i, (_, _, counts) in enumerate(checked)
            if min(counts) < 6]
    print(f"    像素复核：16 个标记点中着色不足 6 px 的 {len(weak)} 个 {weak}")
    assert not weak, "标记点未在预期位置渲染"
    issues = audit_layout(fig3d)
    verdicts["3d"] = print_report(issues)
    export_with_qa(fig3d, OUT_DIR / "raw_dem_terrain_3d", FIG_SIZE)
    plt.close(fig3d)

    ground_clearance = scene.clearance(view["theta"], view["azim"])
    work_lift = (scene.node_work - scene.node_ground)[:, None]
    work_clearance = scene.clearance(view["theta"], view["azim"], lift=work_lift)
    with (OUT_DIR / "视线余量.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["编号", "地面海拔（m）", "相对O01东向x（km）", "相对O01北向y（km）",
                         "地面锚点最小视线余量（m）", "标记点（作业海拔）最小视线余量（m）",
                         "地面锚点是否被遮挡"])
        for index, node in enumerate(scene.nodes):
            writer.writerow([node["name"], f"{node['ground']:.3f}", f"{node['x']:.3f}",
                             f"{node['y']:.3f}", f"{ground_clearance[index]:.1f}",
                             f"{work_clearance[index]:.1f}",
                             "是" if ground_clearance[index] <= 0 else "否"])

    fig_plan = build_plan_figure(scene)
    issues = audit_layout(fig_plan)
    verdicts["plan"] = print_report(issues)
    export_with_qa(fig_plan, OUT_DIR / "raw_dem_terrain_plan", (7.6, 6.2))
    plt.close(fig_plan)

    if "FAIL" in verdicts.values():
        print("版面自检 FAIL，需修正后重跑")
        return 1
    print("完成：", ", ".join(sorted(p.name for p in OUT_DIR.iterdir())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
