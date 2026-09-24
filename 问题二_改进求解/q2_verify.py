"""问题二改进方案的独立验证：不复用求解器输出，直接从原始参数与几何表复算。

用法：python 问题二_改进求解/q2_verify.py
输出：每个方案一条 PASS/FAIL 记录（全精度 JSON）。CSV 舍入一致性由本脚本之外的独立检查完成。
"""
from __future__ import annotations
import csv, json, math, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from 问题二_调度核心 import load_data  # 仅用于读取机型参数与货箱清单

D = load_data()
OUT = ROOT / "results" / "问题二_改进方案"
G = 9.81
EPS = 1e-9


def read_geometry():
    path = ROOT / "results" / "问题二_参考口径" / "有向航段几何参数.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {(r["起点"], r["终点"]): r for r in rows}


GEOM = read_geometry()


def independent_energy_and_time(sortie):
    """按题面附录 2 公式独立复算架次能耗与飞行时间。"""
    g = sortie["model"]
    dr = D["drones"][g]
    boxes = D["boxes"]
    remaining = sum(boxes[b]["mass"] for st in sortie["stops"] for b in st["ids"])
    loc = "O01"
    energy = 0.0
    flight = 0.0
    legs = []
    for st in sortie["stops"]:
        leg = GEOM[(loc, st["area"])]
        d = float(leg["水平距离（m）"])
        climb = float(leg["起点爬升（m）"])
        descent = float(leg["终点下降（m）"])
        q = remaining
        leq = dr["range0"] - (dr["range0"] - dr["range_full"]) * (q / dr["payload"]) ** 1.5
        e = dr["battery_kwh"] * d / leq + (dr["mass0"] + q) * G * climb / (3.6e6 * dr["eta"])
        t = climb / dr["climb_speed"] + d / dr["speed"] + descent / dr["descent_speed"]
        energy += e; flight += t
        legs.append({"from": loc, "to": st["area"], "payload": q, "energy": e, "time": t})
        remaining -= sum(boxes[b]["mass"] for b in st["ids"])
        loc = st["area"]
    leg = GEOM[(loc, "O01")]
    d = float(leg["水平距离（m）"]); climb = float(leg["起点爬升（m）"]); descent = float(leg["终点下降（m）"])
    leq = dr["range0"]
    e = dr["battery_kwh"] * d / leq + dr["mass0"] * G * climb / (3.6e6 * dr["eta"])
    t = climb / dr["climb_speed"] + d / dr["speed"] + descent / dr["descent_speed"]
    energy += e; flight += t
    legs.append({"from": loc, "to": "O01", "payload": 0.0, "energy": e, "time": t})
    payload = sum(boxes[b]["mass"] for st in sortie["stops"] for b in st["ids"])
    volume = sum(boxes[b]["volume"] for st in sortie["stops"] for b in st["ids"])
    return {"energy": energy, "flight": flight, "payload": payload, "volume": volume,
            "soc": 1 - energy / dr["battery_kwh"], "legs": legs, "reserve": dr["reserve"]}


def verify(plan_path):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    sorties = plan["sorties"]
    deliveries = plan["deliveries"]
    errs = []
    # 1) 覆盖
    allbox = [b for s in sorties for b in s["box_ids"]]
    if len(allbox) != 80 or len(set(allbox)) != 80: errs.append("箱覆盖不唯一")
    if set(allbox) != set(D["boxes"]): errs.append("箱集合不一致")
    # 2) 逐架次物理量
    for s in sorties:
        chk = independent_energy_and_time(s)
        dr = D["drones"][s["model"]]
        if chk["payload"] > dr["payload"] + 1e-9: errs.append("%s 超质量" % s["id"])
        if chk["volume"] > dr["volume"] + 1e-9: errs.append("%s 超体积" % s["id"])
        if chk["soc"] < dr["reserve"] - 1e-9: errs.append("%s SOC 低于余量" % s["id"])
        if abs(chk["energy"] - s["energy_kwh"]) > 1e-6: errs.append("%s 能耗不一致" % s["id"])
        # 3) 交付时刻：开始 + 装载 + 逐段飞行 + 交接
        t = s["start_s"] + dr["prep"] + len(s["box_ids"]) * dr["load"]
        for k, st in enumerate(s["stops"]):
            t += chk["legs"][k]["time"]
            t += dr["handoff"] + len(st["ids"]) * dr["extra"]
            for b in st["ids"]:
                if abs(t - deliveries[b]) > 1e-6: errs.append("%s 交付时刻不一致" % b)
        # 返航
        t += chk["legs"][-1]["time"]
        if abs(t - s["return_s"]) > 1e-6: errs.append("%s 返航时刻不一致" % s["id"])
    # 4) 时限
    hard = tardy = 0.0
    for b, t in deliveries.items():
        bx = D["boxes"][b]
        if bx["hard"] is not None: hard += max(0.0, t - bx["hard"])
        tardy += bx["weight"] * max(0.0, t - bx["due"])
    if hard > 1e-6: errs.append("硬时限违反 %.3f" % hard)
    if tardy > 1e-6: errs.append("加权延误 %.3f" % tardy)
    # 5) 资源占用
    uav = defaultdict(list); bat = defaultdict(list)
    for s in sorties:
        uav[s["uav"]].append((s["start_s"], s["return_s"], s["id"]))
        bat[s["battery"]].append((s["start_s"], s["charge_end_s"], s["id"]))
    for name, iv in list(uav.items()) + list(bat.items()):
        iv.sort()
        for a, b in zip(iv, iv[1:]):
            if b[0] < a[1] - 1e-6: errs.append("资源重叠 %s %s/%s" % (name, a[2], b[2]))
    # 6) 资源数量
    if len({s["uav"] for s in sorties}) > 8: errs.append("实体无人机超 8")
    return {"file": os.path.basename(plan_path), "sorties": len(sorties),
            "makespan": plan["metrics"]["makespan_s"], "energy": plan["metrics"]["energy_kwh"],
            "boxes": len(deliveries), "errors": errs}


if __name__ == "__main__":
    files = sorted(OUT.glob("方案_*_完整方案.json"))
    files += [OUT / "方案_时间优先(主方案)_完整方案.json"]
    seen = set(); ok = 0
    for f in files:
        if f.name in seen: continue
        seen.add(f.name)
        r = verify(f)
        status = "PASS" if not r["errors"] else "FAIL"
        ok += status == "PASS"
        print("%-46s %s  n=%2d T=%10.3f E=%8.4f  %s" % (
            r["file"], status, r["sorties"], r["makespan"], r["energy"],
            "" if not r["errors"] else r["errors"][:3]))
    print("PASS %d / %d" % (ok, len(seen)))


