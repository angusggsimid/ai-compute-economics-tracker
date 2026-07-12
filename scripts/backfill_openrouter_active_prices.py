#!/usr/bin/env python3
"""Fetch OpenRouter model aliases and OpenRouterList's change-point ledger."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "openrouter_active_price_history.json"
SNAPSHOT_DIR = ROOT / "tracker_snapshots" / "market_facts"
MODELS_URL = "https://openrouter.ai/api/v1/models"
HISTORY_URL = "https://raw.githubusercontent.com/jvrck/openrouterlist/main/data/history/prices.json"


def _fetch(url: str) -> tuple[dict[str, Any], bytes]:
    request = Request(url, headers={"User-Agent": "AIComputeEconomicsTracker/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
    return json.loads(raw), raw


def normalize(models_payload: dict[str, Any], history_payload: dict[str, Any]) -> dict[str, Any]:
    current_models = models_payload.get("data")
    history_models = history_payload.get("models")
    if not isinstance(current_models, list) or not isinstance(history_models, dict):
        raise ValueError("OpenRouter/OpenRouterList schema changed")
    if len(current_models) < 100 or len(history_models) < 100:
        raise ValueError("OpenRouter/OpenRouterList response is unexpectedly small")

    aliases = {}
    current = {}
    for model in current_models:
        model_id = model.get("id")
        if not model_id:
            continue
        aliases[model_id] = model_id
        if model.get("canonical_slug"):
            aliases[model["canonical_slug"]] = model_id
        pricing = model.get("pricing") or {}
        current[model_id] = {
            "name": model.get("name") or model_id,
            "canonicalSlug": model.get("canonical_slug"),
            "inputUsdPer1m": _per_million(pricing.get("prompt")),
            "outputUsdPer1m": _per_million(pricing.get("completion")),
        }

    cleaned_history = {}
    for model_id, record in history_models.items():
        points = []
        for point in record.get("points") or []:
            if not isinstance(point, list) or len(point) != 3 or not point[0]:
                continue
            points.append([point[0], point[1], point[2]])
        if not points:
            continue
        cleaned_history[model_id] = {
            "name": record.get("name") or model_id,
            "firstSeen": record.get("first_seen") or points[0][0],
            "lastSeen": record.get("last_seen") or points[-1][0],
            "presentNow": bool(record.get("present_now")),
            "points": sorted(points, key=lambda point: point[0]),
        }
    return {
        "asOf": history_payload.get("as_of"),
        "aliases": aliases,
        "currentModels": current,
        "history": cleaned_history,
    }


def _per_million(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if parsed < 0 else parsed * 1_000_000


def main() -> int:
    models_payload, models_raw = _fetch(MODELS_URL)
    history_payload, history_raw = _fetch(HISTORY_URL)
    normalized = normalize(models_payload, history_payload)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = fetched_at.replace("-", "").replace(":", "").lower()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    models_snapshot = SNAPSHOT_DIR / f"{stamp}-openrouter-models-active-prices.json"
    history_snapshot = SNAPSHOT_DIR / f"{stamp}-openrouterlist-price-history.json"
    models_snapshot.write_bytes(models_raw)
    history_snapshot.write_bytes(history_raw)
    payload = {
        "fetchedAt": fetched_at,
        "data": normalized,
        "sources": {
            "models": {
                "url": MODELS_URL,
                "sha256": "sha256:" + hashlib.sha256(models_raw).hexdigest(),
                "snapshotPath": str(models_snapshot.relative_to(ROOT)),
            },
            "history": {
                "url": HISTORY_URL,
                "sha256": "sha256:" + hashlib.sha256(history_raw).hexdigest(),
                "snapshotPath": str(history_snapshot.relative_to(ROOT)),
                "licenseCaveat": "Repository labels MIT, but its LICENSE retains placeholder copyright fields and has no separate data license.",
            },
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "aliases": len(normalized["aliases"]),
        "currentModels": len(normalized["currentModels"]),
        "historyModels": len(normalized["history"]),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
