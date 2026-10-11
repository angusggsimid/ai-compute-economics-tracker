"""P1–P4 修复的回归测试：每一条都对应一个曾经会让投资人误读的缺陷。

覆盖：财政季→日历季映射、季度连续计数（申报日双报陷阱）、残周剔除尺子、
按供应商先聚的中位价、偶数家合成中位标记、P25–P75 窄样本不可估、
sha256/URL 透传、结论句数据驱动。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

import thesis_engine as T  # noqa: E402
from week_quality import (  # noqa: E402
    complete_week_count,
    drop_partial_first_week,
    is_partial_first_week,
)
from build_time_series_dashboard import (  # noqa: E402
    _breadth_value,
    _capex_quarterly,
    _gpu_from_neocloud,
    build_snapshot,
)

KINDS = {"on-demand", "secure", "community"}


# ---------- P2.1 财政季→日历季映射 ----------

def _actual(company, date_, period, value=1.0):
    return {
        "date": date_,
        "company": company,
        "metric": "capex actual",
        "value": value,
        "unit": "USD_B",
        "period": period,
        "source_url": "https://www.sec.gov/x.htm",
    }


def test_fiscal_quarter_maps_to_calendar_quarter_per_company():
    rows = [
        _actual("Microsoft", "2026-03-31", "FY2026 Q3", 30.9),   # MSFT 财年 Q3=日历 Q1
        _actual("Oracle", "2026-08-31", "FY2026 Q1", 28.5),      # Oracle 财年 Q1=6-8月=日历 Q3
        _actual("Meta", "2026-03-31", "FY2026 Q1", 19.0),        # Meta 财年=日历年
    ]
    quarterly, _ = _capex_quarterly(rows)
    got = {(r["series"], r["group"]) for r in quarterly}
    assert ("Microsoft", "26Q1") in got
    assert ("Oracle", "26Q3") in got
    assert ("Meta", "26Q1") in got


def test_fiscal_quarter_excludes_cumulative_and_annual_rows():
    rows = [
        _actual("Meta", "2026-03-31", "FY2026 Q1", 19.0),
        _actual("Meta", "2026-06-30", "FY2026 Q2 累计（约6个月）", 49.1),  # 累计，不是单季
        _actual("Meta", "2026-07-29", "FY2026 Q2", 30.1),
        _actual("Oracle", "2026-05-31", "FY2026", 55.7),                   # 年度，不是季度
    ]
    quarterly, _ = _capex_quarterly(rows)
    meta = {r["group"]: r["value"] for r in quarterly if r["series"] == "Meta"}
    assert meta == {"26Q1": 19.0, "26Q2": 30.1}, "累计行或重复财季污染了单季序列"
    assert not [r for r in quarterly if r["series"] == "Oracle and value" == 55.7]


def test_quarter_count_ignores_filing_date_double_report():
    """Meta/Alphabet 同一份 Q2 被披露两次（6/30 累计 + 7/29 单季）。
    旧实现按申报日折算季度，会把 2 个真实季度数成 3 个。"""
    rows = [
        _actual("Meta", "2026-03-31", "FY2026 Q1"),
        _actual("Meta", "2026-06-30", "FY2026 Q2 累计（约6个月）"),
        _actual("Meta", "2026-07-29", "FY2026 Q2"),
    ]
    out = T.evaluate_commitment({"capex": {"rows": rows}, "reference": {"datasets": {}}})
    assert out["metrics"]["companiesWith3ConsecutiveQuarters"] == 0
    assert out["metrics"]["maxConsecutiveQuarters"] == 2
    assert out["metrics"]["consecutiveQuartersByCompany"]["Meta"] == 2


def test_quarter_count_reaches_three_only_with_three_real_quarters():
    rows = [
        _actual("Amazon", "2025-12-31", "FY2025 Q4"),
        _actual("Amazon", "2026-03-31", "FY2026 Q1"),
        _actual("Amazon", "2026-06-30", "FY2026 Q2"),
    ]
    out = T.evaluate_commitment({"capex": {"rows": rows}, "reference": {"datasets": {}}})
    assert out["metrics"]["consecutiveQuartersByCompany"]["Amazon"] == 3
    assert out["metrics"]["companiesWith3ConsecutiveQuarters"] == 1


def test_quarter_run_resets_on_gap():
    rows = [
        _actual("Amazon", "2025-03-31", "FY2025 Q1"),
        _actual("Amazon", "2025-06-30", "FY2025 Q2"),
        _actual("Amazon", "2026-03-31", "FY2026 Q1"),
        _actual("Amazon", "2026-06-30", "FY2026 Q2"),
    ]
    out = T.evaluate_commitment({"capex": {"rows": rows}, "reference": {"datasets": {}}})
    # 2025Q2 → 2026Q1 跨年不连续，最长连段应为 2
    assert out["metrics"]["maxConsecutiveQuarters"] == 2


# ---------- P2.6 残周尺子（图与时钟共用） ----------

def test_partial_first_week_detected_and_dropped():
    rows = [
        {"date": "2025-09-22", "value": 0.75},
        {"date": "2025-09-29", "value": 5.38},
        {"date": "2025-10-06", "value": 5.02},
    ]
    assert is_partial_first_week([0.75, 5.38, 5.02])
    kept, dropped = drop_partial_first_week(rows, "value")
    assert dropped == "2025-09-22"
    assert [r["date"] for r in kept] == ["2025-09-29", "2025-10-06"]


def test_normal_series_first_week_is_not_dropped():
    rows = [{"date": f"2026-01-{d:02d}", "value": v} for d, v in ((5, 4.0), (12, 4.2), (19, 4.1))]
    assert not is_partial_first_week([4.0, 4.2, 4.1])
    kept, dropped = drop_partial_first_week(rows, "value")
    assert dropped is None
    assert len(kept) == 3


def test_complete_week_count_matches_chart_series():
    """时钟报的"完整周数"必须等于图上的周数——两者共用 week_quality。"""
    snapshot = build_snapshot()
    chart_dates = {r["date"] for r in snapshot["datasets"]["openrouterVolume"]}
    raw = json.loads((ROOT / "tracker_data" / "backfills" / "openrouter_cost_index.json").read_text("utf-8"))["weeks"]
    assert complete_week_count(raw) == len(chart_dates)


# ---------- P2.2 中位价：按供应商先聚 ----------

def _offer(day, provider, price, series="H100", kind="on-demand"):
    return {"date": day, "provider": provider, "series": series, "kind": kind, "usdPerGpuHour": price}


def test_median_is_taken_over_per_provider_medians_not_raw_quotes():
    """一家供应商挂 3 条极低价不能把中位数拽下去（每家一票）。"""
    rows = [_offer("2026-09-27", "a", 1.0), _offer("2026-09-27", "a", 1.1), _offer("2026-09-27", "a", 1.2)]
    for prov, price in (("b", 5.0), ("c", 5.0), ("d", 5.0), ("e", 5.0)):
        rows.append(_offer("2026-09-27", prov, price))
    out = _gpu_from_neocloud(rows)["prices"]
    assert out[0]["value"] == 5.0, "多挂报价的供应商被重复计票"
    assert out[0]["providerCount"] == 5


def test_even_provider_count_is_flagged_as_synthetic_median():
    rows = [_offer("2026-09-27", p, v) for p, v in (("a", 1.0), ("b", 2.0), ("c", 3.0), ("d", 4.0))]
    out = _gpu_from_neocloud(rows)["prices"][0]
    assert out["medianSynthetic"] is True
    assert out["value"] == 2.5  # 两家均值
    odd = _gpu_from_neocloud([_offer("2026-09-27", p, v) for p, v in (("a", 1.0), ("b", 2.0), ("c", 3.0))])["prices"][0]
    assert odd["medianSynthetic"] is False


def test_p25_p75_undefined_when_fewer_than_four_providers():
    """供应商 <4 家时四分位不可估，必须置空而不是拿全距冒充。"""
    out = _gpu_from_neocloud([_offer("2026-09-27", p, v) for p, v in (("a", 1.0), ("b", 5.0), ("c", 9.0))])["prices"][0]
    assert out["p25"] is None and out["p75"] is None
    assert out["low"] == 1.0 and out["high"] == 9.0, "全距仍须保留"


def test_spot_and_serverless_kinds_are_excluded():
    rows = [_offer("2026-09-27", "a", 1.0), _offer("2026-09-27", "b", 5.0),
            _offer("2026-09-27", "c", 0.01, kind="spot"), _offer("2026-09-27", "d", 99.0, kind="serverless")]
    out = _gpu_from_neocloud(rows)["prices"][0]
    assert out["providerCount"] == 2
    assert out["high"] == 5.0


# ---------- P1 披露层 ----------

def test_every_displayed_source_has_a_real_url():
    snapshot = build_snapshot()
    missing = [k for k, v in snapshot["sources"].items() if not (v.get("urls") or [])]
    assert not missing, f"这些来源没有可点击的真实 URL：{missing}"


def test_breadth_derives_from_daily_availability_window():
    """广度必须由 7 天窗口的逐日 provider 明细推导（可回填、日密）。

    旧口径（目录 providerCount）只在运行日有值，且会被滚动窗口回写覆盖——
    每个提交里都只剩最后一天（2026-10-11 复盘确认后切换）。
    """
    row = {"availabilityByProvider": {"A": [1, 4], "B": [0, 0], "C": [3, 5]}}
    assert _breadth_value(row) == 2, "total=0 的供应商不得计入在架广度"
    assert _breadth_value({"availabilityByProvider": {}}) is None
    assert _breadth_value({}) is None


def test_sources_carry_sha256_when_fetch_succeeded():
    snapshot = build_snapshot()
    for key in ("gpuPrice", "openrouter", "activePrice", "basisH100"):
        sha = snapshot["sources"][key].get("sha256") or ""
        assert sha.count("sha256:") >= 1, f"{key} 缺 sha256"


def test_displayed_gpu_url_is_the_actually_fetched_url():
    """展示的 URL 必须是抓取用的那个，不能是站点首页。"""
    snapshot = build_snapshot()
    url = snapshot["sources"]["gpuPrice"]["urls"][0]
    assert "gpurentalprices.com/data" not in url
    assert url.startswith("https://")


def test_multi_url_sources_render_all_links_not_one_broken_concat():
    snapshot = build_snapshot()
    capex_urls = snapshot["sources"]["capex"]["urls"]
    assert len(capex_urls) > 1
    assert all("|" not in u for u in capex_urls), "URL 里不能有拼接分隔符"
    basis = snapshot["sources"]["basisH100"]["urls"]
    assert len(basis) == 3 and all("|" not in u for u in basis)


# ---------- P3 结论句数据驱动 ----------

def test_no_handwritten_conclusion_strings_remain_in_markup():
    """手写结论会随数据变化说反话（曾出现"自12月起走平"而序列实为 8.9 倍波动）。"""
    from build_time_series_dashboard import build_html
    html = build_html(build_snapshot())
    for banned in ("自 12 月起加权价走平", "本身是一条结论", "溢价收敛", "大单/口径变化待查"):
        assert banned not in html, f"仍存在手写结论句：{banned}"


def test_provider_count_label_is_derived_from_data():
    snapshot = build_snapshot()
    universe = snapshot["meta"]["providerUniverse"]
    latest = {}
    for r in snapshot["datasets"]["gpuPrice"]:
        cur = latest.get(r["series"])
        if cur is None or r["date"] > cur["date"]:
            latest[r["series"]] = r
    # 全域家数必须 ≥ 任一 GPU 当日参与家数，否则标签本身就在说谎
    assert universe >= max(r["providerCount"] for r in latest.values())
    for series, row in latest.items():
        assert row["providerCount"] > 0, series
