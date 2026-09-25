# -*- coding: utf-8 -*-
"""q2_spp_local：文献 (Friedrich & Elbert 2022) 的受限集合划分 + 局部分支(local branching)。

文献做法：ALNS 过程中把可行路线存入池；每隔若干迭代用 SPP 重组路线（当前最好解初始化、限时）。
本实现取"围绕现有最好解的路线池 + 局部分支约束"：
  覆盖:  每个货箱恰好一次
  架次数: sum z_r <= N_target
  资源:  逐机型工时 <= n_g * T_cap
  时限:  有效必要条件（完成期限 D_r = LS_r + d_r 的累计工时）
  局部分支: sum_{r in S_incumbent} z_r >= |S_incumbent| - k   （最多改动 k 条现有路线）
目标：最小化能耗（先保证可行性，再在可行解上比时间/能耗）。
"""
import sys, os, json, time, random
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix, vstack
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as FS
import q2_lns2 as L
D = L.D; HERE = os.path.dirname(os.path.abspath(__file__)); NSHIP = L.NSHIP
BOXES = sorted(D["boxes"].keys()); BIDX = {b: i for i, b in enumerate(BOXES)}

def collect_plans():
    plans = []
    for f in ["par4.json", "par4b.json", "prio.json", "pareto.json"]:
        p = os.path.join(HERE, "runs", f)
        if not os.path.exists(p): continue
        for rec in json.load(open(p, encoding="utf-8")):
            if not isinstance(rec, dict): continue
            for kk in ("time", "energy", "sorties"):
                if kk in rec and isinstance(rec[kk], dict) and "specs" in rec[kk]:
                    plans.append([L.norm(s) for s in rec[kk]["specs"]])
            if "specs" in rec: plans.append([L.norm(s) for s in rec["specs"]])
    for f in ["方案_时间优先(主方案)_完整方案.json", "方案_均衡_完整方案.json",
              "方案_能耗优先_完整方案.json", "方案_架次优先_完整方案.json",
              "方案_23架次_5903s_完整方案.json"]:
        p = os.path.join(os.path.dirname(HERE), "results", "问题二_改进方案", f)
        if os.path.exists(p):
            plans.append([L.norm(s) for s in json.load(open(p, encoding="utf-8"))["sorties"]])
    return plans

def build_pool(plans, top=60):
    scored = []
    for sp in plans:
        pl = L.decode(sp, D, require_all=True)
        if pl is None: continue
        m = pl["metrics"]
        if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: continue
        scored.append((m["makespan_s"], m["energy_kwh"], m["sorties"], sp))
    scored.sort(key=lambda x: (x[2], x[0], x[1]))
    keep = scored[:top] + [x for x in scored if x[2] <= 22]
    pool = {}
    for _, _, _, sp in keep:
        for s in sp:
            r = L.route_info(s)
            if r is None: continue
            key = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
            pool[key] = r
    return list(pool.values())

def solve(pool, inc_keys, N_target, T_cap, k, tl=90.0):
    n = len(pool)
    rows, cols, vals, lb, ub = [], [], [], [], []; row = 0
    for b in BOXES:
        hit = False
        for j, r in enumerate(pool):
            if b in r["boxes"]: rows.append(row); cols.append(j); vals.append(1.0); hit = True
        if not hit: return None
        lb.append(1.0); ub.append(1.0); row += 1
    for j in range(n): rows.append(row); cols.append(j); vals.append(1.0)
    lb.append(-np.inf); ub.append(float(N_target)); row += 1
    for g in "ABC":
        for j, r in enumerate(pool):
            if r["model"] == g: rows.append(row); cols.append(j); vals.append(r["duration"])
        lb.append(-np.inf); ub.append(NSHIP[g] * T_cap); row += 1
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
    A = coo_matrix((vals, (rows, cols)), shape=(row, n)).tocsr()
    c = np.array([r["energy"] + 1e-4 for r in pool])
    return milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
                integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
                options={"time_limit": tl, "mip_rel_gap": 0.0, "disp": False})

if __name__ == "__main__":
    N_target = int(sys.argv[1]); T_cap = float(sys.argv[2]); start_file = sys.argv[3]
    ks = [int(x) for x in sys.argv[4].split(",")]; out = sys.argv[5]
    t0 = time.time()
    plans = collect_plans(); pool = build_pool(plans, top=60)
    print("plans=%d pool=%d" % (len(plans), len(pool)), flush=True)
    inc = json.load(open(start_file, encoding="utf-8"))
    inc_specs = [L.norm(s) for s in inc["specs"]]
    inc_keys = set()
    for s in inc_specs:
        r = L.route_info(s)
        if r: inc_keys.add((r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"])))
    print("incumbent n=%d T=%.3f E=%.3f" % (inc["metrics"]["sorties"], inc["metrics"]["makespan_s"], inc["metrics"]["energy_kwh"]), flush=True)
    best = inc
    for k in ks:
        res = solve(pool, inc_keys, N_target, T_cap, k, tl=90.0)
        if res is None or res.x is None:
            print("k=%d: no solution (%s)" % (k, None if res is None else res.message), flush=True); continue
        sel = [pool[j] for j in range(len(pool)) if res.x[j] > 0.5]
        specs = [{"model": r["model"], "stops": r["stops"]} for r in sel]
        full, ordered = L and None, None
        import q2_transfer as T
        full, ordered = T.schedule_ordered(specs)
        if full is None:
            print("k=%d: MILP n=%d E=%.3f but schedule FAIL" % (k, len(sel), sum(r["energy"] for r in sel)), flush=True); continue
        m = full["metrics"]
        print("k=%d: MILP n=%d E=%.4f -> schedule n=%d T=%.3f E=%.4f hard=%.1f tardy=%.1f" % (
            k, len(sel), sum(r["energy"] for r in sel), m["sorties"], m["makespan_s"], m["energy_kwh"],
            m["hard_excess_s"], m["weighted_tardiness"]), flush=True)
        if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6 and m["makespan_s"] <= T_cap + 1e-6:
            if (m["sorties"], m["makespan_s"], m["energy_kwh"]) < (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"]):
                best = {"specs": ordered, "metrics": m}
                json.dump(best, open(os.path.join(HERE, "runs", out), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print("  >>> ACCEPTED n=%d T=%.3f E=%.4f" % (m["sorties"], m["makespan_s"], m["energy_kwh"]), flush=True)
    print("FINAL n=%d T=%.3f E=%.3f  %.1fs" % (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"], time.time()-t0))
