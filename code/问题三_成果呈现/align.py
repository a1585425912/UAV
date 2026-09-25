import sys, json
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data
from 问题三_通信核心 import Terrain
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed
from 问题三_联合调度 import SITES, evaluate_plan, relay_plan, transport_starts
data=load_data(); terrain=Terrain()
specs,_,info=optimize_seed(data)
starts,resources=transport_starts(specs,REFERENCE_STARTS,data)
pub=json.load(open(r"results\问题三_参考口径\主方案_完整方案.json",encoding="utf-8"))
def sig(spec): return (spec["model"], tuple(st["area"] for st in spec["stops"]), tuple(len(st["ids"]) for st in spec["stops"]))
pubmap={sig(t):t for t in pub["transport"]}
aligned=[pubmap[sig(s)]["start_s"] for s in specs]
print("按结构对齐后的已发布 starts:", [round(x,1) for x in aligned])
# 用已发布 starts + 3 中继
r_pub3=evaluate_plan(specs, aligned, relay_plan(terrain,4695,6260,7315), 0.5, None)
print("已发布starts + 3中继:", r_pub3["metrics"])
# 用已发布 starts + 已发布4中继
r_pub4=evaluate_plan(specs, aligned, pub["relays"], 0.5, None)
print("已发布starts + 已发布4中继:", r_pub4["metrics"])
# 用计算 starts + 3 中继
r_new3=evaluate_plan(specs, starts, relay_plan(terrain,4695,6260,7315), 0.5, None)
print("计算starts + 3中继:", r_new3["metrics"])
