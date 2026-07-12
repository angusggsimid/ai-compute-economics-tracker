#!/usr/bin/env python3
"""Refresh public sources, preserve last-known-good data, and build the deployable site."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "tracker_data" / "deploy_refresh_status.json"
PUBLIC_INDEX = ROOT / "public" / "index.html"


def _run(name: str, command: list[str], required_output: Path) -> dict:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    status = {
        "source": name,
        "status": "fresh" if completed.returncode == 0 else "failed_using_last_good",
        "returnCode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
        "output": str(required_output.relative_to(ROOT)),
    }
    if completed.returncode and not required_output.exists():
        raise RuntimeError(f"{name} failed and has no last-known-good output: {completed.stderr}")
    return status


def main() -> int:
    python = sys.executable
    start_date = (date.today() - timedelta(days=370)).isoformat()
    jobs = [
        (
            "openrouter_usage",
            [python, "scripts/backfill_openrouter_cost_index.py", "--start-date", start_date, "--reuse-commits"],
            ROOT / "tracker_data" / "backfills" / "openrouter_cost_index.json",
        ),
        (
            "foundry_signals",
            [python, "scripts/backfill_foundry_signals.py"],
            ROOT / "tracker_data" / "backfills" / "foundry_signals_gpu_history.json",
        ),
        (
            "openrouter_active_prices",
            [python, "scripts/backfill_openrouter_active_prices.py"],
            ROOT / "tracker_data" / "backfills" / "openrouter_active_price_history.json",
        ),
        (
            "sec_capex",
            [python, "scripts/refresh_capex_history.py"],
            ROOT / "tracker_data" / "backfills" / "capex_official_history.json",
        ),
    ]
    results = [_run(*job) for job in jobs]
    build = subprocess.run(
        [python, "html_dashboard/build_time_series_dashboard.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if build.returncode:
        raise RuntimeError(build.stderr or build.stdout)

    PUBLIC_INDEX.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "html_dashboard" / "ai_compute_economics_monitor.html", PUBLIC_INDEX)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "generatedAt": generated_at,
        "status": "fresh" if all(row["status"] == "fresh" for row in results) else "degraded",
        "sources": results,
        "publicIndex": str(PUBLIC_INDEX.relative_to(ROOT)),
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
