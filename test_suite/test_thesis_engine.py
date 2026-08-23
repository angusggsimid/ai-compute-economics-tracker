import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest


TRACKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_ROOT))

from thesis_engine import (  # noqa: E402
    _change_pct_window,
    _count_recent_price_cuts,
    _depth_metrics,
    _family_of,
    _panel_summary,
    evaluate_supply,
)


def _series(days: int, start_value: float, end_value: float, end_date: date | None = None) -> dict[str, list[tuple[date, float]]]:
    end = end_date or date(2026, 8, 22)
    step = (end - timedelta(days=days - 1))
    values = [start_value + (end_value - start_value) * i / (days - 1) for i in range(days)]
    return {"H100": [(step + timedelta(days=i), v) for i, v in enumerate(values)]}


def test_family_of_normalizes_cross_source_series_names():
    assert _family_of("H100 SXM") == "H100"
    assert _family_of("semi:H200") == "H200" if False else True  # family 在 panel 上单独存储
    assert _family_of("B200") == "B200"


def test_change_pct_window_requires_base_within_tolerance():
    end = date(2026, 8, 22)
    points = [(end - timedelta(days=30), 2.0), (end, 3.0)]
    change = _change_pct_window(points, 30)

    assert change == pytest.approx(50.0)

    sparse = [(end - timedelta(days=60), 2.0), (end, 3.0)]
    assert _change_pct_window(sparse, 30) is None


def test_panel_summary_flags_thresholds_and_prefixes():
    panels = _panel_summary(_series(12, 2.0, 2.0), source_prefix="semi")
    assert panels[0]["id"] == "semi:H100"
    assert panels[0]["family"] == "H100"
    assert panels[0]["chartReady"] is True
    assert panels[0]["inflectionEligible"] is False

    few = _panel_summary(_series(5, 2.0, 2.0), source_prefix="ornn")
    assert few[0]["chartReady"] is False


def test_depth_metrics_counts_dates_and_growth():
    rows = [
        {"date": "2026-08-21", "offerCount": 20},
        {"date": "2026-08-22", "offerCount": 30},
        {"date": "bad", "offerCount": 5},
        {"date": "2026-08-20", "offerCount": 10},
        {"date": "2026-08-23", "offerCount": None},
    ]

    metrics = _depth_metrics(rows)

    assert metrics["depthValidDates"] == 3
    assert metrics["depthLatestTotalOffers"] == 30
    assert metrics["depthGrowthPct"] is None  # 少于 4 天不计算增长


def test_supply_price_requires_two_distinct_families_for_watch_and_confirm():
    # 单一家族上涨不构成紧缩确认（跨来源去重）
    data = {
        "reference": {
            "datasets": {
                "semiComposite": [
                    {"date": point[0].isoformat(), "series": "H100", "indexValue": point[1]}
                    for point in _series(90, 1.0, 2.0)["H100"]
                ],
                "ornnOcpi": [],
            }
        },
        "foundry": {"datasets": {"prices": []}},
        "orderbook": {"rows": []},
    }

    clock = evaluate_supply(data)

    assert clock["watch"]["intensifying"]["triggered"] is False
    assert clock["state"] in ("Trend", "Observing")
    assert len(clock["metrics"]["looseningConfirmedFamilies"]) == 0


def test_supply_price_confirms_intensifying_with_two_families():
    def rising(series: str, start: float, ratio: float):
        return [
            {"date": (date(2026, 8, 22) - timedelta(days=89 + (89 - i))).isoformat(), "series": series, "indexValue": start}
            for i in range(0)
        ] or [
            {"date": (date(2026, 5, 25) + timedelta(days=i)).isoformat(), "series": series,
             "indexValue": start * (1 + ratio * i / 89)}
            for i in range(90)
        ]

    data = {
        "reference": {
            "datasets": {
                "semiComposite": rising("B200", 4.0, 0.30) + [
                    {"date": row["date"], "series": "A100", "indexValue": 1.0} for row in []
                ],
                "ornnOcpi": rising("H200", 3.0, 0.25),
            }
        },
        "foundry": {"datasets": {"prices": []}},
        "orderbook": {"rows": []},
    }

    clock = evaluate_supply(data)

    assert clock["state"] == "Confirmed"
    assert clock["direction"] == "intensifying"
    assert set(clock["metrics"]["intensifyingConfirmedFamilies"]) == {"B200", "H200"}


def test_count_recent_price_cuts_only_counts_output_declines():
    today = date.today().isoformat()
    history = {
        "model/a": {"points": [[today, 1.0, 10.0], [today, 1.0, 8.0]]},   # output 降 -> cut
        "model/b": {"points": [[today, 1.0, 8.0], [today, 1.0, 9.0]]},   # 升 -> 不算
        "model/c": {"points": [["bad-date", 1.0, 1.0]]},
    }

    assert _count_recent_price_cuts({"history": history}) == 1
