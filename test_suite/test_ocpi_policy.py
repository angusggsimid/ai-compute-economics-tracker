import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

import tracker_v2  # noqa: E402
from production_store import ProductionStore  # noqa: E402
from tracker_v2 import Database  # noqa: E402
from data_sources.ocpi_policy import update_ocpi_policy  # noqa: E402


def _gpu_provenance(source_id, source_url, snapshot_path, raw_hash, fetched_at):
    return {
        "run_id": "gpu-prices-test-run",
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": snapshot_path,
        "source_type": "aggregator",
        "collection_method": "html_parse",
        "observed_at": "2026-07-05T00:00:00Z",
        "fetched_at": fetched_at,
        "raw_payload_hash": raw_hash,
        "is_production_eligible": True,
        "confidence": 0.7,
        "error_code": None,
    }


def _gpu_row(provider, gpu_model, price, source_id, source_url, snapshot_path, raw_hash, fetched_at):
    row = {
        "date": "2026-07-05",
        "provider": provider,
        "gpu_model": gpu_model,
        "gpu_variant": f"{gpu_model} SXM",
        "billing_type": "aggregator-public-quote",
        "commitment": "aggregator_quote; quote_date=2026-07-05; quote_age_days=0",
        "gpu_count": 1,
        "region": "unknown",
        "price_per_gpu_hour": price,
        "currency": "USD",
        "availability_observed": True,
    }
    row.update(_gpu_provenance(source_id, source_url, snapshot_path, raw_hash, fetched_at))
    return row


def _insert_computeprices_rows(db):
    db.insert_production_gpu_prices(
        [
            _gpu_row(
                "Verda",
                "H100",
                0.67,
                "computeprices-h100",
                "https://computeprices.com/gpus/h100",
                "tracker_snapshots/gpu_prices/h100.html",
                "sha256:" + ("a" * 64),
                "2026-07-05T09:00:00Z",
            ),
            _gpu_row(
                "Microsoft Azure",
                "H100",
                1.14,
                "computeprices-h100",
                "https://computeprices.com/gpus/h100",
                "tracker_snapshots/gpu_prices/h100.html",
                "sha256:" + ("a" * 64),
                "2026-07-05T09:00:00Z",
            ),
            _gpu_row(
                "Hyperbolic",
                "H100",
                1.40,
                "computeprices-h100",
                "https://computeprices.com/gpus/h100",
                "tracker_snapshots/gpu_prices/h100.html",
                "sha256:" + ("a" * 64),
                "2026-07-05T09:00:00Z",
            ),
            _gpu_row(
                "fal.ai",
                "H200",
                1.40,
                "computeprices-h200",
                "https://computeprices.com/gpus/h200",
                "tracker_snapshots/gpu_prices/h200.html",
                "sha256:" + ("b" * 64),
                "2026-07-05T09:01:00Z",
            ),
            _gpu_row(
                "Provider B",
                "H200",
                2.00,
                "computeprices-h200",
                "https://computeprices.com/gpus/h200",
                "tracker_snapshots/gpu_prices/h200.html",
                "sha256:" + ("b" * 64),
                "2026-07-05T09:01:00Z",
            ),
        ]
    )


def _quality_rows(db_path):
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(
            """
            SELECT event_id, table_name, source_type, collection_method, error_code, message
            FROM production_data_quality_events
            ORDER BY event_id
            """
        ).fetchall()
    finally:
        conn.close()


def _proxy_rows(db_path):
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(
            """
            SELECT proxy_name, metric, gpu_model, value, unit, source_type,
                   source_url, snapshot_path, raw_payload_hash
            FROM production_public_proxy_prices
            ORDER BY gpu_model, metric
            """
        ).fetchall()
    finally:
        conn.close()


