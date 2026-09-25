from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

import 问题三_联合调度 as joint
from 问题三_通信核心 import Point, relay_sortie
from 问题三_全程通信重认证 import PointRasterTerrain

source = json.loads((root / 'results' / '问题三_参考口径' / '主方案_完整方案.json').read_text(encoding='utf-8'))
sites = json.loads((root / '.paper_work' / '正确像元候选点.json').read_text(encoding='utf-8'))['sites']
joint.SITES = {k: Point(sites[i]['lon'], sites[i]['lat'], sites[i]['alt']) for k, i in [('西',1),('东',2),('北',0)]}
joint.SITES['西'] = Point(sites[1]['lon'], sites[1]['lat'], sites[1]['alt'])
joint.Terrain = PointRasterTerrain
specs = [{'model': t['model'], 'stops': t['stops']} for t in source['transport']]
starts = [t['start_s'] for t in source['transport']]
resources = [{k:t[k] for k in ('uav','battery','charge_end_s')} for t in source['transport']]
starts[21] = 7012.0
resources[21]['charge_end_s'] -= source['transport'][21]['start_s'] - starts[21]
terrain = PointRasterTerrain()
relays = joint.relay_plan(terrain, 4695, 6260, 7315)
fourth = relay_sortie(terrain, joint.SITES['西'], relays[1]['relay_free_s'], 9000,
                      'R02', 'R-B4')
fourth['id'], fourth['site'] = 'RS04', '西'
relays.append(fourth)
result = joint.evaluate_plan(specs, starts, relays, 0.5, resources)
print(result['metrics'])
print([(t['id'], round(sum(b-a for a,b in t['gaps']),3)) for t in result['transport'] if t['gaps']])
print([(r['id'],r['soc'],r['link_ready_s'],r['service_end_s']) for r in relays])
(root / '.paper_work' / '试验计划.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
