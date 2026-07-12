import subprocess
import sys
from pathlib import Path

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from decision_engine import DecisionEngine  # noqa: E402
from production_store import (  # noqa: E402
    CapexActualObservation,
    GpuPriceObservation,
    OfficialEventObservation,
)
from tracker_v2 import AnalysisEngine, Database  # noqa: E402


AS_OF = "2026-07-05T12:00:00Z"


def _base_provenance(
    *,
    run_id="decision-test-run",
    source_id="runpod-pricing",
    source_url="https://www.runpod.io/pricing",
    snapshot_path="tracker_snapshots/test/source.html",
    source_type="public_pricing_page",
    collection_method="html_parse",
    observed_at="2026-07-05T00:00:00Z",
    fetched_at="2026-07-05T10:00:00Z",
    confidence=0.9,
):
    return {
        "run_id": run_id,
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": snapshot_path,
        "source_type": source_type,
        "collection_method": collection_method,
        "observed_at": observed_at,
        "fetched_at": fetched_at,
        "raw_payload_hash": "sha256:" + ("d" * 64),
        "is_production_eligible": True,
        "confidence": confidence,
        "error_code": None,
    }


def _official_gpu_row(date, price, provider="RunPod", variant="SXM"):
    return GpuPriceObservation(
        date=date,
        provider=provider,
        gpu_model="H100",
        gpu_variant=variant,
        billing_type="on-demand",
        commitment="per-hour",
        gpu_count=1,
        region="global_public_page",
        price_per_gpu_hour=price,
        currency="USD",
        availability_observed=True,
        **_base_provenance(
            source_id=f"{provider.lower()}-pricing",
            source_url=f"https://example.com/{provider.lower()}/pricing",
            observed_at=f"{date}T00:00:00Z",
            fetched_at="2026-07-05T10:00:00Z",
        ),
    )


def _aggregator_gpu_row(date, price, quote_idx, model="H100"):
    source_id = f"computeprices-{model.lower()}"
    source_url = f"https://computeprices.com/gpus/{model.lower()}"
    return GpuPriceObservation(
        date=date,
        provider=f"ComputeProvider{quote_idx:02d}",
        gpu_model=model,
        gpu_variant="SXM" if model == "H100" else model,
        billing_type="aggregator-public-quote",
        commitment=f"aggregator_quote; quote_date={date}; quote_age_days=1; availability=listed",
        gpu_count=1,
        region="unknown",
        price_per_gpu_hour=price,
        currency="USD",
        availability_observed=True,
        **_base_provenance(
            source_id=source_id,
            source_url=source_url,
            snapshot_path=f"tracker_snapshots/test/{source_id}.html",
            source_type="aggregator",
            observed_at=f"{date}T00:00:00Z",
            fetched_at="2026-07-05T10:00:00Z",
            confidence=0.7,
        ),
    )


def _insert_official_price_easing(db):
    db.insert_production_gpu_prices(
        [
            _official_gpu_row("2026-06-05", 4.00),
            _official_gpu_row("2026-07-05", 3.50),
        ]
    )


def _insert_aggregator_breadth_weakening(db):
    rows = []
    for idx in range(8):
        rows.append(_aggregator_gpu_row("2026-06-05", 2.00 + idx * 0.01, idx))
        rows.append(_aggregator_gpu_row("2026-07-05", 1.60 + idx * 0.01, idx))
    db.insert_production_gpu_prices(rows)


def _capex_actual(ticker, company, period_start, period_end, fiscal_period, value):
    return CapexActualObservation(
        ticker=ticker,
        company=company,
        period_start=period_start,
        period_end=period_end,
        fiscal_period=fiscal_period,
        fiscal_year=2026,
        xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        accession_no=f"{ticker}-{period_end}",
        capex_value=value,
        unit="USD_B",
        filed_at=period_end,
        form_type="10-Q",
        **_base_provenance(
            source_id=f"sec-companyfacts-{ticker}",
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/{ticker}.json",
            snapshot_path=f"tracker_snapshots/test/sec-{ticker}.json",
            source_type="official",
            collection_method="sec_companyfacts_api",
            observed_at=f"{period_end}T00:00:00Z",
            fetched_at="2026-07-05T10:00:00Z",
        ),
    )


def _insert_one_quarter_capex_universe(db):
    rows = [
        ("MSFT", "Microsoft", "2026-01-01", "2026-03-31", "FY2026 Q3", 30.876),
        ("AMZN", "Amazon", "2026-01-01", "2026-03-31", "FY2026 Q1", 44.203),
        ("GOOGL", "Alphabet", "2026-01-01", "2026-03-31", "FY2026 Q1", 35.674),
        ("META", "Meta", "2026-01-01", "2026-03-31", "FY2026 Q1", 18.997),
        ("ORCL", "Oracle", "2025-06-01", "2026-05-31", "FY2026", 55.663),
    ]
    db.insert_production_capex_actuals([_capex_actual(*row) for row in rows])


