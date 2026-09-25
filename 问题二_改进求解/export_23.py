# -*- coding: utf-8 -*-
"""导出并独立验证 23 架次 / 5903.038 s 新方案（含逐架次、逐箱、逐航段坐标）。"""
import sys, os, json, csv
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, decode
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
OUT = os.path.join(os.path.dirname(HERE), "results", "问题二_改进方案")
Q2GEO = os.path.join(os.path.dirname(HERE), "results", "问题二_参考口径", "有向航段几何参数.csv")
NODE = os.path.join(OUT, "节点坐标与作业海拔.csv")
def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
def wr(p, rows):
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def indep_energy(spec):
    g = spec["model"]; dr = D["drones"][g]; legs = D["legs"]; bx = D["boxes"]
    ids = [b for st in spec["stops"] for b in st["ids"]]; rem = sum(bx[b]["mass"] for b in ids); loc = "O01"; E = 0.0
    for st in spec["stops"]:
        q = rem; leg = legs[(loc, st["area"])]
        Leq = dr["range0"] - (dr["range0"] - dr["range_full"]) * (q / dr["payload"]) ** 1.5
        E += dr["battery_kwh"] * leg["distance"] / Leq + (dr["mass0"] + q) * 9.81 * leg["climb"] / (3.6e6 * dr["eta"])
        rem -= sum(bx[b]["mass"] for b in st["ids"]); loc = st["area"]
    leg = legs[(loc, "O01")]
    E += dr["battery_kwh"] * leg["distance"] / dr["range0"] + dr["mass0"] * 9.81 * leg["climb"] / (3.6e6 * dr["eta"])
    return E

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "runs", "plan_23T5903.json")
    tag = sys.argv[2] if len(sys.argv) > 2 else "方案_23架次_5903s"
    o = json.load(open(src, encoding="utf-8"))
    specs = [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in o["specs"]]
    plan = decode(specs, D, require_all=True); m = plan["metrics"]
    print("metrics:", {k: m[k] for k in ["makespan_s", "energy_kwh", "sorties", "hard_excess_s", "weighted_tardiness", "boxes"]})
    errs = []
    allb = [b for s in plan["sorties"] for b in s["box_ids"]]
    if len(allb) != 80 or len(set(allb)) != 80: errs.append("coverage")
    for s in plan["sorties"]:
        dr = D["drones"][s["model"]]
        if s["mass_kg"] > dr["payload"] + 1e-9: errs.append("mass " + s["id"])
        if s["volume_m3"] > dr["volume"] + 1e-9: errs.append("vol " + s["id"])
        if s["return_soc"] < dr["reserve"] - 1e-9: errs.append("soc " + s["id"])
        if abs(indep_energy({"model": s["model"], "stops": s["stops"]}) - s["energy_kwh"]) > 1e-6: errs.append("energy " + s["id"])
    uav = defaultdict(list); bat = defaultdict(list)
    for s in plan["sorties"]:
        uav[s["uav"]].append((s["start_s"], s["return_s"])); bat[s["battery"]].append((s["start_s"], s["charge_end_s"]))
    for iv in list(uav.values()) + list(bat.values()):
        iv.sort()
        for a, b in zip(iv, iv[1:]):
            if b[0] < a[1] - 1e-6: errs.append("overlap")
    for b, t in plan["deliveries"].items():
        hb = D["boxes"][b]["hard"]
        if hb is not None and t > hb + 1e-6: errs.append("hard " + b)
    print("independent validation:", "PASS" if not errs else errs[:8])
    # 导出
    sorties, delivery = [], []
    for s in plan["sorties"]:
        sorties.append({"架次编号": s["id"], "无人机编号": s["uav"], "机型编号": s["model"], "电池编号": s["battery"],
                        "开始时刻_s": round(s["start_s"], 6), "访问服务区顺序": "-".join(st["area"] for st in s["stops"]),
                        "返回O01时刻_s": round(s["return_s"], 6), "架次能耗_kWh": round(s["energy_kwh"], 6),
                        "返航SOC": round(s["return_soc"], 6), "电池充满时刻_s": round(s["charge_end_s"], 6),
                        "总质量_kg": s["mass_kg"], "总体积_m3": s["volume_m3"], "货箱编号列表": ",".join(s["box_ids"])})
    for b, t in sorted(plan["deliveries"].items()):
        bx = D["boxes"][b]
        delivery.append({"货箱编号": b, "架次编号": next(s["id"] for s in plan["sorties"] if b in s["box_ids"]),
                         "服务区编号": bx["area"], "交付完成时刻_s": round(t, 6), "物资类型": bx["type"],
                         "期望送达时间_s": bx["due"], "硬截止时间_s": bx["hard"] if bx["hard"] is not None else "",
                         "加权延误": round(bx["weight"] * max(0.0, t - bx["due"]), 6)})
    nodes = {r["编号"]: r for r in rd(NODE)}; legs_geo = {(r["起点"], r["终点"]): r for r in rd(Q2GEO)}
    legs = []
    for s in plan["sorties"]:
        loc = "O01"
        for k, st in enumerate(s["stops"], 1):
            rem = sum(D["boxes"][b]["mass"] for ss in s["stops"][k-1:] for b in ss["ids"])
            e = D["legs"][(loc, st["area"])]
            legs.append({"架次编号": s["id"], "航段序号": k, "起点": loc, "终点": st["area"],
                         "起点经度_度": nodes[loc]["经度"], "起点纬度_度": nodes[loc]["纬度"],
                         "终点经度_度": nodes[st["area"]]["经度"], "终点纬度_度": nodes[st["area"]]["纬度"],
                         "水平距离_m": round(e["distance"], 6), "计划巡航海拔_m": round(e["cruise"], 6),
                         "航段载重_kg": rem, "航段能耗_kWh": round(D["drones"][s["model"]]["battery_kwh"] * e["distance"] / max(1e-9, D["drones"][s["model"]]["range0"] - (D["drones"][s["model"]]["range0"] - D["drones"][s["model"]]["range_full"]) * (rem / D["drones"][s["model"]]["payload"]) ** 1.5) + (D["drones"][s["model"]]["mass0"] + rem) * 9.81 * e["climb"] / (3.6e6 * D["drones"][s["model"]]["eta"]), 6)})
            loc = st["area"]
        e = D["legs"][(loc, "O01")]
        legs.append({"架次编号": s["id"], "航段序号": len(s["stops"]) + 1, "起点": loc, "终点": "O01",
                     "起点经度_度": nodes[loc]["经度"], "起点纬度_度": nodes[loc]["纬度"],
                     "终点经度_度": nodes["O01"]["经度"], "终点纬度_度": nodes["O01"]["纬度"],
                     "水平距离_m": round(e["distance"], 6), "计划巡航海拔_m": round(e["cruise"], 6),
                     "航段载重_kg": 0.0, "航段能耗_kWh": round(D["drones"][s["model"]]["battery_kwh"] * e["distance"] / D["drones"][s["model"]]["range0"] + D["drones"][s["model"]]["mass0"] * 9.81 * e["climb"] / (3.6e6 * D["drones"][s["model"]]["eta"]), 6)})
    wr(os.path.join(OUT, tag + "_逐架次.csv"), sorties)
    wr(os.path.join(OUT, tag + "_逐箱交付.csv"), delivery)
    wr(os.path.join(OUT, tag + "_逐航段.csv"), legs)
    json.dump({"metrics": m, "sorties": plan["sorties"], "deliveries": plan["deliveries"]},
              open(os.path.join(OUT, tag + "_完整方案.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("exported to", OUT, "as", tag)
    print("errors:", errs if errs else "NONE")
