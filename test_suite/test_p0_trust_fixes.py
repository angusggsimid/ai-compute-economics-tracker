"""P0 信任级修复的回归测试。

覆盖三类曾经会让页面"数字/状态与事实相反"的缺陷：
1. 指引修订取值顺序——旧修订覆盖新修订（页面显示作废版本，且与下方溯源表矛盾）。
2. 新鲜度徽章——上游部分失败却显示绿点。
3. 缓存回放谎报新鲜度——fetchedAt 写成运行时间，行内无"来自缓存"标记。
"""
import json
import re
from datetime import date
from pathlib import Path

from company_config import decision_universe_configs
from scripts.refresh_capex_history import refresh
from html_dashboard.build_time_series_dashboard import _capex_quarterly, _fresh_badge

ROOT = Path(__file__).resolve().parents[1]


def _guidance_row(company, date_, metric, value):
    return {
        "date": date_,
        "company": company,
        "metric": metric,
        "value": value,
        "unit": "USD_B",
        "period": "capex_guidance_revision",
        "source_url": "https://www.sec.gov/example.htm",
    }


def test_guidance_keeps_latest_revision_not_stale_one():
    """Meta 指引有两版修订：4/29 的 125-145 已被 7/29 的 130-145 取代。
    构建层按 (date, company) 倒序传入，必须首写优先，否则 chip 显示作废版本。"""
    rows = [
        # 倒序：最新在前（与调用方排序一致）
        _guidance_row("Meta", "2026-07-29", "fy2026 capex guidance low", 130.0),
        _guidance_row("Meta", "2026-07-29", "fy2026 capex guidance high", 145.0),
        _guidance_row("Meta", "2026-07-29", "fy2026 capex guidance previous low", 125.0),
        _guidance_row("Meta", "2026-07-29", "fy2026 capex guidance previous high", 145.0),
        _guidance_row("Meta", "2026-04-29", "fy2026 capex guidance low", 125.0),
        _guidance_row("Meta", "2026-04-29", "fy2026 capex guidance high", 145.0),
        _guidance_row("Meta", "2026-04-29", "fy2026 capex guidance previous low", 115.0),
        _guidance_row("Meta", "2026-04-29", "fy2026 capex guidance previous high", 135.0),
    ]

    _quarterly, guidance = _capex_quarterly(rows)

    meta = next(g for g in guidance if g["company"] == "Meta")
    assert meta["low"] == 130.0, "旧修订覆盖了新修订"
    assert meta["high"] == 145.0
    assert meta["prevLow"] == 125.0
    assert meta["prevHigh"] == 145.0
    assert meta["revisionDate"] == "2026-07-29"


def test_guidance_single_revision_still_works():
    rows = [
        _guidance_row("Alphabet", "2026-07-22", "fy2026 capex guidance low", 195.0),
        _guidance_row("Alphabet", "2026-07-22", "fy2026 capex guidance high", 205.0),
        _guidance_row("Alphabet", "2026-07-22", "fy2026 capex guidance previous low", 180.0),
        _guidance_row("Alphabet", "2026-07-22", "fy2026 capex guidance previous high", 190.0),
    ]
    _q, guidance = _capex_quarterly(rows)
    alpha = guidance[0]
    assert (alpha["low"], alpha["high"], alpha["prevLow"], alpha["prevHigh"]) == (195.0, 205.0, 180.0, 190.0)


def test_guidance_drops_empty_slots_instead_of_rendering_null():
    """空壳 slot 过去会渲染成 $null–$nullB。"""
    rows = [_guidance_row("Meta", "2026-07-29", "some unrelated metric", 1.0)]
    _q, guidance = _capex_quarterly(rows)
    assert guidance == []


