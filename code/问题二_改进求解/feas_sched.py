import sys, json, time, os, itertools, random
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, decode
D = load_data(); RNG = random.Random(99)

def load_specs(path):
    obj = json.load(open(path, encoding="utf-8"))
    if isinstance(obj, dict) and "sorties" in obj:
        return [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in obj["sorties"]]
    if isinstance(obj, list):
        return [{"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]} for s in obj]
    raise ValueError

def ev(chunk, order):
    r = decode([chunk[i] for i in order], D, require_all=False)
    m = r["metrics"]
    ok = m["hard_excess_s"] <= 1e-6 and m["weighted_tardiness"] <= 1e-6
    return m["makespan_s"], ok, m

def best_feasible_order(chunk, budget):
    k = len(chunk)
    best = None
    if k <= 8:
        for perm in itertools.permutations(range(k)):
            m, ok, _ = ev(chunk, perm)
            if ok and (best is None or m < best[0]): best = (m, perm)
        return best, "brute"
    t0 = time.time()
    order0 = list(range(k)); m0, ok0, _ = ev(chunk, order0)
    best = (m0, order0[:]) if ok0 else None
    while time.time()-t0 < budget:
        order = list(range(k)); RNG.shuffle(order)
        m, ok, _ = ev(chunk, order)
        if ok and (best is None or m < best[0]): best = (m, order[:])
        cur = m if ok else float("inf")
        for _ in range(2500):
            if time.time()-t0 >= budget: break
            cand = order[:]; x = RNG.random()
            if x < .5:
                i,j = RNG.sample(range(k),2); cand[i],cand[j]=cand[j],cand[i]
            elif x < .85:
                i=RNG.randrange(k); j=RNG.randrange(k); v=cand.pop(i); cand.insert(j,v)
            else:
                i,j=sorted(RNG.sample(range(k),2)); cand[i:j+1]=cand[i:j+1][::-1]
            m2, ok2, _ = ev(chunk, cand)
            if ok2 and (best is None or m2 < best[0]): best = (m2, cand[:])
            if ok2 and m2 < cur: order, cur = cand, m2
    return best, "ls"

def run(path):
    specs = load_specs(path)
    base = decode(specs, D, require_all=True)
    by = {}
    for i,s in enumerate(specs): by.setdefault(s["model"], []).append(i)
    final = list(range(len(specs))); det = {}
    t0=time.time()
    for g, idxs in by.items():
        chunk = [specs[i] for i in idxs]
        res, how = best_feasible_order(chunk, 25.0 if g!="A" else 35.0)
        if res is None:
            det[g] = {"n": len(idxs), "feasible": False}
            print("  !! %s no feasible schedule found" % g, flush=True)
            # keep original order for this model
            continue
        m, order = res
        for pos, li in enumerate(order): final[idxs[pos]] = idxs[li]
        det[g] = {"n": len(idxs), "best_makespan": round(m,3), "how": how}
    full = decode([specs[i] for i in final], D, require_all=True)
    return {"file": path, "base_greedy": base["metrics"], "opt": full["metrics"],
            "gain": base["metrics"]["makespan_s"]-full["metrics"]["makespan_s"],
            "detail": det, "order": final, "specs": specs, "seconds": round(time.time()-t0,1)}

if __name__ == "__main__":
    for path in sys.argv[1:]:
        r = run(path)
        print("%-60s base=%9.3f opt=%9.3f n=%2d hard=%.1f tardy=%.1f gain=%.1f %s" % (
            os.path.basename(path), r["base_greedy"]["makespan_s"], r["opt"]["makespan_s"],
            r["opt"]["sorties"], r["opt"]["hard_excess_s"], r["opt"]["weighted_tardiness"],
            r["gain"], r["detail"]), flush=True)
