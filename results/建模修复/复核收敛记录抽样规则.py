"""t5 复核问题二收敛记录的抽样规则：1019 行不是「20×80=1600」缺失，而是逐 100 次记录点被 decode 失败跳过。

机制（问题二_求解.py:168-202）：每 100 次迭代进入一次 trace.append，但 append 之前有两处 continue
  - 第 172-173 行：neighbor() 未生成候选；
  - 第 175-176 行：decode() 返回 None（候选不可行）。
因此「记录点缺失」等价于该次迭代未产生可行候选；记录行数应约等于 80 × 可行率。
本脚本对单组（完成时间优先, seed=0, 2000 次迭代）做同规则复现，并核对逐迭代记录判定，
只读运行、不写任何产物。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import 问题二_求解 as S  # noqa: E402
from 问题二_调度核心 import load_data  # noqa: E402
from 问题二_参考路线种子 import optimize_seed  # noqa: E402

ITERATIONS = 2000
PROFILE = "完成时间优先"
SEED = 0


def main() -> None:
    data = load_data()
    start_specs, warm, _ = optimize_seed(data)
    log: list[tuple[str, bool]] = []
    original_neighbor, original_decode = S.neighbor, S.decode

    def neighbor(*args, **kwargs):
        result = original_neighbor(*args, **kwargs)
        log.append(("neighbor", result is not None))
        return result

    def decode(*args, **kwargs):
        result = original_decode(*args, **kwargs)
        log.append(("decode", result is not None))
        return result

    S.neighbor, S.decode = neighbor, decode
    try:
        _, _, _, _, meta, trace = S.search(start_specs, data, PROFILE, ITERATIONS, SEED)
    finally:
        S.neighbor, S.decode = original_neighbor, original_decode

    # search() 第 155 行在进入循环前先对热启动解调用一次 decode，需剔除
    assert log[0] == ("decode", True), log[0]
    log = log[1:]
    # 按调用顺序还原每次迭代是否产生可记录点
    per_iteration, cursor = [], 0
    for iteration in range(ITERATIONS):
        assert log[cursor][0] == "neighbor", (iteration, log[cursor])
        produced = log[cursor][1]
        cursor += 1
        recorded = False
        if produced:
            assert log[cursor][0] == "decode", (iteration, log[cursor])
            recorded = log[cursor][1]
            cursor += 1
        per_iteration.append(recorded)
    expected = [i + 1 for i, ok in enumerate(per_iteration) if ok and (i + 1) % 100 == 0]
    actual = [row["迭代"] for row in trace]
    print(f"单组复现（{PROFILE}, seed={SEED}, {ITERATIONS} 次迭代）")
    print(f"  physically_valid={meta['physically_valid']}  accepted={meta['accepted']}")
    print(f"  逐迭代还原的记录点 {len(expected)} 个，全部为 100 的倍数：{all(x % 100 == 0 for x in expected)}")
    print(f"  实际 trace 行数 {len(actual)}，与还原点完全一致：{expected == actual}")
    print(f"  100 的倍数采样点 {ITERATIONS // 100} 个，因候选缺失被跳过 {ITERATIONS // 100 - len(actual)} 个")
    print(f"  迭代点连续：{actual == list(range(100, ITERATIONS + 1, 100))}；缺号示例：{[x for x in range(100, ITERATIONS + 1, 100) if x not in actual][:8]}")

    published = list(csv.DictReader((ROOT / "results" / "问题二_参考口径" / "搜索收敛记录.csv").open(encoding="utf-8-sig")))
    metadata = json.loads((ROOT / "results" / "问题二_参考口径" / "搜索元数据.json").read_text(encoding="utf-8"))["搜索"]
    predicted = sum(80 * (m["physically_valid"] / m["iterations"]) for m in metadata)
    print("已发布记录核对")
    print(f"  行数 {len(published)}；20 组；每组 {min(int(r) for r in [sum(1 for x in published if (x['方案'], x['种子']) == (m['profile'], str(m['seed']))) for m in metadata])}"
          f"—{max(sum(1 for x in published if (x['方案'], x['种子']) == (m['profile'], str(m['seed']))) for m in metadata)} 行")
    print(f"  由 搜索元数据.json 的 physically_valid/iterations 预测行数（80 采样点 × 可行率）≈ {predicted:.0f}（观测 {len(published)}）")
    print(f"  元数据 iterations 全为 8000：{ {m['iterations'] for m in metadata} }")


if __name__ == "__main__":
    main()
