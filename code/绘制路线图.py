# -*- coding: utf-8 -*-
"""在镇龙乡任务区 DEM 俯视底图上绘制问题二、问题三各方案的运输路线。

底图与 ``figures/地形与服务区分布/raw_dem_terrain_plan.*`` 完全一致（直接复用
``绘制三维地形.py`` 的 ``Scene``、``terrain_rgba`` 与标注工具）：30 m DEM 柔和山体阴影
＋ 每 100 m 主等高线（50 m 辅助线），O01 为水平原点，+x 向东、+y 向北。

路线数据（只读已发布结果，不改动任何数值）：
- 问题二：``results/问题二_改进方案/方案_<口径>_逐架次.csv``（四个口径）＋
  ``方案对比_四个口径.csv`` 的架次数/完成时间/总能耗；
- 问题三：``results/问题三_参考口径/主方案_运输架次.csv``（22 架次）＋
  ``主方案_中继架次.csv``（4 条中继架次）＋ ``results/问题三_成果呈现/中继覆盖关系.csv``
  （西/东/北三个悬停点位及覆盖服务区）。

运行：``python 绘制路线图.py``
输出：``figures/问题二三_路线图/*.png``、``*.svg``，灰度预览在 ``_qa/``。
"""
from __future__ import annotations

import csv
import importlib
import math
import sys
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, Normalize
from matplotlib.lines import Line2D
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
terrain = importlib.import_module("绘制三维地形")          # 底图与标注工具的唯一来源
from visual_qa import audit_layout, print_report  # noqa: E402

Q2_DIR = ROOT / "results" / "问题二_改进方案"
Q3_DIR = ROOT / "results" / "问题三_参考口径"
Q3_PKG = ROOT / "results" / "问题三_成果呈现"
OUT_DIR = ROOT / "figures" / "问题二三_路线图"

FIG_SIZE = (7.8, 6.1)
AX_RECT = (0.075, 0.075, 0.795, 0.830)
CBAR_RECT = (0.898, 0.300, 0.020, 0.390)
ROUTE_LW = 1.55
ROUTE_ALPHA = 0.95
# 底图是浅色的绿/黄/棕地形，因此路线用「深红 / 深蓝 / 近黑」这种低明度、地形里不存在的色相，
# 保证在浅色山体阴影与等高线上都有足够对比；线型同时区分，灰度打印也不混。
MODEL_COLOR = {"A": "#C62828", "B": "#0D47A1", "C": "#212121"}
MODEL_STYLE = {"A": "-", "B": "--", "C": ":"}
# 中继点使用同一俯视四旋翼符号，以颜色和邻近文字区分三个悬停点。
SITE_COLOR = {"西": "#9B1C8B", "东": "#0077B6", "北": "#D55E00"}
Q2_SCHEMES = ["时间优先(主方案)", "均衡", "能耗优先", "架次优先"]


def drone_marker() -> MplPath:
    """俯视四旋翼：交叉机臂、四个旋翼和机身，作为可缩放矢量 marker。"""
    def polygon(points):
        return MplPath(points + [points[0]],
                       [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1)
                       + [MplPath.CLOSEPOLY])

    parts = [polygon([(-.43, -.52), (-.52, -.43), (.43, .52), (.52, .43)]),
             polygon([(-.52, .43), (-.43, .52), (.52, -.43), (.43, -.52)]),
             MplPath.circle((0, 0), .19)]
    parts.extend(MplPath.circle((x, y), .16)
                 for x in (-.48, .48) for y in (-.48, .48))
    return MplPath.make_compound_path(*parts)


