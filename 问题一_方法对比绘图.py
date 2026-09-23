"""问题一方法对比：从结果 CSV 生成过程图与结果图。"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from 问题一_统一航段精确组批 import load_inputs, safe_payload
from utils.plot_style import choose_font

sys.path.insert(0, str(Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"))
from export_figure import export_figure

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题一_方法对比"
FIG = ROOT / "figures" / "问题一_方法对比"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": choose_font("zh"), "font.size": 8, "svg.fonttype": "none",
                     "axes.spines.top": False, "axes.spines.right": False, "axes.unicode_minus": False})
colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7"]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save(fig, name, size=(7.2, 4.2)):
    fig.tight_layout()
    export_figure(fig, str(FIG / name), formats=["svg", "png"], size_inches=size,
                  dpi=300, grayscale_preview=False, tight=False)
    plt.close(fig)


def main():
    rows = read_csv(OUT / "方法对比_分区.csv")
    staged = {r["服务区"]: r for r in read_csv(OUT / "枚举分阶段耗时.csv")}
    summary = json.loads((OUT / "汇总.json").read_text(encoding="utf-8"))
    areas = [r["服务区"] for r in rows]
    short = [a[-3:] for a in areas]
    x = np.arange(len(areas))
    contracts = []
    drones, boxes, routes = load_inputs()

    # 原始数据图：逐区装载规模
    mass = [sum(b["mass"] for b in boxes[a]) for a in areas]
    volume = [sum(b["volume"] for b in boxes[a]) for a in areas]
    fig, axes = plt.subplots(3, 1, sharex=True)
    for ax, values, label in zip(axes, ([len(boxes[a]) for a in areas], mass, volume),
                                     ("货箱数 (箱)", "总质量 (kg)", "总体积 (m³)")):
        ax.bar(x, values, 0.62, color=colors[0])
        ax.set_ylabel(label)
    axes[-1].set(xticks=x, xticklabels=short, xlabel="服务区编号后3位")
    save(fig, "raw_q1_area_load", (7.2, 6.0))
    contracts.append(("raw_q1_area_load", "S001的箱数、总质量、总体积均最大", "80箱逐箱清单", "三联柱状"))

    # 原始数据图：单箱质量-体积分布与机型上限
    fig, ax = plt.subplots()
    counts = {}
    for a in areas:
        for b in boxes[a]:
            key = (b["mass"], b["volume"])
            counts[key] = counts.get(key, 0) + 1
    ax.scatter([v for _, v in counts], [m for m, _ in counts],
               s=[12 * c for c in counts.values()], color=colors[0], alpha=0.75, linewidths=0)
    for (m, v), c in counts.items():
        ax.annotate(f"{c}箱", (v, m), textcoords="offset points", xytext=(7, -2), fontsize=7)
    for j, name in enumerate(drones):
        drone = drones[name]
        ax.plot([0, drone["volume"]], [drone["payload"], drone["payload"]], color=colors[j + 1], linewidth=1.2,
                label=f"{name}型 额定载重 {drone['payload']:.0f} kg")
        ax.axvline(drone["volume"], color=colors[j + 1], linewidth=0.8, linestyle=":")
    ax.set(xlabel="单箱体积 (m³)", ylabel="单箱质量 (kg)", ylim=(0, 88))
    ax.set_title("80 箱共 4 种规格，标记面积与箱数成正比", fontsize=8)
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    save(fig, "raw_q1_box_mass_volume")
    contracts.append(("raw_q1_box_mass_volume", "单箱质量体积远小于机型上限，限制来自批量叠加", "80箱逐箱清单", "散点与阈值线"))

    # 原始数据图：逐区装载量与单架次能力之比
    fig, ax = plt.subplots()
    mass_cap = [max(min(safe_payload(drones[g], routes[a])[0], drones[g]["payload"]) for g in drones)
                for a in areas]
    volume_cap = max(drones[g]["volume"] for g in drones)
    ax.bar(x - 0.18, [m / c for m, c in zip(mass, mass_cap)], 0.36, color=colors[0],
           label="总质量 / 单架次最大可载质量")
    ax.bar(x + 0.18, [v / volume_cap for v in volume], 0.36, color=colors[1], label="总体积 / 最大货舱体积")
    for level in (1, 2):
        ax.axhline(level, color="#555555", linewidth=0.8, linestyle="--")
    ax.set(xticks=x, xticklabels=short, xlabel="服务区编号后3位", ylabel="装载量与单架次能力之比")
    ax.legend(frameon=False, fontsize=7)
    save(fig, "raw_q1_area_load_ratio")
    contracts.append(("raw_q1_area_load_ratio", "只有S001/S002/S003的装载量超过单架次能力", "逐箱清单与机型参数", "柱状与阈值线"))

    # 过程图：各方法逐区耗时
    fig, ax = plt.subplots()
    series = [("枚举_耗时_s", "枚举DP", 0), ("MILP_耗时_s", "指派MILP", 1), ("贪心_耗时_s", "贪心BFD", 2)]
    width = 0.26
    for key, label, j in series:
        ax.bar(x + (j - 1) * width, [max(float(r[key]), 1e-5) for r in rows], width,
               color=colors[j], label=label)
    ax.set_yscale("log")
    ax.set_ylim(1e-4, 10)
    ax.set(xticks=x, xticklabels=short, xlabel="服务区编号后3位", ylabel="单区求解耗时 (s, 对数轴)")
    ax.legend(frameon=False, ncol=3)
    save(fig, "process_q1_method_runtime")
    contracts.append(("process_q1_method_runtime", "本算例规模下枚举DP与MILP耗时相当，贪心快三个数量级",
                      "方法对比_分区.csv", "对数分组柱"))

    # 过程图：枚举内部两阶段耗时
    fig, ax = plt.subplots()
    ax.bar(x - 0.18, [float(staged[a]["候选枚举耗时_s"]) for a in areas], 0.36, color=colors[0], label="候选子集枚举 2^n")
    ax.bar(x + 0.18, [float(staged[a]["DP耗时_s"]) for a in areas], 0.36, color=colors[1], label="锚点位掩码 DP")
    ax.set_yscale("log")
    ax.set_ylim(1e-5, 10)
    ax.set(xticks=x, xticklabels=short, xlabel="服务区编号后3位", ylabel="耗时 (s, 对数轴)")
    ax.legend(frameon=False)
    save(fig, "process_q1_enum_phase")
    contracts.append(("process_q1_enum_phase", "S001同时支配候选枚举与DP两阶段耗时", "枚举分阶段耗时.csv", "对数分组柱"))

    # 过程图：S001 上 LP 支配剪枝前后
    lp_path = OUT / "LP剪枝对照.json"
    if lp_path.exists():
        lp = json.loads(lp_path.read_text(encoding="utf-8"))
        labels = ["未剪枝", "支配剪枝"]
        columns = [lp["未剪枝"]["列数_全部"], lp["支配剪枝"]["列数_极大"]]
        seconds = [lp["未剪枝"]["耗时_s"], lp["支配剪枝"]["耗时_s"]]
        fig, axes = plt.subplots(1, 2)
        axes[0].bar(labels, columns, 0.5, color=colors[0])
        axes[0].set(ylabel="集合覆盖LP列数")
        axes[1].bar(labels, seconds, 0.5, color=colors[1])
        axes[1].set(ylabel="LP求解耗时 (s)")
        save(fig, "process_q1_lp_pruning")
        contracts.append(("process_q1_lp_pruning", "支配剪枝把S001的LP列数与耗时降一个数量级以上，下界不变",
                          "LP剪枝对照.json", "双面板柱状"))

    # 结果图：架次数上界与两类下界
    fig, ax = plt.subplots()
    ax.bar(x, [int(r["枚举_架次"]) for r in rows], 0.5, color=colors[0], label="精确最优架次")
    ax.scatter(x, [float(r["LP下界_架次"]) for r in rows], marker="_", s=260, linewidths=2.0,
               color=colors[1], label="集合覆盖LP下界", zorder=3)
    ax.scatter(x, [int(r["解析下界_架次"]) for r in rows], marker="x", s=42,
               color=colors[2], label="质量/体积解析下界", zorder=3)
    handles, labels = ax.get_legend_handles_labels()
    order = [labels.index(name) for name in ("精确最优架次", "集合覆盖LP下界", "质量/体积解析下界")]
    ax.set(xticks=x, xticklabels=short, xlabel="服务区编号后3位", ylabel="架次数 (次)", ylim=(0, 2.5))
    ax.legend([handles[k] for k in order], [labels[k] for k in order], frameon=False, ncol=3, loc="upper center")
    save(fig, "result_q1_method_bounds")
    contracts.append(("result_q1_method_bounds", "两类下界在15个服务区全部闭合到精确最优架次",
                      "方法对比_分区.csv", "柱与标记"))

    # 结果图：贪心与精确解的能耗差
    fig, ax = plt.subplots()
    gap = [(float(r["贪心_能耗_kWh"]) - float(r["枚举_能耗_kWh"])) for r in rows]
    ax.bar(x, gap, 0.55, color=colors[1])
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set(xticks=x, xticklabels=short, xlabel="服务区编号后3位", ylabel="贪心减最优能耗 (kWh)")
    save(fig, "result_q1_method_gap")
    contracts.append(("result_q1_method_gap", "贪心架次数与最优一致，能耗只在S001偏高",
                      "方法对比_分区.csv", "柱状"))

    # 结果图：规模实验
    scale_path = OUT / "规模实验.csv"
    if scale_path.exists():
        scale = read_csv(scale_path)
        n = [int(r["箱数"]) for r in scale]

        def numeric(row, key):
            value = row.get(key, "")
            return float(value) if value not in ("", None) else np.nan

        fig, ax = plt.subplots()
        series = (("候选枚举_耗时_s", "候选枚举_状态", "候选子集枚举", 0),
                  ("DP_耗时_s", "DP_状态", "锚点位掩码 DP", 1),
                  ("MILP_耗时_s", None, "指派MILP", 2),
                  ("贪心_耗时_s", None, "贪心BFD", 3))
        for key, status_key, label, j in series:
            values, timeouts = [], []
            for xi, r in zip(n, scale):
                timed_out = status_key is not None and str(r.get(status_key, "")).startswith("超时")
                values.append(np.nan if timed_out else numeric(r, key))
                if timed_out:
                    timeouts.append(xi)
            ax.plot(n, values, marker="o", markersize=4, color=colors[j], label=label)
            if timeouts:
                ax.scatter(timeouts, [75] * len(timeouts), marker="v", s=45, color=colors[j], clip_on=False)
        ax.set_yscale("log")
        ax.set_ylim(1e-4, 100)
        ax.set(xlabel="服务区货箱数 n", ylabel="耗时 (s, 对数轴)")
        ax.legend(frameon=False, ncol=2, loc="lower right")
        save(fig, "result_q1_method_scale")
        contracts.append(("result_q1_method_scale", "n≥19后枚举与DP触及时限，MILP与贪心仍在秒级",
                          "规模实验.csv", "对数折线"))

    with (OUT / "图表契约.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["图文件前缀", "核心结论", "证据", "图型"])
        writer.writerows(contracts)
    print(f"输出 {len(contracts)} 张图：{FIG}")


if __name__ == "__main__":
    main()
