import sys
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from company_config import decision_universe_configs  # noqa: E402
from production_store import (  # noqa: E402
    CapexActualObservation,
    DataQualityEvent,
    GpuPriceObservation,
    OfficialEventObservation,
    PublicProxyPriceObservation,
)
from tracker_v2 import Database, cmd_update  # noqa: E402


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _base_provenance(
    *,
    source_id="runpod-pricing",
    source_url="https://www.runpod.io/pricing",
    snapshot_path="tracker_snapshots/test/source.html",
    source_type="public_pricing_page",
    collection_method="html_parse",
    observed_at=None,
    fetched_at=None,
    confidence=0.9,
    error_code=None,
    eligible=True,
):
    fetched_at = fetched_at or _now_iso()
    return {
        "run_id": "cli-real-data-test",
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": snapshot_path,
        "source_type": source_type,
        "collection_method": collection_method,
        "observed_at": observed_at or fetched_at,
        "fetched_at": fetched_at,
        "raw_payload_hash": "sha256:" + ("c" * 64),
        "is_production_eligible": eligible,
        "confidence": confidence,
        "error_code": error_code,
    }


def _gpu_row(day, price, *, provider="RunPod", source_type="public_pricing_page", variant="SXM"):
    return GpuPriceObservation(
        date=day.isoformat(),
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
            snapshot_path=f"tracker_snapshots/test/{provider.lower()}-{day.isoformat()}.html",
            observed_at=f"{day.isoformat()}T00:00:00Z",
        ),
    )


def _capex_row(config):
    return CapexActualObservation(
        ticker=config.ticker,
        company=config.company_name,
        period_start="2026-01-01",
        period_end="2026-03-31",
        fiscal_period="FY2026 Q1",
        fiscal_year=2026,
        xbrl_tag=config.capex_xbrl_tag,
        accession_no=f"{config.ticker}-2026-q1",
        capex_value=30.0,
        unit="USD_B",
        filed_at="2026-04-30",
        form_type="10-Q",
        **_base_provenance(
            source_id=f"sec-companyfacts-{config.ticker}",
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/{config.cik}.json",
            snapshot_path=f"tracker_snapshots/test/sec-{config.ticker}.json",
            source_type="official",
            collection_method="sec_companyfacts_api",
            observed_at="2026-04-30T00:00:00Z",
            confidence=1.0,
        ),
    )


def _official_event(config, *, event_type="capacity_comment", metric="management_capacity_comment", value=1.0):
    return OfficialEventObservation(
        ticker=config.ticker,
        announcement_date="2026-07-01",
        event_type=event_type,
        metric=metric,
        value=value,
        unit="pct" if "revision" in metric else "evidence_flag",
        description=f"{config.company_name}: official source-backed event.",
        fiscal_period="FY2026",
        **_base_provenance(
            source_id=f"official-event-{config.ticker}",
            source_url=f"https://investors.example.com/{config.ticker}/event",
            snapshot_path=f"tracker_snapshots/test/{config.ticker}-event.html",
            source_type="official",
            collection_method="manual_sourcebacked_yaml",
            observed_at="2026-07-01T00:00:00Z",
            confidence=0.95,
        ),
    )


def _proxy_row(day):
    return PublicProxyPriceObservation(
        date=day.isoformat(),
        provider="ComputePrices",
        proxy_name="public_gpu_price_proxy",
        metric="computeprices_row_median_price_per_gpu_hour_proxy",
        value=2.25,
        unit="USD_per_gpu_hour",
        gpu_model="H100",
        region="aggregator_rows",
        **_base_provenance(
            source_id="computeprices-h100",
            source_url="https://computeprices.com/gpus/h100",
            snapshot_path="tracker_snapshots/test/computeprices-h100.html",
            source_type="aggregator",
            collection_method="html_parse",
            observed_at=f"{day.isoformat()}T00:00:00Z",
            confidence=0.65,
        ),
    )


def _quality_event(code, target):
    return DataQualityEvent(
        event_id=f"cli-real-data-test:{target}:{code}",
        table_name=f"production_{target.replace('-', '_')}",
        severity="error",
        message=f"{code}: simulated source failure for CLI closure test.",
        affected_key=target,
        is_blocking=True,
        **_base_provenance(
            source_id=target,
            source_url=f"https://example.com/{target}",
            snapshot_path=f"tracker_snapshots/test/{target}.error.txt",
            source_type="manual_verified",
            collection_method="unavailable_marker",
            confidence=0.0,
            error_code=code,
            eligible=False,
        ),
    )


