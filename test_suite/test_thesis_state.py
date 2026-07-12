import sys
from datetime import date, timedelta
from pathlib import Path


TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from thesis_state import ThesisStateEngine, classify_supply, write_state_report  # noqa: E402
from tracker_v2 import Database  # noqa: E402


INSERT_FACT = """
INSERT INTO production_market_facts (
    date, track, entity, sub_entity, metric, value, unit, dimension,
    vendor, source_name, notes, run_id, source_id, source_url, snapshot_path,
    source_type, collection_method, observed_at, fetched_at, raw_payload_hash,
    is_production_eligible, confidence
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _fact(day, track, entity, metric, value, *, source_id, vendor, dimension, unit="count"):
    timestamp = f"{day} 09:00:00"
    return (
        str(day), track, entity, vendor, metric, value, unit, dimension,
        vendor, "test source", "test", f"run-{day}", source_id,
        f"https://example.com/{source_id}", f"{source_id}-{day}.json",
        "official", "api", timestamp, timestamp, f"hash-{source_id}-{day}", True, 0.9,
    )


def test_empty_database_returns_four_unobservable_clocks(tmp_path):
    db_path = tmp_path / "tracker.db"
    Database(str(db_path))

    report = ThesisStateEngine(str(db_path)).evaluate().to_dict()

    assert [clock["state"] for clock in report["clocks"]] == [
        "Unobservable", "Unobservable", "Unobservable", "Unobservable"
    ]
    assert "composite_score" not in report
    assert "confidence" not in report
    serialized = __import__("json").dumps(report)
    assert "composite_score" not in serialized
    assert "confidence" not in serialized


def test_supply_inflection_requires_price_breadth_duration_and_depth():
    base = {
        "exact_series": 30,
        "panel_count": 3,
        "chart_ready_panels": 3,
        "inflection_ready_panels": 3,
        "decline_30d_breadth": 2,
        "depth_valid_dates": 25,
        "depth_growth_30d_pct": 18.0,
        "confirmed_90d_breadth": 0,
    }

    positive = classify_supply(base)
    no_depth = classify_supply({**base, "depth_growth_30d_pct": -2.0})
    too_narrow = classify_supply({**base, "decline_30d_breadth": 1})
    confirmed = classify_supply({**base, "confirmed_90d_breadth": 2})

    assert positive["state"] == "Inflection Watch"
    assert no_depth["state"] == "Trend"
    assert "depth_not_confirming" in no_depth["blockers"]
    assert too_narrow["state"] == "Trend"
    assert "insufficient_market_breadth" in too_narrow["blockers"]
    assert confirmed["state"] == "Confirmed"


def test_proxy_usage_can_reach_trend_but_not_inflection(tmp_path):
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    conn = db.get_connection()
    start = date(2026, 4, 6)
    rows = []
    for offset in range(13):
        week = start + timedelta(days=offset * 7)
        rows.append(
            _fact(
                week, "openrouter_usage", "Others", "tool_call_count", 100 + offset * 10,
                source_id="openrouter-frontend-rankings-tool-call-count",
                vendor="OpenRouter", dimension="weekly_frontend_public",
            )
        )
    conn.executemany(INSERT_FACT, rows)
    conn.close()

    report = ThesisStateEngine(str(db_path)).evaluate().to_dict()
    demand = next(clock for clock in report["clocks"] if clock["clock_id"] == "demand_unit_economics")

    assert demand["state"] == "Trend"
    assert demand["source_coverage"]["proxy_series"] == 1
    assert "proxy_not_inflection_eligible" in demand["blockers"]
    assert demand["evidence"][0]["series_id"].startswith("ser_")


def test_single_capex_period_is_observing_not_trend(tmp_path):
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO production_capex_actuals (
            ticker, company, period_start, period_end, fiscal_period, fiscal_year,
            xbrl_tag, accession_no, capex_value, unit, filed_at, form_type,
            run_id, source_id, source_url, snapshot_path, source_type,
            collection_method, observed_at, fetched_at, raw_payload_hash,
            is_production_eligible, confidence
        ) VALUES (
            'META', 'Meta', '2026-01-01', '2026-03-31', 'FY2026 Q1', 2026,
            'PaymentsToAcquirePropertyPlantAndEquipment', '0001', 18.997, 'USD_B',
            '2026-04-29', '10-Q', 'capex-run', 'sec-meta-capex',
            'https://sec.example/meta', 'meta.json', 'official', 'sec_api',
            '2026-03-31 00:00:00', '2026-04-29 00:00:00', 'capex-hash', TRUE, 0.99
        )
        """
    )
    conn.close()

    report = ThesisStateEngine(str(db_path)).evaluate().to_dict()
    commitment = next(clock for clock in report["clocks"] if clock["clock_id"] == "commitment_monetization")

    assert commitment["state"] == "Observing"
    assert commitment["metrics"]["sequential_capex_companies"] == 0
    assert "insufficient_sequential_quarters" in commitment["blockers"]


def test_negative_guidance_requires_breadth_before_inflection_watch(tmp_path):
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    conn = db.get_connection()
    rows = []
    for ticker in ("META", "AMZN"):
        for metric, value in (
            ("fy2027_capex_guidance_previous_high", 120.0),
            ("fy2027_capex_guidance_high", 100.0),
        ):
            rows.append((
                ticker, "2026-07-11", "capex_guidance_revision", metric, value, "USD_B",
                "Guidance reduced", "FY2027", f"run-{ticker}-{metric}",
                f"source-{ticker}-{metric}", f"https://example.com/{ticker}",
                f"{ticker}.html", "official", "manual_verified", "2026-07-11 00:00:00",
                "2026-07-11 01:00:00", f"hash-{ticker}-{metric}", True, 0.95,
            ))
    conn.executemany(
        """
        INSERT INTO production_official_events (
            ticker, announcement_date, event_type, metric, value, unit,
            description, fiscal_period, run_id, source_id, source_url,
            snapshot_path, source_type, collection_method, observed_at,
            fetched_at, raw_payload_hash, is_production_eligible, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.close()

    report = ThesisStateEngine(str(db_path)).evaluate().to_dict()
    commitment = next(clock for clock in report["clocks"] if clock["clock_id"] == "commitment_monetization")

    assert commitment["state"] == "Inflection Watch"
    assert commitment["metrics"]["negative_guidance_companies"] == 2


def test_state_report_writes_versioned_artifacts_and_transition_history(tmp_path):
    db_path = tmp_path / "tracker.db"
    output = tmp_path / "states"
    Database(str(db_path))

    first = write_state_report(str(db_path), output)
    first_payload = __import__("json").loads(Path(first["json"]).read_text())
    second = write_state_report(str(db_path), output)
    second_payload = __import__("json").loads(Path(second["json"]).read_text())

    assert len(first_payload["transitions"]) == 4
    assert {row["change_type"] for row in first_payload["transitions"]} == {"initial_state"}
    assert second_payload["transitions"] == []
    assert Path(second["latest_json"]).exists()
    assert "四个时钟独立判断" in Path(second["latest_markdown"]).read_text()
