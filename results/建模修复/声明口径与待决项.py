"""t5 口径声明（不改动任何方案数值）：在 README 与问题二三四复核报告中显式写明两处已登记待决项。"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

README_BLOCK = """
## 口径说明与待决项

- **作业高度基准**：问题二至问题四的节点作业高度取原题附件《调度中心与服务区.xlsx》的节点表地面海拔 + 30 m；问题一的几何缓存（`results/航路节点坐标与作业高度.csv`、`results/单服务区往返几何参数.csv`）仍按 DEM 像元地面高程 + 30 m 生成，因此 `results/有向航段几何参数.csv` 与 `results/问题二_参考口径/有向航段几何参数.csv` 是作业高度基准不同的同名双版本（240/240 条爬升/下降不同，最大 10.563 m，计划巡航海拔相同）。按同一组批重算，切到节点表基准后问题一已发布指标变化为 ΔE = +0.000996 kWh（+0.0017%）、ΔT = −5.494 s（−0.0168%）；统一口径需重解问题一并重写四问结果工作簿，且时间相对变化超过 0.01% 复核阈值，故登记为待决项，本轮不做静默改数。量化脚本：`results/建模修复/检验作业高度口径.py`。
- **DEM 像元采样语义**：原始 GeoTIFF 的 `GTRasterTypeGeoKey`(1025) = 2（`RasterPixelIsPoint`），而问题三的中继选点与巡航海拔生产路径仍使用 `问题三_通信核心.Terrain` 的 floor 索引加像元中心（Area 口径）；问题三的通信证书已用 `PointRasterTerrain` 语义重新认证（`问题三_全程通信重认证.py`，0.5 s 分辨率、未认证 0 s）。切换采样语义会改变节点高程（1 像元内最大 10.423 m）、中继悬停海拔与覆盖矩阵，实质影响问题三/四数值，登记为待决项。
- 两条待决项的影响范围、建议方案与全部 finding 处置见 [`results/建模修复/04_修复清单.md`](results/建模修复/04_修复清单.md)。

## 复现"""

REPORT_ADD_3 = """3. 问题二若沿用节点表海拔，可保持本次独立复算结论。问题一的往返几何缓存仍按 DEM 像元地面高程 + 30 m 生成，与问题二/三所用节点表基准（地面海拔 + 30 m）在 240/240 条爬升/下降上不同、最大 10.563 m；把问题一切到节点表基准后，问题一已发布指标变化为 ΔE = +0.000996 kWh（+0.0017%）、ΔT = −5.494 s（−0.0168%）。统一口径需重解问题一并重写 Q1–Q4 结果工作簿，且时间相对变化超过 0.01% 复核阈值，故登记为待决项（`../results/建模修复/04_修复清单.md`），本轮不改数；量化脚本 `建模修复/检验作业高度口径.py`。
4. `问题三_参考口径/主方案_通信保障.csv` 的每一行都是相邻同状态子区间的合并结果（`问题三_联合调度.py:138-143`）：对合并后的长区间整体套用「端点位置包络」证书严格强于逐段认证，因此按发布区间端点整体重跑 `certified_link` 出现「不可用」属预期保守性，不能作为发布状态不可复现的证据。端到端复现以 `问题三_全程通信重认证.py`（`PointRasterTerrain`、0.5 s 分辨率、未认证 0 s）为准。
5. DEM 像元采样语义（`RasterPixelIsPoint` 与生产路径 Area 口径）会实质改变问题三/四数值，已登记为待决项；在本轮结论中不适用，故未改动任何已发布数值。"""


def patch(path: Path, old: str, new: str, expect: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == expect, (path, text.count(old))
    path.write_text(text.replace(old, new, 1 if expect == 1 else expect), encoding="utf-8")
    print(f"已更新 {path.relative_to(ROOT)}  SHA-256={hashlib.sha256(path.read_bytes()).hexdigest()}")


def main() -> None:
    patch(ROOT / "README.md", "\n## 复现", README_BLOCK, 1)
    report = ROOT / "results" / "问题二三四_复核报告.md"
    old3 = "3. 问题二若沿用节点表海拔，可保持本次独立复算结论；全题提交前应继续统一问题一与后续问题的节点作业高度口径。"
    patch(report, old3, REPORT_ADD_3, 1)


if __name__ == "__main__":
    main()
