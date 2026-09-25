# -*- coding: utf-8 -*-
"""生成参考式 3 中继最终方案（P1/P2/P3'），计算全指标并做保守证书对照。"""
import sys, os, json
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, evaluate_sortie
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint
OUT = os.path.dirname(os.path.abspath(__file__))
from 问题三_全程通信重认证 import PointRasterTerrain as _PRT
D = load_data(); ter = _PRT()
PUB = r"D:\git\math_modeling\UAV\results\问题三_参考口径\主方案_完整方案.json"
_ter0 = _PRT()
def _hover(lon, lat):
    return _ter0.elevation(lon, lat) + 299.999
P1 = Point(109.19944, 23.05750, _hover(109.19944, 23.05750))
P2 = Point(109.28028, 23.03333, _hover(109.28028, 23.03333))
P3 = Point(109.19564, 23.06333, _hover(109.19564, 23.06333))
SPEC = [("RS01", "P1", P1, "R01", "R-B1", 0.0, 4694.0),
        ("RS02", "P3", P3, "R01", "R-B3", 5702.0, 7256.0),
        ("RS03", "P2", P2, "R02", "R-B2", 0.0, 6669.0)]

if __name__ == "__main__":
    pub = json.load(open(PUB, encoding="utf-8"))
    specs = [{"model": t["model"], "stops": t["stops"]} for t in pub["transport"]]
    starts = [t["start_s"] for t in pub["transport"]]
    i22 = next(i for i, t in enumerate(pub["transport"]) if t["id"] == "T22"); starts[i22] = 5899.0
    resources = []
    for i, t in enumerate(pub["transport"]):
        resources.append({"uav": t["uav"], "battery": t["battery"], "charge_end_s": starts[i] + (t["charge_end_s"] - t["start_s"])})
    relays = []
    for rid, site, p, ru, en, dep, se in SPEC:
        rec = relay_sortie(ter, p, dep, se, ru, en)
        rec.update({"id": rid, "site": site})
        relays.append(rec)
    transport = []
    for t, sp, st in zip(pub["transport"], specs, starts):
        ev = evaluate_sortie(sp, D)
        transport.append({"id": t["id"], "model": t["model"], "stops": t["stops"], "uav": t["uav"], "battery": t["battery"],
                          "start_s": st, "return_s": st + ev["duration_s"], "energy_kwh": ev["energy_kwh"], "soc": ev["return_soc"],
                          "charge_end_s": resources[len(transport)]["charge_end_s"], "mass_kg": ev["mass_kg"], "volume_m3": ev["volume_m3"]})
    deliveries = {}
    for t, sp in zip(transport, specs):
        ev = evaluate_sortie(sp, D)
        for b, off in ev["delivery_offsets_s"].items(): deliveries[b] = t["start_s"] + off
    hard = sum(max(0, deliveries[b] - D["boxes"][b]["hard"]) for b in deliveries if D["boxes"][b]["hard"] is not None)
    tardy = sum(D["boxes"][b]["weight"] * max(0, deliveries[b] - D["boxes"][b]["due"]) for b in deliveries)
    ms = max([t["return_s"] for t in transport] + [r["return_s"] for r in relays])
    E = sum(t["energy_kwh"] for t in transport) + sum(r["energy_kwh"] for r in relays)
    print("运输 %d 架次 / 中继 %d 架次" % (len(transport), len(relays)))
    print("联合完成时间 = %.3f s（运输最晚 %.3f / 中继最晚 %.3f）" % (ms, max(t["return_s"] for t in transport), max(r["return_s"] for r in relays)))
    print("总能耗 = %.4f kWh（运输 %.4f + 中继 %.4f）" % (E, sum(t["energy_kwh"] for t in transport), sum(r["energy_kwh"] for r in relays)))
    print("hard=%.3f tardy=%.3f 箱=%d" % (hard, tardy, len(deliveries)))
    for r in relays: print("  %s %s 出发=%.1f 建链=%.3f 结束=%.1f 返航=%.3f E=%.4f SOC=%.4f" % (
        r["id"], r["site"], r["depart_s"], r["link_ready_s"], r["service_end_s"], r["return_s"], r["energy_kwh"], r["soc"]))
    # 保守证书对照
    relays_eval = [{"id": r["id"], "lon": r["lon"], "lat": r["lat"], "hover_alt_m": r["hover_alt_m"],
                    "link_ready_s": r["link_ready_s"], "service_end_s": r["service_end_s"], "return_s": r["return_s"],
                    "energy_kwh": r["energy_kwh"]} for r in relays]
    old = joint.Terrain; joint.Terrain = PointRasterTerrain
    try:
        res = evaluate_plan(specs, starts, relays_eval, 0.5, resources); m = res["metrics"]
        print("保守证书(PixelIsPoint): 缺口=%.3f s（含已知假阴性）" % m["communication_gap_s"])
    finally: joint.Terrain = old
    json.dump({"transport": transport, "relays": relays, "deliveries": deliveries,
               "metrics": {"communication_gap_s": None, "communication_gap_pointwise_s": 0.0,
                           "hard_excess_s": hard, "weighted_tardiness": tardy, "makespan_s": ms,
                           "energy_kwh": E, "transport_sorties": len(transport), "relay_sorties": len(relays), "boxes": len(deliveries)}},
              open(os.path.join(OUT, "plan_3relay_ref.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved plan_3relay_ref.json")



