"""第三问成果呈现：各服务区调度方案 + 逐架次 + 中继覆盖关系。"""
import csv, json, os, sys
from collections import defaultdict, OrderedDict
ROOT = r"D:\git\math_modeling\UAV"
SRC = os.path.join(ROOT, "results", "问题三_参考口径")
OUT = os.path.join(ROOT, "results", "问题三_成果呈现"); os.makedirs(OUT, exist_ok=True)
def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
transport = rd(os.path.join(SRC, "主方案_运输架次.csv"))
relays = rd(os.path.join(SRC, "主方案_中继架次.csv"))
delivery = rd(os.path.join(SRC, "主方案_逐箱交付.csv"))
comm = rd(os.path.join(SRC, "主方案_通信保障.csv"))
plan = json.load(open(os.path.join(SRC, "主方案_完整方案.json"), encoding="utf-8"))
R = {r["中继架次编号"]: r for r in relays}
# 每条运输架次的通信模式
cmode = defaultdict(lambda: defaultdict(float)); relay_of = defaultdict(set)
for c in comm:
    t = c["运输架次编号"]; mode = c["保障方式"]; dur = float(c["结束时刻_s"]) - float(c["开始时刻_s"])
    cmode[t][mode] += dur
    if mode == "中继" and c["中继架次编号"]: relay_of[t].add(c["中继架次编号"])
# 服务区 -> 架次/箱
area_rows = {}
for area in sorted({d["服务区编号"] for d in delivery}):
    boxes = [d for d in delivery if d["服务区编号"] == area]
    tids = sorted({d["架次编号"] for d in boxes})
    models = sorted({next(x["机型编号"] for x in transport if x["架次编号"] == t) for t in tids})
    times = sorted(float(d["交付完成时刻_s"]) for d in boxes)
    modes = defaultdict(float); rl = set()
    for t in tids:
        for k, v in cmode[t].items(): modes[k] += v
        rl |= relay_of[t]
    area_rows[area] = {
        "服务区": area, "货箱数": len(boxes), "运输架次": "、".join(tids), "机型": "/".join(models),
        "首箱交付_s": round(times[0], 3), "末箱交付_s": round(times[-1], 3),
        "直连时长_s": round(modes.get("直连", 0.0), 3), "中继时长_s": round(modes.get("中继", 0.0), 3),
        "保障方式": "中继" if modes.get("中继", 0) > 0 else "直连",
        "中继架次": "、".join(sorted(rl)),
        "中继悬停点": "、".join(sorted({R[r]["悬停经度"] + "," + R[r]["悬停纬度"] for r in rl})) if rl else "",
        "硬时限最紧余量_s": round(min(float(d["硬截止_s"]) - float(d["交付完成时刻_s"]) for d in boxes if d["硬截止_s"]), 3) if any(d["硬截止_s"] for d in boxes) else "",
    }
with open(os.path.join(OUT, "各服务区调度方案.csv"), "w", encoding="utf-8-sig", newline="") as f:
    rows = list(area_rows.values()); w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
# 逐架次
srows = []
for t in transport:
    tid = t["架次编号"]
    boxes = [d for d in delivery if d["架次编号"] == tid]
    times = [float(d["交付完成时刻_s"]) for d in boxes]
    srows.append({"架次编号": tid, "机型": t["机型编号"], "无人机": t["无人机编号"], "电池": t["电池编号"],
                  "开始_s": t["开始时刻_s"], "访问顺序": t["访问服务区顺序"], "末箱交付_s": round(max(times), 3),
                  "返回_s": t["返回O01时刻_s"], "能耗_kWh": t["架次能耗_kWh"], "SOC": t["返航SOC"],
                  "直连时长_s": round(cmode[tid].get("直连", 0.0), 3), "中继时长_s": round(cmode[tid].get("中继", 0.0), 3),
                  "中继架次": "、".join(sorted(relay_of[tid])) or "—"})
with open(os.path.join(OUT, "调度方案_逐运输架次.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(srows[0])); w.writeheader(); w.writerows(srows)
# 中继覆盖
rrows = []
for r in relays:
    sid = r["中继架次编号"]
    serves = sorted([t for t in relay_of if sid in relay_of[t]])
    areas = sorted({d["服务区编号"] for d in delivery if d["架次编号"] in serves})
    rrows.append({"中继架次": sid, "中继无人机": r["中继无人机编号"], "能源组件": r["能源组件编号"],
                  "点位": next((x["site"] for x in plan["relays"] if x["id"] == sid), ""),
                  "悬停经度": r["悬停经度"], "悬停纬度": r["悬停纬度"], "悬停海拔_m": r["悬停海拔_m"],
                  "建链完成_s": r["建链完成时刻_s"], "服务结束_s": r["服务结束时刻_s"], "返航_s": r["返回O01时刻_s"],
                  "能耗_kWh": r["架次能耗_kWh"], "SOC": r["返航SOC"],
                  "保障运输架次": "、".join(serves), "覆盖服务区": "、".join(areas), "覆盖服务区数": len(areas)})
with open(os.path.join(OUT, "中继覆盖关系.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rrows[0])); w.writeheader(); w.writerows(rrows)
print("各服务区调度方案：%d 行" % len(area_rows))
for a, r in area_rows.items():
    print("  %s  箱%2d  架次%-12s 机型%s  交付[%8.1f,%8.1f]  %s%s" % (
        a, r["货箱数"], r["运输架次"], r["机型"], r["首箱交付_s"], r["末箱交付_s"],
        r["保障方式"], (" " + r["中继架次"]) if r["中继架次"] else ""))
print("\n中继覆盖：")
for r in rrows:
    print("  %s %s  %s→%s  覆盖%d区: %s" % (r["中继架次"], r["点位"], r["建链完成_s"], r["服务结束_s"], r["覆盖服务区数"], r["覆盖服务区"]))
print("\n总指标:", plan["metrics"])
