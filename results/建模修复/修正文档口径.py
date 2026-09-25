"""t5 文档口径最小修正：把与产物矛盾的字面值改为产物真值。

每次替换断言命中次数，打印 文件:行 原值→新值 与文件 SHA-256。
产物依据：
- 中继架次数 4：results/问题三_参考口径/主方案_中继架次.csv（RS01–RS04，4 条）
- K=3 缺口优先：results/问题四_参考口径/K3_缺口优先.json（缺口总数 4、资源总需求合计 33、作业量CV 1.250481869…、B_B 缺口 0）
- 通信口径：results/问题二三四_复核报告.md（按 RasterPixelIsPoint 重建像元边界后已完成保守连续通信认证）

注意（本次仓库清理）：上述产物依据所在的 results/问题三_参考口径/、results/问题四_参考口径/ 与
results/问题四_参考口径/图表契约.md 已在删除性清理中移除；本脚本保留为历史修复记录，重放前需先运行
python code/问题三四_复现.py 重建这两棵目录（README.md 的对应字面值已在清理时同步更新）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITS = [
    ("README.md", "22 运输架次、3 中继架次，通信缺口 0", "22 运输架次、4 中继架次，通信缺口 0", 1),
    ("README.md", "两组缺口 2 件，三组缺口 5 件", "两组缺口 2 件，三组缺口 4 件", 1),
    ("results/问题四_参考口径/图表契约.md", "固定的 22 个运输架次与 3 个中继架次",
     "固定的 22 个运输架次与 4 个中继架次", 1),
    ("results/问题四_参考口径/图表契约.md", "K=3 至少缺 B 机 2 架、B 电池 1 组、中继机 2 架",
     "K=3 至少缺 B 机 2 架、中继机 2 架（B 型电池无缺口）", 1),
    ("results/问题四_参考口径/图表契约.md", "该资源计划固定于通信待修正的问题三方案",
     "该资源计划固定于已通过保守连续通信认证的问题三主方案", 1),
    ("results/问题四_参考口径/图表契约.md", "现有问题三计划通信待修正",
     "固定于已通过保守连续通信认证的问题三主方案", 1),
]


def main() -> None:
    cache: dict[Path, str] = {}
    for rel, old, new, expected in EDITS:
        path = ROOT / rel
        text = cache.get(path) or path.read_text(encoding="utf-8")
        hits = text.count(old)
        assert hits == expected, (rel, hits, expected, old)
        before = [i for i, line in enumerate(text.splitlines(), 1) if old in line]
        text = text.replace(old, new)
        cache[path] = text
        print(f"[{rel}:{before}] {old}  ->  {new}")
    for path, text in cache.items():
        path.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"已写入 {path.relative_to(ROOT)}  SHA-256={digest}")


if __name__ == "__main__":
    main()
