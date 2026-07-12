import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from tracker_v2 import PRODUCTION_PROVENANCE_FIELDS, ProductionDataContractError, Database  # noqa: E402


def _field_names(model):
    return {field.name for field in dataclasses.fields(model)}


def _base_provenance(source_type="public_pricing_page"):
    return {
        "run_id": "run-20260705-t15",
        "source_id": "integration-test-source",
        "source_url": "https://example.com/source",
        "snapshot_path": "tracker_snapshots/test/source.html",
        "source_type": source_type,
        "collection_method": "html_parse",
        "observed_at": "2026-07-05T09:00:00Z",
        "fetched_at": "2026-07-05T09:05:00Z",
        "raw_payload_hash": "sha256:integration-surface",
        "is_production_eligible": True,
        "confidence": 0.95,
        "error_code": None,
    }


def test_observation_models_cover_t1_tables_and_provenance():
    from production_store import (  # noqa: E402
        CapexActualObservation,
        DataQualityEvent,
        GpuPriceObservation,
        OfficialEventObservation,
        PipelineRun,
    )

    provenance = set(PRODUCTION_PROVENANCE_FIELDS)
    expected = {
        GpuPriceObservation: {
            "date",
            "provider",
            "gpu_model",
            "gpu_variant",
            "billing_type",
            "commitment",
            "gpu_count",
            "region",
            "price_per_gpu_hour",
            "currency",
            "availability_observed",
        },
        CapexActualObservation: {
            "ticker",
            "company",
            "period_start",
            "period_end",
            "fiscal_period",
            "fiscal_year",
            "xbrl_tag",
            "accession_no",
            "capex_value",
            "unit",
            "filed_at",
            "form_type",
        },
        OfficialEventObservation: {
            "ticker",
            "announcement_date",
            "event_type",
            "metric",
            "value",
            "unit",
            "description",
            "fiscal_period",
        },
        DataQualityEvent: {
            "event_id",
            "table_name",
            "severity",
            "message",
            "affected_key",
            "is_blocking",
        },
        PipelineRun: {
            "pipeline_name",
            "status",
            "started_at",
            "completed_at",
            "rows_loaded",
            "message",
        },
    }

    for model, required_fields in expected.items():
        fields = _field_names(model)
        assert required_fields <= fields
        assert provenance <= fields


def test_company_config_contains_decision_universe_and_missing_config_error():
    from company_config import COMPANY_CONFIGS, CompanyConfigError, get_company_config  # noqa: E402

    assert set(COMPANY_CONFIGS) == {"MSFT", "AMZN", "GOOGL", "META", "ORCL"}
    for ticker in COMPANY_CONFIGS:
        config = get_company_config(ticker)
        assert config.ticker == ticker
        assert config.company_name
        assert len(config.cik) == 10
        assert config.capex_xbrl_tag
        assert config.included_in_decision_universe is True

    orcl = get_company_config("ORCL")
    assert orcl.cik == "0001341439"
    assert orcl.capex_xbrl_tag == "PaymentsToAcquirePropertyPlantAndEquipment"

    with pytest.raises(CompanyConfigError) as exc:
        get_company_config("NVDA")
    assert "COMPANY_CONFIG_MISSING" in str(exc.value)
    assert "allowed tickers" in str(exc.value)


