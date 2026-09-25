# -*- coding: utf-8 -*-
"""对 plan_3relay_ref.json 做逐点通信 + 物理/资源全量复核。"""
import sys, os, json, math
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from PIL import Image
from 问题二_调度核心 import load_data, evaluate_sortie
from 问题三_通信核心 import load_nodes, load_parameters, Point, Terrain
from 问题三_全程通信重认证 import PointRasterTerrain
from 问题三_联合调度 import trajectory, position
from 问题三_像元点链路复核 import link
D = load_data(); nodes = load_nodes(); params = load_parameters()
IM = Image.open(r"D:\git\math_modeling\UAV\数据\镇龙乡及周边30米DEM.tif")
plan = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan_3relay_ref.json"), encoding="utf-8"))

def pos_at(t, start, rel):
    ev = evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)
    ph = trajectory(ev, D, nodes)
    for q in ph:
        if q["t0"] <= rel <= q["t1"]: return position(q, rel)
    return None

if __name__ == "__main__":
    hubs = [r for r in plan["relays"]]
    def active(tt): return [r for r in hubs if r["link_ready_s"] <= tt <= r["service_end_s"]]
    hub = nodes["O01"]; gw = Point(hub.lon, hub.lat, hub.alt + params["gateway_height"])
    total = 0.0; det = []
    for t in plan["transport"]:
        ev = evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)
        ph = trajectory(ev, D, nodes); gaps = []; cur = None
        for q in ph:
            tt = q["t0"]
            while tt <= q["t1"] + 1e-9:
                p = position(q, tt); ok = False
                try:
                    cl, loss, thr = link(IM, p, gw, params["limit_direct"], params)
                    if loss <= thr: ok = True
                except Exception: pass
                if not ok:
                    for r in active(t["start_s"] + tt):
                        try:
                            cl, loss, thr = link(IM, p, Point(r["lon"], r["lat"], r["hover_alt_m"]), params["limit_access"], params)
                            if loss <= thr: ok = True; break
                        except Exception: pass
                if not ok:
                    if cur is None: cur = [t["start_s"]+tt, t["start_s"]+tt]
                    else: cur[1] = t["start_s"]+tt
                else:
                    if cur is not None: gaps.append(tuple(cur)); cur = None
                tt += 0.5
        if cur is not None: gaps.append(tuple(cur))
        g = sum(b-a for a,b in gaps); total += g
        if g > 1e-6: det.append((t["id"], round(g,2)))
    print("逐点(0.5 s)通信: 缺口合计 %.3f s %s" % (total, det if det else "(无缺口)"))
    errs = []
    for t in plan["transport"]:
        ev = evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)
        dr = D["drones"][t["model"]]
        if ev["mass_kg"] > dr["payload"] + 1e-9 or ev["volume_m3"] > dr["volume"] + 1e-9: errs.append("载荷 " + t["id"])
        if ev["return_soc"] < dr["reserve"] - 1e-9: errs.append("SOC " + t["id"])
    if len(plan["deliveries"]) != 80: errs.append("箱数")
    for r in plan["relays"]:
        g = PointRasterTerrain().elevation(r["lon"], r["lat"])
        if r["hover_alt_m"] - g > 300 + 1e-6: errs.append("离地 " + r["id"])
        if r["soc"] < 0.2 - 1e-9: errs.append("SOC " + r["id"])
    for key, ek in (("uav","return_s"), ("battery","charge_end_s"), ("relay_id","relay_free_s"), ("energy_id","energy_free_s")):
        iv = defaultdict(list)
        rows = plan["transport"] if key in ("uav","battery") else plan["relays"]
        for x in rows: iv[x[key]].append((x["start_s"] if key in ("uav","battery") else x["depart_s"], x[ek], x.get("id") or x.get("relay_id")))
        for name, xs in iv.items():
            xs.sort()
            for a,b in zip(xs, xs[1:]):
                if b[0] < a[1] - 1e-8: errs.append("重叠 %s %s %s" % (key, a[2], b[2]))
    print("物理/资源校验:", "PASS" if not errs else errs[:6])
    m = plan["metrics"]; print("指标:", m)

