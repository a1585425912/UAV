"""问题三：输出通过连续通信与资源核验的当前主方案。"""
from __future__ import annotations

import argparse
import json

from 问题二_调度核心 import load_data
from 问题三_通信核心 import Terrain
from 问题三_联合种子 import REFERENCE_STARTS, optimize_seed
from 问题三_联合调度 import SITES, evaluate_plan, relay_plan, transport_starts
from 问题三_结果输出 import OUT, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", type=float, default=.5)
    args = parser.parse_args()
    data, terrain = load_data(), Terrain()
    for name, point in SITES.items():
        assert abs(point.alt - terrain.elevation(point.lon, point.lat) - 300) < 1e-5, name
    specs, _, milp_info = optimize_seed(data)
    starts, resources = transport_starts(specs, REFERENCE_STARTS, data)
    main_plan = evaluate_plan(specs, starts, relay_plan(terrain, 4695, 6260, 7315),
                              args.resolution, resources)
    assert main_plan["metrics"]["communication_gap_s"] == 0
    assert main_plan["metrics"]["hard_excess_s"] == 0
    assert main_plan["metrics"]["weighted_tardiness"] == 0
    save(main_plan, "主方案")
    metadata = {"箱号指派MILP": milp_info, "通信证书最细区间_s": args.resolution,
                "候选悬停点": {k: {"经度": v.lon, "纬度": v.lat, "海拔_m": v.alt} for k, v in SITES.items()},
                "主方案服务窗口": {r["id"]: [r["link_ready_s"], r["service_end_s"]]
                            for r in main_plan["relays"]}}
    (OUT / "求解元数据.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
