import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from data_quality import (  # noqa: E402
    FAIL,
    PASS,
    WARN,
    evaluate_quality_gate,
    record_pipeline_run,
    record_quality_event,
)
from production_store import (  # noqa: E402
    CapexActualObservation,
    GpuPriceObservation,
    OfficialEventObservation,
    ProductionStore,
)
from tracker_v2 import Database, GPUPriceRecord  # noqa: E402


AS_OF = "2026-07-05T12:00:00Z"


def _fresh_utc_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _base_provenance(
    *,
    run_id="test-run-20260705",
    source_id="runpod-pricing",
    source_url="https://www.runpod.io/pricing",
    snapshot_path="tracker_snapshots/test/source.html",
    source_type="public_pricing_page",
    collection_method="html_parse",
    observed_at="2026-07-05T10:00:00Z",
    fetched_at="2026-07-05T10:05:00Z",
    eligible=True,
    confidence=0.95,
    error_code=None,
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
        "raw_payload_hash": "sha256:" + ("a" * 64),
        "is_production_eligible": eligible,
        "confidence": confidence,
        "error_code": error_code,
    }


def _gpu_observation(
    provider,
    *,
    fetched_at="2026-07-05T10:05:00Z",
    source_type="public_pricing_page",
    source_id=None,
    source_url=None,
):
    source_id = source_id or f"{provider.lower()}-pricing"
    source_url = source_url or f"https://example.com/{provider.lower()}/pricing"
    return GpuPriceObservation(
        date=fetched_at[:10],
        provider=provider,
        gpu_model="H100",
        gpu_variant="SXM",
        billing_type="on-demand",
        commitment="per-hour",
        gpu_count=1,
        region="global_public_page",
        price_per_gpu_hour=3.29,
        currency="USD",
        availability_observed=True,
        **_base_provenance(
            source_id=source_id,
            source_url=source_url,
            source_type=source_type,
            fetched_at=fetched_at,
            observed_at=fetched_at,
        ),
    )


def _capex_observation(ticker, company, period_end="2026-03-31"):
    return CapexActualObservation(
        ticker=ticker,
        company=company,
        period_start="2026-01-01",
        period_end=period_end,
        fiscal_period="FY2026 Q1",
        fiscal_year=2026,
        xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        accession_no=f"{ticker}-2026-q1",
        capex_value=30.0,
        unit="USD_B",
        filed_at="2026-04-30",
        form_type="10-Q",
        **_base_provenance(
            source_id=f"sec-companyfacts-{ticker}",
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/{ticker}.json",
            source_type="official",
            collection_method="sec_companyfacts_api",
            observed_at="2026-04-30T00:00:00Z",
            fetched_at="2026-07-05T10:05:00Z",
        ),
    )


def _official_event_observation(ticker, company):
    return OfficialEventObservation(
        ticker=ticker,
        announcement_date="2026-07-01",
        event_type="capacity_comment",
        metric="management_capacity_comment",
        value=1.0,
        unit="signal",
        description=f"{company}: official capacity comment.",
        fiscal_period="FY2026",
        **_base_provenance(
            source_id=f"official-event-{ticker}",
            source_url=f"https://investors.example.com/{ticker}/event",
            source_type="official",
            collection_method="manual_sourcebacked_yaml",
            observed_at="2026-07-01T00:00:00Z",
            fetched_at="2026-07-05T10:05:00Z",
        ),
    )


def _insert_capex_universe(db):
    rows = [
        _capex_observation("MSFT", "Microsoft"),
        _capex_observation("AMZN", "Amazon"),
        _capex_observation("GOOGL", "Alphabet"),
        _capex_observation("META", "Meta"),
        _capex_observation("ORCL", "Oracle", period_end="2026-05-31"),
    ]
    db.insert_production_capex_actuals(rows)


def _insert_official_event_universe(db):
    db.insert_production_official_events(
        [
            _official_event_observation("MSFT", "Microsoft"),
            _official_event_observation("AMZN", "Amazon"),
            _official_event_observation("GOOGL", "Alphabet"),
            _official_event_observation("META", "Meta"),
            _official_event_observation("ORCL", "Oracle"),
        ]
    )


def _reason_codes(result):
    return {reason.reason_code for reason in result.reasons}


