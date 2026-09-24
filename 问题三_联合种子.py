"""从参考 PDF 第 28–30 页的 22 架次访问结构构造逐箱可检验的搜索起点。

参考材料仅给各站箱数，没有给箱号；箱号按原始逐箱时限排序重新指派。
此模块只提供启发式起点，最终结果由物理/资源解码和搜索独立确认。
"""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from 问题二_调度核心 import decode, evaluate_sortie, segment

# 每项为 (机型, (服务区, 本站箱数), ...)，只借用参考架次访问结构。
TEMPLATE = [
    ("A", ("S002", 2)),
    ("A", ("S014", 2)),
    ("A", ("S001", 3)),
    ("A", ("S006", 2), ("S015", 1)),
    ("B", ("S012", 3)),
    ("B", ("S010", 3)),
    ("C", ("S006", 4), ("S007", 4)),
    ("C", ("S001", 1), ("S002", 6)),
    ("A", ("S001", 2)),
    ("B", ("S013", 3)),
    ("B", ("S001", 2)),
    ("A", ("S001", 1), ("S014", 1)),
    ("A", ("S003", 2)),
    ("C", ("S001", 4), ("S008", 2)),
    ("C", ("S007", 1), ("S003", 6)),
    ("B", ("S008", 3)),
    ("B", ("S009", 3)),
    ("C", ("S011", 3), ("S004", 2)),
    ("A", ("S004", 2)),
    ("A", ("S004", 2)),
    ("C", ("S005", 6), ("S001", 2)),
    ("B", ("S015", 2)),
]

# 参考 PDF 的开始时刻只用于固定访问结构中辨别可分配的硬时限槽位；
# 实际资源和开始时刻始终由解码器重新计算。
REFERENCE_STARTS = (0, 0, 0, 0, 0, 0, 0, 0, 1311, 1555, 1923, 1990,
                    2176, 2434, 2480, 3066, 5028, 5259, 5612, 5612, 5652, 5899)


def make_seed(data):
    boxes = data["boxes"]
    available = defaultdict(list)
    for bid, box in boxes.items():
        available[box["area"]].append(bid)
    for area, ids in available.items():
        ids.sort(key=lambda bid: (boxes[bid]["hard"] if boxes[bid]["hard"] is not None else float("inf"),
                                  boxes[bid]["due"], -boxes[bid]["weight"], -boxes[bid]["mass"], bid))
    specs = []
    for entry in TEMPLATE:
        model, *stops = entry
        chosen = []
        for area, count in stops:
            ids = available[area][:count]
            assert len(ids) == count
            del available[area][:count]
            chosen.append({"area": area, "ids": ids})
        specs.append({"model": model, "stops": chosen})
    assert all(not ids for ids in available.values())
    assert sum(len(stop["ids"]) for spec in specs for stop in spec["stops"]) == 80
    return specs


