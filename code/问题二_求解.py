"""问题二：固定参考架次 MILP 热启动，资源解码驱动的大邻域搜索与权衡。"""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
from collections import defaultdict

from 问题二_调度核心 import decode, load_data
from 问题二_参考路线种子 import optimize_seed
from 问题二_结果输出 import OUT, save, write_csv

PROFILES = {
    "完成时间优先": (10.0, 5.0, 5.0),
    "均衡": (1.0, 300.0, 300.0),
    "能耗优先": (.2, 1000.0, 100.0),
    "架次优先": (.2, 100.0, 3000.0),
}
OPERATORS = ("交换同区货箱", "移动同区货箱", "重排架次", "交换架次",
             "换机型", "反转站序", "合并架次", "拆分架次", "移除重插")


def penalty(metrics, weights):
    duration, energy, count = weights
    return (1e7 * metrics["hard_excess_s"]
            + 1e4 * metrics["weighted_tardiness"]
            + duration * metrics["makespan_s"]
            + energy * metrics["energy_kwh"]
            + count * metrics["sorties"])


def priority(metrics):
    return (metrics["hard_excess_s"] > 1e-6, metrics["hard_excess_s"],
            metrics["weighted_tardiness"], metrics["makespan_s"],
            metrics["energy_kwh"], metrics["sorties"])


def occurrences(specs):
    by_area = defaultdict(list)
    for ti, spec in enumerate(specs):
        for si, stop in enumerate(spec["stops"]):
            by_area[stop["area"]].append((ti, si))
    return by_area


def remove_empty(specs):
    for spec in specs:
        spec["stops"] = [stop for stop in spec["stops"] if stop["ids"]]
    return [spec for spec in specs if spec["stops"]]


def neighbor(specs, rng, operator, data):
    candidate = copy.deepcopy(specs)
    n = len(candidate)
    if operator in ("交换同区货箱", "移动同区货箱"):
        grouped = occurrences(candidate)
        areas = [area for area, places in grouped.items() if len(places) >= 2]
        if not areas:
            return None
        first, second = rng.sample(grouped[rng.choice(areas)], 2)
        a = candidate[first[0]]["stops"][first[1]]["ids"]
        b = candidate[second[0]]["stops"][second[1]]["ids"]
        ia, ib = rng.randrange(len(a)), rng.randrange(len(b))
        if operator == "交换同区货箱":
            a[ia], b[ib] = b[ib], a[ia]
        else:
            b.append(a.pop(ia))
            candidate = remove_empty(candidate)
    elif operator == "重排架次":
        i, j = rng.sample(range(n), 2)
        candidate.insert(j, candidate.pop(i))
    elif operator == "交换架次":
        i, j = rng.sample(range(n), 2)
        candidate[i], candidate[j] = candidate[j], candidate[i]
    elif operator == "换机型":
        i = rng.randrange(n)
        candidate[i]["model"] = rng.choice([g for g in "ABC" if g != candidate[i]["model"]])
    elif operator == "反转站序":
        choices = [i for i, spec in enumerate(candidate) if len(spec["stops"]) > 1]
        if not choices:
            return None
        candidate[rng.choice(choices)]["stops"].reverse()
    elif operator == "合并架次":
        i, j = sorted(rng.sample(range(n), 2))
        left, right = candidate[i], candidate[j]
        areas = {stop["area"] for stop in left["stops"] + right["stops"]}
        if len(areas) > 3:
            return None
        for stop in right["stops"]:
            same = next((s for s in left["stops"] if s["area"] == stop["area"]), None)
            if same is None:
                left["stops"].append(stop)
            else:
                same["ids"].extend(stop["ids"])
        left["model"] = rng.choice((left["model"], right["model"], "C"))
        candidate.pop(j)
    elif operator == "拆分架次":
        i = rng.randrange(n)
        spec = candidate[i]
        if len(spec["stops"]) > 1:
            cut = rng.randrange(1, len(spec["stops"]))
            moved = spec["stops"][cut:]
            spec["stops"] = spec["stops"][:cut]
        else:
            stop = spec["stops"][0]
            if len(stop["ids"]) < 2:
                return None
            cut = rng.randrange(1, len(stop["ids"]))
            moved = [{"area": stop["area"], "ids": stop["ids"][cut:]}]
            stop["ids"] = stop["ids"][:cut]
        new_model = rng.choice((spec["model"], "A", "B", "C"))
        candidate.insert(i + 1, {"model": new_model, "stops": moved})
    elif operator == "移除重插":
        count = rng.randint(1, 3)
        for _ in range(count):
            places = [(i, j) for i, spec in enumerate(candidate)
                      for j, stop in enumerate(spec["stops"]) if stop["ids"]]
            if not places:
                return None
            ti, si = rng.choice(places)
            source = candidate[ti]["stops"][si]
            bid = source["ids"].pop(rng.randrange(len(source["ids"])))
            area = data["boxes"][bid]["area"]
            candidate = remove_empty(candidate)
            choices = [(i, j) for i, spec in enumerate(candidate)
                       for j, stop in enumerate(spec["stops"]) if stop["area"] == area]
            options = ["same"] * (3 if choices else 0) + ["new_stop"] * 2 + ["new_sortie"]
            action = rng.choice(options)
            if action == "same":
                i, j = rng.choice(choices)
                candidate[i]["stops"][j]["ids"].append(bid)
            elif action == "new_stop":
                possible = [i for i, spec in enumerate(candidate)
                            if len(spec["stops"]) < 3 and area not in {s["area"] for s in spec["stops"]}]
                if possible:
                    i = rng.choice(possible)
                    candidate[i]["stops"].insert(rng.randrange(len(candidate[i]["stops"]) + 1),
                                                  {"area": area, "ids": [bid]})
                else:
                    action = "new_sortie"
            if action == "new_sortie":
                candidate.insert(rng.randrange(len(candidate) + 1),
                                 {"model": rng.choice("ABC"), "stops": [{"area": area, "ids": [bid]}]})
    else:
        raise ValueError(operator)
    return candidate


