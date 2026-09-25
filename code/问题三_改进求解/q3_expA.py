# -*- coding: utf-8 -*-
"""实验A：压缩中继无用悬停尾部（只改服务结束，运输计划与点位固定），并重新做连续通信认证。

只允许调整 service_end（及其派生的返航/能耗/SOC/充满/周转），不修改运输计划与中继点位。
认证使用与发布方案一致的 PixelIsPoint 口径；同时报告默认 Terrain 口径。
"""
import sys, os, json, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合调度 import evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
ROOT = r"D:\git\math_modeling\UAV"
PUB = os.path.join(ROOT, "results", "问题三_参考口径", "主方案_完整方案.json")
import 问题三_联合调度 as joint

def rerun(specs, starts, relays, resources, terrain_cls):
    old = joint.Terrain
    joint.Terrain = terrain_cls
    try:
        return evaluate_plan(specs, starts, relays, 0.5, resources)
    finally:
        joint.Terrain = old

def rebuild_relay(terrain, base, service_end):
    r = dict(base)
    rec = relay_sortie(terrain, Point(base["lon"], base["lat"], base["hover_alt_m"]),
                       base["depart_s"], service_end, base["relay_id"], base["energy_id"])
    for k in ("service_end_s", "return_s", "relay_free_s", "energy_free_s", "energy_kwh", "soc"):
        r[k] = rec[k]
    return r

if __name__ == "__main__":
    ter = Terrain(); data = load_data()
    pub = json.load(open(PUB, encoding="utf-8"))
    specs = [{"model": t["model"], "stops": t["stops"]} for t in pub["transport"]]
    starts = [t["start_s"] for t in pub["transport"]]
    resources = [{"uav": t["uav"], "battery": t["battery"], "charge_end_s": t["charge_end_s"]} for t in pub["transport"]]
    last = {}
    for c in pub["communications"]:
        if c["status"] == "中继":
            last[c["relay_id"]] = max(last.get(c["relay_id"], 0.0), c["end_s"])
    print("最后已分配需求:", {k: round(v,6) for k,v in last.items()})
    # 原始
    base_p = rerun(specs, starts, pub["relays"], resources, PointRasterTerrain)
    print("原始(Point): 缺口=%.6f 联合完成=%.6f E=%.6f" % (
        base_p["metrics"]["communication_gap_s"], base_p["metrics"]["makespan_s"], base_p["metrics"]["energy_kwh"]))
    # 压缩：把每条中继 service_end 设到其"最后已分配需求"（若无则不动）
    relays = []
    for r in pub["relays"]:
        se = r["service_end_s"]
        if r["id"] in last and last[r["id"]] < se - 1e-9:
            se = last[r["id"]]
        relays.append(rebuild_relay(ter, r, se))
    comp = rerun(specs, starts, relays, resources, PointRasterTerrain)
    print("压缩后(Point): 缺口=%.6f 联合完成=%.6f E=%.6f" % (
        comp["metrics"]["communication_gap_s"], comp["metrics"]["makespan_s"], comp["metrics"]["energy_kwh"]))
    for r in relays:
        print("   %s %s 服务结束 %.3f 返航 %.3f 能耗 %.6f SOC %.4f 充满 %.3f" % (
            r["id"], r["site"], r["service_end_s"], r["return_s"], r["energy_kwh"], r["soc"], r["energy_free_s"]))
    if comp["metrics"]["communication_gap_s"] > 1e-6:
        print(">>> 压缩产生缺口，需回退/细化")
    else:
        json.dump({"transport": pub["transport"], "relays": relays, "deliveries": pub["deliveries"],
                   "communications": comp["communications"], "metrics": comp["metrics"]},
                  open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "expA_compressed.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(">>> 已保存 expA_compressed.json")
    # 默认 Terrain 对照
    try:
        cd = rerun(specs, starts, relays, resources, Terrain)
        print("压缩后(默认Terrain): 缺口=%.6f 完成=%.6f" % (cd["metrics"]["communication_gap_s"], cd["metrics"]["makespan_s"]))
    except Exception as e:
        print("默认Terrain认证异常:", e)
