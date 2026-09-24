"""t5 修正问题二收敛记录口径：明确「每 100 次迭代一个记录点、候选缺失即缺号」的实际抽样规则。

依据（复现命令：python results/建模修复/复核收敛记录抽样规则.py）：
- 问题二_求解.py:191-202 在 (iteration+1)%100==0 或最后一次迭代时才 append；
- 同函数 172-173/175-176 行在 neighbor 未生成候选或 decode 返回 None 时 continue，跳过 append；
- 单组复现（完成时间优先, seed=0, 2000 次）：20 个 100 倍数采样点仅记录 11 个，缺号与「该次迭代无可记录候选」逐一对应；
- 已发布 搜索收敛记录.csv 1019 行，与 搜索元数据.json 的 physically_valid/iterations 预测（80 采样点×可行率）≈1025 行一致。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "results" / "问题二_参考口径" / "图表契约.md"
OLD = "| `process_q2_convergence` | 过程 | 完成时间优先搜索的历史最好加权代价随迭代下降 | 5 个种子，100 次记录一次，各自轨迹 | 多折线 |"
NEW = ("| `process_q2_convergence` | 过程 | 完成时间优先搜索的历史最好加权代价随迭代下降 | 4 组权重 × 5 种子，每 100 次迭代一个记录点、"
       "各组各自轨迹；该次迭代未产生可行候选（问题二_求解.py:172-176 的 continue）时该记录点缺号，"
       "故每组实际 42–61 行、全表 1019 行（20 组 × 8000 次迭代），已与 physically_valid 可行率核对一致 | 多折线 |")


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    assert text.count(OLD) == 1, text.count(OLD)
    line = next(i for i, value in enumerate(text.splitlines(), 1) if OLD in value)
    PATH.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"[{PATH.relative_to(ROOT)}:{line}] 原值：{OLD}")
    print(f"[{PATH.relative_to(ROOT)}:{line}] 新值：{NEW}")
    print(f"SHA-256={hashlib.sha256(PATH.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
