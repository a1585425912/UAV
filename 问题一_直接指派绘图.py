"""为问题一直接指派 MILP 汇集共享证据图，并绘制求解过程图与子问题流程图。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from utils.plot_style import choose_font
from plot_q1_distance_terrain import main as plot_distance_terrain
from plot_q1_rated_soc import main as plot_rated_soc
from 问题一_流程图 import main as draw_flow_q1

sys.path.insert(0, str(Path(r"C:\Users\mika\.claude\skills\math-modeling") / "tools" / "figure" / "scripts"))
from export_figure import export_figure  # noqa: E402

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


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    plot_distance_terrain(TARGET)
    plot_rated_soc()
    # 其余数据图随当前结果提交；下文重绘直接指派的求解过程与流程图。
    shared = ("raw_q1_range_payload", "raw_q1_box_count",
              "process_q1_energy_boundary", "process_q1_rated_soc",
              "result_q1_safe_payload", "result_q1_trips_by_area", "result_q1_trip_soc")
    for stem in shared:
        if not (TARGET / (stem + ".png")).exists():
            raise FileNotFoundError(f"当前版本的数据图缺失：{stem}.png")
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
    # 子问题流程图按 Skill 的建模流程图规范由 问题一_流程图.py 生成（含 shape/越界/缺字自检）
    draw_flow_q1()
    for path in TARGET.glob("*.svg"):
        path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n",
                        encoding="utf-8")
    print(f"图表已生成：{TARGET}")


if __name__ == "__main__":
    main()
