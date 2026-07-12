"""Independent-frequency thesis state machines for the AI compute tracker."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb


STATES = ("Unobservable", "Observing", "Trend", "Inflection Watch", "Confirmed")


@dataclass
class ClockState:
    clock_id: str
    title: str
    natural_frequency: str
    state: str
    basis: str
    confirms: List[str]
    disconfirms: List[str]
    next_proof_point: str
    source_coverage: Dict[str, Any]
    metrics: Dict[str, Any]
    blockers: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ThesisStateReport:
    generated_at: str
    db_path: str
    clocks: List[ClockState]
    methodology: Dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "db_path": self.db_path,
            "clocks": [asdict(clock) for clock in self.clocks],
            "methodology": self.methodology,
        }


def classify_supply(metrics: Dict[str, Any]) -> Dict[str, Any]:
    blockers: List[str] = []
    if int(metrics.get("exact_series") or 0) == 0:
        return {"state": "Unobservable", "blockers": ["no_exact_configuration_series"]}
    if int(metrics.get("panel_count") or 0) == 0:
        return {"state": "Observing", "blockers": ["no_fixed_matched_panel"]}
    if int(metrics.get("chart_ready_panels") or 0) == 0:
        return {"state": "Observing", "blockers": ["insufficient_panel_history"]}
    if int(metrics.get("confirmed_90d_breadth") or 0) >= 2:
        return {"state": "Confirmed", "blockers": []}

    if int(metrics.get("inflection_ready_panels") or 0) < 2:
        blockers.append("insufficient_30d_duration")
    if int(metrics.get("decline_30d_breadth") or 0) < 2:
        blockers.append("insufficient_market_breadth")
    depth_growth = metrics.get("depth_growth_30d_pct")
    if int(metrics.get("depth_valid_dates") or 0) < 20 or depth_growth is None or depth_growth < 10:
        blockers.append("depth_not_confirming")
    if not blockers:
        return {"state": "Inflection Watch", "blockers": []}
    return {"state": "Trend", "blockers": blockers}


class ThesisStateEngine:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)

    @staticmethod
    def _scalar(con: duckdb.DuckDBPyConnection, sql: str, default: Any = 0) -> Any:
        row = con.execute(sql).fetchone()
        return default if not row or row[0] is None else row[0]

    @staticmethod
    def _records(con: duckdb.DuckDBPyConnection, sql: str) -> List[Dict[str, Any]]:
        frame = con.execute(sql).fetchdf()
        if frame.empty:
            return []
        records = frame.to_dict(orient="records")
        for record in records:
            for key, value in list(record.items()):
                if hasattr(value, "isoformat"):
                    record[key] = value.isoformat()
                elif hasattr(value, "item"):
                    record[key] = value.item()
        return records

    def _source_coverage(self, con: duckdb.DuckDBPyConnection, policy_ids: List[str]) -> Dict[str, Any]:
        quoted = ",".join("'" + value.replace("'", "''") + "'" for value in policy_ids)
        rows = self._records(
            con,
            f"""
            SELECT policy_id, status, criticality, age_hours, reason_code
            FROM source_freshness
            WHERE policy_id IN ({quoted})
            ORDER BY policy_id
            """,
        )
        return {
            "policies": rows,
            "fresh": sum(row["status"] == "fresh" for row in rows),
            "stale": sum(row["status"] == "stale" for row in rows),
            "missing": sum(row["status"] == "missing" for row in rows),
        }

    def _depth_metrics(self, con: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
        row = con.execute(
            """
            WITH daily AS (
                SELECT date, sum(value) AS offers
                FROM canonical_market_observation
                WHERE track='gpu_available_offer'
                  AND metric='available_offer_count'
                  AND period_complete=TRUE
                GROUP BY date
            )
            SELECT
                count(*) AS valid_dates,
                min(date) AS first_date,
                max(date) AS last_date,
                arg_min(offers, date) AS first_offers,
                arg_max(offers, date) AS last_offers
            FROM daily
            """
        ).fetchone()
        valid_dates, first_date, last_date, first_offers, last_offers = row
        growth = None
        if valid_dates >= 20 and first_offers not in (None, 0):
            growth = round((last_offers / first_offers - 1) * 100, 4)
        breadth = int(self._scalar(con, """
            WITH daily AS (
                SELECT date, entity, sum(value) AS offers
                FROM canonical_market_observation
                WHERE track='gpu_available_offer'
                  AND metric='available_offer_count'
                  AND period_complete=TRUE
                GROUP BY date, entity
            ), by_gpu AS (
                SELECT entity, count(*) AS valid_dates,
                       arg_min(offers, date) AS first_offers,
                       arg_max(offers, date) AS last_offers
                FROM daily
                GROUP BY entity
            )
            SELECT count(*)
            FROM by_gpu
            WHERE valid_dates >= 20
              AND first_offers > 0
              AND (last_offers / first_offers - 1) * 100 >= 25
        """))
        return {
            "depth_valid_dates": int(valid_dates or 0),
            "depth_first_date": first_date.isoformat() if first_date else None,
            "depth_last_date": last_date.isoformat() if last_date else None,
            "depth_first_offers": first_offers,
            "depth_last_offers": last_offers,
            "depth_growth_30d_pct": growth,
            "expanding_gpu_breadth": breadth,
        }

    def _supply(self, con: duckdb.DuckDBPyConnection) -> ClockState:
        depth = self._depth_metrics(con)
        metrics = {
            "exact_series": int(self._scalar(con, "SELECT count(*) FROM series_definition WHERE evidence_class='matched_venue_series'")),
            "panel_count": int(self._scalar(con, "SELECT count(DISTINCT panel_id) FROM matched_panel_index")),
            "chart_ready_panels": int(self._scalar(con, "SELECT count(DISTINCT panel_id) FROM matched_panel_index WHERE eligible_for_chart")),
            "inflection_ready_panels": int(self._scalar(con, "SELECT count(DISTINCT panel_id) FROM matched_panel_index WHERE eligible_for_inflection")),
            "decline_30d_breadth": int(self._scalar(con, """
                SELECT count(*) FROM (
                    SELECT panel_id, arg_max(change_30d_pct, date) AS change_30d
                    FROM matched_panel_index GROUP BY panel_id
                ) WHERE change_30d <= -10
            """)),
            "confirmed_90d_breadth": int(self._scalar(con, """
                SELECT count(*) FROM (
                    SELECT panel_id,
                           arg_max(change_90d_pct, date) AS change_90d,
                           bool_or(eligible_for_90d) AS eligible_90d
                    FROM matched_panel_index GROUP BY panel_id
                ) WHERE eligible_90d AND change_90d <= -15
            """)),
            **depth,
        }
        classification = classify_supply(metrics)
        rejection_counts = self._records(con, """
            SELECT panel_reason_code AS reason_code, count(*) AS series
            FROM matched_panel_candidate
            WHERE eligible_for_matched_panel=FALSE
            GROUP BY panel_reason_code
            ORDER BY series DESC
        """)
        evidence = self._records(con, """
            SELECT series_id, entity, vendor, valid_dates, first_date, last_date,
                   chart_reason_code
            FROM series_quality
            WHERE evidence_class='matched_venue_series'
            ORDER BY valid_dates DESC, entity, vendor
            LIMIT 8
        """)
        metrics["candidate_rejections"] = rejection_counts
        return ClockState(
            clock_id="supply_price",
            title="Supply Price",
            natural_frequency="daily",
            state=classification["state"],
            basis="Exact-configuration GPU rental panels; published changing-composition aggregates are excluded.",
            confirms=["At least two frontier GPU panels decline >=10% over 30D.", "Offer depth rises >=10% with at least 20 valid daily observations."],
            disconfirms=["Price decline is isolated to one GPU family.", "Offer depth is flat/down or panel composition changes."],
            next_proof_point="Accumulate 10 daily observations for charting and 20 for 30D inflection eligibility.",
            source_coverage=self._source_coverage(con, [
                "gpuperhour_daily", "runpod_daily", "vast_daily",
                "computeprices_gpu_daily", "computeprices_trend_daily",
                "azure_daily", "aws_spot_daily",
            ]),
            metrics=metrics,
            blockers=classification["blockers"],
            evidence=evidence,
        )

    def _capacity(self, con: duckdb.DuckDBPyConnection) -> ClockState:
        metrics = self._depth_metrics(con)
        if metrics["depth_valid_dates"] == 0:
            state, blockers = "Unobservable", ["no_capacity_history"]
        elif metrics["depth_valid_dates"] < 10:
            state, blockers = "Observing", ["insufficient_capacity_history"]
        elif metrics["depth_valid_dates"] < 20:
            state, blockers = "Trend", ["insufficient_30d_duration"]
        elif metrics["depth_valid_dates"] >= 60 and metrics["expanding_gpu_breadth"] >= 2:
            state, blockers = "Confirmed", []
        elif (metrics["depth_growth_30d_pct"] is not None
              and metrics["depth_growth_30d_pct"] >= 25
              and metrics["expanding_gpu_breadth"] >= 2):
            state, blockers = "Inflection Watch", []
        else:
            state, blockers = "Trend", ["capacity_breadth_not_expanding"]
        evidence = self._records(con, """
            SELECT observation_id, date, entity, value, unit, source_id
            FROM canonical_market_observation
            WHERE track='gpu_available_offer' AND metric='available_offer_count'
            ORDER BY date DESC, entity
            LIMIT 8
        """)
        return ClockState(
            clock_id="capacity_utilization",
            title="Capacity & Utilization",
            natural_frequency="daily / weekly",
            state=state,
            basis="Available offer counts and capacity proxies remain separate from price.",
            confirms=["Offer/capacity breadth expands across at least two frontier GPU families.", "Expansion persists for 20+ valid days."],
            disconfirms=["Only low-quality or non-rentable inventory increases.", "Depth falls while apparent prices decline."],
            next_proof_point="Reach 10 valid daily orderbook observations, then test 30D breadth.",
            source_coverage=self._source_coverage(con, [
                "gpuperhour_daily", "runpod_daily", "vast_daily",
            ]),
            metrics=metrics,
            blockers=blockers,
            evidence=evidence,
        )

    def _demand(self, con: duckdb.DuckDBPyConnection) -> ClockState:
        chart_series = int(self._scalar(con, "SELECT count(*) FROM series_quality WHERE track='openrouter_usage' AND eligible_for_chart"))
        proxy_series = int(self._scalar(con, "SELECT count(*) FROM series_quality WHERE track='openrouter_usage' AND evidence_class='public_proxy' AND eligible_for_chart"))
        official_inflection = int(self._scalar(con, "SELECT count(*) FROM series_quality WHERE track='openrouter_usage' AND evidence_class<>'public_proxy' AND eligible_for_inflection"))
        negative_price_changes = int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track='token_price' AND event_type='price_change' AND change_pct<0"))
        positive_commercial_changes = int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track='app_commercialization' AND event_type='value_change' AND change_pct>0"))
        usage_series = int(self._scalar(con, "SELECT count(*) FROM series_definition WHERE track='openrouter_usage'"))
        usage_changes = {
            row[0]: row[1]
            for row in con.execute("""
                WITH weekly AS (
                    SELECT date, metric, sum(value) AS value
                    FROM canonical_market_observation
                    WHERE track='openrouter_usage' AND period_complete=TRUE
                    GROUP BY date, metric
                ), changed AS (
                    SELECT date, metric, value,
                           lag(value, 4) OVER (PARTITION BY metric ORDER BY date) AS value_4w_ago,
                           row_number() OVER (PARTITION BY metric ORDER BY date DESC) AS latest_rank
                    FROM weekly
                )
                SELECT metric,
                       CASE WHEN value_4w_ago IS NULL OR value_4w_ago=0 THEN NULL
                            ELSE round((value/value_4w_ago-1)*100, 4) END AS change_4w_pct
                FROM changed
                WHERE latest_rank=1
            """).fetchall()
        }
        if usage_series == 0 and negative_price_changes == 0:
            state, blockers = "Unobservable", ["no_usage_or_price_change_series"]
        elif chart_series == 0:
            state, blockers = "Observing", ["insufficient_usage_history"]
        elif official_inflection >= 2 and negative_price_changes >= 3 and positive_commercial_changes >= 2:
            state, blockers = "Confirmed", []
        elif official_inflection > 0 and negative_price_changes >= 3:
            state, blockers = "Inflection Watch", []
        else:
            state = "Trend"
            blockers = ["proxy_not_inflection_eligible"] if proxy_series else ["usage_price_bridge_unconfirmed"]
        metrics = {
            "usage_series": usage_series,
            "chart_ready_usage_series": chart_series,
            "proxy_series": proxy_series,
            "official_inflection_series": official_inflection,
            "negative_token_price_changes": negative_price_changes,
            "positive_commercialization_changes": positive_commercial_changes,
            "tool_call_4w_change_pct": usage_changes.get("tool_call_count"),
            "image_processing_4w_change_pct": usage_changes.get("image_processing_count"),
        }
        evidence = self._records(con, """
            SELECT l.series_id, l.entity, l.metric, l.vendor, max(l.date) AS last_date,
                   count(*) AS valid_points
            FROM line_ready_observation l
            WHERE l.track='openrouter_usage'
            GROUP BY l.series_id, l.entity, l.metric, l.vendor
            ORDER BY valid_points DESC, l.series_id
            LIMIT 8
        """)
        return ClockState(
            clock_id="demand_unit_economics",
            title="Demand & Unit Economics",
            natural_frequency="weekly / event",
            state=state,
            basis="Usage trends and token price changes are tracked separately; public activity proxy cannot confirm an inflection.",
            confirms=["Official/comparable usage accelerates after real token price cuts.", "Usage-price relationship persists across multiple models."],
            disconfirms=["Usage growth is only a frontend proxy or one-off model mix shift.", "Price cuts occur without volume response."],
            next_proof_point="Obtain official usage series or another independent demand source; preserve complete-week filtering.",
            source_coverage={**self._source_coverage(con, [
                "openrouter_frontend_weekly", "openrouter_models_daily",
                "litellm_catalog_daily", "models_dev_daily",
            ]), "proxy_series": proxy_series},
            metrics=metrics,
            blockers=blockers,
            evidence=evidence,
        )

    def _commitment(self, con: duckdb.DuckDBPyConnection) -> ClockState:
        event_count = int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track IN ('cloud_capex_actual','cloud_official_event','china_cloud_capex','app_commercialization')"))
        sequential_companies = int(self._scalar(con, "SELECT count(DISTINCT entity) FROM series_definition WHERE track='cloud_capex_actual' AND valid_dates>=2"))
        trend_companies = int(self._scalar(con, "SELECT count(DISTINCT entity) FROM series_definition WHERE track='cloud_capex_actual' AND valid_dates>=3"))
        negative_actual_companies = int(self._scalar(con, """
            SELECT count(DISTINCT entity) FROM (
                SELECT entity, value,
                       lag(value) OVER (PARTITION BY series_id ORDER BY date) AS prior_value
                FROM canonical_observation
                WHERE track='cloud_capex_actual'
            ) WHERE prior_value IS NOT NULL AND value < prior_value
        """))
        guidance_breadth = con.execute("""
            WITH guidance AS (
                SELECT entity, date, metric, value
                FROM canonical_observation
                WHERE track='cloud_official_event'
                  AND dimension='capex_guidance_revision'
                  AND value IS NOT NULL
            ), previous AS (
                SELECT entity, date, metric,
                       replace(metric, '_previous_', '_') AS current_metric,
                       value AS previous_value
                FROM guidance
                WHERE metric LIKE '%_previous_%'
            ), current_values AS (
                SELECT entity, date, metric, value AS current_value
                FROM guidance
                WHERE metric NOT LIKE '%_previous_%'
            )
            SELECT
                count(DISTINCT c.entity) FILTER (WHERE c.current_value < p.previous_value),
                count(DISTINCT c.entity) FILTER (WHERE c.current_value > p.previous_value)
            FROM current_values c
            JOIN previous p
              ON c.entity=p.entity AND c.date=p.date AND c.metric=p.current_metric
        """).fetchone()
        negative_guidance_companies = int(guidance_breadth[0] or 0)
        positive_guidance_companies = int(guidance_breadth[1] or 0)
        if event_count == 0:
            state, blockers = "Unobservable", ["no_official_commitment_events"]
        elif negative_actual_companies >= 2:
            state, blockers = "Confirmed", []
        elif negative_guidance_companies >= 2:
            state, blockers = "Inflection Watch", []
        elif trend_companies >= 3:
            state, blockers = "Trend", []
        else:
            state, blockers = "Observing", ["insufficient_sequential_quarters"]
        metrics = {
            "official_and_commercial_events": event_count,
            "sequential_capex_companies": sequential_companies,
            "three_period_capex_companies": trend_companies,
            "negative_guidance_companies": negative_guidance_companies,
            "positive_guidance_companies": positive_guidance_companies,
            "negative_actual_capex_companies": negative_actual_companies,
        }
        evidence = self._records(con, """
            SELECT event_id, date, track, entity, metric, value, unit, event_type, source_id
            FROM event_observation
            WHERE track IN ('cloud_capex_actual','cloud_official_event','china_cloud_capex','app_commercialization')
            ORDER BY date DESC, entity, metric
            LIMIT 12
        """)
        return ClockState(
            clock_id="commitment_monetization",
            title="Commitment & Monetization",
            natural_frequency="quarterly / event",
            state=state,
            basis="CAPEX actuals, guidance, RPO and commercialization events are never interpolated to daily frequency.",
            confirms=["Negative guidance revisions broaden across companies.", "Subsequent CAPEX/RPO actuals confirm the direction."],
            disconfirms=["CAPEX guidance and RPO continue to rise.", "Commercialization events are repeated snapshots rather than new information."],
            next_proof_point="Add sequential quarterly actuals for at least three hyperscalers and classify guidance direction.",
            source_coverage={
                "capex_actual_events": int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track='cloud_capex_actual'")),
                "official_events": int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track='cloud_official_event'")),
                "china_events": int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track='china_cloud_capex'")),
                "commercialization_events": int(self._scalar(con, "SELECT count(*) FROM event_observation WHERE track='app_commercialization'")),
            },
            metrics=metrics,
            blockers=blockers,
            evidence=evidence,
        )

    def evaluate(self, as_of: Optional[str] = None) -> ThesisStateReport:
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            clocks = [self._supply(con), self._capacity(con), self._demand(con), self._commitment(con)]
        finally:
            con.close()
        generated_at = as_of or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return ThesisStateReport(
            generated_at=generated_at,
            db_path=self.db_path,
            clocks=clocks,
            methodology={
                "mixed_frequency_weighting": False,
                "state_order": list(STATES),
                "rule": "Each clock advances only on its own natural-frequency evidence and explicit confirmation conditions.",
            },
        )


def render_state_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# AI Compute Thesis State",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "四个时钟独立判断，不合成总分，不跨频率插值。",
        "",
        "| Clock | Frequency | State | Blockers |",
        "|---|---|---|---|",
    ]
    for clock in payload["clocks"]:
        blockers = ", ".join(clock["blockers"]) or "none"
        lines.append(
            f"| {clock['title']} | {clock['natural_frequency']} | **{clock['state']}** | {blockers} |"
        )
    for clock in payload["clocks"]:
        lines.extend([
            "",
            f"## {clock['title']} | {clock['state']}",
            "",
            clock["basis"],
            "",
            f"Next proof point: {clock['next_proof_point']}",
            "",
            "Confirm conditions:",
        ])
        lines.extend(f"- {item}" for item in clock["confirms"])
        lines.append("")
        lines.append("Disconfirm conditions:")
        lines.extend(f"- {item}" for item in clock["disconfirms"])
        lines.append("")
        lines.append(f"Evidence rows: {len(clock['evidence'])}")
    transitions = payload.get("transitions") or []
    lines.extend(["", "## State Changes", ""])
    if transitions:
        for transition in transitions:
            lines.append(
                f"- {transition['clock_id']}: {transition['from_state'] or 'none'} -> "
                f"{transition['to_state']} ({transition['change_type']})"
            )
    else:
        lines.append("- No state change versus the previous snapshot.")
    return "\n".join(lines) + "\n"


def write_state_report(db_path: str, output_dir: str | Path) -> Dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = ThesisStateEngine(db_path).evaluate().to_dict()
    previous_path = output / "latest-thesis-state.json"
    previous = None
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    previous_states = {
        clock["clock_id"]: clock["state"] for clock in (previous or {}).get("clocks", [])
    }
    transitions = []
    for clock in payload["clocks"]:
        old = previous_states.get(clock["clock_id"])
        new = clock["state"]
        if old == new:
            continue
        if old is None:
            change_type = "initial_state"
        else:
            old_rank = STATES.index(old)
            new_rank = STATES.index(new)
            change_type = "upgrade" if new_rank > old_rank else "downgrade"
        transitions.append({
            "clock_id": clock["clock_id"],
            "from_state": old,
            "to_state": new,
            "change_type": change_type,
        })
    payload["transitions"] = transitions
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    versioned_json = output / f"{stamp}-thesis-state.json"
    versioned_md = output / f"{stamp}-thesis-state.md"
    latest_md = output / "latest-thesis-state.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    markdown = render_state_markdown(payload)
    versioned_json.write_text(json_text, encoding="utf-8")
    previous_path.write_text(json_text, encoding="utf-8")
    versioned_md.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    return {
        "json": str(versioned_json),
        "markdown": str(versioned_md),
        "latest_json": str(previous_path),
        "latest_markdown": str(latest_md),
    }
