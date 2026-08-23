#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the time-axis-first AI compute economics dashboard."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COST_INDEX_PATH = ROOT / "tracker_data" / "backfills" / "openrouter_cost_index.json"
FOUNDRY_HISTORY_PATH = ROOT / "tracker_data" / "backfills" / "foundry_signals_gpu_history.json"
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


def _reference_extract(reference_raw: dict[str, Any], orderbook_raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
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
    foundry_prices = []
    try:
        import json as _json
        foundry_prices = _json.loads(FOUNDRY_HISTORY_PATH.read_text(encoding="utf-8"))["datasets"]["prices"]
    except Exception:
        foundry_prices = []
    for row in foundry_prices:
        family = str(row.get("series", ""))
        if family in basis_rows and isinstance(row.get("value"), (int, float)):
            basis_rows[family].append({
                "date": row["date"],
                "series": "Foundry 报价中位",
                "value": round(float(row["value"]), 4),
            })
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

    return (
        {
            "basisH100": sorted(basis_rows["H100"], key=lambda r: (r["date"], r["series"])),
            "basisH200": sorted(basis_rows["H200"], key=lambda r: (r["date"], r["series"])),
            "basisB200": sorted(basis_rows["B200"], key=lambda r: (r["date"], r["series"])),
            "contractBand": sorted(contract, key=lambda r: r["date"]),
            "otpi": sorted(otpi, key=lambda r: (r["date"], r["series"])),
        },
        {
            "orderbookValidDays": _valid_days(orderbook_raw.get("rows") or []),
            "otpiValidDays": _valid_days(otpi),
            "contractPeriods": len({row["date"] for row in contract}),
        },
    )


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
    capex_raw = json.loads(CAPEX_HISTORY_PATH.read_text(encoding="utf-8"))
    openrouter = _openrouter_extract(_openrouter_rows(openrouter_raw))
    active_prices = _active_model_price_extract(openrouter["raw"], active_price_raw)

    gpu = _gpu_extract(foundry_raw)
    capex = sorted(capex_raw.get("rows") or [], key=lambda row: (row["date"], row["company"]), reverse=True)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    dated_rows = (
        openrouter["volume"] + openrouter["composition"]
        + gpu["prices"] + gpu["availability"] + active_prices["tiers"]
    )
    ref_datasets, ref_meta = _reference_extract(reference_raw, orderbook_raw)
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
            "gpuAvailability": gpu["availability"],
            "gpuPremium": gpu["premium"],
            "capex": capex,
        },
        "sources": {
            "openrouter": {
                "label": "OpenRouter public model rankings chart",
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
                "label": "Foundry Signals GPU Price Index",
                "url": foundry_raw["sources"]["price"]["url"],
                "definition": "Daily median across source-published provider prices, with source low/high range and a tracker-calculated 30-day moving average. Vertical markers expose provider-count changes. Provider composition changed over time; this is an illustrative third-party aggregate, not an official transaction index.",
            },
            "gpuPremium": {
                "label": "Derived from Foundry Signals provider-price medians",
                "url": foundry_raw["sources"]["price"]["url"],
                "definition": "Rolling 30-day median of H200/H100 and B200/H100 daily rental-price ratios. A value above 1 means a premium to H100; composition changes remain a limitation.",
            },
            "gpuAvailability": {
                "label": "Foundry Signals GPU Availability Index",
                "url": foundry_raw["sources"]["availability"]["url"],
                "definition": "Share of checks where at least one tracked provider had rentable capacity. H100/H200 availability applies the source's under-$4/hour filter; provider coverage changed over time. Early history is monthly and H200 begins in May 2026.",
            },
            "capex": {
                "label": "SEC companyfacts and official company disclosures",
                "definition": "Quarterly and event-frequency observations preserve source units and are not interpolated.",
            },
        },
    }
    snapshot["datasets"].update(ref_datasets)
    snapshot["meta"].update(ref_meta)
    snapshot["datasets"]["orderbookDepth"] = sorted(
        (
            {
                "date": row.get("date"),
                "series": str(row.get("source", "unknown")),
                "value": int(row["offerCount"]),
            }
            for row in (orderbook_raw.get("rows") or [])
            if isinstance(row.get("offerCount"), int)
        ),
        key=lambda r: (r["date"], r["series"]),
    )
    snapshot["sources"].update({
        "basisH100": {"url": "https://gpu-index.semianalysis.com/ | https://index.ornn.com | https://signals.foundry.ai", "label": "H100 三源价格对照", "definition": "同一 GPU 家族下三种口径并列：供应商报价中位、综合现货-合约指数、成交加权指数。口径不同，仅作交叉对照，不构成同质序列。"},
        "basisH200": {"url": "https://gpu-index.semianalysis.com/ | https://index.ornn.com | https://signals.foundry.ai", "label": "H200 三源价格对照", "definition": "口径同上。Foundry 与 Ornn 可能方向分歧，分歧本身是证据而非噪声。"},
        "basisB200": {"url": "https://gpu-index.semianalysis.com/ | https://index.ornn.com | https://signals.foundry.ai", "label": "B200 三源价格对照", "definition": "口径同上。"},
        "contractBand": {"url": "https://gpu-index.semianalysis.com/api/public-data", "label": "SemiAnalysis H100 1Y 合约调查区间", "definition": "月度调查的25-75分位合约价区间，半年期阶梯展示。许可：公开页引用需署名。"},
        "orderbookDepth": {"url": "https://api.gpuindexes.com/api/offers | https://console.vast.ai/api/v0/bundles/ | https://api.runpod.io/graphql", "label": "GPU 订单簿逐源观测", "definition": "gpuperhour/vast 为逐条报价 offers、runpod 为型号挂牌 types，单位语义不同故分序列展示不合并。时点观测，<10 有效日只画点不连线。"},
        "otpi": {"url": "https://index.ornn.com/api/otpi", "label": "Ornn OTPI 已实现 token 价", "definition": "按 lab 的成交加权 token 实现价（USD/Mtok），免费层滚动窗口每日快照累积。许可：Ornn 免费层署名引用。"},
    })
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
        cards.append(
            f'<article class="clock-card {CLOCK_STATE_CLASS.get(state, "")}">'
            f'<h4>{CLOCK_LABELS.get(clock.get("clock_id"), clock.get("title", ""))}</h4>'
            f'<div class="clock-state">{badge}</div>'
            f'<p class="clock-metric">{_clock_key_metric(clock)}</p>'
            f'<p class="clock-next">{clock.get("next_proof_point", "")}</p>'
            f"</article>"
        )
    generated = report.get("generatedAt", "")
    return (
        '<section class="section" id="clocks"><div class="section-head"><h2>四时钟判断状态</h2>'
        f'<span class="section-kicker">自动评估 · {generated}</span></div>'
        f'<div class="grid four">{"".join(cards)}</div></section>'
    )


