#!/usr/bin/env python3
"""Run the Phase 3 daily collection closure with locking and SLA checks."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "ai_compute_tracker_production.db"
RUN_DIR = ROOT / "tracker_data" / "phase3_runs"
LOCK_DIR = ROOT / "tracker_data" / "phase3_daily.lock"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _update_command(db_path: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tracker_v2.py"),
        "update",
        "--production",
        "--only",
        "market-facts",
        "--db",
        str(db_path),
    ]


def _health_snapshot(db_path: Path) -> dict:
    sys.path.insert(0, str(ROOT))
    from tracker_v2 import Database

    with contextlib.redirect_stdout(io.StringIO()):
        Database(str(db_path))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        source_rows = con.execute(
            """
            SELECT policy_id, criticality, status, reason_code, age_hours,
                   latest_fetched_at, matched_source_ids, observation_rows
            FROM source_freshness
            ORDER BY criticality, policy_id
            """
        ).fetchdf().to_dict(orient="records")
        exact_series = con.execute(
            """
            SELECT count(*)
            FROM series_definition
            WHERE evidence_class='matched_venue_series'
              AND metric='price_per_gpu_hour'
            """
        ).fetchone()[0]
        exact_chart_ready = con.execute(
            """
            SELECT count(*)
            FROM series_quality
            WHERE evidence_class='matched_venue_series'
              AND eligible_for_chart=TRUE
            """
        ).fetchone()[0]
        panel_members = con.execute("SELECT count(*) FROM matched_panel_member").fetchone()[0]
        latest_pipeline = con.execute(
            """
            SELECT pipeline_name, status, completed_at, rows_loaded, message
            FROM pipeline_health_latest
            WHERE pipeline_name='market-facts'
            """
        ).fetchone()
    finally:
        con.close()

    unhealthy_core = [
        row for row in source_rows
        if row["criticality"] == "core" and row["status"] != "fresh"
    ]
    return {
        "sources": source_rows,
        "unhealthy_core_sources": unhealthy_core,
        "exact_config_series": int(exact_series),
        "exact_config_chart_ready": int(exact_chart_ready),
        "matched_panel_members": int(panel_members),
        "latest_market_facts_pipeline": list(latest_pipeline) if latest_pipeline else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 daily collector and SLA closure")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve()
    command = _update_command(db_path)
    if args.dry_run:
        print(json.dumps({
            "mode": "dry_run",
            "db_path": str(db_path),
            "working_directory": str(ROOT),
            "command": command,
            "lock_path": str(LOCK_DIR),
            "run_log_directory": str(RUN_DIR),
        }, ensure_ascii=False, indent=2))
        return 0

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        LOCK_DIR.mkdir(parents=False)
    except FileExistsError:
        print(f"PHASE3_RUN_LOCKED: another run owns {LOCK_DIR}", file=sys.stderr)
        return 2

    started_at = _utc_now()
    update_result = None
    try:
        if not args.audit_only:
            update_result = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=1200,
            )
        health = _health_snapshot(db_path)
        sys.path.insert(0, str(ROOT))
        from thesis_state import write_state_report

        state_paths = write_state_report(db_path, ROOT / "tracker_data" / "thesis_states")
        state_payload = json.loads(Path(state_paths["latest_json"]).read_text(encoding="utf-8"))
        state_summary = {
            clock["clock_id"]: clock["state"] for clock in state_payload["clocks"]
        }
        update_ok = args.audit_only or (update_result is not None and update_result.returncode == 0)
        status = "SUCCESS" if update_ok and not health["unhealthy_core_sources"] else "FAILED"
        completed_at = _utc_now()
        payload = {
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "db_path": str(db_path),
            "audit_only": args.audit_only,
            "update_returncode": None if update_result is None else update_result.returncode,
            "update_stdout": "" if update_result is None else update_result.stdout[-12000:],
            "update_stderr": "" if update_result is None else update_result.stderr[-12000:],
            "health": health,
            "thesis_states": state_summary,
            "thesis_state_paths": state_paths,
            "state_transitions": state_payload.get("transitions", []),
        }
        stamp = completed_at.replace(":", "").replace("-", "")
        log_path = RUN_DIR / f"{stamp}-phase3-daily.json"
        log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({
            "status": status,
            "log_path": str(log_path),
            "exact_config_series": health["exact_config_series"],
            "exact_config_chart_ready": health["exact_config_chart_ready"],
            "matched_panel_members": health["matched_panel_members"],
            "unhealthy_core_sources": [row["policy_id"] for row in health["unhealthy_core_sources"]],
            "thesis_states": state_summary,
            "state_transitions": state_payload.get("transitions", []),
        }, ensure_ascii=False, indent=2))
        return 0 if status == "SUCCESS" else 1
    except subprocess.TimeoutExpired as exc:
        print(f"PHASE3_RUN_TIMEOUT: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(LOCK_DIR, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
