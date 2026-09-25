# -*- coding: utf-8 -*-
"""joint_recon2：候选架次池 + 含时限必要条件的集合划分 MILP + 时限感知排程 + 惰性 no-good 割。

与 joint_recon.py / pool_opt.py 的关键区别：
1) 每个候选架次预计算最晚开始时间 LS（满足硬时限与零延误），并换算完成期限 D=LS+duration；
2) MILP 加入有效必要条件：对每个机型、每个期限 t，sum_{r:D_r<=t} d_r x_r <= n_g * t；
3) 选出的架次交给 feas_sched 的逐机型时限感知调度（B/C 全排列、A 局部搜索）；
4) 排程失败只加 no-good 割重解，不把子问题失败当不可行。
"""
import sys, os, json, time, random, itertools
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix, vstack
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as FS
from 问题二_调度核心 import load_data, decode, evaluate_sortie
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
NSHIP = {"A": 4, "B": 2, "C": 2}
BOXES = sorted(D["boxes"].keys()); BIDX = {b: i for i, b in enumerate(BOXES)}

def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}

def route_feasible(spec):
    """返回 (duration, energy, boxes, LS, return_soc)；不可行返回 None。"""
    spec = norm(spec)
    ev = evaluate_sortie(spec, D)
    if ev is None: return None
    off = ev["delivery_offsets_s"]; boxes = ev["box_ids"]
    ls = min(min(D["boxes"][b]["due"] - off[b],
                 (D["boxes"][b]["hard"] - off[b]) if D["boxes"][b]["hard"] is not None else 1e18) for b in boxes)
    if ls < 0: return None
    return {"model": spec["model"], "stops": spec["stops"], "boxes": boxes,
            "duration": ev["duration_s"], "energy": ev["energy_kwh"], "ls": ls, "soc": ev["return_soc"]}

def build_pool(extra_rand=0, seed=0):
    pool = {}
    def add(spec):
        r = route_feasible(spec)
        if r is None: return
        key = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
        if key in pool: return
        pool[key] = r
    for f in ["par4b.json", "par4.json", "prio.json", "pareto.json", "par_r1.json", "par_r2.json"]:
        p = os.path.join(HERE, "runs", f)
        if not os.path.exists(p):
            p = os.path.join(os.path.dirname(os.path.dirname(HERE)), "results", "问题二_改进方案", f)
        if not os.path.exists(p): continue
        try: obj = json.load(open(p, encoding="utf-8"))
        except Exception: continue
        for rec in obj:
            if not isinstance(rec, dict): continue
            for kk in ("time", "energy", "sorties"):
                if kk in rec and isinstance(rec[kk], dict) and "specs" in rec[kk]:
                    for s in rec[kk]["specs"]: add(s)
            if "specs" in rec:
                for s in rec["specs"]: add(s)
    for f in ["方案_时间优先(主方案)_完整方案.json", "方案_均衡_完整方案.json",
              "方案_能耗优先_完整方案.json", "方案_架次优先_完整方案.json"]:
        p = os.path.join(os.path.dirname(os.path.dirname(HERE)), "results", "问题二_改进方案", f)
        if os.path.exists(p):
            o = json.load(open(p, encoding="utf-8"))
            for s in o["sorties"]: add(s)
    # 随机重组成员：对每个服务区的货箱随机分组，再组合 1-3 区
    if extra_rand:
        rng = random.Random(seed)
        by_area = {}
        for b, bx in D["boxes"].items(): by_area.setdefault(bx["area"], []).append(b)
        areas = sorted(by_area)
        for _ in range(extra_rand):
            g = rng.choice("ABC"); na = rng.randint(1, 3); chosen = rng.sample(areas, na)
            stops = []
            for a in chosen:
                ids = by_area[a]; k = rng.randint(1, len(ids))
                stops.append({"area": a, "ids": rng.sample(ids, k)})
            add({"model": g, "stops": stops})
    return list(pool.values())

def schedule(sel, budget_bc=8.0, budget_a=15.0):
    by = {}
    for i, r in enumerate(sel): by.setdefault(r["model"], []).append(i)
    for g, idxs in by.items():
        chunk = [{"model": sel[i]["model"], "stops": sel[i]["stops"]} for i in idxs]
        res, how = FS.best_feasible_order(chunk, budget_bc if g != "A" else budget_a)
        if res is None: return None
    # 通过 feas_sched 的顺序重建完整方案，再取 makespan
    final = []
    for g, idxs in by.items():
        chunk = [{"model": sel[i]["model"], "stops": sel[i]["stops"]} for i in idxs]
        res, how = FS.best_feasible_order(chunk, budget_bc if g != "A" else budget_a)
        m, order = res
        final += [chunk[o] for o in order]
    full = decode(final, D, require_all=True)
    return full