def search(start_specs, data, profile, iterations, seed):
    rng = random.Random(seed)
    weights = PROFILES[profile]
    current_specs = copy.deepcopy(start_specs)
    current = decode(current_specs, data, require_all=True)
    assert current is not None
    current_score = penalty(current["metrics"], weights)
    best_specs, best = copy.deepcopy(current_specs), current
    best_score = current_score
    lex_specs, lex_best = copy.deepcopy(current_specs), current
    trace = []
    accepted, physically_valid = 0, 0
    temp0 = max(100.0, current_score * .02)
    temp_end = max(1.0, temp0 * .001)
    op_weights = {op: 1.0 for op in OPERATORS}
    op_hits = {op: 0 for op in OPERATORS}
    op_rewards = {op: 0.0 for op in OPERATORS}
    for iteration in range(iterations):
        op = rng.choices(OPERATORS, weights=[op_weights[name] for name in OPERATORS], k=1)[0]
        op_hits[op] += 1
        candidate_specs = neighbor(current_specs, rng, op, data)
        if candidate_specs is None:
            continue
        candidate = decode(candidate_specs, data, require_all=True)
        if candidate is None:
            continue
        physically_valid += 1
        score = penalty(candidate["metrics"], weights)
        temp = temp0 * (temp_end / temp0) ** (iteration / max(1, iterations - 1))
        improved_current = score < current_score - 1e-7
        improved_best = score < best_score - 1e-7 and candidate["metrics"]["hard_excess_s"] <= 1e-6
        if priority(candidate["metrics"]) < priority(lex_best["metrics"]):
            lex_specs, lex_best = copy.deepcopy(candidate_specs), candidate
        if score <= current_score or rng.random() < math.exp(min(0, (current_score - score) / temp)):
            current_specs, current, current_score = candidate_specs, candidate, score
            accepted += 1
            op_rewards[op] += 9 if improved_current else 3
        if improved_best:
            best_specs, best, best_score = copy.deepcopy(candidate_specs), candidate, score
            op_rewards[op] += 33
        if (iteration + 1) % 100 == 0:
            for name in OPERATORS:
                if op_hits[name]:
                    op_weights[name] = max(.1, .9 * op_weights[name] + .1 * op_rewards[name] / op_hits[name])
                op_hits[name] = 0
                op_rewards[name] = 0.0
        if (iteration + 1) % 100 == 0 or iteration + 1 == iterations:
            trace.append({"方案": profile, "种子": seed, "迭代": iteration + 1,
                          "当前代价": current_score, "历史最优代价": best_score,
                          "历史最优完成时间_s": best["metrics"]["makespan_s"],
                          "历史最优能耗_kWh": best["metrics"]["energy_kwh"],
                          "历史最优架次": best["metrics"]["sorties"]})
    return best_specs, best, lex_specs, lex_best, {"profile": profile, "seed": seed,
                              "iterations": iterations, "physically_valid": physically_valid,
                              "accepted": accepted, "score": best_score,
                              "operator_weights": op_weights}, trace