DRONE_MARKER = drone_marker()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def draw_base(ax, scene, *, label_nodes=True):
    """与 raw_dem_terrain_plan 相同的底图：柔和山体阴影 + 主/辅等高线 + 节点。"""
    light = LightSource(azdeg=315, altdeg=45)
    norm = Normalize(scene.vmin, scene.vmax)
    rgba = terrain.terrain_rgba(scene.crop, light, norm,
                                scene.dx * 1000.0, scene.dy * 1000.0)
    minor = np.arange(scene.vmin, scene.vmax + 1, 50.0)
    major = np.arange(math.ceil(scene.vmin / 100) * 100, scene.vmax + 1, 100.0)
    ax.contour(scene.gx, scene.gy, scene.crop, levels=minor, colors="#263B45",
               linewidths=0.22, alpha=0.10, zorder=3)
    contour = ax.contour(scene.gx, scene.gy, scene.crop, levels=major, colors="#263B45",
                         linewidths=0.52, alpha=0.38, zorder=4)
    ax.clabel(contour, fmt="%d", fontsize=5.5, inline=True, colors="#263B45",
              levels=major[::2])
    ax.imshow(rgba, origin="upper", zorder=2,
              extent=[scene.x_axis[0], scene.x_axis[-1],
                      scene.y_axis[-1], scene.y_axis[0]])
    ax.set_xlim(scene.x_axis[0], scene.x_axis[-1])
    ax.set_ylim(scene.y_axis[-1], scene.y_axis[0])
    ax.set_aspect("equal")
    ax.set_xlabel("东西距离 x（km）", fontproperties=terrain.FONT)
    ax.set_ylabel("南北距离 y（km）", fontproperties=terrain.FONT)
    for label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        label.set_fontproperties(terrain.FONT)
    ax.grid(color="#D5DBDF", linewidth=0.5, zorder=1)
    ax.annotate("N", xy=(0.975, 0.965), xycoords="axes fraction", ha="center", va="top",
                fontsize=11, weight="bold", fontproperties=terrain.FONT)
    ax.annotate("", xy=(0.975, 0.955), xytext=(0.975, 0.895), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color="#17252B", lw=1.0))
    cax = ax.figure.add_axes(CBAR_RECT)
    colorbar = ax.figure.colorbar(terrain.ScalarMappable(norm=norm, cmap=terrain.TERRAIN_CMAP),
                                  cax=cax)
    colorbar.set_label("高程（m）", labelpad=6, fontproperties=terrain.FONT)
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(terrain.FONT)
    colorbar.ax.tick_params(labelsize=8)
    if not label_nodes:
        return
    anchors = [(scene.node_x[i], scene.node_y[i]) for i in range(16)]
    texts = [f"{scene.nodes[i]['name']}  {scene.node_ground[i]:.0f} m" for i in range(16)]
    ax.figure.canvas.draw()
    failing, clashes = terrain.place_labels(
        ax, anchors, texts, fontsize=terrain.LABEL_FONTSIZE, dpi=ax.figure.dpi,
        occupied=terrain.marker_boxes(anchors, ax, dpi=ax.figure.dpi, marker_px=6.0))
    return failing, clashes


def node_markers(ax, scene, *, visited=None):
    """服务区白点 + O01 星标（尺寸与底图一致）。"""
    ax.scatter(scene.node_x[1:], scene.node_y[1:], s=34, facecolor="white",
               edgecolor="#B23A00", linewidth=1.1, zorder=8)
    ax.scatter([scene.node_x[0]], [scene.node_y[0]], marker="*", s=200, color="#D55E00",
               edgecolor="white", linewidth=1.1, zorder=9)


def route_legs(sequences) -> set[tuple[int, int]]:
    """所有架次用到的无向航段集合（去重后用于铺浅色衬底，避免重复叠加成白带）。"""
    legs = set()
    for sequence in sequences:
        order = [0, *sequence, 0]
        for a, b in zip(order[:-1], order[1:]):
            legs.add((a, b) if a < b else (b, a))
    return legs


def draw_route_casings(ax, scene, sequences) -> int:
    """在每个去重航段下铺一层浅色衬底，让深色路线在深/浅地形上都能看清。"""
    legs = route_legs(sequences)
    for a, b in sorted(legs):
        ax.plot([scene.node_x[a], scene.node_x[b]], [scene.node_y[a], scene.node_y[b]],
                color="#FFFFFF", linewidth=ROUTE_LW + 1.5, alpha=0.55,
                solid_capstyle="round", zorder=5)
    return len(legs)


def draw_routes(ax, scene, sequences, models):
    """逐架次画航段折线（O01→服务区…→O01），机型决定颜色与线型。"""
    assert len(sequences) == len(models)
    for sequence, model in zip(sequences, models):
        order = [0, *sequence, 0]
        ax.plot([scene.node_x[i] for i in order], [scene.node_y[i] for i in order],
                color=MODEL_COLOR[model], linestyle=MODEL_STYLE[model],
                linewidth=ROUTE_LW, alpha=ROUTE_ALPHA, zorder=6,
                solid_capstyle="round")
    return len(sequences)


def model_legend():
    return [Line2D([], [], color=MODEL_COLOR[k], linestyle=MODEL_STYLE[k], linewidth=2,
                   label=f"{k} 型无人机") for k in "ABC"]


def save(fig, name: str) -> None:
    terrain.export_with_qa(fig, OUT_DIR / name, FIG_SIZE)
    plt.close(fig)
    print(f"    saved {name}")


# ---------------------------------------------------------------------------
# 问题二：四个口径的运输路线
# ---------------------------------------------------------------------------

