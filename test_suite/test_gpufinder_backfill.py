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

from scripts.backfill_gpufinder import _availability_series, _load_previous  # noqa: E402


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
    }), encoding="utf-8")
    daily, monthly = _load_previous(path)
    assert len(daily) == 1 and daily[0]["date"] == "2026-09-22", "累积行没有被读回来"
    assert len(monthly) == 1


def test_backfill_output_accumulates_and_has_no_duplicate_rows():
    """真实产物必须逐日累积，且 (date, gpu) 唯一。"""
    payload = json.loads((ROOT / "tracker_data" / "backfills" / "gpufinder_market.json").read_text("utf-8"))
    rows = payload["rows"]
    keys = [(r["date"], r["gpu"]) for r in rows]
    assert len(keys) == len(set(keys)), "存在重复的 (date, gpu) 行"
    assert len({r["date"] for r in rows}) >= 2, "累积日期数不足，疑似又被覆盖"


def test_backfill_keeps_availability_history_for_charts():
    """稀缺度图依赖 availabilityPct 的逐日历史，至少应有多日可用。"""
    payload = json.loads((ROOT / "tracker_data" / "backfills" / "gpufinder_market.json").read_text("utf-8"))
    days = {r["date"] for r in payload["rows"] if r.get("availabilityPct") is not None}
    assert len(days) >= 2, f"可用率历史仅 {len(days)} 天"