def test_guidance_calendar_single_value_keeps_note():
    rows = [_guidance_row("Microsoft", "2026-07-29", "calendar 2026 capex guidance", 175.0)]
    _q, guidance = _capex_quarterly(rows)
    msft = guidance[0]
    assert msft["low"] == msft["high"] == 175.0
    assert "CY2026" in (msft.get("note") or "")


class FailingSecClient:
    def fetch_companyfacts(self, config):
        raise RuntimeError(f"HTTP 403 for {config.ticker}")


class WorkingSecClient:
    def fetch_companyfacts(self, config):
        return {
            "facts": {
                "us-gaap": {
                    config.capex_xbrl_tag: {
                        "units": {
                            "USD": [
                                {
                                    "start": "2026-01-01",
                                    "end": "2026-03-31",
                                    "val": 4_000_000_000,
                                    "accn": "0001-26-000001",
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-05-01",
                                }
                            ]
                        }
                    }
                }
            }
        }


def _cached_capex_file(tmp_path, observed_date, previous_fetched_at):
    payload = {
        "rows": [
            {
                "date": observed_date,
                "company": config.company_name,
                "metric": "capex actual",
                "value": 1.0,
                "unit": "USD_B",
                "period": "quarter",
                "source_url": f"https://data.sec.gov/{config.ticker}",
            }
            for config in decision_universe_configs()
        ],
        "fetchedAt": previous_fetched_at,
        "sources": {
            config.ticker: {"url": "u", "fetchedAt": previous_fetched_at, "status": "fresh"}
            for config in decision_universe_configs()
        },
    }
    path = tmp_path / "capex.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_all_failed_fetch_marks_rows_as_cache_and_does_not_advance_fetched_at(tmp_path):
    """全部上游失败时：行必须标 fromCache=True，fetchedAt 不得推进到本次运行时间。"""
    path = _cached_capex_file(tmp_path, "2026-03-31", "2026-04-15T00:00:00Z")

    payload = refresh(path, client=FailingSecClient(), as_of=date(2026, 7, 13))

    assert payload["refreshStatus"] == "current_for_frequency"
    assert payload["fetchedCount"] == 0
    assert payload["fetchedAt"] == "2026-04-15T00:00:00Z", "缓存回放把 fetchedAt 写成了本次运行时间"
    assert payload["runAt"] != payload["fetchedAt"]
    assert all(row["fromCache"] is True for row in payload["rows"])
    # 失败源的 fetchedAt 也必须保留上一次成功时间
    for entry in payload["sources"].values():
        assert entry["fetchedAt"] == "2026-04-15T00:00:00Z"
        assert entry["lastAttemptAt"] == payload["runAt"]


def test_successful_fetch_marks_rows_as_fresh(tmp_path):
    path = _cached_capex_file(tmp_path, "2026-03-31", "2026-04-15T00:00:00Z")

    payload = refresh(path, client=WorkingSecClient(), as_of=date(2026, 7, 13))

    assert payload["fetchedCount"] == len(decision_universe_configs())
    assert payload["fetchedAt"] == payload["runAt"]
    assert not any(row["fromCache"] for row in payload["rows"]), "本期实抓的行不应标为缓存"


def test_badge_downgrades_source_with_upstream_failures(monkeypatch, tmp_path):
    """上游 5 家全失败时不得显示绿点，且必须披露最旧滞后天数。"""
    status = {
        "generatedAt": "2026-09-27T13:59:06Z",
        "publishable": True,
        "sources": [
            {
                "source": "sec_capex",
                "status": "current_for_frequency",
                "qualityWarnings": 5,
                "cacheCoverage": {
                    "MSFT": {"latestDate": "2026-06-30", "ageDays": 89, "current": True},
                    "ORCL": {"latestDate": "2026-08-31", "ageDays": 27, "current": True},
                },
            },
            {"source": "openrouter_usage", "status": "fresh"},
        ],
    }
    path = tmp_path / "tracker_data" / "deploy_refresh_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr("html_dashboard.build_time_series_dashboard.ROOT", tmp_path)

    html = _fresh_badge({})

    rows = [r for r in html.split('<div class="fresh-row">')[1:]]
    sec_row = next((r for r in rows if "sec_capex" in r), None)
    assert sec_row, "sec_capex 行缺失"
    assert 'class="fresh-dot warn"' in sec_row, "上游失败却给了非 warn 色调"
    assert "5 家上游失败" in sec_row
    assert "最旧一条滞后 89 天" in sec_row
    assert 'class="fresh-dot ok"' not in sec_row
    # 正常源仍应是绿点（降级不得扩散）
    ok_row = next((r for r in rows if "openrouter_usage" in r), "")
    assert 'class="fresh-dot ok"' in ok_row
    # 顶部汇总必须把降级源排除在"就绪"之外
    assert "1/2 源就绪" in html


