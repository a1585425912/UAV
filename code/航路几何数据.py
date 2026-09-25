"""以 O01 为原点，生成 DEM 节点作业高度及全部有向直飞航段参数。

运行：python 航路几何数据.py
输出：results/航路节点坐标与作业高度.csv、results/有向航段几何参数.csv、
      results/单服务区往返几何参数.csv。
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parent.parent
NODE_PATH = ROOT / "数据" / "无人机应急物资运输基础数据" / "调度中心与服务区.xlsx"
DEM_PATH = next((ROOT / "数据").rglob("*DEM.mat"))
OUT = ROOT / "results"
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def ecef_at_sea_level(lon_deg: float, lat_deg: float) -> tuple[float, float, float]:
    lon, lat = math.radians(lon_deg), math.radians(lat_deg)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    return n * math.cos(lat) * math.cos(lon), n * math.cos(lat) * math.sin(lon), n * (1 - WGS84_E2) * math.sin(lat)


def local_xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """WGS84 地心坐标在 O01 水平切平面的东、北方向投影，单位 m。"""
    xyz = ecef_at_sea_level(lon, lat)
    xyz0 = ecef_at_sea_level(lon0, lat0)
    dx, dy, dz = (a - b for a, b in zip(xyz, xyz0))
    l0, p0 = math.radians(lon0), math.radians(lat0)
    east = -math.sin(l0) * dx + math.cos(l0) * dy
    north = -math.sin(p0) * math.cos(l0) * dx - math.sin(p0) * math.sin(l0) * dy + math.cos(p0) * dz
    return east, north


def line_cells(lon0, lat0, lon1, lat1, dem_meta):
    """返回有向航段穿过的 DEM 像元高程；沿用现行几何缓存的穿格口径。"""
    dem, lat_top, lon_left, dx, dy, nodata = dem_meta
    x0, y0 = (lon0 - lon_left) / dx, (lat_top - lat0) / dy
    x1, y1 = (lon1 - lon_left) / dx, (lat_top - lat1) / dy
    breaks = [0.0, 1.0]
    for a, b in ((x0, x1), (y0, y1)):
        if abs(b - a) < 1e-12:
            continue
        lo, hi = sorted((a, b))
        for boundary in np.arange(math.floor(lo - 0.5) + 1, math.ceil(hi - 0.5) + 1) + 0.5:
            t = (boundary - a) / (b - a)
            if 0 < t < 1:
                breaks.append(float(t))
    breaks.sort()
    values = []
    for left, right in zip(breaks[:-1], breaks[1:]):
        t = (left + right) / 2
        row = math.floor(y0 + t * (y1 - y0) + 0.5)
        col = math.floor(x0 + t * (x1 - x0) + 0.5)
        assert 0 <= row < dem.shape[0] and 0 <= col < dem.shape[1], "航段离开DEM覆盖"
        z = float(dem[row, col])
        assert z != nodata and np.isfinite(z), "航段经过无效DEM像元"
        values.append(z)
    return values


def write_csv(path: Path, fieldnames: list[str], data: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def main() -> None:
    rows = list(load_workbook(NODE_PATH, read_only=True, data_only=True).active.values)
    source = [r for r in rows if isinstance(r[0], str) and (r[0] == "O01" or r[0].startswith("S0"))]
    assert len(source) == 16 and source[0][0] == "O01"
    mat = loadmat(DEM_PATH)
    dem = mat["dem"]
    latitudes = mat["latitude"][:, 0]
    longitudes = mat["longitude"][0]
    nodata = float(mat["nodata"][0, 0])
    assert int(mat["epsg_code"][0, 0]) == 4326
    dem_meta = (dem, float(latitudes[0]), float(longitudes[0]),
                float(longitudes[1] - longitudes[0]), float(latitudes[0] - latitudes[1]), nodata)
    lon0, lat0 = map(float, source[0][2:4])
    origin_row = int(np.argmin(np.abs(latitudes - lat0)))
    origin_col = int(np.argmin(np.abs(longitudes - lon0)))
    origin_ground = float(dem[origin_row, origin_col])
    nodes = []
    for row in source:
        name, lon, lat, sheet_z = row[0], float(row[2]), float(row[3]), float(row[4])
        col = int(np.argmin(np.abs(longitudes - lon)))
        r = int(np.argmin(np.abs(latitudes - lat)))
        ground = float(dem[r, col])
        assert math.isfinite(ground) and ground != nodata, f"{name}: 无效 DEM 像元"
        east, north = local_xy(lon, lat, lon0, lat0)
        nodes.append({"编号": name, "经度（度）": lon, "纬度（度）": lat,
                      "东向x（m）": east, "北向y（m）": north,
                      "节点表地面海拔（m）": sheet_z, "DEM地面海拔（m）": ground,
                      "DEM减节点表（m）": ground - sheet_z,
                      "作业海拔（m）": ground + (0 if name == "O01" else 30),
                      "相对O01作业高度z（m）": ground + (0 if name == "O01" else 30) - origin_ground,
                      "DEM行号（从0起）": r, "DEM列号（从0起）": col})
    nodes[0]["东向x（m）"] = nodes[0]["北向y（m）"] = nodes[0]["相对O01作业高度z（m）"] = 0.0

    legs = []
    for start in nodes:
        for end in nodes:
            if start["编号"] == end["编号"]:
                continue
            heights = line_cells(start["经度（度）"], start["纬度（度）"],
                                 end["经度（度）"], end["纬度（度）"], dem_meta)
            cruise = max(heights) + 50
            start_z, end_z = start["作业海拔（m）"], end["作业海拔（m）"]
            assert cruise >= max(start_z, end_z), (start["编号"], end["编号"])
            dx = end["东向x（m）"] - start["东向x（m）"]
            dy = end["北向y（m）"] - start["北向y（m）"]
            legs.append({"起点": start["编号"], "终点": end["编号"],
                         "水平距离（m）": math.hypot(dx, dy),
                         "起点作业海拔（m）": start_z, "终点作业海拔（m）": end_z,
                         "航段DEM最高海拔（m）": max(heights), "计划巡航海拔（m）": cruise,
                         "起点爬升（m）": cruise - start_z, "终点下降（m）": cruise - end_z,
                         "经过DEM像元段数": len(heights)})
    OUT.mkdir(exist_ok=True)
    by_pair = {(leg["起点"], leg["终点"]): leg for leg in legs}
    round_trips = []
    for site in nodes[1:]:
        name = site["编号"]
        outward, backward = by_pair[("O01", name)], by_pair[(name, "O01")]
        round_trips.append({"服务区": name,
                            "去程水平距离（m）": outward["水平距离（m）"],
                            "返程水平距离（m）": backward["水平距离（m）"],
                            "去程巡航海拔（m）": outward["计划巡航海拔（m）"],
                            "返程巡航海拔（m）": backward["计划巡航海拔（m）"],
                            "去程爬升（m）": outward["起点爬升（m）"],
                            "去程下降（m）": outward["终点下降（m）"],
                            "返程爬升（m）": backward["起点爬升（m）"],
                            "返程下降（m）": backward["终点下降（m）"],
                            "水平总距离（m）": outward["水平距离（m）"] + backward["水平距离（m）"],
                            "总爬升（m）": outward["起点爬升（m）"] + backward["起点爬升（m）"],
                            "总下降（m）": outward["终点下降（m）"] + backward["终点下降（m）"]})
    write_csv(OUT / "航路节点坐标与作业高度.csv", list(nodes[0]), nodes)
    write_csv(OUT / "有向航段几何参数.csv", list(legs[0]), legs)
    write_csv(OUT / "单服务区往返几何参数.csv", list(round_trips[0]), round_trips)
    print(f"节点 {len(nodes)} 个；有向航段 {len(legs)} 条；O01 DEM 海拔 {nodes[0]['DEM地面海拔（m）']:.3f} m")
    print(f"最大节点表与 DEM 差值 {max(abs(x['DEM减节点表（m）']) for x in nodes):.3f} m")


if __name__ == "__main__":
    main()
