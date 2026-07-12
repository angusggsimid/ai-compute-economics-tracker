import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

import tracker_v2  # noqa: E402
from tracker_v2 import Database  # noqa: E402


def _run_tracker(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), *args],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )


def _count(db_path, sql):
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def _seed_rows(db_path):
    return _count(
        db_path,
        """
        SELECT
            (SELECT COUNT(*) FROM gpu_prices_daily WHERE source = 'seed_data')
          + (SELECT COUNT(*) FROM capex_quarterly WHERE source = 'seed_data')
          + (SELECT COUNT(*) FROM ocpi_daily WHERE source = 'seed_data')
          + (SELECT COUNT(*) FROM capex_guidance WHERE source = 'seed_guidance')
          + (SELECT COUNT(*) FROM capex_daily_implied WHERE source LIKE 'forward_%')
          + (SELECT COUNT(*) FROM capex_nowcast WHERE source = 'gpu_price_proxy')
          + (SELECT COUNT(*) FROM csi_history)
        """,
    )


def _production_rows(db_path):
    return _count(
        db_path,
        """
        SELECT
            (SELECT COUNT(*) FROM production_gpu_prices)
          + (SELECT COUNT(*) FROM production_capex_actuals)
          + (SELECT COUNT(*) FROM production_official_events)
          + (SELECT COUNT(*) FROM production_public_proxy_prices)
          + (SELECT COUNT(*) FROM production_data_quality_events)
          + (SELECT COUNT(*) FROM production_pipeline_runs)
        """,
    )


def _insert_production_gpu_row(db_path):
    db = Database(str(db_path))
    db.insert_production_gpu_prices(
        [
            {
                "date": "2026-07-05",
                "provider": "RunPod",
                "gpu_model": "H100",
                "gpu_variant": "PCIe",
                "billing_type": "on-demand",
                "commitment": "none",
                "gpu_count": 1,
                "region": "US",
                "price_per_gpu_hour": 2.89,
                "currency": "USD",
                "availability_observed": True,
                "run_id": "seed-isolation-test",
                "source_id": "runpod-pricing",
                "source_url": "https://www.runpod.io/pricing",
                "snapshot_path": "tracker_snapshots/test/runpod.html",
                "source_type": "public_pricing_page",
                "collection_method": "html_parse",
                "observed_at": "2026-07-05T09:00:00Z",
                "fetched_at": "2026-07-05T09:05:00Z",
                "raw_payload_hash": "sha256:seed-isolation",
                "is_production_eligible": True,
                "confidence": 0.95,
                "error_code": None,
            }
        ]
    )


def test_init_defaults_to_schema_only_without_seed_l2_l3_or_csi(tmp_path):
    result = _run_tracker(tmp_path, "init")

    assert result.returncode == 0, result.stderr
    assert "schema only" in result.stdout.lower()
    assert "seed data" not in result.stdout.lower()

    db_path = tmp_path / "ai_compute_tracker.db"
    assert db_path.exists()
    assert _seed_rows(db_path) == 0
    assert _production_rows(db_path) == 0


def test_demo_seed_is_explicit_and_clearly_labeled(tmp_path):
    result = _run_tracker(tmp_path, "init", "--demo-seed")

    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "DEMO ONLY" in combined

    db_path = tmp_path / "ai_compute_tracker.db"
    assert _seed_rows(db_path) > 0
    assert _production_rows(db_path) == 0


def test_reset_production_db_requires_confirm_and_preserves_demo_rows(tmp_path):
    demo = _run_tracker(tmp_path, "init", "--demo-seed")
    assert demo.returncode == 0, demo.stderr
    db_path = tmp_path / "ai_compute_tracker.db"
    _insert_production_gpu_row(db_path)

    refused = _run_tracker(tmp_path, "reset-production-db")
    assert refused.returncode != 0
    assert "RESET_REQUIRES_CONFIRMATION" in refused.stderr
    assert _production_rows(db_path) == 1
    assert _seed_rows(db_path) > 0

    confirmed = _run_tracker(tmp_path, "reset-production-db", "--confirm-real-data-reset")
    assert confirmed.returncode == 0, confirmed.stderr
    assert "PRODUCTION_DB_RESET" in confirmed.stdout
    assert _production_rows(db_path) == 0
    assert _seed_rows(db_path) > 0


def test_default_update_refuses_legacy_hardcoded_demo_collectors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    called = {"gpu": False, "ocpi": False}

    def forbidden_gpu():
        called["gpu"] = True
        raise AssertionError("hardcoded GPU demo collector must not run in default update")

    def forbidden_ocpi():
        called["ocpi"] = True
        raise AssertionError("hardcoded OCPI demo collector must not run in default update")

    monkeypatch.setattr(
        tracker_v2.GPUCollector,
        "fetch_gpu_price_from_providers",
        staticmethod(forbidden_gpu),
    )
    monkeypatch.setattr(
        tracker_v2.GPUCollector,
        "fetch_ocpi_public",
        staticmethod(forbidden_ocpi),
    )

    with pytest.raises(SystemExit) as exc:
        tracker_v2.cmd_update()

    assert exc.value.code != 0
    assert called == {"gpu": False, "ocpi": False}


def test_production_report_refuses_seed_only_database_without_investment_conclusion(tmp_path):
    demo = _run_tracker(tmp_path, "init", "--demo-seed")
    assert demo.returncode == 0, demo.stderr

    result = _run_tracker(tmp_path, "report", "--production")

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "FAIL_SEED_ONLY" in combined
    assert "OVERWEIGHT" not in combined
    assert "UNDERWEIGHT" not in combined
    assert "NEUTRAL: Maintain balanced AI exposure" not in combined