def test_production_store_writes_all_supported_observations_through_t1_database(tmp_path):
    from production_store import (  # noqa: E402
        CapexActualObservation,
        DataQualityEvent,
        GpuPriceObservation,
        OfficialEventObservation,
        ProductionStore,
    )

    db = Database(str(tmp_path / "tracker.db"))
    store = ProductionStore(db)

    gpu = GpuPriceObservation(
        date="2026-07-05",
        provider="RunPod",
        gpu_model="H100",
        gpu_variant="PCIe",
        billing_type="on-demand",
        commitment="none",
        gpu_count=1,
        region="US",
        price_per_gpu_hour=2.89,
        currency="USD",
        availability_observed=True,
        **_base_provenance(),
    )
    capex = CapexActualObservation(
        ticker="ORCL",
        company="Oracle",
        period_start="2025-06-01",
        period_end="2026-05-31",
        fiscal_period="FY2026",
        fiscal_year=2026,
        xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        accession_no="0000950170-26-000001",
        capex_value=55.663,
        unit="USD_B",
        filed_at="2026-06-18",
        form_type="10-K",
        **_base_provenance(source_type="official"),
    )
    event = OfficialEventObservation(
        ticker="ORCL",
        announcement_date="2026-06-18",
        event_type="rpo",
        metric="remaining_performance_obligations",
        value=638.0,
        unit="USD_B",
        description="Official RPO disclosure.",
        fiscal_period="FY2026",
        **_base_provenance(source_type="official"),
    )
    quality = DataQualityEvent(
        event_id="dq-orcl-config-present",
        table_name="production_capex_actuals",
        severity="info",
        message="Company config present for ORCL.",
        affected_key="ORCL",
        is_blocking=False,
        **_base_provenance(source_type="manual_verified"),
    )

    assert store.insert_gpu_prices([gpu]) == 1
    assert store.insert_capex_actuals([capex]) == 1
    assert store.insert_official_events([event]) == 1
    assert store.insert_quality_events([quality]) == 1

    conn = db.get_connection()
    counts = dict(
        conn.execute(
            """
            SELECT 'gpu' AS name, COUNT(*) FROM production_gpu_prices
            UNION ALL SELECT 'capex', COUNT(*) FROM production_capex_actuals
            UNION ALL SELECT 'events', COUNT(*) FROM production_official_events
            UNION ALL SELECT 'quality', COUNT(*) FROM production_data_quality_events
            """
        ).fetchall()
    )
    conn.close()

    assert counts == {"gpu": 1, "capex": 1, "events": 1, "quality": 1}


def test_production_store_keeps_t1_provenance_guard(tmp_path):
    from production_store import GpuPriceObservation, ProductionStore  # noqa: E402

    db = Database(str(tmp_path / "tracker.db"))
    store = ProductionStore(db)
    bad_gpu = GpuPriceObservation(
        date="2026-07-05",
        provider="RunPod",
        gpu_model="H100",
        gpu_variant="PCIe",
        billing_type="on-demand",
        commitment="none",
        gpu_count=1,
        region="US",
        price_per_gpu_hour=2.89,
        currency="USD",
        availability_observed=True,
        **_base_provenance(source_type="seed"),
    )

    with pytest.raises(ProductionDataContractError) as exc:
        store.insert_gpu_prices([bad_gpu])

    assert "PRODUCTION_SOURCE_TYPE_REJECTED" in str(exc.value)


def test_public_proxy_update_reports_missing_computeprices_rows_without_legacy_fallback(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TRACKER_V2 / "tracker_v2.py"),
            "update",
            "--production",
            "--only",
            "public-proxy-prices",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "OCPI unavailable" in combined
    assert "public_gpu_price_proxy unavailable" in combined
    assert "PUBLIC_PROXY_SOURCE_MISSING" in combined
    assert "NOT_IMPLEMENTED_COLLECTOR" not in combined


def test_production_update_unknown_only_lists_allowed_values(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TRACKER_V2 / "tracker_v2.py"),
            "update",
            "--production",
            "--only",
            "unknown-source",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "UNKNOWN_PRODUCTION_ONLY" in combined
    assert "allowed values" in combined
    assert "gpu-prices" in combined


def test_production_cli_skeleton_commands_do_not_fall_back_to_legacy_seed(tmp_path):
    commands = [
        ["validate-data", "--production"],
        ["report", "--production"],
        ["status", "--quality"],
    ]

    for command in commands:
        result = subprocess.run(
            [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), *command],
            cwd=tmp_path,
            text=True,
            capture_output=True,
        )
        combined = result.stdout + result.stderr
        if command[0] in {"validate-data", "report"}:
            assert result.returncode != 0
            assert "NO_PRODUCTION_DATA" in combined or "quality_gate=FAIL" in combined
        else:
            assert result.returncode == 0, result.stderr
        assert "production" in combined.lower()
        assert "seed_data" not in combined
