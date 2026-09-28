import json
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import pytest


TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2 / "html_dashboard"))
sys.path.insert(0, str(TRACKER_V2))

from build_time_series_dashboard import COST_INDEX_PATH, build_html, build_snapshot  # noqa: E402
from week_quality import complete_week_count  # noqa: E402


def test_time_series_dashboard_uses_full_openrouter_history_without_synthetic_provider_zeroes():
    snapshot = build_snapshot()

    volume = snapshot["datasets"]["openrouterVolume"]
    composition = snapshot["datasets"]["openrouterComposition"]
    dates = sorted({row["date"] for row in volume})

    # 图上只允许出现完整周：断言"等于完整周数"而不是硬编码 52，这样数据每周增长时依然成立。
    # 注意：残周只在它还落在 370 天滚动窗口内时存在——窗口一旦滚过它，底表首周就是完整周、
    # volumePartialWeekDropped 应为 None。因此这里必须按状态分支，不能假设残周永远存在。
    # （曾因硬编码"残周一定是第一周"而在 2026-09-28 窗口滚动后误报失败。）
    raw_weeks = json.loads(COST_INDEX_PATH.read_text(encoding="utf-8"))["weeks"]
    expected = complete_week_count(raw_weeks)
    assert len(dates) == expected
    assert len({row["date"] for row in composition}) == expected
    dropped = snapshot["meta"]["volumePartialWeekDropped"]
    if dropped is None:
        # 无残周可剔：图上首周必须就是底表首周
        assert dates[0] == str(raw_weeks[0]["date"])
    else:
        # 有残周：必须被剔除，且剔除的正是底表首周
        assert dropped == str(raw_weeks[0]["date"])
        assert dropped not in dates
    assert date.fromisoformat(dates[-1]) + timedelta(days=6) < date.today()
    for observed_date in {row["date"] for row in composition}:
        rows = [row for row in composition if row["date"] == observed_date]
        # 每周 = Top-N 具名 + 1 个 Others；N 由数据决定，不写死（榜单档数一变就会误报）
        assert len([row for row in rows if row["model"] == "Others"]) == 1
        assert len(rows) - 1 >= 1
        assert sum(row["share"] for row in rows) == pytest.approx(100)


def test_sparse_snapshot_charts_are_not_exposed_as_time_series():
    snapshot = build_snapshot()

    assert "gpuOffers" not in snapshot["datasets"]
    assert "cloudPrice" not in snapshot["datasets"]
    # 2026-09-27 起 gpuPrice 来自 neocloud 34 家数据集（历史自 2026-07-05 起向前积累）
    assert len({row["date"] for row in snapshot["datasets"]["gpuPrice"]}) >= 40
    assert {row["series"] for row in snapshot["datasets"]["gpuPrice"]} == {"H100", "H200", "B200"}
    assert all(row.get("low") is not None and row.get("high") is not None for row in snapshot["datasets"]["gpuPrice"])


def test_price_panels_use_provider_medians_and_expose_composition_changes():
    snapshot = build_snapshot()
    prices = snapshot["datasets"]["gpuPrice"]

    # 跨供应商中位：每家一票，value == median(逐供应商中位)
    assert all(row["value"] == pytest.approx(median(row["providerPrices"].values()), abs=1e-4) for row in prices)
    assert all(row["providerCount"] == len(row["providerPrices"]) for row in prices)
    # 构成变化标注结构自洽：每个标注都与 providerCount 变动对应
    for gpu, changes in snapshot["datasets"]["gpuPriceAnnotations"].items():
        rows = {r["date"]: r["providerCount"] for r in prices if r["series"] == gpu}
        for change in changes:
            assert "→" in change["label"] and change["date"] in rows
    assert {row["series"] for row in snapshot["datasets"]["gpuPremium"]} == {
        "H200 / H100",
        "B200 / H100",
    }


def test_supply_tension_panels_accumulate_and_stay_point_only_until_threshold():
    snapshot = build_snapshot()
    for name in ("scarcity", "listedGap", "breadth"):
        rows = snapshot["datasets"][name]
        assert {row["series"] for row in rows} == {"H100", "H200", "B200"}, name
    html = build_html(snapshot)
    assert "scarcity-chart" in html and "gap-chart" in html and "breadth-chart" in html
    # GPU Finder 为 7 天滚动窗口：少于 10 个有效日前只画观测点
    assert "pointOnly:_sd<10" in html
    assert "gpu-availability" not in html


def test_active_model_price_tiers_preserve_unknown_and_sum_to_total():
    snapshot = build_snapshot()
    tiers = snapshot["datasets"]["activePriceTiers"]
    dates = sorted({row["date"] for row in tiers})
    assert len(dates) >= 51
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
    assert len({row["date"] for row in input_rows}) >= 51
    assert len({row["date"] for row in output_rows}) >= 51
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
