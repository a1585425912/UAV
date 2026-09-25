import sys, os, json, csv
from collections import Counter
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, decode
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
OUT = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
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
front = []
for a in cands:
    va = (a["m"]["makespan_s"], a["m"]["energy_kwh"], a["m"]["sorties"])
    if not any(all(x <= y+1e-7 for x, y in zip((b["m"]["makespan_s"], b["m"]["energy_kwh"], b["m"]["sorties"]), va))
               and any(x < y-1e-7 for x, y in zip((b["m"]["makespan_s"], b["m"]["energy_kwh"], b["m"]["sorties"]), va)) for b in cands):
        front.append(a)
front.sort(key=lambda r: (r["m"]["makespan_s"], r["m"]["energy_kwh"], r["m"]["sorties"]))
with open(os.path.join(OUT, "Pareto前沿_问题二.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f); w.writerow(["序号", "完成时间_s", "总能耗_kWh", "架次数", "A/B/C"])
    for i, r in enumerate(front, 1):
        m = r["m"]; cc = Counter(s["model"] for s in r["specs"])
        w.writerow([i, round(m["makespan_s"], 3), round(m["energy_kwh"], 4), m["sorties"], "%d/%d/%d" % (cc["A"], cc["B"], cc["C"])])
print("feasible=%d non-dominated=%d" % (len(cands), len(front)))
json.dump([{"序号": i + 1, "metrics": r["m"], "specs": r["specs"]} for i, r in enumerate(front)], open(os.path.join(OUT, "Pareto前沿_问题二_specs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for i, r in enumerate(front, 1):
    m = r["m"]; cc = Counter(s["model"] for s in r["specs"])
    print("%2d  T=%9.3f  E=%7.3f  n=%2d  A/B/C=%d/%d/%d" % (i, m["makespan_s"], m["energy_kwh"], m["sorties"], cc["A"], cc["B"], cc["C"]))


