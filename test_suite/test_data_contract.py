import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from tracker_v2 import (  # noqa: E402
    Database,
    GPUPriceRecord,
    ProductionDataContractError,
    PRODUCTION_PROVENANCE_FIELDS,
    PRODUCTION_TABLES,
    SchemaMigrationError,
)


def _base_provenance(source_type="public_pricing_page", source_url="https://example.com/pricing"):
    return {
        "run_id": "run-20260705",
        "source_id": "runpod-pricing",
        "source_url": source_url,
        "snapshot_path": "tracker_snapshots/test/runpod.html",
        "source_type": source_type,
        "collection_method": "html_parse",
        "observed_at": "2026-07-05T09:00:00Z",
        "fetched_at": "2026-07-05T09:05:00Z",
        "raw_payload_hash": "sha256:testpayload",
        "is_production_eligible": True,
        "confidence": 0.95,
        "error_code": None,
    }


def _gpu_row(provider, price, source_url, variant="SXM", gpu_count=1):
    row = {
        "date": "2026-07-05",
        "provider": provider,
        "gpu_model": "H100",
        "gpu_variant": variant,
        "billing_type": "on-demand",
        "commitment": "none",
        "gpu_count": gpu_count,
        "region": "US",
        "price_per_gpu_hour": price,
        "currency": "USD",
        "availability_observed": True,
    }
    row.update(_base_provenance(source_url=source_url))
    return row


def test_production_schema_tables_include_required_provenance(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert set(PRODUCTION_TABLES).issubset(tables)

    for table in PRODUCTION_TABLES:
        cols = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        }
        missing = set(PRODUCTION_PROVENANCE_FIELDS) - cols
        assert not missing, f"{table} missing provenance fields: {sorted(missing)}"

    conn.close()


