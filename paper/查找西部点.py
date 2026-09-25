from __future__ import annotations
import sys, json, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import 问题三_候选中继点 as c
import 问题三_联合调度 as j
from 问题三_全程通信重认证 import PointRasterTerrain
from 问题三_通信核心 import Point, certified_link, load_parameters, load_nodes
from 问题二_调度核心 import load_data,evaluate_sortie
c.Terrain=PointRasterTerrain
needs, sites=c.candidates(step=6)
plan=json.loads((root/'.paper_work'/'试验计划.json').read_text(encoding='utf-8'))
t=plan['transport'][14]
d,n=load_data(),load_nodes()
ph=j.trajectory(evaluate_sortie({'model':t['model'],'stops':t['stops']},d),d,n)
a,b=t['gaps'][0]
mid=(a+b)/2-t['start_s']
p=j.position(next(x for x in ph if x['t0']<=mid<=x['t1']),mid)
ter,par=PointRasterTerrain(),load_parameters()
rank=[]
for s in sites:
    if not {'S003','S007','S015'} <= set(s['covered']): continue
    q=Point(s['lon'],s['lat'],s['alt'])
    if not certified_link(ter,par,p,p,q,par['limit_access'])[0]: continue
    rank.append(s)
rank.sort(key=lambda s:(-len(s['covered']),abs(s['lon']-109.2017)+abs(s['lat']-23.0511)))
print('candidates',len(sites),'ranked',len(rank),'point',p)
east=plan['relays'][1]
scores=[]
started=time.time()
for s in rank[:120]:
    west={'id':'RS01','lon':s['lon'],'lat':s['lat'],'hover_alt_m':s['alt'],
          'link_ready_s':0.0,'service_end_s':4695.0}
    cov=j.certified_intervals(ph,t['start_s'],[west,east],ter,par,n,0.5)
    gap=sum(b-a for a,b,status,_,_ in cov if status=='未证实')
    scores.append((gap,s))
scores.sort(key=lambda x:x[0])
print('scored',len(scores),'elapsed',time.time()-started)
print(json.dumps(scores[:15],ensure_ascii=False,indent=2))
(root/'.paper_work'/'西部候选评分.json').write_text(json.dumps(scores[:20],ensure_ascii=False,indent=2),encoding='utf-8')
