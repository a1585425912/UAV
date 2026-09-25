from __future__ import annotations
import sys,json,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import 问题三_联合调度 as j
from 问题三_全程通信重认证 import PointRasterTerrain
from 问题三_通信核心 import Point,certified_link,load_parameters,load_nodes
from 问题二_调度核心 import load_data,evaluate_sortie
ter,par,nodes=PointRasterTerrain(),load_parameters(),load_nodes()
d=load_data()
plan=json.loads((root/'.paper_work'/'试验计划.json').read_text(encoding='utf-8'))
t=plan['transport'][14]
ph=j.trajectory(evaluate_sortie({'model':t['model'],'stops':t['stops']},d),d,nodes)
east=plan['relays'][1]
hub=nodes['O01']
gateway=Point(hub.lon,hub.lat,hub.alt+par['gateway_height'])
places=[Point(nodes[a].lon,nodes[a].lat,nodes[a].alt+30) for a in ['S002','S003','S007','S015']]
rank=[]
begin=time.time()
for row in range(590,671):
    for col in range(570,641):
        lon=ter.left+(col+.5)*ter.step_lon
        lat=ter.top-(row+.5)*ter.step_lat
        p=Point(lon,lat,float(ter.z[row,col])+300)
        if not certified_link(ter,par,p,p,gateway,par['limit_backhaul'])[0]: continue
        if not all(certified_link(ter,par,x,x,p,par['limit_access'])[0] for x in places): continue
        west={'id':'RS01','lon':lon,'lat':lat,'hover_alt_m':p.alt,
              'link_ready_s':0.0,'service_end_s':4695.0}
        cov=j.certified_intervals(ph,t['start_s'],[west,east],ter,par,nodes,0.5)
        gap=sum(b-a for a,b,status,_,_ in cov if status=='未证实')
        rank.append((gap,row,col,lon,lat,p.alt))
rank.sort()
print('elapsed',time.time()-begin,'feasible_sites',len(rank),'best',rank[:20],flush=True)
(root/'.paper_work'/'密集西部点结果.json').write_text(json.dumps(rank[:100],ensure_ascii=False,indent=2),encoding='utf-8')