def _official_event(ticker, event_type, metric, value, description):
    return OfficialEventObservation(
        ticker=ticker,
        announcement_date="2026-07-01",
        event_type=event_type,
        metric=metric,
        value=value,
        unit="pct" if "revision" in metric else "signal",
        description=description,
        fiscal_period="FY2026",
        **_base_provenance(
            source_id=f"official-event-{ticker}-{event_type}",
            source_url=f"https://investors.example.com/{ticker}/{event_type}",
            snapshot_path=f"tracker_snapshots/test/{ticker}-{event_type}.html",
            source_type="official",
            collection_method="manual_sourcebacked_yaml",
            observed_at="2026-07-01T00:00:00Z",
            fetched_at="2026-07-05T10:00:00Z",
            confidence=0.95,
        ),
    )


def test_price_only_signal_is_watch_and_confidence_capped(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    _insert_official_price_easing(db)

    result = DecisionEngine(db).evaluate(as_of=AS_OF)

    assert result.state == "Watch"
    assert result.confidence <= 40
    assert "GPU_OFFICIAL_EASING" in {item["code"] for item in result.evidence}
    assert "CAPEX_CONFIRMATION_MISSING" in {item["code"] for item in result.missing_data}
    assert result.source_references
    assert "legacy_metrics" in result.to_dict()
    assert result.to_dict()["legacy_metrics"]["csi"]["used_for_production_decision"] is False


def test_official_missing_cap_prevents_cracking_even_with_market_triggers(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    _insert_official_price_easing(db)
    _insert_aggregator_breadth_weakening(db)

    result = DecisionEngine(db).evaluate(as_of=AS_OF)

    assert result.state == "Watch"
    assert result.confidence <= 40
    assert "AGGREGATOR_BREADTH_WEAKENING" in {item["code"] for item in result.evidence}
    assert "CAPEX_CONFIRMATION_MISSING" in {item["code"] for item in result.missing_data}


def test_cracking_requires_official_confirmation_not_display_only_capex(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    _insert_official_price_easing(db)
    _insert_aggregator_breadth_weakening(db)
    _insert_one_quarter_capex_universe(db)
    db.insert_production_official_events(
        [
            _official_event(
                "MSFT",
                "capex_guidance_revision",
                "capex_guidance_revision_pct",
                8.0,
                "Official guidance revision was positive.",
            )
        ]
    )

    result = DecisionEngine(db).evaluate(as_of=AS_OF)

    assert result.state != "Scarcity Premium Cracking"
    assert "CAPEX_TREND_DISPLAY_ONLY" in {item["code"] for item in result.missing_data}
    assert "GUIDANCE_POSITIVE_REVISION" in {item["code"] for item in result.counter_evidence}


def test_negative_official_revision_confirms_cracking_when_market_easing_is_present(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    _insert_official_price_easing(db)
    _insert_aggregator_breadth_weakening(db)
    _insert_one_quarter_capex_universe(db)
    db.insert_production_official_events(
        [
            _official_event(
                "MSFT",
                "capex_guidance_revision",
                "capex_guidance_revision_pct",
                -12.0,
                "Official guidance revision was negative.",
            )
        ]
    )

    result = DecisionEngine(db).evaluate(as_of=AS_OF)

    assert result.state == "Scarcity Premium Cracking"
    assert result.confidence > 40
    assert "GUIDANCE_NEGATIVE_REVISION" in {item["code"] for item in result.evidence}


def test_aggregator_single_snapshot_marks_trend_insufficient(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    db.insert_production_gpu_prices(
        [_aggregator_gpu_row("2026-07-05", 1.50 + idx * 0.01, idx) for idx in range(8)]
    )

    result = DecisionEngine(db).evaluate(as_of=AS_OF)

    assert result.state == "No Signal"
    assert "AGGREGATOR_TREND_INSUFFICIENT" in {item["code"] for item in result.missing_data}


def test_production_report_outputs_decision_state_and_not_primary_csi(tmp_path):
    db_path = tmp_path / "ai_compute_tracker.db"
    db = Database(str(db_path))
    _insert_official_price_easing(db)
    _insert_one_quarter_capex_universe(db)
    db.insert_production_official_events(
        [
            _official_event(
                "MSFT",
                "capacity_comment",
                "management_capacity_comment",
                1.0,
                "Official comment says demand exceeds available AI capacity.",
            )
        ]
    )

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "report", "--production"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert "decision_state=" in result.stdout
    assert "source-backed decision" in result.stdout
    assert "COMPOSITE SCARCITY INDEX" not in result.stdout
    assert "CSI:" not in result.stdout


def test_production_report_does_not_write_csi_history(tmp_path):
    db_path = tmp_path / "ai_compute_tracker.db"
    db = Database(str(db_path))
    _insert_official_price_easing(db)
    _insert_one_quarter_capex_universe(db)
    db.insert_production_official_events(
        [
            _official_event(
                "MSFT",
                "capex_guidance_revision",
                "capex_guidance_revision_pct",
                -12.0,
                "Official guidance revision was negative.",
            )
        ]
    )

    subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "report", "--production"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    conn = db.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM csi_history").fetchone()[0]
    conn.close()

    assert count == 0
    assert "legacy/demo only" in (AnalysisEngine.calculate_csi.__doc__ or "").lower()
