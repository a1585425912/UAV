"""问题二原始/过程/结果三类图与两张建模流程图。"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

from utils.plot_style import PALETTE

SKILL_SCRIPTS = Path("C:/Users/mika/.codex/skills/math-modeling/tools/figure/scripts")
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "results" / "问题二_参考口径"
OUT = ROOT / "figures" / "问题二_参考口径"
OUT.mkdir(parents=True, exist_ok=True)
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
plt.rcParams["font.family"] = FONT.get_name()
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "none"
BLUE, ORANGE, GREEN, RED, GREY = (PALETTE[k] for k in
                                  ("primary", "secondary", "positive", "contrast", "neutral"))
MODELS = {"A": BLUE, "B": ORANGE, "C": GREEN}


def read(name):
    with (SOURCE / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def label(ax, xlabel=None, ylabel=None, title=None):
    if xlabel:
        ax.set_xlabel(xlabel, fontproperties=FONT, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, fontproperties=FONT, fontsize=9)
    if title:
        ax.set_title(title, fontproperties=FONT, fontsize=11, pad=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)


def finish(fig, name, size=None):
    fig.tight_layout(pad=1.1)
    export_figure(fig, basename=str(OUT / name), formats=("svg", "png"),
                  size_inches=size or fig.get_size_inches(), dpi=320,
                  grayscale_preview=False, tight=True)
    plt.close(fig)


def raw_deadlines():
    boxes = read("原始逐箱输入_剖析.csv")
    counts = Counter(row["硬截止_s"] or "无硬截止" for row in boxes)
    names = ["3600 s", "7200 s", "10800 s", "无硬截止"]
    values = [counts.get(key, 0) for key in ("3600", "7200", "10800", "无硬截止")]
    fig, ax = plt.subplots(figsize=(6.7, 3.8))
    bars = ax.bar(names, values, color=[RED, ORANGE, GREEN, GREY], width=.63)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, value + .6, str(value), ha="center", fontsize=8)
    ax.set_ylim(0, max(values) * 1.17)
    ax.grid(axis="y", color="#dddddd", linewidth=.6)
    label(ax, "逐箱硬截止", "货箱数", "80 箱的硬时限分布")
    finish(fig, "raw_q2_deadlines", (6.7, 3.8))


def raw_mass_volume():
    boxes = read("原始逐箱输入_剖析.csv")
    grouped = defaultdict(list)
    for row in boxes:
        grouped[(row["物资类型"], float(row["质量_kg"]), float(row["体积_m3"]))].append(row)
    fig, ax = plt.subplots(figsize=(6.7, 4.0))
    palette = {"医疗物资": RED, "饮用水": BLUE, "应急食品": ORANGE, "生活卫生用品": GREEN}
    for (kind, mass, volume), members in grouped.items():
        ax.scatter(mass, volume * 1000, s=40 + 12*len(members), color=palette[kind],
                   ec="white", lw=1.2, alpha=.87, label=kind, zorder=3)
        ax.annotate(f"n={len(members)}", (mass, volume*1000), xytext=(0, 12),
                    textcoords="offset points", ha="center", fontsize=8)
    handles, names = ax.get_legend_handles_labels()
    unique = dict(zip(names, handles))
    ax.legend(unique.values(), unique.keys(), prop=FONT, frameon=False, loc="upper left")
    ax.grid(color="#dddddd", linewidth=.6)
    label(ax, "单箱质量（kg）", "单箱体积（L）", "物资类别决定四组质量—体积组合")
    finish(fig, "raw_q2_mass_volume", (6.7, 4.0))


def raw_directed_distance():
    legs = read("有向航段几何参数.csv")
    nodes = ["O01"] + [f"S{i:03d}" for i in range(1,16)]
    lookup = {(r["起点"], r["终点"]): float(r["水平距离（m）"])/1000 for r in legs}
    matrix = np.array([[lookup.get((a,b), np.nan) for b in nodes] for a in nodes])
    fig, ax = plt.subplots(figsize=(7.3, 5.8))
    image = ax.imshow(matrix, cmap="viridis", vmin=0, vmax=np.nanmax(matrix))
    ax.set_xticks(range(16), nodes, rotation=90, fontsize=7)
    ax.set_yticks(range(16), nodes, fontsize=7)
    bar = fig.colorbar(image, ax=ax, shrink=.85, pad=.02)
    bar.set_label("水平距离（km）", fontproperties=FONT, fontsize=8)
    label(ax, "终点", "起点", "16 节点间有向航段距离")
    finish(fig, "raw_q2_directed_distance", (7.3, 5.8))


def process_convergence():
    rows = [r for r in read("搜索收敛记录.csv") if r["方案"] == "完成时间优先"]
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for seed in sorted({int(r["种子"]) for r in rows}):
        selected = [r for r in rows if int(r["种子"]) == seed]
        ax.plot([int(r["迭代"]) for r in selected],
                [float(r["历史最优代价"]) / 1000 for r in selected],
                linewidth=1.35, label=f"种子 {seed}")
    ax.grid(color="#dddddd", linewidth=.6)
    ax.legend(prop=FONT, frameon=False, ncol=2, fontsize=7)
    label(ax, "搜索迭代次数", "历史最好加权代价（千单位）", "完成时间优先搜索的收敛轨迹")
    finish(fig, "process_q2_convergence", (7.0, 4.0))


def process_variability():
    rows = json.loads((SOURCE / "搜索元数据.json").read_text(encoding="utf-8"))["搜索"]
    metrics = read("方案权衡.csv")
    lookup = {r["方案"]: r for r in metrics}
    profiles = ["完成时间优先", "均衡", "能耗优先", "架次优先"]
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for pi, profile in enumerate(profiles):
        seeds = sorted(int(r["seed"]) for r in rows if r["profile"] == profile)
        values = [float(lookup[f"{profile}_种子{seed}"]["makespan_s"])/3600 for seed in seeds]
        offsets = np.linspace(-.14,.14,len(values))
        ax.scatter(np.full(len(values), pi)+offsets, values, s=48,
                   color=[BLUE, GREEN, ORANGE, RED][pi], zorder=3)
        ax.plot([pi-.19, pi+.19], [np.median(values)]*2, color="#222222", lw=1.5)
    ax.set_xticks(range(4), profiles, fontproperties=FONT)
    ax.grid(axis="y", color="#dddddd", linewidth=.6)
    label(ax, "目标权重方案（每组 5 个种子）", "完成时间（h）", "同权重多种子搜索的结果差异")
    finish(fig, "process_q2_seed_variability", (7.0, 4.0))


def process_operator_weights():
    rows = json.loads((SOURCE / "搜索元数据.json").read_text(encoding="utf-8"))["搜索"]
    profiles = ["完成时间优先", "均衡", "能耗优先", "架次优先"]
    names = list(rows[0]["operator_weights"])
    short = {"交换同区货箱":"交换箱", "移动同区货箱":"移动箱", "重排架次":"重排",
             "交换架次":"交换架次", "换机型":"换机型", "反转站序":"反转站序",
             "合并架次":"合并", "拆分架次":"拆分", "移除重插":"移除重插"}
    matrix = np.array([[np.mean([r["operator_weights"][name] for r in rows if r["profile"] == profile])
                        for name in names] for profile in profiles])
    fig, ax = plt.subplots(figsize=(8.5, 3.7))
    image = ax.imshow(matrix, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(names)), [short[name] for name in names], rotation=35,
                  ha="right", fontproperties=FONT, fontsize=8)
    ax.set_yticks(range(4), profiles, fontproperties=FONT, fontsize=8)
    bar = fig.colorbar(image, ax=ax, shrink=.85, pad=.02)
    bar.set_label("最终平均算子权重", fontproperties=FONT, fontsize=8)
    label(ax, title="自适应搜索的算子偏好（5 种子均值）")
    finish(fig, "process_q2_operator_weights", (8.5, 3.7))


def result_uav_gantt():
    rows = read("主方案_逐架次.csv")
    uavs = [f"U{i:02d}" for i in range(1,9)]
    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    for row in rows:
        y = uavs.index(row["无人机编号"])
        start, end = float(row["开始时刻_s"])/3600, float(row["返回O01时刻_s"])/3600
        ax.barh(y, end-start, left=start, height=.57, color=MODELS[row["机型编号"]], ec="white")
        ax.text((start+end)/2, y, row["架次编号"], ha="center", va="center", color="white", fontsize=7)
    ax.set_yticks(range(8), uavs)
    ax.invert_yaxis()
    ax.axvline(1, color=RED, ls="--", lw=1)
    ax.axvline(2, color=GREY, ls="--", lw=1)
    label(ax, "任务开始后的时间（h）", "实体无人机", "主方案：8 架实体无人机的 25 架次安排")
    finish(fig, "result_q2_uav_gantt", (8.2, 4.3))


def result_battery_gantt():
    rows = read("主方案_逐架次.csv")
    batteries = [f"{g}-B{i}" for g, count in (("A",6),("B",4),("C",4)) for i in range(1,count+1)]
    fig, ax = plt.subplots(figsize=(8.2, 6.0))
    for row in rows:
        y = batteries.index(row["电池编号"])
        start = float(row["开始时刻_s"])/3600
        ret = float(row["返回O01时刻_s"])/3600
        full = float(row["电池充满时刻_s"])/3600
        ax.barh(y, ret-start, left=start, height=.58, color=MODELS[row["机型编号"]], ec="white")
        ax.barh(y, full-ret, left=ret, height=.58, color="#bbbbbb", ec="white", hatch="///")
    ax.set_yticks(range(len(batteries)), batteries)
    ax.invert_yaxis()
    ax.axvline(1, color=RED, ls="--", lw=1)
    ax.axvline(2, color=GREY, ls="--", lw=1)
    label(ax, "任务开始后的时间（h）", "同型共享电池", "主方案：电池占用（彩色）与充电（斜线）")
    finish(fig, "result_q2_battery_gantt", (8.2, 6.0))


def result_tradeoff():
    rows = [r for r in read("方案权衡.csv") if r["是否非支配"] == "True"]
    fig, ax = plt.subplots(figsize=(7.0, 4.5))
    for count in sorted({int(r["sorties"]) for r in rows}):
        selected = [r for r in rows if int(r["sorties"]) == count]
        ax.scatter([float(r["makespan_s"])/3600 for r in selected],
                   [float(r["energy_kwh"]) for r in selected], s=55,
                   label=f"{count} 架次", edgecolors="white", linewidth=.7)
    for name, text in (("参考热启动","参考起点"), ("完成时间优先_种子4","最快"), ("架次优先_种子4","最低能耗")):
        r = next((r for r in rows if r["方案"] == name), None)
        if r:
            ax.annotate(text, (float(r["makespan_s"])/3600,float(r["energy_kwh"])),
                        xytext=(5,6), textcoords="offset points", fontproperties=FONT, fontsize=8)
    ax.legend(prop=FONT, frameon=False, ncol=2, fontsize=7)
    ax.grid(color="#dddddd", linewidth=.6)
    label(ax, "完成时间（h）", "运输总能耗（kWh）", "已发现非支配方案的时间—能耗—架次权衡")
    finish(fig, "result_q2_tradeoff", (7.0, 4.5))


def result_hard_margin():
    rows = [r for r in read("主方案_逐箱交付.csv") if r["硬截止时间_s"]]
    rows.sort(key=lambda r: float(r["硬截止时间_s"])-float(r["交付完成时刻_s"]))
    values = [float(r["硬截止时间_s"])-float(r["交付完成时刻_s"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 6.6))
    yy = range(len(rows))
    ax.hlines(yy, 0, values, color="#cccccc", lw=.9)
    ax.scatter(values, list(yy), c=[RED if v < 600 else BLUE for v in values], s=22, zorder=3)
    ax.set_yticks(list(yy), [r["货箱编号"] for r in rows], fontsize=6.5)
    ax.invert_yaxis()
    ax.axvline(0, color=RED, lw=1.2)
    ax.grid(axis="x", color="#dddddd", linewidth=.6)
    label(ax, "硬截止减交付时刻（s）", "31 个硬时限货箱", "全部硬时限货箱均留有正余量")
    finish(fig, "result_q2_hard_margin", (7.2, 6.6))


def flow(name, nodes, arrows, size):
    fig, ax = plt.subplots(figsize=size)
    ax.set_xlim(0,1)
    ax.set_ylim(0,1)
    ax.axis("off")
    for key, item in nodes.items():
        x,y,w,h,kind,text = item
        if kind == "decision":
            patch = Polygon([(x+w/2,y+h),(x+w,y+h/2),(x+w/2,y),(x,y+h/2)],
                            closed=True, facecolor="#e8eef3", edgecolor="#536676", linewidth=1)
        elif kind == "data":
            patch = Polygon([(x+.04*w,y),(x+w,y),(x+.96*w,y+h),(x,y+h)],
                            closed=True, facecolor="#eff3f5", edgecolor="#536676", linewidth=1)
        elif kind == "terminal":
            patch = FancyBboxPatch((x,y),w,h,boxstyle="round,pad=.008,rounding_size=.02",
                                   facecolor="#e3eee9",edgecolor="#536676",linewidth=1)
        else:
            patch = Rectangle((x,y),w,h,facecolor="#edf2f5",edgecolor="#536676",linewidth=1)
        ax.add_patch(patch)
        ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontproperties=FONT,fontsize=8)
    for start,end in arrows:
        a,b=nodes[start],nodes[end]
        sx,sy=a[0]+a[2]/2,a[1]
        ex,ey=b[0]+b[2]/2,b[1]+b[3]
        ax.add_patch(FancyArrowPatch((sx,sy-.008),(ex,ey+.008),arrowstyle="-|>",
                                     mutation_scale=11,color="#536676",linewidth=1))
    finish(fig,name,size)


def flowcharts():
    overall={
        "input":(.31,.84,.38,.105,"terminal","题目、80 箱与设备参数"),
        "geo":(.31,.68,.38,.105,"data","DEM 缓存与 240 航段几何"),
        "q1":(.31,.52,.38,.105,"process","问题一：安全载荷与单点组批"),
        "q2":(.31,.36,.38,.105,"process","问题二：多点路线与资源调度"),
        "check":(.31,.20,.38,.105,"decision","逐箱时限/能量/资源审计"),
        "out":(.31,.04,.38,.105,"terminal","Q1/Q2 结果表与模板"),
    }
    flow("flow_overall_model",overall,list(zip(list(overall)[:-1],list(overall)[1:])),(6.5,6.5))
    q2={
        "input":(.25,.86,.50,.09,"terminal","真实箱号、机型、电池与航段"),
        "seed":(.25,.73,.50,.09,"process","参考访问结构 + 逐箱 MILP 热启动"),
        "physics":(.25,.60,.50,.09,"process","逐段载荷、能耗与交付时刻"),
        "decode":(.25,.47,.50,.09,"process","实体无人机/电池最早可用解码"),
        "search":(.25,.34,.50,.09,"process","自适应移除重插与邻域搜索"),
        "audit":(.25,.21,.50,.09,"decision","独立复算 80 箱与资源区间"),
        "out":(.25,.08,.50,.09,"terminal","主方案、权衡表、Q2 模板"),
    }
    flow("flow_q2_model",q2,list(zip(list(q2)[:-1],list(q2)[1:])),(6.5,7.0))


def main():
    raw_deadlines(); raw_mass_volume(); raw_directed_distance()
    process_convergence(); process_variability(); process_operator_weights()
    result_uav_gantt(); result_battery_gantt(); result_tradeoff(); result_hard_margin()
    flowcharts()
    print("已导出问题二 10 张数据图、2 张流程图（SVG、320 DPI PNG）")


if __name__ == "__main__":
    main()
