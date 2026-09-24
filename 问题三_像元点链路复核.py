"""只读复核已发布问题三方案的两个静止投送通信反例。"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from 地理计算 import geodesic_distance
from 问题三_通信核心 import Point, load_nodes, load_parameters


ROOT = Path(__file__).resolve().parent


def worst_terrain_clearance(image, first: Point, second: Point):
    """PixelIsPoint: tiepoint 为首像元中心，穿格边界在整数索引 ±0.5。"""
    tie, scale = image.tag_v2[33922], image.tag_v2[33550]
    x0, x1 = ((p.lon - tie[3]) / scale[0] for p in (first, second))
    y0, y1 = ((tie[4] - p.lat) / scale[1] for p in (first, second))
    cuts = {0.0, 1.0}
    for start, end in ((x0, x1), (y0, y1)):
        if abs(end - start) < 1e-15:
            continue
        for cell in range(math.floor(min(start, end) - 0.5) + 1,
                          math.ceil(max(start, end) - 0.5) + 1):
            parameter = (cell + 0.5 - start) / (end - start)
            if 0 < parameter < 1:
                cuts.add(parameter)
    worst = -math.inf
    ordered = sorted(cuts)
    for left, right in zip(ordered, ordered[1:]):
        mid = (left + right) / 2
        col = math.floor(x0 + mid * (x1 - x0) + 0.5)
        row = math.floor(y0 + mid * (y1 - y0) + 0.5)
        ground = float(image.getpixel((col, row)))
        line_low = min(first.alt + left * (second.alt - first.alt),
                       first.alt + right * (second.alt - first.alt))
        worst = max(worst, ground - line_low)
    return -worst


def link(image, first, second, threshold, parameters):
    clearance = worst_terrain_clearance(image, first, second)
    horizontal = geodesic_distance(first.lon, first.lat, second.lon, second.lat)
    distance_km = math.hypot(horizontal, first.alt - second.alt) / 1000
    loss = 32.45 + 20 * math.log10(parameters["freq_mhz"])
    loss += 20 * math.log10(distance_km)
    if clearance <= 0:
        loss += parameters["obstruction_db"]
    return clearance, loss, threshold


def main():
    image = Image.open(ROOT / "数据" / "镇龙乡及周边30米DEM.tif")
    keys = image.tag_v2[34735]
    geo_keys = {keys[i]: keys[i + 3] for i in range(4, len(keys), 4)}
    assert geo_keys[1025] == 2, "此脚本要求 RasterPixelIsPoint DEM"
    plan = json.loads((ROOT / "results" / "问题三_参考口径" /
                       "主方案_完整方案.json").read_text(encoding="utf-8"))
    parameters, nodes = load_parameters(), load_nodes()
    hub = nodes["O01"]
    gateway = Point(hub.lon, hub.lat, hub.alt + parameters["gateway_height"])
    relays = {r["id"]: Point(r["lon"], r["lat"], r["hover_alt_m"])
              for r in plan["relays"]}
    for trip, area, instant in (("T14", "S008", 4200), ("T18", "S004", 6900)):
        point = nodes[area]
        transport = Point(point.lon, point.lat, point.alt + 30)
        active = [r for r in plan["relays"]
                  if r["link_ready_s"] <= instant < r["service_end_s"]]
        endpoints = [("G01", gateway, parameters["limit_direct"])]
        endpoints += [(r["id"], relays[r["id"]], parameters["limit_access"])
                      for r in active]
        relay_ok = False
        for name, endpoint, threshold in endpoints:
            clearance, loss, limit = link(image, transport, endpoint,
                                          threshold, parameters)
            print(f"{trip} {area} {name}: LOS余量={clearance:.3f} m; "
                  f"损耗={loss:.3f} dB; 门限={limit:.3f} dB")
            if name == "G01":
                assert loss > limit, (trip, name, loss, limit)
            elif loss <= limit:
                relay_ok = True
        assert active, trip
        assert relay_ok, (trip, "在役中继应至少有一条可用链路")
    print("两个静止投送点直连均不可用，且均被在役中继覆盖。")


if __name__ == "__main__":
    main()
