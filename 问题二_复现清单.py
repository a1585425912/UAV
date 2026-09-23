"""按数学建模技能的清单格式记录问题二输入与环境。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HELPER = Path("C:/Users/mika/.codex/skills/math-modeling/references/roles/编程手/scripts/repro_manifest.py")


def main() -> None:
    spec = importlib.util.spec_from_file_location("math_repro_manifest", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    inputs = [
        ROOT / "数据" / "无人机应急物资运输基础数据" / "运输无人机数据.xlsx",
        ROOT / "数据" / "无人机应急物资运输基础数据" / "物资需求与配送时限.xlsx",
        ROOT / "results" / "航路节点坐标与作业高度.csv",
        ROOT / "results" / "有向航段几何参数.csv",
        ROOT / "results" / "问题一_参考口径" / "结果提交_问题一参考口径.xlsx",
    ]
    manifest = module.build_manifest(
        inputs=inputs,
        seed=0,
        parameters={"iterations_per_profile_seed": 8000, "seeds": [0, 1, 2, 3, 4],
                    "profiles": ["完成时间优先", "均衡", "能耗优先", "架次优先"],
                    "hard_deadlines": "医疗期望时间与首批截止时间取较早者"},
        command="python 问题二_复现.py --iterations 8000 --seeds 0 1 2 3 4",
        packages=["numpy", "scipy", "openpyxl", "matplotlib", "pandas", "pillow"],
    )
    output = ROOT / "results" / "问题二_参考口径" / "复现清单.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写复现清单：{output}")


if __name__ == "__main__":
    main()
