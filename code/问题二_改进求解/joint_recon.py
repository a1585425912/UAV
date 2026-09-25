import sys, os, json, itertools, random, time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix, vstack
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, decode, evaluate_sortie, charge_time
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
NSHIP = {"A": 4, "B": 2, "C": 2}

base = json.load(open(r"D:\git\math_modeling\UAV\results\问题二_改进方案\方案_时间优先(主方案)_完整方案.json", encoding="utf-8"))
def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}
target_boxes = sorted({b for s in base["sorties"] if s["model"] == "C" for b in s["box_ids"]})
fixed = [norm(s) for s in base["sorties"] if s["model"] != "C"]
fixed_boxes = {b for s in fixed for st in s["stops"] for b in st["ids"]}
print("target(C boxes)=%d  fixed sorties=%d  fixed boxes=%d" % (len(target_boxes), len(fixed), len(fixed_boxes)))

# candidate pool: routes whose boxes are a subset of target boxes
pool = {}
def add_route(spec):
    spec = norm(spec)
    boxes = [b for st in spec["stops"] for b in st["ids"]]
    if not boxes or not set(boxes) <= set(target_boxes): return
    key = (spec["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in spec["stops"]))
    if key in pool: return
    ev = evaluate_sortie(spec, D)
    if ev is None: return
    pool[key] = {"model": spec["model"], "stops": spec["stops"], "boxes": boxes,
                 "duration": ev["duration_s"], "energy": ev["energy_kwh"]}
for f in ["par4b.json", "par4.json", "prio.json", "pareto.json"]:
    p = os.path.join(HERE, "runs", f)
    if not os.path.exists(p): continue
    for rec in json.load(open(p, encoding="utf-8")):
        for k in ("time", "energy", "sorties"):
            if k in rec and "specs" in rec[k]:
                for s in rec[k]["specs"]: add_route(s)
for s in base["sorties"]:
    if s["model"] == "C": add_route(s)
# generate extra random routes over the target areas
AREAS = sorted({D["boxes"][b]["area"] for b in target_boxes})
rng = random.Random(0)
by_area = {a: [b for b in target_boxes if D["boxes"][b]["area"] == a] for a in AREAS}
for _ in range(4000):
    g = rng.choice("ABC"); ns = rng.randint(1, 3); areas = rng.sample(AREAS, ns)
    stops = []
    for a in areas:
        k = rng.randint(1, len(by_area[a])); ids = rng.sample(by_area[a], k)
        stops.append({"area": a, "ids": ids})
    add_route({"model": g, "stops": stops})
routes = list(pool.values())
print("candidate routes:", len(routes), {g: sum(1 for r in routes if r["model"] == g) for g in "ABC"})

# fixed work per model
fixed_work = {g: 0.0 for g in "ABC"}
for s in fixed:
    ev = evaluate_sortie(s, D); fixed_work[s["model"]] += ev["duration_s"]

BIDX = {b: i for i, b in enumerate(target_boxes)}
n = len(routes)
rows, cols = [], []
for j, r in enumerate(routes):
    for b in r["boxes"]: rows.append(BIDX[b]); cols.append(j)
Aeq = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(target_boxes), n)).tocsr()
# per-model budget: fixed_work_g + sum d_r x_r - n_g*Z <= 0  -> last var is Z
rr, cc, vv = [], [], []
for gi, g in enumerate("ABC"):
    for j, r in enumerate(routes):
        if r["model"] == g: rr.append(gi); cc.append(j); vv.append(r["duration"])
    rr.append(gi); cc.append(n); vv.append(-NSHIP[g])
Aub = coo_matrix((vv, (rr, cc)), shape=(3, n + 1)).tocsr()
A = vstack([coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(target_boxes), n + 1)).tocsr(), Aub]).tocsr()
lb = np.array([1.0]*len(target_boxes) + [-np.inf]*3)
ub = np.array([1.0]*len(target_boxes) + [-fixed_work[g] for g in "ABC"])
c = np.zeros(n + 1); c[n] = 1.0
res = milp(c=c, constraints=LinearConstraint(A, lb, ub), integrality=np.concatenate([np.ones(n), [0]]),
           bounds=Bounds(np.zeros(n + 1), np.concatenate([np.ones(n), [1e5]])),
           options={"time_limit": 120.0, "mip_rel_gap": 0.0, "disp": False})
print("MILP status", res.status, res.message)
if res.x is not None:
    sel = [routes[j] for j in range(n) if res.x[j] > 0.5]
    Z = float(res.x[n])
    print("Z(min makespan LB)=%.3f  selected=%d routes  energy=%.4f" % (Z, len(sel), sum(r["energy"] for r in sel)))
    specs = fixed + [{"model": r["model"], "stops": r["stops"]} for r in sel]
    plan = decode(specs, D, require_all=True)
    if plan:
        m = plan["metrics"]
        print("full plan: n=%d T=%.3f E=%.3f hard=%.1f tardy=%.1f" % (m["sorties"], m["makespan_s"], m["energy_kwh"], m["hard_excess_s"], m["weighted_tardiness"]))
        json.dump({"Z": Z, "specs": specs, "metrics": m}, open(os.path.join(HERE, "joint_recon.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("decode failed (deadline/soc)")

