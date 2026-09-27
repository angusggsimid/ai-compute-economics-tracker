#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the time-axis-first AI compute economics dashboard."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from statistics import median
import statistics
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COST_INDEX_PATH = ROOT / "tracker_data" / "backfills" / "openrouter_cost_index.json"
PROVIDER_DISPLAY = {
    "aws": "AWS", "azure": "Azure", "coreweave": "CoreWeave", "crusoe": "Crusoe",
    "datacrunch": "DataCrunch", "fal": "Fal", "hyperstack": "HyperStack",
    "jarvislabs": "JarvisLabs", "lambda": "Lambda", "massedcompute": "Massed Compute",
    "nebius": "Nebius", "ovh": "OVH", "runpod": "RunPod", "spheron": "Spheron",
    "together": "Together AI", "voltagepark": "Voltage Park", "vultr": "Vultr",
    "modal": "Modal", "vastai": "Vast.ai",
}

FOUNDRY_HISTORY_PATH = ROOT / "tracker_data" / "backfills" / "foundry_signals_gpu_history.json"
NEOCLOUD_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"
GPUFINDER_PATH = ROOT / "tracker_data" / "backfills" / "gpufinder_market.json"
OPENROUTER_ACTIVE_PRICE_PATH = ROOT / "tracker_data" / "backfills" / "openrouter_active_price_history.json"
CAPEX_HISTORY_PATH = ROOT / "tracker_data" / "backfills" / "capex_official_history.json"
REFERENCE_PATH = ROOT / "tracker_data" / "backfills" / "reference_index_history.json"
ORDERBOOK_PATH = ROOT / "tracker_data" / "backfills" / "gpu_orderbook_history.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "ai_compute_economics_monitor.html"
SNAPSHOT_PATH = Path(__file__).resolve().parent / "v4" / "time_series_snapshot.json"


def _openrouter_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rows = []
    for week in payload.get("weeks") or []:
        week_date = week.get("date")
        total = float(week.get("total_tokens") or 0)
        named = 0.0
        for model in week.get("model_rows") or []:
            tokens = float(model.get("tokens") or 0)
            if not week_date or not model.get("model") or tokens < 0:
                continue
            named += tokens
            raw_rows.append({
                "date": week_date,
                "model": model["model"],
                "vendor": model.get("provider") or str(model["model"]).split("/", 1)[0],
                "tokens": tokens,
            })
        raw_rows.append({
            "date": week_date,
            "model": "Others",
            "vendor": "OpenRouter",
            "tokens": max(0.0, total - named),
        })
    if not raw_rows:
        raise ValueError("OpenRouter cost index contains no weekly model rows")
    return sorted(raw_rows, key=lambda row: (row["date"], row["model"]))


