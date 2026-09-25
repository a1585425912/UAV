# -*- coding: utf-8 -*-
"""q2_lns：多架次联合重构（related removal + 含时限集合划分 MILP 修复 + 时限感知排程）。

move：释放 k=3..6 个相关架次，尝试用 <=k-1 个架次服务同一批货箱；候选架次可跨机型。
修复 MILP 含：逐箱覆盖、架次数上限、逐机型工时预算(相对固定架次)、有效时限必要条件。
排程由 feas_sched 逐机型完成（硬时限/零延误约束内最小化完成时间）。
"""
import sys, os, json, time, random, itertools
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as FS
from 问题二_调度核心 import load_data, decode, evaluate_sortie
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
NSHIP = {"A": 4, "B": 2, "C": 2}
BOXES = sorted(D["boxes"].keys())

def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}

def route_info(spec):
    spec = norm(spec)
    ev = evaluate_sortie(spec, D)
    if ev is None: return None
    off = ev["delivery_offsets_s"]; boxes = ev["box_ids"]
    ls = min(min(D["boxes"][b]["due"] - off[b],
                 (D["boxes"][b]["hard"] - off[b]) if D["boxes"][b]["hard"] is not None else 1e18) for b in boxes)
    if ls < 0: return None
    return {"model": spec["model"], "stops": spec["stops"], "boxes": boxes,
            "duration": ev["duration_s"], "energy": ev["energy_kwh"], "ls": ls,
            "deadline": ls + ev["duration_s"], "soc": ev["return_soc"]}

def build_pool(extra_rand=0, seed=0):
    pool = {}
    def add(spec):
        r = route_info(spec)
        if r is None: return
        key = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
        pool.setdefault(key, r)
    for f in ["par4.json", "par4b.json", "prio.json", "pareto.json"]:
        p = os.path.join(HERE, "runs", f)
        if not os.path.exists(p): continue
        for rec in json.load(open(p, encoding="utf-8")):
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
            for s in json.load(open(p, encoding="utf-8"))["sorties"]: add(s)
    if extra_rand:
        rng = random.Random(seed)
        by_area = {}
        for b, bx in D["boxes"].items(): by_area.setdefault(bx["area"], []).append(b)
        areas = sorted(by_area)
        for _ in range(extra_rand):
            g = rng.choice("ABC"); chosen = rng.sample(areas, rng.randint(1, 3))
            stops = []
            for a in chosen:
                ids = by_area[a]; stops.append({"area": a, "ids": rng.sample(ids, rng.randint(1, len(ids)))})
            add({"model": g, "stops": stops})
    return list(pool.values())

def schedule(specs, budget_bc=6.0, budget_a=10.0):
    by = {}
    for s in specs: by.setdefault(s["model"], []).append(s)
    ordered = []
    for g, chunk in by.items():
        res, how = FS.best_feasible_order(chunk, budget_bc if g != "A" else budget_a)
        if res is None: return None
        m, order = res
        ordered += [chunk[i] for i in order]
    return decode(ordered, D, require_all=True)

def repair(fixed, removed, pool, T_cap, extra_time=8.0):
    free = sorted({b for r in removed for b in r["boxes"]})
    fs = set(free)
    cands = [r for r in pool if set(r["boxes"]) <= fs]
    # 若候选不足，补上被移除架次本身
    for r in removed:
        if not any(c["model"] == r["model"] and c["stops"] == r["stops"] for c in cands): cands.append(r)
    if not cands: return None
    BIDX = {b: i for i, b in enumerate(free)}
    n = len(cands)
    rows, cols, vals, lb, ub = [], [], [], [], []
    row = 0
    for b in free:
        hit = False
        for j, r in enumerate(cands):
            if b in r["boxes"]: rows.append(row); cols.append(j); vals.append(1.0); hit = True
        if not hit: return None
        lb.append(1.0); ub.append(1.0); row += 1
    for j in range(n):
        rows.append(row); cols.append(j); vals.append(1.0)
    lb.append(-np.inf); ub.append(float(len(removed) - 1)); row += 1
    # 固定架次的逐机型工时与期限分布
    fixed_work = {g: 0.0 for g in "ABC"}; fixed_dead = {g: [] for g in "ABC"}
    for r in fixed:
        fixed_work[r["model"]] += r["duration"]; fixed_dead[r["model"]].append((r["deadline"], r["duration"]))
    for g in "ABC":
        for j, r in enumerate(cands):
            if r["model"] == g: rows.append(row); cols.append(j); vals.append(r["duration"])
        lb.append(-np.inf); ub.append(NSHIP[g] * T_cap - fixed_work[g]); row += 1
    for g in "ABC":
        for j, r in enumerate(cands):
            if r["model"] != g: continue
            t = r["deadline"]
            fw = sum(d for (dd, d) in fixed_dead[g] if dd <= t + 1e-9)
            for k, r2 in enumerate(cands):
                if r2["model"] == g and r2["deadline"] <= t + 1e-9:
                    rows.append(row); cols.append(k); vals.append(r2["duration"])
            lb.append(-np.inf); ub.append(NSHIP[g] * t - fw); row += 1
    A = coo_matrix((vals, (rows, cols)), shape=(row, n)).tocsr()
    c = np.array([r["energy"] + 1e-4 for r in cands])
    res = milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
               integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
               options={"time_limit": extra_time, "mip_rel_gap": 0.0, "disp": False})
    if res.x is None: return None
    return [cands[j] for j in range(n) if res.x[j] > 0.5]