def test_badge_handles_list_quality_warnings(monkeypatch, tmp_path):
    """积累型信息源上报的是失败明细列表（非 int）：非空时必须降级并计数，而不是让发布构建崩溃。"""
    status = {
        "generatedAt": "2026-10-10T06:00:00Z",
        "publishable": True,
        "sources": [
            {
                "source": "fred_cost_anchors",
                "status": "fresh",
                "publishable": True,
                "blocking": False,
                "qualityWarnings": [
                    {"source": "DGS10", "status": "failed", "message": "HTTP 503"},
                    {"source": "DEXCHUS", "status": "failed", "message": "timeout"},
                ],
            },
            {"source": "openrouter_usage", "status": "fresh", "qualityWarnings": []},
        ],
    }
    path = tmp_path / "tracker_data" / "deploy_refresh_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr("html_dashboard.build_time_series_dashboard.ROOT", tmp_path)

    html = _fresh_badge({})

    rows = [r for r in html.split('<div class="fresh-row">')[1:]]
    fred_row = next((r for r in rows if "fred_cost_anchors" in r), None)
    assert fred_row, "fred_cost_anchors 行缺失"
    assert 'class="fresh-dot warn"' in fred_row, "上游失败明细非空却给了非 warn 色调"
    assert "2 个上游失败" in fred_row
    # 空列表形态是常态，不得被当成降级
    ok_row = next((r for r in rows if "openrouter_usage" in r), "")
    assert 'class="fresh-dot ok"' in ok_row
    assert "1/2 源就绪" in html


def test_badge_nonblocking_source_not_labeled_blocking(monkeypatch, tmp_path):
    """非阻塞信息源（如 foundry_signals）超期时不得标成"阻塞发布"。"""
    status = {
        "generatedAt": "2026-10-10T06:00:00Z",
        "publishable": True,
        "sources": [
            {"source": "foundry_signals", "status": "failed_using_last_good", "publishable": True, "blocking": False},
            {"source": "openrouter_usage", "status": "fresh"},
        ],
    }
    path = tmp_path / "tracker_data" / "deploy_refresh_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr("html_dashboard.build_time_series_dashboard.ROOT", tmp_path)

    html = _fresh_badge({})

    rows = [r for r in html.split('<div class="fresh-row">')[1:]]
    row = next((r for r in rows if "foundry_signals" in r), None)
    assert row, "foundry_signals 行缺失"
    assert "非阻塞源" in row
    assert "阻塞发布" not in row


def test_badge_stays_ok_when_no_degradation(monkeypatch, tmp_path):
    status = {
        "generatedAt": "2026-09-27T13:59:06Z",
        "publishable": True,
        "sources": [
            {"source": "a", "status": "fresh"},
            {"source": "b", "status": "current_for_frequency"},
        ],
    }
    path = tmp_path / "tracker_data" / "deploy_refresh_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr("html_dashboard.build_time_series_dashboard.ROOT", tmp_path)

    html = _fresh_badge({})
    assert "2/2 源就绪" in html
    assert html.count('class="fresh-dot ok"') == 2