def build_html(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    html_output = HTML.replace("__PAYLOAD__", payload)
    return html_output.replace("__CLOCKS__", _clocks_section())


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
<style>
:root{--bg:#f5f5f7;--paper:#fff;--ink:#1d1d1f;--muted:#6e6e73;--line:#d2d2d7;--blue:#0071e3;--cyan:#00a6a6;--green:#248a3d;--orange:#d76b00;--red:#d70015;--purple:#8944ab;--radius:8px}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI","Noto Sans SC",sans-serif;letter-spacing:0}.shell{max-width:1440px;margin:auto;padding:0 28px 64px}.topbar{margin:0 -28px;padding:0 28px;border-bottom:1px solid rgba(0,0,0,.08);background:var(--bg)}.topbar-inner{height:52px;display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{font-size:15px;font-weight:650;white-space:nowrap}.nav{display:flex;gap:4px;overflow:auto}.nav a{padding:7px 10px;color:var(--muted);font-size:13px;text-decoration:none;border-radius:6px}.nav a:hover{background:#fff;color:var(--ink)}.hero{padding:42px 0 30px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:42px;line-height:1.12;font-weight:700}.sub{margin:10px 0 0;color:var(--muted);font-size:16px}.controls{display:flex;align-items:end;flex-wrap:wrap;gap:10px;margin-top:24px}.control label{display:block;margin:0 0 5px;color:var(--muted);font-size:11px;font-weight:650;text-transform:uppercase}.control input{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit}.segments{display:flex;padding:3px;border:1px solid var(--line);border-radius:7px;background:#fff}.segments button{height:28px;padding:0 11px;border:0;border-radius:5px;background:transparent;color:var(--muted);font:inherit;font-size:12px;cursor:pointer}.segments button.active{background:var(--ink);color:#fff}.section{padding:34px 0 8px;border-bottom:1px solid var(--line)}.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:20px;margin-bottom:20px}.section h2{margin:0;font-size:25px;line-height:1.2}.section-kicker{color:var(--muted);font-size:12px;text-transform:uppercase}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.panel{min-width:0;padding:20px;border:1px solid rgba(0,0,0,.09);border-radius:var(--radius);background:var(--paper)}.panel.full{grid-column:1/-1}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.panel h3{margin:0;font-size:17px;line-height:1.35}.panel-note{margin:5px 0 0;color:var(--muted);font-size:12px}.chart{position:relative;min-height:330px;margin-top:12px}.chart svg{display:block;width:100%;height:330px;overflow:visible}.legend{display:flex;flex-wrap:wrap;gap:7px 12px;margin-top:10px}.legend button{display:inline-flex;align-items:center;gap:6px;padding:3px 6px;border:0;border-radius:4px;background:transparent;color:var(--muted);font:inherit;font-size:11px;cursor:pointer}.legend button.off{opacity:.32}.swatch{width:16px;height:3px;border-radius:2px}.key-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin-top:12px;border:1px solid #e5e5ea;border-radius:6px;overflow:hidden;background:#e5e5ea}.key-stat{min-width:0;padding:10px 12px;background:#fafafa}.key-stat b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.key-stat span{display:block;margin-top:4px;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}.source{margin-top:12px;padding-top:10px;border-top:1px solid #ececf0;color:var(--muted);font-size:11px}.source summary{cursor:pointer;list-style:none}.source summary::-webkit-details-marker{display:none}.source a{color:var(--blue)}.tooltip{position:absolute;z-index:5;display:none;max-width:300px;padding:9px 11px;border-radius:6px;background:rgba(29,29,31,.95);color:#fff;font-size:11px;line-height:1.5;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.16)}.empty{display:grid;place-items:center;height:300px;color:var(--muted);font-size:13px}.table-wrap{overflow:auto;border-top:1px solid var(--line)}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:10px 12px;border-bottom:1px solid #e8e8ed;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#fafafa;color:var(--muted);font-weight:650}td.num{text-align:right;font-variant-numeric:tabular-nums}.axis{fill:var(--muted);font-size:10px}.axis-title{fill:var(--muted);font-size:10px;font-weight:650}.gridline{stroke:#e5e5ea;stroke-width:1}.footer{padding:24px 0;color:var(--muted);font-size:11px}
.chart.compact{min-height:240px}.chart.compact svg{height:240px}
@media(max-width:820px){.shell{padding:0 16px 48px}.topbar{position:static;margin:0 -16px;padding:0 16px}.nav{display:none}.hero{padding-top:28px}h1{font-size:32px}.grid{grid-template-columns:1fr}.panel.full{grid-column:1}.panel{padding:16px}.chart{min-height:190px}.chart svg{height:190px}.chart.compact svg{height:170px}.axis,.axis-title{font-size:24px}.key-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.section-head{display:block}.section-kicker{display:block;margin-top:5px}}
.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.grid.four{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.clock-card{padding:16px;border:1px solid rgba(0,0,0,.09);border-radius:var(--radius);background:var(--paper)}.clock-card h4{margin:0;font-size:13px;color:var(--muted);font-weight:650}.clock-state{margin-top:8px;font-size:20px;font-weight:700}.st-observing .clock-state{color:#8e8e93}.st-trend .clock-state{color:#0071e3}.st-watch .clock-state{color:#b25000}.st-confirmed .clock-state{color:#1d7a3d}.clock-metric{margin:8px 0 0;font-size:12px;font-variant-numeric:tabular-nums}.clock-next{margin:6px 0 0;color:var(--muted);font-size:11px}.key-stats{grid-template-columns:repeat(5,minmax(0,1fr))}.subsection-title{grid-column:1/-1;margin:12px 0 0;padding-top:18px;border-top:1px solid var(--line);font-size:15px}.legend-item{display:inline-flex;align-items:center;gap:6px;padding:3px 6px;color:var(--muted);font-size:11px}.swatch.band{height:8px;opacity:.22}.model-detail{grid-column:1/-1;padding:16px 0 0;border-top:1px solid var(--line)}.model-detail>summary{cursor:pointer;list-style:none;font-size:13px;font-weight:650}.model-detail>summary::-webkit-details-marker{display:none}.detail-controls{display:flex;align-items:center;gap:12px;margin:16px 0 0}.detail-select{height:36px;max-width:620px;padding:0 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit}.detail-meta{color:var(--muted);font-size:12px}
@media(max-width:980px){.grid.three{grid-template-columns:1fr}}
@media(max-width:820px){.grid.three{grid-template-columns:1fr}.chart.compact{min-height:190px}.chart.compact svg{height:190px}.detail-controls{align-items:flex-start;flex-direction:column}.detail-select{width:100%;max-width:none}}
@media(max-width:820px){.key-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body><main class="shell">
<header class="topbar"><div class="topbar-inner"><div class="brand">AI Compute Economics</div><nav class="nav"><a href="#demand">需求与模型</a><a href="#compute">GPU</a><a href="#capex">CAPEX</a></nav></div></header>
<section class="hero"><h1>AI Compute Economics</h1><p class="sub">价格、用量与模型结构的时间序列</p><div class="controls"><div class="control"><label>开始日期</label><input id="start" type="date"></div><div class="control"><label>结束日期</label><input id="end" type="date"></div><div class="segments" id="presets"><button data-days="90">3M</button><button data-days="180">6M</button><button data-days="365">1Y</button><button data-days="0" class="active">全部</button></div></div></section>

__CLOCKS__<section class="section" id="demand"><div class="section-head"><h2>需求与活跃模型结构</h2><span class="section-kicker">OpenRouter · 52周</span></div><div class="grid"><article class="panel full" data-source="openrouter"><h3>OpenRouter 模型 Token 总量</h3><p class="panel-note">周度总量与4周均线 · 含公开来源汇总的长尾</p><div id="or-volume" class="chart"></div><div id="or-volume-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="openrouterComposition"><h3>OpenRouter 活跃模型组合更替</h3><p class="panel-note">每周独立展示公开模型与Others的Token占比 · 悬停查看具体模型</p><div id="or-composition" class="chart"></div><div id="composition-legend" class="legend"></div><div id="composition-latest" class="key-stats"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="activePrice"><h3>活跃模型 Output 价格层级迁移</h3><p class="panel-note">占OpenRouter公开周度总Token量 · Others和无法映射模型保留为灰色缺口</p><div id="active-price-tier" class="chart"></div><div id="active-price-tier-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="activePrice"><h3>活跃模型组合 Input 牌价</h3><p class="panel-note">按公开Token量加权 · 美元 / 100万 input tokens</p><div id="active-input-basket" class="chart compact"></div><div id="active-input-basket-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="activePrice"><h3>活跃模型组合 Output 牌价</h3><p class="panel-note">按公开Token量加权 · 美元 / 100万 output tokens</p><div id="active-output-basket" class="chart compact"></div><div id="active-output-basket-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="otpi"><h3>OTPI 已实现 Token 价（积累中）</h3><p class="panel-note" id="otpi-note">按 lab 的成交加权 token 实现价 · 免费层滚动窗口每日快照累积</p><div id="otpi-price" class="chart compact"></div><div id="otpi-price-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><details class="model-detail"><summary>查看近期活跃模型与单模型价格历史</summary><div class="detail-controls"><select id="active-model-select" class="detail-select" aria-label="活跃模型"></select><span id="active-model-meta" class="detail-meta"></span></div><div id="active-model-history" class="chart compact"></div><div id="active-model-history-legend" class="legend"></div><div class="table-wrap"><table><thead><tr><th>近期活跃模型</th><th>4周Token</th><th>总量占比</th><th>Input</th><th>Output</th><th>调价点</th></tr></thead><tbody id="active-model-body"></tbody></table></div></details></div></section>

<section class="section" id="compute"><div class="section-head"><h2>GPU市场</h2><span class="section-kicker">Foundry Signals · 公开历史</span></div><div class="grid three"><article class="panel" data-source="gpuPrice"><h3>H100 租赁价格</h3><p class="panel-note">供应商中位价、最低–最高区间与30日均线</p><div id="gpu-price-h100" class="chart compact"></div><div class="legend"><span class="legend-item"><i class="swatch" style="background:#0071e3"></i>中位价</span><span class="legend-item"><i class="swatch" style="background:#1d1d1f"></i>30日均线</span><span class="legend-item"><i class="swatch band" style="background:#0071e3"></i>最低–最高</span></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="gpuPrice"><h3>H200 租赁价格</h3><p class="panel-note">供应商中位价、最低–最高区间与30日均线</p><div id="gpu-price-h200" class="chart compact"></div><div class="legend"><span class="legend-item"><i class="swatch" style="background:#0071e3"></i>中位价</span><span class="legend-item"><i class="swatch" style="background:#1d1d1f"></i>30日均线</span><span class="legend-item"><i class="swatch band" style="background:#0071e3"></i>最低–最高</span></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="gpuPrice"><h3>B200 租赁价格</h3><p class="panel-note">供应商中位价、最低–最高区间与30日均线</p><div id="gpu-price-b200" class="chart compact"></div><div class="legend"><span class="legend-item"><i class="swatch" style="background:#0071e3"></i>中位价</span><span class="legend-item"><i class="swatch" style="background:#1d1d1f"></i>30日均线</span><span class="legend-item"><i class="swatch band" style="background:#0071e3"></i>最低–最高</span></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel full" data-source="gpuPremium"><h3>GPU 代际租赁溢价</h3><p class="panel-note">相对H100的30日中位价格倍数 · 1.0x表示无溢价</p><div id="gpu-premium" class="chart"></div><div id="gpu-premium-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><h3 class="subsection-title">跨来源交叉验证 · 报价 × 成交 × 合约</h3><article class="panel" data-source="basisH100"><h3>H100：报价 vs 成交指数</h3><p class="panel-note">Foundry 报价中位 × SemiAnalysis 综合指数 × Ornn 成交指数 · 口径不同不可混同，仅作交叉对照</p><div id="basis-h100" class="chart compact"></div><div id="basis-h100-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="basisH200"><h3>H200：报价 vs 成交指数</h3><p class="panel-note">同上三源对照 · 注意 Foundry 与 Ornn 可能方向分歧</p><div id="basis-h200" class="chart compact"></div><div id="basis-h200-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="basisB200"><h3>B200：报价 vs 成交指数</h3><p class="panel-note">同上三源对照</p><div id="basis-b200" class="chart compact"></div><div id="basis-b200-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="contractBand"><h3>H100 一年期合约价区间</h3><p class="panel-note">SemiAnalysis 公开调查区间 · 半年频率阶梯图，不与日线混轴</p><div id="contract-band" class="chart compact"></div><div id="contract-band-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><h3 class="subsection-title">可用率 · 保持来源原始月度频率</h3><article class="panel" data-source="gpuAvailability"><h3>H100 可用率</h3><p class="panel-note">35个月 · 有至少一家供应商可租用的检查占比</p><div id="gpu-availability-h100" class="chart compact"></div><div id="gpu-availability-h100-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="gpuAvailability"><h3>B200 可用率</h3><p class="panel-note">11个月 · B200不适用来源的$4价格上限</p><div id="gpu-availability-b200" class="chart compact"></div><div id="gpu-availability-b200-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="gpuAvailability"><h3>H200 可用率</h3><p class="panel-note">仅3个月 · 只显示观测点，不连接为趋势</p><div id="gpu-availability-h200" class="chart compact"></div><div id="gpu-availability-h200-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article><article class="panel" data-source="orderbookDepth"><h3>供给深度：订单簿观测（积累中）</h3><p class="panel-note" id="orderbook-note">gpuperhour / vast / runpod 分序列 offer 数 · 少于10个有效日只画观测点不连线</p><div id="orderbook-depth" class="chart compact"></div><div id="orderbook-depth-legend" class="legend"></div><details class="source"><summary>来源与口径</summary><p></p></details></article></div></section>

<section class="section" id="capex"><div class="section-head"><h2>CAPEX与官方承诺</h2><span class="section-kicker">Quarterly & event</span></div><article class="panel full" data-source="capex"><div class="table-wrap"><table><thead><tr><th>日期</th><th>公司</th><th>指标</th><th>期间</th><th>单位</th><th>数值</th></tr></thead><tbody id="capex-body"></tbody></table></div><details class="source"><summary>来源与口径</summary><p></p></details></article></section>
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
  const names=[...new Set(c.rows.map(r=>r.series))];
  names.forEach((name,idx)=>{
    const pts=visible.filter(r=>r.series===name).sort((a,b)=>dateNum(a.date)-dateNum(b.date));let segments=[],segment=[];
    const gapDays=c.opt.gapDays||11;pts.forEach((p,i)=>{if(i&&dateNum(p.date)-dateNum(pts[i-1].date)>gapDays*86400000){if(segment.length)segments.push(segment);segment=[]}segment.push(p)});if(segment.length)segments.push(segment);
    if(c.opt.band){const names=[...(states[id]||[])];if(names.length===2){const pick=n=>rows.filter(r=>r.series===n).sort((a,b)=>dateNum(a.date)-dateNum(b.date));const top=pick(names[0]),bot=pick(names[1]).reverse();if(top.length>1&&top.length===bot.length){let d=`M${x(dateNum(top[0].date)).toFixed(1)},${y(+top[0].value).toFixed(1)}`;for(let i=1;i<top.length;i++)d+=` H${x(dateNum(top[i].date)).toFixed(1)} V${y(+top[i].value).toFixed(1)}`;for(const p of bot)d+=` H${x(dateNum(p.date)).toFixed(1)} V${y(+p.value).toFixed(1)}`;svg+=`<path d="${d} Z" fill="${COLORS[0]}" opacity=".13"/>`}}}
    if(!c.opt.pointOnly)segments.forEach(seg=>{let d=`M${x(dateNum(seg[0].date)).toFixed(1)},${y(+seg[0].value).toFixed(1)}`;for(let i=1;i<seg.length;i++){const xx=x(dateNum(seg[i].date)).toFixed(1),yy=y(+seg[i].value).toFixed(1);d+=c.opt.step?` H${xx} V${yy}`:` L${xx},${yy}`}svg+=`<path d="${d}" fill="none" stroke="${COLORS[idx%COLORS.length]}" stroke-width="${name.includes('average')?3:2}" opacity="${name==='Weekly tokens'?0.42:1}"/>`});
    pts.forEach((p,i)=>{if(!c.opt.step||i===0||i===pts.length-1||+p.value!==+pts[i-1].value)svg+=`<circle cx="${x(dateNum(p.date))}" cy="${y(+p.value)}" r="3" fill="${COLORS[idx%COLORS.length]}" data-date="${p.date}" data-series="${esc(name)}" data-value="${p.value}"/>`})
  });
  svg+=`<rect class="hit" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${H-m.t-m.b}" fill="transparent"/></svg><div class="tooltip"></div>`;host.innerHTML=svg;
  const tip=host.querySelector('.tooltip'),svgEl=host.querySelector('svg');
  svgEl.onmousemove=e=>{const rect=svgEl.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W,target=xmin+(px-m.l)/(W-m.l-m.r)*(xmax-xmin),dates=[...new Set(visible.map(r=>r.date))],nearest=dates.reduce((a,b)=>Math.abs(dateNum(b)-target)<Math.abs(dateNum(a)-target)?b:a),rows=visible.filter(r=>r.date===nearest).sort((a,b)=>b.value-a.value);tip.innerHTML=`<strong>${nearest}</strong><br>`+rows.map(r=>`${esc(r.series)}: ${fmt(+r.value,c.opt.kind)}${Number.isFinite(+r.low)&&Number.isFinite(+r.high)?` · range ${fmt(+r.low,c.opt.kind)}–${fmt(+r.high,c.opt.kind)}`:''}${Number.isFinite(+r.coverage)?` · coverage ${(+r.coverage).toFixed(1)}%`:''}`).join('<br>');tip.style.display='block';tip.style.left=Math.min(e.offsetX+14,host.clientWidth-300)+'px';tip.style.top=Math.max(8,e.offsetY-20)+'px'};
  svgEl.onmouseleave=()=>tip.style.display='none';
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
function renderStackedArea(c){const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value);const dates=[...new Set(c.rows.map(r=>r.date).filter(d=>dateNum(d)>=start&&dateNum(d)<=end))].sort();if(!dates.length){host.innerHTML='<div class="empty">所选时间内没有可比数据</div>';return}const names=[...new Set(c.rows.map(r=>r.series))],lookup=new Map(c.rows.map(r=>[r.date+'|'+r.series,+r.value]));const W=1000,H=330,m={l:58,r:18,t:16,b:46},xmin=dateNum(dates[0]),xmax=dateNum(dates[dates.length-1]),x=v=>m.l+(v-xmin)/(xmax-xmin||1)*(W-m.l-m.r),y=v=>H-m.b-v/100*(H-m.t-m.b);let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.opt.title)}">`;[0,25,50,75,100].forEach(v=>{svg+=`<line class="gridline" x1="${m.l}" y1="${y(v)}" x2="${W-m.r}" y2="${y(v)}"/><text class="axis" x="${m.l-8}" y="${y(v)+3}" text-anchor="end">${v}%</text>`});for(let i=0;i<=4;i++){const idx=Math.round((dates.length-1)*i/4),d=dates[idx],xx=x(dateNum(d));svg+=`<text class="axis" x="${xx}" y="${H-20}" text-anchor="middle">${new Date(dateNum(d)).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}let cumulative=Object.fromEntries(dates.map(d=>[d,0]));names.forEach((name,idx)=>{const lower=dates.map(d=>cumulative[d]),upper=dates.map((d,i)=>{const v=lookup.get(d+'|'+name)||0;cumulative[d]+=v;return lower[i]+v});const top=dates.map((d,i)=>`${i?'L':'M'}${x(dateNum(d)).toFixed(1)},${y(upper[i]).toFixed(1)}`).join(' '),bottom=dates.slice().reverse().map((d,j)=>`L${x(dateNum(d)).toFixed(1)},${y(lower[dates.length-1-j]).toFixed(1)}`).join(' '),color=(c.opt.colors&&c.opt.colors[name])||COLORS[idx%COLORS.length];svg+=`<path d="${top} ${bottom} Z" fill="${color}" fill-opacity="${states[c.id].has(name)?0.82:0.04}" stroke="white" stroke-width="0.7"/>`});svg+=`<rect class="hit" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${H-m.t-m.b}" fill="transparent"/></svg><div class="tooltip"></div>`;host.innerHTML=svg;const tip=host.querySelector('.tooltip'),svgEl=host.querySelector('svg');svgEl.onmousemove=e=>{const rect=svgEl.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W,target=xmin+(px-m.l)/(W-m.l-m.r)*(xmax-xmin),nearest=dates.reduce((a,b)=>Math.abs(dateNum(b)-target)<Math.abs(dateNum(a)-target)?b:a),items=names.filter(n=>states[c.id].has(n)).map(n=>({name:n,value:lookup.get(nearest+'|'+n)||0})).sort((a,b)=>b.value-a.value);tip.innerHTML=`<strong>${nearest}</strong><br>`+items.map(r=>`${esc(r.name)}: ${r.value.toFixed(1)}%`).join('<br>');tip.style.display='block';tip.style.left=Math.min(e.offsetX+14,host.clientWidth-260)+'px';tip.style.top=Math.max(8,e.offsetY-20)+'px'};svgEl.onmouseleave=()=>tip.style.display='none'}
function barTimeChart(id,rows,opt){const cfg={id,rows,opt,renderer:renderBarTime};charts.push(cfg);cfg.renderer(cfg)}
function renderBarTime(c){const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value),rows=c.rows.filter(r=>dateNum(r.date)>=start&&dateNum(r.date)<=end).sort((a,b)=>dateNum(a.date)-dateNum(b.date));if(!rows.length){host.innerHTML='<div class="empty">所选时间内没有数据</div>';return}const W=1000,H=240,m={l:58,r:18,t:16,b:42},xmin=dateNum(rows[0].date),xmax=dateNum(rows[rows.length-1].date),step=(W-m.l-m.r)/rows.length,bw=Math.max(5,step*.62),y=v=>H-m.b-v/100*(H-m.t-m.b);let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.opt.title)}">`;[0,25,50,75,100].forEach(v=>svg+=`<line class="gridline" x1="${m.l}" y1="${y(v)}" x2="${W-m.r}" y2="${y(v)}"/><text class="axis" x="${m.l-8}" y="${y(v)+3}" text-anchor="end">${v}%</text>`);rows.forEach((r,i)=>{const xx=m.l+step*(i+.5);svg+=`<rect x="${xx-bw/2}" y="${y(+r.value)}" width="${bw}" height="${y(0)-y(+r.value)}" rx="2" fill="${+r.value>=35?'#0071e3':'#c7c7cc'}" data-date="${r.date}" data-value="${r.value}"/>`});svg+=`<line x1="${m.l}" y1="${y(35)}" x2="${W-m.r}" y2="${y(35)}" stroke="#d76b00" stroke-width="2" stroke-dasharray="6 5"/><text class="axis" x="${W-m.r}" y="${y(35)-6}" text-anchor="end">35% display threshold</text>`;for(let i=0;i<=4;i++){const idx=Math.round((rows.length-1)*i/4),r=rows[idx],xx=m.l+step*(idx+.5);svg+=`<text class="axis" x="${xx}" y="${H-17}" text-anchor="middle">${new Date(dateNum(r.date)).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}svg+='</svg><div class="tooltip"></div>';host.innerHTML=svg;const tip=host.querySelector('.tooltip');host.querySelectorAll('rect[data-date]').forEach(el=>{el.onmouseenter=e=>{tip.innerHTML=`<strong>${el.dataset.date}</strong><br>Price coverage: ${(+el.dataset.value).toFixed(1)}%`;tip.style.display='block';tip.style.left=Math.min(e.offsetX+12,host.clientWidth-220)+'px';tip.style.top='18px'};el.onmouseleave=()=>tip.style.display='none'})}
function rangeChart(id,rows,annotations){const cfg={id,rows,annotations,renderer:renderRangeChart};charts.push(cfg);cfg.renderer(cfg)}
function renderRangeChart(c){
  const host=$('#'+c.id),start=dateNum($('#start').value),end=dateNum($('#end').value),rows=c.rows.filter(r=>dateNum(r.date)>=start&&dateNum(r.date)<=end).sort((a,b)=>dateNum(a.date)-dateNum(b.date));
  if(!rows.length){host.innerHTML='<div class="empty">所选时间内没有价格数据</div>';return}
  const W=1000,H=280,m={l:76,r:18,t:32,b:46},xmin=dateNum(rows[0].date),xmax=dateNum(rows[rows.length-1].date),values=rows.flatMap(r=>[+r.low,+r.high,+r.value,+r.movingAverage30d]).filter(Number.isFinite),ymin=Math.max(0,Math.min(...values)*.88),ymax=Math.max(...values)*1.08,x=v=>m.l+(v-xmin)/(xmax-xmin||1)*(W-m.l-m.r),y=v=>H-m.b-(v-ymin)/(ymax-ymin||1)*(H-m.t-m.b);
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="GPU provider median and range">`;
  for(let i=0;i<=4;i++){const v=ymin+(ymax-ymin)*i/4,yy=y(v);svg+=`<line class="gridline" x1="${m.l}" y1="${yy}" x2="${W-m.r}" y2="${yy}"/><text class="axis" x="${m.l-8}" y="${yy+3}" text-anchor="end">${fmt(v,'usd')}</text>`}
  for(let i=0;i<=4;i++){const d=xmin+(xmax-xmin)*i/4,xx=x(d);svg+=`<text class="axis" x="${xx}" y="${H-18}" text-anchor="middle">${new Date(d).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</text>`}
  const top=rows.map((r,i)=>`${i?'L':'M'}${x(dateNum(r.date)).toFixed(1)},${y(+r.high).toFixed(1)}`).join(' '),bottom=rows.slice().reverse().map(r=>`L${x(dateNum(r.date)).toFixed(1)},${y(+r.low).toFixed(1)}`).join(' ');svg+=`<path d="${top} ${bottom} Z" fill="#0071e3" fill-opacity=".12"/>`;
  const medianPath=rows.map((r,i)=>`${i?'L':'M'}${x(dateNum(r.date)).toFixed(1)},${y(+r.value).toFixed(1)}`).join(' '),averagePath=rows.map((r,i)=>`${i?'L':'M'}${x(dateNum(r.date)).toFixed(1)},${y(+r.movingAverage30d).toFixed(1)}`).join(' ');svg+=`<path d="${medianPath}" fill="none" stroke="#0071e3" stroke-width="2"/><path d="${averagePath}" fill="none" stroke="#1d1d1f" stroke-width="3"/>`;
  (c.annotations||[]).filter(a=>dateNum(a.date)>=start&&dateNum(a.date)<=end).forEach((a,i)=>{const xx=x(dateNum(a.date));svg+=`<line x1="${xx}" y1="${m.t}" x2="${xx}" y2="${H-m.b}" stroke="#d76b00" stroke-width="1.4" stroke-dasharray="4 4"/><text class="axis" x="${xx+4}" y="${m.t+10+(i%2)*12}" fill="#d76b00">${esc(a.label)} providers</text>`});
  svg+=`<rect class="hit" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${H-m.t-m.b}" fill="transparent"/></svg><div class="tooltip"></div>`;host.innerHTML=svg;const tip=host.querySelector('.tooltip'),svgEl=host.querySelector('svg');svgEl.onmousemove=e=>{const rect=svgEl.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W,target=xmin+(px-m.l)/(W-m.l-m.r)*(xmax-xmin),nearest=rows.reduce((a,b)=>Math.abs(dateNum(b.date)-target)<Math.abs(dateNum(a.date)-target)?b:a);tip.innerHTML=`<strong>${nearest.date}</strong><br>中位价 ${fmt(+nearest.value,'usd')}<br>30日均线 ${fmt(+nearest.movingAverage30d,'usd')}<br>区间 ${fmt(+nearest.low,'usd')}–${fmt(+nearest.high,'usd')}<br>${nearest.providerCount} providers`;tip.style.display='block';tip.style.left=Math.min(e.offsetX+14,host.clientWidth-285)+'px';tip.style.top=Math.max(8,e.offsetY-20)+'px'};svgEl.onmouseleave=()=>tip.style.display='none'
}
function activeModelDetail(){
  const models=DATA.datasets.activeModels,select=$('#active-model-select'),body=$('#active-model-body');select.innerHTML=models.map((m,i)=>`<option value="${i}">${esc(m.name)}</option>`).join('');body.innerHTML=models.map(m=>`<tr><td>${esc(m.name)}</td><td class="num">${m.tokens.toFixed(2)}T</td><td class="num">${m.share.toFixed(1)}%</td><td class="num">${m.inputPrice==null?'n/a':fmt(+m.inputPrice,'usd')}</td><td class="num">${m.outputPrice==null?'n/a':fmt(+m.outputPrice,'usd')}</td><td class="num">${m.historyPoints}</td></tr>`).join('');
  const cfg={id:'active-model-history',legendId:'active-model-history-legend',rows:[],opt:{title:'Active model price history',kind:'usd',yTitle:'USD / 1M tokens',zero:true,step:true},renderer:renderChart};charts.push(cfg);
  function choose(){const model=models[+select.value],rows=[];(model.priceHistory||[]).forEach(p=>{if(p.input!=null)rows.push({date:p.date,series:'Input',value:p.input});if(p.output!=null)rows.push({date:p.date,series:'Output',value:p.output})});cfg.rows=rows;states[cfg.id]=new Set(rows.map(r=>r.series));renderLegend(cfg);$('#active-model-meta').textContent=`4周 ${model.tokens.toFixed(2)}T · 占总量 ${model.share.toFixed(1)}% · ${model.historyPoints} 个调价点`;cfg.renderer(cfg)}select.onchange=choose;choose()
}
function sourceDetails(){document.querySelectorAll('[data-source]').forEach(el=>{const s=DATA.sources[el.dataset.source],p=el.querySelector('.source p');if(!s||!p)return;p.innerHTML=`<strong>${esc(s.label)}</strong><br>${esc(s.definition)}${s.url?`<br><a href="${esc(s.url)}">打开原始来源</a>`:''}`})}
function renderTable(){const body=$('#capex-body');body.innerHTML=DATA.datasets.capex.map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.company)}</td><td>${esc(r.metric)}</td><td>${esc(r.period||'')}</td><td>${esc(r.unit)}</td><td class="num">${esc(r.value)}</td></tr>`).join('')}
function redraw(){charts.forEach(c=>c.renderer(c))}function preset(days,btn){document.querySelectorAll('#presets button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');const max=dateNum(DATA.meta.maxDate),min=days?Math.max(dateNum(DATA.meta.minDate),max-days*86400000):dateNum(DATA.meta.minDate);$('#start').value=new Date(min).toISOString().slice(0,10);$('#end').value=DATA.meta.maxDate;redraw()}
$('#start').value=DATA.meta.minDate;$('#end').value=DATA.meta.maxDate;$('#start').onchange=redraw;$('#end').onchange=redraw;document.querySelectorAll('#presets button').forEach(b=>b.onclick=()=>preset(+b.dataset.days,b));
lineChart('or-volume','or-volume-legend',DATA.datasets.openrouterVolume,{title:'OpenRouter token volume',kind:'tokens',yTitle:'Trillion tokens',zero:true});
compositionChart('or-composition',DATA.datasets.openrouterComposition);
const TIER_COLORS={'免费':'#248a3d','<$1':'#0071e3','$1–5':'#00a6a6','>$5':'#d76b00','Others / 无法匹配':'#8e8e93'};
stackedAreaChart('active-price-tier','active-price-tier-legend',DATA.datasets.activePriceTiers,{title:'Active model output price tiers',colors:TIER_COLORS});
lineChart('active-input-basket','active-input-basket-legend',DATA.datasets.activeInputBasket,{title:'Active model input basket listed rate',kind:'usd',yTitle:'USD / 1M input',zero:true});
lineChart('active-output-basket','active-output-basket-legend',DATA.datasets.activeOutputBasket,{title:'Active model output basket listed rate',kind:'usd',yTitle:'USD / 1M output',zero:true});
['H100','H200','B200'].forEach(g=>rangeChart('gpu-price-'+g.toLowerCase(),DATA.datasets.gpuPrice.filter(r=>r.series===g),DATA.datasets.gpuPriceAnnotations[g]));
lineChart('gpu-premium','gpu-premium-legend',DATA.datasets.gpuPremium,{title:'GPU generation rental premium',kind:'multiple',yTitle:'Price ratio to H100',zero:false,reference:1});
lineChart('gpu-availability-h100','gpu-availability-h100-legend',DATA.datasets.gpuAvailability.filter(r=>r.series==='H100'),{title:'H100 availability',kind:'pct',yTitle:'Availability',zero:true,gapDays:45});
lineChart('gpu-availability-b200','gpu-availability-b200-legend',DATA.datasets.gpuAvailability.filter(r=>r.series==='B200'),{title:'B200 availability',kind:'pct',yTitle:'Availability',zero:true,gapDays:45});
lineChart('gpu-availability-h200','gpu-availability-h200-legend',DATA.datasets.gpuAvailability.filter(r=>r.series==='H200'),{title:'H200 availability observations',kind:'pct',yTitle:'Availability',zero:true,gapDays:45,pointOnly:true});

const orderbookRows=DATA.datasets.orderbookDepth||[];
const obDays=DATA.meta&&DATA.meta.orderbookValidDays?DATA.meta.orderbookValidDays:0;
document.getElementById('orderbook-note').textContent=`三源 offer 总数 · 已积累 ${obDays}/10 个有效日${obDays>=10?'，已可连线':'，少于10个有效日只画观测点不连线'}`;
lineChart('orderbook-depth','orderbook-depth-legend',orderbookRows,{title:'Orderbook total offers',kind:'usd',yTitle:'Offers',zero:true,pointOnly:obDays<10});
const otpiDays=DATA.meta&&DATA.meta.otpiValidDays?DATA.meta.otpiValidDays:0;
document.getElementById('otpi-note').textContent=`按 lab 成交加权实现价 · 已积累 ${otpiDays}/10 个有效日${otpiDays>=10?'，已可连线':'，少于10个有效日只画观测点不连线'}`;
lineChart('otpi-price','otpi-price-legend',DATA.datasets.otpi||[],{title:'Ornn OTPI realized token price',kind:'usd',yTitle:'USD/Mtok',zero:true,pointOnly:otpiDays<10});
lineChart('basis-h100','basis-h100-legend',DATA.datasets.basisH100||[],{title:'H100 price basis compare',kind:'usd',yTitle:'USD/GPU-hr',zero:true,gapDays:20});
lineChart('basis-h200','basis-h200-legend',DATA.datasets.basisH200||[],{title:'H200 price basis compare',kind:'usd',yTitle:'USD/GPU-hr',zero:true,gapDays:20});
lineChart('basis-b200','basis-b200-legend',DATA.datasets.basisB200||[],{title:'B200 price basis compare',kind:'usd',yTitle:'USD/GPU-hr',zero:true,gapDays:20});
lineChart('contract-band','contract-band-legend',DATA.datasets.contractBand||[],{title:'H100 1Y contract range',kind:'usd',yTitle:'USD/GPU-hr',zero:true,step:true,band:true});
activeModelDetail();sourceDetails();renderTable();$('#freshness').textContent='Updated '+DATA.meta.generatedAt+' · Public source history only · No composite score';
</script></body></html>'''


if __name__ == "__main__":
    raise SystemExit(main())
