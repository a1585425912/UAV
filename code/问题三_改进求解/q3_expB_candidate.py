# -*- coding: utf-8 -*-
"""实验B：独立复核"8115.197 s / 3 中继 / 75.5924 kWh"候选是否真实可行。"""
import sys, os, json, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data
from 问题三_通信核心 import Terrain, Point, relay_sortie
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed
from 问题三_联合调度 import SITES, evaluate_plan, relay_plan, transport_starts
from 问题三_全程通信重认证 import PointRasterTerrain
import 问题三_联合调度 as joint

def run(specs, starts, relays, resources, terrain_cls, res=0.5):
    old = joint.Terrain; joint.Terrain = terrain_cls
    try: return evaluate_plan(specs, starts, relays, res, resources)
    finally: joint.Terrain = old

if __name__ == "__main__":
    data = load_data(); ter = Terrain()
    specs, _, info = optimize_seed(data)
    starts, resources = transport_starts(specs, REFERENCE_STARTS, data)
    pub = json.load(open(r"D:\git\math_modeling\UAV\results\问题三_参考口径\主方案_完整方案.json", encoding="utf-8"))
    print("MILP:", info)
    print("早开工 vs 发布开工（前 8 条）:")
    for i, (s, r, sp) in enumerate(zip(starts, resources, specs)):
        pubt = pub["transport"][i]
        print("  T%02d %s %-12s 早=%9.3f 发布=%9.3f Δ=%+8.3f uav=%s/%s bat=%s/%s" % (
            i+1, sp["model"], "-".join(st["area"] for st in sp["stops"]), s, pubt["start_s"], s-pubt["start_s"],
            r["uav"], pubt["uav"], r["battery"], pubt["battery"]))
    print()
    rp_source = relay_plan(ter, 4695, 6260, 7315)     # 源码 SITES（北/西/东）
    pub_sites = {}
    for r in pub["relays"]:
        pub_sites.setdefault(r["site"], Point(r["lon"], r["lat"], r["hover_alt_m"]))
    # 用发布坐标重建 3 条中继（同样的服务窗口与资源链）
    rp_pub = []
    for rid, site, rid_uav, rid_eng, dep, se in [("RS01","西","R01","R-B1",0,4695),
                                                 ("RS02","东","R02","R-B2",0,6260),
                                                 ("RS03","北","R01","R-B3",None,7315)]:
        pt = pub_sites[site]
        if dep is None: dep = rp_pub[0]["relay_free_s"]
        rec = relay_sortie(ter, pt, dep, se, rid_uav, rid_eng)
        rec.update({"id": rid, "site": site})
        rp_pub.append(rec)
    combos = [
        ("源码SITES(3中继) + 默认Terrain", rp_source, Terrain),
        ("源码SITES(3中继) + PixelIsPoint", rp_source, PointRasterTerrain),
        ("发布坐标(3中继) + PixelIsPoint", rp_pub, PointRasterTerrain),
        ("发布坐标(4中继) + PixelIsPoint", pub["relays"], PointRasterTerrain),
        ("发布坐标(4中继) + 默认Terrain", pub["relays"], Terrain),
    ]
    for tag, relays, tc in combos:
        try:
            r = run(specs, starts, relays, resources, tc)
            m = r["metrics"]
            ok = m["communication_gap_s"] <= 1e-6 and m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6
            print("%-34s 缺口=%9.3f 完成=%9.3f E=%8.4f 运输=%d 中继=%d 可行=%s" % (
                tag, m["communication_gap_s"], m["makespan_s"], m["energy_kwh"],
                m["transport_sorties"], len(relays), ok), flush=True)
        except Exception as e:
            print("%-34s 异常 %s" % (tag, e), flush=True)
