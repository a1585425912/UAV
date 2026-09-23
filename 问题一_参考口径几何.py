"""按参考 PDF 的节点表海拔与 WGS84 椭球测地距离建立问题一往返航段。

沿线最高 DEM 海拔沿用已保存的统一航段缓存；不重新生成像元序列。
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "问题一_参考口径"
A = 6378137.0
F = 1 / 298.257223563
B = A * (1 - F)


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def geodesic_distance(lon1, lat1, lon2, lat2):
    """Vincenty WGS84 inverse，当前 15 条短航段均收敛。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    u1, u2 = math.atan((1 - F) * math.tan(phi1)), math.atan((1 - F) * math.tan(phi2))
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    lam = dlon
    for _ in range(100):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.sqrt((cu2 * sl) ** 2 + (cu1 * su2 - su1 * cu2 * cl) ** 2)
        if ss == 0:
            return 0.0
        cs = su1 * su2 + cu1 * cu2 * cl
        sigma = math.atan2(ss, cs)
        sa = cu1 * cu2 * sl / ss
        ca2 = 1 - sa * sa
        c2sm = cs - 2 * su1 * su2 / ca2 if ca2 > 1e-15 else 0.0
        c = F / 16 * ca2 * (4 + F * (4 - 3 * ca2))
        next_lam = dlon + (1 - c) * F * sa * (sigma + c * ss *
                    (c2sm + c * cs * (-1 + 2 * c2sm**2)))
        if abs(next_lam - lam) < 1e-13:
            lam = next_lam
            break
        lam = next_lam
    else:
        raise RuntimeError("WGS84 椭球距离未收敛")
    u2sq = ca2 * (A * A - B * B) / (B * B)
    aa = 1 + u2sq / 16384 * (4096 + u2sq * (-768 + u2sq * (320 - 175 * u2sq)))
    bb = u2sq / 1024 * (256 + u2sq * (-128 + u2sq * (74 - 47 * u2sq)))
    ds = bb * ss * (c2sm + bb / 4 * (cs * (-1 + 2 * c2sm**2)
         - bb / 6 * c2sm * (-3 + 4 * ss**2) * (-3 + 4 * c2sm**2)))
    return B * aa * (sigma - ds)


def main():
    nodes = {r["编号"]: r for r in rows(ROOT / "results" / "航路节点坐标与作业高度.csv")}
    cached = rows(ROOT / "results" / "单服务区往返几何参数.csv")
    origin = nodes["O01"]
    z0 = float(origin["节点表地面海拔（m）"])
    built = []
    deltas = []
    for old in cached:
        area = old["服务区"]
        target = nodes[area]
        zi = float(target["节点表地面海拔（m）"]) + 30
        d = geodesic_distance(float(origin["经度（度）"]), float(origin["纬度（度）"]),
                              float(target["经度（度）"]), float(target["纬度（度）"]))
        hout, hback = float(old["去程巡航海拔（m）"]), float(old["返程巡航海拔（m）"])
        if min(hout - z0, hout - zi, hback - zi, hback - z0) < -1e-9:
            raise RuntimeError(f"{area}: 巡航海拔低于节点作业海拔")
        up0, down0, up1, down1 = hout - z0, hout - zi, hback - zi, hback - z0
        built.append({"服务区": area, "去程水平距离（m）": d, "返程水平距离（m）": d,
                      "去程巡航海拔（m）": hout, "返程巡航海拔（m）": hback,
                      "去程爬升（m）": up0, "去程下降（m）": down0,
                      "返程爬升（m）": up1, "返程下降（m）": down1,
                      "水平总距离（m）": 2 * d, "总爬升（m）": up0 + up1,
                      "总下降（m）": down0 + down1})
        deltas.append(abs(d - float(old["去程水平距离（m）"])))
    assert len(built) == 15
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "单服务区往返几何参数.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(built[0]))
        writer.writeheader()
        writer.writerows(built)
    s8 = next(r for r in built if r["服务区"] == "S008")
    print(f"15 条参考口径往返航段；S008 d={s8['去程水平距离（m）']:.3f} m，巡航海拔={s8['去程巡航海拔（m）']:.3f} m，去程爬升={s8['去程爬升（m）']:.3f} m，下降={s8['去程下降（m）']:.3f} m")
    print(f"WGS84 测地距离与现有局部坐标最大差：{max(deltas):.6f} m")


if __name__ == "__main__":
    main()
