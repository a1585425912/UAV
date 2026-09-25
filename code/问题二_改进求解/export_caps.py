"""复制完成时间上限实验的最优方案到结果目录（独立目录，不覆盖主方案）。"""
import json, os, sys
from collections import Counter
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data, decode
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = r"D:\git\math_modeling\UAV\results\问题二_改进方案"
D = load_data()
rows = []
for f in sorted(os.listdir(os.path.join(HERE, "runs"))):
    if not f.startswith("cap_best_"): continue
    o = json.load(open(os.path.join(HERE, "runs", f), encoding="utf-8"))
    p = decode(o["specs"], D, require_all=True); m = p["metrics"]
    cap = int(o["cap"]); cc = Counter(s["model"] for s in o["specs"])
    rows.append({"完成时间上限_s": cap, "完成时间_s": round(m["makespan_s"], 3), "总能耗_kWh": round(m["energy_kwh"], 4),
                 "架次数": m["sorties"], "A_B_C": "%d/%d/%d" % (cc["A"], cc["B"], cc["C"]), "说明": "该上限下能耗最小的方案"})
with open(os.path.join(OUT, "完成时间上限实验.csv"), "w", encoding="utf-8-sig", newline="") as f:
    import csv; w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for r in rows: print(r)

