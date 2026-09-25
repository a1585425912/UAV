# -*- coding: utf-8 -*-
"""按参考解题过程第三问方案（22运输 + T22前移到5899 + 3条中继 P1/P2/P3）在统一口径下独立重认证。"""
import sys, os, json, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, evaluate_sortie, charge_time
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint
ROOT = r"D:\git\math_modeling\UAV"
PUB = os.path.join(ROOT, "results", "问题三_参考口径", "主方案_完整方案.json")

# 参考方案的三个点位与三条中继架次
REF_SITES = {
    "P1": Point(109.19944, 23.05750, 989.9),
    "P2": Point(109.28028, 23.03333, 677.3),
    "P3": Point(109.19444, 23.06333, 1036.2),
}
REF_RELAYS = [
    {"id": "RS01", "site": "P1", "relay_id": "R01", "energy_id": "R-B1", "link_ready_s": 1083.0, "service_end_s": 4694.0},
    {"id": "RS02", "site": "P3", "relay_id": "R01", "energy_id": "R-B3", "link_ready_s": 6670.0, "service_end_s": 7241.0},
    {"id": "RS03", "site": "P2", "relay_id": "R02", "energy_id": "R-B2", "link_ready_s": 732.0,  "service_end_s": 6669.0},
]

REF_RETURN = {"RS01": 5402.0, "RS02": 8019.0, "RS03": 7237.0}
REF_ENERGY = {"RS01": 1.458, "RS02": 0.568, "RS03": 2.118}
def mk_relays():
    out = []
    for r in REF_RELAYS:
        p = REF_SITES[r["site"]]
        out.append({"id": r["id"], "site": r["site"], "relay_id": r["relay_id"], "energy_id": r["energy_id"],
                    "lon": p.lon, "lat": p.lat, "hover_alt_m": p.alt,
                    "link_ready_s": r["link_ready_s"], "service_end_s": r["service_end_s"],
                    "return_s": REF_RETURN[r["id"]], "energy_kwh": REF_ENERGY[r["id"]]})
    return out

def run(specs, starts, relays, resources, terrain_cls):
    old = joint.Terrain; joint.Terrain = terrain_cls
    try: return evaluate_plan(specs, starts, relays, 0.5, resources)
    finally: joint.Terrain = old

if __name__ == "__main__":
    data = load_data(); ter = Terrain()
    pub = json.load(open(PUB, encoding="utf-8"))
    specs = [{"model": t["model"], "stops": t["stops"]} for t in pub["transport"]]
    starts = [t["start_s"] for t in pub["transport"]]
    i22 = next(i for i, t in enumerate(pub["transport"]) if t["id"] == "T22")
    starts[i22] = 5899.0
    resources = []
    for sp, st in zip(specs, starts):
        ev = evaluate_sortie(sp, data)
        resources.append({"uav": None, "battery": None, "charge_end_s": st + ev["duration_s"]})
    # 资源沿用发布（除 T22 充满时刻按新 start 平移）
    for i, t in enumerate(pub["transport"]):
        resources[i]["uav"] = t["uav"]; resources[i]["battery"] = t["battery"]
        resources[i]["charge_end_s"] = starts[i] + (t["charge_end_s"] - t["start_s"])
    relays = mk_relays()
    print("参考 3 中继点位悬停离地（默认 Terrain 口径）:")
    for k, p in REF_SITES.items():
        print("   %s (%.5f,%.5f) hover=%.1f  ground=%.1f  离地=%.1f" % (k, p.lon, p.lat, p.alt, ter.elevation(p.lon, p.lat), p.alt - ter.elevation(p.lon, p.lat)))
    for tag, tc in [("PixelIsPoint", PointRasterTerrain), ("默认Terrain", Terrain)]:
        try:
            res = run(specs, starts, relays, resources, tc); m = res["metrics"]
            ok = m["communication_gap_s"] <= 1e-6 and m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6
            print("[%s] 缺口=%.6f 完成=%.6f E=%.6f 硬=%.1f 延误=%.1f 可行=%s" % (
                tag, m["communication_gap_s"], m["makespan_s"], m["energy_kwh"], m["hard_excess_s"], m["weighted_tardiness"], ok))
            if m["communication_gap_s"] > 1e-6:
                for t in res["transport"]:
                    g = sum(b - a for a, b in t["gaps"])
                    if g > 1e-6: print("     GAP %s %s start=%.1f gap=%.3f" % (t["id"], t["model"], t["start_s"], g))
        except Exception as e:
            import traceback; traceback.print_exc()


