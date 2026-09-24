"""把真实运输箱号、DEM 通信区间与中继资源联立解码。"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict

from 问题二_调度核心 import charge_time, evaluate_sortie, load_data
from 问题三_通信核心 import (Point, Terrain, certified_link, load_nodes,
                         load_parameters, relay_sortie)
from 问题三_联合种子 import optimize_seed


SITES = {
    "北": Point(109.19208333333333, 23.06625, 1022.5951538085938),
    "西": Point(109.20208333333333, 23.034583333333334, 709.6645202636719),
    "东": Point(109.28208333333333, 23.024583333333332, 690.7881774902344),
}

ASSIGNMENTS = [
    ("U01", "A-B1"), ("U02", "A-B2"), ("U03", "A-B3"), ("U04", "A-B4"),
    ("U05", "B-B1"), ("U06", "B-B2"), ("U07", "C-B1"), ("U08", "C-B2"),
    ("U03", "A-B5"), ("U06", "B-B3"), ("U05", "B-B4"), ("U02", "A-B6"),
    ("U01", "A-B3"), ("U08", "C-B3"), ("U07", "C-B4"), ("U06", "B-B2"),
    ("U06", "B-B3"), ("U08", "C-B1"), ("U03", "A-B2"), ("U04", "A-B1"),
    ("U07", "C-B2"), ("U05", "B-B1"),
]


def relay_plan(terrain, switch_end=4698.0, east_end=6670.0, north_end=7350.0):
    west = relay_sortie(terrain, SITES["西"], 0, switch_end, "R01", "R-B1")
    east = relay_sortie(terrain, SITES["东"], 0, east_end, "R02", "R-B2")
    north = relay_sortie(terrain, SITES["北"], west["relay_free_s"], north_end, "R01", "R-B3")
    sorties = []
    for sid, place, raw in (("RS01", "西", west), ("RS02", "东", east), ("RS03", "北", north)):
        row = dict(raw)
        row["id"], row["site"] = sid, place
        sorties.append(row)
    assert west["relay_free_s"] <= north["depart_s"] + 1e-9
    assert all(s["soc"] >= .2 - 1e-9 for s in sorties)
    return sorties


def transport_starts(specs, earliest, data):
    """固定真实机与电池，按原先顺序推迟到双资源均可用。"""
    assert len(specs) == len(earliest) == len(ASSIGNMENTS)
    uav_model = {u: g for g, ids in data["uavs"].items() for u in ids}
    uav_free = {u: 0.0 for u in uav_model}
    battery_free = {b: 0.0 for v in data["batteries"].values() for b in v["ids"]}
    starts, resources = [], []
    for spec, desired, (uav, battery) in zip(specs, earliest, ASSIGNMENTS):
        model = spec["model"]
        assert uav_model[uav] == model and battery in data["batteries"][model]["ids"]
        ev = evaluate_sortie(spec, data)
        assert ev is not None
        start = max(float(desired), uav_free[uav], battery_free[battery])
        ret = start + ev["duration_s"]
        charge_end = ret + charge_time(ev["return_soc"], data["batteries"][model]["full_charge_s"])
        uav_free[uav], battery_free[battery] = ret, charge_end
        starts.append(start)
        resources.append({"uav": uav, "battery": battery, "charge_end_s": charge_end})
    return starts, resources


def trajectory(ev, data, nodes):
    """返回架次相对起点的各段连续三维轨迹。"""
    model = data["drones"][ev["model"]]
    t = model["prep"] + len(ev["box_ids"]) * model["load"]
    phases = []
    for leg in ev["legs"]:
        a, b = leg["from"], leg["to"]
        ha = nodes[a].alt + (0 if a == "O01" else 30)
        hb = nodes[b].alt + (0 if b == "O01" else 30)
        cruise = data["legs"][a, b]["cruise"]
        def add(kind, seconds, start, end):
            nonlocal t
            if seconds > 1e-9:
                phases.append({"kind": kind, "from": a, "to": b, "t0": t, "t1": t + seconds,
                               "p0": start, "p1": end})
                t += seconds
        add("爬升", (cruise - ha) / model["climb_speed"],
            Point(nodes[a].lon, nodes[a].lat, ha), Point(nodes[a].lon, nodes[a].lat, cruise))
        add("巡航", data["legs"][a, b]["distance"] / model["speed"],
            Point(nodes[a].lon, nodes[a].lat, cruise), Point(nodes[b].lon, nodes[b].lat, cruise))
        add("下降", (cruise - hb) / model["descent_speed"],
            Point(nodes[b].lon, nodes[b].lat, cruise), Point(nodes[b].lon, nodes[b].lat, hb))
        if b != "O01":
            count = next(len(s["ids"]) for s in ev["stops"] if s["area"] == b)
            duration = model["handoff"] + count * model["extra"]
            hover = Point(nodes[b].lon, nodes[b].lat, hb)
            add("投送", duration, hover, hover)
    assert abs(t - ev["duration_s"]) < 1e-6, (t, ev["duration_s"])
    return phases


def position(phase, relative_t):
    f = (relative_t - phase["t0"]) / (phase["t1"] - phase["t0"])
    a, b = phase["p0"], phase["p1"]
    return Point(a.lon + f * (b.lon - a.lon), a.lat + f * (b.lat - a.lat),
                 a.alt + f * (b.alt - a.alt))


def certified_intervals(phases, start_s, relays, terrain, params, nodes, resolution=.5):
    hub = nodes["O01"]
    gateway = Point(hub.lon, hub.lat, hub.alt + params["gateway_height"])
    chunks = []
    for phase in phases:
        edges = [phase["t0"], phase["t1"]]
        for relay in relays:
            for absolute in (relay["link_ready_s"], relay["service_end_s"]):
                local = absolute - start_s
                if phase["t0"] < local < phase["t1"]:
                    edges.append(local)
        edges = sorted(set(edges))
        for left, right in zip(edges, edges[1:]):
            active = [r for r in relays if r["link_ready_s"] <= start_s + left + 1e-8
                      and start_s + right <= r["service_end_s"] + 1e-8]
            def certify(a, b):
                p0, p1 = position(phase, a), position(phase, b)
                ok, _ = certified_link(terrain, params, p0, p1, gateway, params["limit_direct"])
                if ok:
                    chunks.append((start_s + a, start_s + b, "直连", "", phase["kind"]))
                    return
                for relay in active:
                    target = Point(relay["lon"], relay["lat"], relay["hover_alt_m"])
                    ok, _ = certified_link(terrain, params, p0, p1, target, params["limit_access"])
                    if ok:
                        chunks.append((start_s + a, start_s + b, "中继", relay["id"], phase["kind"]))
                        return
                if b - a <= resolution + 1e-8:
                    chunks.append((start_s + a, start_s + b, "未证实", "", phase["kind"]))
                    return
                mid = (a + b) / 2
                certify(a, mid)
                certify(mid, b)
            certify(left, right)
    merged = []
    for a, b, status, relay_id, phase_kind in chunks:
        if merged and merged[-1][2:] == (status, relay_id, phase_kind) and abs(merged[-1][1] - a) < 1e-6:
            merged[-1] = (merged[-1][0], b, status, relay_id, phase_kind)
        else:
            merged.append((a, b, status, relay_id, phase_kind))
    return merged


def evaluate_plan(specs, starts, relays, resolution=.5, resources=None):
    data, terrain, params, nodes = load_data(), Terrain(), load_parameters(), load_nodes()
    assert len(specs) == len(starts)
    backhaul = {}
    hub = nodes["O01"]
    gateway = Point(hub.lon, hub.lat, hub.alt + params["gateway_height"])
    for relay in relays:
        p = Point(relay["lon"], relay["lat"], relay["hover_alt_m"])
        backhaul[relay["id"]] = certified_link(terrain, params, p, p, gateway,
                                                params["limit_backhaul"])[0]
    assert all(backhaul.values())
    uav_intervals, battery_intervals = defaultdict(list), defaultdict(list)
    transport, delivery, communications = [], {}, []
    total_gap = 0.0
    for index, (spec, start) in enumerate(zip(specs, starts), 1):
        ev = evaluate_sortie(spec, data)
        if ev is None:
            raise ValueError(f"T{index:02d} 物理不可行")
        phases = trajectory(ev, data, nodes)
        coverage = certified_intervals(phases, start, relays, terrain, params, nodes, resolution)
        gaps = [(a, b) for a, b, status, _, _ in coverage if status == "未证实"]
        total_gap += sum(b - a for a, b in gaps)
        transport.append({"id": f"T{index:02d}", "model": spec["model"], "start_s": start,
                          "return_s": start + ev["duration_s"], "energy_kwh": ev["energy_kwh"],
                          "soc": ev["return_soc"], "stops": ev["stops"], "mass_kg": ev["mass_kg"],
                          "volume_m3": ev["volume_m3"], "gaps": gaps})
        delivery.update({bid: start + offset for bid, offset in ev["delivery_offsets_s"].items()})
        communications.extend({"trip": f"T{index:02d}", "start_s": a, "end_s": b,
                               "status": state, "relay_id": rid, "phase": kind}
                              for a, b, state, rid, kind in coverage)
    hard_over = sum(max(0, delivery[bid] - box["hard"]) for bid, box in data["boxes"].items()
                    if box["hard"] is not None)
    weighted = sum(box["weight"] * max(0, delivery[bid] - box["due"])
                   for bid, box in data["boxes"].items())
    if resources is not None:
        assert len(resources) == len(transport)
        for row, assignment in zip(transport, resources):
            row.update(assignment)
        for key, end_key in (("uav", "return_s"), ("battery", "charge_end_s")):
            intervals = defaultdict(list)
            for row in transport:
                intervals[row[key]].append((row["start_s"], row[end_key]))
            for used in intervals.values():
                ordered = sorted(used)
                assert all(a[1] <= b[0] + 1e-8 for a, b in zip(ordered, ordered[1:]))
    return {"transport": transport, "relays": relays, "deliveries": delivery,
            "communications": communications,
            "metrics": {"communication_gap_s": total_gap, "hard_excess_s": hard_over,
                        "weighted_tardiness": weighted,
                        "makespan_s": max([r["return_s"] for r in transport + relays]),
                        "energy_kwh": sum(r["energy_kwh"] for r in transport + relays),
                        "transport_sorties": len(transport), "relay_sorties": len(relays),
                        "boxes": len(delivery)}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", type=float, default=2.0)
    args = parser.parse_args()
    data = load_data()
    specs, _, info = optimize_seed(data)
    relay = relay_plan(Terrain())
    from 问题三_联合种子 import REFERENCE_STARTS
    starts, resources = transport_starts(specs, REFERENCE_STARTS, data)
    result = evaluate_plan(specs, starts, relay, args.resolution, resources)
    print("MILP", info, "指标", result["metrics"])
    print("调整开工", [(i+1, round(a, 3), round(b, 3)) for i, (a, b) in enumerate(zip(REFERENCE_STARTS, starts)) if b-a > 1e-6])
    print("逐架次缺口", [(r["id"], sum(b-a for a,b in r["gaps"])) for r in result["transport"] if r["gaps"]])


if __name__ == "__main__":
    main()
