# -*- coding: utf-8 -*-
"""导出问题三窗口优化方案的逐运输/逐箱/中继/通信明细（独立目录，不覆盖已发布结果）。"""
import os, json, csv
from pathlib import Path

OUT = Path(__file__).resolve().parent

def wr(p, rows):
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

if __name__ == "__main__":
    o = json.loads((OUT / "plan_windows_opt.json").read_text(encoding="utf-8"))
    tr, de, rl, cm = [], [], [], []
    for t in o["transport"]:
        tr.append({"架次编号": t["id"], "机型": t["model"], "无人机": t.get("uav"), "电池": t.get("battery"),
                   "开始时刻_s": round(t["start_s"], 6), "返回时刻_s": round(t["return_s"], 6),
                   "访问服务区顺序": "-".join(s["area"] for s in t["stops"]),
                   "能耗_kWh": round(t["energy_kwh"], 6), "返航SOC": round(t["soc"], 6),
                   "电池充满时刻_s": round(t.get("charge_end_s", float("nan")), 6)})
    for b, t in sorted(o["deliveries"].items()):
        de.append({"货箱编号": b, "交付时刻_s": round(t, 6)})
    for r in o["relays"]:
        rl.append({"中继架次": r["id"], "点位": r["site"], "中继机": r["relay_id"], "能源组件": r["energy_id"],
                   "经度": r["lon"], "纬度": r["lat"], "悬停海拔_m": round(r["hover_alt_m"], 6),
                   "出发_s": round(r["depart_s"], 6), "建链完成_s": round(r["link_ready_s"], 6),
                   "服务结束_s": round(r["service_end_s"], 6), "返航_s": round(r["return_s"], 6),
                   "能耗_kWh": round(r["energy_kwh"], 6), "SOC": round(r["soc"], 6),
                   "能源充满_s": round(r["energy_free_s"], 6)})
    for c in o["communications"]:
        cm.append({"运输架次": c["trip"], "阶段": c["phase"], "开始_s": round(c["start_s"], 6),
                   "结束_s": round(c["end_s"], 6), "保障方式": c["status"], "中继架次": c["relay_id"]})
    for name, rows in [("方案_窗口优化_逐运输架次.csv", tr), ("方案_窗口优化_逐箱交付.csv", de),
                       ("方案_窗口优化_中继架次.csv", rl), ("方案_窗口优化_通信保障.csv", cm)]:
        wr(OUT / name, rows); print("wrote", name, len(rows), "rows")
    print("metrics:", o["metrics"])
