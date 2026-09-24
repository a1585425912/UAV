import sys, json
sys.path.insert(0, r"D:\git\math_modeling\UAV")
from 问题二_调度核心 import load_data, decode
from 问题三_通信核心 import Terrain
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed
from 问题三_联合调度 import SITES, evaluate_plan, relay_plan, transport_starts

data = load_data(); terrain = Terrain()
specs, _, info = optimize_seed(data)
starts, resources = transport_starts(specs, REFERENCE_STARTS, data)
pub = json.load(open(r"results\问题三_参考口径\主方案_完整方案.json", encoding="utf-8"))

# 1) 比较 transport 结构
print("specs 架次数:", len(specs), " 已发布 transport:", len(pub["transport"]))
def sig(spec): return (spec["model"], tuple(st["area"] for st in spec["stops"]), tuple(len(st["ids"]) for st in spec["stops"]))
ps = [sig(s) for s in specs]
qs = []
for t in pub["transport"]:
    qs.append((t["model"], tuple(st["area"] for st in t["stops"]), tuple(len(st["ids"]) for st in t["stops"])))
print("结构完全一致:", sorted(map(str,ps)) == sorted(map(str,qs)))
if sorted(map(str,ps)) != sorted(map(str,qs)):
    print("  specs:", sorted(map(str,ps))[:5])
    print("  pub  :", sorted(map(str,qs))[:5])
# 2) 比较 starts
pubs = [t["start_s"] for t in pub["transport"]]
print("starts 一致:", all(abs(a-b)<1e-6 for a,b in zip(starts,pubs)), " 新starts[:5]", [round(x,1) for x in starts[:5]])
# 3) 3 中继 vs 4 中继
r3 = evaluate_plan(specs, starts, relay_plan(terrain, 4695, 6260, 7315), 0.5, resources)
print("3 中继:", r3["metrics"])
for t in sorted(r3["transport"], key=lambda x:-x["return_s"])[:3]: print("   T", t["id"], round(t["return_s"],3))
print("   中继返回:", [round(r["return_s"],3) for r in r3["relays"]])
# 4) 已发布指标
print("已发布:", pub["metrics"])
# 5) 自动验证 3 中继方案是否满足硬约束
def check(res):
    err=[]
    allb=[b for t in res["transport"] for st in t["stops"] for b in st["ids"]]
    if len(allb)!=80 or len(set(allb))!=80: err.append("箱覆盖")
    for t in res["transport"]:
        if t["soc"] < 0.2-1e-9: err.append("transport SOC "+t["id"])
    for r in res["relays"]:
        if r["soc"] < 0.2-1e-9: err.append("relay SOC "+r["id"])
    if res["metrics"]["hard_excess_s"]>1e-6: err.append("hard")
    if res["metrics"]["weighted_tardiness"]>1e-6: err.append("tardy")
    if res["metrics"]["communication_gap_s"]>1e-6: err.append("gap")
    return err
print("3 中继方案校验:", check(r3) or "PASS")
