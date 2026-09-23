"""从航路几何结果绘制 O01 至各服务区的单程水平直线距离柱状图。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
SKILL_SCRIPTS = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure  # noqa: E402
from setup_style import setup_style  # noqa: E402
from visual_qa import audit_layout, print_report  # noqa: E402


def main() -> None:
    source = ROOT / "results" / "单服务区往返几何参数.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 15
    data = sorted(((r["服务区"], float(r["去程水平距离（m）"]) / 1000) for r in rows),
                  key=lambda item: item[0])
    assert all(value > 0 for _, value in data)

    setup_style(journal="general", lang="zh", use_sciplots=False, constrained_layout=False)
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    fig.subplots_adjust(left=0.10, right=0.97, top=0.89, bottom=0.23)
    names = [item[0] for item in data]
    values = [item[1] for item in data]
    ax.bar(names, values, color="#0072B2", width=0.68, edgecolor="none")
    ax.set_ylim(0, 9)
    ax.set_xlabel("服务区编号", labelpad=9)
    ax.set_ylabel("单程水平直线距离（km）", labelpad=9)
    ax.set_title("各服务区直飞航路距离", loc="left", pad=14, fontsize=14, weight="bold")
    ax.grid(axis="y", color="#D9E2E8", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", rotation=45, length=0, pad=6)
    ax.tick_params(axis="y", length=0)
    fig.text(0.10, 0.035, "数据：30 m DEM 与节点经纬度；WGS84 O01 局部坐标。柱高为单程距离。",
             fontsize=8.5, color="#5B6570")
    issues = audit_layout(fig)
    print_report(issues)
    assert not any(severity == "FAIL" for severity, _ in issues), issues
    output = ROOT / "figures" / "raw_q1_route_straight_distance"
    export_figure(fig, basename=str(output), formats=["svg", "png"],
                  size_inches=(10.5, 5.8), dpi=300, grayscale_preview=True)
    plt.close(fig)
    print(f"已绘制 {len(data)} 条单程航路。")


if __name__ == "__main__":
    main()
