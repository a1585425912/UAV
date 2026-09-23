"""从原始输入重建问题二的几何、方案、审计和图表。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / script), *args]
    print("运行：", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=8000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    args = parser.parse_args()
    run("问题二_参考口径几何.py")
    run("问题二_原始输入剖析.py")
    run("问题二_求解.py", "--iterations", str(args.iterations),
        "--seeds", *(str(seed) for seed in args.seeds))
    run("问题二_独立审计.py")
    run("问题二_参考口径绘图.py")
    run("问题二_复现清单.py")
    print("问题二复现与独立审计完成。")


if __name__ == "__main__":
    main()
