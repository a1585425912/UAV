# -*- coding: utf-8 -*-
"""q2_exact_plan：对给定方案逐机型做精确 MILP 排程，合成完整方案并独立验证。

用法：python q2_exact_plan.py <输入方案.json> <输出方案.json> [时限s]
"""
import sys, os, json, time
from collections import defaultdict
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q2_exact_sched as ES
from 问题二_调度核心 import load_data, decode, charge_time, evaluate_sortie
D = load_data()

def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}

def build(plan_path, out_path, tl):
    o = json.load(open(plan_path, encoding="utf-8"))
    specs = [norm(s) for s in o["specs"]]
    by = defaultdict(list)
    for s in specs: by[s["model"]].append(s)
    sorties = []
    for g in "ABC":
        if not by[g]: continue
        res = ES.solve(by[g], g, tl)
        print("  %s n=%d status=%s T=%s %.1fs" % (g, len(by[g]), res["status"], res.get("makespan"), res["seconds"]), flush=True)
        if res.get("assign") is None: raise SystemExit("model %s no solution" % g)
        for a in res["assign"]:
            sp = by[g][a["i"]]
            ev = evaluate_sortie(sp, D)
            st = max(0.0, a["start"])
            ret = st + ev["duration_s"]
            ce = ret + charge_time(ev["return_soc"], D["batteries"][g]["full_charge_s"])
            sorties.append({"id": None, "model": g, "uav": a["uav"], "battery": a["battery"],
                            "start_s": st, "return_s": ret, "charge_end_s": ce,
                            "energy_kwh": ev["energy_kwh"], "return_soc": ev["return_soc"],
                            "stops": sp["stops"], "box_ids": ev["box_ids"], "mass_kg": ev["mass_kg"],
                            "volume_m3": ev["volume_m3"], "_off": ev["delivery_offsets_s"]})
    sorties.sort(key=lambda s: (s["start_s"], s["model"]))
    deliveries = {}
    for k, s in enumerate(sorties, 1):
        s["id"] = "T%02d" % k
        for b, off in s.pop("_off").items(): deliveries[b] = s["start_s"] + off
    hard = sum(max(0.0, deliveries[b] - D["boxes"][b]["hard"]) for b in deliveries if D["boxes"][b]["hard"] is not None)
    tardy = sum(D["boxes"][b]["weight"] * max(0.0, deliveries[b] - D["boxes"][b]["due"]) for b in deliveries)
    m = {"hard_excess_s": hard, "weighted_tardiness": tardy,
         "makespan_s": max(s["return_s"] for s in sorties),
         "energy_kwh": sum(s["energy_kwh"] for s in sorties), "sorties": len(sorties), "boxes": len(deliveries)}
    print("  combined:", {k: round(m[k],6) if isinstance(m[k],float) else m[k] for k in m}, flush=True)
    # 资源不重叠检查
    errs = []
    uav = defaultdict(list); bat = defaultdict(list)
    for s in sorties:
        uav[s["uav"]].append((s["start_s"], s["return_s"], s["id"]))
        bat[s["battery"]].append((s["start_s"], s["charge_end_s"], s["id"]))
    for name, iv in list(uav.items()) + list(bat.items()):
        iv.sort()
        for a, b in zip(iv, iv[1:]):
            if b[0] < a[1] - 1e-6: errs.append("overlap %s %s %s" % (name, a[2], b[2]))
    if len(deliveries) != 80: errs.append("coverage")
    if hard > 1e-6: errs.append("hard")
    if tardy > 1e-6: errs.append("tardy")
    print("  resource check:", "PASS" if not errs else errs[:6], flush=True)
    json.dump({"metrics": m, "sorties": sorties, "deliveries": deliveries}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return m, errs

if __name__ == "__main__":
    t0 = time.time()
    m, errs = build(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 150.0)
    print("saved", sys.argv[2], "%.1fs" % (time.time()-t0))


