import json
import subprocess
import sys
from pathlib import Path


TRACKER_V2 = Path(__file__).resolve().parents[1]
RUNNER = TRACKER_V2 / "scripts" / "run_phase3_daily.py"


def test_phase3_runner_dry_run_is_side_effect_free_and_explicit(tmp_path):
    db_path = tmp_path / "production.db"
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--dry-run", "--db", str(db_path)],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["mode"] == "dry_run"
    assert payload["db_path"] == str(db_path.resolve())
    assert "--production" in payload["command"]
    assert payload["command"][payload["command"].index("--only") + 1] == "market-facts"
    assert not db_path.exists()
