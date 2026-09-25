"""Recreate the Q1 rated-load return-SOC chart as vertical grouped bars."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
GEOMETRY = ROOT / "results" / "单服务区往返几何参数.csv"
DATA = ROOT / "results" / "问题一_非枚举整数规划" / "process_q1_rated_soc_data.csv"
STEM = ROOT / "figures" / "问题一_非枚举整数规划" / "process_q1_rated_soc"

# Mass with battery (kg), rated payload (kg), zero/full payload range (m),
# and usable battery energy (kWh), copied from the task's aircraft data.
AIRCRAFT = {
    "A": (70.0, 25.0, 25000.0, 20000.0, 4.5),
    "B": (65.0, 30.0, 28000.0, 16000.0, 4.0),
    "C": (69.9, 80.0, 26000.0, 12000.0, 8.0),
}
COLORS = {"A": "#2468A0", "B": "#E29B28", "C": "#7657A9"}


def load_data() -> tuple[list[str], dict[str, list[float]]]:
    with GEOMETRY.open(encoding="utf-8-sig", newline="") as stream:
        routes = sorted(csv.DictReader(stream), key=lambda row: row["服务区"])
    assert len(routes) == 15
    areas = [route["服务区"] for route in routes]
    soc = {model: [] for model in AIRCRAFT}
    for route in routes:
        distance = float(route["去程水平距离（m）"])
        climb_out = float(route["去程爬升（m）"])
        climb_back = float(route["返程爬升（m）"])
        for model, (mass0, payload, range0, range_full, energy) in AIRCRAFT.items():
            outbound_horizontal = energy * distance / range_full
            outbound_climb = (mass0 + payload) * 9.81 * climb_out / (3.6e6 * 0.72)
            return_horizontal = energy * distance / range0
            return_climb = mass0 * 9.81 * climb_back / (3.6e6 * 0.72)
            used = outbound_horizontal + outbound_climb + return_horizontal + return_climb
            soc[model].append(100.0 * (1.0 - used / energy))
    return areas, soc


def save_data(areas: list[str], soc: dict[str, list[float]]) -> None:
    with DATA.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["服务区", "A型额定满载返航SOC_%", "B型额定满载返航SOC_%", "C型额定满载返航SOC_%"])
        for i, area in enumerate(areas):
            writer.writerow([area, *(f"{soc[model][i]:.6f}" for model in "ABC")])


def main() -> None:
    areas, soc = load_data()
    save_data(areas, soc)
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "font.size": 8,
        "svg.fonttype": "none",
        "svg.hashsalt": "q1-rated-soc",
        "pdf.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.75,
        "axes.unicode_minus": False,
        "legend.frameon": False,
    })

    fig, ax = plt.subplots(figsize=(7.2, 4.9))
    x = np.arange(len(areas), dtype=float)
    offsets = {"A": -0.23, "B": 0.0, "C": 0.23}
    for model in "ABC":
        values = np.asarray(soc[model])
        mass0, payload, range0, range_full, energy = AIRCRAFT[model]
        ax.bar(x + offsets[model], values, width=0.21, color=COLORS[model],
               label=f"{model} 型：{payload:g} kg，{energy:g} kWh", zorder=3)

    ax.axhline(20, color="#777777", linewidth=0.85, linestyle=(0, (4, 3)), zorder=2)
    ax.set_xlim(-0.65, len(areas) - 0.35)
    ax.set_ylim(-2, 80)
    ax.spines["bottom"].set_position(("data", 0))
    ax.set_xticks(x, areas, rotation=45, ha="right", rotation_mode="anchor")
    ax.set_yticks(np.arange(0, 81, 10))
    ax.set_xlabel("服务区", labelpad=7)
    ax.set_ylabel("额定满载返航 SOC (%)", labelpad=7)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), ncol=1, fontsize=7,
              title="机型（额定载荷，电池能量）", title_fontsize=7,
              handlelength=1.5, labelspacing=1.0, borderaxespad=0)
    fig.subplots_adjust(left=0.10, right=0.74, bottom=0.18, top=0.92)

    svg = STEM.with_suffix(".svg")
    fig.savefig(svg, metadata={"Date": None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
                   encoding="utf-8")
    fig.savefig(STEM.with_suffix(".png"), dpi=600)
    plt.close(fig)
    print(f"Saved {STEM} in SVG and PNG formats")


if __name__ == "__main__":
    main()
