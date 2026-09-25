from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

import 问题三_候选中继点 as sites
from 问题三_全程通信重认证 import PointRasterTerrain

sites.Terrain = PointRasterTerrain
needs, all_sites = sites.candidates(step=8)
selected, info = sites.choose_sites(needs, all_sites)
out = root / '.paper_work' / '正确像元候选点.json'
out.write_text(json.dumps({'needs': [name for name, _ in needs], 'sites': selected,
                           'info': info, 'count': len(all_sites)}, ensure_ascii=False, indent=2),
               encoding='utf-8')
print(out.read_text(encoding='utf-8'))
