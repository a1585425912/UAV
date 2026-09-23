"""第一问结果图：从真实附件和求解结果重建 3×3 证据图及流程图。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image

from utils.plot_style import PALETTE, choose_font
from 问题1_求解 import ROOT, energy, geometry, inputs, load_dem, patterns

SKILL_FIG = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SKILL_FIG))
from export_figure import export_figure

FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)
PREVIEW = ROOT / "results" / "figure_previews"
PREVIEW.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": choose_font("zh"), "font.size": 8,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "svg.fonttype": "none", "axes.unicode_minus": False})
COLORS = [PALETTE[k] for k in ("primary", "secondary", "positive")]


def save(fig, name, size=(7.2, 4.2)):
    fig.tight_layout()
    export_figure(fig, str(FIG / name), formats=["svg", "png"], size_inches=size,
                  dpi=300, grayscale_preview=False, tight=False)
    with Image.open(FIG / f"{name}.png") as im:
        im.convert("L").save(PREVIEW / f"{name}_grayscale.png", dpi=(300, 300))
    plt.close(fig)


def draw():
    drones, origin, sites, boxes = inputs()
    dem = load_dem()
    geos = {s: geometry(s, origin, site, dem) for s, site in sites.items()}
    historical = ROOT / "results" / "历史结果_旧口径"
    trips = pd.read_csv(historical / "单点组批.csv")
    caps = pd.read_csv(historical / "最大安全载荷.csv")
    sens = pd.read_csv(historical / "返航余量敏感性.csv")
    alt = pd.read_csv(historical / "指标权衡.csv")
    names = list(sites)
    short = [s[-3:] for s in names]
    counts = pd.DataFrame([{ "服务区": s, "类型": b["type"], "质量": b["mass"], "体积": b["volume"]}
                           for s, bs in boxes.items() for b in bs])
    contracts = []

    # Raw 1: terrain exposure and flight distance are distinct site attributes.
    fig, ax = plt.subplots()
    ax.scatter([g.distance / 1000 for g in geos.values()], [g.cruise - 50 for g in geos.values()],
               s=34, color=COLORS[0])
    for s, g in geos.items():
        ax.annotate(s[-3:], (g.distance / 1000, g.cruise - 50), xytext=(3, 2),
                    textcoords="offset points", fontsize=6)
    ax.set(xlabel="O01 至服务区水平距离 (km)", ylabel="航段 DEM 最高高程 (m)")
    save(fig, "raw_q1_distance_terrain")
    contracts.append(("raw_q1_distance_terrain", "距离与沿线最高地形并不完全同序", "节点与DEM", "散点", "7.2×4.2 in"))

    # Raw 2: box counts by type and site.
    ct = counts.groupby(["服务区", "类型"]).size().unstack(fill_value=0).reindex(names)
    fig, ax = plt.subplots()
    bottom = np.zeros(len(names))
    for j, typ in enumerate(ct.columns):
        vals = ct[typ].values
        ax.bar(short, vals, bottom=bottom, label=typ, color=COLORS[j % 3] if j < 3 else PALETTE["accent"])
        bottom += vals
    ax.set(xlabel="服务区编号后3位", ylabel="货箱数 (箱)")
    ax.legend(frameon=False, ncol=4, loc="upper right", fontsize=7)
    save(fig, "raw_q1_box_demand")
    contracts.append(("raw_q1_box_demand", "S001的货箱数显著高于多数服务区", "逐箱清单", "堆叠柱", "7.2×4.2 in"))

    # Raw 3: supplied range-load curve; physical input rather than optimized output.
    fig, ax = plt.subplots()
    for j, (name, d) in enumerate(drones.items()):
        q = np.linspace(0, d.payload, 100)
        L = d.range0 - (d.range0 - d.range_full) * (q / d.payload) ** 1.5
        ax.plot(q, L / 1000, label=f"{name}型", color=COLORS[j], linewidth=1.8)
    ax.set(xlabel="有效载荷 (kg)", ylabel="等效航程 (km)")
    ax.legend(frameon=False)
    save(fig, "raw_q1_range_payload")
    contracts.append(("raw_q1_range_payload", "载荷使三机型等效航程按不同曲线下降", "机型参数和题面公式", "曲线", "7.2×4.2 in"))

    # Process 1: feasibility boundary on the tightest site's energy curves.
    target = "S004"
    fig, ax = plt.subplots()
    for j, (name, d) in enumerate(drones.items()):
        q = np.linspace(0, d.payload, 100)
        ax.plot(q, [energy(d, geos[target], x) for x in q], color=COLORS[j], label=f"{name}型能耗")
        ax.axhline(0.8 * d.energy, color=COLORS[j], linestyle="--", linewidth=0.9, alpha=0.8)
        ax.text(81, 0.8 * d.energy, f"{name}型阈值", color=COLORS[j], fontsize=6,
                ha="left", va="center")
    ax.set(xlabel="有效载荷 (kg)", ylabel="S004 往返能耗 (kWh)", xlim=(0, 91))
    ax.legend(frameon=False, ncol=2, fontsize=7)
    save(fig, "process_q1_energy_boundary")
    contracts.append(("process_q1_energy_boundary", "S004的C型载荷受能量边界限制", "DEM+能量模型", "曲线与阈值", "7.2×4.2 in"))

    # Process 2: rated-load SOC shows where the reserve constraint binds.
    soc = np.array([[100 * (1 - energy(drones[g], geos[s], drones[g].payload) / drones[g].energy)
                     for g in drones] for s in names])
    fig, ax = plt.subplots()
    im = ax.pcolormesh(np.arange(4), np.arange(16), soc, cmap="viridis", vmin=0, vmax=80)
    ax.set(xticks=np.arange(3) + 0.5, xticklabels=list(drones), yticks=np.arange(15) + 0.5, yticklabels=short,
           xlabel="机型", ylabel="服务区编号后3位")
    ax.set_ylim(15, 0)
    for i in range(15):
        for j in range(3):
            ax.text(j + 0.5, i + 0.5, f"{soc[i, j]:.0f}", ha="center", va="center",
                    fontsize=6, color="white" if soc[i, j] < 40 else "black")
    ax.set_title("格内数值：额定满载返航 SOC (%)", fontsize=8)
    save(fig, "process_q1_rated_soc", (5.3, 5.2))
    contracts.append(("process_q1_rated_soc", "部分远距离服务区额定满载时SOC接近或低于20%", "DEM+机型参数", "热力图", "5.3×5.2 in"))

    # Process 3: exact pattern enumeration size by site and model.
    pc = np.zeros((15, 3), dtype=int)
    for i, s in enumerate(names):
        _, _, pats = patterns(boxes[s], drones, geos[s], 0.2)
        c = Counter(p["model"] for p in pats)
        pc[i] = [c[g] for g in drones]
    fig, ax = plt.subplots()
    for j, g in enumerate(drones):
        ax.bar(np.arange(15) + (j - 1) * 0.25, pc[:, j], width=0.24, color=COLORS[j], label=f"{g}型")
    ax.set(xticks=range(15), xticklabels=short, xlabel="服务区编号后3位", ylabel="可行组批模式数 (种)")
    ax.legend(frameon=False)
    save(fig, "process_q1_pattern_count")
    contracts.append(("process_q1_pattern_count", "类型压缩后可行组批数随需求规模改变", "精确模式枚举", "分组柱", "7.2×4.2 in"))

    # Result 1: 45 safe payloads.
    capmat = caps.pivot(index="服务区编号", columns="机型编号", values="最大安全载荷（kg）").reindex(names)[list(drones)].values
    fig, ax = plt.subplots()
    im = ax.pcolormesh(np.arange(4), np.arange(16), capmat, cmap="YlGnBu", vmin=0, vmax=80)
    ax.set(xticks=np.arange(3) + 0.5, xticklabels=list(drones), yticks=np.arange(15) + 0.5, yticklabels=short,
           xlabel="机型", ylabel="服务区编号后3位")
    ax.set_ylim(15, 0)
    for i in range(15):
        for j in range(3):
            ax.text(j + 0.5, i + 0.5, f"{capmat[i, j]:.1f}", ha="center", va="center",
                    fontsize=6, color="white" if capmat[i, j] > 40 else "black")
    ax.set_title("格内数值：最大安全载荷 (kg)", fontsize=8)
    save(fig, "result_q1_safe_payload", (5.3, 5.2))
    contracts.append(("result_q1_safe_payload", "C型在部分服务区达不到额定80kg", "45个二分载荷结果", "热力图", "5.3×5.2 in"))

    # Result 2: optimized trips and energy by site.
    grouped = trips.groupby("服务区编号").agg(trips=("架次编号", "count"), energy=("架次能耗（kWh）", "sum")).reindex(names)
    fig, (ax0, ax1) = plt.subplots(2, 1, sharex=True)
    ax0.bar(short, grouped["trips"], color=COLORS[0])
    ax0.set_ylabel("最少架次 (次)")
    ax1.bar(short, grouped["energy"], color=COLORS[1])
    ax1.set(xlabel="服务区编号后3位", ylabel="往返能耗 (kWh)")
    save(fig, "result_q1_trip_energy", (7.2, 5.0))
    contracts.append(("result_q1_trip_energy", "基准方案18架次且各区能耗差异明显", "最优架次表", "上下柱", "7.2×5.0 in"))

    # Result 3: reserve sensitivity and infeasibility.
    summary = sens.groupby("返航余量（%）").first()
    fig, ax = plt.subplots()
    feasible = summary["全任务架次"].notna()
    ax.plot(summary.index[feasible], summary.loc[feasible, "全任务架次"], marker="o", color=COLORS[0])
    for x in summary.index[~feasible]:
        ax.axvline(x, color=PALETTE["contrast"], linestyle=":", alpha=0.7)
        ax.text(x, 19.5, "不可行", rotation=90, ha="right", va="center", fontsize=7)
    ax.set(xlabel="返航安全余量 (%)", ylabel="全任务最少架次 (次)", xticks=summary.index,
           ylim=(17, 22))
    save(fig, "result_q1_reserve_sensitivity")
    contracts.append(("result_q1_reserve_sensitivity", "余量30%增至20架次，40%起本模型无可行全覆盖", "余量情景重求解", "折线与不可行标记", "7.2×4.2 in"))

    # Additional result: energy-first tradeoff.
    totals = alt.groupby("方案")[["架次数", "总能耗（kWh）", "累计作业时间（s）"]].sum()
    fig, axes = plt.subplots(1, 3)
    for ax, col, unit in zip(axes, ["架次数", "总能耗（kWh）", "累计作业时间（s）"], ["次", "kWh", "h"]):
        vals = totals[col].values.copy()
        if unit == "h":
            vals = vals / 3600
        ax.bar(["架次优先", "能耗优先"], vals, color=[COLORS[0], COLORS[1]])
        ax.set_ylabel(f"{col.split('（')[0]} ({unit})")
        ax.set_ylim(0, max(vals) * 1.16)
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7)
    save(fig, "result_q1_priority_tradeoff", (7.2, 3.4))
    contracts.append(("result_q1_priority_tradeoff", "能耗优先只节省0.098kWh却增加一架次", "两种精确优化目标", "三指标对照", "7.2×3.4 in"))

    flow()
    pd.DataFrame(contracts, columns=["图文件前缀", "核心结论", "证据", "图型", "尺寸"]).to_csv(
        historical / "图表契约.csv", index=False, encoding="utf-8-sig")


def flow():
    for filename, labels in [
        ("flow_overall_model", ["附件输入", "DEM航段", "载荷能量", "组批枚举", "整数规划", "约束核验", "结果表与图"]),
        ("flow_q1_model", ["80箱与15区", "逐区模式", "先最少架次", "再最小能耗", "再最小时间", "逐箱映射", "余量重算"]),
    ]:
        fig, ax = plt.subplots(figsize=(7.2, 2.5))
        ax.set(xlim=(0, 7.4), ylim=(0, 1))
        ax.axis("off")
        for i, label in enumerate(labels):
            x = 0.12 + i * 1.04
            patch = FancyBboxPatch((x, 0.35), 0.88, 0.30, boxstyle="round,pad=0.03",
                                   linewidth=0.8, edgecolor=PALETTE["primary"], facecolor="#EDF5FA")
            ax.add_patch(patch)
            ax.text(x + 0.44, 0.50, label, ha="center", va="center", fontsize=7)
            if i < len(labels) - 1:
                ax.add_patch(FancyArrowPatch((x + 0.90, 0.5), (x + 1.02, 0.5),
                                             arrowstyle="->", mutation_scale=8, linewidth=0.8,
                                             color=PALETTE["dark"]))
        save(fig, filename, (7.2, 2.5))


if __name__ == "__main__":
    draw()
