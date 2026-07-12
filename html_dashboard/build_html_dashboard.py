#!/usr/bin/env python3
"""
Build a portable HTML dashboard from source-backed tracker_v2 production data.

The output intentionally does not depend on Streamlit. It embeds a compact data
extract and renders charts with plain SVG so the global date filter and per-chart
legend toggles can re-scale the charts deterministically.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable

import duckdb
import requests


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "ai_compute_tracker_production.db"
OUT_DIR = ROOT / "html_dashboard"
DATA_DIR = OUT_DIR / "data"
HTML_PATH = OUT_DIR / "ai_compute_trend_board.html"
DATA_PATH = DATA_DIR / "ai_compute_dashboard_extract.json"

TOKEN_HISTORY_DAILY_API = "https://api.github.com/repos/Socialpranker/token-history/contents/data/models/daily"
TOKEN_HISTORY_RAW = "https://raw.githubusercontent.com/Socialpranker/token-history/main/data/models/daily/{name}"
TOKEN_HISTORY_TRENDS = "https://raw.githubusercontent.com/Socialpranker/token-history/main/data/models/trends.json"

FOCUS_GPU = ["A100 80GB", "A100", "H100", "H200", "B200", "B300", "L40S", "RTX 4090", "RTX 5090", "MI300X"]
FOCUS_TOKEN_VENDORS = ["openai", "anthropic", "google", "deepseek", "qwen", "moonshot", "bytedance", "x-ai", "mistral", "meta"]


def _connect() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Production database not found: {DB_PATH}")
    return duckdb.connect(str(DB_PATH), read_only=True)


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    frame = con.execute(sql).df()
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _short_model(value: str, limit: int = 34) -> str:
    text = str(value or "").strip()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    text = text.replace("-preview", "").replace("-instruct", "")
    text = re.sub(r"-20\d{6,8}$", "", text)
    text = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", text)
    if len(text) > limit:
        return text[: limit - 1] + "..."
    return text


def _normalize_gpu(value: str) -> str:
    text = str(value or "").replace("NVIDIA ", "").strip()
    if text == "A100 80GB":
        return "A100 80GB"
    return text


def _date(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text[:10]


def _series_from_rows(rows: Iterable[dict[str, Any]], *, x: str, y: str, series: str) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        val = _safe_float(row.get(y))
        date = _date(row.get(x))
        name = str(row.get(series) or "").strip()
        if date and name and val is not None:
            out.append({"date": date, "series": name, "value": val})
    return out


def production_extract(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    market_count = con.execute("select count(*) from production_market_facts_analysis").fetchone()[0]
    quality_count = con.execute("select count(*) from production_data_quality_events_latest").fetchone()[0]
    latest_fetch = con.execute("select max(fetched_at) from production_market_facts").fetchone()[0]

    gpu_rental = _rows(
        con,
        """
        select date, replace(entity, 'NVIDIA ', '') as gpu, median(value) as price
        from production_market_facts_analysis
        where track='gpu_rental_trend'
          and metric='avg_price_per_gpu_hour'
          and value > 0
        group by date, gpu
        order by date, gpu
        """,
    )
    gpu_rental = [r for r in gpu_rental if r["gpu"] in FOCUS_GPU]

    gpu_market_fixing = _rows(
        con,
        """
        with shaped as (
          select date,
                 entity as gpu,
                 dimension as tenor,
                 median(case when metric='price_usd_per_gpu_hr' then value end) as price,
                 median(case when metric='delta_1d_pct' then value end) as delta_1d,
                 median(case when metric='delta_7d_pct' then value end) as delta_7d,
                 median(case when metric='delta_30d_pct' then value end) as delta_30d,
                 median(case when metric='observations' then value end) as observations,
                 median(case when metric='venues_eligible' then value end) as venues_eligible,
                 median(case when metric='venues_total' then value end) as venues_total
          from production_market_facts_analysis
          where track='gpu_market_fixing'
          group by date, gpu, tenor
        )
        select *
        from shaped
        where price is not null
        order by date, gpu, tenor
        """,
    )
    gpu_market_fixing = [r for r in gpu_market_fixing if r["gpu"] in FOCUS_GPU]

    cloud_instance = _rows(
        con,
        """
        select coalesce(cast(fetched_at as date), date) as date,
               vendor || ' ' || entity || ' ' ||
               case when dimension='low_priority' then 'LP'
                    when dimension='on_demand' then 'OD'
                    else dimension end as series,
               min(value) as price
        from production_market_facts_analysis
        where track='cloud_instance_price'
          and metric='instance_price_per_hour'
          and entity in ('H100', 'H200', 'A100', 'MI300X')
          and dimension in ('spot', 'low_priority', 'on_demand')
          and value > 0
        group by 1,2
        order by 1,2
        """,
    )

    orderbook = _rows(
        con,
        """
        with gpuperhour as (
          select date, entity as gpu,
                 median(case when metric='available_price_per_gpu_hour' then value end) as price,
                 median(case when metric='available_offer_count' then value end) as offers,
                 'GPUPerHour' as source
          from production_market_facts_analysis
          where track='gpu_available_offer'
          group by date, entity
        ),
        vast as (
          select date, entity as gpu,
                 median(case when metric='price_median_per_gpu_hour' then value end) as price,
                 median(case when metric='offer_count' then value end) as offers,
                 'Vast.ai' as source
          from production_market_facts_analysis
          where track='vast_offer_snapshot'
          group by date, entity
        ),
        runpod as (
          select date, entity as gpu,
                 min(case when metric in (
                    'community_price_per_gpu_hour',
                    'secure_price_per_gpu_hour',
                    'lowest_uninterruptable_price_per_gpu_hour'
                 ) then value end) as price,
                 max(case when metric='max_gpu_count' then value end) as offers,
                 'RunPod on-demand' as source
          from production_market_facts_analysis
          where track='runpod_gpu_price_snapshot'
          group by date, entity
        ),
        combined as (
          select date, gpu, price, offers, source from gpuperhour
          union all
          select date, gpu, price, offers, source from vast
          union all
          select date, gpu, price, offers, source from runpod
        )
        select date, gpu, price, offers, source
        from combined
        where price is not null and offers is not null
        order by date, gpu, source
        """,
    )

    gpu_index = _rows(
        con,
        """
        with shaped as (
          select date, replace(entity, 'NVIDIA ', '') as gpu,
                 median(case when metric in ('range_low_price_per_gpu_hour', 'aggregate_low_price_per_gpu_hour') then value end) as low,
                 median(case when metric='median_price_per_gpu_hour' then value end) as median,
                 median(case when metric in ('range_high_price_per_gpu_hour', 'aggregate_high_price_per_gpu_hour') then value end) as high
          from production_market_facts_analysis
          where track='gpu_rental_index'
          group by date, gpu
        )
        select * from shaped
        where low is not null or median is not null or high is not null
        order by gpu
        """,
    )
    gpu_index = [r for r in gpu_index if r["gpu"] in FOCUS_GPU]

    openrouter_proxy = _rows(
        con,
        """
        select date, metric as series, sum(value) as value
        from production_market_facts_analysis
        where track='openrouter_usage'
          and metric in ('tool_call_count', 'image_processing_count')
          and date + INTERVAL 6 DAY <= CAST(
              (select max(fetched_at) from production_market_facts) AS DATE
          )
        group by date, metric
        order by date, metric
        """,
    )

    token_price = _rows(
        con,
        """
        with normalized as (
          select date, entity, vendor, median(value) as price
          from production_market_facts_analysis
          where track='token_price'
            and metric='output_price_per_1m_tokens'
            and value > 0
          group by date, entity, vendor
        ),
        eligible as (
          select entity, vendor, count(distinct date) as days, max(date) as latest
          from normalized
          where lower(vendor) in ('openai','anthropic','google','deepseek','qwen','moonshot','bytedance','x-ai','mistral','meta')
          group by entity, vendor
          having count(distinct date) >= 5
        ),
        latest_prices as (
          select n.entity, n.vendor, n.price,
                 row_number() over (partition by n.vendor order by n.price desc, n.entity) as vendor_rank
          from normalized n
          join eligible e using(entity, vendor)
          where n.date=e.latest
        ),
        selected as (
          select entity, vendor
          from latest_prices
          where vendor_rank <= 2
        )
        select date, vendor || ' · ' || entity as series, price
        from normalized
        join selected using(entity, vendor)
        order by date, series
        """,
    )

    model_price = _rows(
        con,
        """
        with pivoted as (
          select date, entity, vendor,
                 median(case when metric='output_price_per_1m_tokens' then value end) as price,
                 median(case when metric='quality_score' then value end) as quality
          from production_market_facts_analysis
          where track='model_value_score'
          group by date, entity, vendor
        ),
        latest as (
          select max(date) as latest_date from pivoted
        ),
        selected as (
          select entity, vendor
          from pivoted, latest
          where date=latest_date and quality >= 80 and price > 0
          order by price asc, quality desc
          limit 8
        )
        select p.date, p.entity as model, p.vendor, p.price, p.quality
        from pivoted p
        join selected s using(entity, vendor)
        where p.price > 0 and p.quality >= 80
        order by p.date, p.price
        """,
    )

    multimodal = _rows(
        con,
        """
        select date,
               entity || ' · ' || sub_entity || ' · ' || dimension as series,
               metric,
               median(value) as value
        from production_market_facts_analysis
        where track='multimodal_generation_cost'
          and metric in ('video_generation_price_per_1m_tokens', 'video_generation_5s_example_credits')
        group by date, series, metric
        order by date, series
        """,
    )

    commercialization = _rows(
        con,
        """
        select date, entity as series, metric, median(value) as value
        from production_market_facts_analysis
        where track='app_commercialization'
          and metric in ('arr', 'business_adoption_share')
        group by date, series, metric
        order by date, series
        """,
    )

    capex_us = _rows(
        con,
        """
        with latest as (
          select *, row_number() over (partition by ticker order by period_end desc) as rn
          from production_capex_actuals
        )
        select 'US' as region, ticker, company, capex_value, unit, fiscal_period, period_end, source_url
        from latest
        where rn = 1
        order by case ticker when 'MSFT' then 1 when 'AMZN' then 2 when 'GOOGL' then 3 when 'META' then 4 when 'ORCL' then 5 else 99 end
        """,
    )

    china_capex = _rows(
        con,
        """
        select 'China' as region, entity as company, sub_entity as ticker, metric, value, unit, date, notes, source_url, source_type, confidence
        from production_market_facts_analysis
        where track='china_cloud_capex'
        order by company, metric
        """,
    )

    quality_events = _rows(
        con,
        """
        select severity, source_id, affected_key, message, fetched_at
        from production_data_quality_events_latest
        where source_id like '%openrouter%'
           or affected_key like '%openrouter%'
           or affected_key like '%vast%'
           or affected_key like '%runpod%'
           or affected_key like '%gcp%'
           or affected_key like '%aws%'
           or affected_key like '%china_cloud_capex%'
        order by fetched_at desc
        limit 24
        """,
    )

    return {
        "meta": {
            "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "db_path": str(DB_PATH),
            "production_market_facts": int(market_count),
            "quality_events": int(quality_count),
            "latest_fetch": latest_fetch.isoformat() if latest_fetch else None,
        },
        "gpuRental": _series_from_rows(gpu_rental, x="date", y="price", series="gpu"),
        "gpuMarketFixing": [
            {
                "date": _date(r.get("date")),
                "gpu": r.get("gpu"),
                "tenor": r.get("tenor"),
                "price": _safe_float(r.get("price")),
                "delta1d": _safe_float(r.get("delta_1d")),
                "delta7d": _safe_float(r.get("delta_7d")),
                "delta30d": _safe_float(r.get("delta_30d")),
                "observations": _safe_float(r.get("observations")),
                "venuesEligible": _safe_float(r.get("venues_eligible")),
                "venuesTotal": _safe_float(r.get("venues_total")),
            }
            for r in gpu_market_fixing
            if _safe_float(r.get("price")) is not None
        ],
        "cloudInstance": _series_from_rows(cloud_instance, x="date", y="price", series="series"),
        "orderbook": [
            {
                "date": _date(r.get("date")),
                "gpu": r.get("gpu"),
                "source": r.get("source"),
                "series": f"{r.get('gpu')} · {r.get('source')}",
                "price": _safe_float(r.get("price")),
                "offers": _safe_float(r.get("offers")),
            }
            for r in orderbook
            if _safe_float(r.get("price")) is not None and _safe_float(r.get("offers")) is not None
        ],
        "gpuIndex": [
            {
                "date": _date(r.get("date")),
                "gpu": r.get("gpu"),
                "low": _safe_float(r.get("low")),
                "median": _safe_float(r.get("median")),
                "high": _safe_float(r.get("high")),
            }
            for r in gpu_index
        ],
        "openrouterProxy": _series_from_rows(openrouter_proxy, x="date", y="value", series="series"),
        "tokenPrice": [
            {"date": _date(r.get("date")), "series": _short_model(r.get("series"), 38), "value": _safe_float(r.get("price"))}
            for r in token_price
            if _safe_float(r.get("price")) is not None
        ],
        "modelPrice": [
            {
                "date": _date(r.get("date")),
                "series": _short_model(r.get("model"), 30),
                "value": _safe_float(r.get("price")),
                "quality": _safe_float(r.get("quality")),
            }
            for r in model_price
            if _safe_float(r.get("price")) is not None
        ],
        "multimodal": [
            {
                "date": _date(r.get("date")),
                "series": _short_model(r.get("series"), 36),
                "metric": r.get("metric"),
                "value": _safe_float(r.get("value")),
            }
            for r in multimodal
            if _safe_float(r.get("value")) is not None
        ],
        "commercialization": [
            {"date": _date(r.get("date")), "series": r.get("series"), "metric": r.get("metric"), "value": _safe_float(r.get("value"))}
            for r in commercialization
            if _safe_float(r.get("value")) is not None
        ],
        "capexUs": capex_us,
        "capexChina": [{**row, "date": _date(row.get("date"))} for row in china_capex],
        "qualityEvents": quality_events,
    }


def token_history_extract() -> dict[str, Any]:
    out: dict[str, Any] = {
        "series": [],
        "meta": {
            "source": "Socialpranker/token-history",
            "source_url": "https://github.com/Socialpranker/token-history",
            "status": "not_fetched",
        },
    }
    try:
        listing = requests.get(TOKEN_HISTORY_DAILY_API, timeout=25, headers={"User-Agent": "codex-research"}).json()
        files = sorted(item["name"] for item in listing if str(item.get("name", "")).endswith(".json"))
        daily: dict[str, dict[str, float]] = {}
        for name in files:
            payload = requests.get(TOKEN_HISTORY_RAW.format(name=name), timeout=25, headers={"User-Agent": "codex-research"}).json()
            daily[name.replace(".json", "")] = {str(k): float(v) for k, v in payload.items()}
        if not daily:
            return out
        coverage: dict[str, dict[str, float]] = defaultdict(lambda: {"days": 0, "total": 0.0, "latest": 0.0})
        latest_date = sorted(daily)[-1]
        for date, values in daily.items():
            for model, value in values.items():
                coverage[model]["days"] += 1
                coverage[model]["total"] += value
                if date == latest_date:
                    coverage[model]["latest"] = value
        max_days = max((stats["days"] for stats in coverage.values()), default=0)
        top_models = [
            model
            for model, stats in sorted(
                coverage.items(),
                key=lambda kv: (kv[1]["days"], kv[1]["total"], kv[1]["latest"]),
                reverse=True,
            )
            if stats["days"] >= max(2, max_days - 1)
        ][:8]
        rows = []
        for date, values in sorted(daily.items()):
            for model in top_models:
                if model in values:
                    rows.append({"date": date, "series": _short_model(model, 32), "value": values[model] / 1e12})
        try:
            trends = requests.get(TOKEN_HISTORY_TRENDS, timeout=25, headers={"User-Agent": "codex-research"}).json()
        except Exception:
            trends = {}
        out["series"] = rows
        out["meta"] = {
            "source": "Socialpranker/token-history",
            "source_url": "https://github.com/Socialpranker/token-history",
            "status": "fetched",
            "first_date": min(daily),
            "last_date": max(daily),
            "days": len(daily),
            "max_model_days": int(max_days),
            "as_of": trends.get("as_of"),
            "warming_up": trends.get("warming_up"),
            "note": "GitHub archive of OpenRouter model token rankings; sparse by model and not an official live OpenRouter API pull.",
        }
    except Exception as exc:
        out["meta"]["status"] = "failed"
        out["meta"]["error"] = str(exc)
    return out


def _all_dates(data: dict[str, Any]) -> list[str]:
    dates = set()
    for key, value in data.items():
        if isinstance(value, list):
            for row in value:
                if isinstance(row, dict) and row.get("date"):
                    dates.add(_date(row["date"]))
        elif isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, list):
                    for row in nested:
                        if isinstance(row, dict) and row.get("date"):
                            dates.add(_date(row["date"]))
    return sorted(dates)


def build_html(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    title = "AI Compute Price & Cost Trends"
    return HTML_TEMPLATE.replace("__DATA__", payload).replace("__TITLE__", escape(title))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = _connect()
    data = production_extract(con)
    data["openrouterTokenArchive"] = token_history_extract()
    dates = _all_dates(data)
    data["meta"]["min_date"] = dates[0] if dates else None
    data["meta"]["max_date"] = dates[-1] if dates else None
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML_PATH.write_text(build_html(data), encoding="utf-8")
    print(f"Wrote {HTML_PATH}")
    print(f"Wrote {DATA_PATH}")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f5f5f7;
      --paper: #ffffff;
      --ink: #1d1d1f;
      --muted: #6e6e73;
      --line: #d8dbe2;
      --soft: #eceef2;
      --blue: #002fa7;
      --blue2: #5b8def;
      --orange: #ff9500;
      --green: #0f9f8f;
      --red: #d92d20;
      --shadow: 0 18px 45px rgba(15, 23, 42, .07);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", "Noto Sans SC", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(0,47,167,.04) 1px, transparent 1px),
        linear-gradient(0deg, rgba(0,47,167,.035) 1px, transparent 1px),
        var(--bg);
      background-size: 56px 56px;
    }
    .wrap { width: min(1440px, calc(100vw - 40px)); margin: 0 auto; padding: 28px 0 56px; }
    .hero {
      background: #050507;
      color: #fff;
      border-radius: var(--radius);
      padding: 28px 30px;
      box-shadow: var(--shadow);
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(360px, .8fr);
      gap: 24px;
      align-items: end;
    }
    .eyebrow { color: #aeb6c7; font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
    h1 { margin: 8px 0 10px; font-size: clamp(34px, 5vw, 74px); line-height: .96; letter-spacing: 0; font-weight: 760; }
    .hero p { margin: 0; color: #d9dce5; font-size: 15px; line-height: 1.55; max-width: 920px; }
    .kpis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .kpi { background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.13); border-radius: var(--radius); padding: 12px; min-height: 82px; }
    .kpi-label { color: #aeb6c7; font-size: 12px; font-weight: 700; }
    .kpi-value { font-size: 22px; font-weight: 780; margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .kpi-note { color: #d9dce5; font-size: 12px; margin-top: 4px; }
    .controls {
      margin: 16px 0 18px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      background: rgba(255,255,255,.88);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px 14px;
      backdrop-filter: blur(18px);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .control-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    label { color: var(--muted); font-size: 12px; font-weight: 760; }
    input[type=date] { border: 1px solid var(--line); background: #fff; border-radius: var(--radius); padding: 7px 9px; color: var(--ink); font: inherit; }
    button { border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: var(--radius); padding: 8px 11px; font-weight: 760; cursor: pointer; }
    button:hover { border-color: var(--blue); color: var(--blue); }
    .source-pill { color: var(--muted); font-size: 12px; }
    .section {
      margin-top: 18px;
      padding: 12px 0 6px;
      border-top: 2px solid var(--ink);
      display: grid;
      grid-template-columns: 240px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .section-kicker { font-size: 12px; font-weight: 850; color: var(--blue); letter-spacing: .06em; text-transform: uppercase; }
    .section-title { font-size: clamp(22px, 3vw, 38px); line-height: 1.02; font-weight: 780; }
    .section-note { color: var(--muted); font-size: 14px; line-height: 1.5; max-width: 780px; }
    .grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; }
    .card {
      grid-column: span 6;
      background: rgba(255,255,255,.92);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 16px 16px 12px;
      min-height: 430px;
      overflow: hidden;
    }
    .card.wide { grid-column: span 12; }
    .card-head { min-height: 54px; display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
    .card-title { font-size: 18px; font-weight: 820; line-height: 1.2; }
    .card-subtitle { color: var(--muted); font-size: 13px; line-height: 1.38; margin-top: 4px; }
    .badge { flex: 0 0 auto; font-size: 11px; font-weight: 780; color: var(--blue); background: #edf3ff; border: 1px solid #d8e6ff; border-radius: 999px; padding: 5px 8px; }
    .chart { width: 100%; height: 310px; margin-top: 8px; overflow: hidden; }
    .wide .chart { height: 360px; }
    svg { width: 100%; height: 100%; display: block; overflow: hidden; }
    .axis text { fill: var(--muted); font-size: 11px; }
    .axis line, .axis path { stroke: #b8bdc9; stroke-width: 1; }
    .grid-line { stroke: #e8eaf0; stroke-width: 1; }
    .axis-title { fill: var(--muted); font-size: 12px; font-weight: 700; }
    .legend { display: flex; flex-wrap: wrap; gap: 7px 10px; margin-top: 9px; min-height: 28px; }
    .legend button { display: inline-flex; align-items: center; gap: 6px; padding: 5px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; color: var(--muted); }
    .legend button.active { color: var(--ink); border-color: #b8bdc9; background: #f7f8fb; }
    .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
    .caption { color: var(--muted); font-size: 12px; line-height: 1.42; margin-top: 8px; border-top: 1px solid #eceef2; padding-top: 8px; }
    .empty { color: var(--muted); background: #f7f8fb; border: 1px dashed #cfd4df; border-radius: var(--radius); padding: 22px; margin-top: 18px; }
    .table-card { grid-column: span 12; background: rgba(255,255,255,.92); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 16px; overflow-x: auto; }
    table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; color: var(--muted); font-size: 11px; letter-spacing: .05em; text-transform: uppercase; border-bottom: 1px solid var(--line); padding: 8px 8px; }
    td { border-bottom: 1px solid #eceef2; padding: 10px 8px; vertical-align: top; line-height: 1.38; }
    .muted { color: var(--muted); }
    .warn { color: #9a3412; }
    .sources { margin-top: 22px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .sources a { color: var(--blue); text-decoration: none; }
    @media (max-width: 980px) {
      .wrap { width: min(100vw - 24px, 760px); padding-top: 14px; }
      .hero { grid-template-columns: 1fr; padding: 22px; }
      .controls { grid-template-columns: 1fr; position: static; }
      .section { grid-template-columns: 1fr; }
      .card, .card.wide { grid-column: span 12; }
      .grid { gap: 12px; }
      .chart, .wide .chart { height: 320px; }
      .kpis { grid-template-columns: 1fr; }
      input[type=date] { width: 150px; max-width: 100%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div>
        <div class="eyebrow">Source-backed dashboard · no blended frequency index</div>
        <h1>AI Compute Price & Cost Trends</h1>
        <p>只展示带日期的价格、成本、用量和 CAPEX 事实。日频/周频/季度事件分开展示；RunPod、Vast、GPUMarkets 等公开源进入真实底表，缺授权的官方历史数据在质量事件里暴露。</p>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="kpi-label">production facts</div><div class="kpi-value" id="kpiFacts">--</div><div class="kpi-note">source-backed rows</div></div>
        <div class="kpi"><div class="kpi-label">date window</div><div class="kpi-value" id="kpiDate">--</div><div class="kpi-note">global filter</div></div>
        <div class="kpi"><div class="kpi-label">OpenRouter archive</div><div class="kpi-value" id="kpiOR">--</div><div class="kpi-note">token-history status</div></div>
        <div class="kpi"><div class="kpi-label">quality events</div><div class="kpi-value" id="kpiQuality">--</div><div class="kpi-note">known gaps visible</div></div>
      </div>
    </header>

    <div class="controls">
      <div class="control-row">
        <label for="startDate">开始</label><input type="date" id="startDate" />
        <label for="endDate">结束</label><input type="date" id="endDate" />
        <button id="resetDates" type="button">重置日期</button>
      </div>
      <div class="source-pill" id="freshness"></div>
    </div>

    <section class="section"><div><div class="section-kicker">L1 · Supply Price</div><div class="section-title">GPU 与云实例价格</div></div><div class="section-note">先看算力本身的价格、深度和分散度。租赁价、订单簿和官方云 VM-hour 分开画，不混成一个指数。</div></section>
    <div class="grid">
      <div class="card wide" id="card-gpu-rental"></div>
      <div class="card" id="card-gpu-fixing"></div>
      <div class="card" id="card-orderbook"></div>
      <div class="card wide" id="card-cloud"></div>
    </div>

    <section class="section"><div><div class="section-kicker">L2 · Demand And Unit Economics</div><div class="section-title">OpenRouter、Token 与模型成本</div></div><div class="section-note">再看应用需求和模型单位经济。OpenRouter 官方 daily token/API key 缺失时，使用 token-history archive 和公开前端 proxy，并明确标注来源。</div></section>
    <div class="grid">
      <div class="card wide" id="card-or-token"></div>
      <div class="card wide" id="card-or-proxy"></div>
      <div class="card wide" id="card-token-price"></div>
      <div class="card" id="card-model-price"></div>
      <div class="card" id="card-multimodal"></div>
      <div class="card wide" id="card-commercial"></div>
    </div>

    <section class="section"><div><div class="section-kicker">L3 · CAPEX Confirmation</div><div class="section-title">云厂商 CAPEX 官方说明</div></div><div class="section-note">CAPEX 是确认层，不和日频价格混权重。美国 5 家来自 SEC/官方事件，中国厂商只展示 source-backed 或明确口径限制。</div></section>
    <div class="grid">
      <div class="table-card" id="capex-table"></div>
      <div class="table-card" id="quality-table"></div>
    </div>
    <div class="sources" id="sources"></div>
  </div>

  <script>
  const DATA = __DATA__;
  const palette = ["#002fa7","#5b8def","#111827","#737373","#0f9f8f","#ff9500","#7c3aed","#d92d20","#94a3b8","#155e75"];
  const state = { hidden: {}, start: DATA.meta.min_date, end: DATA.meta.max_date };

  const fmt = {
    money: v => "$" + Number(v).toLocaleString(undefined, {maximumFractionDigits: 2}),
    compact: v => Number(v).toLocaleString(undefined, {maximumFractionDigits: v >= 100 ? 0 : 2}),
    tokensT: v => Number(v).toLocaleString(undefined, {maximumFractionDigits: 2}) + "T",
    pct: v => Number(v).toLocaleString(undefined, {maximumFractionDigits: 1}) + "%",
  };

  function byDate(row) { return row.date >= state.start && row.date <= state.end; }
  function seriesNames(rows) { return Array.from(new Set(rows.map(d => d.series || d.gpu).filter(Boolean))); }
  function visibleRows(id, rows, key="series") {
    const hidden = state.hidden[id] || {};
    return rows.filter(byDate).filter(d => !hidden[d[key]]);
  }
  function clear(el) { el.innerHTML = ""; }
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m])); }

  function card(id, title, subtitle, badge, caption) {
    const el = document.getElementById(id);
    clear(el);
    el.innerHTML = `<div class="card-head"><div><div class="card-title">${esc(title)}</div><div class="card-subtitle">${esc(subtitle)}</div></div><div class="badge">${esc(badge)}</div></div><div class="chart"></div><div class="legend"></div><div class="caption">${esc(caption)}</div>`;
    return {root: el, chart: el.querySelector(".chart"), legend: el.querySelector(".legend")};
  }
  function showEmpty(target, text) { target.chart.innerHTML = `<div class="empty">${esc(text)}</div>`; target.legend.innerHTML = ""; }

  function scaleLinear(domain, range) {
    const [d0,d1] = domain; const [r0,r1] = range;
    const span = d1 - d0 || 1;
    return v => r0 + (v - d0) * (r1 - r0) / span;
  }
  function dateMs(d) { return new Date(d + "T00:00:00Z").getTime(); }
  function niceY(values) {
    let min = Math.min(...values, 0), max = Math.max(...values, 1);
    if (!isFinite(min) || !isFinite(max)) return [0, 1];
    if (min === max) { min *= .9; max *= 1.1; }
    const pad = (max - min) * .12;
    return [Math.max(0, min - pad), max + pad];
  }
  function ticks(min, max, count=5) {
    const out = [];
    for (let i=0; i<count; i++) out.push(min + (max-min) * i / (count-1));
    return out;
  }
  function renderLegend(id, target, names, key="series") {
    if (!state.hidden[id]) state.hidden[id] = {};
    target.legend.innerHTML = names.map((name, i) => {
      const active = !state.hidden[id][name];
      return `<button type="button" data-name="${esc(name)}" class="${active ? "active" : ""}"><span class="dot" style="background:${palette[i % palette.length]}"></span>${esc(name)}</button>`;
    }).join("");
    target.legend.querySelectorAll("button").forEach(btn => {
      btn.addEventListener("click", () => {
        const name = btn.dataset.name;
        state.hidden[id][name] = !state.hidden[id][name];
        renderAll();
      });
    });
  }
  function renderLineChart(id, rows, target, opts) {
    const names = seriesNames(rows).slice(0, opts.maxSeries || 10);
    renderLegend(id, target, names);
    const filtered = visibleRows(id, rows.filter(d => names.includes(d.series)));
    if (filtered.length < 1) return showEmpty(target, opts.empty || "日期范围内没有可展示数据。");
    const width = target.chart.clientWidth || 900, height = target.chart.clientHeight || 320;
    const m = {l: 64, r: 20, t: 18, b: 46};
    const xs = filtered.map(d => dateMs(d.date)), ys = filtered.map(d => Number(d.value));
    const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [m.l, width-m.r]);
    const [y0,y1] = niceY(ys); const y = scaleLinear([y0,y1], [height-m.b, m.t]);
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(opts.title || "")}">`;
    ticks(y0,y1).forEach(t => { svg += `<line class="grid-line" x1="${m.l}" y1="${y(t)}" x2="${width-m.r}" y2="${y(t)}"/><text x="${m.l-8}" y="${y(t)+4}" text-anchor="end" fill="#6e6e73" font-size="11">${opts.yFormat ? opts.yFormat(t) : fmt.compact(t)}</text>`; });
    const dateVals = Array.from(new Set(filtered.map(d => d.date))).sort();
    const xTickDates = dateVals.length <= 6 ? dateVals : [dateVals[0], dateVals[Math.floor(dateVals.length*.25)], dateVals[Math.floor(dateVals.length*.5)], dateVals[Math.floor(dateVals.length*.75)], dateVals[dateVals.length-1]];
    xTickDates.forEach(d => { svg += `<text x="${x(dateMs(d))}" y="${height-18}" text-anchor="middle" fill="#6e6e73" font-size="11">${d.slice(5)}</text>`; });
    svg += `<text class="axis-title" x="${width/2}" y="${height-1}" text-anchor="middle">${esc(opts.xTitle || "日期")}</text><text class="axis-title" transform="translate(15 ${height/2}) rotate(-90)" text-anchor="middle">${esc(opts.yTitle || "")}</text>`;
    names.forEach((name, i) => {
      const group = filtered.filter(d => d.series === name).sort((a,b) => a.date.localeCompare(b.date));
      if (!group.length) return;
      const path = group.map((d,j) => `${j ? "L" : "M"}${x(dateMs(d.date)).toFixed(1)},${y(Number(d.value)).toFixed(1)}`).join(" ");
      const color = palette[i % palette.length];
      if (dateVals.length >= 3 && group.length >= 2) svg += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.4"/>`;
      group.forEach(d => { svg += `<circle cx="${x(dateMs(d.date))}" cy="${y(Number(d.value))}" r="3" fill="${color}"><title>${esc(name)} · ${d.date} · ${opts.tipFormat ? opts.tipFormat(d.value) : fmt.compact(d.value)}</title></circle>`; });
      const last = group[group.length-1];
      const showDirectLabel = opts.directLabels === true || (opts.directLabels !== false && names.length <= 5 && dateVals.length >= 3);
      if (showDirectLabel) {
        const lx = x(dateMs(last.date));
        const anchor = lx > width - m.r - 120 ? "end" : "start";
        const tx = anchor === "end" ? width - m.r - 4 : lx + 8;
        svg += `<text x="${tx}" y="${y(Number(last.value))+4}" text-anchor="${anchor}" fill="${color}" font-size="11" font-weight="700">${esc(name.slice(0,20))}</text>`;
      }
    });
    svg += `</svg>`;
    target.chart.innerHTML = svg;
  }

  function renderFixingChart(id, rows, target) {
    const within = rows.filter(byDate).filter(d => d.price != null);
    const spot = within.filter(d => d.tenor === "spot");
    const base = spot.length ? spot : within;
    if (!base.length) return showEmpty(target, "日期范围内没有 GPUMarkets fixing。");
    const latest = Array.from(new Map(base.sort((a,b) => a.date.localeCompare(b.date)).map(d => [d.gpu, d])).values())
      .sort((a,b) => Number(a.price) - Number(b.price)).slice(0, 10);
    const width = target.chart.clientWidth || 700, height = target.chart.clientHeight || 300;
    const m = {l: 76, r: 30, t: 20, b: 46};
    const xMax = Math.max(...latest.map(d => Number(d.price))) * 1.18;
    const x = scaleLinear([0, xMax], [m.l, width-m.r]);
    const rowH = (height-m.t-m.b) / Math.max(1, latest.length);
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="GPUMarkets fixing and 30 day delta">`;
    ticks(0, xMax).forEach(t => { svg += `<line class="grid-line" x1="${x(t)}" y1="${m.t}" x2="${x(t)}" y2="${height-m.b}"/><text x="${x(t)}" y="${height-20}" text-anchor="middle" fill="#6e6e73" font-size="11">${fmt.money(t)}</text>`; });
    latest.forEach((d,i) => {
      const y = m.t + rowH*i + rowH/2;
      const delta = d.delta30d == null ? "" : `${Number(d.delta30d).toFixed(1)}%`;
      const color = d.delta30d == null ? "#737373" : (Number(d.delta30d) > 0 ? "#ff9500" : "#002fa7");
      svg += `<text x="${m.l-10}" y="${y+4}" text-anchor="end" fill="#1d1d1f" font-size="12" font-weight="760">${esc(d.gpu)}</text>`;
      svg += `<line x1="${m.l}" x2="${x(Number(d.price))}" y1="${y}" y2="${y}" stroke="#d8dbe2" stroke-width="2"/>`;
      svg += `<circle cx="${x(Number(d.price))}" cy="${y}" r="6" fill="${color}"><title>${esc(d.gpu)} · ${d.date} · ${fmt.money(d.price)} · 30D ${delta} · obs ${fmt.compact(d.observations || 0)}</title></circle>`;
      svg += `<text x="${Math.min(width-m.r, x(Number(d.price))+10)}" y="${y+4}" fill="${color}" font-size="11" font-weight="760">${fmt.money(d.price)} / ${esc(delta || "n/a")}</text>`;
    });
    svg += `<text class="axis-title" x="${width/2}" y="${height-2}" text-anchor="middle">USD / GPU hour</text><text class="axis-title" transform="translate(15 ${height/2}) rotate(-90)" text-anchor="middle">GPU</text></svg>`;
    target.chart.innerHTML = svg;
    target.legend.innerHTML = `<span class="muted">点 = latest ${spot.length ? "spot" : "available"} fixing；标签 = price / 30D delta；source frequency = current fixing + deltas。</span>`;
  }

  function renderRangeChart(id, rows, target) {
    const data = rows.filter(byDate).filter(d => d.low || d.median || d.high).slice(0, 12);
    if (!data.length) return showEmpty(target, "日期范围内没有聚合价格区间。");
    const width = target.chart.clientWidth || 700, height = target.chart.clientHeight || 300;
    const m = {l: 76, r: 28, t: 22, b: 42};
    const vals = data.flatMap(d => [d.low, d.median, d.high]).filter(v => v != null);
    const x = scaleLinear([0, Math.max(...vals) * 1.12], [m.l, width-m.r]);
    const rowH = (height-m.t-m.b) / Math.max(1, data.length);
    let svg = `<svg viewBox="0 0 ${width} ${height}">`;
    ticks(0, Math.max(...vals) * 1.12).forEach(t => { svg += `<line class="grid-line" x1="${x(t)}" y1="${m.t}" x2="${x(t)}" y2="${height-m.b}"/><text x="${x(t)}" y="${height-18}" text-anchor="middle" fill="#6e6e73" font-size="11">${fmt.money(t)}</text>`; });
    data.forEach((d,i) => {
      const y = m.t + rowH*i + rowH/2;
      svg += `<text x="${m.l-10}" y="${y+4}" text-anchor="end" fill="#1d1d1f" font-size="12" font-weight="700">${esc(d.gpu)}</text>`;
      if (d.low != null && d.high != null) svg += `<line x1="${x(d.low)}" x2="${x(d.high)}" y1="${y}" y2="${y}" stroke="#002fa7" stroke-width="5" stroke-linecap="round"/>`;
      if (d.median != null) svg += `<rect x="${x(d.median)-5}" y="${y-5}" width="10" height="10" transform="rotate(45 ${x(d.median)} ${y})" fill="#002fa7"><title>${esc(d.gpu)} median ${fmt.money(d.median)}</title></rect>`;
    });
    svg += `<text class="axis-title" x="${width/2}" y="${height-1}" text-anchor="middle">USD / GPU hour</text></svg>`;
    target.chart.innerHTML = svg;
    target.legend.innerHTML = `<span class="muted">横线 = low/high，蓝钻 = median；该源当前为截面价格带。</span>`;
  }

  function renderOrderbookChart(id, rows, target) {
    const sources = Array.from(new Set(rows.map(d => d.source).filter(Boolean)));
    renderLegend(id, target, sources, "source");
    const hidden = state.hidden[id] || {};
    const data = rows.filter(byDate).filter(d => d.price != null && d.offers != null && !hidden[d.source]);
    if (!data.length) return showEmpty(target, "日期范围内没有订单簿快照。");
    const latestBySeries = Array.from(new Map(data.sort((a,b) => a.date.localeCompare(b.date)).map(d => [`${d.gpu}-${d.source}`, d])).values())
      .sort((a,b) => a.gpu.localeCompare(b.gpu) || a.price-b.price).slice(0, 14);
    const width = target.chart.clientWidth || 700, height = target.chart.clientHeight || 300;
    const m = {l: 110, r: 28, t: 20, b: 46};
    const xMax = Math.max(...latestBySeries.map(d => Number(d.price))) * 1.18;
    const x = scaleLinear([0, xMax], [m.l, width-m.r]);
    const rowH = (height-m.t-m.b) / Math.max(1, latestBySeries.length);
    const maxOffers = Math.max(...latestBySeries.map(d => Number(d.offers) || 1));
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Available GPU orderbook by source">`;
    ticks(0, xMax).forEach(t => { svg += `<line class="grid-line" x1="${x(t)}" y1="${m.t}" x2="${x(t)}" y2="${height-m.b}"/><text x="${x(t)}" y="${height-20}" text-anchor="middle" fill="#6e6e73" font-size="11">${fmt.money(t)}</text>`; });
    latestBySeries.forEach((d,i) => {
      const y = m.t + rowH*i + rowH/2;
      const r = 4 + 13 * Math.sqrt((Number(d.offers) || 1) / maxOffers);
      const color = palette[Math.max(0, sources.indexOf(d.source)) % palette.length];
      svg += `<text x="${m.l-10}" y="${y+4}" text-anchor="end" fill="#1d1d1f" font-size="11" font-weight="720">${esc(`${d.gpu} · ${d.source}`)}</text><circle cx="${x(d.price)}" cy="${y}" r="${r}" fill="${color}" fill-opacity=".78" stroke="#fff"><title>${esc(d.gpu)} · ${esc(d.source)} · ${d.date} · ${fmt.money(d.price)} · depth ${fmt.compact(d.offers)}</title></circle>`;
      svg += `<text x="${Math.min(width-m.r, x(d.price)+8)}" y="${y+4}" fill="${color}" font-size="10" font-weight="720">${fmt.money(d.price)}</text>`;
    });
    svg += `<text class="axis-title" x="${width/2}" y="${height-2}" text-anchor="middle">USD / GPU hour</text><text class="axis-title" transform="translate(16 ${height/2}) rotate(-90)" text-anchor="middle">GPU / Source</text></svg>`;
    target.chart.innerHTML = svg;
  }

  function renderSplitLineChart(id, rows, target, metricA, metricB, opts) {
    const a = rows.filter(d => d.metric === metricA).map(d => ({date:d.date, series:d.series, value:d.value}));
    const b = rows.filter(d => d.metric === metricB).map(d => ({date:d.date, series:d.series, value:d.value}));
    target.chart.innerHTML = `<div style="display:grid;grid-template-columns:1fr;gap:12px;height:100%"><div class="split-a" style="min-height:145px"></div><div class="split-b" style="min-height:145px"></div></div>`;
    renderLineChart(id+"_a", a, {chart: target.chart.querySelector(".split-a"), legend: target.legend}, {maxSeries: opts.maxSeries || 6, yTitle: opts.yTitleA, tipFormat: opts.formatA, yFormat: opts.formatA, empty: opts.emptyA});
    renderLineChart(id+"_b", b, {chart: target.chart.querySelector(".split-b"), legend: document.createElement("div")}, {maxSeries: opts.maxSeries || 6, yTitle: opts.yTitleB, tipFormat: opts.formatB, yFormat: opts.formatB, empty: opts.emptyB});
  }

  function renderCapexTables() {
    const el = document.getElementById("capex-table");
    const us = DATA.capexUs || [], cn = DATA.capexChina || [];
    let html = `<div class="card-head"><div><div class="card-title">CAPEX 官方确认层</div><div class="card-subtitle">美国 5 家 + 中国云厂商 source-backed 事实；非云 CAPEX 或 R&D 会明确标口径。</div></div><div class="badge">official / source-backed</div></div>`;
    html += `<table><thead><tr><th>区域</th><th>公司</th><th>指标</th><th>数值</th><th>期间</th><th>口径</th></tr></thead><tbody>`;
    us.forEach(r => { html += `<tr><td>美国</td><td>${esc(r.company || r.ticker)}</td><td>${esc(r.ticker)}</td><td>${fmt.money(r.capex_value)}B</td><td>${esc(r.fiscal_period || r.period_end)}</td><td><a href="${esc(r.source_url)}">SEC companyfacts</a></td></tr>`; });
    cn.forEach(r => { html += `<tr><td>中国</td><td>${esc(r.company)}</td><td>${esc(r.metric)}</td><td>${Number(r.value).toLocaleString(undefined,{maximumFractionDigits:2})} ${esc(r.unit)}</td><td>${esc(r.date)}</td><td>${esc((r.notes || "").slice(0,180))}</td></tr>`; });
    html += `</tbody></table>`;
    el.innerHTML = html;

    const q = document.getElementById("quality-table");
    const rows = DATA.qualityEvents || [];
    let qh = `<div class="card-head"><div><div class="card-title">失败暴露与授权缺口</div><div class="card-subtitle">这里不是装饰，是判断边界：缺授权的数据不能被替代源伪装。</div></div><div class="badge">quality events</div></div>`;
    qh += `<table><thead><tr><th>严重度</th><th>影响字段</th><th>信息</th><th>时间</th></tr></thead><tbody>`;
    rows.forEach(r => { qh += `<tr><td class="warn">${esc(r.severity)}</td><td>${esc(r.affected_key)}</td><td>${esc(r.message)}</td><td>${esc(String(r.fetched_at || "").slice(0,16))}</td></tr>`; });
    qh += `</tbody></table>`;
    q.innerHTML = qh;
  }

  function renderSources() {
    const meta = DATA.openrouterTokenArchive?.meta || {};
    document.getElementById("sources").innerHTML = `Sources: production DuckDB ${esc(DATA.meta.db_path)}; GPUMarkets fixings; Vast.ai bundles API; RunPod gpuTypes GraphQL; OpenRouter public frontend rankings; Socialpranker/token-history archive (${esc(meta.first_date || "")} - ${esc(meta.last_date || "")}); ComputePrices/GPUPerHour/GPUs.io/AIMultiple/GetDeploying; LiteLLM/models.dev/OpenRouter Models; ARR.club/Ramp/BytePlus/seedance2.ai; SEC companyfacts and official cloud disclosures.`;
  }

  function renderAll() {
    document.getElementById("kpiFacts").textContent = Number(DATA.meta.production_market_facts || 0).toLocaleString();
    document.getElementById("kpiQuality").textContent = Number(DATA.meta.quality_events || 0).toLocaleString();
    document.getElementById("kpiDate").textContent = `${state.start} / ${state.end}`;
    const orMeta = DATA.openrouterTokenArchive?.meta || {};
    document.getElementById("kpiOR").textContent = orMeta.status === "fetched" ? `${orMeta.days} days` : orMeta.status || "missing";
    document.getElementById("freshness").textContent = `latest fetch ${String(DATA.meta.latest_fetch || "").replace("T"," ").slice(0,16)} UTC`;

    renderLineChart("gpuRental", DATA.gpuRental || [], card("card-gpu-rental", "Exhibit 1 · GPU 可比租赁价格趋势", "同一公开数据层、同一计算口径的短期日度趋势。", "daily comparable", "来源：ComputePrices public 7-day tier；仅展示 H100、H200、B200 的可比日序列，不与跨供应商截面价混合。"), {maxSeries: 8, yTitle: "USD / GPU hour", tipFormat: fmt.money, yFormat: fmt.money, directLabels: false});
    renderFixingChart("gpuFixing", DATA.gpuMarketFixing || [], card("card-gpu-fixing", "Exhibit 2 · GPUMarkets fixing 与 30D 变化", "当前 fixing、30D delta 与样本数；数据不足时不画假趋势线。", "current fixing", "来源：GPUMarkets fixings.csv；显示 spot fixing 优先，frequency=current fixing + 1D/7D/30D deltas。"));
    renderOrderbookChart("orderbook", DATA.orderbook || [], card("card-orderbook", "Exhibit 3 · 可用订单薄价格与深度", "GPUPerHour、Vast、RunPod on-demand 按 source 分开展示。", "snapshot", "来源：GPUPerHour available=true、Vast verified bundles、RunPod gpuTypes on-demand/uninterruptable；不混入 spot 与最低 bid，气泡大小=offers/capacity proxy。"));
    renderLineChart("cloudInstance", DATA.cloudInstance || [], card("card-cloud", "Exhibit 4 · 官方云 GPU 实例价格", "按抓取日展示 AWS/Azure VM-hour；频率按 dashboard 快照日对齐。", "crawl-day", "来源：Azure Retail Prices API、AWS current Spot JSON；VM-hour 不和 per-GPU-hour 混算。"), {maxSeries: 6, yTitle: "USD / VM hour", tipFormat: fmt.money, yFormat: fmt.money, directLabels: false, empty: "官方云实例价格当前快照点不足，无法形成连续趋势。"});

    renderLineChart("orTokens", DATA.openrouterTokenArchive?.series || [], card("card-or-token", "Exhibit 5 · OpenRouter 模型 token 用量", "GitHub archive 的模型日 token 趋势，单位为万亿 tokens。", "daily archive", `来源：Socialpranker/token-history；最新 ${orMeta.last_date || "unknown"}，不是官方实时 API。`), {maxSeries: 6, yTitle: "trillion tokens", tipFormat: fmt.tokensT, yFormat: fmt.tokensT, directLabels: false});
    renderLineChart("orProxy", DATA.openrouterProxy || [], card("card-or-proxy", "Exhibit 6 · OpenRouter 公开 activity proxy", "工具调用与图像处理 count；不是总文本请求。", "weekly proxy", "来源：openrouter.ai frontend rankings endpoint；可作为活跃度方向 proxy。"), {maxSeries: 2, yTitle: "counts", tipFormat: fmt.compact, yFormat: fmt.compact});
    renderLineChart("tokenPrice", DATA.tokenPrice || [], card("card-token-price", "Exhibit 7 · 模型输出 token 价格", "公开价格目录的 output USD / 1M tokens。", "catalog snapshots", "来源：OpenRouter Models、LiteLLM、models.dev、ComputePrices LLM；按快照日期展示，不代表成交折扣。"), {maxSeries: 6, yTitle: "USD / 1M output tokens", tipFormat: fmt.money, yFormat: fmt.money, directLabels: false});
    renderLineChart("modelPrice", DATA.modelPrice || [], card("card-model-price", "Exhibit 8 · 高质量模型输出成本", "质量分 ≥80 的低价模型组。", "quality proxy", "来源：CostGoat public proxy；不替代 Artificial Analysis。"), {maxSeries: 5, yTitle: "USD / 1M output tokens", tipFormat: fmt.money, yFormat: fmt.money, directLabels: false});
    renderSplitLineChart("multimodal", DATA.multimodal || [], card("card-multimodal", "Exhibit 9 · 多模态生成成本", "官方 USD/token 与第三方 credits 分轴。", "split units", "来源：BytePlus ModelArk 与 seedance2.ai；两种单位不混算。"), "video_generation_price_per_1m_tokens", "video_generation_5s_example_credits", {maxSeries: 4, yTitleA: "USD / 1M tokens", yTitleB: "credits / 5s", formatA: fmt.money, formatB: fmt.compact, emptyA: "无 USD/token 趋势点", emptyB: "无 credits 趋势点"});
    renderSplitLineChart("commercial", DATA.commercialization || [], card("card-commercial", "Exhibit 10 · ARR 与商业化信号", "ARR public signal 和企业采用率分轴。", "commercial", "来源：ARR.club public homepage 与 Ramp AI Index；采用率不是收入。"), "arr", "business_adoption_share", {maxSeries: 5, yTitleA: "ARR, USD B", yTitleB: "adoption %", formatA: v => "$"+fmt.compact(v)+"B", formatB: fmt.pct});

    renderCapexTables();
    renderSources();
  }

  function init() {
    const s = document.getElementById("startDate"), e = document.getElementById("endDate");
    s.min = DATA.meta.min_date; s.max = DATA.meta.max_date; s.value = state.start;
    e.min = DATA.meta.min_date; e.max = DATA.meta.max_date; e.value = state.end;
    function updateDates() {
      state.start = s.value <= e.value ? s.value : e.value;
      state.end = s.value <= e.value ? e.value : s.value;
      renderAll();
    }
    s.addEventListener("change", updateDates);
    e.addEventListener("change", updateDates);
    document.getElementById("resetDates").addEventListener("click", () => { state.start = DATA.meta.min_date; state.end = DATA.meta.max_date; s.value = state.start; e.value = state.end; renderAll(); });
    window.addEventListener("resize", () => renderAll());
    renderAll();
  }
  init();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
