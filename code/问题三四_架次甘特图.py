"""按无人机架次（每行一架次）绘制问题三、四任务和充电甘特图。"""
from __future__ import annotations

import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from 问题三四_资源甘特图 import (CHARGE, COLORS, F3, F4, Q4, TRANSIT,
                               axis_hours, export, load, q4_group_items)


def segment(ax, row, start, end, color, hatch=None):
    if end <= start:
        return
    ax.barh(row, (end - start) / 3600, left=start / 3600, height=.68,
            facecolor=color, edgecolor="#65717D" if hatch else "white",
            hatch=hatch, linewidth=.30, zorder=3)


def draw_sortie(ax, row, task, relay=False):
    if relay:
        segment(ax, row, task["depart_s"], task["link_ready_s"], TRANSIT)
        segment(ax, row, task["link_ready_s"], task["service_end_s"], COLORS["R"])
        segment(ax, row, task["service_end_s"], task["return_s"], TRANSIT)
        segment(ax, row, task["return_s"], task["energy_free_s"], CHARGE, "///")
        # 小短线标出机身完成周转的时刻；能源组件仍可继续充电。
        ax.plot(task["relay_free_s"] / 3600, row, marker="|", color="#293747",
                markersize=12, markeredgewidth=1.5, zorder=5)
    else:
        segment(ax, row, task["start_s"], task["return_s"], COLORS[task["model"]])
        segment(ax, row, task["return_s"], task["charge_end_s"], CHARGE, "///")


def y_label(task, relay=False, copied=False):
    if relay:
        mark = "※" if copied else " "
        return f"{task['id']}{mark}   {task['relay_id']}   {task['energy_id']}"
    return f"{task['id']}   {task['uav']}   {task['battery']}"


def axes_style(ax, labels, title, xmax, bottom=False):
    ax.set_yticks(range(len(labels)), labels, fontsize=7.5)
    ax.set_ylim(len(labels) - .52, -.55)
    ax.set_xlim(0, xmax)
    ax.set_xticks([i / 2 for i in range(int(xmax * 2) + 1)])
    ax.set_title(title, loc="left", fontsize=10, weight="bold", pad=7)
    ax.grid(axis="x", color="#DCE3E9", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if bottom:
        ax.set_xlabel("任务开始后的时间（小时）", fontsize=9)


def legend(fig):
    handles = [Patch(facecolor=COLORS[m], label=f"{m} 型运输架次") for m in "ABC"]
    handles += [Patch(facecolor=COLORS["R"], label="中继服务"),
                Patch(facecolor=TRANSIT, label="中继往返/建链"),
                Patch(facecolor=CHARGE, hatch="///", edgecolor="#65717D", label="返航后充电")]
    fig.legend(handles=handles, loc="lower center", ncol=3,
               bbox_to_anchor=(.5, -.01), frameon=False, fontsize=8)


def q3_gantt(plan):
    trips = sorted(plan["transport"], key=lambda t: int(t["id"][1:]))
    relays = sorted(plan["relays"], key=lambda r: r["depart_s"])
    xmax = axis_hours(plan)
    fig, axes = plt.subplots(2, 1, figsize=(11.6, 9.6), sharex=True,
                             gridspec_kw={"height_ratios": [22, 3], "hspace": .18})
    fig.suptitle("问题三｜无人机架次甘特图（现有方案，通信待修正）",
                 fontsize=13, weight="bold", y=.99)
    for row, trip in enumerate(trips):
        draw_sortie(axes[0], row, trip)
    axes_style(axes[0], [y_label(t) for t in trips],
               "A  运输架次｜架次编号 · 执行无人机 · 共享电池", xmax)
    for row, relay in enumerate(relays):
        draw_sortie(axes[1], row, relay, relay=True)
    axes_style(axes[1], [y_label(r, relay=True) for r in relays],
               "B  中继架次｜架次编号 · 中继机 · 能源组件（短线为机身周转结束）", xmax, True)
    legend(fig)
    fig.subplots_adjust(left=.205, right=.99, top=.935, bottom=.09)
    export(fig, F3, "result_q3_sortie_charge_gantt")


def q4_gantt(plan, k):
    partition = json.loads((Q4 / f"K{k}_缺口优先.json").read_text(encoding="utf-8"))
    grouped = []
    for areas in partition["任务组"]:
        trips, relays = q4_group_items(plan, areas)
        tasks = sorted([("T", t) for t in trips] + [("R", r) for r in relays],
                       key=lambda x: (x[1]["start_s"] if x[0] == "T" else x[1]["depart_s"],
                                      x[1]["id"]))
        grouped.append((areas, tasks))
    heights = [max(2.1, .32 * len(tasks) + .95) for _, tasks in grouped]
    fig, axes = plt.subplots(k, 1, figsize=(11.6, sum(heights) + 1.4), sharex=True,
                             gridspec_kw={"height_ratios": heights, "hspace": .25})
    fig.suptitle(f"问题四｜K={k} 分组无人机架次甘特图（固定问题三计划，通信待修正）",
                 fontsize=13, weight="bold", y=.995)
    xmax = axis_hours(plan)
    for index, (ax, (areas, tasks)) in enumerate(zip(axes, grouped), 1):
        for row, (kind, task) in enumerate(tasks):
            draw_sortie(ax, row, task, relay=(kind == "R"))
        labels = [y_label(task, relay=(kind == "R"), copied=(kind == "R"))
                  for kind, task in tasks]
        axes_style(ax, labels,
                   f"G{index}  ·  {len(areas)} 个服务区  ·  "
                   f"{sum(kind == 'T' for kind, _ in tasks)} 运输架次  ·  "
                   f"{sum(kind == 'R' for kind, _ in tasks)} 中继架次副本",
                   xmax, bottom=index == k)
    fig.text(.52, .058, "每行一个架次；左列依次为架次、问题三原无人机、所用电池/组件。"
             "“※”表示按任务组独立复制的中继架次；分区后的实体机重新分配尚未给定。",
             ha="center", fontsize=8)
    legend(fig)
    fig.subplots_adjust(left=.205, right=.99, top=.945, bottom=.13)
    export(fig, F4, f"result_q4_k{k}_sortie_charge_gantt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", choices=("q3", "q4", "all"), default="all")
    args = parser.parse_args()
    plan = load()
    if args.question in ("q3", "all"):
        q3_gantt(plan)
    if args.question in ("q4", "all"):
        q4_gantt(plan, 2)
        q4_gantt(plan, 3)


if __name__ == "__main__":
    main()
