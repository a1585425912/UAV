"""单变量消融：同起点、同种子、同迭代预算，只切换站点上限 3 vs 4。"""
import sys, os, json, time, copy, random, math
sys.path.insert(0, r"D:\git\math_modeling\UAV\code"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 问题二_调度核心 import load_data, decode
import 问题二_求解 as S3
import q2_solver4 as S4
from joblib import Parallel, delayed
HERE = os.path.dirname(os.path.abspath(__file__))
_D = None
def DD():
    global _D
    if _D is None: _D = load_data()
    return _D
def K(m, kind):
    if kind == "time": return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["makespan_s"], m["energy_kwh"], m["sorties"])
    if kind == "energy": return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["energy_kwh"], m["makespan_s"], m["sorties"])
    return (m["hard_excess_s"]>1e-6, m["hard_excess_s"], m["weighted_tardiness"], m["sorties"], m["makespan_s"], m["energy_kwh"])
def search(S, start_specs, prop, iterations, seed):
    dd = DD(); rng = random.Random(seed); weights = S.PROFILES[prop]
    cur = copy.deepcopy(start_specs); cp = decode(cur, dd, require_all=True)
    assert cp is not None
    cs = S.penalty(cp["metrics"], weights)
    bests = {k: (copy.deepcopy(cur), cp) for k in ("time", "energy", "sorties")}
    t0 = max(100.0, cs*.02); t1 = max(1.0, t0*.001)
    opw = {o:1.0 for o in S.OPERATORS}; oph = {o:0 for o in S.OPERATORS}; opr = {o:0.0 for o in S.OPERATORS}
    for it in range(iterations):
        op = rng.choices(S.OPERATORS, weights=[opw[o] for o in S.OPERATORS], k=1)[0]; oph[op]+=1
        cs2 = S.neighbor(cur, rng, op, dd)
        if cs2 is None: continue
        cand = decode(cs2, dd, require_all=True)
        if cand is None: continue
        m = cand["metrics"]
        if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6:
            for k in bests:
                if K(m,k) < K(bests[k][1]["metrics"], k): bests[k] = (copy.deepcopy(cs2), cand)
        sc = S.penalty(m, weights); improved = sc < cs - 1e-7
        temp = t0*(t1/t0)**(it/max(1,iterations-1))
        if sc <= cs or rng.random() < math.exp(min(0,(cs-sc)/temp)):
            cur, cs = cs2, sc; opr[op] += 9 if improved else 3
        if (it+1) % 100 == 0:
            for o in S.OPERATORS:
                if oph[o]: opw[o] = max(.1, .9*opw[o] + .1*opr[o]/oph[o])
                oph[o]=0; opr[o]=0.0
    return {k: {"specs": bests[k][0], "metrics": bests[k][1]["metrics"]} for k in bests}
def worker(tag, start_specs, prop, iterations, seed):
    S = S3 if tag == "S3" else S4
    return {"solver": tag, "prop": prop, "seed": seed, "best": search(S, start_specs, prop, iterations, seed)}
if __name__ == "__main__":
    W = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
    def load(p):
        o = json.load(open(p, encoding="utf-8"))
        return [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in o["sorties"]]
    bases = [("time", load(W + r"\方案_时间优先(主方案)_完整方案.json")),
             ("bal", load(W + r"\方案_均衡_完整方案.json")),
             ("eng", load(W + r"\方案_能耗优先_完整方案.json"))]
    iters, nseed, n_jobs, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    tasks = [(solver, b, prop, seed) for solver in ("S3", "S4") for btag, b in bases
             for prop in ("完成时间优先", "能耗优先") for seed in range(8000, 8000+nseed)]
    print("tasks", len(tasks), flush=True)
    res = []; t0 = time.time()
    gen = Parallel(n_jobs=n_jobs, verbose=5, return_as="generator_unordered")(
        delayed(worker)(solver, b, prop, iters, seed) for solver, b, prop, seed in tasks)
    for i, r in enumerate(gen):
        res.append(r)
        if i % 4 == 0 or i == len(tasks)-1:
            line = []
            for tag in ("S3", "S4"):
                g = [x for x in res if x["solver"] == tag]
                if g:
                    line.append("%s time=%.1f energy=%.3f n=%d" % (tag,
                        min(x["best"]["time"]["metrics"]["makespan_s"] for x in g),
                        min(x["best"]["energy"]["metrics"]["energy_kwh"] for x in g),
                        min(x["best"]["sorties"]["metrics"]["sorties"] for x in g)))
            print("[%3d/%3d] %.1fs  %s" % (i+1, len(tasks), time.time()-t0, " | ".join(line)), flush=True)
            json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("done")