def test_missing_ocpi_feed_writes_licensed_unavailable_marker_without_fallback_value(tmp_path, monkeypatch):
    monkeypatch.delenv("ORNN_OCPI_FEED_URL", raising=False)
    monkeypatch.delenv("ORNN_OCPI_FEED_TOKEN", raising=False)
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))

    result = update_ocpi_policy(
        store=ProductionStore(db),
        run_id="ocpi-policy-test",
        fetched_at="2026-07-05T10:00:00Z",
    )

    ocpi_events = [event for event in result.quality_events if event.affected_key == "ornn_ocpi"]
    assert len(ocpi_events) == 1
    event = ocpi_events[0]
    assert event.error_code == "DATA_SOURCE_UNAVAILABLE"
    assert event.source_type == "licensed_unavailable"
    assert event.collection_method == "unavailable_marker"
    assert result.public_proxy_rows == []

    rows = _quality_rows(db_path)
    assert any(
        row[2] == "licensed_unavailable"
        and row[3] == "unavailable_marker"
        and row[4] == "DATA_SOURCE_UNAVAILABLE"
        for row in rows
    )

    conn = duckdb.connect(str(db_path))
    try:
        composite_count = conn.execute(
            "SELECT COUNT(*) FROM ocpi_daily WHERE source = 'composite_public'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert composite_count == 0


def test_computeprices_rows_generate_public_gpu_price_proxy_not_ocpi(tmp_path):
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    _insert_computeprices_rows(db)

    result = update_ocpi_policy(
        store=ProductionStore(db),
        run_id="public-proxy-test",
        fetched_at="2026-07-05T10:00:00Z",
    )

    assert len(result.public_proxy_rows) == 6
    assert {row.proxy_name for row in result.public_proxy_rows} == {"public_gpu_price_proxy"}
    assert {row.source_type for row in result.public_proxy_rows} == {"aggregator"}
    assert all("ocpi" not in row.proxy_name.lower() for row in result.public_proxy_rows)

    rows = _proxy_rows(db_path)
    assert len(rows) == 6
    assert {row[0] for row in rows} == {"public_gpu_price_proxy"}
    assert {row[1] for row in rows} == {
        "computeprices_row_count_proxy",
        "computeprices_row_min_price_per_gpu_hour_proxy",
        "computeprices_row_median_price_per_gpu_hour_proxy",
    }
    h100_values = {(metric, unit): value for _, metric, gpu, value, unit, *_ in rows if gpu == "H100"}
    assert h100_values[("computeprices_row_count_proxy", "rows")] == pytest.approx(3)
    assert h100_values[("computeprices_row_min_price_per_gpu_hour_proxy", "USD_per_gpu_hour")] == pytest.approx(0.67)
    assert h100_values[("computeprices_row_median_price_per_gpu_hour_proxy", "USD_per_gpu_hour")] == pytest.approx(1.14)
    assert all(row[5] == "aggregator" for row in rows)
    assert all(row[6].startswith("https://computeprices.com/gpus/") for row in rows)
    assert all(row[7] for row in rows)
    assert all(str(row[8]).startswith("sha256:") for row in rows)


def test_production_public_proxy_update_does_not_call_legacy_ocpi_or_write_composite_public(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "ai_compute_tracker.db"
    db = Database(str(db_path))
    _insert_computeprices_rows(db)
    called = {"legacy_ocpi": False}

    def forbidden_legacy_ocpi():
        called["legacy_ocpi"] = True
        raise AssertionError("production public-proxy-prices must not call hardcoded OCPI")

    monkeypatch.setattr(
        tracker_v2.GPUCollector,
        "fetch_ocpi_public",
        staticmethod(forbidden_legacy_ocpi),
    )

    tracker_v2.cmd_update(production=True, only="public-proxy-prices")

    assert called == {"legacy_ocpi": False}
    rows = _proxy_rows(db_path)
    assert rows
    assert all(row[0] == "public_gpu_price_proxy" for row in rows)

    conn = duckdb.connect(str(db_path))
    try:
        composite_count = conn.execute(
            "SELECT COUNT(*) FROM ocpi_daily WHERE source = 'composite_public'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert composite_count == 0


def test_cli_output_separates_ocpi_unavailable_from_public_proxy_available(tmp_path):
    db_path = tmp_path / "ai_compute_tracker.db"
    db = Database(str(db_path))
    _insert_computeprices_rows(db)

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

    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "OCPI unavailable" in combined
    assert "public_gpu_price_proxy available" in combined
    assert "composite_public" not in combined
