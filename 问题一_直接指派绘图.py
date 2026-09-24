"""为问题一直接指派 MILP 汇集共享证据图，并绘制新算法流程与求解过程图。"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from utils.plot_style import choose_font
from plot_q1_rated_soc import main as plot_rated_soc

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "figures" / "问题一_非枚举整数规划"
RESULT = ROOT / "results" / "问题一_非枚举整数规划"
plt.rcParams.update({"font.family": choose_font("zh"), "font.size": 8,
                     "svg.fonttype": "none", "axes.spines.top": False,
                     "axes.spines.right": False, "axes.unicode_minus": False})


def save(fig, name, size=(7.2, 4.2)):
    fig.set_size_inches(*size)
    fig.tight_layout()
    svg = TARGET / f"{name}.svg"
    fig.savefig(svg, metadata={"Date": None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
                   encoding="utf-8")
    fig.savefig(TARGET / f"{name}.png", dpi=300)
    plt.close(fig)


def flow(name, labels, loop_from, loop_to):
    fig, ax = plt.subplots()
    ax.set(xlim=(0, 7.4), ylim=(0, 1.12))
    ax.axis("off")
    for j, label in enumerate(labels):
        xpos = 0.12 + j * 1.04
        ax.add_patch(FancyBboxPatch((xpos, 0.35), 0.88, 0.3,
                                    boxstyle="round,pad=0.03", linewidth=0.8,
                                    edgecolor="#0072B2", facecolor="#E8F1F7"))
        ax.text(xpos + 0.44, 0.5, label, ha="center", va="center", fontsize=7)
        if j < len(labels) - 1:
            ax.add_patch(FancyArrowPatch((xpos + 0.91, 0.5), (xpos + 1.02, 0.5),
                                         arrowstyle="->", mutation_scale=8, linewidth=0.8))
    start = 0.56 + loop_from * 1.04
    end = 0.56 + loop_to * 1.04
    ax.plot([start, start, end], [0.68, 0.86, 0.86], color="#D55E00", linewidth=0.85)
    ax.annotate("", xy=(end, 0.68), xytext=(end, 0.86),
                arrowprops={"arrowstyle": "->", "color": "#D55E00", "linewidth": 0.85})
    ax.text((start + end) / 2, 0.91, "未满足能耗约束或间隙未收敛：新增切平面",
            ha="center", va="bottom", fontsize=6.5, color="#A44A00")
    save(fig, name, (7.2, 2.5))


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    plot_rated_soc()
    # 其余数据图随当前结果提交；下文只重绘直接指派的求解过程与流程图。
    shared = ("raw_q1_distance_terrain", "raw_q1_range_payload", "raw_q1_box_count",
              "process_q1_energy_boundary", "process_q1_rated_soc",
              "result_q1_safe_payload", "result_q1_trips_by_area", "result_q1_trip_soc")
    for stem in shared:
        for suffix in (".svg", ".png"):
            if not (TARGET / (stem + suffix)).exists():
                raise FileNotFoundError(f"当前版本的数据图缺失：{stem + suffix}")
    summary = json.loads((RESULT / "汇总.json").read_text(encoding="utf-8"))
    areas = sorted(summary["分区求解"])
    calls = [summary["分区求解"][area]["MILP调用次数"] for area in areas]
    gap = [max(0.0, summary["分区求解"][area]["能耗最优性绝对间隙_kWh"]) for area in areas]
    fig, ax = plt.subplots()
    ax.bar(range(len(areas)), calls, color="#0072B2", width=0.7)
    ax.set(xlabel="服务区", ylabel="MILP 调用次数", ylim=(0, max(calls) + 1))
    ax.set_xticks(range(len(areas)), [area[-3:] for area in areas], rotation=45)
    ax.text(0.98, 0.97, f"最大能耗下界间隙: {max(gap):.2e} kWh",
            transform=ax.transAxes, ha="right", va="top", fontsize=8)
    save(fig, "process_q1_milp_calls")
    flow("flow_overall_model", ["航段与货箱", "机型参数", "安全载荷", "逐箱指派", "MILP切平面", "真实能耗复核", "结果输出"], 5, 4)
    flow("flow_q1_model", ["货箱数据", "航段载荷", "逐箱指派", "MILP三级优化", "真实能耗", "最优性判定", "余量与审计"], 5, 3)
    for path in TARGET.glob("*.svg"):
        path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n",
                        encoding="utf-8")
    print(f"图表已生成：{TARGET}")


if __name__ == "__main__":
    main()