def nondominated(records):
    kept = []
    seen = set()
    for name, plan in records:
        m = plan["metrics"]
        if m["hard_excess_s"] > 1e-6 or m["weighted_tardiness"] > 1e-6:
            continue
        vector = (m["makespan_s"], m["energy_kwh"], m["sorties"])
        dominated = any(all(x <= y + 1e-7 for x, y in zip((other["metrics"]["makespan_s"],
                                                             other["metrics"]["energy_kwh"],
                                                             other["metrics"]["sorties"]), vector))
                        and any(x < y - 1e-7 for x, y in zip((other["metrics"]["makespan_s"],
                                                               other["metrics"]["energy_kwh"],
                                                               other["metrics"]["sorties"]), vector))
                        for _, other in records)
        if not dominated:
            signature = tuple(round(value, 6) for value in vector)
            if signature not in seen:
                kept.append(name)
                seen.add(signature)
    return kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=4000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = parser.parse_args()
    data = load_data()
    start_specs, warm, milp_info = optimize_seed(data)
    assert warm["metrics"]["hard_excess_s"] <= 1e-6 and warm["metrics"]["weighted_tardiness"] <= 1e-6
    OUT.mkdir(parents=True, exist_ok=True)
    print("参考热启动", warm["metrics"], milp_info, flush=True)
    records = [("参考热启动", warm)]
    traces, metadata = [], []
    for profile in PROFILES:
        best_specs, best_plan, best_meta = start_specs, warm, None
        for seed in args.seeds:
            specs, plan, lex_specs, lex_plan, meta, trace = search(start_specs, data, profile, args.iterations, seed)
            traces.extend(trace)
            metadata.append(meta)
            print(profile, seed, plan["metrics"], flush=True)
            records.append((f"{profile}_种子{seed}", plan))
            records.append((f"词典序候选_{profile}_种子{seed}", lex_plan))
            if best_meta is None or penalty(plan["metrics"], PROFILES[profile]) < penalty(best_plan["metrics"], PROFILES[profile]) - 1e-7:
                best_specs, best_plan, best_meta = specs, plan, meta
        records.append((profile, best_plan))
    # 主方案严格按零硬违约、零加权延误后的 F2/F3/F4 顺序选取所有已找到的可行点。
    main_name, main_plan = min(records, key=lambda item: priority(item[1]["metrics"]))
    save(main_plan, data, "主方案", with_template=True)
    table = []
    pareto_names = nondominated(records)
    pareto = set(pareto_names)
    pareto_files = {}
    for index, name in enumerate(pareto_names, 1):
        stem = f"非支配方案_{index:02d}"
        plan = next(plan for label, plan in records if label == name)
        save(plan, data, stem)
        pareto_files[name] = stem
    for name, plan in records:
        table.append({"方案": name, **plan["metrics"], "是否非支配": name in pareto,
                      "对应结果文件": pareto_files.get(name, "")})
    write_csv(OUT / "方案权衡.csv", table)
    write_csv(OUT / "搜索收敛记录.csv", traces)
    (OUT / "搜索元数据.json").write_text(json.dumps({"MILP热启动": milp_info, "搜索": metadata,
                                                  "主方案来源": main_name, "非支配方案": sorted(pareto)},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("主方案", main_name, main_plan["metrics"], flush=True)


if __name__ == "__main__":
    main()
