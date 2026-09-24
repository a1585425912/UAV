import sys, os, json, time, copy, random, math
sys.path.insert(0, r"D:\git\math_modeling\UAV"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 问题二_调度核心 import load_data, decode
import q2_solver4 as S
from joblib import Parallel, delayed
S.PROFILES["时间极端"] = (1000.0, 1.0, 1.0)
HERE = os.path.dirname(os.path.abspath(__file__))
_D = None
def DD():
    global _D
    if _D is None: _D = load_data()
    return _D
def K(m):
    return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["makespan_s"], m["energy_kwh"], m["sorties"])
def search(start_specs, iterations, seed):
    dd = DD(); rng = random.Random(seed); weights = S.PROFILES.setdefault("时间极端", (1000.0, 1.0, 1.0))
    cur = copy.deepcopy(start_specs); cp = decode(cur, dd, require_all=True); cs = S.penalty(cp["metrics"], weights)
    best = (copy.deepcopy(cur), cp)
    t0 = max(100.0, cs*.02); t1 = max(1.0, t0*.001)
    opw = {o: 1.0 for o in S.OPERATORS}; oph = {o:0 for o in S.OPERATORS}; opr = {o:0.0 for o in S.OPERATORS}
    for it in range(iterations):
        op = rng.choices(S.OPERATORS, weights=[opw[o] for o in S.OPERATORS], k=1)[0]; oph[op]+=1
        cand_specs = S.neighbor(cur, rng, op, dd)
        if cand_specs is None: continue
        cand = decode(cand_specs, dd, require_all=True)
        if cand is None: continue
        m = cand["metrics"]
        if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6 and K(m) < K(best[1]["metrics"]):
            best = (copy.deepcopy(cand_specs), cand)
        sc = S.penalty(m, weights); improved = sc < cs - 1e-7
        temp = t0*(t1/t0)**(it/max(1, iterations-1))
        if sc <= cs or rng.random() < math.exp(min(0,(cs-sc)/temp)):
            cur, cp, cs = cand_specs, cand, sc; opr[op] += 9 if improved else 3
        if (it+1) % 100 == 0:
            for o in S.OPERATORS:
                if oph[o]: opw[o] = max(.1, .9*opw[o] + .1*opr[o]/oph[o])
                oph[o]=0; opr[o]=0.0
    return {"specs": best[0], "metrics": best[1]["metrics"]}
def worker(b, iters, seed): return search(b, iters, seed)
if __name__ == "__main__":
    W = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
    def load(p):
        o = json.load(open(p, encoding="utf-8"))
        return [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in o["sorties"]]
    bases = [("time", load(W + r"\方案_时间优先(主方案)_完整方案.json"))]
    from 问题二_参考路线种子 import optimize_seed
    hot, warm, milp = optimize_seed(DD())
    bases.append(("hot", hot))
    iters, nseed, n_jobs, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    tasks = [(tag, b, 5000+s) for tag, b in bases for s in range(nseed)]
    print("tasks", len(tasks), flush=True)
    res = []; t0 = time.time()
    gen = Parallel(n_jobs=n_jobs, verbose=5, return_as="generator_unordered")(delayed(worker)(b, iters, seed) for tag, b, seed in tasks)
    for i, r in enumerate(gen):
        r["base"] = tasks[i][0]; r["seed"] = tasks[i][2]; res.append(r)
        bt = min(x["metrics"]["makespan_s"] for x in res)
        print("[%3d/%3d] %.1fs best_time=%.3f" % (i+1, len(tasks), time.time()-t0, bt), flush=True)
        if i % 3 == 0 or i == len(tasks)-1: json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("BEST", min(res, key=lambda x: (x["metrics"]["makespan_s"], x["metrics"]["energy_kwh"]))["metrics"])




