"""绘制 15 条 O01→服务区→O01 航路的去、返程爬升高度。

图表契约：比较每条单服务区往返航路的总爬升，并呈现去程与返程构成。
证据：results/单服务区往返几何参数.csv；确定性几何量，无抽样误差棒。
运行：python 航路爬升柱状图.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
FIGURE_SCRIPTS = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(FIGURE_SCRIPTS))
from export_figure import export_figure  # noqa: E402
from setup_style import setup_style  # noqa: E402
from visual_qa import audit_layout  # noqa: E402


def main() -> None:
    source = ROOT / "results" / "单服务区往返几何参数.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 15
    rows.sort(key=lambda row: float(row["总爬升（m）"]), reverse=True)
    sites = [row["服务区"] for row in rows]
    outward = np.array([float(row["去程爬升（m）"]) for row in rows])
    backward = np.array([float(row["返程爬升（m）"]) for row in rows])
    totals = np.array([float(row["总爬升（m）"]) for row in rows])
    assert np.allclose(outward + backward, totals)

    setup_style(journal="general", lang="zh", constrained_layout=True)
    plt.rcParams.update({"font.size": 9, "axes.labelsize": 10, "xtick.labelsize": 8,
                         "ytick.labelsize": 9, "legend.fontsize": 9})
    fig, ax = plt.subplots(figsize=(8.0, 5.7))
    y = np.arange(len(rows))
    ax.barh(y, outward, color="#0072B2", label="去程爬升", height=0.66)
    ax.barh(y, backward, left=outward, color="#E69F00", label="返程爬升", height=0.66)
    ax.set_yticks(y, sites)
    ax.invert_yaxis()
    ax.set_xlim(0, float(max(totals)) * 1.14)
    ax.set_xlabel("累计爬升高度（m）")
    ax.set_title("O01 → 服务区 → O01：往返累计爬升", loc="left", fontsize=12, pad=13)
    ax.legend(loc="lower right", frameon=False, ncol=2)
    for position, total in zip(y, totals):
        ax.text(total + 6, position, f"{total:.0f}", va="center", ha="left", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(False)
    issues = audit_layout(fig)
    if any(severity == "FAIL" for severity, _ in issues):
        raise RuntimeError(f"图表布局检查失败：{issues}")
    out = ROOT / "figures" / "route_climb_roundtrip"
    paths = export_figure(fig, str(out), formats=["svg", "png"],
                          size_inches=(8.0, 5.7), dpi=300,
                          grayscale_preview=True, tight=False)
    plt.close(fig)
    print(f"已导出 {len(paths)} 个文件；最高 {sites[0]} {totals[0]:.1f} m；最低 {sites[-1]} {totals[-1]:.1f} m")
    for severity, message in issues:
        print(f"{severity}: {message}")


if __name__ == "__main__":
    main()
