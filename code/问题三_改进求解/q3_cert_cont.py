# -*- coding: utf-8 -*-
"""q3_cert_cont：更紧的连续通信证书（统一 PixelIsPoint）。

相对现有 certified_link 的两点收紧：
1) 距离上界：线段两端点到固定端点的三维距离取 max（距离函数沿直线段是凸的，最大值必在端点），
   不再额外加"每度位移上界"的粗项；
2) 遮挡证明：静止段（a==b，如投送悬停）直接用逐点精确 LOS（worst_terrain_clearance），
   该判据对整段静止区间有效；运动段仍用外包走廊证明（保守，但距离上界已收紧）。
返回 (是否认证, 依据)。
"""
import sys, os, math
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from PIL import Image
from 问题三_通信核心 import load_nodes, load_parameters
from 问题三_像元点链路复核 import worst_terrain_clearance
from 问题三_全程通信重认证 import PointRasterTerrain

ROOT = r"D:\git\math_modeling\UAV"
NODES = load_nodes(); PARAMS = load_parameters(); TERRAIN = PointRasterTerrain()
IMAGE = Image.open(os.path.join(ROOT, "数据", "镇龙乡及周边30米DEM.tif"))

def _planar(p):
    x, y = TERRAIN.xy(p)
    return float(x), float(y), float(p.alt)

def _dist(p, q):
    ax, ay, az = _planar(p); bx, by, bz = _planar(q)
    return math.hypot(math.hypot(ax-bx, ay-by), az-bz)

def certified_link_v2(a, b, fixed, threshold_db, margin=0.1):
    d = max(_dist(a, fixed), _dist(b, fixed)) + margin
    d_km = max(d / 1000.0, 1e-9)
    fspl = 32.45 + 20*math.log10(PARAMS["freq_mhz"]) + 20*math.log10(d_km)
    if fspl + PARAMS["obstruction_db"] <= threshold_db - 1e-9:
        return True, "距离上界+遮挡上界仍可用"
    if fspl > threshold_db - 1e-9:
        return False, "距离上界未获认证"
    if abs(a.lon-b.lon) < 1e-12 and abs(a.lat-b.lat) < 1e-12 and abs(a.alt-b.alt) < 1e-9:
        clearance = worst_terrain_clearance(IMAGE, a, fixed)
        return (clearance > 0), ("静止段精确LOS 余量=%.3f m" % clearance)
    clear = TERRAIN.certify_clear(a, b, fixed)
    return clear, ("走廊证明无遮挡" if clear else "运动段视线未认证")

