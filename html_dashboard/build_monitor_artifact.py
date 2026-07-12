#!/usr/bin/env python3
"""Build the Phase 5 portable dashboard artifact from production-only views."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "ai_compute_tracker_production.db"
DEFAULT_STATE = ROOT / "tracker_data" / "thesis_states" / "latest-thesis-state.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "v3" / "artifact.json"
CORE_GPUS = ("H100", "H200", "B200")


def scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    result = con.execute(sql)
    columns = [item[0] for item in result.description]
    return [{column: scalar(value) for column, value in zip(columns, row)} for row in result.fetchall()]


def source(source_id: str, label: str, sql: str, tables: list[str], generated_at: str,
           filters: list[str], definitions: list[str]) -> dict[str, Any]:
    return {
        "id": source_id,
        "label": label,
        "query": {
            "engine": "duckdb",
            "sql": sql.strip(),
            "description": label,
            "executed_at": generated_at,
            "tables_used": tables,
            "filters": filters,
            "metric_definitions": definitions,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    state_report = json.loads(args.state.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    con = duckdb.connect(str(args.db), read_only=True)

    states = []
    for clock in state_report["clocks"]:
        states.append({
            "clock_id": clock["clock_id"],
            "state": clock["state"],
            "frequency": clock["natural_frequency"],
            "next_proof": clock["next_proof_point"],
            "blocker": ", ".join(clock.get("blockers", [])) or "none",
        })
    state_values = []
    for item in states:
        escaped = [str(item[key]).replace("'", "''") for key in ("clock_id", "state", "frequency", "next_proof", "blocker")]
        state_values.append("('" + "','".join(escaped) + "')")
    state_sql = (
        "SELECT * FROM (VALUES " + ",".join(state_values) + ") "
        "AS latest_thesis_state(clock_id, state, frequency, next_proof, blocker)"
    )

    gpu_progress_sql = """
        WITH base AS (
          SELECT entity AS gpu,
                 MAX(valid_dates) AS valid_days,
                 COUNT(*) AS exact_series,
                 COUNT(DISTINCT vendor) AS venues,
                 SUM(CASE WHEN eligible_for_chart THEN 1 ELSE 0 END) AS chart_ready_series,
                 STRING_AGG(DISTINCT chart_reason_code, ', ') AS blocker
          FROM series_quality
          WHERE track = 'gpu_rental'
            AND evidence_class = 'matched_venue_series'
            AND entity IN ('H100', 'H200', 'B200')
          GROUP BY entity
        )
        SELECT gpu, 'Observed history' AS measure, valid_days AS days,
               valid_days, 10 AS chart_threshold_days, exact_series, venues,
               chart_ready_series, blocker,
               CASE gpu WHEN 'H100' THEN 1 WHEN 'H200' THEN 2 ELSE 3 END AS sort_order
        FROM base
        UNION ALL
        SELECT gpu, '10-day chart threshold' AS measure, 10 AS days,
               valid_days, 10 AS chart_threshold_days, exact_series, venues,
               chart_ready_series, blocker,
               CASE gpu WHEN 'H100' THEN 1 WHEN 'H200' THEN 2 ELSE 3 END AS sort_order
        FROM base
        ORDER BY sort_order, measure DESC
    """
    gpu_progress = rows(con, gpu_progress_sql)

    depth_sql = """
        WITH latest AS (
          SELECT MAX(date) AS date FROM canonical_observation
          WHERE track = 'gpu_available_offer' AND period_complete
        ), offers AS (
          SELECT canonical_observation.date AS date, entity AS gpu, SUM(value) AS offers,
                 COUNT(DISTINCT source_id) AS depth_sources
          FROM canonical_observation, latest
          WHERE track = 'gpu_available_offer' AND metric = 'available_offer_count'
            AND canonical_observation.date = latest.date AND period_complete
          GROUP BY canonical_observation.date, entity
        ), prices AS (
          SELECT canonical_observation.date AS date, entity AS gpu,
                 QUANTILE_CONT(value, 0.25) AS price_p25,
                 MEDIAN(value) AS price_p50,
                 QUANTILE_CONT(value, 0.75) AS price_p75,
                 COUNT(DISTINCT series_id) AS exact_configs,
                 COUNT(DISTINCT vendor) AS price_venues
          FROM canonical_observation, latest
          WHERE track = 'gpu_rental' AND evidence_class = 'matched_venue_series'
            AND canonical_observation.date = latest.date AND period_complete
          GROUP BY canonical_observation.date, entity
        )
        SELECT o.date, o.gpu, o.offers, o.depth_sources,
               ROUND(p.price_p25, 3) AS price_p25,
               ROUND(p.price_p50, 3) AS price_p50,
               ROUND(p.price_p75, 3) AS price_p75,
               p.exact_configs, p.price_venues,
               '$' || PRINTF('%.2f', p.price_p25) || ' to $' ||
                 PRINTF('%.2f', p.price_p75) AS price_range,
               '$' || PRINTF('%.2f', p.price_p50) || ' · P25-P75 $' ||
                 PRINTF('%.2f', p.price_p25) || '-$' || PRINTF('%.2f', p.price_p75) AS price_summary,
               o.gpu || ' · ' || CAST(o.offers AS VARCHAR) || ' offers · median $' ||
                 PRINTF('%.2f', p.price_p50) || ' · P25-P75 $' ||
                 PRINTF('%.2f', p.price_p25) || '-$' || PRINTF('%.2f', p.price_p75) AS depth_summary
        FROM offers o LEFT JOIN prices p USING (date, gpu)
        WHERE o.gpu IN ('A100','H100','H200','B200','B300','L40S','MI300X')
        ORDER BY o.offers DESC
    """
    depth = rows(con, depth_sql)

    cloud_sql = """
        WITH latest_per_series AS (
          SELECT *, ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY fetched_at DESC, date DESC) AS rn
          FROM canonical_observation
          WHERE track = 'cloud_instance_price' AND period_complete
            AND entity IN ('A100','H100','H200','Blackwell GPU')
        ), comparable AS (
          SELECT vendor, entity AS gpu, sub_entity AS sku, dimension AS billing,
                 value AS vm_hour_usd, date, source_id,
                 ROW_NUMBER() OVER (
                   PARTITION BY vendor, entity, dimension ORDER BY value ASC, sub_entity
                 ) AS price_rank
          FROM latest_per_series WHERE rn = 1
        )
        SELECT vendor, gpu, sku, billing, ROUND(vm_hour_usd, 3) AS vm_hour_usd,
               date, source_id, vendor || ' · ' || gpu || ' · ' ||
                 REGEXP_REPLACE(REGEXP_REPLACE(sku, '^Standard_', ''), '_v[0-9]+$', '') AS offer
        FROM comparable
        WHERE price_rank = 1
        ORDER BY vm_hour_usd DESC
        LIMIT 14
    """
    cloud = rows(con, cloud_sql)

    model_change_sql = """
        WITH ranked AS (
          SELECT date, vendor, entity AS model, sub_entity AS venue, metric,
                 ROUND(prior_value, 4) AS prior_price,
                 ROUND(value, 4) AS current_price,
                 ROUND(change_pct, 2) AS change_pct, unit, source_id,
                 ROW_NUMBER() OVER (
                   PARTITION BY LOWER(vendor), entity, metric
                   ORDER BY date DESC, ABS(change_pct) DESC
                 ) AS rn
          FROM event_observation
          WHERE track = 'token_price' AND event_type = 'price_change'
            AND vendor IN ('OpenAI','Anthropic','Google','DeepSeek','Moonshot','Meta','Alibaba')
            AND sub_entity IN ('OpenRouter','Google Cloud','Deep Infra','IO.NET','Scaleway')
            AND ABS(change_pct) >= 5
        )
        SELECT date, vendor, model, venue, metric, prior_price, current_price,
               change_pct, unit, source_id,
               vendor || ' · ' || model || ' · ' ||
                 CASE metric WHEN 'input_price_per_1m_tokens' THEN 'Input'
                             WHEN 'output_price_per_1m_tokens' THEN 'Output'
                             ELSE 'Cached input' END AS price_line
        FROM ranked WHERE rn = 1
        ORDER BY ABS(change_pct) DESC, vendor, model
        LIMIT 16
    """
    model_changes = rows(con, model_change_sql)

    demand_sql = """
        SELECT date, metric, SUM(value) AS activity_count,
               COUNT(DISTINCT series_id) AS included_series
        FROM line_ready_observation
        WHERE track = 'openrouter_usage'
          AND metric IN ('tool_call_count','image_processing_count')
        GROUP BY date, metric
        ORDER BY date, metric
    """
    demand_raw = rows(con, demand_sql)
    by_metric: dict[str, list[dict[str, Any]]] = {}
    for row in demand_raw:
        by_metric.setdefault(row["metric"], []).append(row)
    demand: list[dict[str, Any]] = []
    metric_labels = {"tool_call_count": "Tool calls", "image_processing_count": "Image processing"}
    for metric, metric_rows in by_metric.items():
        values: list[float] = []
        averages: list[tuple[dict[str, Any], float]] = []
        for row in metric_rows:
            value = float(row["activity_count"])
            values.append(value)
            if len(values) >= 4:
                average = sum(values[-4:]) / 4
                averages.append((row, average))
        base = averages[0][1] if averages else 1.0
        for row, average in averages:
            demand.append({
                    **row,
                    "activity_count": round(average, 2),
                    "series": metric_labels[metric] + " · 4W MA",
                    "index_value": round(average / base * 100, 2),
            })

    capex_sql = """
        SELECT date, vendor AS company, ROUND(value, 2) AS capex_usd_b,
               unit, dimension AS fiscal_period, source_id
        FROM event_observation
        WHERE track = 'cloud_capex_actual' AND event_type = 'initial_observation'
          AND date = DATE '2026-03-31'
        ORDER BY capex_usd_b DESC
    """
    capex = rows(con, capex_sql)

    commitment_sql = """
        WITH labeled AS (
          SELECT e.date, e.track,
                 CASE e.vendor WHEN 'ORCL' THEN 'Oracle' WHEN 'AMZN' THEN 'Amazon'
                               WHEN 'GOOGL' THEN 'Alphabet' WHEN 'META' THEN 'Meta'
                               WHEN 'MSFT' THEN 'Microsoft' ELSE e.vendor END AS company,
                 e.metric, ROUND(e.value, 3) AS value, e.unit,
                 COALESCE(p.fiscal_period, e.dimension) AS dimension,
                 e.source_id, e.source_url,
                 CASE
                   WHEN e.track = 'cloud_capex_actual' THEN 'CAPEX actual'
                   WHEN e.metric = 'remaining_performance_obligations' THEN 'RPO'
                   WHEN e.metric = 'cloud_backlog' THEN 'Cloud backlog'
                   WHEN e.metric = 'ttm_capex_increase_reflects_ai_investment' THEN 'TTM CAPEX increase linked to AI'
                   WHEN e.metric = 'fy2026_capex_guidance_previous_low' THEN 'Prior FY2026 CAPEX guidance low'
                   WHEN e.metric = 'fy2026_capex_guidance_previous_high' THEN 'Prior FY2026 CAPEX guidance high'
                   WHEN e.metric = 'fy2026_capex_guidance_low' THEN 'Current FY2026 CAPEX guidance low'
                   WHEN e.metric = 'fy2026_capex_guidance_high' THEN 'Current FY2026 CAPEX guidance high'
                   WHEN e.metric = 'capex_short_lived_assets_comment' THEN 'Short-lived asset CAPEX comment'
                   WHEN e.metric = 'customer_demand_exceeds_supply' THEN 'Demand exceeds supply comment'
                   WHEN e.metric = 'capex_quarterly' THEN 'Quarterly CAPEX actual'
                   WHEN e.metric = 'ai_cloud_capex_ttm' THEN 'AI/cloud CAPEX TTM'
                   WHEN e.metric = 'rd_spending' THEN 'R&D context (not CAPEX)'
                   WHEN e.metric = 'cloud_revenue_including_other_segments' THEN 'Cloud revenue context (not CAPEX)'
                   ELSE REPLACE(e.metric, '_', ' ')
                 END AS signal
          FROM event_observation e
          LEFT JOIN production_capex_actuals p
            ON e.track = 'cloud_capex_actual' AND e.vendor = p.company AND e.date = p.period_end
          WHERE e.track IN ('cloud_capex_actual','cloud_official_event','china_cloud_capex')
        )
        SELECT *,
               CAST(value AS VARCHAR) || ' ' || unit ||
                 CASE WHEN dimension IS NULL OR dimension = '' THEN '' ELSE ' · ' || dimension END AS observed,
               CAST(date AS VARCHAR) || ' · ' || company || ' · ' || signal || ' · ' ||
                 CAST(value AS VARCHAR) || ' ' || unit ||
                 CASE WHEN dimension IS NULL OR dimension = '' THEN '' ELSE ' · ' || dimension END AS event_summary
        FROM labeled
        ORDER BY date DESC, track, company
    """
    commitment = rows(con, commitment_sql)

    commercialization_sql = """
        SELECT
          COUNT(DISTINCT series_id) FILTER (WHERE event_type = 'initial_observation') AS public_series,
          COUNT(DISTINCT series_id) FILTER (WHERE event_type = 'value_change' AND change_pct > 0) AS positive_revisions,
          COUNT(DISTINCT series_id) FILTER (WHERE event_type = 'value_change' AND change_pct < 0) AS negative_revisions,
          MAX(date) AS latest_event_date
        FROM event_observation
        WHERE track = 'app_commercialization'
    """
    commercialization = rows(con, commercialization_sql)

    health_sql = """
        SELECT purpose AS source, natural_frequency AS frequency, status,
               age_hours, latest_observation_date, observation_rows,
               COALESCE(reason_code, 'ok') AS reason,
               natural_frequency || ' · ' || status AS cadence,
               CAST(age_hours AS VARCHAR) || 'h · ' || COALESCE(reason_code, 'ok') AS freshness,
               purpose || ' · ' || natural_frequency || ' · ' || status || ' · ' ||
                 CAST(age_hours AS VARCHAR) || 'h · ' || COALESCE(reason_code, 'ok') AS source_summary
        FROM source_freshness
        ORDER BY CASE status WHEN 'stale' THEN 1 WHEN 'missing' THEN 2 ELSE 3 END,
                 criticality, purpose
    """
    health = rows(con, health_sql)

    sources = [
        source("gpu_progress", "Exact-configuration GPU series qualification", gpu_progress_sql,
               ["series_quality"], generated_at,
               ["track=gpu_rental", "evidence_class=matched_venue_series", "H100/H200/B200 only"],
               ["Valid days are distinct complete daily observations.", "Chart threshold is 10 valid days."]),
        source("market_depth", "Latest GPU orderbook depth and exact-config price distribution", depth_sql,
               ["canonical_observation"], generated_at,
               ["latest complete snapshot", "available offers and matched venue series only"],
               ["P25/P50/P75 are cross-sectional USD/GPU-hour quantiles.", "Offers are observable available listings, not installed capacity."]),
        source("cloud_snapshot", "Official cloud GPU VM price snapshot", cloud_sql,
               ["canonical_observation"], generated_at,
               ["latest row per series", "frontier GPU families", "two lowest VM offers per vendor/GPU/billing"],
               ["Values are VM-hour prices and are not normalized per GPU.", "Spot and retail are separate billing dimensions."]),
        source("model_events", "Core model catalog price-change events", model_change_sql,
               ["event_observation"], generated_at,
               ["real price_change events only", "core model vendors", "absolute change >=5%", "supported comparison venues"],
               ["Change = current catalog price / prior catalog price - 1.", "Rows are venue-level catalog changes, not vendor-wide official price announcements."]),
        source("demand_proxy", "Complete-week OpenRouter public activity proxy", demand_sql,
               ["line_ready_observation"], generated_at,
               ["complete weekly observations", "chart-qualified series", "tool calls and image processing"],
               ["Index starts at 100 for each metric.", "4W MA requires four complete weekly observations.", "This is a public activity proxy, not total token volume."]),
        source("us_capex", "Calendar Q1 2026 official US hyperscaler CAPEX actuals", capex_sql,
               ["event_observation"], generated_at,
               ["cloud_capex_actual", "initial official observation", "period end 2026-03-31"],
               ["CAPEX is shown in USD billions for calendar Q1 2026.", "Oracle's annual FY2026 actual is excluded from the comparable bar chart and retained in the event ledger."]),
        source("commitment_events", "US and China commitment and monetization events", commitment_sql,
               ["event_observation", "production_capex_actuals"], generated_at,
               ["US CAPEX actuals and official cloud events", "China cloud CAPEX and clearly labeled context rows"],
               ["Event-frequency evidence is never interpolated to daily frequency.", "Units and definitions remain source-specific."]),
        source("commercialization_events", "Source-backed application commercialization revisions", commercialization_sql,
               ["event_observation"], generated_at,
               ["app_commercialization only", "distinct stable series", "initial observations separated from true value changes"],
               ["Public series counts first source-backed observations.", "Positive and negative revisions require a real value_change event; repeated snapshots do not count."]),
        source("source_health", "Production source freshness", health_sql,
               ["source_freshness"], generated_at,
               ["all production collection policies"],
               ["Age is measured from latest fetched timestamp.", "Stale thresholds are policy-specific."]),
        {
            "id": "thesis_state",
            "label": "Four-clock thesis state report",
            "query": {
                "engine": "snapshot",
                "sql": state_sql,
                "description": "Latest state-machine output generated from canonical production views.",
                "executed_at": state_report["generated_at"],
                "tables_used": ["matched_panel_index", "series_quality", "event_observation", "source_freshness"],
                "filters": ["no legacy CSI", "no daily CAPEX interpolation"],
                "metric_definitions": ["States are independent and are not combined into a composite score."],
            },
        },
    ]

    manifest_sources = sources
    cards = []
    for item in states:
        cards.append({
            "id": "state_" + item["clock_id"],
            "description": item["next_proof"],
            "dataset": "states",
            "sourceId": "thesis_state",
            "filter": {"clock_id": item["clock_id"]},
            "metrics": [
                {"label": item["clock_id"].replace("_", " ").title(), "field": "state"},
                {"label": "Frequency", "field": "frequency"},
            ],
        })
    cards.extend([
        {
            "id": "commercialization_coverage",
            "description": "Distinct source-backed application or company commercialization series.",
            "dataset": "commercialization",
            "sourceId": "commercialization_events",
            "metrics": [
                {"label": "Public ARR / adoption series", "field": "public_series", "format": "number"},
                {"label": "Latest event", "field": "latest_event_date"},
            ],
        },
        {
            "id": "commercialization_revisions",
            "description": "Only real value changes count; repeated public snapshots are excluded.",
            "dataset": "commercialization",
            "sourceId": "commercialization_events",
            "metrics": [
                {"label": "Positive revisions", "field": "positive_revisions", "format": "number"},
                {"label": "Negative revisions", "field": "negative_revisions", "format": "number"},
            ],
        },
    ])

    charts = [
        {
            "id": "gpu_progress_chart", "title": "Exact-config GPU history accumulated",
            "subtitle": "No fixed matched panel is chart-ready; bars show honest progress toward the 10-day display threshold.",
            "headerMarkdown": "Daily · latest production snapshot · **0 chart-ready panels**",
            "type": "bar", "dataset": "gpu_progress", "sourceId": "gpu_progress",
            "encodings": {
                "x": {"field": "gpu", "type": "nominal", "label": "GPU family"},
                "y": {"field": "days", "type": "quantitative", "label": "Daily observations"},
                "color": {"field": "measure", "type": "nominal", "label": "Measure"},
                "tooltip": [
                    {"field": "exact_series", "type": "quantitative", "label": "Exact series"},
                    {"field": "venues", "type": "quantitative", "label": "Venues"},
                    {"field": "blocker", "type": "text", "label": "Blocker"},
                ],
            },
            "xAxisTitle": "GPU family", "yAxisTitle": "Valid daily observations",
            "emptyState": "A price line will appear only after a fixed exact-configuration panel passes the history threshold.",
        },
        {
            "id": "depth_chart", "title": "Available GPU offers by family",
            "subtitle": "Latest observable orderbook depth; listing count is a capacity proxy, not installed capacity.",
            "headerMarkdown": "Snapshot frequency · latest date **" + (depth[0]["date"] if depth else "unavailable") + "**",
            "type": "bar", "dataset": "depth", "sourceId": "market_depth",
            "encodings": {
                "x": {"field": "gpu", "type": "nominal", "label": "GPU family"},
                "y": {"field": "offers", "type": "quantitative", "label": "Available offers"},
                "tooltip": [
                    {"field": "price_p50", "type": "quantitative", "label": "Median price", "format": "currency"},
                    {"field": "price_p25", "type": "quantitative", "label": "P25 price", "format": "currency"},
                    {"field": "price_p75", "type": "quantitative", "label": "P75 price", "format": "currency"},
                    {"field": "exact_configs", "type": "quantitative", "label": "Exact configs"},
                ],
            },
            "xAxisTitle": "GPU family", "yAxisTitle": "Available offers",
        },
        {
            "id": "cloud_chart", "title": "Cloud GPU VM-hour price snapshot",
            "subtitle": "AWS spot and Azure retail prices remain separate; VM sizes are not normalized to per-GPU economics.",
            "headerMarkdown": "Daily snapshot · official price endpoints · **VM-hour basis**",
            "type": "horizontalBar", "dataset": "cloud", "sourceId": "cloud_snapshot",
            "encodings": {
                "x": {"field": "offer", "type": "nominal", "label": "Cloud offer"},
                "y": {"field": "vm_hour_usd", "type": "quantitative", "label": "USD per VM-hour", "format": "currency"},
                "color": {"field": "billing", "type": "nominal", "label": "Billing"},
                "tooltip": [{"field": "date", "type": "temporal", "label": "Price date"}],
            },
            "xAxisTitle": "Provider · GPU · SKU", "yAxisTitle": "USD per VM-hour", "valueFormat": "currency",
        },
        {
            "id": "model_change_chart", "title": "Observed model price changes",
            "subtitle": "Venue-level catalog changes of at least 5%; only detected price-change events are plotted.",
            "headerMarkdown": "Event frequency · USD per 1M tokens · not a continuous time series",
            "type": "horizontalBar", "dataset": "model_changes", "sourceId": "model_events",
            "encodings": {
                "x": {"field": "price_line", "type": "nominal", "label": "Model price line"},
                "y": {"field": "change_pct", "type": "quantitative", "label": "Price change (%)"},
                "tooltip": [
                    {"field": "date", "type": "temporal", "label": "Event date"},
                    {"field": "venue", "type": "text", "label": "Venue"},
                    {"field": "prior_price", "type": "quantitative", "label": "Prior price", "format": "currency"},
                    {"field": "current_price", "type": "quantitative", "label": "Current price", "format": "currency"},
                ],
            },
            "xAxisTitle": "Model price line", "yAxisTitle": "Price change (%)",
            "referenceLines": [{"value": 0, "label": "No change"}],
        },
        {
            "id": "demand_chart", "title": "OpenRouter public activity proxy",
            "subtitle": "Complete weeks only; weekly counts and four-week moving averages are indexed independently to 100.",
            "headerMarkdown": "Weekly · through **" + (max((r["date"] for r in demand_raw), default="unavailable")) + "** · proxy evidence",
            "type": "line", "dataset": "demand", "sourceId": "demand_proxy",
            "encodings": {
                "x": {"field": "date", "type": "temporal", "label": "Week ending"},
                "y": {"field": "index_value", "type": "quantitative", "label": "Activity index"},
                "color": {"field": "series", "type": "nominal", "label": "Metric"},
                "tooltip": [
                    {"field": "activity_count", "type": "quantitative", "label": "Observed count", "format": "compact"},
                    {"field": "included_series", "type": "quantitative", "label": "Included series"},
                ],
            },
            "xAxisTitle": "Complete week", "yAxisTitle": "Activity index (first week = 100)",
            "referenceLines": [{"value": 100, "label": "Starting level"}],
        },
        {
            "id": "capex_chart", "title": "Calendar Q1 2026 US hyperscaler CAPEX actuals",
            "subtitle": "Four comparable quarter-end observations; Oracle's FY2026 annual actual remains in the event ledger below.",
            "headerMarkdown": "Quarterly · period ended 2026-03-31 · USD billions · official filings",
            "type": "bar", "dataset": "capex", "sourceId": "us_capex",
            "encodings": {
                "x": {"field": "company", "type": "nominal", "label": "Company"},
                "y": {"field": "capex_usd_b", "type": "quantitative", "label": "CAPEX (USD B)"},
                "tooltip": [
                    {"field": "date", "type": "temporal", "label": "Period end"},
                    {"field": "fiscal_period", "type": "text", "label": "Fiscal period"},
                ],
            },
            "xAxisTitle": "Company", "yAxisTitle": "CAPEX (USD billions)", "valueFormat": "currency",
        },
    ]

    tables = [
        {
            "id": "depth_table", "title": "Latest orderbook price distribution",
            "subtitle": "Cross-sectional exact-configuration prices alongside observable offer depth.",
            "dataset": "depth", "sourceId": "market_depth", "density": "compact",
            "defaultSort": {"field": "depth_summary", "direction": "asc"},
            "columns": [
                {"field": "depth_summary", "label": "GPU · offers · exact-config price distribution", "type": "text"},
            ],
        },
        {
            "id": "commitment_table", "title": "US and China CAPEX / commitment ledger",
            "subtitle": "CAPEX, guidance, backlog and capacity evidence preserve native units and event dates; no daily interpolation.",
            "dataset": "commitment", "sourceId": "commitment_events", "density": "compact",
            "defaultSort": {"field": "event_summary", "direction": "desc"},
            "columns": [
                {"field": "event_summary", "label": "Date · company · signal · observed value", "type": "text"},
            ],
        },
        {
            "id": "health_table", "title": "Source freshness and coverage",
            "subtitle": "Stale and missing sources are exposed rather than silently backfilled.",
            "dataset": "health", "sourceId": "source_health", "density": "compact",
            "columns": [
                {"field": "source_summary", "label": "Source · cadence · status · age · reason", "type": "text"},
            ],
        },
    ]

    blocks = [
        {"id": "intro", "type": "markdown", "body": "# AI Compute Economics Monitor\n\nFour independent clocks. Each exhibit keeps its natural frequency; no blended score and no synthetic interpolation."},
        {"id": "states_market", "type": "metric-strip", "cardIds": [card["id"] for card in cards[:2]]},
        {"id": "states_business", "type": "metric-strip", "cardIds": [card["id"] for card in cards[2:4]]},
        {"id": "supply_heading", "type": "markdown", "body": "## 01 · Compute Price\n\nExact-configuration rental evidence only. A true H100/H200/B200 line appears after a fixed panel clears the data threshold."},
        {"id": "supply_chart", "type": "chart", "chartId": "gpu_progress_chart"},
        {"id": "depth_heading", "type": "markdown", "body": "## 02 · Market Depth\n\nCurrent orderbook breadth and cross-sectional price distribution."},
        {"id": "depth_chart_block", "type": "chart", "chartId": "depth_chart"},
        {"id": "depth_table_block", "type": "table", "tableId": "depth_table", "layout": "full"},
        {"id": "cloud_heading", "type": "markdown", "body": "## 03 · Cloud\n\nOfficial VM-hour prices. Billing modes and instance sizes are kept explicit."},
        {"id": "cloud_chart_block", "type": "chart", "chartId": "cloud_chart"},
        {"id": "model_heading", "type": "markdown", "body": "## 04 · Model Economics\n\nObserved catalog price changes for core model families."},
        {"id": "model_chart_block", "type": "chart", "chartId": "model_change_chart"},
        {"id": "demand_heading", "type": "markdown", "body": "## 05 · Demand\n\nPublic activity proxy with complete-week filtering and four-week smoothing."},
        {"id": "demand_chart_block", "type": "chart", "chartId": "demand_chart"},
        {"id": "commitment_heading", "type": "markdown", "body": "## 06 · Commitment\n\nCAPEX, guidance, backlog and capacity evidence at quarterly or event frequency."},
        {"id": "commercialization_metrics", "type": "metric-strip", "cardIds": ["commercialization_coverage", "commercialization_revisions"]},
        {"id": "capex_chart_block", "type": "chart", "chartId": "capex_chart"},
        {"id": "commitment_table_block", "type": "table", "tableId": "commitment_table", "layout": "full"},
        {"id": "quality_heading", "type": "markdown", "body": "## Data quality\n\nOpen only when you need to inspect freshness, coverage or a blocker."},
        {"id": "health_table_block", "type": "table", "tableId": "health_table", "layout": "full"},
    ]

    artifact = {
        "surface": "dashboard",
        "manifest": {
            "version": 1,
            "surface": "dashboard",
            "title": "AI Compute Economics Monitor",
            "description": "A source-backed monitor of compute price, capacity, model economics, demand and capital commitment.",
            "generatedAt": generated_at,
            "filters": [],
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": manifest_sources,
            "blocks": blocks,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "partial" if any(row["status"] != "fresh" for row in health) else "ready",
            "datasets": {
                "states": states,
                "gpu_progress": gpu_progress,
                "depth": depth,
                "cloud": cloud,
                "model_changes": model_changes,
                "demand": demand,
                "capex": capex,
                "commitment": commitment,
                "commercialization": commercialization,
                "health": health,
            },
            "accessIssues": [],
        },
        "sources": sources,
        "package_info": {
            "originUrl": "artifact://ai-compute-economics-monitor",
            "controls": {"edit": False, "refresh": False},
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "datasets": {key: len(value) for key, value in artifact["snapshot"]["datasets"].items()},
        "charts": len(charts),
        "tables": len(tables),
        "status": artifact["snapshot"]["status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
