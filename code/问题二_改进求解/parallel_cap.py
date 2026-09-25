import sys, os, json, time, copy, random, math
sys.path.insert(0, r"D:\git\math_modeling\UAV\code"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 问题二_调度核心 import load_data, decode
import q2_solver4 as S
from joblib import Parallel, delayed
HERE = os.path.dirname(os.path.abspath(__file__))
_D = None
def DD():
    global _D
    if _D is None: _D = load_data()
    return _D
def penalty_cap(m, cap):
    if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: return 1e12 + m["hard_excess_s"] + m["weighted_tardiness"]
    return 1e7*max(0.0, m["makespan_s"]-cap) + 1e3*m["energy_kwh"] + 1.0*m["sorties"]
def search(start_specs, cap, iterations, seed):
    dd = DD(); rng = random.Random(seed)
    cur = copy.deepcopy(start_specs); cp = decode(cur, dd, require_all=True)
    assert cp is not None
    cs = penalty_cap(cp["metrics"], cap)
    best = (copy.deepcopy(cur), cp)
    t0 = max(100.0, 1e3*cp["metrics"]["energy_kwh"]*.02); t1 = max(1.0, t0*.001)
    opw = {o:1.0 for o in S.OPERATORS}; oph = {o:0 for o in S.OPERATORS}; opr = {o:0.0 for o in S.OPERATORS}
    for it in range(iterations):
        op = rng.choices(S.OPERATORS, weights=[opw[o] for o in S.OPERATORS], k=1)[0]; oph[op]+=1
        cand_specs = S.neighbor(cur, rng, op, dd)
        if cand_specs is None: continue
        cand = decode(cand_specs, dd, require_all=True)
        if cand is None: continue
        m = cand["metrics"]; sc = penalty_cap(m, cap); improved = sc < cs - 1e-7
        def key(x): return (x["energy_kwh"], x["sorties"], x["makespan_s"])
        if m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6 and m["makespan_s"] <= cap + 1e-6:
            if key(m) < key(best[1]["metrics"]): best = (copy.deepcopy(cand_specs), cand)
        temp = t0*(t1/t0)**(it/max(1, iterations-1))
        if sc <= cs or rng.random() < math.exp(min(0,(cs-sc)/temp)):
            cur, cp, cs = cand_specs, cand, sc; opr[op] += 9 if improved else 3
        if (it+1) % 100 == 0:
            for o in S.OPERATORS:
                if oph[o]: opw[o] = max(.1, .9*opw[o] + .1*opr[o]/oph[o])
                oph[o]=0; opr[o]=0.0
    return {"cap": cap, "specs": best[0], "metrics": best[1]["metrics"]}
def worker(b, cap, iters, seed): return search(b, cap, iters, seed)
if __name__ == "__main__":
    W = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
    def load(p):
        o = json.load(open(p, encoding="utf-8"))
        return [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in o["sorties"]]
    L = {"time": load(W + r"\方案_时间优先(主方案)_完整方案.json"),
         "bal": load(W + r"\方案_均衡_完整方案.json"),
         "eng": load(W + r"\方案_能耗优先_完整方案.json")}
    CAPS = {6000: ["time", "bal"], 6600: ["bal", "eng"], 7200: ["eng", "bal"]}
    iters, nseed, n_jobs, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    tasks = []
    for cap, keys in CAPS.items():
        for k in keys:
            for s in range(nseed): tasks.append((cap, k, L[k], 7000+s))
    print("tasks", len(tasks), flush=True)
    res = []; t0 = time.time()
    gen = Parallel(n_jobs=n_jobs, verbose=5, return_as="generator_unordered")(delayed(worker)(b, cap, iters, seed) for cap, k, b, seed in tasks)
    for i, r in enumerate(gen):
        r["base"] = tasks[i][1]; r["seed"] = tasks[i][3]; res.append(r)
        if i % 3 == 0 or i == len(tasks)-1:
            msg = []
            for cap in CAPS:
                g = [x for x in res if x["cap"] == cap and x["metrics"]["makespan_s"] <= cap+1e-6]
                msg.append("cap%d:%s" % (cap, ("%.3f/%.3f/n%d" % (min(x["metrics"]["energy_kwh"] for x in g), 0, min(x["metrics"]["sorties"] for x in g))) if g else "-"))
            print("[%3d/%3d] %.1fs %s" % (i+1, len(tasks), time.time()-t0, " ".join(msg)), flush=True)
            json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("done")

