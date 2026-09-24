"""当前四问共用的 WGS84 椭球测地距离。"""
from __future__ import annotations

import math


A = 6378137.0
F = 1 / 298.257223563
B = A * (1 - F)


def geodesic_distance(lon1, lat1, lon2, lat2):
    """Vincenty WGS84 逆解，输入经纬度为度，输出米。"""
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