def optimize_seed(data, time_limit=120):
    """固定参考访问结构，以逐箱 MILP+能耗切平面求可行箱号指派。"""
    boxes, drones = data["boxes"], data["drones"]
    slots, arcs, return_energy = [], [], {}
    for ti, entry in enumerate(TEMPLATE):
        model, *stops = entry
        drone = drones[model]
        elapsed = drone["prep"] + sum(count for _, count in stops) * drone["load"]
        prev = "O01"
        for si, (area, count) in enumerate(stops):
            _, flight = segment(model, prev, area, 0.0, data)
            elapsed += flight + drone["handoff"] + count * drone["extra"]
            slots.append({"trip": ti, "order": si, "area": area, "count": count,
                          "delivery_if_reference_s": REFERENCE_STARTS[ti] + elapsed})
            arcs.append((ti, si, model, prev, area))
            prev = area
        return_energy[ti] = segment(model, prev, "O01", 0.0, data)[0]
    choices = []
    for bid, box in boxes.items():
        for slot_id, slot in enumerate(slots):
            if slot["area"] != box["area"]:
                continue
            if box["hard"] is not None and slot["delivery_if_reference_s"] > box["hard"] + 1e-6:
                continue
            choices.append((bid, slot_id))
    by_box = defaultdict(list)
    by_slot = defaultdict(list)
    by_trip = defaultdict(list)
    for col, (bid, slot_id) in enumerate(choices):
        by_box[bid].append(col)
        by_slot[slot_id].append(col)
        by_trip[slots[slot_id]["trip"]].append(col)
    assert len(by_box) == len(boxes) and len(by_slot) == len(slots)
    nx = len(choices)
    nz = len(arcs)
    lower = np.zeros(nx + nz)
    upper = np.r_[np.ones(nx), [drones[model]["battery_kwh"] for _, _, model, _, _ in arcs]]
    integrality = np.r_[np.ones(nx, dtype=int), np.zeros(nz, dtype=int)]
    objective = np.r_[np.zeros(nx), np.ones(nz)]
    rows, cols, values, lows, highs = [], [], [], [], []

    def add(coeffs, lo=-np.inf, hi=np.inf):
        index = len(lows)
        for col, value in coeffs.items():
            if value:
                rows.append(index)
                cols.append(col)
                values.append(value)
        lows.append(lo)
        highs.append(hi)

    for bid, indices in by_box.items():
        add({col: 1 for col in indices}, lo=1, hi=1)
    for slot_id, indices in by_slot.items():
        add({col: 1 for col in indices}, lo=slots[slot_id]["count"], hi=slots[slot_id]["count"])
    for ti, indices in by_trip.items():
        model = TEMPLATE[ti][0]
        add({col: boxes[choices[col][0]]["mass"] for col in indices}, hi=drones[model]["payload"])
        add({col: boxes[choices[col][0]]["volume"] for col in indices}, hi=drones[model]["volume"])
    arc_loads = []
    for ai, (ti, si, model, start, end) in enumerate(arcs):
        load = {col: boxes[bid]["mass"] for col, (bid, slot_id) in enumerate(choices)
                if slots[slot_id]["trip"] == ti and slots[slot_id]["order"] >= si}
        arc_loads.append(load)
    for ti in range(len(TEMPLATE)):
        model = TEMPLATE[ti][0]
        coeffs = {nx + ai: 1 for ai, arc in enumerate(arcs) if arc[0] == ti}
        add(coeffs, hi=(1 - drones[model]["reserve"]) * drones[model]["battery_kwh"] - return_energy[ti])

    cuts = {ai: set() for ai in range(nz)}

    def add_cut(ai, q0):
        if any(abs(q0 - old) < 1e-7 for old in cuts[ai]):
            return False
        cuts[ai].add(q0)
        ti, si, model, start, end = arcs[ai]
        drone = drones[model]
        leg = data["legs"][start, end]
        qmax = drone["payload"]
        range_q = drone["range0"] - (drone["range0"] - drone["range_full"]) * (q0 / qmax) ** 1.5
        derivative = (drone["battery_kwh"] * leg["distance"] / (range_q * range_q)
                      * (drone["range0"] - drone["range_full"]) * 1.5 * math.sqrt(q0) / qmax ** 1.5
                      + 9.81 * leg["climb"] / (3.6e6 * drone["eta"]))
        f0 = segment(model, start, end, q0, data)[0]
        coeffs = {col: derivative * mass for col, mass in arc_loads[ai].items()}
        coeffs[nx + ai] = -1
        add(coeffs, hi=-f0 + derivative * q0)
        return True

    for ai, (_, _, model, _, _) in enumerate(arcs):
        for q0 in (0.0, drones[model]["payload"] / 2, drones[model]["payload"]):
            add_cut(ai, q0)

    for iteration in range(50):
        matrix = coo_matrix((values, (rows, cols)), shape=(len(lows), nx + nz)).tocsr()
        answer = milp(objective, integrality=integrality, bounds=Bounds(lower, upper),
                      constraints=LinearConstraint(matrix, lows, highs),
                      options={"time_limit": time_limit, "mip_rel_gap": 1e-7})
        if answer.status != 0 or answer.x is None:
            raise RuntimeError(f"参考访问结构逐箱指派 MILP 未得最优解：{answer.status} {answer.message}")
        loads = [sum(mass * answer.x[col] for col, mass in load.items()) for load in arc_loads]
        actual = [segment(arc[2], arc[3], arc[4], min(load, drones[arc[2]]["payload"]), data)[0]
                  for arc, load in zip(arcs, loads)]
        added = False
        for ti in range(len(TEMPLATE)):
            model = TEMPLATE[ti][0]
            indices = [ai for ai, arc in enumerate(arcs) if arc[0] == ti]
            used = sum(actual[ai] for ai in indices) + return_energy[ti]
            if used > (1 - drones[model]["reserve"]) * drones[model]["battery_kwh"] + 1e-8:
                for ai in indices:
                    added |= add_cut(ai, loads[ai])
        if not added:
            break
    else:
        raise RuntimeError("参考结构能耗切平面达到迭代上限")
    specs = [{"model": entry[0], "stops": [{"area": area, "ids": []} for area, _ in entry[1:]]}
             for entry in TEMPLATE]
    for col, (bid, slot_id) in enumerate(choices):
        if answer.x[col] > .5:
            slot = slots[slot_id]
            specs[slot["trip"]]["stops"][slot["order"]]["ids"].append(bid)
    for spec in specs:
        for stop in spec["stops"]:
            stop["ids"].sort()
        assert evaluate_sortie(spec, data) is not None
    result = decode(specs, data, require_all=True)
    assert result is not None
    return specs, result, {"milp_iterations": iteration + 1, "variables": nx + nz,
                           "cuts": sum(map(len, cuts.values())), "mip_gap": answer.mip_gap}
