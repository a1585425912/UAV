# -*- coding: utf-8 -*-
"""问题二候选到问题三的通信感知组合审计。

公开同题实现中一个值得保留的做法，是把 Q2 的多个候选作为 Q3 热启动，
而不是默认 Q2 最快方案必然也是 Q3 最好方案。本脚本用本仓库同一物理与
PixelIsPoint 通信口径，比较：
  A. 当前已认证 Q3 正式方案；
  B. Q2 的 22 架次 / 5792 s 时间方案直接配用当前中继窗口。
B 只作诊断，通信缺口不为零时绝不晋升为正式方案。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(HERE))

from 问题三_全程通信重认证 import PointRasterTerrain  # noqa: E402
from 问题三_联合调度 import evaluate_plan  # noqa: E402
import 问题三_联合调度 as joint  # noqa: E402
import q3_cont_cert  # noqa: E402

FORMAL = HERE / "plan_windows_opt.json"
Q2_FAST = ROOT / "results" / "问题二_改进方案" / "方案_22架次_5792s_完整方案.json"
OUT = ROOT / "results" / "问题三_改进求解" / "候选组合审计.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_q2_with_relays(q2, relays):
    specs = [{"model": t["model"], "stops": t["stops"]} for t in q2["sorties"]]
    starts = [t["start_s"] for t in q2["sorties"]]
    resources = [{"uav": t["uav"], "battery": t["battery"],
                  "charge_end_s": t["charge_end_s"]} for t in q2["sorties"]]
    previous = joint.Terrain
    joint.Terrain = PointRasterTerrain
    try:
        return evaluate_plan(specs, starts, relays, 0.5, resources)
    finally:
        joint.Terrain = previous


def main():
    formal = json.loads(FORMAL.read_text(encoding="utf-8"))
    q2 = json.loads(Q2_FAST.read_text(encoding="utf-8"))
    warm = evaluate_q2_with_relays(q2, formal["relays"])
    continuous_gap, certified, detail = q3_cont_cert.run(
        formal["transport"], formal["relays"], resolution=0.1)
    warm_gaps = [{"架次": row["id"], "未认证_s": sum(b-a for a, b in row["gaps"])}
                 for row in warm["transport"] if row["gaps"]]
    output = {
        "正式Q3": {
            "文件": str(FORMAL.relative_to(ROOT)), "SHA256": sha(FORMAL),
            "指标": formal["metrics"], "严格连续未认证_s": continuous_gap,
            "严格连续已认证_s": certified,
        },
        "Q2最快方案直接继承测试": {
            "文件": str(Q2_FAST.relative_to(ROOT)), "SHA256": sha(Q2_FAST),
            "Q2指标": q2["metrics"], "套用现有中继后的Q3指标": warm["metrics"],
            "有缺口架次": warm_gaps,
            "判定": "拒绝晋升" if warm["metrics"]["communication_gap_s"] > 1e-8 else "进入严格连续复核",
        },
        "选择规则": "通信缺口、硬时限违反、加权延误均为0且严格连续认证通过，方可比较完成时间、能耗与架次",
        "说明": "Q2最快不等于Q3最好；本审计用于防止跨问题静默替换上游方案。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("正式Q3连续未认证 %.6f s" % continuous_gap)
    print("Q2最快方案直接套用中继：通信缺口 %.6f s，涉及 %d 架次，%s" % (
        warm["metrics"]["communication_gap_s"], len(warm_gaps),
        output["Q2最快方案直接继承测试"]["判定"]))
    print("saved", OUT)
    raise SystemExit(0 if continuous_gap <= 1e-8 else 2)


if __name__ == "__main__":
    main()
