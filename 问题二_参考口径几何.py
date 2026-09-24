"""用节点表海拔与 WGS84 距离统一问题二的 240 条有向航段。"""
from __future__ import annotations

import csv
from pathlib import Path

from 地理计算 import geodesic_distance

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题二_参考口径"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    nodes = {row["编号"]: row for row in read(ROOT / "results" / "航路节点坐标与作业高度.csv")}
    source = read(ROOT / "results" / "有向航段几何参数.csv")
    assert len(nodes) == 16 and len(source) == 240
    built = []
    for old in source:
        start, end = old["起点"], old["终点"]
        a, b = nodes[start], nodes[end]
        cruise = float(old["航段DEM最高海拔（m）"]) + 50
        za = float(a["节点表地面海拔（m）"]) + (0 if start == "O01" else 30)
        zb = float(b["节点表地面海拔（m）"]) + (0 if end == "O01" else 30)
        climb, descent = cruise - za, cruise - zb
        if min(climb, descent) < -1e-8:
            raise ValueError(f"{start}->{end}: 巡航海拔低于作业高度")
        distance = geodesic_distance(float(a["经度（度）"]), float(a["纬度（度）"]),
                                     float(b["经度（度）"]), float(b["纬度（度）"]))
        built.append({"起点": start, "终点": end, "水平距离（m）": distance,
                      "起点作业海拔（m）": za, "终点作业海拔（m）": zb,
                      "航段DEM最高海拔（m）": float(old["航段DEM最高海拔（m）"]),
                      "计划巡航海拔（m）": cruise, "起点爬升（m）": climb,
                      "终点下降（m）": descent, "经过DEM像元段数": int(old["经过DEM像元段数"])})
    assert len({(r["起点"], r["终点"]) for r in built}) == 240
    route = {(r["起点"], r["终点"]): r for r in built}
    for (start, end), row in route.items():
        rev = route[end, start]
        assert abs(row["水平距离（m）"] - rev["水平距离（m）"]) < 1e-7
        assert abs(row["计划巡航海拔（m）"] - rev["计划巡航海拔（m）"]) < 1e-7
        assert abs(row["起点爬升（m）"] - rev["终点下降（m）"]) < 1e-7
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "有向航段几何参数.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(built[0]))
        writer.writeheader()
        writer.writerows(built)
    sample = route["O01", "S008"]
    print(f"240 条航段；O01→S008: d={sample['水平距离（m）']:.3f} m，H={sample['计划巡航海拔（m）']:.3f} m，爬升={sample['起点爬升（m）']:.3f} m，下降={sample['终点下降（m）']:.3f} m")


if __name__ == "__main__":
    main()
