import sys, os, json, csv, math
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, decode
D = load_data()
HERE = os.path.dirname(os.path.abspath(__file__))

def indep_energy(spec):
    g = spec["model"]; drone = D["drones"][g]; legs = D["legs"]
    boxes = D["boxes"]
    ids = [b for st in spec["stops"] for b in st["ids"]]
    rem = sum(boxes[b]["mass"] for b in ids)
    loc = "O01"; E = 0.0
    for st in spec["stops"]:
        q = rem
        leg = legs[(loc, st["area"])]
        Leq = drone["range0"] - (drone["range0"] - drone["range_full"]) * (q / drone["payload"]) ** 1.5
        E += drone["battery_kwh"] * leg["distance"] / Leq + (drone["mass0"] + q) * 9.81 * leg["climb"] / (3.6e6 * drone["eta"])
        rem -= sum(boxes[b]["mass"] for b in st["ids"])
        loc = st["area"]
    leg = legs[(loc, "O01")]
    Leq = drone["range0"]
    E += drone["battery_kwh"] * leg["distance"] / Leq + drone["mass0"] * 9.81 * leg["climb"] / (3.6e6 * drone["eta"])
    return E

def check(specs, tag):
    plan = decode(specs, D, require_all=True)
    m = plan["metrics"]
    print("[%s] sorties=%d makespan=%.3f energy=%.4f hard=%.3f tardy=%.3f" % (
        tag, m["sorties"], m["makespan_s"], m["energy_kwh"], m["hard_excess_s"], m["weighted_tardiness"]))
    errs = []
    allbox = [b for s in plan["sorties"] for b in s["box_ids"]]
    if len(allbox) != 80 or len(set(allbox)) != 80: errs.append("box coverage")
    if set(allbox) != set(D["boxes"]): errs.append("box set mismatch")
    for s in plan["sorties"]:
        g = s["model"]; dr = D["drones"][g]
        mass = sum(D["boxes"][b]["mass"] for b in s["box_ids"])
        vol = sum(D["boxes"][b]["volume"] for b in s["box_ids"])
        if mass > dr["payload"] + 1e-9: errs.append("mass " + s["id"])
        if vol > dr["volume"] + 1e-9: errs.append("volume " + s["id"])
        if s["return_soc"] < dr["reserve"] - 1e-9: errs.append("soc " + s["id"])
        indep = indep_energy({"model": g, "stops": s["stops"]})
        if abs(indep - s["energy_kwh"]) > 1e-6: errs.append("energy " + s["id"] + " %.6f vs %.6f" % (indep, s["energy_kwh"]))
    uav = defaultdict(list); bat = defaultdict(list)
    for s in plan["sorties"]:
        uav[s["uav"]].append((s["start_s"], s["return_s"], s["id"]))
        bat[s["battery"]].append((s["start_s"], s["charge_end_s"], s["id"]))
    for name, iv in list(uav.items()) + list(bat.items()):
        iv.sort()
        for a, b in zip(iv, iv[1:]):
            if b[0] < a[1] - 1e-6: errs.append("overlap %s %s %s" % (name, a[2], b[2]))
    for b, t in plan["deliveries"].items():
        hb = D["boxes"][b]["hard"]
        if hb is not None and t > hb + 1e-6: errs.append("hard " + b)
    print("  independent energy check: %s" % ("OK" if not any(e.startswith("energy") for e in errs) else "FAIL"))
    print("  resource/uav overlap check: %s" % ("OK" if not any(e.startswith("overlap") for e in errs) else "FAIL"))
    print("  errors:", errs if errs else "NONE")
    return plan, errs

if __name__ == "__main__":
    obj = json.load(open(os.path.join(HERE, "best_feasible.json"), encoding="utf-8"))
    plan, errs = check(obj["specs"], obj["source"])
    # export to a new results folder
    OUT = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
    os.makedirs(OUT, exist_ok=True)
    sorties, delivery = [], []
    for s in plan["sorties"]:
        sorties.append({"架次编号": s["id"], "无人机编号": s["uav"], "机型编号": s["model"], "电池编号": s["battery"],
                        "开始时刻_s": round(s["start_s"], 6), "访问服务区顺序": "-".join(st["area"] for st in s["stops"]),
                        "返回O01时刻_s": round(s["return_s"], 6), "架次能耗_kWh": round(s["energy_kwh"], 6),
                        "返航SOC": round(s["return_soc"], 6), "电池充满时刻_s": round(s["charge_end_s"], 6),
                        "总质量_kg": s["mass_kg"], "总体积_m3": s["volume_m3"],
                        "货箱编号列表": ",".join(s["box_ids"])})
    for b, t in sorted(plan["deliveries"].items()):
        bx = D["boxes"][b]
        delivery.append({"货箱编号": b, "架次编号": next(s["id"] for s in plan["sorties"] if b in s["box_ids"]),
                         "服务区编号": bx["area"], "交付完成时刻_s": round(t, 6),
                         "物资类型": bx["type"], "期望送达时间_s": bx["due"],
                         "硬截止时间_s": bx["hard"] if bx["hard"] is not None else "",
                         "加权延误": round(bx["weight"] * max(0.0, t - bx["due"]), 6)})
    for name, rows in [("改进方案_逐架次.csv", sorties), ("改进方案_逐箱交付.csv", delivery)]:
        with open(os.path.join(OUT, name), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump({"metrics": plan["metrics"], "sorties": plan["sorties"], "deliveries": plan["deliveries"]},
              open(os.path.join(OUT, "改进方案_完整方案.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("exported to", OUT)
