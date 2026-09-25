import sys, time, json
sys.path.insert(0, r"D:\git\math_modeling\UAV\code")
from 问题二_调度核心 import load_data
from 问题三_通信核心 import Terrain
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed
from 问题三_联合调度 import SITES, evaluate_plan, relay_plan, transport_starts

t0=time.time(); data=load_data(); terrain=Terrain(); print("load %.1fs"%(time.time()-t0), flush=True)
t0=time.time(); specs,_,info=optimize_seed(data); print("seed %.1fs"%(time.time()-t0), flush=True)
t0=time.time(); starts,resources=transport_starts(specs, REFERENCE_STARTS, data); print("starts %.1fs"%(time.time()-t0), flush=True)
t0=time.time(); relay=relay_plan(terrain,4695,6260,7315); print("relay_plan %.1fs"%(time.time()-t0), flush=True)
t0=time.time(); r=evaluate_plan(specs,starts,relay,0.5,resources); print("evaluate %.1fs"%(time.time()-t0), flush=True)
print("metrics",r["metrics"], flush=True)
