# -*- coding: utf-8 -*-
"""修复 T15 断链：延长 RS01 服务结束，沿链重算 R01→RS02，并做全量严格逐点检查。"""
import sys, os, json
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q3_certify as C
from 问题三_通信核心 import Point, relay_sortie
from 问题三_全程通信重认证 import PointRasterTerrain
OUT = os.path.dirname(os.path.abspath(__file__))
ter = PointRasterTerrain()
def hover(lon, lat): return ter.elevation(lon, lat) + 299.999
P1 = Point(109.19944, 23.05750, hover(109.19944, 23.05750))
P2 = Point(109.28028, 23.03333, hover(109.28028, 23.03333))
P3 = Point(109.19564, 23.06333, hover(109.19564, 23.06333))
S1 = 4694.5        # 原 4694.0 → 覆盖 T15 的 4694.246801
S2 = 7256.0
S3 = 6669.0
if __name__ == "__main__":
    r1 = relay_sortie(ter, P1, 0.0, S1, "R01", "R-B1")
    r2 = relay_sortie(ter, P3, r1["relay_free_s"], S2, "R01", "R-B3")
    r3 = relay_sortie(ter, P2, 0.0, S3, "R02", "R-B2")
    relays = [
        {"id": "RS01", "site": "P1", "lon": P1.lon, "lat": P1.lat, "hover_alt_m": P1.alt,
         "link_ready_s": r1["link_ready_s"], "service_end_s": S1, "depart_s": 0.0, "return_s": r1["return_s"],
         "relay_free_s": r1["relay_free_s"], "energy_kwh": r1["energy_kwh"], "soc": r1["soc"]},
        {"id": "RS02", "site": "P3", "lon": P3.lon, "lat": P3.lat, "hover_alt_m": P3.alt,
         "link_ready_s": r2["link_ready_s"], "service_end_s": S2, "depart_s": r2["depart_s"], "return_s": r2["return_s"],
         "relay_free_s": r2["relay_free_s"], "energy_kwh": r2["energy_kwh"], "soc": r2["soc"]},
        {"id": "RS03", "site": "P2", "lon": P2.lon, "lat": P2.lat, "hover_alt_m": P2.alt,
         "link_ready_s": r3["link_ready_s"], "service_end_s": S3, "depart_s": 0.0, "return_s": r3["return_s"],
         "relay_free_s": r3["relay_free_s"], "energy_kwh": r3["energy_kwh"], "soc": r3["soc"]},
    ]
    print("链路: RS01 free=%.3f   RS02 depart=%.3f ready=%.3f   RS03 ready=%.3f" % (
        r1["relay_free_s"], r2["depart_s"], r2["link_ready_s"], r3["link_ready_s"]))
    print("能耗: RS01 %.4f / RS02 %.4f / RS03 %.4f kWh；SOC %.4f/%.4f/%.4f" % (
        r1["energy_kwh"], r2["energy_kwh"], r3["energy_kwh"], r1["soc"], r2["soc"], r3["soc"]))
    pub = json.load(open(r"D:\git\math_modeling\UAV\results\问题三_参考口径\主方案_完整方案.json", encoding="utf-8"))
    starts = [t["start_s"] for t in pub["transport"]]
    i22 = next(i for i, t in enumerate(pub["transport"]) if t["id"] == "T22"); starts[i22] = 5899.0
    transport = [{"id": t["id"], "model": t["model"], "stops": t["stops"], "start_s": st} for t, st in zip(pub["transport"], starts)]
    tot, det = C.check_plan(transport, relays, 0.5)
    print("全量严格逐点(0.5 s)缺口 = %.6f s" % tot)
    for x in det: print("   ", x)
    # 细查历史上出过问题的架次（0.1 s）
    watch = ["T01", "T02", "T12", "T13", "T15", "T18", "T19", "T20", "T21", "T22"]
    tot2 = 0.0; det2 = []
    for t in transport:
        if t["id"] not in watch: continue
        gaps, ev = C.check_task(t, t["start_s"], relays, 0.1)
        g = sum(b - a for a, b, _ in gaps); tot2 += g
        if gaps: det2.append((t["id"], round(g, 6), [(round(a,3), round(b,3)) for a,b,_ in gaps]))
    print("重点架次 0.1 s 缺口 = %.6f s" % tot2)
    for x in det2: print("   ", x)
    json.dump({"transport": transport, "relays": relays}, open(os.path.join(OUT, "plan_3relay_fixed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved plan_3relay_fixed.json")
