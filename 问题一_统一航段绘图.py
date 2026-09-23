"""从统一航段问题一输出生成数据、过程、结果图及流程图。"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from 问题一_统一航段精确组批 import ROOT, OUT, load_inputs, read_csv, trip
from utils.plot_style import choose_font

sys.path.insert(0, str(Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"))
from export_figure import export_figure

FIG = ROOT / "figures" / "问题一_统一航段"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": choose_font("zh"), "font.size": 8, "svg.fonttype": "none",
                     "axes.spines.top": False, "axes.spines.right": False, "axes.unicode_minus": False})
colors = ["#0072B2", "#D55E00", "#009E73"]


def save(fig, name, size=(7.2, 4.2)):
    fig.tight_layout()
    export_figure(fig, str(FIG / name), formats=["svg", "png"], size_inches=size,
                  dpi=300, grayscale_preview=False, tight=False)
    plt.close(fig)


def flow(name, labels):
    fig, ax = plt.subplots()
    ax.set(xlim=(0, 7.4), ylim=(0, 1))
    ax.axis("off")
    for j, label in enumerate(labels):
        x = 0.12 + j * 1.04
        ax.add_patch(FancyBboxPatch((x, 0.35), 0.88, 0.3, boxstyle="round,pad=0.03",
                                    linewidth=0.8, edgecolor=colors[0], facecolor="#E8F1F7"))
        ax.text(x + 0.44, 0.5, label, ha="center", va="center", fontsize=7)
        if j < len(labels) - 1:
            ax.add_patch(FancyArrowPatch((x + 0.91, 0.5), (x + 1.02, 0.5),
                                         arrowstyle="->", mutation_scale=8, linewidth=0.8))
    save(fig, name, (7.2, 2.5))


def main():
    drones, boxes, routes = load_inputs()
    areas = sorted(boxes)
    short = [x[-3:] for x in areas]
    caps = read_csv(OUT / "最大安全载荷_45组.csv")
    details = read_csv(OUT / "安全载荷能耗明细.csv")
    candidates = read_csv(OUT / "全部可行组批.csv")
    chosen = read_csv(OUT / "最优组批_逐架次.csv")
    contracts = []

    fig, ax = plt.subplots()
    ax.scatter([float(routes[a]["去程水平距离（m）"]) / 1000 for a in areas],
               [float(routes[a]["去程巡航海拔（m）"]) - 50 for a in areas], color=colors[0], s=32)
    for a in areas:
        ax.annotate(a[-3:], (float(routes[a]["去程水平距离（m）"]) / 1000,
                               float(routes[a]["去程巡航海拔（m）"]) - 50), xytext=(3, 2),
                    textcoords="offset points", fontsize=6)
    ax.set(xlabel="单程水平距离 (km)", ylabel="航段最高 DEM 海拔 (m)")
    save(fig, "raw_q1_distance_terrain")
    contracts.append(("raw_q1_distance_terrain", "距离与地形暴露不完全同序", "15条统一航段", "散点"))

    fig, ax = plt.subplots()
    counts = [len(boxes[a]) for a in areas]
    ax.bar(short, counts, color=colors[0])
    ax.set(xlabel="服务区编号后3位", ylabel="货箱数 (箱)")
    save(fig, "raw_q1_box_count")
    contracts.append(("raw_q1_box_count", "S001箱数最多", "80箱逐箱清单", "柱状"))

    fig, ax = plt.subplots()
    for j, (name, d) in enumerate(drones.items()):
        q = np.linspace(0, d["payload"], 120)
        L = d["range0"] - (d["range0"] - d["range_full"]) * (q / d["payload"]) ** 1.5
        ax.plot(q, L / 1000, color=colors[j], label=f"{name}型")
    ax.set(xlabel="有效载荷 (kg)", ylabel="标准等效航程 (km)")
    ax.legend(frameon=False)
    save(fig, "raw_q1_range_payload")
    contracts.append(("raw_q1_range_payload", "载荷增加时航程下降", "题面公式和机型参数", "曲线"))

    fig, ax = plt.subplots()
    area = "S004"
    for j, (name, d) in enumerate(drones.items()):
        q = np.linspace(0, d["payload"], 120)
        ax.plot(q, [trip(d, routes[area], float(x))["total_kwh"] for x in q], color=colors[j], label=f"{name}型")
        ax.hlines(0.8 * d["energy"], 0, d["payload"], colors=colors[j], linestyles="--", linewidth=0.8,
                  label=f"{name}型20%余量上限")
    ax.set(xlabel="有效载荷 (kg)", ylabel="S004往返能耗 (kWh)")
    ax.legend(frameon=False, ncol=2, fontsize=7)
    save(fig, "process_q1_energy_boundary")
    contracts.append(("process_q1_energy_boundary", "S004的C型载荷受能量限制", "能耗模型", "曲线与阈值"))

    soc = np.array([[100 * (1 - float(next(r["满载能耗_kwh"] for r in details if r["服务区"] == a and r["机型"] == g)) / drones[g]["energy"])
                     for g in drones] for a in areas])
    fig, ax = plt.subplots()
    im = ax.pcolormesh(np.arange(4), np.arange(16), soc, cmap="viridis", vmin=-5, vmax=80)
    ax.set(xticks=np.arange(3) + 0.5, xticklabels=list(drones), yticks=np.arange(15) + 0.5, yticklabels=short,
           xlabel="机型", ylabel="服务区编号后3位")
    ax.set_ylim(15, 0)
    for i in range(15):
        for j in range(3):
            ax.text(j + 0.5, i + 0.5, f"{soc[i,j]:.1f}", ha="center", va="center", fontsize=6,
                    color="white" if soc[i,j] < 40 else "black")
    ax.set_title("格内数值：额定满载返航SOC (%)", fontsize=8)
    save(fig, "process_q1_rated_soc", (5.3, 5.2))
    contracts.append(("process_q1_rated_soc", "部分额定满载架次不满足20%余量", "45组满载试算", "热力图"))

    cc = Counter((r["服务区"], r["机型"]) for r in candidates)
    fig, ax = plt.subplots()
    for j, g in enumerate(drones):
        ax.bar(np.arange(15) + (j - 1) * 0.25, [cc[(a, g)] for a in areas], width=0.24,
               color=colors[j], label=f"{g}型")
    ax.set_yscale("log")
    ax.set(xticks=range(15), xticklabels=short, xlabel="服务区编号后3位", ylabel="可行逐箱子集数（对数轴）", ylim=(0.8, 30000))
    ax.legend(frameon=False)
    save(fig, "process_q1_candidate_count")
    contracts.append(("process_q1_candidate_count", "逐区完整候选数量随箱数变化", "19525条可行候选", "分组柱"))

    mat = np.array([[float(next(r["最大安全载荷_kg"] for r in caps if r["服务区"] == a and r["机型"] == g))
                     for g in drones] for a in areas])
    fig, ax = plt.subplots()
    im = ax.pcolormesh(np.arange(4), np.arange(16), mat, cmap="YlGnBu", vmin=0, vmax=80)
    ax.set(xticks=np.arange(3) + 0.5, xticklabels=list(drones), yticks=np.arange(15) + 0.5, yticklabels=short,
           xlabel="机型", ylabel="服务区编号后3位")
    ax.set_ylim(15, 0)
    for i in range(15):
        for j in range(3):
            ax.text(j + 0.5, i + 0.5, f"{mat[i,j]:.1f}", ha="center", va="center", fontsize=6,
                    color="white" if mat[i,j] > 40 else "black")
    save(fig, "result_q1_safe_payload", (5.3, 5.2))
    contracts.append(("result_q1_safe_payload", "45组安全载荷中6组由能量约束主导", "安全载荷表", "带数值热力图"))

    site_trips = Counter(r["服务区"] for r in chosen)
    fig, ax = plt.subplots()
    ax.bar(short, [site_trips[a] for a in areas], color=colors[0])
    ax.set(xlabel="服务区编号后3位", ylabel="最少架次 (次)")
    save(fig, "result_q1_trips_by_area")
    contracts.append(("result_q1_trips_by_area", "3个服务区各需2架次，其余各1架次", "精确DP结果", "柱状"))

    fig, ax = plt.subplots()
    for j, name in enumerate(drones):
        points = [(k, r) for k, r in enumerate(chosen, 1) if r["机型"] == name]
        if points:
            ax.scatter([k for k, _ in points], [100 * float(r["返航SOC"]) for _, r in points],
                       color=colors[j], s=36, label=f"{name}型")
    ax.axhline(20, color="#555555", linestyle="--", linewidth=0.8)
    ax.set(xlabel="最优方案架次序号", ylabel="返航SOC (%)", xticks=range(1, len(chosen) + 1), ylim=(0, 100))
    ax.legend(frameon=False)
    save(fig, "result_q1_trip_soc")
    contracts.append(("result_q1_trip_soc", "全部18架次返航SOC不低于20%", "最优架次表", "点图"))

    flow("flow_overall_model", ["原始附件", "统一航段", "载荷能量", "逐箱候选", "精确组批", "独立审计", "结果文件"])
    flow("flow_q1_model", ["45组载荷", "全部子集", "机型筛选", "位掩码DP", "逐箱回溯", "约束复算", "问题二接口"])
    with (OUT / "图表契约.csv").open("w", encoding="utf-8-sig", newline="") as f:
        import csv
        w = csv.writer(f)
        w.writerow(["图文件前缀", "核心结论", "证据", "图型"])
        w.writerows(contracts)
    print(f"输出 {len(contracts)} 张数据图及 2 张流程图：{FIG}")


if __name__ == "__main__":
    main()
