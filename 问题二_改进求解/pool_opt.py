import sys, os, json, time, random
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix, vstack
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, decode, evaluate_sortie, charge_time
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
NSHIP = {"A": 4, "B": 2, "C": 2}
BOXES = sorted(D["boxes"].keys()); BIDX = {b: i for i, b in enumerate(BOXES)}
def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}
pool = {}
def add(spec):
    spec = norm(spec)
    key = (spec["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in spec["stops"]))
    if key in pool: return
    ev = evaluate_sortie(spec, D)
    if ev is None: return
    off = ev["delivery_offsets_s"]; boxes = ev["box_ids"]
    ls = min(min(D["boxes"][b]["due"] - off[b],
                 (D["boxes"][b]["hard"] - off[b]) if D["boxes"][b]["hard"] is not None else 1e18) for b in boxes)
    pool[key] = {"model": spec["model"], "stops": spec["stops"], "boxes": boxes,
                 "duration": ev["duration_s"], "energy": ev["energy_kwh"], "ls": ls, "soc": ev["return_soc"]}
for f in ["par4b.json", "par4.json", "prio.json", "pareto.json"]:
    p = os.path.join(HERE, "runs", f)
    if not os.path.exists(p): continue
    for rec in json.load(open(p, encoding="utf-8")):
        for k in ("time", "energy", "sorties"):
            if k in rec and "specs" in rec[k]:
                for s in rec[k]["specs"]: add(s)
base = json.load(open(r"D:\git\math_modeling\UAV\results\问题二_改进方案\方案_时间优先(主方案)_完整方案.json", encoding="utf-8"))
for s in base["sorties"]: add(s)
routes = list(pool.values()); n = len(routes)
print("pool:", n, {g: sum(1 for r in routes if r["model"] == g) for g in "ABC"}, flush=True)

def list_sched(sel, order):
    uav = {u: 0.0 for g in "ABC" for u in D["uavs"][g]}
    bat = {b: 0.0 for g in "ABC" for b in D["batteries"][g]["ids"]}
    last = 0.0
    for i in order:
        r = sel[i]; g = r["model"]
        st, u, b = min((max(uav[u], bat[b]), u, b) for u in D["uavs"][g] for b in D["batteries"][g]["ids"])
        if st > r["ls"] + 1e-6: return None
        ret = st + r["duration"]; uav[u] = ret
        bat[b] = ret + charge_time(r["soc"], D["batteries"][g]["full_charge_s"]); last = max(last, ret)
    return last

def schedule(sel, tries=120, seed=0):
    rng = random.Random(seed); n = len(sel); best = None
    base_order = sorted(range(n), key=lambda i: sel[i]["ls"])
    for order in [base_order] + [[i for i in base_order if i not in set(sel[j]["model"] for j in range(n))] ]:
        pass
    m = list_sched(sel, base_order)
    if m is not None: best = (m, base_order[:])
    for _ in range(tries):
        order = base_order[:]
        for _ in range(rng.randint(1, 4)):
            i, j = rng.sample(range(n), 2); order[i], order[j] = order[j], order[i]
        m = list_sched(sel, order)
        if m is not None and (best is None or m < best[0]): best = (m, order[:])
    return best

cov_rows = [BIDX[b] for r in routes for b in r["boxes"]]
cov_cols = [j for j, r in enumerate(routes) for _ in r["boxes"]]
Aeq = coo_matrix((np.ones(len(cov_rows)), (cov_rows, cov_cols)), shape=(len(BOXES), n + 1)).tocsr()
def solve(T_override=None, cuts=()):
    rr, cc, vv = [], [], []
    for gi, g in enumerate("ABC"):
        for j, r in enumerate(routes):
            if r["model"] == g: rr.append(gi); cc.append(j); vv.append(r["duration"])
        rr.append(gi); cc.append(n); vv.append(-NSHIP[g])
    Aub = coo_matrix((vv, (rr, cc)), shape=(3, n + 1)).tocsr()
    A = vstack([Aeq, Aub]).tocsr()
    lb = np.array([1.0]*len(BOXES) + [-np.inf]*3); ub = np.array([1.0]*len(BOXES) + [0.0]*3)
    if cuts:
        cr, cc2, cv, cl, cu = [], [], [], [], []
        for k, S in enumerate(cuts):
            for j in S: cr.append(k); cc2.append(j); cv.append(1.0)
            cl.append(-np.inf); cu.append(len(S)-1)
        A = vstack([A, coo_matrix((cv, (cr, cc2)), shape=(len(cuts), n+1)).tocsr()]).tocsr()
        lb = np.concatenate([lb, np.array(cl)]); ub = np.concatenate([ub, np.array(cu)])
    c = np.zeros(n+1); c[n] = 1.0
    res = milp(c=c, constraints=LinearConstraint(A, lb, ub), integrality=np.concatenate([np.ones(n), [0]]),
               bounds=Bounds(np.zeros(n+1), np.concatenate([np.ones(n), [1e5]])),
               options={"time_limit": 15.0, "mip_rel_gap": 0.0, "disp": False})
    return res

if __name__ == "__main__":
    cuts = []; best = None; t0 = time.time()
    for attempt in range(120):
        res = solve(cuts=cuts)
        if res.x is None:
            print("attempt %d infeasible/limit: %s" % (attempt, res.message), flush=True); break
        selidx = [j for j in range(n) if res.x[j] > 0.5]
        sel = [routes[j] for j in selidx]; Z = float(res.x[n])
        sch = schedule(sel, tries=150, seed=attempt)
        if sch is not None:
            ms, order = sch
            if ms < 5903.038 - 1e-6:
                best = {"makespan": ms, "Z": Z, "n": len(sel), "energy": sum(r["energy"] for r in sel),
                        "specs": [{"model": r["model"], "stops": r["stops"]} for r in sel]}
                print("FEASIBLE makespan=%.3f Z=%.3f n=%d E=%.4f" % (ms, Z, len(sel), best["energy"]), flush=True)
                json.dump(best, open(os.path.join(HERE, "pool_best.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                break
        cuts.append(selidx)
        if (attempt+1) % 10 == 0:
            print("attempt %d  Z=%.3f  n=%d  cuts=%d  %.1fs" % (attempt+1, Z, len(sel), len(cuts), time.time()-t0), flush=True)
    print("BEST", best and {k: best[k] for k in ("makespan","Z","n","energy")})


