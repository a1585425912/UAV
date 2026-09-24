import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
ROOT = r"D:\git\math_modeling\UAV"
PKG = os.path.join(ROOT, "results", "问题三_成果呈现"); OUT = os.path.join(ROOT, "figures", "问题三_成果呈现")
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
plt.rcParams["font.family"] = FONT.get_name(); plt.rcParams["axes.unicode_minus"] = False; plt.rcParams["svg.fonttype"] = "none"
BLUE, ORANGE, GREEN, RED, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#6B7280"
def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
def save(fig, name):
    fig.tight_layout(pad=1.0)
    fig.savefig(os.path.join(OUT, name + ".png"), dpi=320, bbox_inches="tight")
    fig.savefig(os.path.join(OUT, name + ".svg"), bbox_inches="tight"); plt.close(fig); print("saved", name)
areas = rd(os.path.join(PKG, "各服务区调度方案.csv"))
relays = rd(os.path.join(PKG, "中继覆盖关系.csv"))
# 图：服务区调度甘特
fig, ax = plt.subplots(figsize=(9.2, 5.6))
ys = list(range(len(areas)))
for i, a in enumerate(areas):
    t0 = float(a["首箱交付_s"]); t1 = float(a["末箱交付_s"])
    color = ORANGE if a["保障方式"] == "中继" else BLUE
    ax.barh(i, max(t1 - t0, 40), left=t0, height=.5, color=color, ec="white", zorder=3)
    ax.text(t1 + 80, i, "%s(%d箱) %s" % (a["服务区"], int(a["货箱数"]), a["保障方式"]), va="center",
            fontproperties=FONT, fontsize=7, zorder=4)
for r in relays:
    a0 = float(r["建链完成_s"]) / 3600; a1 = float(r["服务结束_s"]) / 3600
    ax.axvspan(a0, a1, color=GREEN, alpha=.07, zorder=1)
relay_ticks = [(float(r["建链完成_s"]), r["中继架次"], r["点位"]) for r in relays]
for t, sid, site in relay_ticks:
    ax.axvline(t, color=GREEN, ls="--", lw=.8, alpha=.6, zorder=2)
    ax.text(t, len(areas) - .3, "%s(%s)" % (sid, site), rotation=90, fontproperties=FONT, fontsize=6.5, color=GREEN, va="top", ha="right", zorder=5)
ax.set_yticks(ys, [a["服务区"] for a in areas], fontproperties=FONT, fontsize=8)
ax.invert_yaxis()
ax.set_xscale("log")
ax.set_xlabel("任务开始后的时间（s，对数轴）", fontproperties=FONT, fontsize=9)
ax.set_title("第三问：各服务区交付时刻与中继保障（橙色=经中继，蓝色=直连；绿色带状=中继服务窗口）", fontproperties=FONT, fontsize=10.5, pad=9)
ax.grid(axis="x", color="#dddddd", linewidth=.5); ax.tick_params(labelsize=8)
save(fig, "result_q3_area_schedule")

# 图：权重/敏感性分析
rows = rd(os.path.join(PKG, "中继窗口权重分析.csv"))
fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.2))
ax = axes[0]
names = ["3中继\n标准窗口", "4中继\n已发布"]
T = [8115.197, 9573.284]; E = [75.5924, 76.1971]; N = [25, 26]
x = range(2); w = .27
ax.bar([i - w for i in x], [t / 3600 for t in T], w, color=BLUE, label="完成时间 (h)")
ax2 = ax.twinx()
ax2.bar([i for i in x], E, w, color=GREEN, label="总能耗 (kWh)")
ax2.set_ylabel("总能耗（kWh）", fontproperties=FONT, fontsize=9)
ax.bar([i + w for i in x], [n / 10 for n in N], w, color=ORANGE, label="架次数 /10")
for i, (t, e, n) in enumerate(zip(T, E, N)):
    ax.text(i - w, t / 3600 + .05, "%.2f" % (t / 3600), ha="center", fontsize=7.5)
    ax2.text(i, e + .03, "%.2f" % e, ha="center", fontsize=7.5)
    ax.text(i + w, n / 10 + .05, "%d" % n, ha="center", fontsize=7.5)
ax.set_xticks(list(x), names, fontproperties=FONT)
ax.set_ylabel("完成时间（h）", fontproperties=FONT, fontsize=9)
ax.set_title("候选方案的四项指标对比", fontproperties=FONT, fontsize=10.5, pad=9)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, prop=FONT, frameon=False, fontsize=7.5, loc="upper left")
ax.grid(axis="y", color="#dddddd", linewidth=.5)
ax = axes[1]
labels = [r["方案"] for r in rows]; gaps = [float(r["通信缺口_s"]) for r in rows]
colors = [GREEN if g <= 1e-6 else RED for g in gaps]
ax.barh(range(len(labels)), gaps, color=colors, ec="white")
ax.set_yticks(range(len(labels)), labels, fontproperties=FONT, fontsize=7)
ax.invert_yaxis(); ax.set_xscale("log")
ax.set_xlabel("通信未保障时长（s，对数轴）", fontproperties=FONT, fontsize=9)
ax.set_title("中继窗口敏感性：缩短窗口会产生缺口", fontproperties=FONT, fontsize=10.5, pad=9)
ax.grid(axis="x", color="#dddddd", linewidth=.5); ax.tick_params(labelsize=8)
save(fig, "result_q3_weight_analysis")
