"""仅复核第一问第(1)项：15区×3机型的最大连续安全载荷。

独立于“问题1_求解.py”读取附件、密集采样 DEM，并用 Brent 法求根。
同时列出球面距离与 WGS84 椭球距离口径，检查上次结果的距离近似误差。
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.io import loadmat
from scipy.optimize import brentq


BASE = Path(__file__).resolve().parent
FILES = BASE / "数据" / "无人机应急物资运输基础数据"
DEM_FILE = next((BASE / "数据").rglob("*DEM.mat"))
G = 9.80665


def sheet_rows(name):
    workbook = load_workbook(FILES / name, read_only=True, data_only=True)
    return list(workbook.active.values)


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def vincenty_m(lon1, lat1, lon2, lat2):
    """WGS84 椭球逆解；本题点距小于 15 km，迭代稳定。"""
    a, f = 6378137.0, 1 / 298.257223563
    b = a * (1 - f)
    u1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    l = math.radians(lon2 - lon1)
    lam = l
    for _ in range(100):
        sin_sig = math.hypot(math.cos(u2) * math.sin(lam),
                             math.cos(u1) * math.sin(u2) - math.sin(u1) * math.cos(u2) * math.cos(lam))
        if sin_sig == 0:
            return 0.0
        cos_sig = math.sin(u1) * math.sin(u2) + math.cos(u1) * math.cos(u2) * math.cos(lam)
        sig = math.atan2(sin_sig, cos_sig)
        sin_alpha = math.cos(u1) * math.cos(u2) * math.sin(lam) / sin_sig
        cos2_alpha = 1 - sin_alpha**2
        cos2_sig_m = cos_sig - 2 * math.sin(u1) * math.sin(u2) / cos2_alpha if cos2_alpha > 1e-15 else 0.0
        c = f / 16 * cos2_alpha * (4 + f * (4 - 3 * cos2_alpha))
        next_lam = l + (1 - c) * f * sin_alpha * (
            sig + c * sin_sig * (cos2_sig_m + c * cos_sig * (-1 + 2 * cos2_sig_m**2)))
        if abs(next_lam - lam) < 1e-13:
            lam = next_lam
            break
        lam = next_lam
    else:
        raise RuntimeError("Vincenty 未收敛")
    u2sq = cos2_alpha * (a*a - b*b) / (b*b)
    big_a = 1 + u2sq / 16384 * (4096 + u2sq * (-768 + u2sq * (320 - 175 * u2sq)))
    big_b = u2sq / 1024 * (256 + u2sq * (-128 + u2sq * (74 - 47 * u2sq)))
    delta = big_b * sin_sig * (cos2_sig_m + big_b / 4 * (
        cos_sig * (-1 + 2 * cos2_sig_m**2) - big_b / 6 * cos2_sig_m
        * (-3 + 4 * sin_sig**2) * (-3 + 4 * cos2_sig_m**2)))
    return b * big_a * (sig - delta)


def dense_max_dem(dem, lat_centers, lon_centers, p0, p1):
    """每 1/20 像元密集采样经纬度直线，不复用原来的像元边界遍历。"""
    step_lon = lon_centers[1] - lon_centers[0]
    step_lat = lat_centers[0] - lat_centers[1]
    c0 = (p0[0] - lon_centers[0]) / step_lon
    c1 = (p1[0] - lon_centers[0]) / step_lon
    r0 = (lat_centers[0] - p0[1]) / step_lat
    r1 = (lat_centers[0] - p1[1]) / step_lat
    n = max(2, int(math.ceil(20 * max(abs(c1 - c0), abs(r1 - r0)))) + 1)
    t = np.linspace(0, 1, n)
    rows = np.rint(r0 + (r1 - r0) * t).astype(int)
    cols = np.rint(c0 + (c1 - c0) * t).astype(int)
    assert rows.min() >= 0 and cols.min() >= 0
    assert rows.max() < dem.shape[0] and cols.max() < dem.shape[1]
    values = dem[rows, cols]
    assert np.isfinite(values).all() and (values != -32767).all()
    return float(values.max()), n


def load_inputs():
    nodes = sheet_rows("调度中心与服务区.xlsx")
    assert nodes[2][0] == "O01"
    hub = tuple(float(x) for x in nodes[2][2:5])
    zones = [(r[0], tuple(float(x) for x in r[2:5])) for r in nodes[6:21]]
    assert len(zones) == 15 and len({z[0] for z in zones}) == 15
    models = {}
    for r in sheet_rows("运输无人机数据.xlsx")[2:5]:
        models[r[0]] = dict(m0=float(r[2]), qmax=float(r[3]),
                            l0=float(r[6]), lf=float(r[7]),
                            eu=float(r[8]), rho=float(r[9]) / 100,
                            eta=float(r[16]))
    assert set(models) == {"A", "B", "C"}
    mat = loadmat(DEM_FILE)
    assert int(mat["epsg_code"][0, 0]) == 4326
    return hub, zones, models, mat["dem"], mat["latitude"][:, 0], mat["longitude"][0]


def solve_capacity(model, distance, climb_out, climb_back):
    def energy(q):
        equivalent_range = model["l0"] - (model["l0"] - model["lf"]) * (q / model["qmax"])**1.5
        horizontal = model["eu"] * distance * (1 / equivalent_range + 1 / model["l0"])
        climbing = G / (3.6e6 * model["eta"]) * (
            (model["m0"] + q) * climb_out + model["m0"] * climb_back)
        return horizontal + climbing
    budget = (1 - model["rho"]) * model["eu"]
    if energy(0) > budget:
        return None, energy(0), energy(model["qmax"]), None
    if energy(model["qmax"]) <= budget:
        capacity = model["qmax"]
    else:
        capacity = brentq(lambda q: energy(q) - budget, 0, model["qmax"], xtol=1e-11)
    return capacity, energy(0), energy(model["qmax"]), energy(capacity) - budget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="只验证一个服务区，例如 S008")
    args = parser.parse_args()
    hub, zones, models, dem, lat, lon = load_inputs()
    previous = {}
    with (BASE / "results" / "Q1_安全载荷.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            previous[(r["服务区编号"], r["机型编号"])] = float(r["最大安全载荷（kg）"])
    output = []
    for site, node in zones:
        if args.site and site != args.site:
            continue
        highest, samples = dense_max_dem(dem, lat, lon, hub, node)
        cruise = highest + 50
        climb_out = cruise - hub[2]
        climb_back = cruise - node[2] - 30
        assert min(climb_out, climb_back) >= 0
        sphere = haversine_m(*hub[:2], *node[:2])
        ellipsoid = vincenty_m(*hub[:2], *node[:2])
        for name, model in models.items():
            q_sphere, _, _, residual_s = solve_capacity(model, sphere, climb_out, climb_back)
            q_wgs84, e0, eq, residual_w = solve_capacity(model, ellipsoid, climb_out, climb_back)
            old = previous[(site, name)]
            assert q_sphere is not None and q_wgs84 is not None
            assert abs(q_sphere - old) < 1e-7, (site, name, q_sphere, old)
            output.append({"服务区编号": site, "机型编号": name,
                           "DEM最高高程（m）": highest, "密集采样点数": samples,
                           "球面水平距离（m）": sphere, "WGS84水平距离（m）": ellipsoid,
                           "上次载荷（kg）": old, "球面复算载荷（kg）": q_sphere,
                           "WGS84复算载荷（kg）": q_wgs84,
                           "WGS84-上次（kg）": q_wgs84 - old,
                           "WGS84空载能耗（kWh）": e0,
                           "WGS84额定满载能耗（kWh）": eq,
                           "WGS84边界残差（kWh）": residual_w})
    if not args.site:
        assert len(output) == 45
        target = BASE / "results" / "Q1_子问题1_独立复核.csv"
        with target.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(output[0]))
            writer.writeheader()
            writer.writerows(output)
        print(target)
    print("rows", len(output), "max_abs_WGS84_delta_kg",
          max(abs(r["WGS84-上次（kg）"]) for r in output))
    for r in output:
        if args.site or abs(r["WGS84-上次（kg）"]) > 1e-4:
            print(r["服务区编号"], r["机型编号"],
                  f"old={r['上次载荷（kg）']:.6f}",
                  f"WGS84={r['WGS84复算载荷（kg）']:.6f}",
                  f"delta={r['WGS84-上次（kg）']:.6f}")


if __name__ == "__main__":
    main()
