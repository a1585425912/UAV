# -*- coding: utf-8 -*-
"""对问题三任意方案做独立物理/资源/通信复核。用法: python q3_validate.py <方案.json>"""
import sys, os, json, math
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, evaluate_sortie, charge_time
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint
D = load_data(); ter = Terrain()

def main(path):
    o = json.load(open(path, encoding="utf-8")); errs = []
    print("metrics(文件):", o.get("metrics"))
    # 运输
    delivery = {}
    for t in o["transport"]:
        sp = {"model": t["model"], "stops": t["stops"]}
        ev = evaluate_sortie(sp, D)
        if ev is None: errs.append("物理 " + t["id"]); continue
        dr = D["drones"][t["model"]]
        if ev["mass_kg"] > dr["payload"] + 1e-9 or ev["volume_m3"] > dr["volume"] + 1e-9: errs.append("载荷 " + t["id"])
        if ev["return_soc"] < dr["reserve"] - 1e-9: errs.append("SOC " + t["id"])
        for b, off in ev["delivery_offsets_s"].items(): delivery[b] = t["start_s"] + off
    hard = sum(max(0, delivery[b] - D["boxes"][b]["hard"]) for b in delivery if D["boxes"][b]["hard"] is not None)
    tardy = sum(D["boxes"][b]["weight"] * max(0, delivery[b] - D["boxes"][b]["due"]) for b in delivery)
    print("运输: 箱=%d hard=%.6f tardy=%.6f" % (len(delivery), hard, tardy))
    if len(delivery) != 80: errs.append("箱数")
    # 中继
    for r in o["relays"]:
        ground = ter.elevation(r["lon"], r["lat"])
        if r["hover_alt_m"] - ground > 300 + 1e-6: errs.append(r["id"] + " 离地")
        rec = relay_sortie(ter, Point(r["lon"], r["lat"], r["hover_alt_m"]), r["depart_s"], r["service_end_s"], r["relay_id"], r["energy_id"])
        if abs(rec["energy_kwh"] - r["energy_kwh"]) > 1e-6: errs.append(r["id"] + " 能耗")
        if rec["soc"] < 0.2 - 1e-9: errs.append(r["id"] + " SOC")
        print("  %s 离地=%.1f 能耗=%.4f SOC=%.4f 返航=%.3f" % (r["id"], r["hover_alt_m"]-ground, rec["energy_kwh"], rec["soc"], rec["return_s"]))
    # 资源不重叠
    for key, ek in (("uav","return_s"), ("battery","charge_end_s"), ("relay_id","relay_free_s"), ("energy_id","energy_free_s")):
        iv = defaultdict(list)
        rows = o["transport"] if key in ("uav","battery") else o["relays"]
        for x in rows: iv[x[key]].append((x["start_s"] if key in ("uav","battery") else x["depart_s"], x[ek], x.get("id") or x.get("relay_id")))
        for name, xs in iv.items():
            xs.sort()
            for a, b in zip(xs, xs[1:]):
                if b[0] < a[1] - 1e-8: errs.append("重叠 %s %s %s" % (key, a[2], b[2]))
    # 通信
    specs = [{"model": t["model"], "stops": t["stops"]} for t in o["transport"]]
    starts = [t["start_s"] for t in o["transport"]]
    resources = [{"uav": t["uav"], "battery": t["battery"], "charge_end_s": t["charge_end_s"]} for t in o["transport"]]
    old = joint.Terrain; joint.Terrain = PointRasterTerrain
    try:
        res = evaluate_plan(specs, starts, o["relays"], 0.5, resources); m = res["metrics"]
    finally:
        joint.Terrain = old
    print("PixelIsPoint 重认证: 缺口=%.6f 完成=%.6f E=%.6f 硬=%.1f 延误=%.1f" % (
        m["communication_gap_s"], m["makespan_s"], m["energy_kwh"], m["hard_excess_s"], m["weighted_tardiness"]))
    if m["communication_gap_s"] > 1e-6: errs.append("通信缺口")
    print("独立校验:", "PASS" if not errs else errs[:8])

if __name__ == "__main__":
    main(sys.argv[1])
