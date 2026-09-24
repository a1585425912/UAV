"""在已证可覆盖的 DEM 候选点中改进第二阶段中继位置。"""
from __future__ import annotations

import csv

from 问题二_调度核心 import evaluate_sortie, load_data
from 问题三_通信核心 import Point, Terrain, certified_link, load_nodes, load_parameters, relay_sortie
from 问题三_联合调度 import (SITES, evaluate_plan, position, relay_plan,
                         trajectory, transport_starts)
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed


def main():
    data, terrain, params, nodes = load_data(), Terrain(), load_parameters(), load_nodes()
    specs, _, _ = optimize_seed(data)
    starts, resources = transport_starts(specs, REFERENCE_STARTS, data)
    baseline = evaluate_plan(specs, starts, relay_plan(terrain), 1, resources)
    used = [r for r in baseline["communications"] if r["relay_id"] == "RS03"]
    points = []
    for row in used:
        index = int(row["trip"][1:]) - 1
        phases = trajectory(evaluate_sortie(specs[index], data), data, nodes)
        for absolute in (row["start_s"], (row["start_s"] + row["end_s"]) / 2, row["end_s"]):
            local = absolute - starts[index]
            phase = next((p for p in phases if p["t0"] - 1e-8 <= local <= p["t1"] + 1e-8), None)
            if phase is not None:
                points.append(position(phase, min(phase["t1"], max(phase["t0"], local))))
    with open("results/问题三_参考口径/候选悬停点覆盖.csv", encoding="utf-8-sig") as stream:
        candidates = list(csv.DictReader(stream))
    west = relay_plan(terrain)[0]
    results = []
    for row in candidates:
        if "S004" not in row["覆盖服务区"].split("、"):
            continue
        point = Point(float(row["经度"]), float(row["纬度"]), float(row["悬停海拔_m"]))
        if not all(certified_link(terrain, params, p, p, point, params["limit_access"])[0]
                   for p in points):
            continue
        sortie = relay_sortie(terrain, point, west["relay_free_s"], 7320, "R01", "R-B3")
        results.append((sortie["return_s"], sortie["link_ready_s"], point))
    results.sort()
    print("RS03 采样位置数", len(points), "可覆盖候选", len(results))
    for item in results[:12]:
        print(item)


if __name__ == "__main__":
    main()
