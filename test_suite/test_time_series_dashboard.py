import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import pytest


TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2 / "html_dashboard"))

from build_time_series_dashboard import build_html, build_snapshot  # noqa: E402


def test_time_series_dashboard_uses_full_openrouter_history_without_synthetic_provider_zeroes():
    snapshot = build_snapshot()

    volume = snapshot["datasets"]["openrouterVolume"]
    composition = snapshot["datasets"]["openrouterComposition"]
    dates = sorted({row["date"] for row in volume})

    assert len(dates) >= 52
    assert len({row["date"] for row in composition}) >= 52
    assert date.fromisoformat(dates[-1]) + timedelta(days=6) < date.today()
    for observed_date in {row["date"] for row in composition}:
        rows = [row for row in composition if row["date"] == observed_date]
        assert len(rows) == 10
        assert len([row for row in rows if row["model"] == "Others"]) == 1
        assert sum(row["share"] for row in rows) == pytest.approx(100)


def test_sparse_snapshot_charts_are_not_exposed_as_time_series():
    snapshot = build_snapshot()

    assert "gpuOffers" not in snapshot["datasets"]
    assert "cloudPrice" not in snapshot["datasets"]
    assert len({row["date"] for row in snapshot["datasets"]["gpuPrice"]}) >= 200
    assert len({row["date"] for row in snapshot["datasets"]["gpuAvailability"]}) >= 35
    assert {row["series"] for row in snapshot["datasets"]["gpuPrice"]} == {"H100", "H200", "B200"}
    assert all(row.get("low") is not None and row.get("high") is not None for row in snapshot["datasets"]["gpuPrice"])


def test_foundry_price_panels_use_provider_medians_and_expose_composition_changes():
    snapshot = build_snapshot()
    prices = snapshot["datasets"]["gpuPrice"]

    assert all(row["value"] == pytest.approx(median(row["providerPrices"].values())) for row in prices)
    assert all(row["providerCount"] == len(row["providerPrices"]) for row in prices)
    assert snapshot["datasets"]["gpuPriceAnnotations"]["H100"][-1] == {
        "date": "2026-06-22",
        "label": "3→5",
    }
    assert {row["series"] for row in snapshot["datasets"]["gpuPremium"]} == {
        "H200 / H100",
        "B200 / H100",
    }


def test_availability_is_faceted_and_h200_is_explicitly_point_only():
    snapshot = build_snapshot()
    availability = snapshot["datasets"]["gpuAvailability"]
    assert len([row for row in availability if row["series"] == "H100"]) == 35
    assert len([row for row in availability if row["series"] == "B200"]) == 11
    assert len([row for row in availability if row["series"] == "H200"]) == 3
    html = build_html(snapshot)
    assert "gpu-availability-h200" in html
    assert "pointOnly:true" in html


def test_active_model_price_tiers_preserve_unknown_and_sum_to_total():
    snapshot = build_snapshot()
    tiers = snapshot["datasets"]["activePriceTiers"]
    dates = sorted({row["date"] for row in tiers})
    assert len(dates) >= 52
    for observed_date in dates:
        rows = [row for row in tiers if row["date"] == observed_date]
        assert {row["series"] for row in rows} == {"免费", "<$1", "$1–5", ">$5", "Others / 无法匹配"}
        assert sum(row["value"] for row in rows) == pytest.approx(100)
        assert next(row["value"] for row in rows if row["series"] == "Others / 无法匹配") > 0


def test_active_model_basket_is_usage_filtered_and_coverage_is_visible():
    snapshot = build_snapshot()
    active = snapshot["datasets"]["activeModels"]
    input_rows = snapshot["datasets"]["activeInputBasket"]
    output_rows = snapshot["datasets"]["activeOutputBasket"]

    assert 1 <= len(active) <= 12
    assert all("deepseek-r1" not in row["rankId"] for row in active)
    assert all(row["tokens"] > 0 and row["share"] > 0 for row in active)
    assert len({row["date"] for row in input_rows}) >= 52
    assert len({row["date"] for row in output_rows}) >= 52
    assert all(0 < row["coverage"] <= 100 for row in input_rows + output_rows)


def test_fixed_representative_token_price_section_is_removed():
    snapshot = build_snapshot()
    html = build_html(snapshot)

    assert "tokenInputPrice" not in snapshot["datasets"]
    assert "tokenOutputPrice" not in snapshot["datasets"]
    assert "代表模型 Output Token 牌价" not in html
    assert "代表模型 Input Token 牌价" not in html
    assert "Token价格" not in html
    assert "OpenRouter 活跃模型组合更替" in html
