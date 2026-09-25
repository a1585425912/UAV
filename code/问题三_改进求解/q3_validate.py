# -*- coding: utf-8 -*-
"""问题三正式方案独立校验。

默认校验 ``plan_windows_opt.json``，也可传入任意同结构方案：

    python q3_validate.py [方案.json]

校验覆盖：80 箱唯一覆盖、载荷/SOC/时限、运输与中继物理量、四类资源
半开区间不重叠、通信表连续性与中继服务窗口、PixelIsPoint 连续重认证、
以及全部汇总指标重算。任一检查失败时以非零状态退出。
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(HERE))

from 问题二_调度核心 import evaluate_sortie, load_data  # noqa: E402
from 问题三_通信核心 import Point, relay_sortie  # noqa: E402
from 问题三_全程通信重认证 import PointRasterTerrain  # noqa: E402
from 问题三_联合调度 import evaluate_plan  # noqa: E402
import 问题三_联合调度 as joint  # noqa: E402
import q3_cont_cert  # noqa: E402

DEFAULT_PLAN = HERE / "plan_windows_opt.json"
TOL = 1e-6


def close(a: float, b: float, tol: float = TOL) -> bool:
    return abs(float(a) - float(b)) <= tol


def check_no_overlap(rows, resource_key: str, start_key: str, end_key: str, errors: list[str]) -> None:
    intervals = defaultdict(list)
    for row in rows:
        intervals[row[resource_key]].append((row[start_key], row[end_key], row["id"]))
    for resource, used in intervals.items():
        used.sort()
        for left, right in zip(used, used[1:]):
            if right[0] < left[1] - 1e-8:
                errors.append("资源重叠 %s=%s: %s 与 %s" % (
                    resource_key, resource, left[2], right[2]))


def main(path: Path) -> int:
    plan = json.loads(path.read_text(encoding="utf-8"))
    data = load_data()
    terrain = PointRasterTerrain()
    errors: list[str] = []
    print("方案:", path)
    print("文件指标:", plan.get("metrics"))

    delivery = {}
    seen_boxes = []
    for trip in plan["transport"]:
        ev = evaluate_sortie({"model": trip["model"], "stops": trip["stops"]}, data)
        if ev is None:
            errors.append("运输物理不可行 " + trip["id"])
            continue
        drone = data["drones"][trip["model"]]
        if ev["mass_kg"] > drone["payload"] + 1e-9:
            errors.append("超质量载荷 " + trip["id"])
        if ev["volume_m3"] > drone["volume"] + 1e-9:
            errors.append("超体积载荷 " + trip["id"])
        if ev["return_soc"] < drone["reserve"] - 1e-9:
            errors.append("运输返航 SOC 不足 " + trip["id"])
        for key in ("energy_kwh", "mass_kg", "volume_m3"):
            if not close(ev[key], trip[key]):
                errors.append("%s 不一致 %s" % (key, trip["id"]))
        if not close(trip["return_s"], trip["start_s"] + ev["duration_s"]):
            errors.append("返航时刻不一致 " + trip["id"])
        for box_id, offset in ev["delivery_offsets_s"].items():
            if box_id in delivery:
                errors.append("货箱重复 " + box_id)
            delivery[box_id] = trip["start_s"] + offset
            seen_boxes.append(box_id)

    if len(delivery) != 80 or len(seen_boxes) != 80:
        errors.append("货箱覆盖不是 80 箱")
    if set(delivery) != set(plan["deliveries"]):
        errors.append("运输架次货箱集合与 deliveries 不一致")
    for box_id, value in delivery.items():
        if not close(value, plan["deliveries"][box_id]):
            errors.append("交付时刻不一致 " + box_id)
    hard = sum(max(0.0, delivery[box_id] - box["hard"])
               for box_id, box in data["boxes"].items() if box["hard"] is not None)
    tardy = sum(box["weight"] * max(0.0, delivery[box_id] - box["due"])
                for box_id, box in data["boxes"].items())

    for row in plan["relays"]:
        point = Point(row["lon"], row["lat"], row["hover_alt_m"])
        ground = terrain.elevation(point.lon, point.lat)
        if point.alt - ground > 300 + 1e-6:
            errors.append("中继悬停离地超限 " + row["id"])
        rebuilt = relay_sortie(
            terrain, point, row["depart_s"], row["service_end_s"],
            row["relay_id"], row["energy_id"])
        for key in ("link_ready_s", "return_s", "relay_free_s", "energy_free_s",
                    "energy_kwh", "soc"):
            if not close(rebuilt[key], row[key]):
                errors.append("中继 %s 不一致 %s" % (key, row["id"]))
        if rebuilt["soc"] < 0.2 - 1e-9:
            errors.append("中继返航 SOC 不足 " + row["id"])

    check_no_overlap(plan["transport"], "uav", "start_s", "return_s", errors)
    check_no_overlap(plan["transport"], "battery", "start_s", "charge_end_s", errors)
    check_no_overlap(plan["relays"], "relay_id", "depart_s", "relay_free_s", errors)
    check_no_overlap(plan["relays"], "energy_id", "depart_s", "energy_free_s", errors)

    relay_by_id = {row["id"]: row for row in plan["relays"]}
    comm_by_trip = defaultdict(list)
    for row in plan["communications"]:
        comm_by_trip[row["trip"]].append(row)
        relay_id = row.get("relay_id") or ""
        if relay_id:
            if relay_id not in relay_by_id:
                errors.append("通信表引用未知中继 " + relay_id)
            else:
                relay = relay_by_id[relay_id]
                if (row["start_s"] < relay["link_ready_s"] - 1e-8
                        or row["end_s"] > relay["service_end_s"] + 1e-8):
                    errors.append("通信表超出中继窗口 %s/%s" % (row["trip"], relay_id))
    for trip in plan["transport"]:
        rows = sorted(comm_by_trip[trip["id"]], key=lambda x: (x["start_s"], x["end_s"]))
        if not rows:
            errors.append("通信表缺架次 " + trip["id"])
            continue
        for left, right in zip(rows, rows[1:]):
            if not close(left["end_s"], right["start_s"]):
                errors.append("通信表有空洞 %s %.6f..%.6f" % (
                    trip["id"], left["end_s"], right["start_s"]))

    specs = [{"model": trip["model"], "stops": trip["stops"]} for trip in plan["transport"]]
    starts = [trip["start_s"] for trip in plan["transport"]]
    resources = [{"uav": trip["uav"], "battery": trip["battery"],
                  "charge_end_s": trip["charge_end_s"]} for trip in plan["transport"]]
    previous = joint.Terrain
    joint.Terrain = PointRasterTerrain
    try:
        checked = evaluate_plan(specs, starts, plan["relays"], 0.5, resources)
    finally:
        joint.Terrain = previous
    metrics = checked["metrics"]
    if metrics["communication_gap_s"] > TOL:
        errors.append("PixelIsPoint 连续通信未认证 %.6f s" % metrics["communication_gap_s"])

    # 使用更紧的端点距离上界与自适应细分再次做连续时间认证。
    # 这一步专门拦截窗口二分压到临界点后可能遗漏的亚秒级边界空洞。
    uncertified, certified, continuous_detail = q3_cont_cert.run(
        plan["transport"], plan["relays"], resolution=0.1)
    if uncertified > 1e-8:
        errors.append("严格连续通信仍有 %.6f s 未认证: %s" % (
            uncertified, continuous_detail))

    expected = {
        **metrics,
        "hard_excess_s": hard,
        "weighted_tardiness": tardy,
        "energy_kwh": sum(row["energy_kwh"] for row in plan["transport"] + plan["relays"]),
        "makespan_s": max(row["return_s"] for row in plan["transport"] + plan["relays"]),
        "transport_sorties": len(plan["transport"]),
        "relay_sorties": len(plan["relays"]),
        "boxes": len(delivery),
    }
    for key, value in expected.items():
        if key in plan["metrics"] and not close(plan["metrics"][key], value):
            errors.append("汇总指标不一致 %s: 文件=%s 重算=%s" % (
                key, plan["metrics"][key], value))

    print("通信段:", dict(Counter(row["status"] for row in checked["communications"])))
    print("严格连续认证: 已认证 %.6f s，未认证 %.6f s" % (certified, uncertified))
    print("重算指标:", expected)
    if errors:
        print("FAIL (%d):" % len(errors))
        for item in errors:
            print(" -", item)
        return 1
    print("PASS: 物理、资源、时限、通信与汇总指标全部一致")
    return 0


if __name__ == "__main__":
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PLAN
    raise SystemExit(main(source))
