"""只读：在 PixelIsPoint 坐标下复验已发布问题三计划的连续链路证书。"""
from __future__ import annotations

import json
from pathlib import Path

import 问题三_联合调度 as joint
from 问题三_通信核心 import Terrain


ROOT = Path(__file__).resolve().parent


class PointRasterTerrain(Terrain):
    def __init__(self):
        super().__init__()
        # 原 tiepoint 是像元中心；Terrain 内的 floor 索引及 (列+0.5) 中心
        # 公式需要像元左上边界，故仅将内部边界原点移动半个像元。
        self.left -= self.step_lon / 2
        self.top += self.step_lat / 2


def main():
    source = ROOT / "results" / "问题三_参考口径" / "主方案_完整方案.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    specs = [{"model": trip["model"], "stops": trip["stops"]}
             for trip in original["transport"]]
    starts = [trip["start_s"] for trip in original["transport"]]
    resources = [{"uav": trip["uav"], "battery": trip["battery"],
                  "charge_end_s": trip["charge_end_s"]}
                 for trip in original["transport"]]
    previous_terrain = joint.Terrain
    try:
        joint.Terrain = PointRasterTerrain
        checked = joint.evaluate_plan(specs, starts, original["relays"], 0.5, resources)
    finally:
        joint.Terrain = previous_terrain
    gaps = {trip["id"]: sum(b - a for a, b in trip["gaps"])
            for trip in checked["transport"] if trip["gaps"]}
    print(f"原缺口: {original['metrics']['communication_gap_s']:.6f} s")
    print(f"PixelIsPoint 保守认证未获认证: {checked['metrics']['communication_gap_s']:.6f} s")
    print("涉及架次:", gaps)
    assert len(gaps) == 0
    assert abs(checked["metrics"]["communication_gap_s"]) < 1e-8


if __name__ == "__main__":
    main()
