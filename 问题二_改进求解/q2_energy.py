# -*- coding: utf-8 -*-
"""q2_energy：在保持架次数与完成时间上限不变的前提下，用单箱迁移下降能耗。

父方案：runs/plan_23T5903.json（23 架次 / 5903.038 s / 67.934 kWh）。
目标：找 23 架次、makespan <= T_cap、能耗更低、其余约束不变的方案。
"""
import sys, os, json, time, copy
sys.path.insert(0, r"D:\git\math_modeling\UAV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q2_transfer as T
D = T.D; HERE = os.path.dirname(os.path.abspath(__file__)); NSHIP = T.NSHIP

def total_energy(specs):
    return sum(T.ev(s)["energy_kwh"] for s in specs)

def per_model(specs):
    out = {g: [] for g in "ABC"}
    for s in specs:
        e = T.ev(s)
        if e is None: return None
        out[s["model"]].append(e["duration_s"])
    return out

def proxy_from(pm):
    v = 0.0
    for g in "ABC":
        if not pm[g]: continue
        v = max(v, T.opt2(pm[g]) if NSHIP[g] == 2 else sum(pm[g]) / NSHIP[g])
    return v

if __name__ == "__main__":
    T_cap = float(sys.argv[1]); rounds = int(sys.argv[2]); start_file = sys.argv[3]; out_name = sys.argv[4]
    t0 = time.time()
    start = json.load(open(start_file, encoding="utf-8"))
    specs = [T.norm(s) for s in start["specs"]]
    full = T.decode(specs, D, require_all=True); m0 = full["metrics"]
    energy = sum(T.ev(s)["energy_kwh"] for s in specs)
    print("start n=%d T=%.3f E=%.4f" % (m0["sorties"], m0["makespan_s"], energy), flush=True)
    for rnd in range(rounds):
        n = len(specs)
        base_pm = per_model(specs)
        if base_pm is None: break
        cands = []
        for i in range(n):
            e_i = T.ev(specs[i])
            if e_i is None: continue
            for bid in [x for st in specs[i]["stops"] for x in st["ids"]]:
                for j in range(n):
                    if j == i: continue
                    e_j = T.ev(specs[j])
                    if e_j is None: continue
                    mv = T.move_box(specs, i, bid, j)
                    if mv is None: continue
                    ni, nj = T.ev(mv[i]), T.ev(mv[j])
                    if ni is None or nj is None: continue
                    pm = {g: list(v) for g, v in base_pm.items()}
                    pm[specs[i]["model"]] = [x for k, x in enumerate(base_pm[specs[i]["model"]])]
                    # 用索引重建更稳妥
                    pm = {g: [] for g in "ABC"}
                    for k, s in enumerate(mv):
                        e = ni if k == i else (nj if k == j else T.ev(s))
                        if e is None: pm = None; break
                        pm[s["model"]].append(e["duration_s"])
                    if pm is None: continue
                    p = proxy_from(pm)
                    if p > T_cap + 1e-6: continue
                    ne = energy - e_i["energy_kwh"] - e_j["energy_kwh"] + ni["energy_kwh"] + nj["energy_kwh"]
                    if ne < energy - 1e-6: cands.append((ne, p, mv))
        cands.sort(key=lambda x: (x[0], x[1]))
        print("[%d] energy=%.4f  candidates=%d  bestE=%s" % (rnd, energy, len(cands), None if not cands else round(cands[0][0],4)), flush=True)
        improved = False
        for ne, p, mv in cands[:25]:
            f2, ordered = T.schedule_ordered(mv)
            if f2 is None: continue
            m = f2["metrics"]
            if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6: continue
            if m["makespan_s"] > T_cap + 1e-6: continue
            if m["sorties"] > m0["sorties"]: continue
            if m["energy_kwh"] < energy - 1e-6:
                specs, energy, m0 = ordered, m["energy_kwh"], m
                improved = True
                print("  ACCEPT T=%.3f E=%.4f" % (m["makespan_s"], energy), flush=True)
                json.dump({"specs": ordered, "metrics": m}, open(os.path.join(HERE, "runs", out_name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                break
        if not improved:
            print("  no energy-improving move; stop", flush=True); break
    print("FINAL n=%d T=%.3f E=%.4f  %.1fs" % (m0["sorties"], m0["makespan_s"], energy, time.time()-t0))
