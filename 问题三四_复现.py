"""从仓库内原始数据复现问题三、四结果、审计、图和输入指纹。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "数据" / "无人机应急物资运输基础数据"
INPUTS = {
    "问题三": [
        DATA / "运输无人机数据.xlsx",
        DATA / "物资需求与配送时限.xlsx",
        DATA / "中继无人机数据.xlsx",
        DATA / "通信链路参数.xlsx",
        DATA / "调度中心与服务区.xlsx",
        ROOT / "数据" / "镇龙乡及周边30米DEM.tif",
        ROOT / "results" / "航路节点坐标与作业高度.csv",
        ROOT / "results" / "有向航段几何参数.csv",
        ROOT / "results" / "问题二_参考口径" / "结果提交_主方案.xlsx",
    ],
    "问题四": [
        ROOT / "results" / "问题三_参考口径" / "主方案_完整方案.json",
        ROOT / "results" / "问题三_参考口径" / "主方案_通信保障.csv",
        ROOT / "results" / "问题三_参考口径" / "结果提交_主方案.xlsx",
    ],
}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def manifest(question: str, command: str) -> None:
    packages = {}
    for name in ("numpy", "scipy", "pandas", "openpyxl", "Pillow", "matplotlib"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    inputs = INPUTS[question]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"复现输入缺失: {missing}")
    result = {
        "生成时间_UTC": datetime.now(timezone.utc).isoformat(),
        "运行命令": command,
        "随机种子": 0,
        "Python": platform.python_version(),
        "依赖版本": packages,
        "输入SHA256": {str(path.relative_to(ROOT)): digest(path) for path in inputs},
        "关键口径": {
            "问题三": "30m DEM；保守连续链路证书；未认证区间计缺口；交通与中继均计能耗/完成时刻",
            "问题四": "固定问题三主方案；跨站架次不可拆；各组独立资源；最小缺口→最小总配置→最小CV",
        }[question],
    }
    target = ROOT / "results" / f"{question}_参考口径" / "复现清单.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"复现清单：{target}", flush=True)


def run(script: str) -> None:
    print(f"执行：{script}", flush=True)
    subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-site-search", action="store_true", help="沿用已保存的候选悬停点覆盖表")
    args = parser.parse_args()
    if not args.skip_site_search:
        run("问题三_候选中继点.py")
    run("问题三_求解.py")
    run("问题四_分区求解.py")
    run("问题三四_独立审计.py")
    run("问题三四_参考口径绘图.py")
    command = "python 问题三四_复现.py" + (" --skip-site-search" if args.skip_site_search else "")
    manifest("问题三", command)
    manifest("问题四", command)


if __name__ == "__main__":
    main()
