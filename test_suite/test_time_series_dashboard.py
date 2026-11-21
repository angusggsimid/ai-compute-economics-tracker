import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import pytest


TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2 / "html_dashboard"))
sys.path.insert(0, str(TRACKER_V2))

from build_time_series_dashboard import COST_INDEX_PATH, build_html, build_snapshot, _executive_summary, _guidance_moves  # noqa: E402
from thesis_engine import generate_executive_summary  # noqa: E402
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
    # 2026-11-21 起供给端有"历史段 + 新段"可读，门槛从 10 天降到 4 天：不再整块退化成 KPI 卡
    assert "pointOnly:_sd<4" in html
    assert "pointOnly:_gd<4" in html
    # 缺口只画虚线桥，后端不补点
    assert html.count("bridgeGaps:true") >= 4
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


def test_executive_summary_contract():
    snapshot = build_snapshot()
    summary = snapshot.get("meta", {}).get("executiveSummary")
    assert summary is not None
    assert summary.get("macroStance")
    assert len(summary.get("takeaways") or []) == 4
    for item in summary["takeaways"]:
        assert item["clock"] in ("Supply Price", "Capacity", "Demand", "Commitment")
        assert len(item["text"]) >= 10
    html = build_html(snapshot)
    assert 'id="executive-summary"' in html
    capacity = next(item for item in summary["takeaways"] if item["clock"] == "Capacity")
    gap = next(row["value"] for row in reversed(snapshot["datasets"]["listedGap"]) if row["series"] == "H100")
    gap_date = max(row["date"] for row in snapshot["datasets"]["listedGap"] if row["series"] == "H100")
    assert f"{gap:.1f}%" in capacity["text"]
    assert gap_date in capacity["text"], "虚低度必须带快照日期"
    assert "当天快照" not in capacity["text"]
    demand = next(item for item in summary["takeaways"] if item["clock"] == "Demand")
    token_date = max(row["date"] for row in snapshot["datasets"]["openrouterVolume"] if row["series"] == "Weekly tokens")
    assert token_date in demand["text"], "周 token 必须带完整周日期"
    assert "同为上修" not in summary["coreNarrative"]
    # 下移公司必须写进承诺条；从同一份底表推导，避免数据更新后测试变成硬编码。
    downs = [
        item["company"]
        for item in snapshot["meta"].get("capexGuidance") or []
        if isinstance(item.get("prevLow"), (int, float))
        and isinstance(item.get("low"), (int, float))
        and item["low"] < item["prevLow"]
    ]
    commit_text = next(item["text"] for item in summary["takeaways"] if item["clock"] == "Commitment")
    for company in downs:
        assert company in commit_text
    assert "不得概括" not in commit_text


def test_executive_summary_refuses_to_invent_clocks():
    summary = generate_executive_summary([])
    assert "未运行" in summary["macroStance"]
    assert len(summary["takeaways"]) == 4
    assert all(item["badge"] == "未运行" for item in summary["takeaways"])
    assert "Observing" not in json.dumps(summary, ensure_ascii=False)
    partial = generate_executive_summary([{"clock_id": "supply_price", "state": "Trend", "direction": None}])
    assert "缺少时钟" in partial["macroStance"]
    assert "Observing" not in json.dumps(partial, ensure_ascii=False)


def test_summary_does_not_claim_simultaneous_upgrade_when_only_cuts():
    clocks = [
        {"clock_id": "supply_price", "state": "Confirmed", "direction": "intensifying", "metrics": {}},
        {"clock_id": "capacity", "state": "Trend", "metrics": {}},
        {"clock_id": "demand_unit_economics", "state": "Observing", "metrics": {}, "blockers": []},
        {"clock_id": "commitment_monetization", "state": "Inflection Watch", "direction": "intensifying", "metrics": {}},
    ]
    summary = generate_executive_summary(clocks, {"guidanceUp": [], "guidanceDown": ["Microsoft"]})
    assert "同时" not in summary["coreNarrative"]
    assert "下移" in summary["coreNarrative"]


def test_executive_summary_handles_malformed_thesis_file(monkeypatch, tmp_path):
    path = tmp_path / "latest-thesis-state.json"
    monkeypatch.setattr("build_time_series_dashboard.THESIS_PATH", path)
    path.write_text("[]", encoding="utf-8")
    summary = _executive_summary({"datasets": {}, "meta": {}})
    assert "缺失或不可读" in summary["macroStance"]
    path.write_text("{}", encoding="utf-8")
    summary = _executive_summary({"datasets": {}, "meta": {}})
    assert "没有四时钟状态" in summary["macroStance"]
    assert all(item["badge"] == "未运行" for item in summary["takeaways"])


def test_guidance_moves_detects_calendar_cut_and_keeps_upgrade():
    ups, downs = _guidance_moves([
        {"company": "Microsoft", "low": 170, "high": 170, "prevLow": 175, "prevHigh": 175},
        {"company": "Alphabet", "low": 195, "high": 205, "prevLow": 180, "prevHigh": 190},
        {"company": "NoPrev", "low": 10, "high": 20, "prevLow": None, "prevHigh": None},
    ])
    assert downs == ["Microsoft"]
    assert ups == ["Alphabet"]
    assert "NoPrev" not in ups + downs


def test_industry_events_are_dated_and_sourced():
    events_path = TRACKER_V2 / "tracker_data" / "industry_events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    assert len(events) >= 5
    dates = []
    for event in events:
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", event["date"])
        assert event["importance"] in ("high", "medium", "low")
        assert event["label"]
        assert event.get("source"), "事件必须能回到项目内来源，不能只凭记忆"
        dates.append(event["date"])
    assert dates == sorted(dates)
    assert "Llama 3" not in json.dumps(events, ensure_ascii=False)


def test_cross_clock_sandbox_is_in_the_page():
    snapshot = build_snapshot()
    html = build_html(snapshot)
    assert 'id="sandbox-chart"' in html
    assert 'id="toggle-events"' in html
    assert "SANDBOX_SERIES_CATALOG" in html
    # 下拉里的 dataset/series 必须真的能取到点；否则默认选项和切换都会画出空图。
    pairs = re.findall(r"\{id:'([^']+)',label:'[^']*',dataset:'([^']+)',series:'([^']+)'\}", html)
    assert len(pairs) >= 7
    for combo_id, dataset, series in pairs:
        rows = [row for row in snapshot["datasets"].get(dataset, []) if row.get("series") == series]
        assert rows, f"{combo_id} -> {dataset}/{series} 没有数据"


def test_event_markers_reach_primary_volume_and_price_charts():
    html = build_html(build_snapshot())
    # 事件线不能只落在次要图上：主图（Token 总量、H100 价格）必须调用同一个渲染器。
    assert "function eventMarkers" in html
    assert html.count("eventMarkers(start,end,x") >= 2
    assert "g==='H100'?{eventLabels:true}" in html
