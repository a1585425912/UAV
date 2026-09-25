# -*- coding: utf-8 -*-
"""固化修复版 3 中继方案：全指标 + 物理/资源 + 逐点通信 + 连续认证汇总。"""
import sys, os, json
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q3_certify as C
import q3_cont_cert as QC
from 问题三_通信核心 import Point, relay_sortie
from 问题三_全程通信重认证 import PointRasterTerrain
from 问题二_调度核心 import load_data, evaluate_sortie
OUT = os.path.dirname(os.path.abspath(__file__))
D = load_data(); TER = PointRasterTerrain()
def hover(lon, lat): return TER.elevation(lon, lat) + 299.999
P1 = Point(109.19944, 23.05750, hover(109.19944, 23.05750))
P2 = Point(109.28028, 23.03333, hover(109.28028, 23.03333))
P3 = Point(109.19564, 23.06333, hover(109.19564, 23.06333))
S1, S2, S3 = 4694.5, 7256.0, 6669.0

if __name__ == "__main__":
    r1 = relay_sortie(TER, P1, 0.0, S1, "R01", "R-B1")
    r2 = relay_sortie(TER, P3, r1["relay_free_s"], S2, "R01", "R-B3")
    r3 = relay_sortie(TER, P2, 0.0, S3, "R02", "R-B2")
    relays = [
        {"id": "RS01", "site": "P1", "relay_id": "R01", "energy_id": "R-B1", "lon": P1.lon, "lat": P1.lat, "hover_alt_m": P1.alt,
         "depart_s": 0.0, "link_ready_s": r1["link_ready_s"], "service_end_s": S1, "return_s": r1["return_s"],
         "relay_free_s": r1["relay_free_s"], "energy_free_s": r1["energy_free_s"], "energy_kwh": r1["energy_kwh"], "soc": r1["soc"]},
        {"id": "RS02", "site": "P3", "relay_id": "R01", "energy_id": "R-B3", "lon": P3.lon, "lat": P3.lat, "hover_alt_m": P3.alt,
         "depart_s": r2["depart_s"], "link_ready_s": r2["link_ready_s"], "service_end_s": S2, "return_s": r2["return_s"],
         "relay_free_s": r2["relay_free_s"], "energy_free_s": r2["energy_free_s"], "energy_kwh": r2["energy_kwh"], "soc": r2["soc"]},
        {"id": "RS03", "site": "P2", "relay_id": "R02", "energy_id": "R-B2", "lon": P2.lon, "lat": P2.lat, "hover_alt_m": P2.alt,
         "depart_s": 0.0, "link_ready_s": r3["link_ready_s"], "service_end_s": S3, "return_s": r3["return_s"],
         "relay_free_s": r3["relay_free_s"], "energy_free_s": r3["energy_free_s"], "energy_kwh": r3["energy_kwh"], "soc": r3["soc"]},
    ]
    pub = json.load(open(r"D:\git\math_modeling\UAV\results\问题三_参考口径\主方案_完整方案.json", encoding="utf-8"))
    starts = [t["start_s"] for t in pub["transport"]]
    i22 = next(i for i, t in enumerate(pub["transport"]) if t["id"] == "T22"); starts[i22] = 5899.0
    transport = []; deliveries = {}; errs = []
    for t, st in zip(pub["transport"], starts):
        ev = evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)
        dr = D["drones"][t["model"]]
        if ev["mass_kg"] > dr["payload"] + 1e-9 or ev["volume_m3"] > dr["volume"] + 1e-9: errs.append("载荷 " + t["id"])
        if ev["return_soc"] < dr["reserve"] - 1e-9: errs.append("SOC " + t["id"])
        transport.append({"id": t["id"], "model": t["model"], "stops": t["stops"], "uav": t["uav"], "battery": t["battery"],
                          "start_s": st, "return_s": st + ev["duration_s"], "energy_kwh": ev["energy_kwh"], "soc": ev["return_soc"],
                          "charge_end_s": st + (t["charge_end_s"] - t["start_s"]), "mass_kg": ev["mass_kg"], "volume_m3": ev["volume_m3"]})
        for b, off in ev["delivery_offsets_s"].items(): deliveries[b] = st + off
    hard = sum(max(0, deliveries[b] - D["boxes"][b]["hard"]) for b in deliveries if D["boxes"][b]["hard"] is not None)
    tardy = sum(D["boxes"][b]["weight"] * max(0, deliveries[b] - D["boxes"][b]["due"]) for b in deliveries)
    ms = max([t["return_s"] for t in transport] + [r["return_s"] for r in relays])
    E = sum(t["energy_kwh"] for t in transport) + sum(r["energy_kwh"] for r in relays)
    # 资源不重叠
    for key, ek in (("uav","return_s"), ("battery","charge_end_s"), ("relay_id","relay_free_s"), ("energy_id","energy_free_s")):
        iv = defaultdict(list); rows = transport if key in ("uav","battery") else relays
        for x in rows: iv[x[key]].append((x["start_s"] if key in ("uav","battery") else x["depart_s"], x[ek], x.get("id") or x.get("relay_id")))
        for name, xs in iv.items():
            xs.sort()
            for a, b in zip(xs, xs[1:]):
                if b[0] < a[1] - 1e-8: errs.append("重叠 %s %s %s" % (key, a[2], b[2]))
    tot_pw, det_pw = C.check_plan([{"id": t["id"], "model": t["model"], "stops": t["stops"], "start_s": t["start_s"]} for t in transport], relays, 0.5)
    uc, cert_, det_uc = QC.run([{"id": t["id"], "model": t["model"], "stops": t["stops"], "start_s": t["start_s"]} for t in transport], relays, 0.5)
    print("== 修复版 3 中继方案 ==")
    print("运输 %d + 中继 %d；联合完成 %.6f s（运输最晚 %.3f / 中继最晚 %.3f）" % (
        len(transport), len(relays), ms, max(t["return_s"] for t in transport), max(r["return_s"] for r in relays)))
    print("总能耗 %.6f kWh（运输 %.4f + 中继 %.4f）" % (E, sum(t["energy_kwh"] for t in transport), sum(r["energy_kwh"] for r in relays)))
    print("hard=%.6f tardy=%.6f 箱=%d；物理/资源校验: %s" % (hard, tardy, len(deliveries), "PASS" if not errs else errs[:6]))
    print("严格逐点通信(0.5 s，含单点/边界): 缺口 %.6f s" % tot_pw)
    print("连续认证: 已认证 %.3f s；未认证 %.3f s（%d 架次的过渡段）" % (cert_, uc, len(det_uc)))
    json.dump({"transport": transport, "relays": relays, "deliveries": deliveries,
               "metrics": {"hard_excess_s": hard, "weighted_tardiness": tardy, "makespan_s": ms, "energy_kwh": E,
                           "transport_sorties": len(transport), "relay_sorties": len(relays), "boxes": len(deliveries),
                           "pointwise_gap_s": tot_pw, "continuous_certified_s": cert_, "continuous_uncertified_s": uc},
               "uncertified_intervals": [{"task": x[0], "seconds": x[1]} for x in det_uc]},
              open(os.path.join(OUT, "plan_3relay_fixed_final.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved plan_3relay_fixed_final.json")
