# -*- coding: utf-8 -*-
"""对给定方案做连续通信认证（含中继启停与阶段边界，自适应细分）。"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(HERE))
import q3_cert_cont as CC
from 问题三_通信核心 import Point, load_nodes
from 问题三_联合调度 import trajectory, position
from 问题二_调度核心 import evaluate_sortie
NODES = load_nodes()

def cert(a, b, p0, p1, t0abs, t1abs, relays):
    ok, why = CC.certified_link_v2(p0, p1, Point(NODES["O01"].lon, NODES["O01"].lat, NODES["O01"].alt + CC.PARAMS["gateway_height"]), CC.PARAMS["limit_direct"])
    if ok: return "直连", "", why
    for r in relays:
        if r["link_ready_s"] - 1e-9 <= t0abs and t1abs <= r["service_end_s"] + 1e-9:
            ok, why = CC.certified_link_v2(p0, p1, Point(r["lon"], r["lat"], r["hover_alt_m"]), CC.PARAMS["limit_access"])
            if ok: return "中继", r["id"], why
    return None, "", ""

def certify_task(task, relays, resolution=2.0):
    ev = evaluate_sortie({"model": task["model"], "stops": task["stops"]}, D := None) if False else None
    return None

def run(transport, relays, resolution=2.0):
    total = 0.0; detail = []; certified = 0.0
    for t in transport:
        from 问题二_调度核心 import load_data, evaluate_sortie
        D = load_data()
        ev = evaluate_sortie({"model": t["model"], "stops": t["stops"]}, D)
        ph = trajectory(ev, D, NODES)
        uncert = []
        for q in ph:
            edges = {q["t0"], q["t1"]}
            for r in relays:
                for x in (r["link_ready_s"], r["service_end_s"]):
                    rel = x - t["start_s"]
                    if q["t0"] < rel < q["t1"]: edges.add(rel)
            edges = sorted(edges)
            for a, b in zip(edges, edges[1:]):
                stack = [(a, b)]
                while stack:
                    x, y = stack.pop()
                    p0, p1 = position(q, x), position(q, y)
                    st, rid, why = cert(x, y, p0, p1, t["start_s"]+x, t["start_s"]+y, relays)
                    if st is not None:
                        certified += (y - x); continue
                    if y - x <= resolution:
                        uncert.append((t["start_s"]+x, t["start_s"]+y, q["kind"])); continue
                    m = (x + y) / 2
                    stack.append((m, y)); stack.append((x, m))
        g = sum(b-a for a, b, k in uncert); total += g
        if g > 1e-9: detail.append((t["id"], round(g, 3), [(round(a,3), round(b,3), k) for a,b,k in uncert]))
    return total, certified, detail

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="问题三连续通信证书复核")
    parser.add_argument("--plan", default=str(HERE / "plan_windows_opt.json"))
    parser.add_argument("--resolution", type=float, default=0.5)
    args = parser.parse_args()
    source = Path(args.plan).resolve()
    plan = json.loads(source.read_text(encoding="utf-8"))
    tot, cert_, det = run(plan["transport"], plan["relays"], args.resolution)
    print("方案:", source)
    print("连续认证：已认证 %.3f s，未认证 %.3f s" % (cert_, tot))
    for x in det: print("   ", x)
    raise SystemExit(0 if tot <= 1e-8 else 2)

