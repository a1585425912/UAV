"""由问题三、四的真实 CSV/JSON 生成三类结果图与方法流程图。"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

from utils.plot_style import PALETTE
from 问题三_通信核心 import Point, Terrain, certified_link, load_nodes, load_parameters
from 问题三_联合调度 import SITES
from 问题四_分区求解 import CATEGORIES, STOCK, assess, prepare


SKILL_SCRIPTS = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure

ROOT = Path(__file__).resolve().parent
Q3 = ROOT / "results" / "问题三_参考口径"
Q4 = ROOT / "results" / "问题四_参考口径"
F3 = ROOT / "figures" / "问题三_参考口径"
F4 = ROOT / "figures" / "问题四_参考口径"
F3.mkdir(parents=True, exist_ok=True)
F4.mkdir(parents=True, exist_ok=True)
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
plt.rcParams["font.family"] = FONT.get_name()
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "none"
BLUE, ORANGE, GREEN, RED, GREY = (PALETTE[k] for k in
                                  ("primary", "secondary", "positive", "contrast", "neutral"))
PURPLE = "#8B5FBF"
MODEL_COLOR = {"A": BLUE, "B": ORANGE, "C": GREEN}
RELAY_COLOR = {"RS01": ORANGE, "RS02": BLUE, "RS03": PURPLE}


def data_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def finish(fig, root, name):
    fig.tight_layout(pad=1.15)
    export_figure(fig, basename=str(root / name), formats=("svg", "png"),
                  size_inches=fig.get_size_inches(), dpi=320,
                  grayscale_preview=False, tight=True)
    svg = root / f"{name}.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())
                   + "\n", encoding="utf-8")
    plt.close(fig)


def style(ax, title, xlabel="", ylabel=""):
    ax.set_title(title, fontsize=11, pad=9)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.22)


def q3_raw_nodes():
    terrain, params, nodes = Terrain(), load_parameters(), load_nodes()
    hub = nodes["O01"]
    gateway = Point(hub.lon, hub.lat, hub.alt + params["gateway_height"])
    fig, ax = plt.subplots(figsize=(7.3, 5.3))
    for name, point in nodes.items():
        if name == "O01":
            ax.scatter(point.lon, point.lat, marker="*", s=170, c=RED, zorder=4)
            ax.annotate(name, (point.lon, point.lat), xytext=(4, -3), textcoords="offset points", fontsize=8)
            continue
        hover = Point(point.lon, point.lat, point.alt + 30)
        direct = certified_link(terrain, params, hover, hover, gateway, params["limit_direct"])[0]
        ax.scatter(point.lon, point.lat, marker="o" if direct else "s", s=55,
                   c=GREEN if direct else BLUE, zorder=3)
        ax.annotate(name, (point.lon, point.lat), xytext=(4, 3), textcoords="offset points", fontsize=7)
    for name, p in SITES.items():
        ax.scatter(p.lon, p.lat, marker="^", s=105, facecolor=ORANGE, edgecolor="black", zorder=5)
        ax.annotate(name, (p.lon, p.lat), xytext=(-3, 8), textcoords="offset points", fontsize=9)
    ax.scatter([], [], marker="o", c=GREEN, label="站点直连可用")
    ax.scatter([], [], marker="s", c=BLUE, label="站点需中继")
    ax.scatter([], [], marker="^", c=ORANGE, label="选定中继点")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    style(ax, "原始站点静态链路与中继候选位置", "经度 (°E)", "纬度 (°N)")
    ax.set_aspect(1 / np.cos(np.deg2rad(23.05)))
    finish(fig, F3, "raw_q3_direct_nodes")


def q3_raw_candidate():
    rows = data_csv(Q3 / "候选悬停点覆盖.csv")
    count = Counter(len(x["覆盖服务区"].split("、")) for x in rows)
    xs = sorted(count)
    fig, ax = plt.subplots(figsize=(6.2, 3.7))
    ax.bar(xs, [count[x] for x in xs], color=BLUE, width=.7)
    style(ax, "3102 个可用候选点的静态覆盖范围", "可覆盖需中继服务区数", "候选点数")
    ax.set_xticks(xs)
    ax.set_ylim(bottom=0)
    finish(fig, F3, "raw_q3_candidate_coverage")


def q3_raw_energy():
    rows = data_csv(Q3 / "主方案_运输架次.csv")
    fig, ax = plt.subplots(figsize=(5.8, 3.8))
    for i, model in enumerate("ABC"):
        values = [float(r["架次能耗_kWh"]) for r in rows if r["机型编号"] == model]
        x = i + np.linspace(-.12, .12, len(values))
        ax.scatter(x, values, color=MODEL_COLOR[model], s=35, label=f"{model}：n={len(values)}")
    ax.set_xticks(range(3), ["A", "B", "C"])
    ax.legend(frameon=False, fontsize=8)
    style(ax, "各机型单架次能耗原始点", "运输机型", "架次能耗 (kWh)")
    finish(fig, F3, "raw_q3_transport_energy")


def q3_process_sites():
    rows = data_csv(Q3 / "候选悬停点覆盖.csv")
    selected = []
    for name, p in SITES.items():
        selected.append((name, next(r for r in rows if abs(float(r["经度"]) - p.lon) < 1e-8
                                    and abs(float(r["纬度"]) - p.lat) < 1e-8)))
    areas = [f"S{i:03d}" for i in (2, 3, 4, 5, 7, 8, 9, 10, 12, 13, 14, 15)]
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    for y, (name, site) in enumerate(selected):
        covered = set(site["覆盖服务区"].split("、"))
        for x, area in enumerate(areas):
            ax.add_patch(Rectangle((x-.47, y-.4), .94, .8,
                                   facecolor=BLUE if area in covered else "#EDF1F4",
                                   edgecolor="white"))
    ax.set_xlim(-.5, len(areas)-.5); ax.set_ylim(-.5, 2.5)
    ax.set_xticks(range(len(areas)), areas, rotation=50, ha="right")
    ax.set_yticks(range(3), [s[0] for s in selected])
    style(ax, "三个悬停位置的站点覆盖互补性", "需中继服务区", "悬停点")
    finish(fig, F3, "process_q3_site_selection")


def q3_process_windows():
    rows = data_csv(Q3 / "主方案_中继架次.csv")
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    for y, r in enumerate(rows):
        start, ready, end, ret = (float(r[k]) / 3600 for k in
                                   ("开始时刻_s", "建链完成时刻_s", "服务结束时刻_s", "返回O01时刻_s"))
        ax.barh(y, ready-start, left=start, height=.55, color="#BCC5CC")
        ax.barh(y, end-ready, left=ready, height=.55, color=RELAY_COLOR[r["中继架次编号"]])
        ax.barh(y, ret-end, left=end, height=.55, color="#BCC5CC")
        ax.text((ready+end)/2, y, r["中继架次编号"], ha="center", va="center", fontsize=8, color="white")
    ax.set_yticks(range(3), [r["中继无人机编号"]+" / "+r["中继架次编号"] for r in rows])
    ax.invert_yaxis(); ax.set_xlim(left=0)
    style(ax, "西→北换位与东侧中继服务窗口", "任务开始后的时间 (h)", "实体中继机")
    finish(fig, F3, "process_q3_windows")


def q3_process_certificate():
    rows = data_csv(Q3 / "主方案_通信保障.csv")
    stages = ["爬升", "巡航", "下降", "投送"]
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    direct = [sum((float(r["结束时刻_s"])-float(r["开始时刻_s"])) for r in rows
                  if r["通信阶段"] == phase and r["保障方式"] == "直连") / 3600 for phase in stages]
    relay = [sum((float(r["结束时刻_s"])-float(r["开始时刻_s"])) for r in rows
                 if r["通信阶段"] == phase and r["保障方式"] == "中继") / 3600 for phase in stages]
    ax.bar(stages, direct, color=GREEN, label="直连证书")
    ax.bar(stages, relay, bottom=direct, color=BLUE, label="中继证书")
    ax.legend(frameon=False, fontsize=8)
    style(ax, "各飞行阶段均有完整通信保障", "运输阶段", "所有架次累计时长 (h)")
    finish(fig, F3, "process_q3_certificate")


def q3_result_gantt():
    trips = data_csv(Q3 / "主方案_运输架次.csv")
    relays = data_csv(Q3 / "主方案_中继架次.csv")
    fig, ax = plt.subplots(figsize=(8.6, 7.2))
    for y, r in enumerate(trips):
        a, b = float(r["开始时刻_s"])/3600, float(r["返回O01时刻_s"])/3600
        ax.barh(y, b-a, left=a, height=.7, color=MODEL_COLOR[r["机型编号"]])
    for j, r in enumerate(relays, len(trips)):
        a, b = float(r["开始时刻_s"])/3600, float(r["返回O01时刻_s"])/3600
        ax.barh(j, b-a, left=a, height=.7, color=PURPLE)
    ax.set_yticks(range(25), [r["架次编号"] for r in trips]+[r["中继架次编号"] for r in relays], fontsize=7)
    ax.invert_yaxis(); ax.set_xlim(left=0)
    style(ax, "运输与中继联合调度：最后由 RS03 返航", "任务开始后的时间 (h)", "架次")
    finish(fig, F3, "result_q3_joint_gantt")


def q3_result_coverage():
    rows = data_csv(Q3 / "主方案_通信保障.csv")
    fig, ax = plt.subplots(figsize=(8.4, 5.8))
    trips = [f"T{i:02d}" for i in range(1, 23)]
    for y, trip in enumerate(trips):
        for r in rows:
            if r["运输架次编号"] != trip:
                continue
            a, b = float(r["开始时刻_s"])/3600, float(r["结束时刻_s"])/3600
            color = GREEN if r["保障方式"] == "直连" else RELAY_COLOR[r["中继架次编号"]]
            ax.barh(y, b-a, left=a, color=color, height=.7, linewidth=0)
    ax.set_yticks(range(22), trips, fontsize=7); ax.invert_yaxis()
    ax.scatter([], [], c=GREEN, label="直连")
    for rid in RELAY_COLOR:
        ax.scatter([], [], c=RELAY_COLOR[rid], label=rid)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="lower right")
    style(ax, "22 个运输架次的逐段通信证书", "任务开始后的时间 (h)", "运输架次")
    finish(fig, F3, "result_q3_coverage")


def q3_result_deadlines():
    rows = data_csv(Q3 / "主方案_逐箱交付.csv")
    hard = sorted([(float(r["硬截止_s"]) - float(r["交付完成时刻_s"]), r["货箱编号"])
                   for r in rows if r["硬截止_s"]], key=lambda x: x[0])
    fig, ax = plt.subplots(figsize=(7.0, 6.3))
    ys = np.arange(len(hard))
    ax.scatter([x[0] for x in hard], ys, c=[ORANGE if i < 3 else BLUE for i in ys], s=26)
    ax.axvline(0, color=RED, linewidth=1)
    ax.set_yticks(ys, [x[1] for x in hard], fontsize=6)
    ax.invert_yaxis()
    style(ax, "31 个硬时限货箱均有正余量", "截止时刻 − 交付时刻 (s)", "货箱编号")
    finish(fig, F3, "result_q3_deadlines")


def q4_raw_components(comp):
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    xs = np.arange(1, len(comp)+1)
    sizes = [len(c) for c in comp]
    ax.scatter(xs, sizes, s=85, color=BLUE)
    for x, size, group in zip(xs, sizes, comp):
        ax.annotate("、".join(group), (x, size), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=6, rotation=25)
    ax.set_xticks(xs, [f"C{i}" for i in xs]); ax.set_ylim(0, max(sizes)+1.2)
    style(ax, "15 区由多站架次连成 7 个不可分单元", "不可分单元", "服务区数")
    finish(fig, F4, "raw_q4_components")


def q4_raw_inventory():
    names = ["A机", "B机", "C机", "A电池", "B电池", "C电池", "中继机", "能源组件"]
    fig, ax = plt.subplots(figsize=(6.1, 3.7))
    ax.barh(names, list(STOCK.values()), color=BLUE)
    ax.invert_yaxis(); ax.set_xlim(left=0)
    style(ax, "现有八类设备与能源库存", "库存数量 (架/组)", "资源类别")
    finish(fig, F4, "raw_q4_inventory")


def q4_raw_unpartitioned(prepared):
    need = assess([tuple(range(len(prepared[0])))], prepared)["total"]
    xs = np.arange(len(CATEGORIES))
    fig, ax = plt.subplots(figsize=(7.0, 3.7))
    ax.bar(xs, [need[k] for k in CATEGORIES], color=GREEN, width=.6, label="未分区需求")
    ax.scatter(xs, [STOCK[k] for k in CATEGORIES], color=RED, marker="_", s=230, label="库存")
    ax.set_xticks(xs, ["A机", "B机", "C机", "A电", "B电", "C电", "中继机", "组件"])
    ax.legend(frameon=False, fontsize=8)
    style(ax, "未分区时全部资源峰值不超库存", "资源类别", "峰值数量 (架/组)")
    finish(fig, F4, "raw_q4_unpartitioned")


def q4_process_tradeoff(plans):
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for p in plans:
        color = BLUE if p["K"] == 2 else ORANGE
        marker = "o" if p["方案"] == "缺口优先" else "s"
        ax.scatter(p["作业量CV"], p["缺口总数"], s=95, color=color, marker=marker)
        ax.annotate(f"K={p['K']} {p['方案']}", (p["作业量CV"], p["缺口总数"]),
                    xytext=(6, 3), textcoords="offset points", fontsize=7)
    style(ax, "资源缺口与组间工作量均衡的权衡", "工作量 CV（越低越均衡）", "资源缺口总数 (架/组)")
    ax.set_ylim(bottom=0)
    finish(fig, F4, "process_q4_shortfall_cv")


def q4_process_workload(primary):
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4), sharey=True)
    for ax, p in zip(axes, primary):
        values = np.array(p["各组运输作业量_s"]) / 3600
        ax.bar(range(len(values)), values, color=[BLUE, ORANGE, GREEN][:len(values)])
        ax.set_xticks(range(len(values)), [f"组{i+1}" for i in range(len(values))])
        ax.set_title(f"K={p['K']}，CV={p['作业量CV']:.3f}", fontsize=10)
        ax.set_xlabel("任务组", fontsize=8)
    style(axes[0], "缺口最小方案的工作量集中", "任务组", "组内运输作业量 (h)")
    finish(fig, F4, "process_q4_workload")


def q4_process_relay(plans, q3):
    use = defaultdict(set)
    areas = {t["id"]: {s["area"] for s in t["stops"]} for t in q3["transport"]}
    for row in q3["communications"]:
        if row["relay_id"]:
            use[row["relay_id"]].update(areas[row["trip"]])
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.5))
    for ax, p in zip(axes, plans):
        for yi, group in enumerate(p["任务组"]):
            for xi, rid in enumerate(("RS01", "RS02", "RS03")):
                active = bool(set(group) & use[rid])
                ax.add_patch(Rectangle((xi-.45, yi-.4), .9, .8,
                                       color=BLUE if active else "#EDF1F4", ec="white"))
        ax.set_xlim(-.5, 2.5); ax.set_ylim(-.5, p["K"]-.5)
        ax.set_xticks(range(3), ["RS01", "RS02", "RS03"])
        ax.set_yticks(range(p["K"]), [f"组{i+1}" for i in range(p["K"])])
        ax.set_title(f"K={p['K']}", fontsize=10)
    style(axes[0], "独立分组使部分中继架次需要复制", "中继架次", "任务组")
    finish(fig, F4, "process_q4_relay_duplication")


def q4_result_resources(p, name):
    xs = np.arange(len(CATEGORIES))
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    demand = [p["资源总需求"][k] for k in CATEGORIES]
    ax.bar(xs, demand, color=[RED if demand[i] > STOCK[k] else BLUE for i, k in enumerate(CATEGORIES)], width=.62)
    ax.scatter(xs, [STOCK[k] for k in CATEGORIES], color="black", marker="_", s=260, label="现有库存")
    ax.set_xticks(xs, ["A机", "B机", "C机", "A电", "B电", "C电", "中继机", "组件"])
    ax.legend(frameon=False, fontsize=8)
    style(ax, f"K={p['K']} 缺口最小分区：总缺口 {p['缺口总数']}", "资源类别", "各组独立需求合计 (架/组)")
    finish(fig, F4, name)


def q4_result_map(primary):
    nodes = load_nodes()
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 4.0), sharex=True, sharey=True)
    colors = [BLUE, ORANGE, GREEN]
    for ax, p in zip(axes, primary):
        style(ax, f"K={p['K']}：{p['缺口总数']} 项缺口", "经度 (°E)", "纬度 (°N)")
        lookup = {a: i for i, group in enumerate(p["任务组"]) for a in group}
        for area, node in nodes.items():
            if area == "O01":
                ax.scatter(node.lon, node.lat, marker="*", color=RED, s=140)
                continue
            ax.scatter(node.lon, node.lat, color=colors[lookup[area]], s=42)
            ax.annotate(area, (node.lon, node.lat), xytext=(3, 3), textcoords="offset points", fontsize=6)
        ax.set_aspect(1/np.cos(np.deg2rad(23.05)))
        handles = [Line2D([0], [0], marker="o", linestyle="", color=color,
                          label=f"G{i+1}") for i, color in enumerate(colors[:p["K"]])]
        handles.append(Line2D([0], [0], marker="*", linestyle="", color=RED, label="O01"))
        ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.20),
                  ncol=p["K"]+1, fontsize=7, frameon=False)
    fig.suptitle("任务组空间分布与不可分路线约束", fontsize=11)
    fig.subplots_adjust(bottom=0.22)
    finish(fig, F4, "result_q4_partition_map")


def flow(root, name, labels, title):
    fig, ax = plt.subplots(figsize=(6.5, max(4.6, len(labels)*.78+1)))
    ax.set_xlim(0, 10); ax.set_ylim(0, len(labels)*1.2+1)
    for i, wording in enumerate(labels):
        y = len(labels)*1.2 - i*1.2
        patch = FancyBboxPatch((1.7, y-.42), 6.6, .84, boxstyle="round,pad=.06,rounding_size=.08",
                               facecolor="#EAF2F7", edgecolor="#60788B", linewidth=1)
        ax.add_patch(patch)
        ax.text(5, y, wording, ha="center", va="center", fontsize=9)
        if i < len(labels)-1:
            ax.add_patch(FancyArrowPatch((5, y-.45), (5, y-.73), arrowstyle="-|>",
                                         mutation_scale=13, color="#60788B"))
    ax.set_title(title, fontsize=11)
    ax.axis("off")
    finish(fig, root, name)


def main():
    q3 = json.loads((Q3 / "主方案_完整方案.json").read_text(encoding="utf-8"))
    prepared = prepare(q3)
    plans = [json.loads((Q4 / f"K{k}_{name}.json").read_text(encoding="utf-8"))
             for k in (2, 3) for name in ("缺口优先", "兼顾均衡")]
    primary = [p for p in plans if p["方案"] == "缺口优先"]
    q3_raw_nodes(); q3_raw_candidate(); q3_raw_energy()
    q3_process_sites(); q3_process_windows(); q3_process_certificate()
    q3_result_gantt(); q3_result_coverage(); q3_result_deadlines()
    q4_raw_components(prepared[0]); q4_raw_inventory(); q4_raw_unpartitioned(prepared)
    q4_process_tradeoff(plans); q4_process_workload(primary); q4_process_relay(primary, q3)
    q4_result_resources(primary[0], "result_q4_k2_resources")
    q4_result_resources(primary[1], "result_q4_k3_resources")
    q4_result_map(primary)
    flow(F3, "flow_overall_model", ["问题一、二：真实货箱与运输物理", "问题三：原始 DEM 与双向链路",
                                     "候选点 → 联合排程 → 区间证书", "问题四：固定问题三计划进行分区",
                                     "独立审计与 Q3/Q4 提交模板"], "问题一至四的结果继承")
    flow(F3, "flow_q3_model", ["原始 DEM / 通信参数 / 80 箱", "链路证书筛选中继候选点",
                                "MILP 箱号指派与资源排程", "西→北 / 东侧中继窗口", "逐段连续通信证书",
                                "硬时限、SOC、占用独立复算"], "问题三求解与检验")
    flow(F4, "flow_overall_model", ["问题三联合调度已固定", "多站架次构造不可分单元",
                                     "各资源占用区间与库存", "K=2/3 整数规划及缺口核算",
                                     "逐组资源表与模板审计"], "问题四结果继承")
    flow(F4, "flow_q4_model", ["读入问题三全部运输与中继架次", "同一架次服务区并入连通单元",
                                "区间峰值形成资源约束", "先缺口、再规模、后 CV 的 MILP",
                                "独立复算与 K=2/3 方案导出"], "问题四分区求解")
    print("问题三、四各生成 9 张数据图和 2 张流程图。")


if __name__ == "__main__":
    main()
