"""GPU Finder 采集的累积正确性。

曾有一个静默数据丢失缺陷：写入用 "rows"、读取用 "daily"，
导致每天都把之前累积的行丢掉，稀缺度/广度图长期卡在"已积累 1/10 天"，
看起来像"刚接入"，实际是每天在丢数据。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backfill_gpufinder import (  # noqa: E402
    TRACK_DUE_DAYS,
    _availability_series,
    _due_tracks,
    _load_previous,
    _merge_daily,
    _merge_sources,
    _sweep_due,
)
from datetime import datetime, timezone  # noqa: E402


def _availability_payload(days: list[str]) -> dict:
    return {
        "providers": [
            {
                "providerName": "A",
                "counts": [{"cells": [{"date": d, "available": 1, "total": 4} for d in days]}],
            },
            {
                "providerName": "B",
                "counts": [{"cells": [{"date": d, "available": 2, "total": 4} for d in days]}],
            },
        ]
    }


def test_availability_series_keeps_all_days_in_rolling_window():
    """上游是 7 天滚动窗口：必须逐日全部落盘，只取最新一天会让历史永久丢失。"""
    days = [f"2026-09-{d:02d}" for d in range(22, 29)]
    series = _availability_series(_availability_payload(days))
    assert [s["date"] for s in series] == days, "滚动窗口内的历史日被丢弃"
    assert all(s["availabilityPct"] == 37.5 for s in series)
    assert all(s["availabilityByProvider"] for s in series)


def test_availability_series_skips_days_without_totals():
    payload = _availability_payload(["2026-09-27", "2026-09-28"])
    payload["providers"][0]["counts"][0]["cells"].append({"date": "2026-09-26", "available": 0, "total": 0})
    series = _availability_series(payload)
    assert [s["date"] for s in series] == ["2026-09-27", "2026-09-28"]


def test_load_previous_reads_rows_key(tmp_path):
    """写入键是 "rows"；读成 "daily" 会让累积归零。"""
    path = tmp_path / "gpufinder_market.json"
    path.write_text(json.dumps({
        "rows": [{"date": "2026-09-22", "gpu": "H100", "availabilityPct": 20.0}],
        "monthlyHistory": [{"month": "2026-08", "gpu": "H100"}],
        "fetchedAt": "2026-10-09T06:00:00Z",
        "refreshStatus": "fresh",
        "sources": {"/availability": {"url": "https://gpufinder.dev/api/v1/availability", "sha256": "sha256:abc"}},
    }), encoding="utf-8")
    daily, monthly, meta = _load_previous(path)
    assert len(daily) == 1 and daily[0]["date"] == "2026-09-22", "累积行没有被读回来"
    assert len(monthly) == 1
    assert meta["sources"]["/availability"]["url"].startswith("https://gpufinder.dev/")
    assert meta["fetchedAt"] == "2026-10-09T06:00:00Z"
    # 旧格式没有 lastSuccessAt：上一轮 refreshStatus 为 fresh 时退回 fetchedAt（避免首轮误判为"从未成功"）
    assert meta["lastSuccessAt"] == "2026-10-09T06:00:00Z"


def test_merge_sources_keeps_last_good_urls_on_total_failure():
    """断供时必须沿用上次成功抓取的 URL/sha：面板仍展示累积数据，来源链接不能消失
    （否则发布门会按"来源缺真实 URL"拦截）。"""
    prev = {"/availability": {"url": "https://gpufinder.dev/api/v1/availability?gpu=h100", "sha256": "sha256:abc"}}
    merged = _merge_sources(prev, {}, "2026-10-09T06:00:00Z")
    assert merged["/availability"]["url"].startswith("https://gpufinder.dev/")
    assert merged["/availability"]["sha256"] == "sha256:abc"
    assert merged["/availability"]["carriedFrom"] == "2026-10-09T06:00:00Z", "沿用条目必须标注实际抓取时间"


def test_merge_sources_fresh_entry_wins_and_drops_marker():
    prev = {"/snapshot": {"url": "https://old.example", "sha256": "sha256:old", "carriedFrom": "2026-10-01T00:00:00Z"}}
    fresh = {"/snapshot": {"url": "https://gpufinder.dev/api/v1/snapshot?gpu=h100", "sha256": "sha256:new"}}
    merged = _merge_sources(prev, fresh, "2026-10-09T06:00:00Z")
    assert merged["/snapshot"]["sha256"] == "sha256:new"
    assert "carriedFrom" not in merged["/snapshot"], "本轮成功抓取的条目不得带沿用标记"


def test_sweep_due_cadence_for_free_tier():
    """到期制周更：距上次成功 <6.5 天跳过（守住 60 次/月免费额度），≥6.5 天才放行。"""
    now = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)
    assert _sweep_due(None, now), "从未成功过必须视为到期"
    assert not _sweep_due("2026-10-14T06:00:00Z", now), "2 天前成功过不应再扫"
    assert _sweep_due("2026-10-09T06:00:00Z", now), "7 天前成功必须到期"
    assert _sweep_due("坏了的时间戳", now), "解析失败按到期处理，宁可多试一次"


def test_merge_daily_accumulates_across_runs_without_duplicates():
    """累积行为：历史日必须保留；同一份数据（含 7 天回补）重复合并不得产生重复行。"""
    day1 = [{"date": "2026-09-27", "gpu": "H100", "availabilityPct": 21.9}]
    day2 = [
        {"date": "2026-09-27", "gpu": "H100", "availabilityPct": 21.9, "availabilityByProvider": {"A": [1, 4]}},
        {"date": "2026-09-28", "gpu": "H100", "availabilityPct": 22.4, "providerCount": 23},
    ]
    merged = _merge_daily(day1, day2)
    assert len({r["date"] for r in merged}) == 2, "历史日被覆盖，累积失效"
    # 再次运行（同一份回补数据）不得产生重复
    again = _merge_daily(merged, day2)
    assert len(again) == len({(r["date"], r["gpu"]) for r in again}), "重复运行产生了重复行"
    # 本期行字段更全，应覆盖同键历史行
    assert len(again) == 2


def test_merge_daily_keeps_history_when_today_is_empty():
    """上游今天全失败（fresh 为空）时，历史绝不能丢。"""
    prev = [{"date": "2026-09-27", "gpu": "H100", "availabilityPct": 21.9}]
    assert _merge_daily(prev, []) == prev


def test_merge_daily_preserves_fields_against_window_rewrite():
    """滚动窗口回写的行只带可用率字段：字段级合并必须保住该日此前抓到的价格/家数字段。

    历史缺陷：整行覆盖让 gap/广度每个提交里都只剩最后一天（2026-10-11 复盘确认）。
    """
    prev = [{
        "date": "2026-10-09", "gpu": "H100",
        "cheapestListedPrice": 2.0, "cheapestAvailablePrice": 2.2,
        "listedAvailableGapPct": 10.0, "providerCount": 23,
        "availabilityPct": 13.0, "availabilityByProvider": {"A": [1, 4]},
    }]
    fresh = [{"date": "2026-10-09", "gpu": "H100", "availabilityPct": 13.5, "availabilityByProvider": {"A": [2, 4]}}]
    merged = _merge_daily(prev, fresh)[0]
    assert merged["listedAvailableGapPct"] == 10.0, "窗口回写把该日价差字段抹掉了"
    assert merged["providerCount"] == 23, "窗口回写把该日家数字段抹掉了"
    assert merged["availabilityPct"] == 13.5, "本轮抓到的可用率应覆盖旧值"


def test_merge_daily_explicit_none_wins_and_stale_gap_removed():
    """快照里"今日无在库报价"是事实：显式 None 必须覆盖旧值，且已不可计算的旧价差要清掉。"""
    prev = [{"date": "2026-10-09", "gpu": "B200", "cheapestListedPrice": 3.75,
             "cheapestAvailablePrice": 5.6, "listedAvailableGapPct": 49.3}]
    fresh = [{"date": "2026-10-09", "gpu": "B200", "cheapestListedPrice": 3.75,
              "cheapestListedProvider": "x", "cheapestAvailablePrice": None, "cheapestAvailableProvider": None}]
    merged = _merge_daily(prev, fresh)[0]
    assert merged["cheapestAvailablePrice"] is None
    assert "listedAvailableGapPct" not in merged, "旧价差在已不可计算时必须清除而不是沿用"


def test_due_tracks_per_track_cadence():
    """轨道各按自己的间隔到期：availability 6 天、snapshot 2.5 天、history/catalog 低频。"""
    now = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)
    cadence = {"availability": "2026-10-15T06:00:00Z", "snapshot": "2026-10-13T06:00:00Z",
               "history": "2026-09-16T06:00:00Z", "catalog": "2026-09-15T06:00:00Z"}
    due = _due_tracks(cadence, now)
    assert "availability" not in due, "1 天前采过可用率不应该再采"
    assert "snapshot" in due and "history" in due and "catalog" in due
    assert _due_tracks({}, now) == list(TRACK_DUE_DAYS), "没有任何节奏记录时全部视为到期"
    assert _due_tracks(cadence, now, force=True) == list(TRACK_DUE_DAYS)


def test_committed_artifact_shape_is_sane():
    """产物结构自检：键名与去重（不依赖"当天恰好多天"这种时点条件）。"""
    payload = json.loads((ROOT / "tracker_data" / "backfills" / "gpufinder_market.json").read_text("utf-8"))
    assert "rows" in payload, "写入键必须是 rows（曾因读成 daily 导致累积归零）"
    assert payload["rows"], "rows 不应为空"
    keys = [(r["date"], r["gpu"]) for r in payload["rows"]]
    assert len(keys) == len(set(keys)), "存在重复的 (date, gpu) 行"
    # 发布门要求每个展示面板都有真实来源 URL：断供期间元数据也必须保留，不得整体清空
    assert payload.get("sources"), "来源元数据为空：断供时必须沿用上次成功抓取的 URL/sha（会被发布门拦截）"
