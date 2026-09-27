#!/usr/bin/env python3
"""回填 neocloud 数据集的历史缺口：从 adriannutiu/gpu-rental-prices 的 git 历史抓取被滚动窗口删除的每日快照。

该仓库每日提交 data/snapshots/YYYY-MM-DD.json，但工作区只保留近期窗口；
被删除的旧快照仍存在于 git 历史中，可通过 GitHub API 按文件路径定位历史提交并取回。
一次性/按需运行：只填补本地数据集缺失的日期，不覆盖已有数据。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backfill_neocloud_prices import ROW_FIELDS, normalize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"
REPO = "adriannutiu/gpu-rental-prices"
SNAPSHOT_TMPL = "data/snapshots/{}.json"


def _gh_json(args: list[str]):
    proc = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=60)
    if proc.returncode:
        raise RuntimeError(f"gh api failed: {proc.stderr[:200]}")
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def _fetch_snapshot(day: str) -> dict | None:
    commits = _gh_json([f"repos/{REPO}/commits?path={SNAPSHOT_TMPL.format(day)}&per_page=1"])
    if not commits:
        return None
    sha = commits[0]["sha"]
    content = _gh_json([f"repos/{REPO}/contents/{SNAPSHOT_TMPL.format(day)}?ref={sha}"])
    if not content or "content" not in content:
        return None
    import base64
    raw = base64.b64decode(content["content"]).decode("utf-8")
    return json.loads(raw)


def main() -> int:
    stored = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    rows = stored["rows"]
    have = {r["date"] for r in rows}
    first, last = min(have), max(have)
    cursor = date.fromisoformat(first)
    end = date.fromisoformat(last)
    missing = []
    while cursor <= end:
        day = cursor.isoformat()
        if day not in have:
            missing.append(day)
        cursor += timedelta(days=1)
    if not missing:
        print(json.dumps({"status": "no_gap", "range": [first, last]}))
        return 0

    added_rows = 0
    filled_days = 0
    failed = []
    for day in missing:
        try:
            payload = _fetch_snapshot(day)
        except Exception as exc:
            failed.append({"date": day, "error": str(exc)[:120]})
            continue
        if not payload:
            failed.append({"date": day, "error": "snapshot not found in git history"})
            continue
        offers = payload.get("offers") if isinstance(payload, dict) else None
        if not offers or not payload.get("date"):
            failed.append({"date": day, "error": "unexpected schema"})
            continue
        normalized = normalize(payload)
        rows.extend(normalized)
        added_rows += len(normalized)
        filled_days += 1

    rows.sort(key=lambda r: (r["date"], r["provider"], r["series"], r["kind"]))
    stored["rows"] = rows
    stored["attribution"] = stored.get("attribution", "") + "；缺口回填：GitHub git 历史快照"
    tmp = OUTPUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    print(json.dumps({
        "status": "filled",
        "missingDays": len(missing),
        "filledDays": filled_days,
        "addedRows": added_rows,
        "failed": failed[:5],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