def test_analysis_views_dedupe_facts_and_expose_ineligible_rows(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    base = (
        "2026-07-05", "gpu_rental", "H100", "H100 SXM", "price_per_gpu_hour",
        "USD/GPU hr", "on_demand", "RunPod", "RunPod API", "runpod-gpu-types",
        "https://api.runpod.io/graphql",
    )
    conn.executemany(
        """
        INSERT INTO production_market_facts (
            date, track, entity, sub_entity, metric, value, unit, dimension,
            vendor, source_name, source_id, source_url, run_id, snapshot_path,
            source_type, collection_method, observed_at, fetched_at,
            raw_payload_hash, is_production_eligible, confidence, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (*base[:5], 2.40, *base[5:], "run-old", "old.json", "official", "api",
             "2026-07-05 08:00:00", "2026-07-05 08:01:00", "old", True, 0.8, "old"),
            (*base[:5], 2.40, *base[5:], "run-new", "new.json", "official", "api",
             "2026-07-05 09:00:00", "2026-07-05 09:01:00", "new", True, 0.9, "new"),
            ("2026-07-05", "runpod_gpu_price_snapshot", "B300", "B300 MIG slice",
             "secure_price_per_gpu_hour", 0.35, "USD/GPU hr", "secure_cloud", "RunPod",
             "RunPod API", "runpod-gpu-types", "https://api.runpod.io/graphql", "run-mig",
             "mig.json", "official", "api", "2026-07-05 09:00:00", "2026-07-05 09:01:00",
             "mig", True, 0.8, "mig"),
        ],
    )

    rows = conn.execute(
        """
        SELECT sub_entity, value, eligible_for_analysis, analysis_exclusion_reason
        FROM production_market_facts_canonical
        ORDER BY sub_entity
        """
    ).fetchall()
    conn.close()

    assert rows == [
        ("B300 MIG slice", 0.35, False, "runpod_mig_slice"),
        ("H100 SXM", 2.40, True, None),
    ]


def test_latest_quality_view_keeps_one_state_per_affected_key(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO production_data_quality_events (
            event_id, table_name, severity, message, affected_key, is_blocking,
            run_id, source_id, source_url, snapshot_path, source_type,
            collection_method, observed_at, fetched_at, raw_payload_hash,
            is_production_eligible, confidence, error_code
        ) VALUES
          ('old', 'production_market_facts', 'warning', 'old state', 'gpu_orderbook_runpod', FALSE,
           'old', 'runpod', 'https://example.com', 'old.json', 'official', 'api',
           '2026-07-04 08:00:00', '2026-07-04 08:01:00', 'old', FALSE, 0, 'OLD'),
          ('new', 'production_market_facts', 'warning', 'new state', 'gpu_orderbook_runpod', FALSE,
           'new', 'runpod', 'https://example.com', 'new.json', 'official', 'api',
           '2026-07-05 08:00:00', '2026-07-05 08:01:00', 'new', FALSE, 0, 'NEW')
        """
    )
    result = conn.execute(
        "SELECT event_id, message FROM production_data_quality_events_latest"
    ).fetchall()
    conn.close()

    assert result == [("new", "new state")]


def test_seed_source_type_is_rejected_for_production_insert(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    row = _gpu_row("RunPod", 2.89, "https://www.runpod.io/pricing")
    row["source_type"] = "seed"

    with pytest.raises(ProductionDataContractError) as exc:
        db.insert_production_gpu_prices([row])

    message = str(exc.value)
    assert "PRODUCTION_SOURCE_TYPE_REJECTED" in message
    assert "seed/mock" in message


def test_gpu_upsert_key_keeps_runpod_lambda_computeprices_h100_rows(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    rows = [
        _gpu_row("RunPod", 2.89, "https://www.runpod.io/pricing", variant="PCIe"),
        _gpu_row("Lambda", 3.99, "https://lambda.ai/pricing", variant="SXM"),
        _gpu_row("ComputePrices", 1.40, "https://computeprices.com/gpus/h100", variant="SXM"),
    ]
    db.insert_production_gpu_prices(rows)

    # 同一个 deterministic key 再写一次，应更新 RunPod 价格，但不能删掉另外两家。
    updated_runpod = _gpu_row("RunPod", 3.29, "https://www.runpod.io/pricing", variant="PCIe")
    db.insert_production_gpu_prices([updated_runpod])

    conn = db.get_connection()
    result = conn.execute(
        """
        SELECT provider, price_per_gpu_hour
        FROM production_gpu_prices
        WHERE date = '2026-07-05' AND gpu_model = 'H100'
        ORDER BY provider
        """
    ).fetchall()
    conn.close()

    assert result == [
        ("ComputePrices", 1.40),
        ("Lambda", 3.99),
        ("RunPod", 3.29),
    ]


def test_production_gpu_query_ignores_legacy_seed_only_rows(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    db.insert_gpu_prices(
        [
            GPUPriceRecord(
                date="2026-07-05",
                provider="RunPod",
                gpu_model="H100",
                billing_type="on-demand",
                price_per_hour=0.01,
                source="seed_data",
            )
        ]
    )

    assert db.get_production_gpu_prices(gpu_model="H100").empty

    db.insert_production_gpu_prices(
        [_gpu_row("RunPod", 2.89, "https://www.runpod.io/pricing", variant="PCIe")]
    )
    production = db.get_production_gpu_prices(gpu_model="H100")

    assert len(production) == 1
    assert production.iloc[0]["provider"] == "RunPod"
    assert production.iloc[0]["price_per_gpu_hour"] == 2.89


def test_status_prints_source_type_quality_counts_and_legacy_unclassified(tmp_path):
    db_path = tmp_path / "ai_compute_tracker.db"
    db = Database(str(db_path))
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO gpu_prices_daily
            (date, provider, gpu_model, billing_type, price_per_hour, region, source)
        VALUES
            ('2026-07-05', 'legacy-provider', 'H100', 'on-demand', 0.01, 'US', NULL)
        """
    )
    conn.close()
    db.insert_production_gpu_prices(
        [_gpu_row("RunPod", 2.89, "https://www.runpod.io/pricing", variant="PCIe")]
    )

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "status"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "source_type data quality counts" in result.stdout
    assert "public_pricing_page" in result.stdout
    assert "legacy_unclassified" in result.stdout


def test_schema_migration_failure_exposes_clear_error(tmp_path):
    bad_path = tmp_path / "missing" / "tracker.db"

    with pytest.raises(SchemaMigrationError) as exc:
        Database(str(bad_path))

    assert "SCHEMA_MIGRATION_FAILED" in str(exc.value)