def q2_route_map(scene, scheme: str, metrics: dict) -> None:
    sorties = read_csv(Q2_DIR / f"方案_{scheme}_逐架次.csv")
    expected = int(metrics["架次数"])
    assert len(sorties) == expected, f"{scheme}: 架次表 {len(sorties)} 条 ≠ 对比表 {expected}"
    order: list[list[int]] = []
    models: list[str] = []
    visits: dict[str, int] = {}
    index_of = {node["name"]: i for i, node in enumerate(scene.nodes)}
    for row in sorties:
        names = [n for n in row["访问服务区顺序"].split("-") if n]
        assert names and all(n in index_of for n in names), row
        order.append([index_of[n] for n in names])
        models.append(row["机型编号"])
        for name in names:
            visits[name] = visits.get(name, 0) + 1

    fig = plt.figure(figsize=FIG_SIZE)
    ax = fig.add_axes(AX_RECT)
    failing, clashes = draw_base(ax, scene)
    draw_route_casings(ax, scene, order)
    drawn = draw_routes(ax, scene, order, models)
    node_markers(ax, scene, visited=visits)

    hours = float(metrics["完成时间_s"]) / 3600.0
    title = (f"问题二 {scheme} 方案：{drawn} 架次运输路线"
             f"（完成 {hours:.2f} h，总能耗 {float(metrics['总能耗_kWh']):.2f} kWh）")
    ax.set_title(title, fontproperties=terrain.FONT, fontsize=11.5, pad=8)

    handles = model_legend()
    handles.append(Line2D([], [], marker="*", linestyle="None", markersize=11,
                          markerfacecolor="#D55E00", markeredgecolor="white",
                          label="调度中心 O01"))
    ax.legend(handles=handles, loc="upper left", frameon=True, fontsize=8,
              prop=terrain.FONT, framealpha=0.86, edgecolor="#C9D2D8")
    print(f"    问题二 {scheme}：{drawn} 架次，标签越界 {len(failing)}、"
          f"重叠 {len(clashes)}")
    issues = audit_layout(fig)
    verdict = print_report(issues)
    assert verdict != "FAIL", issues
    save(fig, f"result_q2_route_map_{scheme}")


# ---------------------------------------------------------------------------
# 问题三：主方案运输路线 + 中继悬停点
# ---------------------------------------------------------------------------

