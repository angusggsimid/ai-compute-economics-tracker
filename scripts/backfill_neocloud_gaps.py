#!/usr/bin/env python3
"""从上游 gpu-rental-prices 的逐日快照回填价格历史缺口（真实数据，绝不插值）。

为什么需要：上游 `data/latest.json` 只给"当天"一份快照，我们的日更一旦漏跑（例如 2026-10-30→11-18
整条链路被 429 挡住），那些日子就永久缺行。但上游同时保留了 `data/snapshots/YYYY-MM-DD.json`——
每个交易日一份原始快照，同一份采集管线、同一套字段口径，可以直接回补。

边界（必须如实记录）：
- 只回补上游确实存在的日期；上游当天没出快照的日期**留空**，不插值、不借邻近日的值。
- 每份回填都在 `backfills` 里留 `date / url / sha256 / rows`，可逐条复核。
- 已存在的日期一律跳过，重复运行不改变结果。

定位：一次性修复 + 日常兜底（其余脚本仍按 latest.json 累积）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


try:  # 直接执行与作为包导入两种模式都要能用
    from backfill_neocloud_prices import ROW_FIELDS, SOURCE_URL, USER_AGENT, normalize as normalize_payload
except ImportError:  # pragma: no cover
    from scripts.backfill_neocloud_prices import (  # type: ignore
        ROW_FIELDS,
        SOURCE_URL,
        USER_AGENT,
        normalize as normalize_payload,
    )

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"
SNAPSHOT_BASE = "https://raw.githubusercontent.com/adriannutiu/gpu-rental-prices/main/data/snapshots"
# 仓库里最早的快照是 2026-08-16；比这更早的缺口上游没有原始文件，回填不了。
SNAPSHOT_FLOOR = date(2026, 8, 16)


def snapshot_url(day: str) -> str:
    return f"{SNAPSHOT_BASE}/{day}.json"


def missing_dates(present: set[str], start: date, end: date) -> list[str]:
    """[start, end] 内本地缺失、且上游可能存在的日期（升序）。"""
    out: list[str] = []
    cur = max(start, SNAPSHOT_FLOOR)
    while cur <= end:
        key = cur.isoformat()
        if key not in present:
            out.append(key)
        cur += timedelta(days=1)
    return out


def merge_rows(previous: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (date, provider, series, kind, price) 去重；已有日期保持原样，只加新日期。"""
    existing_dates = {str(r.get("date")) for r in previous}
    kept = [{field: row.get(field) for field in ROW_FIELDS} for row in previous]
    seen = {
        (r.get("date"), r.get("provider"), r.get("series"), r.get("vramGb"), r.get("kind"), r.get("usdPerGpuHour"))
        for r in kept
    }
    added: list[dict[str, Any]] = []
    for row in additions:
        if str(row.get("date")) in existing_dates:
            continue
        key = (row.get("date"), row.get("provider"), row.get("series"), row.get("vramGb"), row.get("kind"), row.get("usdPerGpuHour"))
        if key in seen:
            continue
        seen.add(key)
        added.append({field: row.get(field) for field in ROW_FIELDS})
    return sorted(kept + added, key=lambda row: (row["date"], row["provider"], row["series"], row["kind"]))


def _fetch(day: str) -> tuple[dict[str, Any] | None, str, str | None]:
    """返回 (payload, sha256, error)。404 视为"上游没有这一天"，不算失败。"""
    url = snapshot_url(day)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None, "", "HTTP 404（上游无此日快照）"
        return None, "", f"HTTP {exc.code}"
    except (URLError, TimeoutError) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"[:160]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, "", "上游快照不是合法 JSON"
    if not isinstance(payload.get("offers"), list) or not payload.get("date"):
        return None, "", "上游快照 schema 不符"
    if str(payload["date"])[:10] != day:
        return None, "", f"快照日期不符（{payload['date']} != {day}）"
    return payload, "sha256:" + hashlib.sha256(raw).hexdigest(), None


def main() -> int:
    stored = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    previous = stored.get("rows") or []
    present = {str(r["date"]) for r in previous}
    earliest = date.fromisoformat(min(present))
    today = datetime.now(timezone.utc).date()

    cached_unavailable = {
        str(item.get("date"))
        for item in (stored.get("backfillStatus") or {}).get("unavailable") or []
        if item.get("reason", "").startswith("HTTP 404")
    }
    retry_floor = (today - timedelta(days=2)).isoformat()
    wanted = [
        day
        for day in missing_dates(present, earliest, today)
        if not (day in cached_unavailable and day < retry_floor)
    ]
    additions: list[dict[str, Any]] = []
    filled: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for day in wanted:
        payload, sha, error = _fetch(day)
        if payload is None:
            unavailable.append({"date": day, "reason": error or "unknown"})
            continue
        rows = normalize_payload(payload)
        additions.extend(rows)
        filled.append({"date": day, "url": snapshot_url(day), "sha256": sha, "rows": len(rows)})

    merged = merge_rows(previous, additions)
    backfills = list(stored.get("backfills") or [])
    known = {(b.get("date"), b.get("sha256")) for b in backfills}
    for item in filled:
        if (item["date"], item["sha256"]) not in known:
            backfills.append(item)

    stored["rows"] = merged
    stored["backfills"] = sorted(backfills, key=lambda b: str(b.get("date")))
    known_unavailable = {
        str(item.get("date")): item
        for item in (stored.get("backfillStatus") or {}).get("unavailable") or []
    }
    for item in unavailable:
        known_unavailable[item["date"]] = item
    stored["backfillStatus"] = {
        "checkedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "requested": len(wanted),
        "filled": len(filled),
        "unavailable": [known_unavailable[day] for day in sorted(known_unavailable)],
        "rule": "只回补上游逐日快照真实存在的日期；上游缺失的日期保持空缺，不插值、不借用邻近日。",
        "snapshotBase": SNAPSHOT_BASE,
    }
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)

    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": "fresh" if filled else "current_for_frequency",
        "publishable": True,
        "rowsTotal": len(merged),
        "datesFilled": [item["date"] for item in filled],
        "datesUnavailable": [item["date"] for item in unavailable],
        "sourceUrl": SOURCE_URL,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
