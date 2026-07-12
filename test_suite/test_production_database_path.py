import os
import subprocess
import sys
from pathlib import Path

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from production_store import ProductionStore  # noqa: E402
from tracker_v2 import set_default_db_path  # noqa: E402


def test_cli_db_option_initializes_explicit_database_without_touching_legacy(tmp_path):
    production_db = tmp_path / "ai_compute_tracker_production.db"
    legacy_db = tmp_path / "ai_compute_tracker.db"

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "init", "--db", str(production_db)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert production_db.exists()
    assert not legacy_db.exists()
    assert f"Database ready at: {production_db}" in result.stdout


def test_db_env_var_routes_default_database_and_production_store(tmp_path, monkeypatch):
    production_db = tmp_path / "env_production.db"
    legacy_db = tmp_path / "ai_compute_tracker.db"
    env = {**os.environ, "AI_COMPUTE_TRACKER_DB": str(production_db)}

    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "init"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert production_db.exists()
    assert not legacy_db.exists()

    monkeypatch.setenv("AI_COMPUTE_TRACKER_DB", str(production_db))
    store = ProductionStore()
    assert store.database.db_path == str(production_db)


def test_cli_db_override_is_propagated_to_late_imported_production_store(tmp_path, monkeypatch):
    production_db = tmp_path / "late_imported_production.db"
    monkeypatch.delenv("AI_COMPUTE_TRACKER_DB", raising=False)

    set_default_db_path(str(production_db))
    try:
        assert os.environ["AI_COMPUTE_TRACKER_DB"] == str(production_db)
        store = ProductionStore()
        assert store.database.db_path == str(production_db)
    finally:
        set_default_db_path(None)
        monkeypatch.delenv("AI_COMPUTE_TRACKER_DB", raising=False)
