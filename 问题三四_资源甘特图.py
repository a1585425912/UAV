"""按真实资源编号及分组资源槽展示运输、中继与充电时序。

图表忠实反映已发布计划；问题三的通信硬约束尚未通过复核。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from utils.plot_style import PALETTE

ROOT = Path(__file__).resolve().parent
SKILL_SCRIPTS = Path.home() / ".codex" / "skills" / "math-modeling" / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from export_figure import export_figure

Q3 = ROOT / "results" / "问题三_参考口径"
Q4 = ROOT / "results" / "问题四_参考口径"
F3 = ROOT / "figures" / "问题三_参考口径"
F4 = ROOT / "figures" / "问题四_参考口径"
COLORS = {"A": PALETTE["primary"], "B": PALETTE["secondary"],
          "C": PALETTE["positive"], "R": PALETTE["accent"]}
CHARGE = "#D8DEE5"
TRANSIT = "#A5AFBA"

plt.rcParams.update({"font.family": "Microsoft YaHei", "axes.unicode_minus": False,
                     "svg.fonttype": "none", "font.size": 8})


def load():
    plan = json.loads((Q3 / "主方案_完整方案.json").read_text(encoding="utf-8"))
    assert len(plan["transport"]) == 22 and len(plan["relays"]) == 3
    return plan


def bar(ax, y, start, end, color, label="", hatch=None, text_color="white"):
    assert end >= start
    if end - start < 1e-8:
        return
    left, width = start / 3600, (end - start) / 3600
    ax.barh(y, width, left=left, height=.70, color=color, hatch=hatch,
            edgecolor="#64717D" if hatch else "white", linewidth=.25, zorder=3)
    if label and width >= .10:
        ax.text(left + width / 2, y, label, va="center", ha="center",
                fontsize=6.7, color=text_color, weight="bold", zorder=4)


def axis_hours(plan):
    latest = max([t["charge_end_s"] for t in plan["transport"]]
                 + [r["energy_free_s"] for r in plan["relays"]]
                 + [r["relay_free_s"] for r in plan["relays"]])
    return math.ceil(latest / 1800) / 2


def decorate(ax, names, title, xmax_h, show_xlabel=False):
    ax.set_yticks(range(len(names)), names, fontsize=7)
    ax.set_ylim(len(names) - .45, -.55)
    ax.set_title(title, fontsize=10, loc="left", pad=7, weight="bold")
    ax.set_xlim(0, xmax_h)
    ax.set_xticks([i / 2 for i in range(int(xmax_h * 2) + 1)])
    ax.grid(axis="x", color="#DCE3E9", lw=.65)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if show_xlabel:
        ax.set_xlabel("任务开始后的时间（小时）", fontsize=9)


def export(fig, folder, stem):
    folder.mkdir(parents=True, exist_ok=True)
    export_figure(fig, basename=str(folder / stem), formats=("svg", "png"),
                  size_inches=fig.get_size_inches(), dpi=320, grayscale_preview=True,
                  tight=True)
    preview = folder / f"{stem}_grayscale.png"
    preview_folder = ROOT / "results" / "figure_previews" / folder.name
    preview_folder.mkdir(parents=True, exist_ok=True)
    preview.replace(preview_folder / preview.name)
    plt.close(fig)


def q3_figure(plan):
    trips, relays = plan["transport"], plan["relays"]
    xmax_h = axis_hours(plan)
    drone_rows = [f"U{i:02d}" for i in range(1, 9)]
    battery_rows = sorted({t["battery"] for t in trips}, key=lambda s: (s[0], int(s.split("B")[-1])))
    relay_rows = ["R01", "R02"]
    energy_rows = sorted({r["energy_id"] for r in relays})
    fig, axes = plt.subplots(4, 1, figsize=(11.4, 11.0), sharex=True,
                             gridspec_kw={"height_ratios": [8, len(battery_rows), 2, 3], "hspace": .28})
    fig.suptitle("问题三｜运输、中继与充电资源时序（现有方案，通信待修正）",
                 fontsize=13, weight="bold", y=.99)

    for y, uid in enumerate(drone_rows):
        for trip in trips:
            if trip["uav"] == uid:
                bar(axes[0], y, trip["start_s"], trip["return_s"], COLORS[trip["model"]], trip["id"])
    decorate(axes[0], drone_rows, "A  运输实体无人机｜条内为架次编号", xmax_h)

    for y, bid in enumerate(battery_rows):
        for trip in trips:
            if trip["battery"] == bid:
                bar(axes[1], y, trip["start_s"], trip["return_s"], COLORS[trip["model"]], trip["id"])
                bar(axes[1], y, trip["return_s"], trip["charge_end_s"], CHARGE, hatch="///")
    decorate(axes[1], battery_rows, "B  共享运输电池｜斜纹为返航后充满时间", xmax_h)

    for y, uid in enumerate(relay_rows):
        for relay in relays:
            if relay["relay_id"] != uid:
                continue
            bar(axes[2], y, relay["depart_s"], relay["link_ready_s"], TRANSIT)
            bar(axes[2], y, relay["link_ready_s"], relay["service_end_s"], COLORS["R"], relay["id"])
            bar(axes[2], y, relay["service_end_s"], relay["return_s"], TRANSIT)
            bar(axes[2], y, relay["return_s"], relay["relay_free_s"], CHARGE, hatch="xx")
    decorate(axes[2], relay_rows, "C  中继实体无人机｜服务段与返航后周转", xmax_h)

    for y, eid in enumerate(energy_rows):
        for relay in relays:
            if relay["energy_id"] == eid:
                bar(axes[3], y, relay["depart_s"], relay["return_s"], COLORS["R"], relay["id"])
                bar(axes[3], y, relay["return_s"], relay["energy_free_s"], CHARGE, hatch="///")
    decorate(axes[3], energy_rows, "D  中继能源组件｜斜纹为返航后充满时间", xmax_h, True)
    handles = [Patch(facecolor=COLORS[m], label=f"{m} 型运输任务") for m in "ABC"]
    handles += [Patch(facecolor=COLORS["R"], label="中继服务/组件占用"),
                Patch(facecolor=TRANSIT, label="中继往返及建链"),
                Patch(facecolor=CHARGE, hatch="///", edgecolor="#64717D", label="充电"),
                Patch(facecolor=CHARGE, hatch="xx", edgecolor="#64717D", label="机身周转")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               bbox_to_anchor=(.5, -.012), fontsize=8)
    fig.subplots_adjust(left=.12, right=.985, top=.94, bottom=.075)
    export(fig, F3, "result_q3_resource_charge_gantt")


def interval_slots(records, interval_end):
    """区间图着色；返回每个任务的组内专用资源槽。"""
    release = []
    assignment = {}
    for key, start, end in sorted(records, key=lambda x: (x[1], x[2], x[0])):
        assert end >= start
        free = next((i for i, t in enumerate(release) if t <= start + 1e-8), None)
        if free is None:
            free = len(release)
            release.append(-1)
        release[free] = end
        assignment[key] = free
    return assignment, len(release)


def q4_group_items(plan, group):
    areas = set(group)
    trips = [t for t in plan["transport"] if any(s["area"] in areas for s in t["stops"])]
    assert all(all(s["area"] in areas for s in t["stops"]) for t in trips)
    trips_by_id = {t["id"] for t in trips}
    relayed = {c["relay_id"] for c in plan["communications"]
               if c["trip"] in trips_by_id and c["relay_id"]}
    relays = [r for r in plan["relays"] if r["id"] in relayed]
    return trips, relays


def group_lanes(trips, relays, need):
    lanes = []
    for model in "ABC":
        members = [t for t in trips if t["model"] == model]
        for kind, suffix, end_key in (("U", "机", "return_s"), ("B", "电池", "charge_end_s")):
            assignment, count = interval_slots(
                [(t["id"], t["start_s"], t[end_key]) for t in members], end_key)
            assert count == need[f"{kind}_{model}"], (kind, model, count, need)
            for slot in range(count):
                lanes.append((f"{model}{suffix}{slot+1}", kind, model,
                              [t for t in members if assignment[t["id"]] == slot]))
    for kind, label, end_key in (("R", "中继机", "relay_free_s"),
                                  ("RB", "中继组件", "energy_free_s")):
        assignment, count = interval_slots(
            [(r["id"], r["depart_s"], r[end_key]) for r in relays], end_key)
        assert count == need[kind], (kind, count, need)
        for slot in range(count):
            lanes.append((f"{label}{slot+1}", kind, "R",
                          [r for r in relays if assignment[r["id"]] == slot]))
    return lanes


def q4_figure(plan, k):
    xmax_h = axis_hours(plan)
    partition = json.loads((Q4 / f"K{k}_缺口优先.json").read_text(encoding="utf-8"))
    groups = []
    for area_group, need in zip(partition["任务组"], partition["资源需求"]):
        trips, relays = q4_group_items(plan, area_group)
        lanes = group_lanes(trips, relays, need)
        assert len(lanes) == sum(need.values())
        groups.append((area_group, trips, relays, lanes))
    heights = [max(2.2, .28 * len(x[3]) + .9) for x in groups]
    fig, axes = plt.subplots(k, 1, figsize=(11.5, sum(heights) + 1.4), sharex=True,
                             gridspec_kw={"height_ratios": heights, "hspace": .24})
    fig.suptitle(f"问题四｜K={k} 组独立资源时序（固定问题三计划，通信待修正）",
                 fontsize=13, weight="bold", y=.995)
    for group_index, (ax, (area_group, trips, relays, lanes)) in enumerate(zip(axes, groups), 1):
        for y, (label, kind, model, items) in enumerate(lanes):
            for task in items:
                if kind == "U":
                    bar(ax, y, task["start_s"], task["return_s"], COLORS[model],
                        f"{task['id']}/{task['uav']}")
                elif kind == "B":
                    bar(ax, y, task["start_s"], task["return_s"], COLORS[model], task["id"])
                    bar(ax, y, task["return_s"], task["charge_end_s"], CHARGE, hatch="///")
                elif kind == "R":
                    bar(ax, y, task["depart_s"], task["link_ready_s"], TRANSIT)
                    bar(ax, y, task["link_ready_s"], task["service_end_s"], COLORS["R"], task["id"])
                    bar(ax, y, task["service_end_s"], task["return_s"], TRANSIT)
                    bar(ax, y, task["return_s"], task["relay_free_s"], CHARGE, hatch="xx")
                else:
                    bar(ax, y, task["depart_s"], task["return_s"], COLORS["R"], task["id"])
                    bar(ax, y, task["return_s"], task["energy_free_s"], CHARGE, hatch="///")
        decorate(ax, [row[0] for row in lanes],
                 f"G{group_index}  ·  {len(area_group)} 个服务区  ·  {len(trips)} 运输架次"
                 f"  ·  {len(relays)} 中继任务副本", xmax_h, group_index == k)
    fig.text(.5, .025, "组内机位为独立资源槽；条内为原架次/原无人机。斜纹为充电，交叉纹为中继机身周转；跨组中继任务独立复制。",
             ha="center", fontsize=8)
    fig.subplots_adjust(left=.125, right=.985, top=.955, bottom=.12)
    export(fig, F4, f"result_q4_k{k}_resource_charge_gantt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", choices=("q3", "q4", "all"), default="all")
    args = parser.parse_args()
    plan = load()
    if args.question in ("q3", "all"):
        q3_figure(plan)
    if args.question in ("q4", "all"):
        q4_figure(plan, 2)
        q4_figure(plan, 3)


if __name__ == "__main__":
    main()
