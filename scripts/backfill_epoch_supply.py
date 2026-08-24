#!/usr/bin/env python3
"""Ingest Epoch AI chip sales timelines (CC BY 4.0-ish open dataset) as Capacity supply-side anchor.

按芯片型号×季度的出货量与 H100e 算力估计（含分位区间）。全历史数据集，每次整表刷新幂等覆盖。
定位：非阻塞信息源，为 Capacity 时钟提供供给侧物理部署节奏。
许可：Epoch AI 开放数据库，署名引用。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "epoch_chip_sales.json"
SOURCE_URL = "https://epoch.ai/data/ai_chip_sales_timelines_by_chip.csv"
USER_AGENT = "AIComputeEconomicsTracker/1.0"
ATTRIBUTION = "Data by Epoch AI (epoch.ai/data/ai-chip-sales), open database; attribution required."

KEEP_COLUMNS = (
    "Name",
    "Chip manufacturer",
    "Start date",
    "End date",
    "Incomplete",
    "Number of Units",
    "Compute estimate in H100e (median)",
    "Chip type",
)


def fetch_and_normalize() -> tuple[list[dict[str, Any]], bytes]:
    request = Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    rows: list[dict[str, Any]] = []
    for record in reader:
        row: dict[str, Any] = {}
        for col in KEEP_COLUMNS:
            value = (record.get(col) or "").strip()
            if not value:
                continue
            if col in ("Number of Units", "Compute estimate in H100e (median)"):
                try:
                    row[col] = float(value)
                except ValueError:
                    continue
            else:
                row[col] = value
        if row.get("Start date") and row.get("Number of Units") is not None:
            rows.append(row)
    rows.sort(key=lambda r: (r.get("Start date", ""), str(r.get("Name", ""))))
    return rows, raw


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        rows, raw = fetch_and_normalize()
        status = "fresh"
        message = ""
    except Exception as exc:
        rows, raw, status, message = [], b"", "failed", str(exc)

    payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": status,
        "publishable": True,
        "attribution": ATTRIBUTION,
        "sourceUrl": SOURCE_URL,
        "sourceSha256": "sha256:" + hashlib.sha256(raw).hexdigest() if raw else None,
        "rows": rows,
        "quality": [{"status": "failed", "message": message}] if message else [],
        "blocking": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)

    chips = sorted({str(r.get("Chip type")) for r in rows})
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": status,
        "publishable": True,
        "rowsTotal": len(rows),
        "chipTypes": len(chips),
        "failedSources": payload["quality"],
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
