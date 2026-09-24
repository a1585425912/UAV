"""从真实 DEM 的悬停像元筛选通信点，保存可复核覆盖矩阵。"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from 问题三_通信核心 import Point, Terrain, certified_link, load_nodes, load_parameters, maximum_distance


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题三_参考口径"


def candidates(step=6):
    terrain, params, nodes = Terrain(), load_parameters(), load_nodes()
    hub = nodes["O01"]
    gateway = Point(hub.lon, hub.lat, hub.alt + params["gateway_height"])
    needs = []
    for area, node in nodes.items():
        if area == "O01":
            continue
        place = Point(node.lon, node.lat, node.alt + 30)
        direct, _ = certified_link(terrain, params, place, place, gateway, params["limit_direct"])
        if not direct:
            needs.append((area, place))
    # 仅保留节点群外围 1.5km 的 DEM 网格；证书本身仍按原始 DEM 算。
    lons = [p.lon for _, p in needs]
    lats = [p.lat for _, p in needs]
    pad_lon, pad_lat = .025, .025
    c0 = max(0, int((min(lons) - pad_lon - terrain.left) / terrain.step_lon))
    c1 = min(terrain.z.shape[1], int((max(lons) + pad_lon - terrain.left) / terrain.step_lon) + 1)
    r0 = max(0, int((terrain.top - max(lats) - pad_lat) / terrain.step_lat))
    r1 = min(terrain.z.shape[0], int((terrain.top - min(lats) + pad_lat) / terrain.step_lat) + 1)
    sites = []
    clear_range = 10 ** ((params["limit_access"] - 32.45 - 20 * math.log10(params["freq_mhz"])) / 20) * 1000
    for row in range(r0, r1, step):
        for col in range(c0, c1, step):
            lon = terrain.left + (col + .5) * terrain.step_lon
            lat = terrain.top - (row + .5) * terrain.step_lat
            point = Point(lon, lat, float(terrain.z[row, col]) + 300)
            ok, _ = certified_link(terrain, params, point, point, gateway, params["limit_backhaul"])
            if not ok:
                continue
            covered = []
            for area, place in needs:
                if maximum_distance(place, place, point) > clear_range:
                    continue
                available, _ = certified_link(terrain, params, place, place, point, params["limit_access"])
                if available:
                    covered.append(area)
            if covered:
                sites.append({"row": row, "col": col, "lon": lon, "lat": lat, "alt": point.alt,
                              "covered": covered})
    return needs, sites


def choose_sites(needs, sites, max_sites=4):
    names = [a for a, _ in needs]
    by_pattern = {}
    for site in sites:
        key = tuple(site["covered"])
        old = by_pattern.get(key)
        if old is None or site["alt"] < old["alt"]:
            by_pattern[key] = site
    unique = list(by_pattern.values())
    if not unique:
        return [], {"status": "无候选"}
    rows, cols, vals = [], [], []
    for i, name in enumerate(names):
        for j, site in enumerate(unique):
            if name in site["covered"]:
                rows.append(i); cols.append(j); vals.append(1)
    matrix = coo_matrix((vals, (rows, cols)), shape=(len(names), len(unique))).tocsr()
    answer = milp(np.ones(len(unique)), integrality=np.ones(len(unique)),
                  bounds=Bounds(np.zeros(len(unique)), np.ones(len(unique))),
                  constraints=LinearConstraint(matrix, np.ones(len(names)), np.full(len(names), np.inf)),
                  options={"time_limit": 60, "mip_rel_gap": 0})
    if answer.x is None:
        return [], {"status": answer.message, "uncovered": sorted(set(names) - set(a for s in sites for a in s["covered"]))}
    picked = [site for site, x in zip(unique, answer.x) if x > .5]
    return picked, {"status": answer.message, "sites": len(picked), "patterns": len(unique),
                    "all_covered": sorted(set(a for site in picked for a in site["covered"])) == sorted(names)}


def main():
    needs, sites = candidates()
    selected, meta = choose_sites(needs, sites)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "候选悬停点覆盖.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["行", "列", "经度", "纬度", "悬停海拔_m", "覆盖服务区"])
        writer.writeheader()
        for site in sites:
            writer.writerow({"行": site["row"], "列": site["col"], "经度": site["lon"], "纬度": site["lat"],
                             "悬停海拔_m": site["alt"], "覆盖服务区": "、".join(site["covered"])})
    print("需中继服务区", [a for a, _ in needs], "候选数", len(sites), "选点", selected, "状态", meta)


if __name__ == "__main__":
    main()
