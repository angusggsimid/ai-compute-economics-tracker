#!/usr/bin/env python3
"""Fetch and normalize Foundry Signals public GPU history endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "foundry_signals_gpu_history.json"
SNAPSHOT_DIR = ROOT / "tracker_snapshots" / "market_facts"
AVAILABILITY_URL = "https://www.foundrysignals.com/api/history?range=ALL"
PRICE_URL = "https://www.foundrysignals.com/api/price/history?range=ALL"
GPU_NAMES = {"H100 80GB": "H100", "H200 141GB": "H200", "B200": "B200"}


def _fetch(url: str, attempts: int = 3) -> tuple[dict[str, Any], bytes]:
    """瞬时 5xx/网络抖动重试：3 次指数退避（2s/4s/8s）。上游持续故障仍按失败处理。"""
    import time
    from urllib.error import HTTPError, URLError
    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            request = Request(url, headers={"User-Agent": "AIComputeEconomicsTracker/1.0"})
            with urlopen(request, timeout=30) as response:
                raw = response.read()
            payload = json.loads(raw)
            if not isinstance(payload.get("data"), dict):
                raise ValueError(f"Foundry Signals schema changed for {url}: missing data object")
            return payload, raw
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            continue
    raise last_error if last_error else RuntimeError("fetch failed")


def normalize(availability: dict[str, Any], prices: dict[str, Any]) -> dict[str, Any]:
    availability_rows = []
    for source_name, points in availability["data"].items():
        gpu = GPU_NAMES.get(source_name)
        if not gpu or not isinstance(points, list):
            continue
        for point in points:
            value = point.get("availability_pct")
            if not point.get("date") or not isinstance(value, (int, float)):
                continue
            availability_rows.append({
                "date": point["date"],
                "series": gpu,
                "value": float(value),
                "movingAverage30d": point.get("moving_avg_30d"),
            })

    price_rows = []
    for source_name, points in prices["data"].items():
        gpu = GPU_NAMES.get(source_name)
        if not gpu or not isinstance(points, list):
            continue
        for point in points:
            average = point.get("avg_price")
            provider_prices = {
                key: float(value)
                for key, value in (point.get("provider_prices") or {}).items()
                if isinstance(value, (int, float)) and value > 0
            }
            if not point.get("date") or not isinstance(average, (int, float)) or not provider_prices:
                continue
            price_rows.append({
                "date": point["date"],
                "series": gpu,
                "value": float(median(provider_prices.values())),
                "average": float(average),
                "low": point.get("min_price"),
                "high": point.get("max_price"),
                "providerCount": len(provider_prices),
                "providerPrices": provider_prices,
            })

    if not availability_rows or not price_rows:
        raise ValueError("Foundry Signals returned no usable availability or price rows")
    price_rows.sort(key=lambda row: (row["series"], row["date"]))
    by_gpu: dict[str, list[dict[str, Any]]] = {}
    for row in price_rows:
        by_gpu.setdefault(row["series"], []).append(row)
    for rows in by_gpu.values():
        for index, row in enumerate(rows):
            window = rows[max(0, index - 29):index + 1]
            row["movingAverage30d"] = sum(item["value"] for item in window) / len(window)

    return {
        "availability": sorted(availability_rows, key=lambda row: (row["date"], row["series"])),
        "prices": sorted(price_rows, key=lambda row: (row["date"], row["series"])),
    }


def main() -> int:
    availability, availability_raw = _fetch(AVAILABILITY_URL)
    prices, price_raw = _fetch(PRICE_URL)
    normalized = normalize(availability, prices)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = fetched_at.replace("-", "").replace(":", "").lower()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    availability_snapshot = SNAPSHOT_DIR / f"{stamp}-foundry-signals-availability.json"
    price_snapshot = SNAPSHOT_DIR / f"{stamp}-foundry-signals-price.json"
    availability_snapshot.write_bytes(availability_raw)
    price_snapshot.write_bytes(price_raw)

    payload = {
        "fetchedAt": fetched_at,
        "datasets": normalized,
        "sources": {
            "availability": {
                "url": AVAILABILITY_URL,
                "sha256": "sha256:" + hashlib.sha256(availability_raw).hexdigest(),
                "snapshotPath": str(availability_snapshot.relative_to(ROOT)),
            },
            "price": {
                "url": PRICE_URL,
                "sha256": "sha256:" + hashlib.sha256(price_raw).hexdigest(),
                "snapshotPath": str(price_snapshot.relative_to(ROOT)),
            },
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "availabilityRows": len(normalized["availability"]),
        "priceRows": len(normalized["prices"]),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
