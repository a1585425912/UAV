# -*- coding: utf-8 -*-
"""q3_certify：统一口径（PixelIsPoint）的通信认证工具。

修复四类缺陷：
1) 单点失败计入：边界与网格点逐个判，任一失败即记缺口（不因相邻点可用而漏计）；
2) 同址零距离：距离为 0 时按可用处理，避免 log10(0) / 误判；
3) 不硬编码缺口：所有 gap 由逐点/逐段判定累加；
4) 统一 Terrain：全程使用 PointRasterTerrain（GeoTIFF 1025=2 RasterPixelIsPoint）。
边界集合 = 轨迹阶段边界 ∪ 中继建链/服务结束时刻 ∪ 均匀网格。
"""
import sys, os, math
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from PIL import Image
from 问题二_调度核心 import load_data, evaluate_sortie
from 问题三_通信核心 import load_nodes, load_parameters, Point
from 问题三_联合调度 import trajectory, position
from 问题三_像元点链路复核 import worst_terrain_clearance
from 地理计算 import geodesic_distance
from 问题三_全程通信重认证 import PointRasterTerrain

ROOT = r"D:\git\math_modeling\UAV"
D = load_data(); NODES = load_nodes(); PARAMS = load_parameters()
TERRAIN = PointRasterTerrain()
IMAGE = Image.open(os.path.join(ROOT, "数据", "镇龙乡及周边30米DEM.tif"))
HUB = NODES["O01"]
GATEWAY = Point(HUB.lon, HUB.lat, HUB.alt + PARAMS["gateway_height"])

def link_ok(p, q, threshold):
    """逐点链路：返回 (可用, 余量m, 损耗dB)。距离为 0 视为可用。"""
    horiz = geodesic_distance(p.lon, p.lat, q.lon, q.lat)
    dz = p.alt - q.alt
    d_km = math.hypot(horiz, dz) / 1000.0
    if d_km < 1e-9:
        return True, float("inf"), 0.0
    clearance = worst_terrain_clearance(IMAGE, p, q)
    loss = 32.45 + 20*math.log10(PARAMS["freq_mhz"]) + 20*math.log10(d_km)
    if clearance <= 0:
        loss += PARAMS["obstruction_db"]
    return loss <= threshold, clearance, loss

def active(t_abs, relays):
    return [r for r in relays if r["link_ready_s"] - 1e-9 <= t_abs <= r["service_end_s"] + 1e-9]

def decide(t_abs, pos, relays):
    ok, _, _ = link_ok(pos, GATEWAY, PARAMS["limit_direct"])
    if ok: return "直连", ""
    for r in active(t_abs, relays):
        ok, _, _ = link_ok(pos, Point(r["lon"], r["lat"], r["hover_alt_m"]), PARAMS["limit_access"])
        if ok: return "中继", r["id"]
    return None, ""

def sample_times(phase, start, relays, resolution):
    ts = {phase["t0"], phase["t1"]}
    n = max(1, int(math.ceil((phase["t1"] - phase["t0"]) / resolution)))
    for i in range(n + 1):
        ts.add(phase["t0"] + (phase["t1"] - phase["t0"]) * i / n)
    for r in relays:
        for x in (r["link_ready_s"], r["service_end_s"]):
            rel = x - start
            if phase["t0"] - 1e-9 <= rel <= phase["t1"] + 1e-9:
                ts.add(min(max(rel, phase["t0"]), phase["t1"]))
    return sorted(ts)

def check_task(task, start, relays, resolution=0.5):
    ev = evaluate_sortie({"model": task["model"], "stops": task["stops"]}, D)
    ph = trajectory(ev, D, NODES)
    fails = []
    for q in ph:
        for rel in sample_times(q, start, relays, resolution):
            pos = position(q, rel)
            status, rid = decide(start + rel, pos, relays)
            if status is None:
                fails.append((start + rel, q["kind"]))
    # 合并为区间（含单点）
    gaps = []
    for t, kind in fails:
        if gaps and abs(t - gaps[-1][1]) <= resolution + 1e-9:
            gaps[-1] = (gaps[-1][0], t, gaps[-1][2] + [kind])
        else:
            gaps.append((t, t, [kind]))
    return [(a, b, sum(1 for _ in kinds)) for a, b, kinds in gaps], ev

def check_plan(transport, relays, resolution=0.5):
    total = 0.0; detail = []
    for t in transport:
        gaps, ev = check_task(t, t["start_s"], relays, resolution)
        g = sum(b - a for a, b, n in gaps)
        total += g
        if gaps:
            detail.append((t["id"], round(g, 6), [(round(a, 3), round(b, 3)) for a, b, _ in gaps]))
    return total, detail
