import sys, os, json, time, copy, random, math
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 问题二_调度核心 import load_data, decode
import q2_solver4 as S
from joblib import Parallel, delayed
HERE = os.path.dirname(os.path.abspath(__file__))
_D = None
def DD():
    global _D
    if _D is None: _D = load_data()
    return _D
KINDS = ("time", "energy", "sorties")
def K(m, kind):
    if kind == "time":   return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["makespan_s"], m["energy_kwh"], m["sorties"])
    if kind == "energy": return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["energy_kwh"], m["makespan_s"], m["sorties"])
    return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["sorties"], m["makespan_s"], m["energy_kwh"])
def search_prio(start_specs, prop, iterations, seed):
    dd = DD(); rng = random.Random(seed); weights = S.PROFILES[prop]
    cur = copy.deepcopy(start_specs); cp = decode(cur, dd, require_all=True)
    assert cp is not None, "base plan infeasible"
    cs = S.penalty(cp["metrics"], weights)
    bests = {k: (copy.deepcopy(cur), cp) for k in KINDS}
    t0 = max(100.0, cs*.02); t1 = max(1.0, t0*.001)
    opw = {o: 1.0 for o in S.OPERATORS}; oph = {o: 0 for o in S.OPERATORS}; opr = {o: 0.0 for o in S.OPERATORS}
    for it in range(iterations):
        op = rng.choices(S.OPERATORS, weights=[opw[o] for o in S.OPERATORS], k=1)[0]
        oph[op] += 1
        cand_specs = S.neighbor(cur, rng, op, dd)
        if cand_specs is None: continue
        cand = decode(cand_specs, dd, require_all=True)
        if cand is None: continue
        m = cand["metrics"]
        if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6:
            for k in KINDS:
                if K(m, k) < K(bests[k][1]["metrics"], k):
                    bests[k] = (copy.deepcopy(cand_specs), cand)
        sc = S.penalty(m, weights); improved = sc < cs - 1e-7
        temp = t0*(t1/t0)**(it/max(1, iterations-1))
        if sc <= cs or rng.random() < math.exp(min(0,(cs-sc)/temp)):
            cur, cp, cs = cand_specs, cand, sc
            opr[op] += 9 if improved else 3
        if (it+1) % 100 == 0:
            for o in S.OPERATORS:
                if oph[o]: opw[o] = max(.1, .9*opw[o] + .1*opr[o]/oph[o])
                oph[o] = 0; opr[o] = 0.0
    return {k: {"specs": bests[k][0], "metrics": bests[k][1]["metrics"]} for k in KINDS}
def worker(b, prop, iters, seed): return search_prio(b, prop, iters, seed)
if __name__ == "__main__":
    R = r"D:\git\math_modeling\UAV\results"
    def load(p):
        o = json.load(open(p, encoding="utf-8"))
        return [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in o["sorties"]]
    W = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
    btime = load(W + r"\方案_时间优先(主方案)_完整方案.json")
    bbal = load(W + r"\方案_均衡_完整方案.json")
    beng = load(W + r"\方案_能耗优先_完整方案.json")
    bsort = load(W + r"\方案_架次优先_完整方案.json")
    nd06 = load(R + r"\问题二_参考口径\非支配方案_06_完整方案.json")
    nd11 = load(R + r"\问题二_参考口径\非支配方案_11_完整方案.json")
    combos = [("完成时间优先", [("time", btime), ("bal", bbal), ("eng", beng)]),
              ("能耗优先", [("eng", beng), ("bal", bbal), ("sort", bsort)]),
              ("架次优先", [("sort", bsort), ("nd06", nd06), ("nd11", nd11)])]
    iters = int(sys.argv[1]); nseed = int(sys.argv[2]); n_jobs = int(sys.argv[3]); out = sys.argv[4]
    tasks = []
    for prop, bases in combos:
        for tag, b in bases:
            for s in range(nseed): tasks.append((prop, tag, b, 4000+s))
    print("tasks", len(tasks), "MAXSTOPS=4", flush=True)
    res = []; t0 = time.time()
    gen = Parallel(n_jobs=n_jobs, verbose=5, return_as="generator_unordered")(
        delayed(worker)(b, prop, iters, seed) for prop, tag, b, seed in tasks)
    for i, r in enumerate(gen):
        r["prop"] = tasks[i][0]; r["base"] = tasks[i][1]; r["seed"] = tasks[i][3]
        res.append(r)
        if i % 3 == 0 or i == len(tasks)-1:
            bt = min(x["time"]["metrics"]["makespan_s"] for x in res)
            be = min(x["energy"]["metrics"]["energy_kwh"] for x in res)
            bn = min(x["sorties"]["metrics"]["sorties"] for x in res)
            print("[%3d/%3d] %.1fs best_time=%.1f best_energy=%.3f best_sorties=%d" % (i+1, len(tasks), time.time()-t0, bt, be, bn), flush=True)
            json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("done")

