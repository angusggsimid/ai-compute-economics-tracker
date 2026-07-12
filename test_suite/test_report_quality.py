import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from production_store import CapexActualObservation, GpuPriceObservation, OfficialEventObservation  # noqa: E402
from reports import ReportGenerationError, generate_production_decision_brief  # noqa: E402
from tracker_v2 import Database  # noqa: E402


AS_OF = "2026-07-05T12:00:00Z"


def _fresh_utc_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _base_provenance(
    *,
    run_id="report-quality-test",
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
        "raw_payload_hash": "sha256:" + ("9" * 64),
        "is_production_eligible": True,
        "confidence": confidence,
        "error_code": None,
    }


def _gpu_row(
    *,
    provider="RunPod",
    gpu_model="H100",
    gpu_variant="PCIe",
    price=2.89,
    source_type="public_pricing_page",
    fetched_at="2026-07-05T10:00:00Z",
):
    return GpuPriceObservation(
        date=fetched_at[:10],
        provider=provider,
        gpu_model=gpu_model,
        gpu_variant=gpu_variant,
        billing_type="on-demand",
        commitment="per-hour",
        gpu_count=1,
        region="global_public_page",
        price_per_gpu_hour=price,
        currency="USD",
        availability_observed=True,
        **_base_provenance(
            source_id=f"{provider.lower()}-{gpu_model.lower()}-pricing",
            source_url=f"https://example.com/{provider.lower()}/pricing",
            snapshot_path=f"tracker_snapshots/test/{provider.lower()}-{gpu_model.lower()}.html",
            fetched_at=fetched_at,
            observed_at=fetched_at,
            source_type=source_type,
        ),
    )


def _capex_row(ticker, company, period_end, fiscal_period, value, accession):
    return CapexActualObservation(
        ticker=ticker,
        company=company,
        period_start="2026-01-01",
        period_end=period_end,
        fiscal_period=fiscal_period,
        fiscal_year=2026,
        xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        accession_no=accession,
        capex_value=value,
        unit="USD_B",
        filed_at="2026-04-30",
        form_type="10-Q",
        **_base_provenance(
            source_id=f"sec-companyfacts-{ticker}",
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/{ticker}.json",
            snapshot_path=f"tracker_snapshots/test/sec-{ticker}.json",
            source_type="official",
            collection_method="sec_companyfacts_api",
            observed_at=f"{period_end}T00:00:00Z",
        ),
    )


def _official_event(ticker, event_type="capacity_comment", value=1.0):
    return OfficialEventObservation(
        ticker=ticker,
        announcement_date="2026-07-01",
        event_type=event_type,
        metric="management_capacity_comment",
        value=value,
        unit="evidence_flag",
        description=f"{ticker} official capacity comment.",
        fiscal_period="FY2026",
        **_base_provenance(
            source_id=f"official-event-{ticker}",
            source_url=f"https://investors.example.com/{ticker}/event",
            snapshot_path=f"tracker_snapshots/test/{ticker}-event.html",
            source_type="official",
            collection_method="manual_sourcebacked_yaml",
            observed_at="2026-07-01T00:00:00Z",
            confidence=0.95,
        ),
    )


def _insert_source_backed_rows(db, *, gpu_fetched_at="2026-07-05T10:00:00Z"):
    db.insert_production_gpu_prices(
        [
            _gpu_row(provider="RunPod", gpu_variant="PCIe", price=2.89, fetched_at=gpu_fetched_at),
            _gpu_row(provider="Lambda", gpu_variant="SXM", price=3.29, fetched_at=gpu_fetched_at),
        ]
    )
    db.insert_production_capex_actuals(
        [
            _capex_row("MSFT", "Microsoft", "2026-03-31", "FY2026 Q3", 30.876, "0001193125-26-191507"),
            _capex_row("AMZN", "Amazon", "2026-03-31", "FY2026 Q1", 44.203, "0001018724-26-000014"),
            _capex_row("GOOGL", "Alphabet", "2026-03-31", "FY2026 Q1", 35.674, "0001652044-26-000048"),
            _capex_row("META", "Meta", "2026-03-31", "FY2026 Q1", 18.997, "0001628280-26-028526"),
            _capex_row("ORCL", "Oracle", "2026-05-31", "FY2026", 55.663, "0001193125-26-277521"),
        ]
    )
    db.insert_production_official_events([_official_event(ticker) for ticker in ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]])


def test_source_backed_brief_has_required_sections_and_cited_evidence_tables(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    _insert_source_backed_rows(db)

    result = generate_production_decision_brief(
        db,
        output_dir=tmp_path / "tracker_data",
        as_of=AS_OF,
    )

    report = result.content
    assert "Data quality verdict" in report
    assert "Current decision state" in report
    assert "GPU price evidence table" in report
    assert "CAPEX actual/guidance/RPO evidence table" in report
    assert "Missing data and failed sources" in report
    assert "Investment implication by layer" in report
    assert "RunPod" in report
    assert "H100" in report
    assert "PCIe" in report
    assert "2.89" in report
    assert "source_url=" in report
    assert "snapshot=" in report
    assert "MSFT" in report
    assert "FY2026 Q3" in report
    assert "30.876" in report
    assert "0001193125-26-191507" in report
    assert "legacy/demo" in report
    assert "COMPOSITE SCARCITY INDEX" not in report
    assert "CSI:" not in report
    assert "tracker complete" not in report.lower()
    assert result.output_path is not None
    assert result.output_path.exists()
    assert "production" in result.output_path.name
    assert "source-backed" in result.output_path.name
    assert "20260705" in result.output_path.name


def test_report_generation_fails_when_numeric_evidence_row_has_no_citation(tmp_path):
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    _insert_source_backed_rows(db)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            UPDATE production_gpu_prices
            SET source_url = '', snapshot_path = ''
            WHERE provider = 'RunPod' AND gpu_model = 'H100'
            """
        )
    finally:
        conn.close()

    with pytest.raises(ReportGenerationError) as exc:
        generate_production_decision_brief(
            db,
            output_dir=tmp_path / "tracker_data",
            as_of=AS_OF,
        )

    assert exc.value.code == "REPORT_UNCITED_VALUE"
    assert "REPORT_UNCITED_VALUE" in str(exc.value)


def test_seed_only_cli_report_fails_without_regime_call(tmp_path):
    init = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "init", "--demo-seed"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert init.returncode == 0, init.stderr

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "report", "--production"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Data quality verdict" in combined
    assert "FAIL" in combined
    assert "FAIL_SEED_ONLY" in combined or "NO_PRODUCTION_DATA" in combined
    assert "decision_state=" not in combined
    assert "Scarcity Premium Cracking" not in combined
    assert "regime=" not in combined
    assert "tracker complete" not in combined.lower()


def test_cli_writes_production_source_backed_report_file(tmp_path):
    db = Database(str(tmp_path / "ai_compute_tracker.db"))
    _insert_source_backed_rows(db, gpu_fetched_at=_fresh_utc_iso())

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "report", "--production"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Data quality verdict" in result.stdout
    assert "report_path=" in result.stdout
    report_files = sorted((tmp_path / "tracker_data").glob("*production*source-backed*.md"))
    assert report_files
    content = report_files[-1].read_text(encoding="utf-8")
    assert "RunPod" in content
    assert "2.89" in content
    assert "MSFT" in content
    assert "30.876" in content
