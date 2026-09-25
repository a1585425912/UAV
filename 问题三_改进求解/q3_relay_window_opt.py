# -*- coding: utf-8 -*-
"""固定运输方案，逐条压缩中继服务窗口（坐标下降 + 二分）。
链式依赖：RS03.depart = RS01.relay_free；RS04.depart = RS02.relay_free。
"""
import sys, os, json, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint
ROOT = r"D:\git\math_modeling\UAV"
PUB = os.path.join(ROOT, "results", "问题三_参考口径", "主方案_完整方案.json")
ter = Terrain()

def run(specs, starts, relays, resources):
    old = joint.Terrain; joint.Terrain = PointRasterTerrain
    try: return evaluate_plan(specs, starts, relays, 0.5, resources)
    finally: joint.Terrain = old

def rebuild(pub, s1, s2, s3, s4):
    """按窗口重算 4 条中继（含链式 depart）。"""
    base = {r["id"]: r for r in pub["relays"]}
    def mk(rid, dep, se):
        b = base[rid]
        rec = relay_sortie(ter, Point(b["lon"], b["lat"], b["hover_alt_m"]), dep, se, b["relay_id"], b["energy_id"])
        rec.update({"id": rid, "site": b["site"]})
        return rec
    r1 = mk("RS01", 0.0, s1)
    r2 = mk("RS02", 0.0, s2)
    r3 = mk("RS03", r1["relay_free_s"], s3)
    r4 = mk("RS04", r2["relay_free_s"], s4)
    return [r1, r2, r3, r4]

def feasible(specs, starts, relays, resources):
    try:
        m = run(specs, starts, relays, resources)["metrics"]
        return (m["communication_gap_s"] <= 1e-6 and m["hard_excess_s"] <= 1e-6
                and m["weighted_tardiness"] <= 1e-6), m
    except Exception:
        return False, None

if __name__ == "__main__":
    pub = json.load(open(PUB, encoding="utf-8"))
    specs = [{"model": t["model"], "stops": t["stops"]} for t in pub["transport"]]
    starts = [t["start_s"] for t in pub["transport"]]
    resources = [{"uav": t["uav"], "battery": t["battery"], "charge_end_s": t["charge_end_s"]} for t in pub["transport"]]
    cur = {r["id"]: r["service_end_s"] for r in pub["relays"]}
    order = ["RS04", "RS03", "RS02", "RS01"]
    for sweep in range(3):
        changed = False
        for rid in order:
            lo = 0.0  # 下界：link_ready
            base_relay = {r["id"]: r for r in pub["relays"]}[rid]
            lo = base_relay["link_ready_s"]
            hi = cur[rid]
            ok_hi, m = feasible(specs, starts, rebuild(pub, cur["RS01"], cur["RS02"], cur["RS03"], cur["RS04"]), resources)
            if not ok_hi: print(rid, "当前窗口已不可行？"); continue
            for _ in range(20):
                mid = (lo + hi) / 2
                trial = dict(cur); trial[rid] = mid
                ok, _ = feasible(specs, starts, rebuild(pub, trial["RS01"], trial["RS02"], trial["RS03"], trial["RS04"]), resources)
                if ok: hi = mid
                else: lo = mid
            if hi < cur[rid] - 1e-6:
                cur[rid] = hi; changed = True
            print("  sweep%d %s -> %.3f (%.1f s 压缩)" % (sweep, rid, cur[rid], base_relay["service_end_s"] - cur[rid]), flush=True)
        if not changed: break
    relays = rebuild(pub, cur["RS01"], cur["RS02"], cur["RS03"], cur["RS04"])
    res = run(specs, starts, relays, resources); m = res["metrics"]
    print("\n最终: 缺口=%.6f 完成=%.6f E=%.6f 运输=%d 中继=%d" % (
        m["communication_gap_s"], m["makespan_s"], m["energy_kwh"], m["transport_sorties"], m["relay_sorties"]))
    for r in relays: print("  %s %s end=%.3f depart=%.3f ready=%.3f return=%.3f E=%.4f SOC=%.4f" % (
        r["id"], r["site"], r["service_end_s"], r["depart_s"], r["link_ready_s"], r["return_s"], r["energy_kwh"], r["soc"]))
    json.dump({"transport": res["transport"], "relays": res["relays"], "deliveries": res["deliveries"],
               "communications": res["communications"], "metrics": m},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan_windows_opt.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("saved plan_windows_opt.json")