def _openrouter_extract(raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        by_date[row["date"]].append(row)

    weeks = []
    for week_date, model_rows in sorted(by_date.items()):
        weeks.append({"date": week_date, "total_tokens": sum(float(row["tokens"]) for row in model_rows)})
    volume = []
    trailing = []
    for index, row in enumerate(weeks):
        volume.append({"date": row["date"], "series": "Weekly tokens", "value": row["total_tokens"] / 1e12})
        if index >= 3:
            average = sum(item["total_tokens"] for item in weeks[index - 3:index + 1]) / 4 / 1e12
            trailing.append({"date": row["date"], "series": "4W average", "value": average})

    leadership = []
    composition = []
    disclosure = []
    for week_date, model_rows in sorted(by_date.items()):
        total = sum(float(row["tokens"]) for row in model_rows)
        named = sorted(
            (row for row in model_rows if str(row["model"]) != "Others"),
            key=lambda row: float(row["tokens"]),
            reverse=True,
        )
        for rank, row in enumerate(named[:3], start=1):
            leadership.append({
                "date": week_date,
                "rank": rank,
                "model": row["model"],
                "vendor": row["vendor"],
                "tokens": float(row["tokens"]) / 1e12,
                "share": float(row["tokens"]) / total * 100 if total else 0.0,
            })
        for rank, row in enumerate(named, start=1):
            composition.append({
                "date": week_date,
                "rank": rank,
                "model": row["model"],
                "vendor": row["vendor"],
                "tokens": float(row["tokens"]) / 1e12,
                "share": float(row["tokens"]) / total * 100 if total else 0.0,
            })
        others = next((float(row["tokens"]) for row in model_rows if str(row["model"]) == "Others"), 0.0)
        composition.append({
            "date": week_date,
            "rank": len(named) + 1,
            "model": "Others",
            "vendor": "OpenRouter",
            "tokens": others / 1e12,
            "share": others / total * 100 if total else 0.0,
        })
        disclosure.append({
            "date": week_date,
            "othersShare": others / total * 100 if total else 0.0,
            "namedShare": (total - others) / total * 100 if total else 0.0,
        })
    return {
        "volume": volume + trailing,
        "leadership": leadership,
        "composition": composition,
        "disclosure": disclosure,
        "raw": raw_rows,
    }


def _price_asof(record: dict[str, Any] | None, observed_date: str, index: int) -> float | None:
    if not record:
        return None
    value = None
    for point in record.get("points") or []:
        if point[0] > observed_date:
            break
        value = point[index]
    return float(value) if isinstance(value, (int, float)) and value >= 0 else None


def _moving_average(rows: list[dict[str, Any]], window: int = 4) -> list[dict[str, Any]]:
    result = []
    for index, row in enumerate(rows):
        if index + 1 < window:
            continue
        selected = rows[index - window + 1:index + 1]
        result.append({
            "date": row["date"],
            "series": "4W average",
            "value": sum(item["value"] for item in selected) / window,
            "coverage": sum(item.get("coverage", 0) for item in selected) / window,
        })
    return result


def _active_model_price_extract(
    ranking_rows: list[dict[str, Any]], payload: dict[str, Any]
) -> dict[str, Any]:
    data = payload["data"]
    aliases = data["aliases"]
    history = data["history"]
    current = data["currentModels"]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ranking_rows:
        by_date[row["date"]].append(row)

    tier_order = ["免费", "<$1", "$1–5", ">$5", "Others / 无法匹配"]
    tiers = []
    input_weekly = []
    output_weekly = []
    resolved_rows = []
    for week_date, rows in sorted(by_date.items()):
        total = sum(float(row["tokens"]) for row in rows)
        tier_tokens = {name: 0.0 for name in tier_order}
        input_numerator = output_numerator = input_weight = output_weight = 0.0
        for row in rows:
            tokens = float(row["tokens"])
            rank_id = str(row["model"])
            if rank_id == "Others":
                tier_tokens["Others / 无法匹配"] += tokens
                continue
            free = rank_id.endswith(":free")
            base_id = aliases.get(rank_id) or (rank_id if rank_id in history else None)
            record = history.get(base_id) if base_id else None
            input_price = 0.0 if free else _price_asof(record, week_date, 1)
            output_price = 0.0 if free else _price_asof(record, week_date, 2)
            resolved_rows.append({
                **row,
                "baseId": base_id,
                "inputPrice": input_price,
                "outputPrice": output_price,
                "free": free,
            })
            if output_price is None:
                tier_tokens["Others / 无法匹配"] += tokens
            elif output_price == 0:
                tier_tokens["免费"] += tokens
            elif output_price < 1:
                tier_tokens["<$1"] += tokens
            elif output_price <= 5:
                tier_tokens["$1–5"] += tokens
            else:
                tier_tokens[">$5"] += tokens
            if input_price is not None:
                input_numerator += tokens * input_price
                input_weight += tokens
            if output_price is not None:
                output_numerator += tokens * output_price
                output_weight += tokens
        for tier in tier_order:
            tiers.append({"date": week_date, "series": tier, "value": tier_tokens[tier] / total * 100 if total else 0})
        if input_weight:
            input_weekly.append({
                "date": week_date,
                "series": "Weekly weighted rate",
                "value": input_numerator / input_weight,
                "coverage": input_weight / total * 100,
            })
        if output_weight:
            output_weekly.append({
                "date": week_date,
                "series": "Weekly weighted rate",
                "value": output_numerator / output_weight,
                "coverage": output_weight / total * 100,
            })

    recent_dates = sorted(by_date)[-4:]
    recent_total = sum(float(row["tokens"]) for row in ranking_rows if row["date"] in recent_dates)
    recent_by_model: dict[str, float] = defaultdict(float)
    for row in ranking_rows:
        if row["date"] in recent_dates and row["model"] != "Others":
            recent_by_model[row["model"]] += float(row["tokens"])
    active_models = []
    named_total = sum(recent_by_model.values())
    cumulative = 0.0
    for rank_id, tokens in sorted(recent_by_model.items(), key=lambda item: item[1], reverse=True):
        if len(active_models) >= 12 or (active_models and cumulative >= named_total * 0.8):
            break
        cumulative += tokens
        free = rank_id.endswith(":free")
        base_id = aliases.get(rank_id) or (rank_id if rank_id in history else None)
        record = history.get(base_id) if base_id else None
        current_record = current.get(base_id) if base_id else None
        price_date = data.get("asOf") or recent_dates[-1]
        input_price = 0.0 if free else _price_asof(record, price_date, 1)
        output_price = 0.0 if free else _price_asof(record, price_date, 2)
        active_models.append({
            "rankId": rank_id,
            "baseId": base_id,
            "name": (current_record or {}).get("name") or (record or {}).get("name") or rank_id,
            "tokens": tokens / 1e12,
            "share": tokens / recent_total * 100 if recent_total else 0,
            "inputPrice": input_price,
            "outputPrice": output_price,
            "historyPoints": len((record or {}).get("points") or []),
            "firstSeen": (record or {}).get("firstSeen"),
            "lastSeen": (record or {}).get("lastSeen"),
            "priceHistory": [
                {"date": point[0], "input": point[1], "output": point[2]}
                for point in ((record or {}).get("points") or [])
            ],
            "free": free,
        })
    return {
        "tiers": tiers,
        "inputBasket": input_weekly + _moving_average(input_weekly),
        "outputBasket": output_weekly + _moving_average(output_weekly),
        "activeModels": active_models,
        "tierOrder": tier_order,
    }


def _gpu_extract(payload: dict[str, Any]) -> dict[str, Any]:
    prices = payload["datasets"]["prices"]
    availability = payload["datasets"]["availability"]
    by_gpu: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prices:
        by_gpu[row["series"]].append(row)
    annotations = {}
    for gpu, rows in by_gpu.items():
        previous = None
        changes = []
        for row in sorted(rows, key=lambda item: item["date"]):
            count = int(row["providerCount"])
            if previous is not None and count != previous:
                changes.append({"date": row["date"], "label": f"{previous}→{count}"})
            previous = count
        annotations[gpu] = changes

    lookup = {(row["date"], row["series"]): row for row in prices}
    dates = sorted({row["date"] for row in prices})
    premium = []
    for gpu in ("H200", "B200"):
        ratios = []
        for observed_date in dates:
            base = lookup.get((observed_date, "H100"))
            target = lookup.get((observed_date, gpu))
            if base and target and base["value"]:
                ratios.append({"date": observed_date, "value": target["value"] / base["value"]})
        for index, row in enumerate(ratios):
            window = ratios[max(0, index - 29):index + 1]
            premium.append({
                "date": row["date"],
                "series": f"{gpu} / H100",
                "value": median(item["value"] for item in window),
            })
    return {"prices": prices, "availability": availability, "annotations": annotations, "premium": premium}


def _gpu_from_neocloud(neocloud_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """从 neocloud 34 家供应商逐条报价聚合出与 Foundry 同构的日度序列。
    同一 (日期, GPU) 下：value=中位价、low/high=区间、providerPrices=逐供应商中位、providerCount=家数。"""
    # 只取非中断性租赁档位（on-demand/secure/community），剔除 spot 与 serverless：
    # spot 可被抢占、serverless 按调用计费，都是不同产品；混入会让"租赁价格"随时间漂移。
    RENTAL_KINDS = {"on-demand", "secure", "community"}
    by_day_gpu: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for row in neocloud_rows or []:
        gpu = str(row.get("series"))
        if gpu not in ("H100", "H200", "B200"):
            continue
        if str(row.get("kind") or "").lower() not in RENTAL_KINDS:
            continue
        price = row.get("usdPerGpuHour")
        day = str(row.get("date"))
        if not isinstance(price, (int, float)) or price <= 0 or len(day) != 10:
            continue
        by_day_gpu[(day, gpu)].append((str(row.get("provider")), float(price)))

    prices: list[dict[str, Any]] = []
    for (day, gpu), entries in sorted(by_day_gpu.items()):
        per_prov: dict[str, list[float]] = defaultdict(list)
        for prov, v in entries:
            per_prov[prov].append(v)
        provider_medians = {prov: round(median(vs), 4) for prov, vs in per_prov.items()}
        prov_values = sorted(provider_medians.values())
        if len(prov_values) >= 4:
            quartiles = statistics.quantiles(prov_values, n=4)
            p25, p75 = round(quartiles[0], 4), round(quartiles[2], 4)
        else:
            p25, p75 = prov_values[0], prov_values[-1]
        prices.append({
            "date": day,
            "series": gpu,
            "value": round(median(prov_values), 4),          # 跨供应商中位（每家一票）
            "p25": p25,
            "p75": p75,
            "low": round(min(prov_values), 4),
            "high": round(max(prov_values), 4),
            "average": round(sum(prov_values) / len(prov_values), 4),
            "providerCount": len(provider_medians),
            "providerPrices": provider_medians,
        })

    by_series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prices:
        by_series[row["series"]].append(row)
    for gpu, rows in by_series.items():
        rows.sort(key=lambda r: r["date"])
        for index, row in enumerate(rows):
            window = rows[max(0, index - 29):index + 1]
            row["movingAverage30d"] = round(sum(w["value"] for w in window) / len(window), 4)

    lookup = {(row["date"], row["series"]): row for row in prices}
    dates = sorted({row["date"] for row in prices})
    premium = []
    for gpu in ("H200", "B200"):
        ratios = []
        for observed_date in dates:
            base = lookup.get((observed_date, "H100"))
            target = lookup.get((observed_date, gpu))
            if base and target and base["value"]:
                ratios.append({"date": observed_date, "value": target["value"] / base["value"]})
        for index, row in enumerate(ratios):
            window = ratios[max(0, index - 29):index + 1]
            premium.append({
                "date": row["date"],
                "series": f"{gpu} / H100",
                "value": median(item["value"] for item in window),
            })
    annotations: dict[str, list[dict[str, Any]]] = {}
    for gpu, rows in by_series.items():
        previous = None
        changes = []
        for row in sorted(rows, key=lambda item: item["date"]):
            count = int(row["providerCount"])
            if previous is not None and count != previous:
                changes.append({"date": row["date"], "label": f"{previous}→{count}"})
            previous = count
        annotations[gpu] = changes

    return {
        "prices": sorted(prices, key=lambda r: (r["date"], r["series"])),
        "premium": premium,
        "annotations": annotations,
    }


def _reference_extract(reference_raw: dict[str, Any], orderbook_raw: dict[str, Any], gpu_prices: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """三源价格对照（按前沿 GPU 分面）+ 合约带 + OTPI 序列与各自的有效日数。"""
    datasets_ref = reference_raw.get("datasets") or {}
    basis_rows: dict[str, list[dict[str, Any]]] = {"H100": [], "H200": [], "B200": []}
    family_map = {"semiComposite": "SemiAnalysis 综合指数", "ornnOcpi": "Ornn 成交指数"}
    for dataset_name, label in family_map.items():
        for row in datasets_ref.get(dataset_name) or []:
            family = str(row.get("series", "")).split()[0]
            if family in basis_rows and isinstance(row.get("indexValue"), (int, float)):
                basis_rows[family].append({
                    "date": row["date"],
                    "series": label,
                    "value": round(float(row["indexValue"]), 4),
                })
    foundry_prices = gpu_prices
    for row in foundry_prices:
        family = str(row.get("series", ""))
        if family in basis_rows and isinstance(row.get("value"), (int, float)):
            basis_rows[family].append({
                "date": row["date"],
                "series": "Neocloud 报价中位",
                "value": round(float(row["value"]), 4),
            })
    # 对照图归一化：截到所有线共存的窗口，各自以共同起点=100 重定基。
    # 绝对水平因口径不同本就不可比；归一化后看的是"相对变化是否同步"（扇形开口=分歧）。
    basis_common_start: dict[str, str] = {}
    for family, rows in basis_rows.items():
        if not rows:
            continue
        by_series: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_series.setdefault(row["series"], []).append(row)
        if len(by_series) < 2:
            continue
        starts = {name: min(r["date"] for r in rs) for name, rs in by_series.items()}
        common_start = max(starts.values())
        rebased = []
        for name, rs in by_series.items():
            rs = sorted(rs, key=lambda r: r["date"])
            base = next((r["value"] for r in rs if r["date"] >= common_start), None)
            if not base:
                continue
            for r in rs:
                if r["date"] >= common_start:
                    rebased.append({"date": r["date"], "series": name, "value": round(100 * r["value"] / base, 2)})
        basis_rows[family] = sorted(rebased, key=lambda r: (r["date"], r["series"]))
        basis_common_start[family] = common_start

    contract = [
        {"date": row["date"], "series": name, "value": round(float(row[field]), 3)}
        for row in datasets_ref.get("semiContract1y") or []
        if row.get("series") == "H100-1y"
        for name, field in (("H100 1Y 合约下限", "lowValue"), ("H100 1Y 合约上限", "highValue"))
        if isinstance(row.get(field), (int, float))
    ]
    otpi = [
        {"date": row["date"], "series": f"{row['series']} OTPI", "value": round(float(row["indexValue"]), 4)}
        for row in datasets_ref.get("ornnOtpi") or []
        if isinstance(row.get("indexValue"), (int, float))
    ]

    def _valid_days(rows: list[dict[str, Any]]) -> int:
        return len({row["date"] for row in rows})

    # E2 固定供应商面板指数：Foundry providerPrices，固定成员、起点=100
    import statistics as _statistics
    panel_rows: list[dict[str, Any]] = []
    panel_meta: dict[str, Any] = {"members": {}}
    for family in ("H100", "B200"):
        per_day: dict[str, dict[str, float]] = {}
        for row in foundry_prices:
            if row.get("series") != family:
                continue
            pp = row.get("providerPrices")
            if isinstance(pp, dict):
                day_prices = {str(k): float(v) for k, v in pp.items() if isinstance(v, (int, float)) and v > 0}
                if day_prices:
                    per_day[str(row["date"])] = day_prices
        if len(per_day) < 10:
            continue
        # 从最近端向回搜索最大的连续后缀窗口，使 >=3 家供应商在该窗口内全程报价
        dates_all = sorted(per_day)
        chosen = None
        for start_idx in range(len(dates_all)):
            window = dates_all[start_idx:]
            if len(window) < 10:
                break
            cov_w: dict[str, int] = {}
            for _d in window:
                for prov in per_day[_d]:
                    cov_w[prov] = cov_w.get(prov, 0) + 1
            members_w = sorted(p_ for p_, cnt in cov_w.items() if cnt >= 0.9 * len(window))
            if len(members_w) >= 3:
                chosen = (window, members_w)
                break
        if not chosen:
            continue
        window, members = chosen
        # 窗口起点推进到全体成员均有报价的首日（否则固定面板无法取基期）
        while window and not all(m in per_day[window[0]] for m in members):
            window = window[1:]
        if len(window) < 10:
            continue
        base_date = window[0]
        base_mean = sum(per_day[base_date][m] for m in members) / len(members)
        panel_meta["members"][family] = {"members": members, "windowStart": base_date, "windowDays": len(window)}
        panel_meta.setdefault("annotations", {})[family] = []
        prev_vals: dict[str, float] | None = None
        prev_mean: float | None = None
        for d in window:
            vals_map = {m: per_day[d][m] for m in members if m in per_day[d]}
            if len(vals_map) != len(members):
                continue
            mean_now = sum(vals_map.values()) / len(vals_map)
            # 台阶归因：环比 >5% 的跳变标注最大变动成员（多为单家调价，避免被误读为市场崩盘）
            if prev_mean is not None and prev_mean > 0 and abs(mean_now / prev_mean - 1) > 0.05 and prev_vals:
                movers = sorted(
                    ((m, vals_map[m] / prev_vals[m] - 1) for m in members if m in prev_vals and prev_vals[m] > 0),
                    key=lambda x: abs(x[1]), reverse=True,
                )
                if movers:
                    m, chg = movers[0]
                    panel_meta["annotations"][family].append({
                        "date": d,
                        "label": f"{PROVIDER_DISPLAY.get(m, m)} {chg * 100:+.0f}%",
                    })
            prev_mean, prev_vals = mean_now, vals_map
            panel_rows.append({
                "date": d,
                "series": f"{family} 固定面板",
                "value": round(100 * (mean_now / base_mean), 2),
            })

        # 持久性成员大变动（≥20% 且新价连续站稳 ≥3 天）：即使面板位移 <5% 也要标注——
        # 只标持久台阶，不标 spheron 式两档翻烧饼的日度振荡。
        annotated_dates = {a["date"] for a in panel_meta["annotations"][family]}
        for m in members:
            member_prices = {d: per_day[d][m] for d in window if m in per_day[d]}
            days_sorted = sorted(member_prices)
            i = 1
            while i < len(days_sorted):
                prev_d, cur_d = days_sorted[i - 1], days_sorted[i]
                if prev_d and member_prices[prev_d] > 0:
                    chg = member_prices[cur_d] / member_prices[prev_d] - 1
                    if abs(chg) >= 0.20:
                        head = days_sorted[max(0, i - 3):i]
                        tail = days_sorted[i + 1:i + 6]
                        head_stable = len(head) == 3 and all(
                            abs(member_prices[h] / member_prices[prev_d] - 1) <= 0.10 for h in head
                        )
                        tail_stable = len(tail) == 5 and all(
                            abs(member_prices[t] / member_prices[cur_d] - 1) <= 0.10 for t in tail
                        )
                        # 真台阶 = 稳(≥3天) → 跳(≥20%) → 稳(≥5天)；滤掉 spheron 式两档翻烧饼
                        if head_stable and tail_stable:
                            if cur_d not in annotated_dates:
                                panel_meta["annotations"][family].append({
                                    "date": cur_d,
                                    "label": f"{PROVIDER_DISPLAY.get(m, m)} {chg * 100:+.0f}%",
                                })
                                annotated_dates.add(cur_d)
                            i += 6
                            continue
                i += 1
        panel_meta["annotations"][family].sort(key=lambda a: a["date"])

    return (
        {
            "panelIndex": sorted(panel_rows, key=lambda r: (r["date"], r["series"])),
            "basisH100": sorted(basis_rows["H100"], key=lambda r: (r["date"], r["series"])),
            "basisH200": sorted(basis_rows["H200"], key=lambda r: (r["date"], r["series"])),
            "basisH200": sorted(basis_rows["H200"], key=lambda r: (r["date"], r["series"])),
            "basisB200": sorted(basis_rows["B200"], key=lambda r: (r["date"], r["series"])),
            "contractBand": sorted(contract, key=lambda r: r["date"]),
            "otpi": sorted(otpi, key=lambda r: (r["date"], r["series"])),
        },
        {
            "basisCommonStart": basis_common_start,
            "orderbookValidDays": _valid_days(orderbook_raw.get("rows") or []),
            "otpiValidDays": _valid_days(otpi),
            "contractPeriods": len({row["date"] for row in contract}),
            "panelMembers": panel_meta["members"],
            "panelAnnotations": panel_meta.get("annotations") or {},
        },
    )


CAPEX_METRIC_LABELS = {
    "capex actual": "资本开支（实际）",
    "PaymentsToAcquirePropertyPlantAndEquipment": "购置固定资产（现金流）",
    "PaymentsToAcquireProductiveAssets": "购置生产性资产（现金流）",
    "capex total incl finance leases": "资本开支（含融资租赁）",
    "capex quarterly": "资本开支（季度）",
    "ttm capex actual net": "资本开支 TTM（净额）",
    "remaining performance obligations": "剩余履约义务（RPO）",
    "cloud backlog": "云订单积压",
    "customer demand exceeds supply": "管理层：需求超过供给",
    "capex short lived assets comment": "管理层：短周期资产说明",
    "cloud revenue including other segments": "云收入（含其他分部）",
    "rd spending": "研发支出",
    "ai cloud capex ttm": "AI 云基建支出（TTM）",
    "ttm capex increase reflects ai investment": "管理层：资本开支增长反映 AI 投入",
    "fy2026 capex guidance low": "FY2026 指引下限",
    "fy2026 capex guidance high": "FY2026 指引上限",
    "fy2026 capex guidance previous low": "FY2026 指引下限（上调前）",
    "fy2026 capex guidance previous high": "FY2026 指引上限（上调前）",
    "calendar 2026 capex guidance": "2026 自然年指引",
}
CAPEX_PERIOD_LABELS = {
    "capex_guidance_revision": "指引修订",
    "management_capacity_comment": "管理层口径（供给）",
    "capacity_comment": "管理层口径",
    "rpo": "订单储备",
    "cloud_context_not_capex": "背景信息（非资本开支）",
    "annual_rd_context_not_capex": "背景信息（非资本开支）",
    "ttm_ai_cloud_infrastructure": "AI 云基建 TTM",
    "q1_2026_total_capex": "2026 Q1（总计）",
    "q1_2026_consolidated_capex": "2026 Q1（合并）",
    "calendar_2026_guidance_after_lease_reclassification": "2026 指引（租赁重分类后）",
}
CAPEX_UNIT_LABELS = {"USD_B": "十亿美元", "CNY_B": "十亿人民币", "evidence_flag": "定性"}


def _capex_display(row: dict[str, Any]) -> dict[str, Any]:
    """把底表的机器格式（XBRL 标签/下划线期间/代码单位）翻译成人话；原始值保留不动。"""
    out = dict(row)
    out["metricLabel"] = CAPEX_METRIC_LABELS.get(str(row.get("metric")), row.get("metric"))
    out["periodLabel"] = CAPEX_PERIOD_LABELS.get(str(row.get("period")), row.get("period") or "")
    out["unitLabel"] = CAPEX_UNIT_LABELS.get(str(row.get("unit")), row.get("unit") or "")
    if row.get("unit") == "evidence_flag":
        out["valueDisplay"] = "—"
    else:
        value = row.get("value")
        out["valueDisplay"] = f"{value:g}" if isinstance(value, (int, float)) else str(value)
    return out


def build_snapshot() -> dict[str, Any]:
    if not COST_INDEX_PATH.exists():
        raise FileNotFoundError(COST_INDEX_PATH)
    if not FOUNDRY_HISTORY_PATH.exists():
        raise FileNotFoundError(FOUNDRY_HISTORY_PATH)
    if not OPENROUTER_ACTIVE_PRICE_PATH.exists():
        raise FileNotFoundError(OPENROUTER_ACTIVE_PRICE_PATH)
    if not CAPEX_HISTORY_PATH.exists():
        raise FileNotFoundError(CAPEX_HISTORY_PATH)
    openrouter_raw = json.loads(COST_INDEX_PATH.read_text(encoding="utf-8"))
    foundry_raw = json.loads(FOUNDRY_HISTORY_PATH.read_text(encoding="utf-8"))
    active_price_raw = json.loads(OPENROUTER_ACTIVE_PRICE_PATH.read_text(encoding="utf-8"))
    reference_raw = json.loads(REFERENCE_PATH.read_text(encoding="utf-8")) if REFERENCE_PATH.exists() else {}
    orderbook_raw = json.loads(ORDERBOOK_PATH.read_text(encoding="utf-8")) if ORDERBOOK_PATH.exists() else {}
    neocloud_raw = json.loads(NEOCLOUD_PATH.read_text(encoding="utf-8")) if NEOCLOUD_PATH.exists() else {}
    gpufinder_raw = json.loads(GPUFINDER_PATH.read_text(encoding="utf-8")) if GPUFINDER_PATH.exists() else {}
    capex_raw = json.loads(CAPEX_HISTORY_PATH.read_text(encoding="utf-8"))
    openrouter = _openrouter_extract(_openrouter_rows(openrouter_raw))
    active_prices = _active_model_price_extract(openrouter["raw"], active_price_raw)

    neocloud_rows = neocloud_raw.get("rows") or []
    if not neocloud_rows:
        # 价格层已 2026-09-27 起全面切换到 neocloud（非中断性租赁口径）；
        # 缺失时硬失败而非静默回退到 Foundry 旧口径，避免两种口径混用。
        raise FileNotFoundError(f"neocloud 价格数据缺失：{NEOCLOUD_PATH}")
    gpu = _gpu_from_neocloud(neocloud_rows)
    scarcity, listed_gap, breadth = [], [], []
    for row in gpufinder_raw.get("rows") or []:
        day, gpu_name = str(row.get("date") or ""), str(row.get("gpu") or "")
        if len(day) != 10 or gpu_name not in ("H100", "H200", "B200"):
            continue
        if isinstance(row.get("availabilityPct"), (int, float)):
            scarcity.append({"date": day, "series": gpu_name, "value": row["availabilityPct"]})
        if isinstance(row.get("listedAvailableGapPct"), (int, float)):
            listed_gap.append({"date": day, "series": gpu_name, "value": row["listedAvailableGapPct"]})
        if isinstance(row.get("providerCount"), (int, float)):
            breadth.append({"date": day, "series": gpu_name, "value": row["providerCount"]})
    capex = [_capex_display(row) for row in sorted(capex_raw.get("rows") or [], key=lambda r: (r["date"], r["company"]), reverse=True)]

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    dated_rows = (
        openrouter["volume"] + openrouter["composition"]
        + gpu["prices"] + scarcity + active_prices["tiers"]
    )
    ref_datasets, ref_meta = _reference_extract(reference_raw, orderbook_raw, gpu["prices"])
    snapshot = {
        "meta": {
            "generatedAt": generated_at,
            "minDate": min(row["date"] for row in dated_rows),
            "maxDate": max(row["date"] for row in dated_rows),
        },
        "datasets": {
            "openrouterVolume": openrouter["volume"],
            "openrouterComposition": openrouter["composition"],
            "openrouterDisclosure": openrouter["disclosure"],
            "activePriceTiers": active_prices["tiers"],
            "activeInputBasket": active_prices["inputBasket"],
            "activeOutputBasket": active_prices["outputBasket"],
            "activeModels": active_prices["activeModels"],
            "activeTierOrder": active_prices["tierOrder"],
            "gpuPrice": gpu["prices"],
            "gpuPriceAnnotations": gpu["annotations"],
            "gpuPremium": gpu["premium"],
            "scarcity": sorted(scarcity, key=lambda r: (r["date"], r["series"])),
            "listedGap": sorted(listed_gap, key=lambda r: (r["date"], r["series"])),
            "breadth": sorted(breadth, key=lambda r: (r["date"], r["series"])),
            "priceChangeCounts": _price_change_counts(active_price_raw, active_prices.get("activeModels") or []),
            "capex": capex,
        },
        "sources": {
            "openrouter": {
                "label": "OpenRouter 公开模型排行榜",
                "url": openrouter_raw["sources"]["openrouter"]["url"],
                "definition": openrouter_raw["method"]["volume"],
            },
            "openrouterComposition": {
                "label": "OpenRouter public weekly named-model composition",
                "url": openrouter_raw["sources"]["openrouter"]["url"],
                "definition": "Each weekly column independently stacks every model disclosed by the public chart plus Others. Segment height is share of that week's total token volume. Columns are not connected, so a model missing from another week is never treated as zero usage.",
            },
            "activePrice": {
                "label": "OpenRouter public weekly rankings + OpenRouter models + OpenRouterList price history",
                "url": active_price_raw["sources"]["history"]["url"],
                "definition": "Weekly named-model token volume is mapped through OpenRouter canonical slugs to OpenRouterList change-point prices. Free models are zero only when explicitly marked :free; Others and unmapped models remain Unknown. Weighted rates describe visible listed-price exposure, not realized spend, because public token volume is not split into input and output.",
            },
            "gpuPrice": {
                "label": "gpurentalprices.com 34 家供应商逐日验证数据集（CC BY 4.0）",
                "url": "https://gpurentalprices.com/data",
                "definition": "34 家供应商逐日验证的整租价格（on-demand/secure/community，剔除 spot/serverless）× 跨供应商中位，含 min–max 区间与 30 日均线；竖线标注供应商数量变化。2026-09-27 起替代 Foundry Signals（口径断点）。",
            },
            "gpuPremium": {
                "label": "由 34 家供应商中位数推导",
                "url": "https://gpurentalprices.com/data",
                "definition": "Rolling 30-day median of H200/H100 and B200/H100 daily rental-price ratios. A value above 1 means a premium to H100.",
            },
            "scarcity": {
                "label": "GPU Finder 市场可用性（gpufinder.dev）",
                "url": "https://gpufinder.dev/api/v1/availability",
                "definition": "Σavailable/Σtotal 全市场可租卡占比（7 天滚动窗口，每日快照向前积累）。连续稀缺度指标，替代 Foundry 的二元可用率。",
            },
            "listedGap": {
                "label": "GPU Finder 报价 vs 在库价差",
                "url": "https://gpufinder.dev/api/v1/snapshot",
                "definition": "最低在库价 ÷ 最低报价 − 1。衡量‘报价虚低程度’：市场越紧，最低报价越可能是没有库存的虚价，该差值越大。",
            },
            "breadth": {
                "label": "GPU Finder 供应商广度",
                "url": "https://gpufinder.dev/api/v1/gpus",
                "definition": "在架供应商数量随时间变化：价格上行+家数增加=供给在响应；价格上行+家数减少=实质性紧缩。",
            },
            "capex": {
                "label": "SEC companyfacts and official company disclosures",
                "definition": "Quarterly and event-frequency observations preserve source units and are not interpolated.",
            },
        },
    }
    snapshot["datasets"].update(ref_datasets)
    snapshot["meta"].update(ref_meta)
    snapshot["meta"]["panelAnnotations"] = ref_meta.get("panelAnnotations") or {}
    snapshot["meta"]["scarcityValidDays"] = len({r["date"] for r in scarcity})
    snapshot["meta"]["gapValidDays"] = len({r["date"] for r in listed_gap})
    # 全局时间轴纪律：任何序列不早于 OpenRouter 用量窗口起点（52 周滚动）
    _or_rows = snapshot["datasets"].get("openrouterVolume") or []
    if _or_rows:
        _or_min = min(str(r.get("date", "")) for r in _or_rows)
        for _key, _rows in list(snapshot["datasets"].items()):
            if (
                isinstance(_rows, list)
                and _rows
                and all(isinstance(r, dict) and "date" in r for r in _rows)
            ):
                _kept = [r for r in _rows if str(r.get("date", "")) >= _or_min]
                if _kept:
                    snapshot["datasets"][_key] = _kept
        snapshot["meta"]["minDate"] = _or_min
    # 订单簿：同一平台当日含多个 GPU 家族行，需按 (日期, 平台) 求和后再成序列，
    # 否则同一日期的多个点会被连线成锯齿（2026-09-27 修复）。
    _ob_agg: dict[tuple[str, str], int] = {}
    for row in (orderbook_raw.get("rows") or []):
        day = row.get("date")
        offers = row.get("offerCount")
        if not day or not isinstance(offers, int):
            continue
        key = (str(day), str(row.get("source", "unknown")))
        _ob_agg[key] = _ob_agg.get(key, 0) + offers
    snapshot["datasets"]["orderbookDepth"] = sorted(
        (
            {"date": day, "series": source, "value": total}
            for (day, source), total in _ob_agg.items()
        ),
        key=lambda r: (r["date"], r["series"]),
    )
    snapshot["sources"].update({
        "basisH100": {"url": "https://gpu-index.semianalysis.com/ | https://index.ornn.com | https://gpurentalprices.com/data", "label": "H100 三源价格对照", "definition": "同一 GPU 家族下三种口径并列：供应商报价中位、综合现货-合约指数、成交加权指数。口径不同，仅作交叉对照，不构成同质序列。"},
        "basisH200": {"url": "https://gpu-index.semianalysis.com/ | https://index.ornn.com | https://gpurentalprices.com/data", "label": "H200 三源价格对照", "definition": "口径同上（H200 无 SemiAnalysis 公开指数，为两源对照）。Neocloud 与 Ornn 可能方向分歧，分歧本身是证据而非噪声。"},
        "basisB200": {"url": "https://gpu-index.semianalysis.com/ | https://index.ornn.com | https://gpurentalprices.com/data", "label": "B200 三源价格对照", "definition": "口径同上。"},
        "contractBand": {"url": "https://gpu-index.semianalysis.com/api/public-data", "label": "SemiAnalysis H100 1Y 合约调查区间", "definition": "月度调查的25-75分位合约价区间，半年期阶梯展示。许可：公开页引用需署名。"},
        "orderbookDepth": {"url": "https://api.gpuindexes.com/api/offers | https://console.vast.ai/api/v0/bundles/ | https://api.runpod.io/graphql", "label": "GPU 订单簿逐源观测", "definition": "gpuperhour/vast 为逐条报价 offers、runpod 为型号挂牌 types，单位语义不同故分序列展示不合并。时点观测，<10 有效日只画点不连线。"},
        "otpi": {"url": "https://index.ornn.com/api/otpi", "label": "Ornn OTPI 已实现 token 价", "definition": "按 lab 的成交加权 token 实现价（USD/Mtok），免费层滚动窗口每日快照累积。许可：Ornn 免费层署名引用。"},
        "top5Share": {"url": "https://openrouter.ai/api/frontend/v1/rankings/model-rankings-chart", "label": "OpenRouter 公开周榜（Top-5 派生）", "definition": "每周公开榜单里最新 Top-5 模型各自的用量占比走势。看的是排名与份额的稳定性：曲线频繁交叉=头部不稳。"},
        "priceChanges": {"url": "https://openrouter.ai/models", "label": "OpenRouter 模型牌价调价点（change-point 账本）", "definition": "头部模型牌价近 4 周被修改的次数（来自我们记录的调价点账本）。高频调价=定价试探/竞争响应，是'价格战'的直接痕迹。"},
        "panelIndex": {"url": "https://gpurentalprices.com/data", "label": "固定供应商面板指数", "definition": "从 34 家供应商数据集取窗口内持续在架成员（覆盖率≥90%），按非中断性租赁价计算成员均值，起点=100；成员当日缺价即断点。消除供应商构成漂移，是供给价格的首选趋势证据。"},
    })
    _pm = snapshot["meta"].get("panelMembers") or {}
    if _pm:
        _member_txt = "；".join(
            f"{gpu}（{len(info.get('members') or [])} 家）：" + "、".join(PROVIDER_DISPLAY.get(m, m) for m in (info.get("members") or []))
            for gpu, info in _pm.items()
        )
        snapshot["sources"]["panelIndex"]["definition"] += " 当前成员：" + _member_txt
    return snapshot


THESIS_PATH = ROOT / "tracker_data" / "thesis_states" / "latest-thesis-state.json"
CLOCK_LABELS = {
    "supply_price": "Supply Price 供给价格",
    "capacity": "Capacity 供给深度",
    "demand_unit_economics": "Demand 需求与单位经济",
    "commitment_monetization": "Commitment 投入与变现",
}
CLOCK_STATE_CLASS = {
    "Unobservable": "st-unobservable",
    "Observing": "st-observing",
    "Trend": "st-trend",
    "Inflection Watch": "st-watch",
    "Confirmed": "st-confirmed",
}


def _clock_key_metric(clock: dict[str, Any]) -> str:
    metrics = clock.get("metrics", {})
    cid = clock.get("clock_id")
    if cid == "supply_price":
        parts = []
        for panel_id, value in sorted((metrics.get("frontierPanels") or {}).items()):
            if value.get("change90dPct") is not None and str(panel_id).split(":")[0] in ("semi", "ornn"):
                sign = "+" if value["change90dPct"] >= 0 else ""
                parts.append(f"{panel_id} 90D {sign}{value['change90dPct']}%")
        return " · ".join(parts[:3]) if parts else "面板变化待积累"
    if cid == "capacity":
        return f"订单簿 {metrics.get('depthValidDates', 0)} 有效日 · 最新 offers {metrics.get('latestTotalOffers')}"
    if cid == "demand_unit_economics":
        return f"{metrics.get('completeWeeks', 0)} 完整周 · 近90日降价模型 {metrics.get('recentPriceCutModels', 0)}"
    return f"{metrics.get('companiesWith3ConsecutiveQuarters', 0)}/{metrics.get('companiesCovered', 0)} 家公司达3连续季度"


def _price_change_counts(active_price_raw: dict[str, Any], active_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """头部模型调价点计数：近 4 周 + 累计（change-point 账本）——定价试探频率的直接证据。"""
    history = ((active_price_raw.get("data") or {}).get("history")) or {}
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=28)).toordinal()
    out = []
    for model in active_models:
        base = str(model.get("baseId") or model.get("rankId") or "")
        entry = history.get(base) or history.get(base.split(":")[0]) or {}
        recent = 0
        for point in entry.get("points") or []:
            try:
                if date.fromisoformat(str(point[0])[:10]).toordinal() >= cutoff:
                    recent += 1
            except Exception:
                continue
        out.append({
            "name": str(model.get("name") or base).split(" (")[0],
            "recent4w": recent,
            "total": int(model.get("historyPoints") or 0),
        })
    return sorted(out, key=lambda r: -r["recent4w"])


def _kpi_html(rows: list[dict[str, Any]], unit: str) -> str:
    """积累期（<10 有效日）用 KPI 卡替代图：大数字 + 进度条，不画坐标轴。"""
    if not rows:
        return ""
    days = len({r["date"] for r in rows})
    latest_day = max(r["date"] for r in rows)
    latest = {r["series"]: r for r in rows if r["date"] == latest_day}
    cards = "".join(
        f'<div class="kpi"><div class="kpi-value">{value}</div><div class="kpi-label">{series}</div></div>'
        for series, row in sorted(latest.items())
        for value in [f"{row['value']:.1f}{unit}"]
    )
    return (
        f'<div class="kpi-row">{cards}</div>'
        f'<div class="kpi-progress"><div class="kpi-bar" style="width:{min(100, days * 10)}%"></div></div>'
        f'<div class="kpi-note">积累中 {days}/10 天——攒够后自动画趋势线（缺口不可回填，每天都在入库）</div>'
    )


def _clocks_section() -> str:
    try:
        report = json.loads(THESIS_PATH.read_text(encoding="utf-8"))
        clocks = report.get("clocks") or []
    except (OSError, json.JSONDecodeError):
        return ""
    if not clocks:
        return ""
    cards = []
    for clock in clocks:
        state = clock.get("state", "Unobservable")
        direction = clock.get("direction")
        badge = state if not direction else f"{state} · {direction}"
        watch = clock.get("watch", {})
        watch_lines = []
        for wname in ("loosening", "intensifying"):
            w = watch.get(wname) or {}
            label = "松动" if wname == "loosening" else "紧缩"
            mark = "✔" if w.get("triggered") else "✘"
            watch_lines.append(f"<b>{label} Watch {mark}</b>")
            for cond in w.get("conditions") or []:
                cond_mark = "✔" if cond.get("met") else "✘"
                evidence = f"（{'、'.join(cond['evidence'])}）" if cond.get("evidence") else ""
                watch_lines.append(f"<span>{cond_mark} {cond.get('condition','')}{evidence}</span>")
        blockers = clock.get("blockers") or []
        detail_items = [
            "<b>确认条件</b>",
            *[f"<span>· {c}</span>" for c in clock.get("confirms", [])],
            "<b>反证条件</b>",
            *[f"<span>· {c}</span>" for c in clock.get("disconfirms", [])],
            *watch_lines,
            "<b>当前阻塞</b>",
            f"<span>{'、'.join(blockers) if blockers else '无'}</span>",
            "<b>数据源</b>",
            "<b>术语</b>",
            "<span>有效日=当天有数据算一天（缺口不回填）；30D/90D 窗口=近 30/90 天变化；Watch=短线触发条件，触发后进 Inflection；Confirmed=长窗口确认；panel=固定供应商价格序列；跨来源去重=同一家族多来源只算一次；proxy=公开榜单等非官方口径</span>",
            f"<span>{'、'.join(clock.get('sources', []))}</span>",
        ]
        cards.append(
            f'<article class="clock-card {CLOCK_STATE_CLASS.get(state, "")}">'
            f'<h4>{CLOCK_LABELS.get(clock.get("clock_id"), clock.get("title", ""))}</h4>'
            f'<div class="clock-state">{badge}</div>'
            f'<p class="clock-metric">{_clock_key_metric(clock)}</p>'
            f'<p class="clock-next">{clock.get("next_proof_point", "")}</p>'
            + (f'<p class="clock-basis">状态依据：{clock.get("stateBasis", "")}</p>' if clock.get("stateBasis") else "")
            + f'<details class="clock-detail"><summary>证据与反证条件</summary>'
            f'<div class="clock-evidence">{"".join(f"<p>{x}</p>" for x in detail_items)}</div>'
            f"</details>"
            f"</article>"
        )
    generated = report.get("generatedAt", "")
    return (
        '<section class="section" id="clocks"><div class="section-head"><h2>四时钟判断状态</h2>'
        f'<span class="section-kicker">自动评估 · {str(generated)[:16].replace("T", " ")} UTC</span></div>'
        f'<div class="grid four">{"".join(cards)}</div></section>'
    )


def _stale_note() -> str:
    try:
        status = json.loads((ROOT / "tracker_data" / "deploy_refresh_status.json").read_text(encoding="utf-8"))
        for row in status.get("sources") or []:
            if row.get("source") == "neocloud_provider_prices" and row.get("status") == "stale_last_good":
                days = row.get("staleDays", "?")
                return (
                    '<div class="stale-note">⚠ 价格数据源上游故障中：本区价格/面板指数为最近一次成功抓取的数据'
                    f'（滞后 {days} 天），上游恢复后自动续更；其余来源正常更新。</div>'
                )
    except Exception:
        pass
    return ""


SOURCE_IMPACT = {
    "openrouter_usage": "需求区：Token 总量 / 组合更替 / 价格层级",
    "openrouter_active_prices": "需求区：Input·Output 组合牌价、单模型调价史",
    "foundry_signals": "交叉验证源（当前上游故障中，暂不影响图表）",
    "sec_capex": "CAPEX 表（季度缓存）",
    "gpu_orderbook": "供给深度图（积累中）",
    "reference_indices": "三源对照图 / 合约带 / OTPI",
    "neocloud_provider_prices": "GPU 价格图 / 代际溢价 / 固定面板指数",
    "epoch_supply": "芯片出货（Capacity 长锚，积累中）",
    "fred_cost_anchors": "CPI 平减与电价锚",
    "gpu_markets_fixings": "Spot/On-demand/Reserved 定盘",
    "throughput_benchmarks": "吞吐基准（单位经济）",
    "gpufinder_market": "市场紧张度三图（稀缺度/虚低度/广度）",
}


def _fresh_badge(snapshot: dict[str, Any]) -> str:
    try:
        status = json.loads((ROOT / "tracker_data" / "deploy_refresh_status.json").read_text(encoding="utf-8"))
        sources = status.get("sources") or []
        total = len(sources)
        healthy = sum(1 for x in sources if x.get("status") in ("fresh", "current_for_frequency"))
        generated = str(status.get("generatedAt", ""))[:16].replace("T", " ")
        tone = "ok" if healthy == total and status.get("publishable") else "warn"
    except Exception:
        return ""

    rows_html = []
    for src in sorted(sources, key=lambda x: (x.get("status") in ("fresh", "current_for_frequency"), str(x.get("source")))):
        name = str(src.get("source"))
        st = str(src.get("status"))
        ready = st in ("fresh", "current_for_frequency")
        dot_cls = "ok" if ready else ("stale" if st == "stale_last_good" else "bad")
        impact = SOURCE_IMPACT.get(name, "")
        note = ""
        if not ready:
            if st == "stale_last_good":
                note = f"（滞后 {src.get('staleDays', '?')} 天，宽限内）"
            elif st == "failed_using_last_good":
                note = "（超期，阻塞发布）"
            elif st == "partial":
                note = "（部分成功）"
            else:
                note = "（失败）"
        rows_html.append(
            f'<div class="fresh-row"><span class="fresh-dot {dot_cls}"></span>'
            f'<b>{name}</b> {st}{note}<span class="fresh-impact">{impact}</span></div>'
        )
    return (
        f'<details class="fresh-details"><summary class="fresh-badge {tone}">'
        f'● 数据更新于 {generated} UTC · {healthy}/{total} 源就绪 ▾</summary>'
        f'<div class="fresh-list">{"".join(rows_html)}</div></details>'
    )


def build_html(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    html_output = HTML.replace("__PAYLOAD__", payload)
    html_output = html_output.replace("__CLOCKS__", _clocks_section())
    html_output = html_output.replace("__FRESH__", _fresh_badge(snapshot))
    html_output = html_output.replace("__STALENOTE__", _stale_note())
    _gf_days = snapshot.get("meta", {}).get("scarcityValidDays", 0)
    _gap_days = snapshot.get("meta", {}).get("gapValidDays", 0)
    if _gf_days < 10:
        html_output = html_output.replace(
            '<div id="scarcity-chart" class="chart compact"></div>',
            _kpi_html(snapshot["datasets"].get("scarcity") or [], "%"),
        )
    if _gap_days < 10:
        html_output = html_output.replace(
            '<div id="gap-chart" class="chart compact"></div>',
            _kpi_html(snapshot["datasets"].get("listedGap") or [], "%"),
        )
    if _gf_days < 10:
        html_output = html_output.replace(
            '<div id="breadth-chart" class="chart compact"></div>',
            _kpi_html(snapshot["datasets"].get("breadth") or [], " 家"),
        )
    return html_output


def main() -> int:
    snapshot = build_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_PATH.write_text(build_html(snapshot), encoding="utf-8")
    print(json.dumps({"html": str(OUTPUT_PATH), "snapshot": str(SNAPSHOT_PATH)}, ensure_ascii=False))
    return 0


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>AI Compute Economics</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta name="description" content="AI Compute Economics——四时钟独立证据链追踪算力经济：GPU 租赁价格、订单簿深度、Token 用量与单位经济、云厂商 CAPEX。">
<style>
:root{--bg:#f5f5f7;--paper:#fff;--ink:#1d1d1f;--muted:#6e6e73;--line:#d2d2d7;--blue:#0071e3;--cyan:#00a6a6;--green:#248a3d;--orange:#d76b00;--red:#d70015;--purple:#8944ab;--radius:8px}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI","Noto Sans SC",sans-serif;letter-spacing:0}.shell{max-width:1440px;margin:auto;padding:0 28px 64px}.topbar{margin:0 -28px;padding:0 28px;border-bottom:1px solid rgba(0,0,0,.08);background:var(--bg)}.topbar-inner{height:52px;display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{font-size:15px;font-weight:650;white-space:nowrap}.nav{display:flex;gap:4px;overflow:auto}.nav a{padding:7px 10px;color:var(--muted);font-size:13px;text-decoration:none;border-radius:6px}.nav a:hover{background:#fff;color:var(--ink)}.hero{padding:42px 0 30px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:42px;line-height:1.12;font-weight:700}.sub{margin:10px 0 0;color:var(--muted);font-size:16px}.controls{display:flex;align-items:end;flex-wrap:wrap;gap:10px;margin-top:24px}.control label{display:block;margin:0 0 5px;color:var(--muted);font-size:11px;font-weight:650;text-transform:uppercase}.control input{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit}.segments{display:flex;padding:3px;border:1px solid var(--line);border-radius:7px;background:#fff}.segments button{height:28px;padding:0 11px;border:0;border-radius:5px;background:transparent;color:var(--muted);font:inherit;font-size:12px;cursor:pointer}.segments button.active{background:var(--ink);color:#fff}.section{padding:34px 0 8px;border-bottom:1px solid var(--line)}.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:20px;margin-bottom:20px}.section h2{margin:0;font-size:25px;line-height:1.2}.section-kicker{color:var(--muted);font-size:12px;text-transform:uppercase}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.panel{min-width:0;padding:20px;border:1px solid rgba(0,0,0,.09);border-radius:var(--radius);background:var(--paper)}.panel.full{grid-column:1/-1}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.panel h3{margin:0;font-size:17px;line-height:1.35}.panel-note{margin:5px 0 0;color:var(--muted);font-size:12px}.chart{position:relative;min-height:330px;margin-top:12px}.chart svg{display:block;width:100%;height:330px;overflow:visible}.legend{display:flex;flex-wrap:wrap;gap:7px 12px;margin-top:10px}.legend button{display:inline-flex;align-items:center;gap:6px;padding:3px 6px;border:0;border-radius:4px;background:transparent;color:var(--muted);font:inherit;font-size:11px;cursor:pointer}.legend button.off{opacity:.32}.swatch{width:16px;height:3px;border-radius:2px}.key-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin-top:12px;border:1px solid #e5e5ea;border-radius:6px;overflow:hidden;background:#e5e5ea}.key-stat{min-width:0;padding:10px 12px;background:#fafafa}.key-stat b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.key-stat span{display:block;margin-top:4px;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}.source{margin-top:12px;padding-top:10px;border-top:1px solid #ececf0;color:var(--muted);font-size:11px}.source summary{cursor:pointer;list-style:none}.source summary::-webkit-details-marker{display:none}.source a{color:var(--blue)}.tooltip{position:absolute;z-index:5;display:none;max-width:300px;padding:9px 11px;border-radius:6px;background:rgba(29,29,31,.95);color:#fff;font-size:11px;line-height:1.5;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.16)}.empty{display:grid;place-items:center;height:300px;color:var(--muted);font-size:13px}.table-wrap{overflow:auto;border-top:1px solid var(--line)}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:10px 12px;border-bottom:1px solid #e8e8ed;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#fafafa;color:var(--muted);font-weight:650}td.num{text-align:right;font-variant-numeric:tabular-nums}.axis{fill:var(--muted);font-size:10px}.axis-title{fill:var(--muted);font-size:10px;font-weight:650}.gridline{stroke:#e5e5ea;stroke-width:1}.footer{padding:24px 0;color:var(--muted);font-size:11px}
.chart.compact{min-height:240px}.chart.compact svg{height:240px}
@media(max-width:820px){.shell{padding:0 16px 48px}.topbar{position:static;margin:0 -16px;padding:0 16px}.nav{display:none}.hero{padding-top:28px}h1{font-size:32px}.grid{grid-template-columns:1fr}.panel.full{grid-column:1}.panel{padding:16px}.chart{min-height:190px}.chart svg{height:190px}.chart.compact svg{height:170px}.axis,.axis-title{font-size:24px}.key-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.section-head{display:block}.section-kicker{display:block;margin-top:5px}}
.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.grid.four{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}@media(max-width:820px){.grid.four{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.grid.four{grid-template-columns:1fr}}.clock-card{padding:16px;border:1px solid rgba(0,0,0,.09);border-radius:var(--radius);background:var(--paper)}.clock-card h4{margin:0;font-size:13px;color:var(--muted);font-weight:650}.clock-state{margin-top:8px;font-size:20px;font-weight:700}.st-observing .clock-state{color:#8e8e93}.st-trend .clock-state{color:#0071e3}.st-watch .clock-state{color:#b25000}.st-confirmed .clock-state{color:#1d7a3d}.clock-metric{margin:8px 0 0;font-size:12px;font-variant-numeric:tabular-nums}.clock-next{margin:6px 0 0;color:var(--muted);font-size:11px}.clock-detail{margin-top:10px;border-top:1px solid #ececf0;padding-top:8px}.clock-detail>summary{cursor:pointer;list-style:none;color:var(--muted);font-size:11px}.clock-detail>summary::-webkit-details-marker{display:none}.clock-detail[open]>summary{color:var(--ink)}.clock-evidence p{margin:4px 0;font-size:11px;line-height:1.5}.clock-evidence p b{display:block;margin-top:6px;color:var(--ink)}
.clock-basis{margin:8px 0 0;padding:6px 10px;background:rgba(0,113,227,.07);border-left:2px solid #0071e3;font-size:11px;line-height:1.6;color:var(--ink)}
.hero-meta{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.fresh-badge{display:inline-flex;align-items:center;padding:5px 10px;border-radius:99px;border:1px solid rgba(0,0,0,.12);font-size:11px;color:var(--muted)}
.fresh-badge.ok{color:#1d7a3d;border-color:rgba(29,122,61,.35)}
.fresh-badge.warn{color:#b25000;border-color:rgba(178,80,0,.35)}
.fresh-details{position:relative;display:inline-block}.fresh-details>summary{cursor:pointer;list-style:none}.fresh-details>summary::-webkit-details-marker{display:none}
.fresh-list{position:absolute;top:110%;left:0;z-index:50;min-width:340px;max-width:480px;padding:10px 12px;background:var(--paper);border:1px solid var(--line);border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.12)}
.fresh-row{padding:5px 0;border-bottom:1px solid #ececf0;font-size:11px;line-height:1.5}.fresh-row:last-child{border-bottom:none}
.fresh-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px}.fresh-dot.ok{background:#248a3d}.fresh-dot.stale{background:#d76b00}.fresh-dot.bad{background:#d70015}
.fresh-impact{display:block;color:var(--muted);margin-left:13px;font-size:10px}
.kpi-row{display:flex;gap:12px;justify-content:space-around;padding:22px 6px 10px}.kpi{text-align:center}.kpi-value{font-size:30px;font-weight:700;line-height:1.1}.kpi-label{font-size:11px;color:var(--muted);margin-top:4px}
.pc-row{display:flex;align-items:center;gap:8px;margin:6px 0}.pc-name{width:118px;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}.pc-barwrap{flex:1;background:#ececf0;height:10px;border-radius:5px}.pc-bar{background:#0071e3;height:10px;border-radius:5px}.pc-count{font-size:10px;width:34px;text-align:right;font-variant-numeric:tabular-nums}
.badge-line{margin:6px 0 2px;font-size:11.5px;font-weight:600;color:#b25000}
.kpi-progress{height:4px;background:#ececf0;border-radius:2px;margin:6px 0 4px}.kpi-bar{height:4px;background:#0071e3;border-radius:2px}.kpi-note{color:var(--muted);font-size:10.5px;line-height:1.5}
.stale-note{margin:0 0 14px;padding:10px 14px;border:1px solid rgba(178,80,0,.35);border-radius:8px;background:rgba(178,80,0,.06);color:#b25000;font-size:12px;line-height:1.6}
.xsync-line{position:absolute;top:0;bottom:34px;width:1px;background:rgba(0,113,227,.45);pointer-events:none;display:none;z-index:2}
@media print{body{background:#fff}.topbar,.controls,.segments,#presets,.nav{display:none!important}.clock-detail>summary{display:none}.panel{break-inside:avoid}}
.fresh-badge{border-color:#3a3a42;color:var(--muted)}}.key-stats{grid-template-columns:repeat(5,minmax(0,1fr))}.subsection-title{grid-column:1/-1;margin:12px 0 0;padding-top:18px;border-top:1px solid var(--line);font-size:15px}.legend-item{display:inline-flex;align-items:center;gap:6px;padding:3px 6px;color:var(--muted);font-size:11px}.swatch.band{height:8px;opacity:.22}.model-detail{grid-column:1/-1;padding:16px 0 0;border-top:1px solid var(--line)}.model-detail>summary{cursor:pointer;list-style:none;font-size:13px;font-weight:650}.model-detail>summary::-webkit-details-marker{display:none}.detail-controls{display:flex;align-items:center;gap:12px;margin:16px 0 0}.detail-select{height:36px;max-width:620px;padding:0 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit}.detail-meta{color:var(--muted);font-size:12px}
@media(max-width:980px){.grid.three{grid-template-columns:1fr}}
@media(max-width:820px){.grid.three{grid-template-columns:1fr}.chart.compact{min-height:190px}.chart.compact svg{height:190px}.detail-controls{align-items:flex-start;flex-direction:column}.detail-select{width:100%;max-width:none}}
@media(max-width:820px){.key-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body><main class="shell">
<header class="topbar"><div class="topbar-inner"><div class="brand">AI Compute Economics</div><nav class="nav"><a href="#demand">需求与模型</a><a href="#compute">GPU</a><a href="#capex">CAPEX</a></nav></div></header>
<section class="hero"><h1>AI Compute Economics</h1><p class="sub">价格、用量与模型结构的时间序列</p><div class="hero-meta">__FRESH__</div><div class="controls"><div class="control"><label>开始日期</label><input id="start" type="date"></div><div class="control"><label>结束日期</label><input id="end" type="date"></div><div class="segments" id="presets"><button data-days="90">3M</button><button data-days="180">6M</button><button data-days="365">1Y</button><button data-days="0" class="active">全部</button></div></div></section>

__CLOCKS__<section class="section" id="demand"><div class="section-head"><h2>需求与活跃模型结构</h2><span class="section-kicker">OpenRouter · 52周</span></div><div class="grid"><article class="panel full" data-source="openrouter"><h3>OpenRouter 模型 Token 总量</h3><p class="panel-note">每周 token 总量与 4 周均线 · 含未具名模型的汇总</p><div id="or-volume" class="chart"></div><div id="or-volume-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="openrouterComposition"><h3>OpenRouter 活跃模型组合更替</h3><p class="panel-note">每周 Top-9 模型的用量占比 · 灰色为未具名模型 · 悬停查看明细</p><div id="or-composition" class="chart"></div><div id="composition-legend" class="legend"></div><div id="composition-badge" class="badge-line"></div><div id="composition-latest" class="key-stats"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="top5Share"><h3>Top-5 模型份额走势</h3><p class="panel-note">最新周 Top-5 模型各自的用量占比 · 末端标模型名 · 与堆叠图配合看"头部换得勤、没人坐稳"</p><div id="top5-share" class="chart"></div><div id="top5-share-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="activePrice"><h3>活跃模型 Output 价格层级迁移</h3><p class="panel-note">按用量加权的输出价格分档 · 灰色=未匹配到价格的用量（近月约占一半，压低了可见迁移幅度）· >$5 档的清零本身是一条结论</p><div id="active-price-tier" class="chart"></div><div id="active-price-tier-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="activePrice"><h3>活跃模型组合 Input 牌价</h3><p class="panel-note">按公开Token量加权 · 美元 / 100万 input tokens · 自 12 月起加权价走平——"降价"主要来自模型组合迁移，不是同款持续降价</p><div id="active-input-basket" class="chart compact"></div><div id="active-input-basket-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="activePrice"><h3>活跃模型组合 Output 牌价</h3><p class="panel-note">按公开Token量加权 · 美元 / 100万 output tokens · 自 12 月起加权价走平——"降价"主要来自模型组合迁移，不是同款持续降价</p><div id="active-output-basket" class="chart compact"></div><div id="active-output-basket-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="otpi"><h3>OTPI 已实现 Token 价（积累中）</h3><p class="panel-note" id="otpi-note">各实验室按实际成交加权的 token 价格 · 免费层 1 个月滚动窗口，每日快照累积</p><div id="otpi-price" class="chart compact"></div><div id="otpi-price-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="priceChanges"><h3>近期活跃模型 · 调价点</h3><p class="panel-note" id="price-change-note">头部模型牌价近 4 周被改了几次——高频调价 = 定价试探与竞争响应</p><div id="price-change-bars"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><details class="model-detail"><summary>查看近期活跃模型与单模型价格历史</summary><div class="detail-controls"><select id="active-model-select" class="detail-select" aria-label="活跃模型"></select><span id="active-model-meta" class="detail-meta"></span></div><div id="active-model-history" class="chart compact"></div><div id="active-model-history-legend" class="legend"></div><div class="table-wrap"><table><thead><tr><th>近期活跃模型</th><th>4周Token</th><th>总量占比</th><th>Input（$/百万）</th><th>Output（$/百万）</th><th>调价点</th></tr></thead><tbody id="active-model-body"></tbody></table></div></details></div></section>

<section class="section" id="compute"><div class="section-head"><h2>GPU市场</h2><span class="section-kicker">多源聚合 · 34 家供应商 · 窗口 ~12 周（2026-09-27 起价格源切换为 gpurentalprices，与更早口径不连续）</span></div>__STALENOTE__<div class="grid three"><article class="panel full" data-source="gpuPrice"><h3>H100 租赁价格</h3><p class="panel-note">上半：中位价走势（y 轴聚焦中位范围）· 下半窄条：P25–P75 价差（市场分化度，越厚越分散）· 均为整租挂牌价，剔除 spot/serverless</p><div id="gpu-price-h100" class="chart compact"></div><div class="legend"><span class="legend-item"><i class="swatch" style="background:#0071e3"></i>中位价</span><span class="legend-item"><i class="swatch" style="background:#1d1d1f"></i>30日均线</span><span class="legend-item"><i class="swatch band" style="background:#0071e3"></i>P25–P75 价差（见下方窄条）</span></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="gpuPrice"><h3>H200 租赁价格</h3><p class="panel-note">上半：中位价走势（y 轴聚焦中位范围）· 下半窄条：P25–P75 价差（市场分化度，越厚越分散）· 均为整租挂牌价，剔除 spot/serverless</p><div id="gpu-price-h200" class="chart compact"></div><div class="legend"><span class="legend-item"><i class="swatch" style="background:#0071e3"></i>中位价</span><span class="legend-item"><i class="swatch" style="background:#1d1d1f"></i>30日均线</span><span class="legend-item"><i class="swatch band" style="background:#0071e3"></i>P25–P75 价差（见下方窄条）</span></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="gpuPrice"><h3>B200 租赁价格</h3><p class="panel-note">上半：中位价走势（y 轴聚焦中位范围）· 下半窄条：P25–P75 价差（市场分化度，越厚越分散）· 均为整租挂牌价，剔除 spot/serverless</p><div id="gpu-price-b200" class="chart compact"></div><div class="legend"><span class="legend-item"><i class="swatch" style="background:#0071e3"></i>中位价</span><span class="legend-item"><i class="swatch" style="background:#1d1d1f"></i>30日均线</span><span class="legend-item"><i class="swatch band" style="background:#0071e3"></i>P25–P75 价差（见下方窄条）</span></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="gpuPremium"><h3>GPU 代际租赁溢价</h3><p class="panel-note">相对H100的30日中位价格倍数 · 1.0x表示无溢价</p><div id="gpu-premium" class="chart"></div><div id="gpu-premium-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><h3 class="subsection-title">跨来源交叉验证 · 报价 × 成交 × 合约</h3><article class="panel" data-source="basisH100"><h3>H100：报价 vs 成交指数</h3><p class="panel-note">Neocloud 挂牌 × SemiAnalysis 综合 × Ornn 成交 · 已截到三源共存窗口、统一起点=100，只看相对变化是否同步</p><div id="basis-h100" class="chart compact"></div><div id="basis-h100-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="basisH200"><h3>H200：报价 vs 成交指数</h3><p class="panel-note">Neocloud 挂牌 × Ornn 成交（SemiAnalysis 无 H200 公开指数）· 起点=100，扇形开口=分歧扩大</p><div id="basis-h200" class="chart compact"></div><div id="basis-h200-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="basisB200"><h3>B200：报价 vs 成交指数</h3><p class="panel-note">Neocloud 挂牌 × SemiAnalysis 综合 × Ornn 成交 · 起点=100，扇形开口=分歧扩大</p><div id="basis-b200" class="chart compact"></div><div id="basis-b200-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="panelIndex"><h3>固定供应商面板指数</h3><p class="panel-note" id="panel-index-note">固定同一批供应商的整租价均值 · 起点=100（灰虚线）· 橙色虚线=成员个体调价造成的台阶 · 有人缺报价当天断开</p><div id="panel-index-chart" class="chart"></div><div id="panel-index-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="contractBand"><h3>H100 一年期合约价区间</h3><p class="panel-note">SemiAnalysis 公开调查区间 · 混合频率（2023 半年→2024 季度→2025-07 起月度）· 阶梯图不与日线混轴</p><div id="contract-band" class="chart compact"></div><div id="contract-band-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><h3 class="subsection-title">市场紧张度 · 供给端（GPU Finder 每日积累）</h3><article class="panel" data-source="scarcity"><h3>市场稀缺度：可租卡占比</h3><p class="panel-note" id="scarcity-note">能租到的卡数 ÷ 在架总卡数 · 越低越紧张 · 每日快照（7 天滚动窗口）</p><div id="scarcity-chart" class="chart compact"></div><div id="scarcity-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="listedGap"><h3>报价虚低度：在库 ÷ 报价</h3><p class="panel-note" id="gap-note">最低在库价 ÷ 最低报价 − 1 · 越紧的型号，挂出来的低价越可能是空头支票</p><div id="gap-chart" class="chart compact"></div><div id="gap-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="breadth"><h3>供应商广度</h3><p class="panel-note" id="breadth-note">在架供应商数 · 涨价时家数还在增，说明供给在跟上</p><div id="breadth-chart" class="chart compact"></div><div id="breadth-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="orderbookDepth"><h3>供给深度：订单簿观测（积累中）</h3><p class="panel-note" id="orderbook-note">三个平台各自的在架报价条数（分开计，不混算）· 少于 10 个有效日只画点</p><div class="grid three"><div><div id="ob-gpuperhour" class="chart compact"></div><div id="ob-gpuperhour-legend" class="legend"></div></div><div><div id="ob-vast" class="chart compact"></div><div id="ob-vast-legend" class="legend"></div></div><div><div id="ob-runpod" class="chart compact"></div><div id="ob-runpod-legend" class="legend"></div></div></div><details class="source"><summary>来源与口径</summary><p></p></details></article></div></section>

<section class="section" id="capex"><div class="section-head"><h2>CAPEX与官方承诺</h2><span class="section-kicker">季度与事件 · 原始频率不插值</span></div><article class="panel full" data-source="capex"><div class="table-wrap"><table><thead><tr><th>日期</th><th>公司</th><th>指标</th><th>期间</th><th>单位</th><th>数值</th></tr></thead><tbody id="capex-body"></tbody></table></div><details class="source"><summary>来源与口径</summary><p></p></details></article></section>
<footer class="footer" id="freshness"></footer></main><script>
const DATA=__PAYLOAD__; const COLORS=['#0071e3','#d76b00','#248a3d','#d70015','#8944ab','#00a6a6','#6e6e73','#af52de','#8e8e93','#5e5ce6'];
const charts=[]; const states={}; const $=s=>document.querySelector(s); const dateNum=s=>new Date(s+'T00:00:00Z').getTime();
function fmt(v,kind){if(kind==='tokens')return v.toFixed(v>=10?1:2)+'T';if(kind==='pct')return v.toFixed(1)+'%';if(kind==='usd')return '$'+(v<1?v.toFixed(3):v.toFixed(2));if(kind==='multiple')return v.toFixed(2)+'x';if(kind==='count')return Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v);if(kind==='index')return v.toFixed(1);return v.toFixed(2)}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function lineChart(id,legendId,rows,opt){const cfg={id,legendId,rows,opt,renderer:renderChart};charts.push(cfg);states[id]=new Set(rows.map(r=>r.series));renderLegend(cfg);cfg.renderer(cfg)}
function renderLegend(c){const names=[...new Set(c.rows.map(r=>r.series))];const host=$('#'+c.legendId);host.innerHTML='';names.forEach((name,i)=>{const color=(c.opt.colors&&c.opt.colors[name])||COLORS[i%COLORS.length],b=document.createElement('button');b.innerHTML=`<span class="swatch" style="background:${color}"></span>${esc(name)}`;b.onclick=()=>{states[c.id].has(name)?states[c.id].delete(name):states[c.id].add(name);b.classList.toggle('off',!states[c.id].has(name));c.renderer(c)};host.appendChild(b)})}
function renderChart(c){
  const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value);
  const visible=c.rows.filter(r=>states[c.id].has(r.series)&&dateNum(r.date)>=start&&dateNum(r.date)<=end);
  if(!visible.length){host.innerHTML='<div class="empty">所选时间内没有可比数据</div>';return}
  const W=1000,H=330,m={l:66,r:20,t:16,b:46},xs=visible.map(r=>dateNum(r.date)),ys=visible.map(r=>+r.value);
  let xmin=Math.min(...xs),xmax=Math.max(...xs);if(xmin===xmax){xmin-=86400000;xmax+=86400000}
  if(Number.isFinite(c.opt.reference))ys.push(c.opt.reference);let ymin=c.opt.zero?0:Math.min(...ys),ymax=Math.max(...ys),pad=(ymax-ymin||1)*.12;
  ymin=c.opt.zero?0:Math.max(0,ymin-pad);ymax+=pad;
  const x=v=>m.l+(v-xmin)/(xmax-xmin)*(W-m.l-m.r),y=v=>H-m.b-(v-ymin)/(ymax-ymin)*(H-m.t-m.b);
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.opt.title)}">`;
  for(let i=0;i<=4;i++){let val=ymin+(ymax-ymin)*i/4,yy=y(val);svg+=`<line class="gridline" x1="${m.l}" y1="${yy}" x2="${W-m.r}" y2="${yy}"/><text class="axis" x="${m.l-9}" y="${yy+3}" text-anchor="end">${esc(fmt(val,c.opt.kind))}</text>`}
  for(let i=0;i<=4;i++){let val=xmin+(xmax-xmin)*i/4,xx=x(val),d=new Date(val);svg+=`<text class="axis" x="${xx}" y="${H-20}" text-anchor="middle">${d.toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}
  svg+=`<text class="axis-title" transform="translate(15 ${H/2}) rotate(-90)" text-anchor="middle">${esc(c.opt.yTitle)}</text>`;
  if(Number.isFinite(c.opt.reference)){const yy=y(c.opt.reference);svg+=`<line x1="${m.l}" y1="${yy}" x2="${W-m.r}" y2="${yy}" stroke="#6e6e73" stroke-width="1.5" stroke-dasharray="6 5"/><text class="axis" x="${W-m.r}" y="${yy-6}" text-anchor="end">${fmt(c.opt.reference,c.opt.kind)}</text>`}
  if(c.opt.annotations){const _flat=Array.isArray(c.opt.annotations)?c.opt.annotations:Object.entries(c.opt.annotations).flatMap(([fam,ls])=>(states[c.id]&&states[c.id].has(fam+' 固定面板'))?ls:[]);_flat.forEach((a,ai)=>{const tv=dateNum(a.date);if(tv<start||tv>end)return;const xx=x(tv);svg+=`<line x1="${xx}" y1="${m.t}" x2="${xx}" y2="${H-m.b}" stroke="#d76b00" stroke-width="1.4" stroke-dasharray="4 4"/><text class="axis" x="${Math.min(xx+4,W-m.r-120)}" y="${m.t+14+((ai%2)*12)}" fill="#d76b00">${esc(a.label)}</text>`})}
  const names=[...new Set(c.rows.map(r=>r.series))];
  names.forEach((name,idx)=>{
    const pts=visible.filter(r=>r.series===name).sort((a,b)=>dateNum(a.date)-dateNum(b.date));let segments=[],segment=[];
    const gapDays=c.opt.gapDays||11;pts.forEach((p,i)=>{if(i&&dateNum(p.date)-dateNum(pts[i-1].date)>gapDays*86400000){if(segment.length)segments.push(segment);segment=[]}segment.push(p)});if(segment.length)segments.push(segment);
    if(c.opt.band){const names=[...(states[c.id]||[])];if(names.length===2){const pick=n=>visible.filter(r=>r.series===n).sort((a,b)=>dateNum(a.date)-dateNum(b.date));const top=pick(names[0]),bot=pick(names[1]).reverse();if(top.length>1&&top.length===bot.length){let d=`M${x(dateNum(top[0].date)).toFixed(1)},${y(+top[0].value).toFixed(1)}`;for(let i=1;i<top.length;i++)d+=` H${x(dateNum(top[i].date)).toFixed(1)} V${y(+top[i].value).toFixed(1)}`;for(const p of bot)d+=` H${x(dateNum(p.date)).toFixed(1)} V${y(+p.value).toFixed(1)}`;svg+=`<path d="${d} Z" fill="${COLORS[0]}" opacity=".13"/>`}}}
  if(c.opt.endLabels){[...states[c.id]].forEach(name=>{const series=visible.filter(r=>r.series===name).sort((a,b)=>dateNum(a.date)-dateNum(b.date));if(!series.length)return;const last=series[series.length-1],lv=+last.value;if(!Number.isFinite(lv))return;const idx=[...states[c.id]].indexOf(name),col=COLORS[idx%COLORS.length];svg+=`<text class="axis" x="${W-m.r-2}" y="${y(lv)-7}" text-anchor="end" fill="${col}" style="font-weight:700">${fmt(lv,c.opt.kind)}</text>`})}
    if(!c.opt.pointOnly)segments.forEach(seg=>{let d=`M${x(dateNum(seg[0].date)).toFixed(1)},${y(+seg[0].value).toFixed(1)}`;for(let i=1;i<seg.length;i++){const xx=x(dateNum(seg[i].date)).toFixed(1),yy=y(+seg[i].value).toFixed(1);d+=c.opt.step?` H${xx} V${yy}`:` L${xx},${yy}`}svg+=`<path d="${d}" fill="none" stroke="${COLORS[idx%COLORS.length]}" stroke-width="${name.includes('average')?3:2}" opacity="${name==='Weekly tokens'?0.42:1}"/>`});
    pts.forEach((p,i)=>{if(!c.opt.step||i===0||i===pts.length-1||+p.value!==+pts[i-1].value)svg+=`<circle cx="${x(dateNum(p.date))}" cy="${y(+p.value)}" r="3" fill="${COLORS[idx%COLORS.length]}" data-date="${p.date}" data-series="${esc(name)}" data-value="${p.value}"/>`})
  });
  svg+=`<rect class="hit" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${H-m.t-m.b}" fill="transparent"/></svg><div class="tooltip"></div>`;host.innerHTML=svg;
  const tip=host.querySelector('.tooltip'),svgEl=host.querySelector('svg');
  svgEl.onpointermove=e=>{const rect=svgEl.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W,target=xmin+(px-m.l)/(W-m.l-m.r)*(xmax-xmin),dates=[...new Set(visible.map(r=>r.date))],nearest=dates.reduce((a,b)=>Math.abs(dateNum(b)-target)<Math.abs(dateNum(a)-target)?b:a),rows=visible.filter(r=>r.date===nearest).sort((a,b)=>b.value-a.value);tip.innerHTML=`<strong>${nearest}</strong><br>`+rows.map(r=>`${esc(r.series)}: ${fmt(+r.value,c.opt.kind)}${Number.isFinite(+r.low)&&Number.isFinite(+r.high)?` · range ${fmt(+r.low,c.opt.kind)}–${fmt(+r.high,c.opt.kind)}`:''}${Number.isFinite(+r.coverage)?` · coverage ${(+r.coverage).toFixed(1)}%`:''}`).join('<br>');tip.style.display='block';tip.style.left=Math.min(e.offsetX+14,host.clientWidth-300)+'px';tip.style.top=Math.max(8,e.offsetY-20)+'px'};
  svgEl.onmouseleave=()=>tip.style.display='none';
  attachSync(c);
}

function attachSync(c){
  const host=$('#'+c.id);const svgEl=host&&host.querySelector('svg');if(!svgEl||svgEl.dataset.synced)return;svgEl.dataset.synced='1';
  svgEl.addEventListener('pointermove',e=>{
    const rect=svgEl.getBoundingClientRect();let frac=(e.clientX-rect.left)/rect.width;frac=Math.max(0,Math.min(1,frac));
    const sec=host.closest('.section');if(!sec)return;
    sec.querySelectorAll('.chart').forEach(ch=>{const s2=ch.querySelector('svg');if(!s2)return;let ln=ch.querySelector('.xsync-line');if(!ln){ln=document.createElement('div');ln.className='xsync-line';ch.appendChild(ln)}ln.style.left=(frac*100)+'%';ln.style.display='block'});
  },true);
  svgEl.addEventListener('pointerleave',()=>{document.querySelectorAll('.xsync-line').forEach(l=>l.style.display='none')});
}

const VENDOR_COLORS={anthropic:'#d76b00',deepseek:'#0071e3',google:'#248a3d',openai:'#1d1d1f','x-ai':'#1d1d1f',qwen:'#5e5ce6',minimax:'#d70015',xiaomi:'#00a6a6',tencent:'#30b0c7',moonshotai:'#8944ab',stepfun:'#bf5af2',nvidia:'#8e8e93','z-ai':'#af52de',OpenRouter:'#b8b8bd'};
function compositionChart(id,rows){const cfg={id,rows,renderer:renderComposition};charts.push(cfg);cfg.renderer(cfg);const vendors=[...new Set(rows.map(r=>r.vendor))];$('#composition-legend').innerHTML=vendors.map(v=>`<span class="legend-item"><i class="swatch" style="background:${VENDOR_COLORS[v]||'#8e8e93'}"></i>${esc(v==='OpenRouter'?'Others':v)}</span>`).join('')}
function renderComposition(c){
  const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value),visible=c.rows.filter(r=>dateNum(r.date)>=start&&dateNum(r.date)<=end),dates=[...new Set(visible.map(r=>r.date))].sort();
  if(!dates.length){host.innerHTML='<div class="empty">所选时间内没有活跃模型组合数据</div>';$('#composition-latest').innerHTML='';return}
  const W=1000,H=350,m={l:58,r:18,t:18,b:48},pw=W-m.l-m.r,ph=H-m.t-m.b,step=pw/dates.length,bw=Math.max(2,step*.82),y=v=>m.t+(100-v)/100*ph;
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="OpenRouter weekly active model composition">`;
  [0,25,50,75,100].forEach(v=>svg+=`<line class="gridline" x1="${m.l}" y1="${y(v)}" x2="${W-m.r}" y2="${y(v)}"/><text class="axis" x="${m.l-8}" y="${y(v)+3}" text-anchor="end">${v}%</text>`);
  dates.forEach((d,i)=>{let cumulative=0;const rows=visible.filter(r=>r.date===d).sort((a,b)=>a.rank-b.rank);rows.forEach(r=>{const bottom=cumulative,top=cumulative+r.share,xx=m.l+step*(i+.5)-bw/2,yy=y(top),height=y(bottom)-yy,color=VENDOR_COLORS[r.vendor]||'#8e8e93';svg+=`<rect x="${xx}" y="${yy}" width="${bw}" height="${Math.max(.5,height)}" fill="${color}" stroke="#fff" stroke-width=".35" data-date="${r.date}" data-rank="${r.rank}" data-model="${esc(r.model)}" data-vendor="${esc(r.vendor)}" data-share="${r.share}" data-tokens="${r.tokens}"/>`;cumulative=top})});
  for(let i=0;i<=4;i++){const idx=Math.round((dates.length-1)*i/4),xx=m.l+step*(idx+.5);svg+=`<text class="axis" x="${xx}" y="${H-20}" text-anchor="middle">${new Date(dateNum(dates[idx])).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}
  svg+='</svg><div class="tooltip"></div>';host.innerHTML=svg;const tip=host.querySelector('.tooltip');host.querySelectorAll('rect[data-model]').forEach(el=>{el.onmouseenter=e=>{const label=el.dataset.model==='Others'?'Others · 未逐模型披露':`Top ${el.dataset.rank} · ${el.dataset.model}`;tip.innerHTML=`<strong>${el.dataset.date}</strong><br>${esc(label)}<br>${(+el.dataset.share).toFixed(1)}% · ${(+el.dataset.tokens).toFixed(2)}T tokens`;tip.style.display='block';tip.style.left=Math.min(e.offsetX+12,host.clientWidth-310)+'px';tip.style.top=Math.max(8,e.offsetY-10)+'px'};el.onmouseleave=()=>tip.style.display='none'});
  const latest=dates[dates.length-1],current=visible.filter(r=>r.date===latest).sort((a,b)=>a.rank-b.rank);$('#composition-latest').innerHTML=current.map(r=>`<div class="key-stat"><b title="${esc(r.model)}">${r.model==='Others'?'Others':`Top ${r.rank} · ${esc(r.model)}`}</b><span>${r.share.toFixed(1)}% · ${r.tokens.toFixed(2)}T</span></div>`).join('');
}
function stackedAreaChart(id,legendId,rows,opt){const cfg={id,legendId,rows,opt,renderer:renderStackedArea};charts.push(cfg);states[id]=new Set(rows.map(r=>r.series));renderLegend(cfg);cfg.renderer(cfg)}
function renderStackedArea(c){const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value);const dates=[...new Set(c.rows.map(r=>r.date).filter(d=>dateNum(d)>=start&&dateNum(d)<=end))].sort();if(!dates.length){host.innerHTML='<div class="empty">所选时间内没有可比数据</div>';return}const names=[...new Set(c.rows.map(r=>r.series))],lookup=new Map(c.rows.map(r=>[r.date+'|'+r.series,+r.value]));const W=1000,H=330,m={l:58,r:18,t:16,b:46},xmin=dateNum(dates[0]),xmax=dateNum(dates[dates.length-1]),x=v=>m.l+(v-xmin)/(xmax-xmin||1)*(W-m.l-m.r),y=v=>H-m.b-v/100*(H-m.t-m.b);let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.opt.title)}">`;[0,25,50,75,100].forEach(v=>{svg+=`<line class="gridline" x1="${m.l}" y1="${y(v)}" x2="${W-m.r}" y2="${y(v)}"/><text class="axis" x="${m.l-8}" y="${y(v)+3}" text-anchor="end">${v}%</text>`});for(let i=0;i<=4;i++){const idx=Math.round((dates.length-1)*i/4),d=dates[idx],xx=x(dateNum(d));svg+=`<text class="axis" x="${xx}" y="${H-20}" text-anchor="middle">${new Date(dateNum(d)).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}let cumulative=Object.fromEntries(dates.map(d=>[d,0]));names.forEach((name,idx)=>{const lower=dates.map(d=>cumulative[d]),upper=dates.map((d,i)=>{const v=lookup.get(d+'|'+name)||0;cumulative[d]+=v;return lower[i]+v});const top=dates.map((d,i)=>`${i?'L':'M'}${x(dateNum(d)).toFixed(1)},${y(upper[i]).toFixed(1)}`).join(' '),bottom=dates.slice().reverse().map((d,j)=>`L${x(dateNum(d)).toFixed(1)},${y(lower[dates.length-1-j]).toFixed(1)}`).join(' '),color=(c.opt.colors&&c.opt.colors[name])||COLORS[idx%COLORS.length];svg+=`<path d="${top} ${bottom} Z" fill="${color}" fill-opacity="${states[c.id].has(name)?0.82:0.04}" stroke="white" stroke-width="0.7"/>`});svg+=`<rect class="hit" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${H-m.t-m.b}" fill="transparent"/></svg><div class="tooltip"></div>`;host.innerHTML=svg;const tip=host.querySelector('.tooltip'),svgEl=host.querySelector('svg');svgEl.onpointermove=e=>{const rect=svgEl.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W,target=xmin+(px-m.l)/(W-m.l-m.r)*(xmax-xmin),nearest=dates.reduce((a,b)=>Math.abs(dateNum(b)-target)<Math.abs(dateNum(a)-target)?b:a),items=names.filter(n=>states[c.id].has(n)).map(n=>({name:n,value:lookup.get(nearest+'|'+n)||0})).sort((a,b)=>b.value-a.value);tip.innerHTML=`<strong>${nearest}</strong><br>`+items.map(r=>`${esc(r.name)}: ${r.value.toFixed(1)}%`).join('<br>');tip.style.display='block';tip.style.left=Math.min(e.offsetX+14,host.clientWidth-260)+'px';tip.style.top=Math.max(8,e.offsetY-20)+'px'};svgEl.onmouseleave=()=>tip.style.display='none'}
function barTimeChart(id,rows,opt){const cfg={id,rows,opt,renderer:renderBarTime};charts.push(cfg);cfg.renderer(cfg)}
function renderBarTime(c){const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value),rows=c.rows.filter(r=>dateNum(r.date)>=start&&dateNum(r.date)<=end).sort((a,b)=>dateNum(a.date)-dateNum(b.date));if(!rows.length){host.innerHTML='<div class="empty">所选时间内没有数据</div>';return}const W=1000,H=240,m={l:58,r:18,t:16,b:42},xmin=dateNum(rows[0].date),xmax=dateNum(rows[rows.length-1].date),step=(W-m.l-m.r)/rows.length,bw=Math.max(5,step*.62),y=v=>H-m.b-v/100*(H-m.t-m.b);let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.opt.title)}">`;[0,25,50,75,100].forEach(v=>svg+=`<line class="gridline" x1="${m.l}" y1="${y(v)}" x2="${W-m.r}" y2="${y(v)}"/><text class="axis" x="${m.l-8}" y="${y(v)+3}" text-anchor="end">${v}%</text>`);rows.forEach((r,i)=>{const xx=m.l+step*(i+.5);svg+=`<rect x="${xx-bw/2}" y="${y(+r.value)}" width="${bw}" height="${y(0)-y(+r.value)}" rx="2" fill="${+r.value>=35?'#0071e3':'#c7c7cc'}" data-date="${r.date}" data-value="${r.value}"/>`});svg+=`<line x1="${m.l}" y1="${y(35)}" x2="${W-m.r}" y2="${y(35)}" stroke="#d76b00" stroke-width="2" stroke-dasharray="6 5"/><text class="axis" x="${W-m.r}" y="${y(35)-6}" text-anchor="end">35% display threshold</text>`;for(let i=0;i<=4;i++){const idx=Math.round((rows.length-1)*i/4),r=rows[idx],xx=m.l+step*(idx+.5);svg+=`<text class="axis" x="${xx}" y="${H-17}" text-anchor="middle">${new Date(dateNum(r.date)).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}svg+='</svg><div class="tooltip"></div>';host.innerHTML=svg;const tip=host.querySelector('.tooltip');host.querySelectorAll('rect[data-date]').forEach(el=>{el.onmouseenter=e=>{tip.innerHTML=`<strong>${el.dataset.date}</strong><br>Price coverage: ${(+el.dataset.value).toFixed(1)}%`;tip.style.display='block';tip.style.left=Math.min(e.offsetX+12,host.clientWidth-220)+'px';tip.style.top='18px'};el.onmouseleave=()=>tip.style.display='none'})}
function rangeChart(id,rows,annotations){const cfg={id,rows,annotations,renderer:renderRangeChart};charts.push(cfg);cfg.renderer(cfg)}
function renderRangeChart(c){
  // 两层设计：上层=中位价趋势（y轴只按中位/均线范围缩放，趋势可见）；
  // 下层=窄条显示 P25-P75 价差随时间（市场分化度）。全距与供应商数进悬停提示。
  const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value),rows=c.rows.filter(r=>dateNum(r.date)>=start&&dateNum(r.date)<=end).sort((a,b)=>dateNum(a.date)-dateNum(b.date));
  if(!rows.length){host.innerHTML='<div class="empty">所选时间内没有价格数据</div>';return}
  const W=1000,H=420,m={l:76,r:18,t:26,b:30},mainH=280,stripTop=330,stripH=56;
  const xmin=dateNum(rows[0].date),xmax=dateNum(rows[rows.length-1].date);
  const mainVals=rows.flatMap(r=>[+r.value,+r.movingAverage30d]).filter(Number.isFinite);
  const rawMin=Math.min(...mainVals),rawMax=Math.max(...mainVals),pad=(rawMax-rawMin||1)*0.25;
  const ymin=rawMin-pad,ymax=rawMax+pad;
  const spread=rows.map(r=>({date:r.date,w:Math.max(0,(+r.p75)-(+r.p25))}));
  const smax=Math.max(...spread.map(s=>s.w))*1.2||1;
  const x=v=>m.l+(v-xmin)/(xmax-xmin||1)*(W-m.l-m.r);
  const y=v=>m.t+mainH-(v-ymin)/(ymax-ymin||1)*mainH;
  const ys=v=>stripTop+stripH-(v/smax)*stripH;
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="GPU median price trend and spread">`;
  for(let i=0;i<=3;i++){const v=ymin+(ymax-ymin)*i/3,yy=y(v);svg+=`<line class="gridline" x1="${m.l}" y1="${yy}" x2="${W-m.r}" y2="${yy}"/><text class="axis" x="${m.l-8}" y="${yy+3}" text-anchor="end">${fmt(v,'usd')}</text>`}
  for(let i=0;i<=4;i++){const d=xmin+(xmax-xmin)*i/4,xx=x(d);svg+=`<text class="axis" x="${xx}" y="${H-6}" text-anchor="middle">${new Date(d).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}
  const medianPath=rows.map((r,i)=>`${i?'L':'M'}${x(dateNum(r.date)).toFixed(1)},${y(+r.value).toFixed(1)}`).join(' ');
  const averagePath=rows.map((r,i)=>`${i?'L':'M'}${x(dateNum(r.date)).toFixed(1)},${y(+r.movingAverage30d).toFixed(1)}`).join(' ');
  svg+=`<path d="${medianPath}" fill="none" stroke="#0071e3" stroke-width="1.4" opacity=".55"/><path d="${averagePath}" fill="none" stroke="#1d1d1f" stroke-width="3"/>`;
  const spTop=spread.map((r,i)=>`${i?'L':'M'}${x(dateNum(r.date)).toFixed(1)},${ys(r.w).toFixed(1)}`).join(' ');
  const spBot=spread.slice().reverse().map(r=>`L${x(dateNum(r.date)).toFixed(1)},${(stripTop+stripH).toFixed(1)}`).join(' ');
  svg+=`<line class="gridline" x1="${m.l}" y1="${stripTop+stripH}" x2="${W-m.r}" y2="${stripTop+stripH}"/>`;
  svg+=`<path d="${spTop} ${spBot} Z" fill="#0071e3" fill-opacity=".12"/>`;
  svg+=`<text class="axis" x="${m.l-8}" y="${stripTop+16}" text-anchor="end">价差</text><text class="axis" x="${m.l-8}" y="${stripTop+30}" text-anchor="end">${fmt(smax/1.2,'usd')}</text>`;
  const last=rows[rows.length-1];
  svg+=`<text class="axis" x="${W-m.r-2}" y="${y(+last.value)-8}" text-anchor="end" fill="#0071e3" style="font-weight:700">${fmt(+last.value,'usd')}</text>`;
  const lastSpread=spread[spread.length-1];
  svg+=`<text class="axis" x="${m.l}" y="${stripTop-8}" fill="#8e8e93">P25–P75 价差（市场分化度）</text>`;
  svg+=`<text class="axis" x="${W-m.r-2}" y="${ys(lastSpread.w)-6}" text-anchor="end" fill="#8e8e93" style="font-weight:700">${fmt(lastSpread.w,'usd')}</text>`;
  svg+=`<rect class="hit" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${H-m.t-m.b}" fill="transparent"/></svg><div class="tooltip"></div>`;
  host.innerHTML=svg;
  const tip=host.querySelector('.tooltip'),svgEl=host.querySelector('svg');
  svgEl.onpointermove=e=>{const rect=svgEl.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W,target=xmin+(px-m.l)/(W-m.l-m.r)*(xmax-xmin),nearest=rows.reduce((a,b)=>Math.abs(dateNum(b.date)-target)<Math.abs(dateNum(a.date)-target)?b:a);
    tip.innerHTML=`<strong>${nearest.date}</strong><br>中位价 ${fmt(+nearest.value,'usd')}<br>P25–P75 ${fmt(+nearest.p25,'usd')}–${fmt(+nearest.p75,'usd')}<br>全距 ${fmt(+nearest.low,'usd')}–${fmt(+nearest.high,'usd')}<br>30日均线 ${fmt(+nearest.movingAverage30d,'usd')}<br>${nearest.providerCount} providers`;
    tip.style.display='block';tip.style.left=Math.min(e.offsetX+14,host.clientWidth-285)+'px';tip.style.top=Math.max(8,e.offsetY-20)+'px'};
  svgEl.onmouseleave=()=>tip.style.display='none'
}
function activeModelDetail(){
  const models=DATA.datasets.activeModels,select=$('#active-model-select'),body=$('#active-model-body');select.innerHTML=models.map((m,i)=>`<option value="${i}">${esc(m.name)}</option>`).join('');
select.value=String(models.reduce((bi,m,i)=>((m.historyPoints||0)>(models[bi].historyPoints||0)?i:bi),0));body.innerHTML=models.map(m=>`<tr><td>${esc(m.name)}</td><td class="num">${m.tokens.toFixed(2)}T</td><td class="num">${m.share.toFixed(1)}%</td><td class="num">${m.inputPrice==null?'n/a':fmt(+m.inputPrice,'usd')}</td><td class="num">${m.outputPrice==null?'n/a':fmt(+m.outputPrice,'usd')}</td><td class="num">${m.historyPoints}</td></tr>`).join('');
  const cfg={id:'active-model-history',legendId:'active-model-history-legend',rows:[],opt:{title:'Active model price history',kind:'usd',yTitle:'USD / 1M tokens',zero:true,step:true},renderer:renderChart};charts.push(cfg);
  function choose(){const model=models[+select.value],rows=[];(model.priceHistory||[]).forEach(p=>{if(p.input!=null)rows.push({date:p.date,series:'Input',value:p.input});if(p.output!=null)rows.push({date:p.date,series:'Output',value:p.output})});cfg.rows=rows;states[cfg.id]=new Set(rows.map(r=>r.series));renderLegend(cfg);$('#active-model-meta').textContent=`4周 ${model.tokens.toFixed(2)}T · 占总量 ${model.share.toFixed(1)}% · ${model.historyPoints} 个调价点`;cfg.renderer(cfg)}select.onchange=choose;choose()
}
function sourceDetails(){document.querySelectorAll('[data-source]').forEach(el=>{const s=DATA.sources[el.dataset.source],p=el.querySelector('.source p');if(!s||!p)return;p.innerHTML=`<strong>${esc(s.label)}</strong><br>${esc(s.definition)}${s.url?`<br><a href="${esc(s.url)}">打开原始来源</a>`:''}`})}
function renderTable(){const body=$('#capex-body');body.innerHTML=DATA.datasets.capex.map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.company)}</td><td>${esc(r.metricLabel||r.metric)}</td><td>${esc(r.periodLabel||r.period||'')}</td><td>${esc(r.unitLabel||r.unit)}</td><td class="num">${esc(r.valueDisplay!=null?r.valueDisplay:r.value)}</td></tr>`).join('')}
function redraw(){charts.forEach(c=>c.renderer(c))}function preset(days,btn){document.querySelectorAll('#presets button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');const max=dateNum(DATA.meta.maxDate),min=days?Math.max(dateNum(DATA.meta.minDate),max-days*86400000):dateNum(DATA.meta.minDate);$('#start').value=new Date(min).toISOString().slice(0,10);$('#end').value=DATA.meta.maxDate;redraw()}
function syncUrl(){const p=new URLSearchParams();p.set('start',$('#start').value);p.set('end',$('#end').value);history.replaceState(null,'',location.pathname+'?'+p.toString())}
const _preset=preset;
$('#start').value=DATA.meta.minDate;$('#end').value=DATA.meta.maxDate;
(function(){const q=new URLSearchParams(location.search),st=q.get('start'),en=q.get('end'),rg=q.get('range');
if(st&&/^\d{4}-\d{2}-\d{2}$/.test(st))$('#start').value=st;
if(en&&/^\d{4}-\d{2}-\d{2}$/.test(en))$('#end').value=en;})();
$('#start').onchange=()=>{syncUrl();redraw()};$('#end').onchange=()=>{syncUrl();redraw()};
preset=function(days,btn){_preset(days,btn);syncUrl();const p=new URLSearchParams(location.search);if(days)p.set('range',days);history.replaceState(null,'',location.pathname+'?'+p.toString())};
document.querySelectorAll('#presets button').forEach(b=>b.onclick=()=>preset(+b.dataset.days,b));
(function(){const rg=new URLSearchParams(location.search).get('range');if(rg){const btn=document.querySelector('#presets button[data-days="'+rg+'"]');if(btn)preset(+rg,btn)}})();
window.addEventListener('beforeprint',()=>document.querySelectorAll('.clock-detail').forEach(d=>d.open=true));
lineChart('or-volume','or-volume-legend',DATA.datasets.openrouterVolume,{title:'OpenRouter token volume',kind:'tokens',yTitle:'Trillion tokens',zero:true,endLabels:true});
compositionChart('or-composition',DATA.datasets.openrouterComposition);
const TIER_COLORS={'免费':'#248a3d','<$1':'#0071e3','$1–5':'#00a6a6','>$5':'#d76b00','Others / 无法匹配':'#8e8e93'};
stackedAreaChart('active-price-tier','active-price-tier-legend',DATA.datasets.activePriceTiers,{title:'Active model output price tiers',colors:TIER_COLORS});
lineChart('active-input-basket','active-input-basket-legend',DATA.datasets.activeInputBasket,{title:'Active model input basket listed rate',kind:'usd',yTitle:'USD / 1M input',zero:true});
lineChart('active-output-basket','active-output-basket-legend',DATA.datasets.activeOutputBasket,{title:'Active model output basket listed rate',kind:'usd',yTitle:'USD / 1M output',zero:true});
['H100','H200','B200'].forEach(g=>rangeChart('gpu-price-'+g.toLowerCase(),DATA.datasets.gpuPrice.filter(r=>r.series===g),DATA.datasets.gpuPriceAnnotations[g]));
lineChart('gpu-premium','gpu-premium-legend',DATA.datasets.gpuPremium,{title:'GPU generation rental premium',kind:'multiple',yTitle:'Price ratio to H100',zero:false,reference:1,endLabels:true});
const _sd=DATA.meta.scarcityValidDays||0,_gd=DATA.meta.gapValidDays||0;
document.getElementById('scarcity-note').textContent=`能租到的卡数 ÷ 在架总卡数 · 已积累 ${_sd}/10 天${_sd>=10?'，已连线':'，先画观测点'}`;
if(document.getElementById('scarcity-chart'))lineChart('scarcity-chart','scarcity-legend',DATA.datasets.scarcity||[],{title:'Market availability pct',kind:'pct',yTitle:'% available',zero:true,gapDays:3,pointOnly:_sd<10});
document.getElementById('gap-note').textContent=`最低在库价 ÷ 最低报价 − 1 · 已积累 ${_gd}/10 天${_gd>=10?'，已连线':'，先画观测点'}`;
if(document.getElementById('gap-chart'))lineChart('gap-chart','gap-legend',DATA.datasets.listedGap||[],{title:'Listed vs in-stock gap',kind:'pct',yTitle:'Gap %',zero:false,gapDays:3,pointOnly:_gd<10});
if(document.getElementById('breadth-chart'))lineChart('breadth-chart','breadth-legend',DATA.datasets.breadth||[],{title:'Provider breadth',kind:'count',yTitle:'Providers',zero:false,gapDays:3,pointOnly:_gd<10});

const orderbookRows=DATA.datasets.orderbookDepth||[];
const obDays=DATA.meta&&DATA.meta.orderbookValidDays?DATA.meta.orderbookValidDays:0;
document.getElementById('orderbook-note').textContent=`三个平台各自的在架报价条数（分开计，不混算）· 已积累 ${obDays} 天${obDays>=10?'，已画趋势线':'，先画点'}`;
[['ob-gpuperhour','gpuperhour'],['ob-vast','vast'],['ob-runpod','runpod']].forEach(([cid,src])=>{if(document.getElementById(cid))lineChart(cid,cid+'-legend',orderbookRows.filter(r=>r.series===src),{title:src+' offers',kind:'count',yTitle:'报价条数',zero:true,gapDays:3,pointOnly:obDays<10})});
const otpiDays=DATA.meta&&DATA.meta.otpiValidDays?DATA.meta.otpiValidDays:0;
document.getElementById('otpi-note').textContent=`各实验室按实际成交加权的 token 价格 · 已积累 ${otpiDays} 天${otpiDays>=10?'，已画趋势线':'，先画点'}`;
lineChart('otpi-price','otpi-price-legend',DATA.datasets.otpi||[],{title:'Ornn OTPI realized token price',kind:'usd',yTitle:'USD/Mtok',zero:true,pointOnly:otpiDays<10,annotations:[{date:'2026-09-17',label:'openai 单日尖峰 · 大单/口径变化待查'}],endLabels:true});
lineChart('basis-h100','basis-h100-legend',DATA.datasets.basisH100||[],{title:'H100 price basis compare',kind:'index',yTitle:'相对变化（起点=100）',zero:false,gapDays:20,endLabels:true});
lineChart('basis-h200','basis-h200-legend',DATA.datasets.basisH200||[],{title:'H200 price basis compare',kind:'index',yTitle:'相对变化（起点=100）',zero:false,gapDays:20,endLabels:true});
lineChart('basis-b200','basis-b200-legend',DATA.datasets.basisB200||[],{title:'B200 price basis compare',kind:'index',yTitle:'相对变化（起点=100）',zero:false,gapDays:20,endLabels:true});
lineChart('contract-band','contract-band-legend',DATA.datasets.contractBand||[],{title:'H100 1Y contract range',kind:'usd',yTitle:'USD/GPU-hr',zero:true,step:true,band:true,endLabels:true});

const panelRows=DATA.datasets.panelIndex||[];
(()=>{const pm=DATA.meta.panelMembers||{};const counts=Object.entries(pm).map(([g,m])=>{const arr=Array.isArray(m)?m:(m&&m.members)||[];return g+' '+arr.length+'家'}).join(' / ');document.getElementById('panel-index-note').textContent='非中断性租赁价 · 固定成员均值（'+counts+'）· 起点=100 · 成员明细见来源与口径'})();
lineChart('panel-index-chart','panel-index-legend',panelRows,{title:'Fixed-provider panel index',kind:'index',yTitle:'Index (base=100)',zero:false,gapDays:11,reference:100,annotations:DATA.meta.panelAnnotations});
(()=>{['basisH100','basisH200','basisB200'].forEach(k=>{const rows=DATA.datasets[k]||[];const names=[...new Set(rows.map(r=>r.series))];const lasts={};names.forEach(n=>{const rs=rows.filter(r=>r.series===n).sort((a,b)=>a.date<b.date?-1:1);if(rs.length)lasts[n]=rs[rs.length-1].value});const vals=Object.values(lasts);if(vals.length>=2){const div=Math.max(...vals)-Math.min(...vals);const label=Object.entries(lasts).map(([n,v])=>n.replace(' 报价中位','').replace(' 成交指数','').replace(' 综合指数','')+' '+v.toFixed(0)).join(' / ');const art=document.querySelector(`article[data-source="${k}"] .panel-note`);if(art)art.textContent+=' · 终值 '+label+'，分歧 '+div.toFixed(0)+' pct'}})})();
(()=>{const pc=DATA.datasets.priceChangeCounts||[];const maxRecent=Math.max(1,...pc.map(r=>r.recent4w));document.getElementById('price-change-bars').innerHTML=pc.slice(0,8).map(r=>`<div class="pc-row"><span class="pc-name">${esc(r.name)}</span><div class="pc-barwrap"><div class="pc-bar" style="width:${Math.max(2,100*r.recent4w/maxRecent)}%"></div></div><span class="pc-count">${r.recent4w}次</span></div>`).join('')||'<div class="empty">暂无</div>';const top3=pc.slice(0,3).map(r=>r.total).join('/');const sum=document.querySelector('.model-detail>summary');if(sum&&top3)sum.textContent=`头部模型近 4 周调价 ${pc.slice(0,3).map(r=>r.recent4w).join('/')} 次（全历史 ${top3} 次）——点开看单模型价格史`})();
(()=>{{const comp=DATA.datasets.openrouterComposition||[];const weeks=[...new Set(comp.map(r=>r.date))].sort();let changes=0,lastTop="";weeks.forEach((w,i)=>{const rows=comp.filter(r=>r.date===w&&r.model!=="Others").sort((a,b)=>b.share-a.share);const top=rows[0];if(top&&lastTop&&top.model!==lastTop)changes++;if(top)lastTop=top.model;if(i===weeks.length-1){const hhi=rows.reduce((sum,r)=>sum+Math.pow(r.share/100,2),0)*10000;const el=document.getElementById("composition-badge");if(el)el.textContent=`${weeks.length} 周里 Top1 已更换 ${changes} 次 · 最新周 HHI 集中度 ${hhi.toFixed(0)}`}});const latestWeek=weeks[weeks.length-1];const top5=comp.filter(r=>r.date===latestWeek&&r.model!=="Others").sort((a,b)=>b.share-a.share).slice(0,5).map(r=>r.model);const rows5=comp.filter(r=>top5.includes(r.model)).map(r=>({date:r.date,series:(r.model.split("/")[1]||r.model).slice(0,18),value:r.share}));if(document.getElementById("top5-share")&&rows5.length)lineChart("top5-share","top5-share-legend",rows5,{title:"Top-5 share",kind:"pct",yTitle:"用量占比 %",zero:true,gapDays:21,endLabels:true})};})();
activeModelDetail();sourceDetails();renderTable();$('#freshness').textContent='更新于 '+DATA.meta.generatedAt.slice(0,16).replace('T',' ')+' UTC · 仅公开来源数据 · 不含综合评分';
</script></body></html>'''


if __name__ == "__main__":
    raise SystemExit(main())
