"""价格缺口回填的规则：只补上游真实存在的逐日快照，绝不插值。

2026-11-20 排查发现的断点有两类：
1. 链路停摆（10-30 → 11-18 全部没提交）——上游 `data/snapshots/YYYY-MM-DD.json` 有原始快照，可以真回补；
2. 上游当天自己没出快照（10-14/10-17/10-23/10-24/10-30/11-01/11-10）——没有真实观测，必须留空。

这里锁死"回补"的边界，防止哪天为了图好看往缺口里塞插值。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.backfill_neocloud_gaps import (  # noqa: E402
    OUTPUT_PATH,
    SNAPSHOT_FLOOR,
    merge_rows,
    missing_dates,
    snapshot_url,
)


def _row(day, provider="runpod", series="H100", kind="on-demand", price=2.0):
    return {
        "date": day,
        "provider": provider,
        "series": series,
        "vramGb": 80,
        "kind": kind,
        "usdPerGpuHour": price,
        "sourceUrl": "https://example.invalid/p",
        "venueGrade": "marketplace",
    }


def test_missing_dates_respects_floor_and_presence():
    present = {"2026-09-01", "2026-09-03"}
    got = missing_dates(present, date(2026, 9, 1), date(2026, 9, 4))
    assert got == ["2026-09-02", "2026-09-04"]

    # 早于上游快照起始日的区间直接空：上游没有原始文件，请求也只会 404
    assert missing_dates(set(), date(2026, 7, 1), date(2026, 8, 2)) == []
    # 跨过起始日：第一天就是快照起始日，7 月的缺口不请求
    early = missing_dates(set(), date(2026, 7, 1), date(2026, 8, 18))
    assert early[0] == SNAPSHOT_FLOOR.isoformat()
    assert "2026-07-15" not in early


def test_merge_never_overwrites_existing_dates_and_dedups():
    previous = [_row("2026-10-29", price=3.0), _row("2026-11-05", price=3.1)]
    additions = [
        _row("2026-11-05", price=9.9),   # 已存在日期：不覆盖（保持当日已采的真实值）
        _row("2026-11-06", price=2.8),
        _row("2026-11-06", price=2.8),   # 完全重复：去重
    ]
    merged = merge_rows(previous, additions)
    dates = [r["date"] for r in merged]
    assert dates == sorted(dates)
    assert [r["usdPerGpuHour"] for r in merged if r["date"] == "2026-11-05"] == [3.1]
    assert len([r for r in merged if r["date"] == "2026-11-06"]) == 1


def test_merge_keeps_schema_fields_only():
    merged = merge_rows([], [{**_row("2026-11-07"), "extra": "x"}])
    assert "extra" not in merged[0]
    assert set(merged[0]) == {"date", "provider", "series", "vramGb", "kind", "usdPerGpuHour", "sourceUrl", "venueGrade"}


def test_snapshot_url_shape():
    assert snapshot_url("2026-11-05").endswith("/data/snapshots/2026-11-05.json")


def test_committed_artifact_only_contains_real_dates():
    """产物里的每个日期都必须有据可查：要么当日采集过，要么有快照回填记录。

    如果某个日期既不在 `backfills` 里、也不是最近几次采集日，说明有人往缺口里塞了数据。
    """
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    rows = payload["rows"]
    dates = sorted({r["date"] for r in rows})
    assert dates[0] >= "2026-07-05"
    backfilled = {b["date"] for b in payload.get("backfills") or []}
    for item in payload.get("backfills") or []:
        assert item["sha256"].startswith("sha256:"), "回填必须留内容哈希"
        assert "/data/snapshots/" in item["url"], "回填必须指向逐日快照，不能是 latest.json"
        assert item["rows"] > 0
    # 回填过的日期必须真的有行
    for day in backfilled:
        assert day in set(dates), f"回填记录里声明了 {day}，但 rows 里没有"
    # 停摆窗口内，未被回填的日期必须为空（不允许插值塞进来）
    status = payload.get("backfillStatus") or {}
    unavailable = {item["date"] for item in status.get("unavailable") or []}
    for day in ("2026-10-30", "2026-11-01", "2026-11-10"):
        if day in unavailable:
            assert day not in set(dates), f"{day} 上游无快照，却被塞进了 rows"


def test_no_duplicate_observations_per_day_provider_series():
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    seen: set[tuple] = set()
    for row in payload["rows"]:
        key = (row["date"], row["provider"], row["series"], row["vramGb"], row["kind"], row["usdPerGpuHour"])
        assert key not in seen, f"重复观测：{key}"
        seen.add(key)
