# -*- coding: utf-8 -*-
"""参考式 3 中继方案（P1/P2/P3'）+ 逐点链路全量验证。
运输：已发布 22 架次，仅 T22 前移到 5899 s。
中继：RS01=R01@P1（提前建链），RS02=R01@P3'（P3 东移 123 m 清 S004 遮挡，窗口延长到 T18 尾部），RS03=R02@P2。
"""
import sys, os, json, math
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from PIL import Image
from 问题二_调度核心 import load_data, evaluate_sortie
from 问题三_通信核心 import load_nodes, load_parameters, Point
from 问题三_联合调度 import trajectory, position
from 问题三_像元点链路复核 import link
D = load_data(); nodes = load_nodes(); params = load_parameters()
IM = Image.open(r"D:\git\math_modeling\UAV\数据\镇龙乡及周边30米DEM.tif")
PUB = r"D:\git\math_modeling\UAV\results\问题三_参考口径\主方案_完整方案.json"

P1 = Point(109.19944, 23.05750, 989.9)
P2 = Point(109.28028, 23.03333, 677.3)
P3 = Point(109.19564, 23.06333, 1029.6)   # 东移后的北点
RELAYS = [
    {"id": "RS01", "site": "P1", "p": P1, "ready": 846.0, "end": 4694.0},
    {"id": "RS02", "site": "P3", "p": P3, "ready": 6614.0, "end": 7256.0},
    {"id": "RS03", "site": "P2", "p": P2, "ready": 732.0, "end": 6669.0},
]

def active(t):
    return [r for r in RELAYS if r["ready"] <= t <= r["end"]]

def point_ok(p, t, need_gateway=True):
    # 直连
    hub = nodes["O01"]; gw = Point(hub.lon, hub.lat, hub.alt + params["gateway_height"])
    try:
        cl, loss, thr = link(IM, p, gw, params["limit_direct"], params)
        if loss <= thr: return "直连"
    except Exception: pass
    for r in active(t):
        try:
            cl, loss, thr = link(IM, p, r["p"], params["limit_access"], params)
            if loss <= thr: return r["id"]
        except Exception: pass
    return None

if __name__ == "__main__":
    pub = json.load(open(PUB, encoding="utf-8"))
    starts = [t["start_s"] for t in pub["transport"]]
    i22 = next(i for i, t in enumerate(pub["transport"]) if t["id"] == "T22"); starts[i22] = 5899.0
    step = 0.5; total_gap = 0.0; detail = []
    for t, st in zip(pub["transport"], starts):
        ev = evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)
        ph = trajectory(ev, D, nodes)
        gaps = []; cur = None
        for q in ph:
            if q["kind"] == "投送":
                samples = [q["t0"] + i * step for i in range(int((q["t1"]-q["t0"])/step)+1)]
            else:
                samples = [q["t0"] + i * step for i in range(int((q["t1"]-q["t0"])/step)+1)]
            for rel in samples:
                if rel > q["t1"]: continue
                p = position(q, rel)
                if point_ok(p, st + rel) is None:
                    if cur is None: cur = [st + rel, st + rel]
                    else: cur[1] = st + rel
                else:
                    if cur is not None: gaps.append(tuple(cur)); cur = None
        if cur is not None: gaps.append(tuple(cur))
        g = sum(b - a for a, b in gaps)
        total_gap += g
        if g > 1e-6: detail.append((t["id"], round(g, 2), [(round(a,1), round(b,1)) for a,b in gaps]))
    print("逐点(0.5 s)验证 3 中继方案：缺口合计 %.3f s" % total_gap)
    if detail:
        for x in detail: print("  ", x)
    else:
        print("  无缺口：全部运输轨迹在逐点模型下被直连/在役中继覆盖")
    # 汇总
    transport_energy = sum(evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)["energy_kwh"] for t in pub["transport"])
    print("运输能耗 %.4f kWh；中继 3 条；联合完成时间 = max(运输最晚返航 %.1f, 中继最晚返航 %.1f)" % (
        transport_energy, max(starts[i] + evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)["duration_s"] for i, t in enumerate(pub["transport"])), 7256.0 + 778.0))
