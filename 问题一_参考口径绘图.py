"""根据问题一参考口径 CSV 绘制载荷、权衡和返航余量图。"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
plt.rcParams["svg.fonttype"] = "none"

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "results" / "问题一_参考口径"
OUT = ROOT / "figures" / "问题一_参考口径"
OUT.mkdir(parents=True, exist_ok=True)
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
COLORS = {"A": "#4E79A7", "B": "#F28E2B", "C": "#59A14F"}


def rows(name):
    with (SOURCE / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def labels(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, fontproperties=FONT, fontsize=11)
    ax.set_ylabel(ylabel, fontproperties=FONT, fontsize=11)
    ax.set_title(title, fontproperties=FONT, fontsize=13, pad=12)
    ax.grid(axis="y", color="#dddddd", linewidth=.7)
    ax.spines[["top", "right"]].set_visible(False)


def save(fig, stem):
    fig.savefig(OUT / f"{stem}.png", dpi=320, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def payload():
    data = rows("最大安全载荷_45组.csv")
    areas = sorted({r["服务区"] for r in data})
    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = range(len(areas))
    for shift, model in zip((-.25, 0, .25), "ABC"):
        values = [float(next(r["最大安全载荷_kg"] for r in data if r["服务区"] == area and r["机型"] == model)) for area in areas]
        ax.bar([i + shift for i in x], values, width=.23, color=COLORS[model], label=f"{model} 型")
    ax.set_xticks(list(x), areas, rotation=45)
    labels(ax, "服务区", "最大安全载荷（kg）", "20% 返航余量下的最大安全载荷")
    ax.set_ylim(0, 100)
    ax.legend(prop=FONT, frameon=False, ncol=3)
    save(fig, "最大安全载荷_15区3机型")


def frontier():
    data = rows("架次能耗权衡.csv")
    x = [int(r["总架次数"]) for r in data]
    e = [float(r["最小总能耗_kWh"]) for r in data]
    t = [float(r["对应累计作业时间_s"]) / 3600 for r in data]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(x, e, "o-", color="#4E79A7", linewidth=2, label="最低能耗")
    ax.scatter(x[:2], e[:2], s=110, facecolors="none", edgecolors="#D62728", linewidth=2, zorder=4)
    ax2 = ax.twinx()
    ax2.plot(x, t, "s--", color="#F28E2B", linewidth=1.6, label="累计作业时间")
    ax2.set_ylabel("累计作业时间（h）", fontproperties=FONT, fontsize=11)
    labels(ax, "全任务架次数", "最低总能耗（kWh）", "架次数—能耗—累计时间权衡（红圈为非支配方案）")
    ax.set_xticks(x)
    ax.legend(prop=FONT, frameon=False, loc="upper left")
    ax2.legend(prop=FONT, frameon=False, loc="upper right")
    save(fig, "架次能耗时间权衡")


def reserve():
    data = rows("返航余量汇总.csv")
    x = [float(r["返航余量_百分比"]) for r in data]
    count = [int(r["架次数"]) for r in data]
    energy = [float(r["总能耗_kWh"]) for r in data]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(x, count, "o-", color="#4E79A7", linewidth=2, label="架次数")
    ax.set_ylim(16, 27)
    ax.set_yticks(range(16, 28, 2))
    ax2 = ax.twinx()
    ax2.plot(x, energy, "s--", color="#F28E2B", linewidth=1.6, label="总能耗")
    ax2.set_ylabel("总能耗（kWh）", fontproperties=FONT, fontsize=11)
    labels(ax, "最低返航 SOC 要求（%）", "全任务架次数", "返航余量要求对方案的影响")
    ax.set_xticks(x)
    ax.legend(prop=FONT, frameon=False, loc="upper left")
    ax2.legend(prop=FONT, frameon=False, loc="upper center")
    save(fig, "返航余量敏感性")


if __name__ == "__main__":
    payload()
    frontier()
    reserve()
    print(f"完成 3 张问题一图，每张 PNG/SVG：{OUT}")
