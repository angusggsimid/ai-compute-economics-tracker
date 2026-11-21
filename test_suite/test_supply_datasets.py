"""供给端三图的装配规则：一条公式、切换日只管一件事、缺口不许编数。

背景：2026-11-20 前用 GPU Finder（实例数加权 Σavailable/Σtotal），之后用 GrabGPU
（provider 在库占比）。为了让图是"一条线"，两段必须用同一条公式 —— 历史段用
`availabilityByProvider` 现算 provider 占比；而 2026-11-01→11-19 完全无观测，
只能由前端画虚线桥，绝不能在后端补点。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from build_time_series_dashboard import (  # noqa: E402
    _breadth_value,
    _provider_share,
    _supply_datasets,
)


def _gf_row(day, gpu="H100", by_provider=None, gap=None, raw_pct=99.9):
    return {
        "date": day,
        "gpu": gpu,
        "availabilityPct": raw_pct,
        "availabilityByProvider": by_provider or {},
        "listedAvailableGapPct": gap,
    }


def _stock_row(day, gpu="H100", pct=50.0, breadth=5, gap=1.0):
    return {
        "date": day,
        "gpu": gpu,
        "availabilityPct": pct,
        "breadthProviders": breadth,
        "listedAvailableGapPct": gap,
        "availabilityByProvider": {"a": [1, 1]},
    }


def test_provider_share_uses_known_providers_only():
    row = _gf_row(
        "2026-10-31",
        by_provider={"a": [0, 10], "b": [4, 4], "c": [0, 0], "d": [0, 6]},
    )
    # a/c 之外的已知 provider：a(缺货) b(有货) d(缺货) → 1/3；c 的 total=0 不算分母
    assert _provider_share(row) == 33.33
    assert _breadth_value(row) == 1

    assert _provider_share({"availabilityByProvider": None}) is None
    assert _provider_share({"availabilityByProvider": {"x": [0, 1]}}) == 0.0


def test_legacy_segment_is_converted_not_passed_through():
    """历史段必须换算成 provider 占比，而不是直接沿用实例数加权值。"""
    gf = {"rows": [_gf_row("2026-10-31", by_provider={"a": [1, 1], "b": [0, 1]}, raw_pct=88.8, gap=4.0)]}
    stock = {"rows": [_stock_row("2026-11-20", pct=53.33, breadth=8, gap=0.0)]}
    switch, scarcity, gap, breadth = _supply_datasets(stock, gf)
    assert switch == "2026-11-20"
    legacy = [r for r in scarcity if r["date"] == "2026-10-31"][0]
    assert legacy["value"] == 50.0, "1/2 在库 → 50%，不是原始 88.8"
    assert [r["value"] for r in breadth if r["date"] == "2026-10-31"] == [1]
    assert [r["value"] for r in gap if r["date"] == "2026-10-31"] == [4.0]


def test_no_rows_on_or_after_switch_date_from_legacy():
    """切换日之后旧源的行一律丢弃，避免两种 provider 池在同一天打架。"""
    gf = {
        "rows": [
            _gf_row("2026-11-19", by_provider={"a": [1, 1]}, gap=9.0),
            _gf_row("2026-11-20", by_provider={"a": [1, 1]}, gap=9.0),
        ]
    }
    stock = {"rows": [_stock_row("2026-11-20", pct=53.33, gap=0.0)]}
    _sw, scarcity, gap, _b = _supply_datasets(stock, gf)
    # 切换日之前的旧源行保留（11-19 → 100.0），切换日当天必须用新源（53.33，不是旧源的 100.0）
    assert {r["date"]: r["value"] for r in scarcity} == {"2026-11-19": 100.0, "2026-11-20": 53.33}
    assert {r["date"]: r["value"] for r in gap} == {"2026-11-19": 9.0, "2026-11-20": 0.0}


def test_gaps_are_not_fabricated():
    """缺口两端之间不许出现任何后端补出来的点。"""
    gf = {"rows": [_gf_row("2026-10-31", by_provider={"a": [1, 1]}, gap=1.0)]}
    stock = {"rows": [_stock_row("2026-11-20", pct=50.0, gap=2.0)]}
    _sw, scarcity, _gap, breadth = _supply_datasets(stock, gf)
    observed = {"2026-10-31", "2026-11-20"}
    assert {r["date"] for r in scarcity} == observed
    assert {r["date"] for r in breadth} == observed
    # 中间 20 天没有任何点：前端用 bridgeGaps 画虚线，而不是后端插值
    mid = [d for d in ("2026-11-01", "2026-11-10", "2026-11-19") if d in {r["date"] for r in scarcity}]
    assert mid == []


def test_frontier_filter_and_empty_inputs():
    gf = {"rows": [_gf_row("2026-10-31", gpu="RTX 4090", by_provider={"a": [1, 1]})]}
    _sw, scarcity, _gap, _b = _supply_datasets({"rows": []}, gf)
    assert scarcity == [], "只画 H100/H200/B200"

    sw, scarcity, gap, breadth = _supply_datasets({}, {})
    assert sw is None and scarcity == [] and gap == [] and breadth == []
