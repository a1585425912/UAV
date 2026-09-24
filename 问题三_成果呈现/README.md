# 第三问成果呈现（可复现）

把已发布的第三问主方案（`results/问题三_参考口径/`）整理成四类可发表成果：
中继 UAV 位置图、运输路线图、各服务区调度方案、权重/敏感性分析。
**只做呈现，不改动已发布数值。**

## 文件

| 脚本 | 产出 |
|---|---|
| `make_q3_tables.py` | `results/问题三_成果呈现/各服务区调度方案.csv`、`调度方案_逐运输架次.csv`、`中继覆盖关系.csv` |
| `make_q3_figures.py` | `figures/问题三_成果呈现/result_q3_relay_sites.*`、`result_q3_transport_routes.*` |
| `make_q3_figs2.py` | `result_q3_area_schedule.*`、`result_q3_weight_analysis.*` |
| `weight_sweep2.py` | `results/问题三_成果呈现/中继窗口权重分析.csv` |
| `make_q3_report.py` | `results/问题三_成果呈现/问题三_成果呈现_结果说明.md` |
| `timing.py` / `compare.py` / `align.py` | 复核用：评估耗时、运输结构对齐、3 中继 vs 4 中继对比 |

## 复现

```powershell
cd D:\git\math_modeling\UAV
python 问题三_成果呈现\make_q3_tables.py
python 问题三_成果呈现\make_q3_figures.py
python 问题三_成果呈现\make_q3_figs2.py
python 问题三_成果呈现\weight_sweep2.py
python 问题三_成果呈现\make_q3_report.py
```

依赖：Python 3.12.8、numpy、scipy、matplotlib、openpyxl；DEM 使用 `数据/镇龙乡及周边30米DEM.mat`。

## 成果说明

- **中继位置图** `result_q3_relay_sites.png`：DEM 山体阴影底图；▲=O01/G01 网关；虚线=网关→中继回传链路；■=西点位（RS01/RS04）、◆=东点位（RS02）、✚=北点位（RS03）；灰线为 22 条运输航线。
- **运输路线图** `result_q3_transport_routes.png`：22 条运输架次按机型着色，叠加 3 个中继点。
- **各服务区调度方案** `各服务区调度方案.csv` + `result_q3_area_schedule.png`：15 个服务区的货箱数、所属运输架次、机型、首/末箱交付时刻、直连/中继保障、中继架次与点位、硬时限最紧余量；甘特图叠加 4 条中继服务窗口。
- **权重/敏感性分析** `中继窗口权重分析.csv` + `result_q3_weight_analysis.png`：目标优先级为「通信缺口=0 → 时限/延误=0 → 联合完成时间 → 总能耗 → 架次数」；缩短中继窗口会产生 3291–8198 s 缺口，说明当前窗口（4695/6260/7315 s）是连续通信的必要配置。

## 关键发现（待独立验证）

当前源码 `问题三_联合调度.transport_starts` 给出更早的运输开工时刻，配合**标准 3 条中继**即可做到
**通信缺口 0 / 完成时间 8115.197 s / 总能耗 75.592 kWh / 25 架次**；
而已发布方案使用较晚开工（T22 于 7012 s 起飞），需要第 4 条中继 RS04，完成时间 9573.284 s。
若 3 中继方案通过完整通信证书与资源审计，第三问有约 **1458 s（15.2%）** 的改进空间。
本目录只记录该发现，未改动 `results/问题三_参考口径/` 的任何数值；后续应像第二问那样走独立复核。
