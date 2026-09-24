"""Plot Q1 sortie composition and per-sortie payload use as separate figures."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from plot_q1_rated_soc import AIRCRAFT


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "results" / "问题一_非枚举整数规划" / "最优组批_逐架次.csv"
DEFAULT_OUTPUT = ROOT / "figures" / "问题一_非枚举整数规划"
MODELS = ("A", "B", "C")
COLORS = {"A": "#425B9A", "B": "#2797B5", "C": "#18A184"}
TRIPS_STEM = "result_q1_trips_by_area"
LOAD_STEM = "result_q1_load_utilization"


def load_sorties():
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 18 or any(row["机型"] not in MODELS for row in rows):
        raise ValueError("Expected 18 Q1 sorties using models A, B or C")
    areas = sorted({row["服务区"] for row in rows})
    if areas != [f"S{i:03d}" for i in range(1, 16)]:
        raise ValueError("Expected service areas S001–S015")
    return rows, areas


def save_figure(fig, out_dir: Path, stem: str, publication: bool):
    path = out_dir / stem
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    if publication:
        svg = path.with_suffix(".svg")
        fig.savefig(svg, bbox_inches="tight", metadata={"Date": None})
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
                       encoding="utf-8")
        fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
        fig.savefig(path.with_suffix(".tiff"), dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(path)


def plot_trips(rows, areas, out_dir: Path, publication: bool):
    counts = defaultdict(Counter)
    masses = defaultdict(float)
    for row in rows:
        area = row["服务区"]
        counts[area][row["机型"]] += 1
        masses[area] += float(row["质量_kg"])
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    y = np.arange(len(areas), dtype=float)
    left = np.zeros(len(areas))
    for model in MODELS:
        values = np.array([counts[area][model] for area in areas], dtype=float)
        ax.barh(y, values, left=left, height=0.63, color=COLORS[model],
                label=f"{model} 型", zorder=2)
        left += values
    for i, area in enumerate(areas):
        ax.text(left[i] + 0.06, y[i], f"{int(left[i])} 架 / {masses[area]:.0f} kg",
                va="center", ha="left", fontsize=7)
    ax.set_yticks(y, areas)
    ax.invert_yaxis()
    ax.set_xlim(0, 3.15)
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xlabel("单服务区往返架次（架次）")
    ax.set_ylabel("服务区")
    for tick in (1, 2):
        ax.axvline(tick, color="#DDE4EA", linewidth=0.55, zorder=0)
    ax.legend(loc="lower right", ncol=1, fontsize=7.5)
    fig.subplots_adjust(left=0.12, right=0.98, bottom=0.13, top=0.98)
    save_figure(fig, out_dir, TRIPS_STEM, publication)
    with (out_dir / f"{TRIPS_STEM}_data.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["服务区", "A型架次", "B型架次", "C型架次", "总架次", "总质量_kg"])
        for area in areas:
            writer.writerow([area, *(counts[area][model] for model in MODELS),
                             sum(counts[area].values()), masses[area]])


def plot_load_utilization(rows, out_dir: Path, publication: bool):
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    model_y = {model: i for i, model in enumerate(MODELS)}
    by_model = {model: [row for row in rows if row["机型"] == model] for model in MODELS}
    data = []
    for model in MODELS:
        group = by_model[model]
        if not group:
            continue
        offsets = np.linspace(-0.13, 0.13, len(group))
        for row, offset in zip(group, offsets):
            mass = float(row["质量_kg"])
            utilization = 100 * mass / AIRCRAFT[model][1]
            data.append((row["服务区"], row["架次"], model, mass, utilization))
            ax.scatter(utilization, model_y[model] + offset, s=29,
                       color=COLORS[model], edgecolor="white", linewidth=0.4, zorder=3)
    ax.axvline(100, color="#808890", linestyle="--", linewidth=0.9)
    ax.text(99.5, 2.43, "100% 额定载荷", ha="right", va="top", fontsize=7, color="#667078")
    ax.set_yticks([0, 1, 2], ["A 型", "B 型", "C 型"])
    ax.set_ylim(-0.42, 2.48)
    ax.set_xlim(45, 105)
    ax.set_xticks(np.arange(50, 101, 10))
    ax.set_xlabel("单架次载重利用率（批次质量 / 额定载荷，%）")
    ax.set_ylabel("机型")
    ax.grid(axis="x", color="#DDE4EA", linewidth=0.55, zorder=0)
    for model in ("B", "C"):
        ax.scatter([], [], s=29, color=COLORS[model], label=f"{model} 型（{len(by_model[model])} 架次）")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7.5, borderaxespad=0)
    fig.subplots_adjust(left=0.10, right=0.78, bottom=0.23, top=0.96)
    save_figure(fig, out_dir, LOAD_STEM, publication)
    with (out_dir / f"{LOAD_STEM}_data.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["服务区", "架次", "机型", "质量_kg", "额定载荷利用率_pct"])
        writer.writerows(data)


def main(out_dir: Path = DEFAULT_OUTPUT, publication: bool = False):
    rows, areas = load_sorties()
    out_dir.mkdir(parents=True, exist_ok=True)
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial", "DejaVu Sans", "sans-serif"],
        "font.size": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "legend.frameon": False,
    })
    plot_trips(rows, areas, out_dir, publication)
    plot_load_utilization(rows, out_dir, publication)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--publication", action="store_true", help="Also export PDF and 600 dpi TIFF")
    args = parser.parse_args()
    main(args.out_dir, publication=args.publication)
