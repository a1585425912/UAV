import sys, os, json
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, decode
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}
seen = set(); cands = []
def add(specs):
    specs = [norm(s) for s in specs]
    sig = frozenset((s["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in s["stops"])) for s in specs)
    if sig in seen: return
    p = decode(specs, D, require_all=True)
    if p is None: return
    m = p["metrics"]
    if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: return
    seen.add(sig); cands.append({"specs": specs, "m": m})
for f in ["par4b.json", "par4.json", "prio.json", "pareto.json"]:
    p = os.path.join(HERE, "runs", f)
    if os.path.exists(p):
        for rec in json.load(open(p, encoding="utf-8")):
            for k in ("time", "energy", "sorties"):
                if k in rec and "specs" in rec[k]: add(rec[k]["specs"])
print("candidates:", len(cands))
for cap in (5903.038154612774, 6000, 6600, 7200, 8000, 9000):
    g = [c for c in cands if c["m"]["makespan_s"] <= cap + 1e-9]
    if not g: print("cap %9.1f  no feasible" % cap); continue
    e = min(g, key=lambda c: (c["m"]["energy_kwh"], c["m"]["sorties"], c["m"]["makespan_s"]))
    s = min(g, key=lambda c: (c["m"]["sorties"], c["m"]["makespan_s"], c["m"]["energy_kwh"]))
    cc = Counter(x["model"] for x in e["specs"])
    print("cap %9.1f  min-energy: T=%.3f E=%.4f n=%d A/B/C=%d/%d/%d | min-sorties: T=%.3f E=%.4f n=%d" % (
        cap, e["m"]["makespan_s"], e["m"]["energy_kwh"], e["m"]["sorties"], cc["A"], cc["B"], cc["C"],
        s["m"]["makespan_s"], s["m"]["energy_kwh"], s["m"]["sorties"]))
    json.dump({"cap": cap, "specs": e["specs"], "metrics": e["m"]}, open(os.path.join(HERE, "runs", "cap_best_%d.json" % int(cap)), "w", encoding="utf-8"), ensure_ascii=False)

