"""从 D题 目录运行：python 问题一_统一航段复现.py。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
for script in ("问题一_统一航段精确组批.py", "问题一_统一航段独立审计.py", "问题一_统一航段绘图.py"):
    subprocess.run([sys.executable, str(root / script)], cwd=root, check=True)
