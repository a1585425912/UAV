"""把 feas_sched 的逐机型调度优化应用到发布方案并重新导出（makespan/能耗不变，仅调整时序）。"""
import sys, os, json, csv
sys.path.insert(0, r"D:\git\math_modeling\UAV\code"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as fs
from 问题二_调度核心 import load_data, decode, evaluate_sortie
ROOT = r"D:\git\math_modeling\UAV"; OUT = os.path.join(ROOT, "results", "问题二_改进方案"); D = load_data()
def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
GEOM = {(r["起点"], r["终点"]): r for r in rd(os.path.join(ROOT, "results", "问题二_参考口径", "有向航段几何参数.csv"))}
SCHEMES = ["方案_时间优先(主方案)", "方案_均衡", "方案_能耗优先", "方案_架次优先"]
for tag in SCHEMES:
    path = os.path.join(OUT, tag + "_完整方案.json")
    r = fs.run(path)
    specs = r["specs"]; order = r["order"]
    plan = decode([specs[i] for i in order], D, require_all=True)
    m = plan["metrics"]
    assert abs(m["makespan_s"] - r["base_greedy"]["makespan_s"]) < 1e-6, (tag, m["makespan_s"], r["base_greedy"])
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
                bid = next(st["ids"] for st in s["stops"] if st["area"] == b); handed = dr["handoff"] + len(bid) * dr["extra"]
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
                         "加权延误": round(bx["weight"] * max(0.0, tt - bx["due"]), 6)})
    for fn, rows in [(tag + "_逐架次.csv", sorties), (tag + "_逐箱交付.csv", delivery), (tag + "_逐航段.csv", legs)]:
        with open(os.path.join(OUT, fn), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump({"metrics": m, "sorties": plan["sorties"], "deliveries": plan["deliveries"]},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%-24s makespan=%.3f energy=%.4f n=%d  (逐机型重排后)" % (tag, m["makespan_s"], m["energy_kwh"], m["sorties"]))
