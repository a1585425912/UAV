# -*- coding: utf-8 -*-
"""用 B 型重排（T22 前移）取消 RS04，合成 3 中继方案并做 PixelIsPoint 连续认证。"""
import sys, os, json, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 问题二_调度核心 import load_data, evaluate_sortie, charge_time
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint
from q3_b_sched import sched, norm
ROOT = r"D:\git\math_modeling\UAV"
PUB = os.path.join(ROOT, "results", "问题三_参考口径", "主方案_完整方案.json")

def run(specs, starts, relays, resources):
    old = joint.Terrain; joint.Terrain = PointRasterTerrain
    try: return evaluate_plan(specs, starts, relays, 0.5, resources)
    finally: joint.Terrain = old

def build_res(spec, start):
    ev = evaluate_sortie(spec, D)
    return start + ev["duration_s"] + charge_time(ev["return_soc"], D["batteries"][spec["model"]]["full_charge_s"])

if __name__ == "__main__":
    D = load_data(); ter = Terrain()
    pub = json.load(open(PUB, encoding="utf-8"))
    specs = [{"model": t["model"], "stops": t["stops"]} for t in pub["transport"]]
    b_idx = [i for i, s in enumerate(specs) if s["model"] == "B"]
    b_specs = [specs[i] for i in b_idx]
    i22 = next(j for j, s in enumerate(b_specs) if b_specs[j] and True)  # placeholder
    i22 = next(j for j, t in enumerate([pub["transport"][i] for i in b_idx]) if t["id"] == "T22")
    relays3 = [r for r in pub["relays"] if r["id"] != "RS04"]
    best = None
    for deadline in [3104.4, 2600.0, 2000.0]:
        r = sched(b_specs, "B", (i22, deadline), tl=60)
        if not r.get("starts"): print("deadline", deadline, "无解"); continue
        starts = [t["start_s"] for t in pub["transport"]]
        resources = [{"uav": t["uav"], "battery": t["battery"], "charge_end_s": t["charge_end_s"]} for t in pub["transport"]]
        for j, i in enumerate(b_idx):
            starts[i] = max(0.0, r["starts"][j])
            resources[i] = {"uav": r["assign"][j]["uav"], "battery": r["assign"][j]["battery"],
                            "charge_end_s": build_res(specs[i], starts[i])}
        try:
            res = run(specs, starts, relays3, resources); m = res["metrics"]
        except Exception as e:
            print("deadline", deadline, "异常", e); continue
        ok = m["communication_gap_s"] <= 1e-6 and m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6
        print("deadline=%7.1f T22start=%8.3f -> 缺口=%9.3f 完成=%9.3f E=%7.4f 硬超=%.1f 延误=%.1f 可行=%s" % (
            deadline, starts[b_idx[i22]], m["communication_gap_s"], m["makespan_s"], m["energy_kwh"],
            m["hard_excess_s"], m["weighted_tardiness"], ok), flush=True)
        if ok and (best is None or m["makespan_s"] < best[0]):
            best = (m["makespan_s"], m["energy_kwh"], res, starts, resources)
    if best:
        ms, en, res, starts, resources = best
        print("\n>>> 3 中继最优: 完成=%.3f E=%.4f" % (ms, en))
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan_3relay.json")
        json.dump({"transport": res["transport"], "relays": res["relays"], "deliveries": res["deliveries"],
                   "communications": res["communications"], "metrics": res["metrics"]}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("saved", out)
        for t in sorted(res["transport"], key=lambda x: x["start_s"]):
            print("   %s %s %-10s %8.3f-%8.3f uav=%s bat=%s" % (t["id"], t["model"], "-".join(s["area"] for s in t["stops"]), t["start_s"], t["return_s"], t.get("uav"), t.get("battery")))
    else:
        print(">>> 未找到可行 3 中继方案")

