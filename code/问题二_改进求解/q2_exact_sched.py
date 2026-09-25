# -*- coding: utf-8 -*-
"""q2_exact_sched：单机型"无人机+共享电池"精确排程 MILP（含充电占用）。

对给定方案中某一机型的所有架次，精确求解：分配实体无人机与电池、排列顺序、开始时刻，
最小化最后返航时刻。约束：一架次同时占用一架无人机与一组电池；电池返航后按两阶段充电，
充电完成前不可再用。MILP 由 scipy(HiGHS) 求解。
用法：python q2_exact_sched.py <方案.json> <机型A/B/C> [时限s] [输出json]
"""
import sys, os, json, time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, decode, charge_time, evaluate_sortie
HERE = os.path.dirname(os.path.abspath(__file__)); D = load_data()

def norm(s): return {"model": s["model"], "stops": [{"area": st["area"], "ids": list(st["ids"])} for st in s["stops"]]}

def solve(specs, model, tl=120.0):
    n = len(specs)
    uavs = D["uavs"][model]; bats = D["batteries"][model]["ids"]
    m, k = len(uavs), len(bats)
    dur, chg, LS = [], [], []
    for sp in specs:
        ev = evaluate_sortie(norm(sp), D)
        dur.append(ev["duration_s"])
        chg.append(charge_time(ev["return_soc"], D["batteries"][model]["full_charge_s"]))
        ls = min(min(D["boxes"][b]["due"] - off,
                     (D["boxes"][b]["hard"] - off) if D["boxes"][b]["hard"] is not None else 1e18)
                 for b, off in ev["delivery_offsets_s"].items())
        LS.append(ls)
    dur = np.array(dur); chg = np.array(chg); LS = np.array(LS)
    H = float((dur + chg).sum()) + 1.0
    nAU, nAB, nY, nZ = n*m, n*k, m*n*(n-1), k*n*(n-1)
    off_au, off_ab = 0, nAU; off_y, off_z = off_ab+nAB, off_ab+nAB+nY
    off_s, off_T = off_z+nZ, off_z+nZ+n; N = off_s+n+1
    AU = lambda i,u: off_au+i*m+u
    AB = lambda i,b: off_ab+i*k+b
    Y  = lambda u,i,j: off_y+(u*n+i)*(n-1)+(j if j<i else j-1)
    Z  = lambda b,i,j: off_z+(b*n+i)*(n-1)+(j if j<i else j-1)
    S  = lambda i: off_s+i
    rows, cols, vals, lb, ub = [], [], [], [], []; r = 0
    def add(dct, l, h):
        nonlocal r
        for c, v in dct.items(): rows.append(r); cols.append(c); vals.append(float(v))
        lb.append(l); ub.append(h); r += 1
    for i in range(n):
        add({AU(i,u): 1 for u in range(m)}, 1, 1)
        add({AB(i,b): 1 for b in range(k)}, 1, 1)
    for u in range(m):
        for i in range(n):
            for j in range(i+1, n):
                add({Y(u,i,j): -1, Y(u,j,i): -1, AU(i,u): 1, AU(j,u): 1}, -np.inf, 1)
    for b in range(k):
        for i in range(n):
            for j in range(i+1, n):
                add({Z(b,i,j): -1, Z(b,j,i): -1, AB(i,b): 1, AB(j,b): 1}, -np.inf, 1)
    for u in range(m):
        for i in range(n):
            for j in range(n):
                if i == j: continue
                add({AU(i,u): -1, Y(u,i,j): 1}, -np.inf, 0)
                add({AU(j,u): -1, Y(u,i,j): 1}, -np.inf, 0)
                add({S(j): 1, S(i): -1, Y(u,i,j): -H}, dur[i]-H, np.inf)
    for b in range(k):
        for i in range(n):
            for j in range(n):
                if i == j: continue
                add({AB(i,b): -1, Z(b,i,j): 1}, -np.inf, 0)
                add({AB(j,b): -1, Z(b,i,j): 1}, -np.inf, 0)
                add({S(j): 1, S(i): -1, Z(b,i,j): -H}, dur[i]+chg[i]-H, np.inf)
    for i in range(n):
        add({off_T: 1, S(i): -1}, dur[i], np.inf)
        add({S(i): 1}, -np.inf, LS[i])
    A = coo_matrix((vals, (rows, cols)), shape=(r, N)).tocsr()
    c = np.zeros(N); c[off_T] = 1.0
    integ = np.zeros(N); integ[:off_s] = 1
    ub_arr = np.full(N, H); ub_arr[off_s:off_s+n] = np.minimum(H, LS); bnd = Bounds(np.zeros(N), ub_arr); bnd.ub[:off_s] = 1.0
    t0 = time.time()
    res = milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(hi:=ub)),
               integrality=integ, bounds=bnd, options={"time_limit": tl, "mip_rel_gap": 0.0, "disp": False})
    out = {"model": model, "n": n, "status": int(res.status), "message": str(res.message),
           "seconds": round(time.time()-t0, 2)}
    if res.x is not None:
        starts = [float(res.x[S(i)]) for i in range(n)]
        out["makespan"] = float(res.x[off_T]); out["starts"] = [round(x,3) for x in starts]
        assign = []
        for i in range(n):
            u = max(range(m), key=lambda uu: res.x[AU(i,uu)])
            b = max(range(k), key=lambda bb: res.x[AB(i,bb)])
            assign.append({"i": i, "uav": uavs[u], "battery": bats[b], "start": round(starts[i], 6)})
        out["assign"] = assign
    return out

if __name__ == "__main__":
    path, model = sys.argv[1], sys.argv[2]
    tl = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
    o = json.load(open(path, encoding="utf-8"))
    specs = [norm(s) for s in o["specs"] if s["model"] == model]
    r = solve(specs, model, tl)
    print(json.dumps(r, ensure_ascii=False))
    if len(sys.argv) > 4: json.dump(r, open(os.path.join(HERE, "runs", sys.argv[4]), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