def related_removal(routes, rng, k, mode="random"):
    n = len(routes)
    if mode == "longC":
        seed = max(range(n), key=lambda i: routes[i]["duration"] if routes[i]["model"] == "C" else -1)
    else:
        seed = rng.randrange(n)
    areas = {i: {st["area"] for st in routes[i]["stops"]} for i in range(n)}
    sc = []
    for i in range(n):
        if i == seed: continue
        ov = len(areas[seed] & areas[i]) / max(1, len(areas[seed] | areas[i]))
        same = 1.0 if routes[i]["model"] == routes[seed]["model"] else 0.0
        sc.append((-(ov + 0.5 * same), i))
    sc.sort()
    chosen = [seed] + [i for _, i in sc[:k - 1]]
    return sorted(chosen)

if __name__ == "__main__":
    k_max = int(sys.argv[1]); T_cap = float(sys.argv[2]); iters = int(sys.argv[3]); seed = int(sys.argv[4])
    start_file = sys.argv[5] if len(sys.argv) > 5 else os.path.join(HERE, "runs", "best23_byT.json")
    rng = random.Random(seed)
    t0 = time.time()
    pool = build_pool(extra_rand=8000, seed=seed)
    print("pool=%d %.1fs" % (len(pool), time.time()-t0), flush=True)
    start = json.load(open(start_file, encoding="utf-8"))
    fixed_all = [norm(s) for s in start["specs"]]
    base = decode(fixed_all, D, require_all=True)
    best = base; best_specs = fixed_all
    print("start: n=%d T=%.3f E=%.3f" % (base["metrics"]["sorties"], base["metrics"]["makespan_s"], base["metrics"]["energy_kwh"]), flush=True)
    for it in range(iters):
        k = rng.randint(3, k_max)
        idx = related_removal([route_info(s) for s in best_specs], rng, k, "random" if rng.random() < 0.7 else "longC")
        removed = [best_specs[i] for i in idx]
        fixed = [best_specs[i] for i in range(len(best_specs)) if i not in set(idx)]
        sel = repair([route_info(s) for s in fixed], [route_info(s) for s in removed], pool, T_cap)
        if sel is None: continue
        new_specs = fixed + [{"model": r["model"], "stops": r["stops"]} for r in sel]
        full = schedule(new_specs)
        if full is None: continue
        m = full["metrics"]
        if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: continue
        cur = (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"])
        cand = (m["sorties"], m["makespan_s"], m["energy_kwh"])
        if cand < cur and m["makespan_s"] <= T_cap + 1e-6:
            best, best_specs = full, new_specs
            print("[%4d] ACCEPT n=%d T=%.3f E=%.3f  (%.1fs)" % (it, cand[0], cand[1], cand[2], time.time()-t0), flush=True)
            json.dump({"specs": new_specs, "metrics": m}, open(os.path.join(HERE, "runs", "lns_best_n%d_T%d.json" % (k_max, int(T_cap))), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if (it + 1) % 50 == 0:
            print("[%4d] best n=%d T=%.3f E=%.3f  %.1fs" % (it+1, best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"], time.time()-t0), flush=True)
    print("FINAL n=%d T=%.3f E=%.3f" % (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"]))