def q3_route_map(scene) -> None:
    index_of = {node["name"]: i for i, node in enumerate(scene.nodes)}
    sorties = read_csv(Q3_DIR / "主方案_运输架次.csv")
    relays = read_csv(Q3_DIR / "主方案_中继架次.csv")
    cover = read_csv(Q3_PKG / "中继覆盖关系.csv")
    assert len(sorties) == 22 and len(relays) == 4, (len(sorties), len(relays))

    order, models, visits = [], [], {}
    for row in sorties:
        names = [n for n in row["访问服务区顺序"].split("-") if n]
        assert names and all(n in index_of for n in names), row
        order.append([index_of[n] for n in names])
        models.append(row["机型编号"])
        for name in names:
            visits[name] = visits.get(name, 0) + 1

    lon0, lat0 = scene.nodes[0]["lon"], scene.nodes[0]["lat"]
    sites: dict[str, dict] = {}
    for row in cover:
        site = row["点位"]
        if site in sites:
            assert abs(sites[site]["lon"] - float(row["悬停经度"])) < 1e-9
            assert abs(sites[site]["lat"] - float(row["悬停纬度"])) < 1e-9
            assert abs(sites[site]["alt"] - float(row["悬停海拔_m"])) < 1e-6
            sites[site]["relays"].add(row["中继无人机"])
            sites[site]["sorties"].update(row["保障运输架次"].split("、"))
            sites[site]["relay_sorties"].append(row["中继架次"])
            continue
        east, north = terrain.local_xy(float(row["悬停经度"]), float(row["悬停纬度"]),
                                       lon0, lat0)
        sites[site] = {"lon": float(row["悬停经度"]), "lat": float(row["悬停纬度"]),
                       "x": float(east), "y": float(north),
                       "alt": float(row["悬停海拔_m"]),
                       "relays": {row["中继无人机"]},
                       "sorties": set(row["保障运输架次"].split("、")),
                       "relay_sorties": [row["中继架次"]]}
    assert set(sites) == {"西", "东", "北"}, sites
    assert sum(len(info["relay_sorties"]) for info in sites.values()) == len(relays)
    # 中继悬停海拔 = 该点地面高程 + 300 m（问题三模型的作业高度约定）
    for site, info in sites.items():
        ground = float(scene.sample(np.array([info["x"]]), np.array([info["y"]]))[0])
        info["ground"] = ground
        assert abs(info["alt"] - ground - 300.0) < 1.0, (site, info["alt"], ground)

    fig = plt.figure(figsize=FIG_SIZE)
    ax = fig.add_axes(AX_RECT)
    failing, clashes = draw_base(ax, scene)
    draw_route_casings(ax, scene, order)
    drawn = draw_routes(ax, scene, order, models)

    for site, info in sites.items():
        # 亮色回传链路在浅色地形上对比不足，先铺一层深色衬底再画亮色虚线。
        ax.plot([scene.node_x[0], info["x"]], [scene.node_y[0], info["y"]],
                color="#102028", linestyle="--", linewidth=3.0, alpha=0.42, zorder=7)
        ax.plot([scene.node_x[0], info["x"]], [scene.node_y[0], info["y"]],
                color=SITE_COLOR[site], linestyle="--", linewidth=1.5, alpha=0.98,
                zorder=8)
        ax.scatter([info["x"]], [info["y"]], marker=DRONE_MARKER, s=300,
                   color=SITE_COLOR[site], edgecolor="white", linewidth=0.75, zorder=10)
        offsets = {"西": (9, -12), "东": (-12, 10), "北": (-12, 9)}
        offset = offsets[site]
        ha = "left" if site == "西" else "right"
        va = "top" if site == "西" else "bottom"
        relay_names = "/".join(sorted(info["relays"]))
        ax.annotate(f"{site}中继 · {relay_names}\n"
                    f"{info['alt']:.0f} m · 保障 {len(info['sorties'])} 架次",
                    (info["x"], info["y"]), xytext=offset, textcoords="offset points",
                    ha=ha, va=va,
                    fontsize=7.1, color="#17252B", fontproperties=terrain.FONT, zorder=11,
                    bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "none",
                          "alpha": 0.86})
    assert len([line for line in ax.lines if line.get_zorder() == 8
                and line.get_linestyle() == "--"]) == len(sites), "回传链路条数异常"
    assert len(ax.collections) >= len(sites) + 1, "中继点位散点未画出"
    node_markers(ax, scene, visited=visits)

    energy = sum(float(r["架次能耗_kWh"]) for r in sorties)
    finish = max(max(float(r["返回O01时刻_s"]) for r in sorties),
                 max(float(r["返回O01时刻_s"]) for r in relays)) / 3600.0
    ax.set_title(f"问题三 主方案：{drawn} 架次运输与 3 个中继点"
                 f"（全任务完成 {finish:.2f} h，运输能耗 {energy:.2f} kWh）",
                 fontproperties=terrain.FONT, fontsize=11.5, pad=8)
    handles = model_legend()
    handles.append(Line2D([], [], marker="*", linestyle="None", markersize=11,
                          markerfacecolor="#D55E00", markeredgecolor="white",
                          label="调度中心 O01 / 网关 G01"))
    handles.append(Line2D([], [], marker=DRONE_MARKER, linestyle="None",
                          markersize=9, markerfacecolor=SITE_COLOR["东"],
                          markeredgecolor=SITE_COLOR["东"], markeredgewidth=0.3,
                          label="中继无人机"))
    handles.append(Line2D([], [], color="#6B7280", linestyle="--", linewidth=1.2,
                          label="回传链路（网关→中继）"))
    ax.legend(handles=handles, loc="upper left", frameon=True, fontsize=7.4,
              prop=terrain.FONT, framealpha=0.86, edgecolor="#C9D2D8", labelspacing=0.35)
    print(f"    问题三：{drawn} 架次 + {len(sites)} 个中继点，标签越界 {len(failing)}、"
          f"重叠 {len(clashes)}")
    issues = audit_layout(fig)
    verdict = print_report(issues)
    assert verdict != "FAIL", issues
    save(fig, "result_q3_route_map_运输与中继")


def main() -> int:
    terrain.setup_style(journal="general", lang="zh", use_sciplots=False,
                        constrained_layout=False)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                                       "Source Han Sans SC", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False

    scene = terrain.Scene(terrain.load_nodes(terrain.NODE_CSV))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metrics = {row["方案"]: row for row in read_csv(Q2_DIR / "方案对比_四个口径.csv")}
    assert set(metrics) == set(Q2_SCHEMES), set(metrics)

    print("问题二：四个口径的运输路线")
    for scheme in Q2_SCHEMES:
        q2_route_map(scene, scheme, metrics[scheme])
    print("问题三：主方案运输路线与中继点位")
    q3_route_map(scene)
    print("完成：", ", ".join(sorted(p.name for p in OUT_DIR.glob("*.*"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
