# -*- coding: utf-8 -*-
"""q2_spp_minT：以完成时间为目标的受限集合划分（22 架次闯关）。

与 q2_spp_local 同一套路线池与约束，但目标改为最小化 Z：
    sum_{r in 机型g} d_r z_r <= n_g * Z   (g=A,B,C)
    min Z + eps * energy
保持 覆盖=1、架次数<=N_target、有效时限必要条件；选出后做时限感知排程并检查真实 makespan。
"""
import sys, os, json, time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q2_lns2 as L
import q2_transfer as T
import q2_spp_local as S
D = L.D; HERE = os.path.dirname(os.path.abspath(__file__)); NSHIP = L.NSHIP
BOXES = sorted(D["boxes"].keys())

def solve_minZ(pool, inc_keys, N_target, Z_ub, k, tl=90.0):
    n = len(pool); N = n + 1
    rows, cols, vals, lb, ub = [], [], [], [], []; row = 0
    for b in BOXES:
        for j, r in enumerate(pool):
            if b in r["boxes"]: rows.append(row); cols.append(j); vals.append(1.0)
        lb.append(1.0); ub.append(1.0); row += 1
    for j in range(n): rows.append(row); cols.append(j); vals.append(1.0)
    lb.append(-np.inf); ub.append(float(N_target)); row += 1
    for g in "ABC":
        for j, r in enumerate(pool):
            if r["model"] == g: rows.append(row); cols.append(j); vals.append(r["duration"])
        rows.append(row); cols.append(n); vals.append(-NSHIP[g])
        lb.append(-np.inf); ub.append(0.0); row += 1
    for g in "ABC":
        for j, r in enumerate(pool):
            if r["model"] != g: continue
            t = r["deadline"]
            for kk, r2 in enumerate(pool):
                if r2["model"] == g and r2["deadline"] <= t + 1e-9:
                    rows.append(row); cols.append(kk); vals.append(r2["duration"])
            lb.append(-np.inf); ub.append(NSHIP[g] * t); row += 1
    inc_idx = [j for j, r in enumerate(pool)
               if (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"])) in inc_keys]
    if inc_idx and k < len(inc_idx):
        for j in inc_idx: rows.append(row); cols.append(j); vals.append(-1.0)
        lb.append(-np.inf); ub.append(-(len(inc_idx) - k)); row += 1
    A = coo_matrix((vals, (rows, cols)), shape=(row, N)).tocsr()
    c = np.zeros(N); c[n] = 1.0
    for j, r in enumerate(pool): c[j] = 1e-6 * r["energy"]
    integ = np.concatenate([np.ones(n), [0]])
    return milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
                integrality=integ, bounds=Bounds(np.zeros(N), np.concatenate([np.ones(n), [Z_ub]])),
                options={"time_limit": tl, "mip_rel_gap": 0.0, "disp": False})

if __name__ == "__main__":
    N_target = int(sys.argv[1]); Z_ub = float(sys.argv[2]); start_file = sys.argv[3]
    ks = [int(x) for x in sys.argv[4].split(",")]; out = sys.argv[5]
    t0 = time.time()
    plans = S.collect_plans(); pool = S.build_pool(plans, top=80)
    print("pool=%d" % len(pool), flush=True)
    inc = json.load(open(start_file, encoding="utf-8")); inc_specs = [L.norm(s) for s in inc["specs"]]
    inc_keys = set()
    for s in inc_specs:
        r = L.route_info(s)
        if r: inc_keys.add((r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"])))
    best = inc
    for k in ks:
        res = solve_minZ(pool, inc_keys, N_target, Z_ub, k, tl=90.0)
        if res is None or res.x is None:
            print("k=%d: no solution (%s)" % (k, None if res is None else res.message), flush=True); continue
        sel = [pool[j] for j in range(len(pool)) if res.x[j] > 0.5]
        Z = float(res.x[len(pool)])
        specs = [{"model": r["model"], "stops": r["stops"]} for r in sel]
        full, ordered = T.schedule_ordered(specs)
        if full is None:
            print("k=%d: MILP n=%d Z=%.1f but schedule FAIL" % (k, len(sel), Z), flush=True); continue
        m = full["metrics"]
        print("k=%d: MILP n=%d Z=%.3f E=%.3f -> schedule n=%d T=%.3f E=%.4f hard=%.1f tardy=%.1f" % (
            k, len(sel), Z, sum(r["energy"] for r in sel), m["sorties"], m["makespan_s"], m["energy_kwh"],
            m["hard_excess_s"], m["weighted_tardiness"]), flush=True)
        if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6:
            if (m["sorties"], m["makespan_s"], m["energy_kwh"]) < (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"]):
                best = {"specs": ordered, "metrics": m}
                json.dump(best, open(os.path.join(HERE, "runs", out), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print("  >>> ACCEPTED n=%d T=%.3f E=%.4f" % (m["sorties"], m["makespan_s"], m["energy_kwh"]), flush=True)
    print("FINAL n=%d T=%.3f E=%.3f  %.1fs" % (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"], time.time()-t0))
