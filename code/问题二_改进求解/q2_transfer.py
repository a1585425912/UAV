# -*- coding: utf-8 -*-
"""q2_transfer：以 C 型瓶颈为导向的单箱迁移局部搜索。

目标：在完成时间不增加（<=T_cap）的前提下，把 23 架次压到 22/更低，或把 23 架次的
完成时间压到 <=5903.038（当前 5969.038，差 66 s）。
代理指标：逐机型任务时长的最优划分上界（B/C 用 2 机精确子集和，A 用总时长/4）。
只有代理改善的候选才做完整时限感知排程验证。
"""
import sys, os, json, time, itertools, random, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feas_sched as FS
from 问题二_调度核心 import load_data, decode, evaluate_sortie
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()
NSHIP = {"A": 4, "B": 2, "C": 2}
def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}
def ev(spec):
    return evaluate_sortie(norm(spec), D)
def dur_of(spec):
    e = ev(spec); return None if e is None else e["duration_s"]
def opt2(ds):
    tot = sum(ds); best = tot
    for mask in range(1 << len(ds)):
        a = sum(ds[i] for i in range(len(ds)) if mask >> i & 1)
        best = min(best, max(a, tot - a))
    return best
def proxy(specs):
    ds = {g: [] for g in "ABC"}
    for s in specs:
        e = ev(s)
        if e is None: return None
        ds[s["model"]].append(e["duration_s"])
    v = 0.0
    for g in "ABC":
        if not ds[g]: continue
        v = max(v, opt2(ds[g]) if NSHIP[g] == 2 else sum(ds[g]) / NSHIP[g])
    return v
def schedule_ordered(specs, bc=6.0, a=10.0):
    by = {}
    for s in specs: by.setdefault(s["model"], []).append(s)
    ordered = []
    for g, chunk in by.items():
        res, how = FS.best_feasible_order(chunk, bc if g != "A" else a)
        if res is None: return None, None
        m, order = res
        ordered += [chunk[i] for i in order]
    full = decode(ordered, D, require_all=True)
    return full, ordered
def schedule(specs, bc=6.0, a=10.0):
    return schedule_ordered(specs, bc, a)[0]
def move_box(specs, i, bid, j):
    """把 specs[i] 的货箱 bid 移到 specs[j]（新架次 j==len 表示新建）。"""
    out = [norm(s) for s in specs]
    src = out[i]; area = D["boxes"][bid]["area"]
    # 从源移除
    for st in src["stops"]:
        if bid in st["ids"]:
            st["ids"].remove(bid)
            if not st["ids"]: src["stops"].remove(st)
            break
    if not src["stops"]: return None
    if j >= len(out):
        out.append({"model": "A", "stops": [{"area": area, "ids": [bid]}]})
    else:
        tgt = out[j]
        hit = next((st for st in tgt["stops"] if st["area"] == area), None)
        if hit is not None: hit["ids"].append(bid)
        else:
            # 插入到使路线最短的位置（简单枚举）
            bestpos, bestd = 0, None
            for pos in range(len(tgt["stops"]) + 1):
                cand = copy.deepcopy(tgt)
                cand["stops"].insert(pos, {"area": area, "ids": [bid]})
                d = dur_of(cand)
                if d is not None and (bestd is None or d < bestd): bestd, bestpos = d, pos
            if bestd is None: return None
            tgt["stops"].insert(bestpos, {"area": area, "ids": [bid]})
    return out

if __name__ == "__main__":
    T_cap = float(sys.argv[1]); rounds = int(sys.argv[2]); seed = int(sys.argv[3])
    start_file = sys.argv[4]; out_name = sys.argv[5]
    rng = random.Random(seed); t0 = time.time()
    start = json.load(open(start_file, encoding="utf-8"))
    best_specs = [norm(s) for s in start["specs"]]
    base = decode(best_specs, D, require_all=True)
    best_m = base["metrics"]; best_proxy = proxy(best_specs)
    print("start n=%d T=%.3f E=%.3f proxy=%.3f" % (best_m["sorties"], best_m["makespan_s"], best_m["energy_kwh"], best_proxy), flush=True)
    for rnd in range(rounds):
        cands = []
        n = len(best_specs)
        for i in range(n):
            if best_specs[i]["model"] != "C": continue  # 只动 C（源）
            for bid in [x for st in best_specs[i]["stops"] for x in st["ids"]]:
                for j in range(n + 1):
                    if j == i: continue
                    mv = move_box(best_specs, i, bid, j)
                    if mv is None: continue
                    p = proxy(mv)
                    if p is None: continue
                    if p < best_proxy - 1e-6: cands.append((p, mv))
        # 也允许 A/B -> C 的迁移（若能把 C 从瓶颈上移走反而可能更差，这里只在 C 减少时保留）
        cands.sort(key=lambda x: x[0])
        print("[%d] proxy=%9.3f  candidates=%d  best_proxy=%s" % (rnd, best_proxy, len(cands), None if not cands else round(cands[0][0],3)), flush=True)
        improved = False
        for p, mv in cands[:20]:
            full, ord_specs = schedule_ordered(mv)
            if full is None: continue
            m = full["metrics"]
            if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: continue
            cur = (best_m["sorties"], best_m["makespan_s"], best_m["energy_kwh"])
            cand = (m["sorties"], m["makespan_s"], m["energy_kwh"])
            if cand <= cur and m["makespan_s"] <= T_cap + 1e-6 and cand != cur:
                best_specs, best_m, best_proxy = mv, m, p
                improved = True
                print("  ACCEPT n=%d T=%.3f E=%.3f proxy=%.3f" % (cand[0], cand[1], cand[2], p), flush=True)
                json.dump({"specs": ord_specs, "metrics": m, "proxy": p}, open(os.path.join(HERE, "runs", out_name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                break
        if not improved:
            print("  no improving move; stop", flush=True); break
    print("FINAL n=%d T=%.3f E=%.3f  %.1fs" % (best_m["sorties"], best_m["makespan_s"], best_m["energy_kwh"], time.time()-t0))