def test_empty_production_database_fails_with_no_production_data(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == FAIL
    assert "NO_PRODUCTION_DATA" in _reason_codes(result)
    assert result.exit_code == 1


def test_quality_gate_warns_for_legacy_seed_but_does_not_treat_it_as_production_fail(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    db.insert_gpu_prices(
        [
            GPUPriceRecord(
                date="2026-07-05",
                provider="legacy",
                gpu_model="H100",
                billing_type="on-demand",
                price_per_hour=0.01,
                source="seed_data",
            )
        ]
    )
    db.insert_production_gpu_prices(
        [
            _gpu_observation(
                "RunPod",
                source_id="runpod-pricing",
                source_url="https://www.runpod.io/pricing",
            )
        ]
    )
    _insert_capex_universe(db)
    _insert_official_event_universe(db)

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == WARN
    assert "LEGACY_SEED_ROWS_PRESENT" in _reason_codes(result)
    assert "SEED_ROWS_PRESENT" not in _reason_codes(result)
    assert result.exit_code == 0


def test_quality_gate_passes_when_required_production_layers_are_fresh_and_covered(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    db.insert_production_gpu_prices(
        [
            _gpu_observation("RunPod", source_id="runpod-pricing", source_url="https://www.runpod.io/pricing"),
            _gpu_observation("Lambda", source_id="lambda-pricing", source_url="https://lambda.ai/pricing"),
        ]
    )
    _insert_capex_universe(db)
    _insert_official_event_universe(db)

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == PASS
    assert result.exit_code == 0
    assert "NO_PRODUCTION_DATA" not in _reason_codes(result)
    assert "CAPEX_COMPANY_MISSING" not in _reason_codes(result)
    assert "SOURCE_STALE" not in _reason_codes(result)


def test_quality_gate_flags_stale_gpu_and_missing_capex_company(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    db.insert_production_gpu_prices(
        [
            _gpu_observation(
                "RunPod",
                fetched_at="2026-06-25T10:05:00Z",
                source_id="runpod-pricing",
                source_url="https://www.runpod.io/pricing",
            )
        ]
    )
    db.insert_production_capex_actuals(
        [
            _capex_observation("MSFT", "Microsoft"),
            _capex_observation("AMZN", "Amazon"),
            _capex_observation("GOOGL", "Alphabet"),
            _capex_observation("META", "Meta"),
        ]
    )
    _insert_official_event_universe(db)

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == FAIL
    assert "SOURCE_STALE" in _reason_codes(result)
    assert "CAPEX_COMPANY_MISSING" in _reason_codes(result)
    assert result.exit_code == 1


def test_quality_gate_reads_source_failures_and_treats_ocpi_unavailable_as_warn(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    store = ProductionStore(db)
    db.insert_production_gpu_prices(
        [_gpu_observation("RunPod", source_id="runpod-pricing", source_url="https://www.runpod.io/pricing")]
    )
    _insert_capex_universe(db)
    _insert_official_event_universe(db)

    record_quality_event(
        store,
        table_name="production_gpu_prices",
        reason_code="GPU_PROVIDER_PARSE_FAILED",
        message="RunPod parser changed.",
        affected_key="runpod-pricing",
        source_id="runpod-pricing",
        source_url="https://www.runpod.io/pricing",
        snapshot_path="tracker_snapshots/gpu_prices/runpod-failed.html",
        run_id="quality-event-test",
        severity="error",
        fetched_at="2026-07-05T10:05:00Z",
    )
    record_quality_event(
        store,
        table_name="ornn_ocpi_feed",
        reason_code="DATA_SOURCE_UNAVAILABLE",
        message="OCPI licensed feed unavailable.",
        affected_key="ornn_ocpi",
        source_id="ornn-ocpi",
        source_url="https://www.ornn.ai/",
        source_type="licensed_unavailable",
        collection_method="unavailable_marker",
        run_id="quality-event-test",
        severity="warning",
        fetched_at="2026-07-05T10:05:00Z",
    )

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == WARN
    assert "GPU_PROVIDER_PARSE_FAILED" in _reason_codes(result)
    assert "DATA_SOURCE_UNAVAILABLE" in _reason_codes(result)
    ocpi_reasons = [
        reason
        for reason in result.reasons
        if reason.reason_code == "DATA_SOURCE_UNAVAILABLE" and reason.affected_key == "ornn_ocpi"
    ]
    assert ocpi_reasons
    assert ocpi_reasons[0].severity == WARN


def test_official_source_failure_is_suppressed_after_newer_source_backed_event(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    store = ProductionStore(db)
    db.insert_production_gpu_prices(
        [_gpu_observation("RunPod", source_id="runpod-pricing", source_url="https://www.runpod.io/pricing")]
    )
    _insert_capex_universe(db)
    _insert_official_event_universe(db)
    record_quality_event(
        store,
        table_name="production_official_events",
        reason_code="SOURCE_UNAVAILABLE",
        message="Old Meta IR page returned HTTP 403.",
        affected_key="META|capex_guidance_revision|fy2026_capex_guidance|2026-04-29",
        source_id="manual_sourcebacked_yaml:meta_old",
        source_url="https://investor.atmeta.com/old",
        source_type="official",
        collection_method="manual_sourcebacked_yaml",
        run_id="old-official-failure",
        severity="warning",
        fetched_at="2026-07-04T10:05:00Z",
    )
    db.insert_production_official_events(
        [
            OfficialEventObservation(
                ticker="META",
                announcement_date="2026-04-29",
                event_type="capex_guidance_revision",
                metric="fy2026_capex_guidance_low",
                value=125.0,
                unit="USD_B",
                description="Meta: source-backed replacement.",
                fiscal_period="FY2026",
                **_base_provenance(
                    source_id="manual_sourcebacked_yaml:meta_new",
                    source_url="https://www.sec.gov/Archives/meta.htm",
                    source_type="official",
                    collection_method="manual_sourcebacked_yaml",
                    observed_at="2026-04-29T00:00:00Z",
                    fetched_at="2026-07-05T10:05:00Z",
                ),
            )
        ]
    )

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == PASS
    assert not [
        reason
        for reason in result.reasons
        if reason.table_name == "production_official_events"
        and reason.reason_code == "SOURCE_UNAVAILABLE"
        and reason.affected_key.startswith("META|")
    ]


def test_pipeline_run_api_writes_snapshot_and_quality_gate_reads_runs(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    store = ProductionStore(db)
    snapshot_dir = tmp_path / "tracker_snapshots" / "pipeline_runs"

    run_id = record_pipeline_run(
        store,
        pipeline_name="gpu-prices",
        status="SUCCESS",
        rows_loaded=2,
        message="Loaded two GPU rows.",
        started_at="2026-07-05T10:00:00Z",
        completed_at="2026-07-05T10:01:00Z",
        snapshot_dir=snapshot_dir,
    )

    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT run_id, pipeline_name, status, rows_loaded, snapshot_path FROM production_pipeline_runs"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0][0] == run_id
    assert rows[0][1] == "gpu-prices"
    assert rows[0][2] == "SUCCESS"
    assert rows[0][3] == 2
    assert Path(rows[0][4]).exists()


def test_validate_data_cli_uses_quality_gate_exit_semantics(tmp_path):
    db_path = tmp_path / "ai_compute_tracker.db"
    db = Database(str(db_path))
    db.insert_production_gpu_prices(
        [
            _gpu_observation(
                "RunPod",
                fetched_at=_fresh_utc_iso(),
                source_id="runpod-pricing",
                source_url="https://www.runpod.io/pricing",
            )
        ]
    )
    _insert_capex_universe(db)
    _insert_official_event_universe(db)

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "validate-data", "--production"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "quality_gate=PASS" in result.stdout
    assert "collectors=NOT_IMPLEMENTED_COLLECTOR" not in result.stdout


def test_validate_data_cli_empty_production_db_exits_nonzero(tmp_path):
    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "validate-data", "--production"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "quality_gate=FAIL" in combined
    assert "NO_PRODUCTION_DATA" in combined


def test_seed_rows_present_in_production_used_tables_is_fail_even_if_inserted_outside_guard(tmp_path):
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    db.insert_production_gpu_prices(
        [_gpu_observation("RunPod", source_id="runpod-pricing", source_url="https://www.runpod.io/pricing")]
    )
    _insert_capex_universe(db)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE production_gpu_prices SET source_type = 'seed' WHERE provider = 'RunPod'"
        )
    finally:
        conn.close()

    result = evaluate_quality_gate(db, as_of=AS_OF)

    assert result.status == FAIL
    assert "SEED_ROWS_PRESENT" in _reason_codes(result)
