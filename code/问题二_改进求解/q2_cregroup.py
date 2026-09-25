# -*- coding: utf-8 -*-
"""q2_cregroup：主线（23 架次 / 5903.038 s）能耗下降。

固定 23 架次方案里的 17 个 A/B 架次，只把 C 型 36 箱重新组批（允许改成 A/B 机型），
总架次数固定 6（保持 23），加入有效时限必要条件与逐机型工时预算，目标最小化新增架次能耗。
选出后做完整时限感知排程，要求 makespan <= 5903.038154612774 且 hard=tardy=0。
"""
import sys, os, json, time, random
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as FS
import q2_transfer as T
import q2_lns2 as L
D = T.D; HERE = os.path.dirname(os.path.abspath(__file__)); NSHIP = T.NSHIP
BASE = os.path.join(HERE, "runs", "plan_23T5903.json")
CAP = 5903.038154612774

def gen_cands(free_boxes, pool, rng, n_rand=8000):
    fs = set(free_boxes)
    cands = [r for r in pool if set(r["boxes"]) <= fs]
    by_area = {}
    for b in free_boxes: by_area.setdefault(D["boxes"][b]["area"], []).append(b)
    areas = sorted(by_area)
    for _ in range(n_rand):
        g = rng.choice("ABC"); chosen = rng.sample(areas, rng.randint(1, min(3, len(areas))))
        stops = []; ok = True
        for a in chosen:
            ids = by_area[a]; stops.append({"area": a, "ids": rng.sample(ids, rng.randint(1, len(ids)))})
        r = L.route_info({"model": g, "stops": stops})
        if r and set(r["boxes"]) <= fs: cands.append(r)
    seen = set(); out = []
    for r in cands:
        k = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
        if k in seen: continue
        seen.add(k); out.append(r)
    return out

if __name__ == "__main__":
    seed = int(sys.argv[1]); n_rand = int(sys.argv[2]); tl = float(sys.argv[3]); out_name = sys.argv[4]
    rng = random.Random(seed); t0 = time.time()
    base = json.load(open(BASE, encoding="utf-8"))
    specs = [T.norm(s) for s in base["specs"]]
    plan = T.decode(specs, D, require_all=True); m0 = plan["metrics"]
    print("base n=%d T=%.3f E=%.4f" % (m0["sorties"], m0["makespan_s"], m0["energy_kwh"]), flush=True)
    cboxes = sorted({b for s in specs if s["model"] == "C" for b in s["stops"][0]["ids"]} | {b for s in specs if s["model"] == "C" for st in s["stops"] for b in st["ids"]})
    fixed = [s for s in specs if s["model"] != "C"]
    fixed_info = [L.route_info(s) for s in fixed]
    fixed_boxes = {b for s in fixed for st in s["stops"] for b in st["ids"]}
    free = [b for b in cboxes if b not in fixed_boxes]
    print("free(C boxes)=%d fixed sorties=%d" % (len(free), len(fixed)), flush=True)
    pool = L.load_pool()
    cands = gen_cands(free, pool, rng, n_rand)
    print("candidates=%d" % len(cands), flush=True)
    n = len(cands); rows, cols, vals, lb, ub = [], [], [], [], []; row = 0
    for b in free:
        hit = False
        for j, r in enumerate(cands):
            if b in r["boxes"]: rows.append(row); cols.append(j); vals.append(1.0); hit = True
        if not hit: print("missing box", b); sys.exit(1)
        lb.append(1.0); ub.append(1.0); row += 1
    for j in range(n): rows.append(row); cols.append(j); vals.append(1.0)
    lb.append(1.0); ub.append(6.0); row += 1          # 总架次数固定 6
    fw = {g: 0.0 for g in "ABC"}; fd = {g: [] for g in "ABC"}
    for r in fixed_info:
        fw[r["model"]] += r["duration"]; fd[r["model"]].append((r["deadline"], r["duration"]))
    for g in "ABC":
        for j, r in enumerate(cands):
            if r["model"] == g: rows.append(row); cols.append(j); vals.append(r["duration"])
        lb.append(-np.inf); ub.append(NSHIP[g] * CAP - fw[g]); row += 1
    for g in "ABC":
        for j, r in enumerate(cands):
            if r["model"] != g: continue
            t = r["deadline"]; f = sum(d for (dd, d) in fd[g] if dd <= t + 1e-9)
            for k, r2 in enumerate(cands):
                if r2["model"] == g and r2["deadline"] <= t + 1e-9: rows.append(row); cols.append(k); vals.append(r2["duration"])
            lb.append(-np.inf); ub.append(NSHIP[g] * t - f); row += 1
    A = coo_matrix((vals, (rows, cols)), shape=(row, n)).tocsr()
    c = np.array([r["energy"] + 1e-4 for r in cands])
    res = milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
               integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
               options={"time_limit": tl, "mip_rel_gap": 0.0, "disp": False})
    print("MILP status", res.status, res.message, flush=True)
    if res.x is None: sys.exit(1)
    sel = [cands[j] for j in range(n) if res.x[j] > 0.5]
    print("selected %d routes, energy=%.4f" % (len(sel), sum(r["energy"] for r in sel)), flush=True)
    new_specs = fixed + [{"model": r["model"], "stops": r["stops"]} for r in sel]
    full, ordered = T.schedule_ordered(new_specs)
    if full is None: print("schedule FAIL"); sys.exit(1)
    m = full["metrics"]
    print("full: n=%d T=%.3f E=%.4f hard=%.1f tardy=%.1f" % (m["sorties"], m["makespan_s"], m["energy_kwh"], m["hard_excess_s"], m["weighted_tardiness"]), flush=True)
    if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6 and m["makespan_s"] <= CAP + 1e-6 and m["sorties"] <= 23 and m["energy_kwh"] < m0["energy_kwh"] - 1e-6:
        json.dump({"specs": ordered, "metrics": m}, open(os.path.join(HERE, "runs", out_name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(">>> ACCEPTED energy %.4f -> %.4f, saved %s" % (m0["energy_kwh"], m["energy_kwh"], out_name))
    else:
        print(">>> rejected")
    print("elapsed %.1fs" % (time.time()-t0))



