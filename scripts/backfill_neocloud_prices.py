#!/usr/bin/env python3
"""Ingest the adriannutiu/gpu-rental-prices open dataset (CC BY 4.0) into a versionable daily history.

22 家 neocloud/云供应商的日度验证挂牌价（逐条 offer，带 source_url 与抓取时间戳），
作为 matched-panel 面板成员池的广度原料。append-only 上游快照 + 我们本地按日累积。
定位：非阻塞信息源；CC BY 4.0 要求署名 gpurentalprices.com。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"
SOURCE_URL = "https://raw.githubusercontent.com/adriannutiu/gpu-rental-prices/main/data/latest.json"
ATTRIBUTION = "Data © gpu-rentalprices.com (adriannutiu/gpu-rental-prices), CC BY 4.0"
USER_AGENT = "AIComputeEconomicsTracker/1.0"

ROW_FIELDS = (
    "date",
    "provider",
    "series",
    "vramGb",
    "kind",
    "usdPerGpuHour",
    "sourceUrl",
)


def _normalize_series(value: Any) -> str:
    text = str(value or "").lower().replace("_", " ").replace("-", " ")
    checks = [
        ("rtx 5090", "RTX 5090"),
        ("rtx 4090", "RTX 4090"),
        ("pro 6000", "RTX PRO 6000"),
        ("mi300x", "MI300X"),
        ("mi325", "MI325X"),
        ("gh200", "GH200"),
        ("b300", "B300"),
        ("b200", "B200"),
        ("h200", "H200"),
        ("h100", "H100"),
        ("a100", "A100"),
        ("l40s", "L40S"),
    ]
    for needle, family in checks:
        if needle in text:
            return family
    return str(value or "unknown")


def _fetch_offers() -> tuple[dict[str, Any], bytes]:
    request = Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    payload = json.loads(raw)
    if not isinstance(payload.get("offers"), list) or not payload.get("date"):
        raise ValueError("gpu-rental-prices latest.json schema changed")
    return payload, raw


def normalize(payload: dict[str, Any]) -> list[dict[str, Any]]:
    date_iso = str(payload["date"])[:10]
    rows: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for offer in payload["offers"]:
        try:
            price = float(offer.get("usd_hr"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        row = {
            "date": date_iso,
            "provider": str(offer.get("provider") or "unknown").strip().lower(),
            "series": _normalize_series(offer.get("gpu")),
            "vramGb": offer.get("vram_gb"),
            "kind": str(offer.get("kind") or "unknown").strip().lower(),
            "usdPerGpuHour": round(price, 6),
            "sourceUrl": str(offer.get("source_url") or SOURCE_URL),
        }
        key = (row["date"], row["provider"], row["series"], row["vramGb"], row["kind"], row["usdPerGpuHour"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    if not rows:
        raise ValueError("gpu-rental-prices returned no usable offers")
    return sorted(rows, key=lambda row: (row["provider"], row["series"], row["kind"], row["usdPerGpuHour"]))


def _load_previous(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["rows"]
        if not isinstance(rows, list):
            raise ValueError("rows is not a list")
        for row in rows:
            if not all(row.get(field) for field in ("date", "provider", "series")):
                raise ValueError(f"malformed row: {row}")
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"neocloud_provider_price_history.json 缓存损坏或 schema 不符（{exc}）；拒绝静默覆盖累积历史。"
        )
    return rows


def _merge(previous_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]], date_iso: str) -> list[dict[str, Any]]:
    """当天的旧行整体替换为最新一轮，其余日期保留。"""
    kept = [
        {field: row.get(field) for field in ROW_FIELDS}
        for row in previous_rows
        if row.get("date") != date_iso
    ]
    return sorted(kept + new_rows, key=lambda row: (row["date"], row["provider"], row["series"], row["kind"]))


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload, raw = _fetch_offers()
    fresh_rows = normalize(payload)
    date_iso = fresh_rows[0]["date"]

    previous_rows = _load_previous(OUTPUT_PATH)
    merged = _merge(previous_rows, fresh_rows, date_iso)

    output_payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": "fresh",
        "publishable": True,
        "rowSchema": list(ROW_FIELDS),
        "attribution": ATTRIBUTION,
        "sourceUrl": SOURCE_URL,
        "sourceSha256": None,
        "rows": merged,
        "quality": [],
    }
    import hashlib

    output_payload["sourceSha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)

    providers = sorted({row["provider"] for row in fresh_rows})
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": "fresh",
        "publishable": True,
        "date": date_iso,
        "todayRows": len(fresh_rows),
        "providers": len(providers),
        "rowsTotal": len(merged),
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