def _install_collectors(monkeypatch, *, mode, calls):
    import data_sources.gpu_pricing as gpu_pricing
    import data_sources.official_events as official_events
    import data_sources.ocpi_policy as ocpi_policy
    import data_sources.sec_capex as sec_capex

    today = date.today()
    previous = today - timedelta(days=30)
    configs = decision_universe_configs()

    def gpu_update():
        calls.append("gpu-prices")
        if mode == "fail":
            events = [_quality_event("GPU_PROVIDER_PARSE_FAILED", "gpu-prices")]
            Database().insert_production_data_quality_events(events)
            return SimpleNamespace(observations=[], quality_events=events)
        rows = [_gpu_row(previous, 4.0), _gpu_row(today, 3.5)]
        Database().insert_production_gpu_prices(rows)
        return SimpleNamespace(observations=rows, quality_events=[])

    def capex_update():
        calls.append("capex-actuals")
        if mode == "fail":
            events = [_quality_event("SEC_SOURCE_UNAVAILABLE", "capex-actuals")]
            Database().insert_production_data_quality_events(events)
            return SimpleNamespace(actuals=[], quality_events=events, trend_availability={})
        rows = [_capex_row(config) for config in configs]
        Database().insert_production_capex_actuals(rows)
        return SimpleNamespace(
            actuals=rows,
            quality_events=[],
            trend_availability={config.ticker: {"sequential_quarter_count": 1, "can_evaluate_trend": False} for config in configs},
        )

    def official_update():
        calls.append("official-events")
        if mode == "fail":
            events = [_quality_event("SOURCE_UNAVAILABLE", "official-events")]
            Database().insert_production_data_quality_events(events)
            result = SimpleNamespace(production_events=[], quality_events=events, rejected_events=[])
            return result, {"events_inserted": 0, "quality_events_inserted": len(events)}
        if mode == "warn_cracking":
            rows = [
                _official_event(
                    configs[0],
                    event_type="capex_guidance_revision",
                    metric="capex_guidance_revision_pct",
                    value=-12.0,
                )
            ]
        else:
            rows = [_official_event(config) for config in configs]
        Database().insert_production_official_events(rows)
        result = SimpleNamespace(production_events=rows, quality_events=[], rejected_events=[])
        return result, {"events_inserted": len(rows), "quality_events_inserted": 0}

    def proxy_update():
        calls.append("public-proxy-prices")
        if mode == "fail":
            events = [_quality_event("PUBLIC_PROXY_SOURCE_MISSING", "public-proxy-prices")]
            Database().insert_production_data_quality_events(events)
            return SimpleNamespace(public_proxy_rows=[], quality_events=events)
        rows = [_proxy_row(today)]
        Database().insert_production_public_proxy_prices(rows)
        return SimpleNamespace(public_proxy_rows=rows, quality_events=[])

    monkeypatch.setattr(gpu_pricing, "update_production_gpu_prices", gpu_update)
    monkeypatch.setattr(sec_capex, "update_sec_capex_actuals", capex_update)
    monkeypatch.setattr(official_events, "collect_and_insert_official_events", official_update)
    monkeypatch.setattr(ocpi_policy, "update_ocpi_policy", proxy_update)


def _table_count(db_path, table_name):
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    finally:
        conn.close()


def test_init_schema_only_does_not_load_seed_or_production_rows(tmp_path):
    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "init"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Schema only" in result.stdout
    assert "NO_PRODUCTION_DATA" in result.stdout
    db_path = tmp_path / "ai_compute_tracker.db"
    assert _table_count(db_path, "gpu_prices_daily") == 0
    assert _table_count(db_path, "capex_quarterly") == 0
    assert _table_count(db_path, "ocpi_daily") == 0
    assert _table_count(db_path, "production_gpu_prices") == 0


def test_init_demo_seed_is_demo_only_and_does_not_populate_production_tables(tmp_path):
    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "init", "--demo-seed"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "DEMO ONLY" in result.stdout
    db_path = tmp_path / "ai_compute_tracker.db"
    assert _table_count(db_path, "gpu_prices_daily") > 0
    assert _table_count(db_path, "capex_quarterly") > 0
    assert _table_count(db_path, "ocpi_daily") > 0
    assert _table_count(db_path, "production_gpu_prices") == 0


def test_full_production_update_runs_collectors_validation_and_report(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    calls = []
    _install_collectors(monkeypatch, mode="pass", calls=calls)

    cmd_update(production=True)

    output = capsys.readouterr().out
    assert calls == ["gpu-prices", "capex-actuals", "official-events", "public-proxy-prices"]
    assert "production data validation" in output
    assert "quality_gate=PASS" in output
    assert "report_path=" in output
    report_files = list((tmp_path / "tracker_data").glob("*production*source-backed*.md"))
    assert report_files


def test_full_production_update_warn_exits_zero_without_cracking_call(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    calls = []
    _install_collectors(monkeypatch, mode="warn_cracking", calls=calls)

    cmd_update(production=True)

    output = capsys.readouterr().out
    assert "quality_gate=WARN" in output
    assert "WARN_CAPEX_CONFIRMATION_MISSING" in output
    assert "Scarcity Premium Cracking" not in output
    assert "regime=" not in output


def test_full_production_update_all_sources_fail_nonzero_and_prints_source_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    calls = []
    _install_collectors(monkeypatch, mode="fail", calls=calls)

    with pytest.raises(SystemExit) as exc:
        cmd_update(production=True)

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exc.value.code != 0
    assert calls == ["gpu-prices", "capex-actuals", "official-events", "public-proxy-prices"]
    assert "quality_gate=FAIL" in output
    assert "GPU_PROVIDER_PARSE_FAILED" in output
    assert "SEC_SOURCE_UNAVAILABLE" in output
    assert "SOURCE_UNAVAILABLE" in output
    assert "PUBLIC_PROXY_SOURCE_MISSING" in output
    assert "decision_state=" not in output
    assert "Scarcity Premium Cracking" not in output


def test_production_update_only_runs_named_target_without_full_closure(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    calls = []
    _install_collectors(monkeypatch, mode="pass", calls=calls)

    cmd_update(production=True, only="gpu-prices")

    output = capsys.readouterr().out
    assert calls == ["gpu-prices"]
    assert "production gpu prices update" in output
    assert "production data validation" not in output
    assert not (tmp_path / "tracker_data").exists()
