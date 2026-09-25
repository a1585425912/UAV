# -*- coding: utf-8 -*-
"""q3_recheck：第三问已发布基准的独立复算 + SITES/口径差异清单（只读）。"""
import sys, os, json, math
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, evaluate_sortie, charge_time
from 问题三_通信核心 import Terrain, Point, load_nodes, load_parameters, certified_link
from 问题三_联合调度 import SITES, evaluate_plan
from 问题三_全程通信重认证 import PointRasterTerrain
ROOT = r"D:\git\math_modeling\UAV"
PUB = os.path.join(ROOT, "results", "问题三_参考口径", "主方案_完整方案.json")

def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}

def main():
    data = load_data(); pub = json.load(open(PUB, encoding="utf-8"))
    print("已发布 metrics:", pub["metrics"])
    print()
    # ---- 1. 运输物理复算 ----
    specs = [norm(t) for t in pub["transport"]]
    starts = [t["start_s"] for t in pub["transport"]]
    resources = [{"uav": t["uav"], "battery": t["battery"], "charge_end_s": t["charge_end_s"]} for t in pub["transport"]]
    delivery = {}; errs = []
    for t, sp, st in zip(pub["transport"], specs, starts):
        ev = evaluate_sortie(sp, data)
        if ev is None: errs.append("物理不可行 " + t["id"]); continue
        for bid, off in ev["delivery_offsets_s"].items(): delivery[bid] = st + off
        if abs(ev["energy_kwh"] - t["energy_kwh"]) > 1e-6: errs.append("能耗不一致 " + t["id"])
        if abs(ev["return_soc"] - t["soc"]) > 1e-9: errs.append("SOC不一致 " + t["id"])
    if len(delivery) != 80 or set(delivery) != set(data["boxes"]): errs.append("箱覆盖")
    hard = sum(max(0, delivery[b] - data["boxes"][b]["hard"]) for b in delivery if data["boxes"][b]["hard"] is not None)
    tardy = sum(data["boxes"][b]["weight"] * max(0, delivery[b] - data["boxes"][b]["due"]) for b in delivery)
    print("[运输] 80箱=%s  hard=%.6f tardy=%.6f" % (len(delivery) == 80, hard, tardy))
    # 资源不重叠
    for key, ek in (("uav", "return_s"), ("battery", "charge_end_s")):
        iv = defaultdict(list)
        for t in pub["transport"]: iv[t[key]].append((t["start_s"], t[ek], t["id"]))
        for name, xs in iv.items():
            xs.sort()
            for a, b in zip(xs, xs[1:]):
                if b[0] < a[1] - 1e-8: errs.append("运输%s重叠 %s %s" % (key, a[2], b[2]))
    print("[运输] 复算错误:", errs if errs else "无")
    # ---- 2. 中继复算 ----
    from 问题三_通信核心 import relay_sortie
    from openpyxl import load_workbook
    ter = Terrain()
    print()
    print("[中继] 逐条复算（默认 Terrain 像元口径）:")
    rerrs = []
    for r in pub["relays"]:
        pt = Point(r["lon"], r["lat"], r["hover_alt_m"])
        ground = ter.elevation(r["lon"], r["lat"])
        try:
            rec = relay_sortie(ter, pt, r["depart_s"], r["service_end_s"], r["relay_id"], r["energy_id"])
            dE = abs(rec["energy_kwh"] - r["energy_kwh"]); dS = abs(rec["soc"] - r["soc"])
            print("  %s site=%s 离地=%.1f m 能耗 %.6f/%.6f Δ=%.2e SOC %.4f/%.4f Δ=%.2e 返航 %.1f/%.1f" % (
                r["id"], r["site"], r["hover_alt_m"] - ground, rec["energy_kwh"], r["energy_kwh"], dE,
                rec["soc"], r["soc"], dS, rec["return_s"], r["return_s"]))
            if abs(rec["return_s"] - r["return_s"]) > 1e-6: rerrs.append(r["id"] + " 返航时刻")
            if r["hover_alt_m"] - ground > 300 + 1e-6: rerrs.append(r["id"] + " 离地超限")
        except Exception as e:
            print("  %s 复算异常: %s" % (r["id"], e)); rerrs.append(r["id"] + " " + str(e))
    # 中继资源
    for key in ("relay_id", "energy_id"):
        iv = defaultdict(list)
        for r in pub["relays"]:
            end = r["relay_free_s"] if key == "relay_id" else r["energy_free_s"]
            iv[r[key]].append((r["depart_s"], end, r["id"]))
        for name, xs in iv.items():
            xs.sort()
            for a, b in zip(xs, xs[1:]):
                if b[0] < a[1] - 1e-8: rerrs.append("中继%s重叠 %s %s" % (key, a[2], b[2]))
    print("[中继] 复算错误:", rerrs if rerrs else "无")
    # ---- 3. 两种 DEM 口径的连续认证 ----
    print()
    import 问题三_联合调度 as joint
    old = joint.Terrain
    try:
        base = evaluate_plan(specs, starts, pub["relays"], 0.5, resources)
        print("[认证/默认Terrain Area] 缺口=%.6f s  联合完成=%.6f  E=%.6f  运输%d 中继%d" % (
            base["metrics"]["communication_gap_s"], base["metrics"]["makespan_s"], base["metrics"]["energy_kwh"],
            base["metrics"]["transport_sorties"], base["metrics"]["relay_sorties"]))
    finally:
        joint.Terrain = PointRasterTerrain
        try:
            pnt = evaluate_plan(specs, starts, pub["relays"], 0.5, resources)
            print("[认证/PixelIsPoint]  缺口=%.6f s  联合完成=%.6f  E=%.6f" % (
                pnt["metrics"]["communication_gap_s"], pnt["metrics"]["makespan_s"], pnt["metrics"]["energy_kwh"]))
        finally:
            joint.Terrain = old
    # ---- 4. SITES vs 发布坐标 ----
    print()
    print("[差异] 源码 SITES vs 已发布中继坐标:")
    for site, src in SITES.items():
        pubr = next((r for r in pub["relays"] if r["site"] == site), None)
        if pubr is None: print("  %s: 发布无此点位" % site); continue
        dlon = abs(src.lon - pubr["lon"]) * 111320 * math.cos(math.radians(23.05))
        dlat = abs(src.lat - pubr["lat"]) * 111320
        print("  %-2s 源码(%.6f,%.6f,h=%.1f) 发布(%.6f,%.6f,h=%.1f) 偏差=%.1f m  悬停海拔差=%.1f m" % (
            site, src.lon, src.lat, src.alt, pubr["lon"], pubr["lat"], pubr["hover_alt_m"],
            math.hypot(dlon, dlat), src.alt - pubr["hover_alt_m"]))

if __name__ == "__main__":
    main()
