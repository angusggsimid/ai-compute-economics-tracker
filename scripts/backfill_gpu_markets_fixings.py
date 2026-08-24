#!/usr/bin/env python3
"""Ingest gpu-markets daily fixings (spot / on-demand / reserved legs across 12 venues).

Phase 1 上游是静态 fixture（series-data.ts），我们按日抓取积累；待其 Phase 2 每日 JSON
上线后自动变为真正的日度定盘流。reserved 腿补充合约层（SemiAnalysis 仅 H100 单点）。
定位：非阻塞信息源。许可见仓库 LICENSE-DATA。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "gpu_markets_fixings.json"
SOURCE_URL = "https://raw.githubusercontent.com/gpu-markets/gpumarkets/main/src/lib/series-data.ts"
USER_AGENT = "AIComputeEconomicsTracker/1.0"
ROW_FIELDS = ("date", "seriesId", "chip", "tenor", "price", "obsCount", "venueCount", "delta30dPct")


def fetch_ts() -> bytes:
    request = Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def parse(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\{\s*id:\s*'([^']+)'.*?tenor:\s*'([^']+)'.*?price:\s*([\d.]+).*?obs:\s*(\d+),\s*venueCount:\s*'([^']+)'(?:.*?delta30d:\s*(-?[\d.]+))?",
        re.S,
    )
    chip_by_id: dict[str, str] = {}
    for m in re.finditer(r"id:\s*'([^']+)'.*?chipName:\s*'([^']+)'", text, re.S):
        chip_by_id[m.group(1)] = m.group(2)
    for match in pattern.finditer(text):
        series_id, tenor, price, obs, venues = match.group(1), match.group(2), float(match.group(3)), int(match.group(4)), match.group(5)
        delta = match.group(6)
        rows.append({
            "seriesId": series_id,
            "chip": chip_by_id.get(series_id, ""),
            "tenor": tenor,
            "price": round(price, 4),
            "obsCount": obs,
            "venueCount": venues,
            "delta30dPct": float(delta) if delta is not None else None,
        })
    if not rows:
        raise ValueError("gpu-markets series-data.ts 解析失败：上游结构可能已变更")
    return sorted(rows, key=lambda r: r["seriesId"])


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    date_iso = fetched_at[:10]
    quality: list[dict[str, str]] = []
    fresh_rows: list[dict[str, Any]] = []
    raw = b""
    message = ""
    try:
        raw = fetch_ts()
        parsed = parse(raw.decode("utf-8"))
        fresh_rows = [{"date": date_iso, **{k: r.get(k) for k in ROW_FIELDS if k != "date"}} for r in parsed]
    except Exception as exc:
        quality.append({"source": "gpu_markets", "status": "failed", "message": str(exc)})

    previous: list[dict[str, Any]] = []
    if OUTPUT_PATH.exists():
        try:
            stored = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            previous = [r for r in stored.get("rows", []) if r.get("date") != date_iso]
        except (json.JSONDecodeError, ValueError) as exc:
            raise SystemExit(f"gpu_markets_fixings.json 缓存损坏（{exc}）；拒绝覆盖累积历史。")

    merged = sorted(
        previous + fresh_rows,
        key=lambda r: (r["date"], r["seriesId"]),
    )

    payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": "fresh" if fresh_rows else "failed",
        "publishable": True,
        "rowSchema": list(ROW_FIELDS),
        "rows": merged,
        "sources": {
            "gpu_markets": {
                "url": SOURCE_URL,
                "fetchedAt": fetched_at,
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest() if raw else None,
                "license": "gpu-markets 仓库 LICENSE-DATA；上游 Phase 2 将改为每日 JSON",
                "status": "fresh" if fresh_rows else "failed",
                "message": message,
            }
        },
        "quality": quality,
        "blocking": False,
        "notes": ["Phase 1 上游为静态 fixture：同日重复抓取幂等，跨日自然积累；上游升级后无需改动本脚本。"],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": payload["refreshStatus"],
        "publishable": True,
        "todayRows": len(fresh_rows),
        "rowsTotal": len(merged),
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
