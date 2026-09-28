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
    _availability_series,
    _load_previous,
    _merge_daily,
)


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


def test_committed_artifact_shape_is_sane():
    """产物结构自检：键名与去重（不依赖"当天恰好多天"这种时点条件）。"""
    payload = json.loads((ROOT / "tracker_data" / "backfills" / "gpufinder_market.json").read_text("utf-8"))
    assert "rows" in payload, "写入键必须是 rows（曾因读成 daily 导致累积归零）"
    assert payload["rows"], "rows 不应为空"
    keys = [(r["date"], r["gpu"]) for r in payload["rows"]]
    assert len(keys) == len(set(keys)), "存在重复的 (date, gpu) 行"
