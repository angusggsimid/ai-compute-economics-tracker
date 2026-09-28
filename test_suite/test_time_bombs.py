"""定时炸弹类缺陷的回归测试：这些代码在某个时点之前都是正确的。

每一条都对应一个"今天正常、明天会炸"的模式——要么下个财报季炸、要么随窗口滚动炸、
要么随数据增长炸。全部必须保持与时间/数据规模无关。
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

import thesis_engine as T  # noqa: E402
from build_time_series_dashboard import (  # noqa: E402
    _capex_metric_label,
    _capex_quarterly,
    build_snapshot,
)


def _g(metric, value, date_="2027-01-28", company="Meta"):
    return {
        "date": date_, "company": company, "metric": metric, "value": value,
        "unit": "USD_B", "period": "capex_guidance_revision", "source_url": "u",
    }


# ---------- 未来财年：标签必须仍然可被冒烟门识别 ----------

def test_future_fiscal_year_guidance_gets_chinese_label():
    """写死 'fy2026 ...' 会让 FY2027 行回退成机器串，
    冒烟门用 /指引(下限|上限)/ 匹配不到 → 下个财报季挂 CI。"""
    for fy in (2026, 2027, 2030):
        assert _capex_metric_label(f"fy{fy} capex guidance low") == f"FY{fy} 指引下限"
        assert _capex_metric_label(f"fy{fy} capex guidance high") == f"FY{fy} 指引上限"
        assert _capex_metric_label(f"fy{fy} capex guidance previous low") == f"FY{fy} 指引下限（上调前）"
        assert _capex_metric_label(f"fy{fy} capex guidance previous high") == f"FY{fy} 指引上限（上调前）"


def test_smoke_gate_regex_matches_any_fiscal_year():
    """冒烟门用这两个中文正则找表行；任何年份都必须命中。"""
    for fy in (2026, 2027, 2031):
        low = _capex_metric_label(f"fy{fy} capex guidance low")
        high = _capex_metric_label(f"fy{fy} capex guidance high")
        assert re.search("指引(下限|上限)", low) and re.search("指引(下限|上限)", high)
        assert not re.search("上调前", low), "未上调前的行不得被误判为 previous"
        assert re.search("上调前", _capex_metric_label(f"fy{fy} capex guidance previous low"))


def test_future_calendar_year_guidance_label_and_note():
    assert _capex_metric_label("calendar 2027 capex guidance") == "2027 自然年指引"
    rows = [_g("calendar 2027 capex guidance", 175.0, "2027-01-28", "Microsoft")]
    _q, guidance = _capex_quarterly(rows)
    assert guidance[0]["low"] == guidance[0]["high"] == 175.0
    assert "CY2027" in guidance[0]["note"]


def test_guidance_buckets_do_not_mix_across_fiscal_years():
    """财年过渡期 FY2026 与 FY2027 并存时，不得拿旧财年当"上一版"。"""
    rows = [
        _g("fy2027 capex guidance low", 150.0, "2027-01-28"),
        _g("fy2027 capex guidance high", 170.0, "2027-01-28"),
        _g("fy2027 capex guidance previous low", 130.0, "2027-01-28"),
        _g("fy2027 capex guidance previous high", 145.0, "2027-01-28"),
        _g("fy2026 capex guidance low", 125.0, "2026-04-29"),
        _g("fy2026 capex guidance high", 145.0, "2026-04-29"),
    ]
    _q, guidance = _capex_quarterly(sorted(rows, key=lambda r: (r["date"], r["company"]), reverse=True))
    fy27 = next(g for g in guidance if g["fiscalYear"] == "FY2027")
    fy26 = next(g for g in guidance if g["fiscalYear"] == "FY2026")
    assert (fy27["low"], fy27["high"]) == (150.0, 170.0)
    assert (fy27["prevLow"], fy27["prevHigh"]) == (130.0, 145.0), "FY2027 的上一版被 FY2026 污染"
    assert fy26["low"] == 125.0 and fy26["prevLow"] is None


def test_guidance_payload_carries_fiscal_year_for_every_company():
    snapshot = build_snapshot()
    for g in snapshot["meta"]["capexGuidance"]:
        assert g.get("fiscalYear"), f"{g.get('company')} 缺 fiscalYear，chip 无法标出财年"
        assert re.fullmatch(r"(FY|CY)\d{4}", g["fiscalYear"])


# ---------- 低频数据不得被周窗口截断 ----------

def test_low_frequency_datasets_are_exempt_from_weekly_window_filter():
    """CAPEX 溯源表与合约调查是季度/事件频率，永远追不上 52 周滚动窗口。
    若被周窗口过滤，会随窗口前移逐行静默消失（CAPEX 只剩 57 天余量、
    合约带曾被从 21 期削到 10 期）。这里做结构 + 行为双重守卫。"""
    src = (ROOT / "html_dashboard" / "build_time_series_dashboard.py").read_text("utf-8")
    assert "_WINDOW_EXEMPT" in src, "周窗口过滤缺少低频数据豁免名单"
    for key in ("capex", "capexQuarterly", "contractBand"):
        assert f'"{key}"' in src.split("_WINDOW_EXEMPT = ")[1].split("}")[0], f"{key} 未在豁免名单里"

    snapshot = build_snapshot()
    periods = {r["date"] for r in snapshot["datasets"]["contractBand"]}
    assert len(periods) >= 20, f"合约带只剩 {len(periods)} 期，疑似被周窗口削掉"


def test_capex_table_keeps_all_backfill_rows():
    """表格必须与底表行数一致：它是可追溯性的最后一环。"""
    snapshot = build_snapshot()
    backfill = json.loads((ROOT / "tracker_data" / "backfills" / "capex_official_history.json").read_text("utf-8"))
    assert len(snapshot["datasets"]["capex"]) == len(backfill["rows"])


# ---------- 深度增长窗口不随历史长度漂移 ----------

def test_depth_growth_uses_recent_window_not_whole_history():
    """同一组 watch 条件里价格是 30D 窗口，深度若用全历史对半，
    数据越久两个条件的时间尺度差越远，近期收缩会被远史稀释到永不触发。"""
    rows = []
    base = date(2026, 1, 1)
    # 长期 400；窗口内后 30 天腰斩到 200。
    # 全历史对半会把这次腰斩稀释成 +100/−100 的平均，看不清；
    # 只看最近 60 天则明确识别为 −50%。
    for i in range(260):
        d = base + timedelta(days=i)
        rows.append({"date": d.isoformat(), "offerCount": 400 if i < 230 else 200})
    metrics = T._depth_metrics(rows)
    assert metrics["depthWindowDays"] == 60, "深度增长必须只看最近窗口"
    assert metrics["depthGrowthPct"] <= -30, f"近期腰斩未被识别：{metrics['depthGrowthPct']}"


def test_depth_growth_unchanged_when_history_shorter_than_window():
    rows = [{"date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(), "offerCount": 100 + i}
            for i in range(40)]
    metrics = T._depth_metrics(rows)
    assert metrics["depthWindowDays"] == 40


# ---------- 编排顺序（防回归：状态文件必须先于构建落盘） ----------

def test_no_local_date_today_in_pipeline():
    """流水线一律用 UTC 日期：本地 date.today() 在 UTC+8 的 00:00–08:00 会早一天，
    370 天窗口可能只剩 51 个完整周并触发 52 周下限报错。"""
    offenders = []
    for rel in ("thesis_engine.py", "scripts/refresh_and_build.py",
                "scripts/refresh_capex_history.py", "scripts/validate_deploy_refresh.py"):
        for n, line in enumerate((ROOT / rel).read_text("utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if ("date.today()" in stripped or "datetime.now()" in stripped) and "timezone.utc" not in stripped:
                offenders.append(f"{rel}:{n}")
    assert not offenders, f"这些位置用了本地日期，会与 CI 的 UTC 不一致：{offenders}"
