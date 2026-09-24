import sys, json, time, csv, os
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data
from 问题三_通信核心 import Terrain
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed
from 问题三_联合调度 import SITES, evaluate_plan, relay_plan, transport_starts
data=load_data(); terrain=Terrain()
specs,_,info=optimize_seed(data); starts,resources=transport_starts(specs,REFERENCE_STARTS,data)
pub=json.load(open(r"results\问题三_参考口径\主方案_完整方案.json",encoding="utf-8"))
def sig(s): return (s["model"],tuple(st["area"] for st in s["stops"]),tuple(len(st["ids"]) for st in s["stops"]))
pm={sig(t):t for t in pub["transport"]}
aligned=[pm[sig(s)]["start_s"] for s in specs]
OUT=r"D:\git\math_modeling\UAV\results\问题三_成果呈现"; rows=[]
def run(tag, starts_use, relays):
    t0=time.time()
    try:
        r=evaluate_plan(specs,starts_use,relays,0.5,resources); m=r["metrics"]
        ok = m["communication_gap_s"]<=1e-6 and m["hard_excess_s"]<=1e-6 and m["weighted_tardiness"]<=1e-6
        row={"方案":tag,"通信缺口_s":round(m["communication_gap_s"],3),"完成时间_s":round(m["makespan_s"],3),
             "总能耗_kWh":round(m["energy_kwh"],4),"运输架次":m["transport_sorties"],"中继架次":len(relays),
             "可行":"是" if ok else "否"}
    except Exception as e:
        row={"方案":tag,"通信缺口_s":"-","完成时间_s":"-","总能耗_kWh":"-","运输架次":22,"中继架次":len(relays),"可行":"异常:"+type(e).__name__}
    rows.append(row)
    print("%-30s %s 缺口=%s T=%s E=%s 中继=%s  %.1fs"%(tag,row["可行"],row["通信缺口_s"],row["完成时间_s"],row["总能耗_kWh"],row["中继架次"],time.time()-t0), flush=True)
run("3中继-标准(早开工)", starts, relay_plan(terrain,4695,6260,7315))
run("4中继-已发布", aligned, pub["relays"])
for sw,ee,ne in [(3500,5000,6500),(2500,3500,5500),(4695,6260,6500),(3500,6260,7315),(4695,5000,7315),(3000,4000,6000)]:
    try:
        rp=relay_plan(terrain,sw,ee,ne); run("窗口(%d,%d,%d)"%(sw,ee,ne), starts, rp)
    except Exception as e:
        print("窗口(%d,%d,%d) relay_plan 异常 %s"%(sw,ee,ne,e), flush=True)
with open(os.path.join(OUT,"中继窗口权重分析.csv"),"w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("saved")
