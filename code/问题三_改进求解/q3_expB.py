# -*- coding: utf-8 -*-
"""实验B：通过前移 T22(S015) 把其通信需求并入 RS03(北) 窗口，取消 RS04。

固定其余 21 条运输与三个点位；调整 T22 开始时刻（受 U05/B-B1 资源可用性约束）与 RS03 服务结束，
重新计算 RS03 的返航/能耗/SOC/充满，并在 PixelIsPoint 口径下重新认证全部运输轨迹。
"""
import sys, os, json, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, evaluate_sortie, charge_time
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint
ROOT = r"D:\git\math_modeling\UAV"
PUB = os.path.join(ROOT, "results", "问题三_参考口径", "主方案_完整方案.json")

def run(specs, starts, relays, resources):
    old = joint.Terrain; joint.Terrain = PointRasterTerrain
    try: return evaluate_plan(specs, starts, relays, 0.5, resources)
    finally: joint.Terrain = old

if __name__ == "__main__":
    data = load_data(); ter = Terrain()
    pub = json.load(open(PUB, encoding="utf-8"))
    specs = [{"model": t["model"], "stops": t["stops"]} for t in pub["transport"]]
    base_starts = [t["start_s"] for t in pub["transport"]]
    idx22 = next(i for i, t in enumerate(pub["transport"]) if t["id"] == "T22")
    # 资源约束：U05 在 T11 后空闲；B-B1 在 T05 后充满
    t11 = next(t for t in pub["transport"] if t["uav"] == "U05" and t["id"] != "T22")
    t05 = next(t for t in pub["transport"] if t["battery"] == "B-B1" and t["id"] != "T22")
    uav_free = max(t["return_s"] for t in pub["transport"] if t["uav"] == "U05" and t["id"] != "T22")
    bat_free = max(t["charge_end_s"] for t in pub["transport"] if t["battery"] == "B-B1" and t["id"] != "T22")
    print("T22 资源最早可开始 = max(U05 %.1f, B-B1 %.1f) = %.1f" % (uav_free, bat_free, max(uav_free, bat_free)))
    # S015 时限
    s015 = {b: (v["due"], v["hard"]) for b, v in data["boxes"].items() if v["area"] == "S015"}
    print("S015 时限(due,hard):", s015)
    specs3 = [r for r in pub["relays"] if r["id"] != "RS04"]
    best = None
    for start22 in [5600.0, 5700.0, 5800.0, 5900.0, 6000.0]:
        if start22 < max(uav_free, bat_free) - 1e-9: continue
        for rs03_end in [7350.0, 7390.6, 7420.0, 7460.0]:
            starts = list(base_starts); starts[idx22] = start22
            # 资源重算（只影响 T22 的充满）
            resources = []
            for t, sp, st in zip(pub["transport"], specs, starts):
                ev = evaluate_sortie(sp, data)
                resources.append({"uav": t["uav"], "battery": t["battery"],
                                  "charge_end_s": st + ev["duration_s"] + charge_time(ev["return_soc"], data["batteries"][t["model"]]["full_charge_s"])})
            relays = []
            for r in specs3:
                rr = dict(r)
                if r["id"] == "RS03":
                    rec = relay_sortie(ter, Point(r["lon"], r["lat"], r["hover_alt_m"]), r["depart_s"], rs03_end, r["relay_id"], r["energy_id"])
                    for k in ("service_end_s", "return_s", "relay_free_s", "energy_free_s", "energy_kwh", "soc"): rr[k] = rec[k]
                relays.append(rr)
            try:
                res = run(specs, starts, relays, resources); m = res["metrics"]
            except Exception as e:
                print("start22=%.0f rs03_end=%.1f 异常 %s" % (start22, rs03_end, e)); continue
            ok = m["communication_gap_s"] <= 1e-6 and m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6
            print("start22=%7.1f rs03_end=%7.1f -> 缺口=%8.3f T=%9.3f E=%7.4f 可行=%s" % (
                start22, rs03_end, m["communication_gap_s"], m["makespan_s"], m["energy_kwh"], ok), flush=True)
            if ok and (best is None or m["makespan_s"] < best[0]):
                best = (m["makespan_s"], m["energy_kwh"], start22, rs03_end, res, starts, relays, resources)
    if best:
        ms, en, s22, re3, res, starts, relays, resources = best
        print("\n>>> 最优 3 中继: T22 start=%.1f, RS03 end=%.1f, 完成=%.3f, E=%.4f" % (s22, re3, ms, en))
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expB_3relay.json")
        json.dump({"transport": res["transport"], "relays": res["relays"], "deliveries": res["deliveries"],
                   "communications": res["communications"], "metrics": res["metrics"]}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("saved", out)
    else:
        print(">>> 未找到可行 3 中继组合")
