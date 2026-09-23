# 山区洪涝灾害下无人机运输与通信协同优化：当前成果

本仓库整理 D 题目前完成的分析、第一问求解结果，以及以 O01 调度中心为原点的航路几何数据与可视化。**目前尚未完成整题**；这些成果是建模与核对材料，参赛提交前需要人工复核。

## 图表预览

| 内容 | 图 |
|---|---|
| O01 至各服务区的单程水平直线距离 | [PNG](figures/raw_q1_route_straight_distance.png) · [SVG](figures/raw_q1_route_straight_distance.svg) |
| 去程爬升与下降高度 | [PNG](figures/raw_q1_route_climb_descent.png) · [SVG](figures/raw_q1_route_climb_descent.svg) |
| DEM 二维地形海拔 | [PNG](figures/raw_q1_dem_terrain_map.png) · [SVG](figures/raw_q1_dem_terrain_map.svg) |
| DEM 三维地形、O01 与 S001–S015 | [PNG](figures/raw_q1_dem_terrain_3d.png) · [SVG](figures/raw_q1_dem_terrain_3d.svg) |

三维图以 O01 为水平原点，x 向东、y 向北、z 为 DEM 地面海拔；图中纵向显示比例放大 6 倍，服务区标记杆仅用于定位。

## 数据与代码

- [航路节点坐标与作业高度](results/航路节点坐标与作业高度.csv)：O01 和 15 个服务区。
- [有向航段几何参数](results/有向航段几何参数.csv)：240 条有向直飞航段。
- [单服务区往返几何参数](results/单服务区往返几何参数.csv)：15 条 O01→服务区→O01 航路。
- [几何计算脚本](航路几何数据.py)和[口径说明](results/航路几何口径说明.md)。
- 第一问的求解代码、结果表和其他图表位于仓库根目录、`results/` 和 `figures/`。

当前几何结果以 **DEM 最近像元海拔**计算作业高度：O01 为地面海拔，服务区为地面海拔加 30 m；每次投送后，从该服务区的 30 m 作业高度重新爬升。航段巡航海拔为经过 DEM 像元的最高海拔加 50 m。

已有部分第一问结果使用**原节点表海拔和球面距离**，与新几何表采用的 DEM 海拔及 WGS84 局部坐标口径不同。两组结果不能直接混用；统一口径后需重新运行受影响的第一问计算。

## 复算说明

原始题目附件与 DEM 数据未放入本仓库。需将原始 `数据/` 目录置于仓库根目录，保持原文件名和目录层级，然后在 Python 环境中安装 `numpy`、`scipy`、`openpyxl`、`matplotlib` 等依赖。绘图脚本还调用本地的 `~/.codex/skills/math-modeling/tools/figure/scripts/` 工具；使用这些脚本前需安装对应的数学建模 Skill。之后执行：

```bash
python 航路几何数据.py
python 绘制航路直线距离.py
python 绘制爬升下降与地形.py
python 绘制三维地形.py
```

第一问求解与图表的具体输入哈希、参数和复现命令见 [复现清单](results/复现清单.json)。
