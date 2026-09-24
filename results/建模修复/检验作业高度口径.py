"""t5 只读量化：把问题一往返几何的作业高度基准从 DEM 地面高程切到附件节点表地面高程。

不写入任何已发布产物；仅打印对照数值，供 04_修复清单.md 引用。
题面出处：题目原文.txt:45（服务区作业高度取其地面海拔以上30米）+ 附件《调度中心与服务区.xlsx》节点表地面海拔字段。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results"
OUT1 = RES / "问题一_非枚举整数规划"
DATA = ROOT / "数据" / "无人机应急物资运输基础数据"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    nodes = {r["编号"]: r for r in rows(RES / "航路节点坐标与作业高度.csv")}
    published = {r["服务区"]: r for r in rows(RES / "单服务区往返几何参数.csv")}
    trips = rows(OUT1 / "最优组批_逐架次.csv")
    summary = json.loads((OUT1 / "汇总.json").read_text(encoding="utf-8"))
    drone_rows = list(load_workbook(DATA / "运输无人机数据.xlsx", read_only=True, data_only=True).active.values)
    drones = {r[0]: r for r in drone_rows[2:5]}

    # 节点表基准：O01 取地面海拔，服务区取地面海拔+30 m（题面原文.txt:45）
    z_node = {n: float(r["节点表地面海拔（m）"]) + (0.0 if n == "O01" else 30.0) for n, r in nodes.items()}
    z_dem = {n: float(r["作业海拔（m）"]) for n, r in nodes.items()}

    def geometry(site, z):
        return {"去程爬升": float(published[site]["去程巡航海拔（m）"]) - z["O01"],
                "去程下降": float(published[site]["去程巡航海拔（m）"]) - z[site],
                "返程爬升": float(published[site]["返程巡航海拔（m）"]) - z[site],
                "返程下降": float(published[site]["返程巡航海拔（m）"]) - z["O01"]}

    geom_delta = {}
    for site in published:
        a, b = geometry(site, z_dem), geometry(site, z_node)
        geom_delta[site] = {k: b[k] - a[k] for k in a}
    worst = max(geom_delta, key=lambda s: max(abs(v) for v in geom_delta[s].values()))
    print("== 几何对照 ==")
    print("节点作业海拔差 (节点表-DEM) m:", {n: round(z_node[n] - z_dem[n], 6) for n in sorted(nodes)})
    print(f"往返爬升/下降最大变化节点 {worst}:", {k: round(v, 6) for k, v in geom_delta[worst].items()})
    print("15 区总爬升变化范围 m:", round(min(v["去程爬升"] for v in geom_delta.values()), 6),
          round(max(v["去程爬升"] for v in geom_delta.values()), 6))

    def energy(model, site, mass, z):
        r = drones[model]
        empty, maxm, cruise_v, no_load, full, battery, eta = map(float, (r[2], r[3], r[5], r[6], r[7], r[8], r[16]))
        g = geometry(site, z)
        out_d, back_d = float(published[site]["去程水平距离（m）"]), float(published[site]["返程水平距离（m）"])
        loaded = no_load - (no_load - full) * (mass / maxm) ** 1.5
        return (battery * out_d / loaded + battery * back_d / no_load
                + 9.81 * ((empty + mass) * g["去程爬升"] + empty * g["返程爬升"]) / (3.6e6 * eta))

    def seconds(model, site, boxes_n, z):
        r = drones[model]
        g = geometry(site, z)
        ascend = g["去程爬升"] + g["返程爬升"]
        descend = g["去程下降"] + g["返程下降"]
        horiz = float(published[site]["水平总距离（m）"])
        return (ascend / float(r[14]) + horiz / float(r[5]) + descend / float(r[15])
                + float(r[10]) + boxes_n * float(r[11]) + float(r[12]) + boxes_n * float(r[13]))

    e_dem = t_dem = 0.0
    e_node = t_node = 0.0
    soc_dem = soc_node = 1.0
    per_area = {}
    for row in trips:
        site, model, mass, n = row["服务区"], row["机型"], float(row["质量_kg"]), int(row["箱数"])
        ed = energy(model, site, mass, z_dem); en = energy(model, site, mass, z_node)
        td = seconds(model, site, n, z_dem); tn = seconds(model, site, n, z_node)
        battery = float(drones[model][8])
        assert abs(ed - float(row["能耗_kwh"])) < 1e-12, (site, ed, row["能耗_kwh"])
        assert abs(td - float(row["作业时间_s"])) < 1e-9
        e_dem += ed; e_node += en; t_dem += td; t_node += tn
        soc_dem = min(soc_dem, 1 - ed / battery); soc_node = min(soc_node, 1 - en / battery)
        a = per_area.setdefault(site, [0.0, 0.0])
        a[0] += ed; a[1] += en

    print("== 已发布 18 架次组批在两种基准下的重算（同一组批）==")
    print(f"DEM 基准:     E={e_dem:.9f} kWh  T={t_dem:.6f} s  minSOC={100*soc_dem:.6f}%")
    print(f"节点表基准:   E={e_node:.9f} kWh  T={t_node:.6f} s  minSOC={100*soc_node:.6f}%")
    print(f"发布汇总值:   E={summary['总能耗_kWh']:.9f} kWh  T={summary['累计作业时间_s']:.6f} s  minSOC={100*summary['最低返航SOC']:.6f}%")
    print(f"绝对变化: dE={e_node-e_dem:+.9f} kWh  dT={t_node-t_dem:+.6f} s  dSOC={100*(soc_node-soc_dem):+.6f} pp")
    print(f"相对变化: dE={100*(e_node-e_dem)/e_dem:.6f}%  dT={100*(t_node-t_dem)/t_dem:.6f}%")
    print("逐区能耗变化 kWh:", {s: round(v[1] - v[0], 9) for s, v in per_area.items()})

    # 安全载荷（45 组）在同一公式下的变化上界：用发布载荷值直接评估
    caps = rows(OUT1 / "最大安全载荷_45组.csv")
    print("== 45 组安全载荷状态 ==")
    changed = []
    for row in caps:
        site, model = row["服务区"], row["机型"]
        q = float(row["最大安全载荷_kg"])
        ed = energy(model, site, q, z_dem); en = energy(model, site, q, z_node)
        if abs(en - ed) > 1e-12:
            changed.append((site, model, row["状态"], round(en - ed, 9)))
    print(f"载荷评估能耗变化非零组数 {len(changed)}/45，最大 |Δ| kWh =",
          max((abs(c[3]) for c in changed), default=0.0))
    print("样例:", changed[:5])


if __name__ == "__main__":
    main()
