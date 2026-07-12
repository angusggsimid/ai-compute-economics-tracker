#!/usr/bin/env python3
"""Maintain a small, versionable CAPEX history for the static dashboard."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_config import decision_universe_configs  # noqa: E402
from data_sources.sec_capex import (  # noqa: E402
    SecCompanyfactsClient,
    companyfacts_url,
    extract_capex_facts,
    select_latest_capex_fact,
)


DEFAULT_OUTPUT = ROOT / "tracker_data" / "backfills" / "capex_official_history.json"


def _key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("date") or ""),
        str(row.get("company") or ""),
        str(row.get("metric") or ""),
        str(row.get("period") or ""),
    )


def _seed_rows(db_path: Path) -> list[dict[str, Any]]:
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        result = con.execute(
            """
            WITH labeled AS (
              SELECT e.date, e.track,
                     CASE e.vendor WHEN 'ORCL' THEN 'Oracle' WHEN 'AMZN' THEN 'Amazon'
                          WHEN 'GOOGL' THEN 'Alphabet' WHEN 'META' THEN 'Meta'
                          WHEN 'MSFT' THEN 'Microsoft' ELSE e.vendor END AS company,
                     e.metric, ROUND(e.value, 3) AS metric_value, e.unit,
                     COALESCE(p.fiscal_period, e.dimension) AS period, e.source_url
              FROM event_observation e
              LEFT JOIN production_capex_actuals p
                ON e.track='cloud_capex_actual' AND e.vendor=p.company AND e.date=p.period_end
              WHERE e.track IN ('cloud_capex_actual','cloud_official_event','china_cloud_capex')
            )
            SELECT CAST(date AS VARCHAR) AS date, company,
                   REPLACE(metric, '_', ' ') AS metric, metric_value AS value,
                   unit, period, source_url
            FROM labeled ORDER BY date DESC, company
            """
        )
        columns = [column[0] for column in result.description]
        return [dict(zip(columns, values)) for values in result.fetchall()]
    finally:
        con.close()


def refresh(output: Path, seed_db: Optional[Path] = None) -> dict[str, Any]:
    previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"rows": []}
    rows = list(previous.get("rows") or [])
    if seed_db is not None:
        rows.extend(_seed_rows(seed_db))

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    client = SecCompanyfactsClient()
    quality = []
    sources = dict(previous.get("sources") or {})
    for config in decision_universe_configs():
        url = companyfacts_url(config.cik)
        try:
            payload = client.fetch_companyfacts(config)
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            selected = select_latest_capex_fact(extract_capex_facts(payload, config.capex_xbrl_tag))
            if selected is None:
                raise ValueError(f"No usable {config.capex_xbrl_tag} fact")
            rows.append({
                "date": selected.period_end,
                "company": config.company_name,
                "metric": "capex actual",
                "value": round(abs(selected.raw_value) / 1_000_000_000, 3),
                "unit": "USD_B",
                "period": selected.fiscal_period,
                "source_url": url,
            })
            sources[config.ticker] = {
                "url": url,
                "fetchedAt": fetched_at,
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "status": "fresh",
            }
        except Exception as exc:  # Keep the last verified row and expose the failure.
            quality.append({"source": config.ticker, "status": "failed", "message": str(exc)})
            sources[config.ticker] = {
                "url": url,
                "fetchedAt": fetched_at,
                "status": "failed",
                "message": str(exc),
            }

    deduplicated = {_key(row): row for row in rows if all(_key(row))}
    payload = {
        "fetchedAt": fetched_at,
        "rows": sorted(deduplicated.values(), key=lambda row: (row["date"], row["company"]), reverse=True),
        "sources": sources,
        "quality": quality,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed-db", type=Path)
    args = parser.parse_args()
    payload = refresh(args.output, args.seed_db)
    print(json.dumps({
        "output": str(args.output),
        "rows": len(payload["rows"]),
        "failedSources": len(payload["quality"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
