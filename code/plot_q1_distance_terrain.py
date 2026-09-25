"""Plot Q1 route terrain and distance on equally spaced route categories."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "results" / "有向航段几何参数.csv"
DEFAULT_OUTPUT = ROOT / "figures" / "问题一_非枚举整数规划"
STEM = "raw_q1_distance_terrain"


def load_routes():
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    routes = sorted(
        (row for row in rows if row["起点"] == "O01" and row["终点"].startswith("S")),
        key=lambda row: row["终点"],
    )
    if len(routes) != 15 or len({row["终点"] for row in routes}) != 15:
        raise ValueError("Expected 15 unique O01-to-service-area routes")
    reverse = {(row["起点"], row["终点"]): row for row in rows}
    data = []
    for row in routes:
        area = row["终点"]
        back = reverse[(area, "O01")]
        dem = float(row["航段DEM最高海拔（m）"])
        distance = float(row["水平距离（m）"]) / 1000
        if not np.isclose(dem, float(back["航段DEM最高海拔（m）"])):
            raise ValueError(f"Outbound/return DEM maxima differ for {area}")
        if not np.isclose(distance, float(back["水平距离（m）"]) / 1000):
            raise ValueError(f"Outbound/return distances differ for {area}")
        data.append((area, distance, dem))
    return data


def main(out_dir: Path = DEFAULT_OUTPUT, publication: bool = False):
    data = load_routes()
    out_dir.mkdir(parents=True, exist_ok=True)
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial", "DejaVu Sans", "sans-serif"],
        "font.size": 8,
        "axes.spines.top": False,
        "axes.spines.right": True,
        "axes.linewidth": 0.8,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "legend.frameon": False,
    })
    x = np.arange(len(data), dtype=float)
    areas = [item[0] for item in data]
    distances = [item[1] for item in data]
    elevations = [item[2] for item in data]

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    bars = ax.bar(x, elevations, width=0.66, color="#3A78A8", label="航段最高 DEM 海拔", zorder=2)
    ax.set_ylabel("航段最高 DEM 海拔 (m)")
    ax.set_ylim(0, 620)
    ax.set_xlim(-0.65, len(data) - 0.35)
    ax.set_xticks(x, areas)
    ax.set_xlabel("服务区航段（O01 往返）")
    ax.grid(axis="y", color="#DDE4EA", linewidth=0.6, zorder=0)
    ax.spines["left"].set_color("#3A78A8")
    ax.tick_params(axis="y", colors="#2E6187")

    ax_distance = ax.twinx()
    (line,) = ax_distance.plot(x, distances, color="#D18432", marker="o", markersize=3.6,
                               linewidth=1.5, label="单程水平距离", zorder=3)
    ax_distance.set_ylabel("单程水平距离 (km)", color="#A85E19")
    ax_distance.set_ylim(0, 10)
    ax_distance.tick_params(axis="y", colors="#A85E19")
    ax_distance.spines["right"].set_color("#D18432")
    ax_distance.spines["right"].set_visible(True)
    ax_distance.spines["top"].set_visible(False)
    ax.legend([bars, line], ["航段最高 DEM 海拔", "单程水平距离"],
              loc="upper right", ncol=1, fontsize=7.5)
    fig.subplots_adjust(left=0.105, right=0.895, bottom=0.17, top=0.96)

    output = out_dir / STEM
    svg_path = output.with_suffix(".svg")
    fig.savefig(svg_path, bbox_inches="tight", metadata={"Date": None})
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
                        encoding="utf-8")
    fig.savefig(output.with_suffix(".png"), dpi=300, bbox_inches="tight")
    if publication:
        fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
        fig.savefig(output.with_suffix(".tiff"), dpi=600, bbox_inches="tight")
    plt.close(fig)
    with output.with_name(STEM + "_data.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["服务区航段", "单程水平距离（km）", "航段DEM最高海拔（m）"])
        writer.writerows(data)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--publication", action="store_true", help="Also export PDF and 600 dpi TIFF")
    args = parser.parse_args()
    main(args.out_dir, publication=args.publication)
