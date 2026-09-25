# -*- coding: utf-8 -*-
"""q2_lns2：跨机型交换 + 邻接架次联合重构（related removal + 现场候选生成 + 含时限集合划分 MILP + 时限感知排程）。

move：释放 R（目标，优先 C 长架次）+ S（邻接架次）共 k 个架次，要求用 <= k-1 个架次
覆盖它们的全部货箱；候选架次允许任意机型与 1-3 站组合，现场随机生成 + 历史池合并。
修复 MILP 含逐箱覆盖、架次数上限、逐机型工时预算、有效时限必要条件；排程用 feas_sched。
"""
import sys, os, json, time, random
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as FS
from 问题二_调度核心 import load_data, decode, evaluate_sortie
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
NSHIP = {"A": 4, "B": 2, "C": 2}
def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}
_CACHE = {}
def route_info(spec):
    spec = norm(spec)
    key = (spec["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in spec["stops"]))
    if key in _CACHE: return _CACHE[key]
    ev = evaluate_sortie(spec, D)
    if ev is None: _CACHE[key] = None; return None
    off = ev["delivery_offsets_s"]; boxes = ev["box_ids"]
    ls = min(min(D["boxes"][b]["due"] - off[b],
                 (D["boxes"][b]["hard"] - off[b]) if D["boxes"][b]["hard"] is not None else 1e18) for b in boxes)
    if ls < 0: _CACHE[key] = None; return None
    r = {"model": spec["model"], "stops": spec["stops"], "boxes": boxes, "duration": ev["duration_s"],
         "energy": ev["energy_kwh"], "ls": ls, "deadline": ls + ev["duration_s"], "soc": ev["return_soc"]}
    _CACHE[key] = r; return r

def load_pool():
    pool = {}
    for f in ["par4.json", "par4b.json", "prio.json", "pareto.json"]:
        p = os.path.join(HERE, "runs", f)
        if not os.path.exists(p): continue
        for rec in json.load(open(p, encoding="utf-8")):
            if not isinstance(rec, dict): continue
            for kk in ("time", "energy", "sorties"):
                if kk in rec and isinstance(rec[kk], dict) and "specs" in rec[kk]:
                    for s in rec[kk]["specs"]:
                        r = route_info(s)
                        if r:
                            key = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
                            pool[key] = r
            if "specs" in rec:
                for s in rec["specs"]:
                    r = route_info(s)
                    if r:
                        key = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
                        pool[key] = r
    return list(pool.values())

def gen_candidates(free_boxes, pool, rng, n_rand=4000):
    fs = set(free_boxes)
    cands = [r for r in pool if set(r["boxes"]) <= fs]
    by_area = {}
    for b in free_boxes: by_area.setdefault(D["boxes"][b]["area"], []).append(b)
    areas = sorted(by_area)
    for _ in range(n_rand):
        g = rng.choice("ABC")
        na = rng.randint(1, min(3, len(areas)))
        chosen = rng.sample(areas, na)
        stops = []
        ok = True
        used = set()
        for a in chosen:
            ids = [b for b in by_area[a] if b not in used]
            if not ids: ok = False; break
            k = rng.randint(1, len(ids)); pick = rng.sample(ids, k); used |= set(pick)
            stops.append({"area": a, "ids": pick})
        if not ok: continue
        r = route_info({"model": g, "stops": stops})
        if r and set(r["boxes"]) <= fs: cands.append(r)
    seen = set(); out = []
    for r in cands:
        key = (r["model"], tuple((st["area"], tuple(sorted(st["ids"]))) for st in r["stops"]))
        if key in seen: continue
        seen.add(key); out.append(r)
    return out

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

def repair(fixed, free_boxes, max_new, pool, rng, T_cap, tl=10.0, n_rand=4000):
    cands = gen_candidates(free_boxes, pool, rng, n_rand)
    if not cands: return None
    free = sorted(free_boxes); n = len(cands)
    rows, cols, vals, lb, ub = [], [], [], [], []; row = 0
    for b in free:
        hit = False
        for j, r in enumerate(cands):
            if b in r["boxes"]: rows.append(row); cols.append(j); vals.append(1.0); hit = True
        if not hit: return None
        lb.append(1.0); ub.append(1.0); row += 1
    for j in range(n): rows.append(row); cols.append(j); vals.append(1.0)
    lb.append(-np.inf); ub.append(float(max_new)); row += 1
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
               options={"time_limit": tl, "mip_rel_gap": 0.0, "disp": False})
    if res.x is None: return None
    return [cands[j] for j in range(n) if res.x[j] > 0.5]

def pick_move(specs, infos, rng, T_cap):
    n = len(specs)
    cand_R = [i for i in range(n) if infos[i]["model"] == "C"]
    if not cand_R: cand_R = list(range(n))
    seedR = max(cand_R, key=lambda i: infos[i]["duration"])
    areas = {i: {st["area"] for st in infos[i]["stops"]} for i in range(n)}
    rel = sorted((i for i in range(n) if i != seedR),
                 key=lambda i: -(len(areas[seedR] & areas[i]) / max(1, len(areas[seedR] | areas[i]))))
    kR = rng.randint(1, 2)
    R = [seedR] + [i for i in rel if i not in [seedR]][:kR]
    R = list(dict.fromkeys(R))
    rest = [i for i in range(n) if i not in R]
    kS = rng.randint(0, 2)
    S = rng.sample(rest, min(kS, len(rest)))
    return R, S

if __name__ == "__main__":
    T_cap = float(sys.argv[1]); iters = int(sys.argv[2]); seed = int(sys.argv[3])
    start_file = sys.argv[4]; out_name = sys.argv[5]
    rng = random.Random(seed); t0 = time.time()
    pool = load_pool(); print("pool=%d" % len(pool), flush=True)
    start = json.load(open(start_file, encoding="utf-8"))
    best_specs = [norm(s) for s in start["specs"]]
    best = decode(best_specs, D, require_all=True)
    print("start n=%d T=%.3f E=%.3f" % (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"]), flush=True)
    accepted = 0
    for it in range(iters):
        infos = [route_info(s) for s in best_specs]
        R, S = pick_move(best_specs, infos, rng, T_cap)
        idx = sorted(set(R) | set(S))
        free_boxes = {b for i in idx for b in infos[i]["boxes"]}
        fixed_info = [infos[i] for i in range(len(infos)) if i not in set(idx)]
        fixed_specs = [best_specs[i] for i in range(len(infos)) if i not in set(idx)]
        sel = repair(fixed_info, free_boxes, len(idx) - 1, pool, rng, T_cap, tl=8.0, n_rand=3000)
        if sel is None: continue
        new_specs = fixed_specs + [{"model": r["model"], "stops": r["stops"]} for r in sel]
        full = schedule(new_specs)
        if full is None: continue
        m = full["metrics"]
        if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: continue
        cur = (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"])
        cand = (m["sorties"], m["makespan_s"], m["energy_kwh"])
        # 接受：架次更少且 T<=cap；或架次不增而时间更短
        improve = (cand[0] < cur[0] and m["makespan_s"] <= T_cap + 1e-6) or (cand[0] <= cur[0] and cand[1] < cur[1] - 1e-6 and m["makespan_s"] <= T_cap + 1e-6)
        if improve:
            best_specs, best = new_specs, full
            accepted += 1
            print("[%4d] ACCEPT n=%d T=%.3f E=%.3f (%.1fs)" % (it, cand[0], cand[1], cand[2], time.time()-t0), flush=True)
            json.dump({"specs": new_specs, "metrics": m}, open(os.path.join(HERE, "runs", out_name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if (it + 1) % 25 == 0:
            print("[%4d] n=%d T=%.3f E=%.3f acc=%d %.1fs" % (it+1, best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"], accepted, time.time()-t0), flush=True)
    print("FINAL n=%d T=%.3f E=%.3f accepted=%d" % (best["metrics"]["sorties"], best["metrics"]["makespan_s"], best["metrics"]["energy_kwh"], accepted))