def solve_milp(pool, n_max, T_cap, time_limit, cuts, obj="energy"):
    n = len(pool)
    rows, cols, vals, lb, ub = [], [], [], [], []
    r = 0
    for b in BOXES:
        hit = False
        for j, rt in enumerate(pool):
            if b in rt["boxes"]:
                rows.append(r); cols.append(j); vals.append(1.0); hit = True
        if not hit: return None
        lb.append(1.0); ub.append(1.0); r += 1
    # 架次数上限
    for j in range(n):
        rows.append(r); cols.append(j); vals.append(1.0)
    lb.append(-np.inf); ub.append(float(n_max)); r += 1
    # 每机型工时预算 <= n_g * T_cap
    for g in "ABC":
        for j, rt in enumerate(pool):
            if rt["model"] == g:
                rows.append(r); cols.append(j); vals.append(rt["duration"])
        lb.append(-np.inf); ub.append(NSHIP[g] * T_cap); r += 1
    # 有效时限必要条件：完成期限 D_r = LS_r + duration
    for g in "ABC":
        ids = [j for j, rt in enumerate(pool) if rt["model"] == g]
        ids.sort(key=lambda j: pool[j]["ls"] + pool[j]["duration"])
        acc = []
        for j in ids:
            acc.append(j)
            for k in acc:
                rows.append(r); cols.append(k); vals.append(pool[k]["duration"])
            lb.append(-np.inf); ub.append(NSHIP[g] * (pool[j]["ls"] + pool[j]["duration"])); r += 1
    A = coo_matrix((vals, (rows, cols)), shape=(r, n)).tocsr()
    if cuts:
        cr, cc, cv, cl, cu = [], [], [], [], []
        for k, S in enumerate(cuts):
            for j in S: cr.append(k); cc.append(j); cv.append(1.0)
            cl.append(-np.inf); cu.append(len(S) - 1)
        A = vstack([A, coo_matrix((cv, (cr, cc)), shape=(len(cuts), n)).tocsr()]).tocsr()
        lb = np.concatenate([lb, np.array(cl)]); ub = np.concatenate([ub, np.array(cu)])
    c = np.array([rt["energy"] + 1e-4 for rt in pool])
    res = milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
               integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
               options={"time_limit": time_limit, "mip_rel_gap": 0.0, "disp": False})
    return res

if __name__ == "__main__":
    n_max = int(sys.argv[1]); T_cap = float(sys.argv[2]); time_limit = float(sys.argv[3]); max_rounds = int(sys.argv[4])
    extra = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    t0 = time.time()
    pool = build_pool(extra_rand=extra)
    print("pool=%d  %.1fs" % (len(pool), time.time()-t0), flush=True)
    cuts = []; best = None
    for rnd in range(max_rounds):
        res = solve_milp(pool, n_max, T_cap, time_limit, cuts)
        if res is None or res.x is None:
            print("round %d: no MILP solution (%s)" % (rnd, None if res is None else res.message), flush=True); break
        selidx = [j for j in range(len(pool)) if res.x[j] > 0.5]
        sel = [pool[j] for j in selidx]
        full = schedule(sel)
        mm = None if full is None else full["metrics"]
        print("round %d: MILP n=%d E=%.4f -> %s" % (rnd, len(sel), sum(r["energy"] for r in sel),
              "schedule FAIL" if mm is None else "T=%.3f E=%.4f hard=%.1f tardy=%.1f" % (
                  mm["makespan_s"], mm["energy_kwh"], mm["hard_excess_s"], mm["weighted_tardiness"])), flush=True)
        if mm is not None and mm["hard_excess_s"] <= 1e-6 and mm["weighted_tardiness"] <= 1e-6 and mm["makespan_s"] <= T_cap + 1e-6:
            best = {"n_max": n_max, "T_cap": T_cap, "specs": [{"model": r["model"], "stops": r["stops"]} for r in sel], "metrics": mm}
            print(">>> FEASIBLE  T=%.3f E=%.4f n=%d" % (mm["makespan_s"], mm["energy_kwh"], mm["sorties"]), flush=True)
            break
        cuts.append(selidx)
    if best:
        out = os.path.join(HERE, "runs", "jr2_n%d_T%d.json" % (n_max, int(T_cap)))
        json.dump(best, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("saved", out)
    print("elapsed %.1fs" % (time.time()-t0))
