import sys, os, json, csv
from collections import Counter
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, decode, evaluate_sortie
ROOT = r"D:\git\math_modeling\UAV"; HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "results", "问题二_改进方案"); D = load_data()
def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
GEOM = {(r["起点"], r["终点"]): r for r in rd(os.path.join(ROOT, "results", "问题二_参考口径", "有向航段几何参数.csv"))}
def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}
seen = set(); cands = []
def add(specs, src):
    specs = [norm(s) for s in specs]
    sig = frozenset((s["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in s["stops"])) for s in specs)
    if sig in seen: return
    p = decode(specs, D, require_all=True)
    if p is None: return
    m = p["metrics"]
    if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: return
    seen.add(sig); cands.append({"src": src, "specs": specs, "m": m})
for f in ["par4b.json", "par4.json", "prio.json", "pareto.json"]:
    p = os.path.join(HERE, "runs", f)
    if os.path.exists(p):
        for rec in json.load(open(p, encoding="utf-8")):
            for k in ("time", "energy", "sorties"):
                if k in rec and "specs" in rec[k]: add(rec[k]["specs"], "%s.%s" % (f, k))
Tmin = min(c["m"]["makespan_s"] for c in cands); Emin = min(c["m"]["energy_kwh"] for c in cands); Nmin = min(c["m"]["sorties"] for c in cands)
schemes = {
    "时间优先(主方案)": min(cands, key=lambda c: (c["m"]["makespan_s"], c["m"]["energy_kwh"], c["m"]["sorties"])),
    "均衡": min(cands, key=lambda c: c["m"]["makespan_s"]/Tmin + c["m"]["energy_kwh"]/Emin + c["m"]["sorties"]/Nmin),
    "能耗优先": min(cands, key=lambda c: (c["m"]["energy_kwh"], c["m"]["makespan_s"], c["m"]["sorties"])),
    "架次优先": min(cands, key=lambda c: (c["m"]["sorties"], c["m"]["makespan_s"], c["m"]["energy_kwh"])),
}
def export(name, pick):
    plan = decode(pick["specs"], D, require_all=True); m = plan["metrics"]
    sorties, delivery, legs = [], [], []
    for s in plan["sorties"]:
        g = s["model"]; dr = D["drones"][g]
        sorties.append({"架次编号": s["id"], "无人机编号": s["uav"], "机型编号": g, "电池编号": s["battery"],
                        "开始时刻_s": round(s["start_s"], 6), "访问服务区顺序": "-".join(st["area"] for st in s["stops"]),
                        "返回O01时刻_s": round(s["return_s"], 6), "架次能耗_kWh": round(s["energy_kwh"], 6),
                        "返航SOC": round(s["return_soc"], 6), "电池充满时刻_s": round(s["charge_end_s"], 6),
                        "总质量_kg": s["mass_kg"], "总体积_m3": s["volume_m3"], "货箱编号列表": ",".join(s["box_ids"])})
        ev = evaluate_sortie({"model": g, "stops": s["stops"]}, D)
        t = s["start_s"] + dr["prep"] + len(ev["box_ids"]) * dr["load"]
        for k, leg in enumerate(ev["legs"]):
            a, b = leg["from"], leg["to"]; gg = GEOM[(a, b)]; arr = t + leg["flight_s"]; handed = 0.0
            if b != "O01":
                boxes = next(st["ids"] for st in s["stops"] if st["area"] == b); handed = dr["handoff"] + len(boxes)*dr["extra"]
            legs.append({"架次编号": s["id"], "航段序号": k+1, "起点": a, "终点": b, "水平距离_m": round(float(gg["水平距离（m）"]), 3),
                         "起点爬升_m": gg["起点爬升（m）"], "终点下降_m": gg["终点下降（m）"], "航段载重_kg": round(leg["payload_kg"], 3),
                         "航段能耗_kWh": round(leg["energy_kwh"], 6), "航段飞行时间_s": round(leg["flight_s"], 3),
                         "起飞时刻_s": round(t, 3), "到达时刻_s": round(arr, 3)})
            t = arr + handed
    for b, tt in sorted(plan["deliveries"].items()):
        bx = D["boxes"][b]
        delivery.append({"货箱编号": b, "架次编号": next(s["id"] for s in plan["sorties"] if b in s["box_ids"]),
                         "服务区编号": bx["area"], "交付完成时刻_s": round(tt, 6), "物资类型": bx["type"],
                         "期望送达时间_s": bx["due"], "硬截止时间_s": bx["hard"] if bx["hard"] is not None else "",
                         "加权延误": round(bx["weight"]*max(0.0, tt-bx["due"]), 6)})
    for fn, rows in [("方案_%s_逐架次.csv" % name, sorties), ("方案_%s_逐箱交付.csv" % name, delivery), ("方案_%s_逐航段.csv" % name, legs)]:
        with open(os.path.join(OUT, fn), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump({"metrics": m, "sorties": plan["sorties"], "deliveries": plan["deliveries"]},
              open(os.path.join(OUT, "方案_%s_完整方案.json" % name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return m
rows = []
for name in ["时间优先(主方案)", "均衡", "能耗优先", "架次优先"]:
    m = export(name, schemes[name]); cc = Counter(s["model"] for s in schemes[name]["specs"])
    rows.append({"方案": name, "架次数": m["sorties"], "完成时间_s": round(m["makespan_s"], 3),
                 "总能耗_kWh": round(m["energy_kwh"], 4), "A_B_C": "%d/%d/%d" % (cc["A"], cc["B"], cc["C"])})
    print("%-16s n=%2d T=%9.3f E=%8.4f A/B/C=%d/%d/%d" % (name, m["sorties"], m["makespan_s"], m["energy_kwh"], cc["A"], cc["B"], cc["C"]))
with open(os.path.join(OUT, "方案对比_四个口径.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("done")

