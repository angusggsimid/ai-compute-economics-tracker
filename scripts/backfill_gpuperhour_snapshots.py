#!/usr/bin/env python3
"""Backfill exact-config GPU rental facts from stored GPUPerHour JSON snapshots."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "ai_compute_tracker_production.db"
sys.path.insert(0, str(ROOT))

from data_sources.market_facts import (  # noqa: E402
    GPUPERHOUR_GPU_QUERIES,
    _gpuperhour_exact_config_facts,
    _parse_gpuperhour_available_offers,
    _safe_slug,
)
from production_store import ProductionStore  # noqa: E402
from tracker_v2 import Database  # noqa: E402


def _snapshot_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill GPUPerHour exact-config series")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve()
    with contextlib.redirect_stdout(io.StringIO()):
        db = Database(str(db_path))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        snapshots = con.execute(
            """
            SELECT * EXCLUDE (snapshot_rank)
            FROM (
                SELECT
                    date, source_id, source_url, snapshot_path, run_id, source_type,
                    collection_method, observed_at, fetched_at, raw_payload_hash,
                    confidence,
                    row_number() OVER (
                        PARTITION BY date, source_id
                        ORDER BY fetched_at DESC NULLS LAST
                    ) AS snapshot_rank
                FROM production_market_facts
                WHERE track='gpu_available_offer'
                  AND metric='available_offer_count'
                  AND source_id LIKE 'gpuperhour-offers-%'
            )
            WHERE snapshot_rank=1
            ORDER BY date, source_id
            """
        ).fetchall()
    finally:
        con.close()

    entity_by_slug = {_safe_slug(entity): entity for entity in GPUPERHOUR_GPU_QUERIES}
    facts = []
    errors = []
    processed = []
    for row in snapshots:
        (
            observed_date, source_id, source_url, snapshot_value, run_id, source_type,
            collection_method, observed_at, fetched_at, raw_payload_hash, confidence,
        ) = row
        entity = entity_by_slug.get(str(source_id).removeprefix("gpuperhour-offers-"))
        path = _snapshot_path(snapshot_value)
        if entity is None or not path.exists():
            errors.append({"source_id": source_id, "snapshot_path": str(path), "reason": "missing_mapping_or_file"})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _source_observed_at, _total, offers = _parse_gpuperhour_available_offers(
                payload, expected_entity=entity
            )
        except Exception as exc:
            errors.append({"source_id": source_id, "snapshot_path": str(path), "reason": str(exc)})
            continue
        provenance = {
            "run_id": str(run_id),
            "source_id": str(source_id),
            "source_url": str(source_url),
            "snapshot_path": str(snapshot_value),
            "source_type": str(source_type),
            "collection_method": str(collection_method),
            "observed_at": str(observed_at),
            "fetched_at": str(fetched_at),
            "raw_payload_hash": str(raw_payload_hash),
            "is_production_eligible": True,
            "confidence": float(confidence),
            "error_code": None,
        }
        snapshot_facts = _gpuperhour_exact_config_facts(
            offers,
            observed_date=str(observed_date),
            provenance=provenance,
        )
        facts.extend(snapshot_facts)
        processed.append({
            "date": str(observed_date),
            "source_id": source_id,
            "snapshot_path": str(snapshot_value),
            "facts": len(snapshot_facts),
        })

    inserted = 0
    if not args.dry_run and facts:
        inserted = ProductionStore(database=db).insert_market_facts(facts)
        with contextlib.redirect_stdout(io.StringIO()):
            Database(str(db_path))

    print(json.dumps({
        "mode": "dry_run" if args.dry_run else "insert",
        "db_path": str(db_path),
        "snapshots_selected": len(snapshots),
        "snapshots_processed": len(processed),
        "facts_prepared": len(facts),
        "facts_inserted": inserted,
        "errors": errors,
        "processed": processed,
    }, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
