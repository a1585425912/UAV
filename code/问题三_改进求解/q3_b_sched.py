# -*- coding: utf-8 -*-
"""在 B 型资源（2 机 + 4 电池）下，求 T22 可开始时间 ≤ 3104.4 s 的可行性排程。
T22 若能在 3104.4 s 前起飞，其 508–1590.6 s 的通信需求即可落入 RS01(西) 的 723.95–4695 s 窗口，
从而有望取消 RS04。"""
import sys, os, json, time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, evaluate_sortie, charge_time
D = load_data()
PUB = r"D:\git\math_modeling\UAV\results\问题三_参考口径\主方案_完整方案.json"

def norm(s): return {"model": s["model"], "stops": s["stops"]}

def sched(specs, model, t22_deadline=None, tl=120.0, constraints=None):
    n = len(specs); uavs = D["uavs"][model]; bats = D["batteries"][model]["ids"]
    m, k = len(uavs), len(bats)
    dur, chg, LS = [], [], []
    for sp in specs:
        ev = evaluate_sortie(norm(sp), D)
        dur.append(ev["duration_s"]); chg.append(charge_time(ev["return_soc"], D["batteries"][model]["full_charge_s"]))
        ls = min(min(D["boxes"][b]["due"] - off,
                     (D["boxes"][b]["hard"] - off) if D["boxes"][b]["hard"] is not None else 1e18)
                 for b, off in ev["delivery_offsets_s"].items())
        LS.append(ls)
    dur = np.array(dur); chg = np.array(chg); LS = np.array(LS); H = float((dur+chg).sum()) + 1.0
    nAU, nAB, nY, nZ = n*m, n*k, m*n*(n-1), k*n*(n-1)
    off_au, off_ab = 0, nAU; off_y, off_z = off_ab+nAB, off_ab+nAB+nY
    off_s, off_T = off_z+nZ, off_z+nZ+n; N = off_s+n+1
    AU = lambda i,u: off_au+i*m+u; AB = lambda i,b: off_ab+i*k+b
    Y = lambda u,i,j: off_y+(u*n+i)*(n-1)+(j if j<i else j-1)
    Z = lambda b,i,j: off_z+(b*n+i)*(n-1)+(j if j<i else j-1)
    S = lambda i: off_s+i
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
    if t22_deadline is not None:
        add({S(t22_deadline[0]): 1}, -np.inf, t22_deadline[1])
    for ci, cub in (constraints or []):
        add({S(ci): 1}, -np.inf, cub)
    A = coo_matrix((vals, (rows, cols)), shape=(r, N)).tocsr()
    c = np.zeros(N); c[off_T] = 1.0
    integ = np.zeros(N); integ[:off_s] = 1
    ub_arr = np.full(N, H); ub_arr[off_s:off_s+n] = np.minimum(H, LS)
    bnd = Bounds(np.zeros(N), ub_arr); bnd.ub[:off_s] = 1.0
    res = milp(c=c, constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
               integrality=integ, bounds=bnd, options={"time_limit": tl, "mip_rel_gap": 0.0, "disp": False})
    out = {"status": int(res.status), "message": str(res.message)}
    if res.x is not None:
        out["makespan"] = float(res.x[off_T])
        out["starts"] = [float(res.x[S(i)]) for i in range(n)]
        out["assign"] = [{"i": i, "uav": uavs[max(range(m), key=lambda uu: res.x[AU(i,uu)])],
                          "battery": bats[max(range(k), key=lambda bb: res.x[AB(i,bb)])],
                          "start": float(res.x[S(i)])} for i in range(n)]
    return out

if __name__ == "__main__":
    pub = json.load(open(PUB, encoding="utf-8"))
    b_specs = [t for t in pub["transport"] if t["model"] == "B"]
    i22 = next(i for i, t in enumerate(b_specs) if t["id"] == "T22")
    print("B 型任务:", [(t["id"], "-".join(s["area"] for s in t["stops"])) for t in b_specs])
    for deadline in [3104.4, 3200.0, 3782.1, None]:
        r = sched(b_specs, "B", (i22, deadline) if deadline else None, tl=60)
        if r.get("starts"):
            order = sorted(zip(b_specs, r["starts"], r["assign"]), key=lambda x: x[1])
            print("T22≤%s: status=%s T=%.1f" % (deadline, r["status"], r["makespan"]))
            for t, st, a in order:
                print("    %s %-10s start=%9.3f uav=%s bat=%s" % (t["id"], "-".join(s["area"] for s in t["stops"]), st, a["uav"], a["battery"]))
        else:
            print("T22≤%s: 无解 status=%s %s" % (deadline, r["status"], r["message"]))



