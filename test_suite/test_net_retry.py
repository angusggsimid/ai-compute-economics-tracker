"""网络重试助手：只对瞬时故障重试，确定性失败立即抛出，用尽后照常报错。

动机：阻塞源任何一次网络抖动都会让整条流水线变红。重试必须"减少假失败"，
但绝不能"掩盖真失败"——所以这两条都要测。
"""
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.net_retry import is_transient, retry_call  # noqa: E402


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("code", [408, 425, 429, 500, 502, 503, 504, 523])
def test_transient_statuses_are_retried(code):
    assert is_transient(_http_error(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
def test_permanent_statuses_are_not_retried(code):
    assert is_transient(_http_error(code)) is False


def test_network_level_errors_are_transient():
    assert is_transient(urllib.error.URLError("temporary failure")) is True
    assert is_transient(TimeoutError("timed out")) is True
    assert is_transient(ConnectionResetError("reset")) is True
    assert is_transient(ValueError("schema changed")) is False


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503)
        return "ok"

    assert retry_call(flaky, label="t", attempts=3, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_raises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise _http_error(500)

    with pytest.raises(urllib.error.HTTPError):
        retry_call(always_fail, label="t", attempts=3, base_delay=0)
    assert calls["n"] == 3, "重试用尽后必须抛出（不得吞掉失败）"


def test_permanent_error_raises_immediately(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    def forbidden():
        calls["n"] += 1
        raise _http_error(403)

    with pytest.raises(urllib.error.HTTPError):
        retry_call(forbidden, label="t", attempts=3, base_delay=0)
    assert calls["n"] == 1, "确定性 4xx 不该重试"


def test_retry_prints_visible_notice(monkeypatch, capsys):
    """重试必须可见——不掩盖上游问题。"""
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    def once_fail():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(503)
        return 1

    retry_call(once_fail, label="某源", attempts=2, base_delay=0)
    assert "[retry]" in capsys.readouterr().out


def test_blocking_backfills_wrap_network_calls():
    """阻塞源必须走重试；且 schema 校验不得被重试包吞掉。"""
    for rel in ("scripts/backfill_openrouter_cost_index.py",
                "scripts/backfill_openrouter_active_prices.py",
                "scripts/backfill_neocloud_prices.py"):
        src = (ROOT / rel).read_text("utf-8")
        assert "retry_call(" in src, f"{rel} 未接入重试"
    neo = (ROOT / "scripts/backfill_neocloud_prices.py").read_text("utf-8")
    assert "schema changed" in neo, "neocloud 的 schema 校验被删掉了"
