"""Unit tests for OpenRouter cost-index complete-week retention and merge."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "backfill_openrouter_cost_index.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("backfill_openrouter_cost_index", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _week(week_date: str, tokens: float = 1.0) -> dict:
    return {
        "date": week_date,
        "total_tokens": tokens,
        "named_tokens": tokens,
        "model_rows": [{"model": "openai/gpt-test", "provider": "openai", "tokens": tokens}],
        "price_snapshot": {
            "sha": f"sha-{week_date}",
            "committed_at": f"{week_date}T00:00:00Z",
            "commit_url": "u",
        },
    }


def test_incomplete_current_week_is_excluded_from_chart_points():
    as_of = date(2026, 7, 14)
    points = [
        {"x": "2025-07-14", "ys": {"a": 1}},
        {"x": "2026-07-06", "ys": {"a": 2}},
        {"x": "2026-07-13", "ys": {"a": 3}},  # ends 2026-07-19, incomplete on 2026-07-14
    ]
    filtered = mod.filter_complete_chart_points(
        points,
        start_date=date(2025, 7, 1),
        as_of=as_of,
    )
    assert [point["x"] for point in filtered] == ["2025-07-14", "2026-07-06"]
    assert not mod.is_complete_week(date(2026, 7, 13), as_of)
    assert mod.is_complete_week(date(2026, 7, 6), as_of)


def test_merge_retains_history_squeezed_out_of_rolling_window():
    """Upstream rolling window drops the oldest complete week; local history must keep it."""
    as_of = date(2026, 7, 14)
    prior = [_week(f"2025-07-{day:02d}", tokens=float(day)) for day in (14, 21, 28)]
    # Rolling window no longer includes 2025-07-14; includes newer complete weeks only.
    upstream = [
        _week("2025-07-21", tokens=210.0),  # newer upstream value for overlap
        _week("2025-07-28", tokens=280.0),
        _week("2026-07-06", tokens=700.0),
    ]
    merged = mod.merge_week_history(
        prior,
        upstream,
        start_date=date(2025, 7, 1),
        as_of=as_of,
    )
    dates = [row["date"] for row in merged]
    assert dates == ["2025-07-14", "2025-07-21", "2025-07-28", "2026-07-06"]
    assert merged[0]["total_tokens"] == 14.0  # retained only from local history
    assert merged[1]["total_tokens"] == 210.0  # upstream wins on duplicate date
    assert all(mod.is_complete_week(date.fromisoformat(row["date"]), as_of) for row in merged)


def test_merge_dedupes_by_week_date_and_drops_incomplete_prior_rows():
    as_of = date(2026, 7, 14)
    prior = [
        _week("2025-07-14", tokens=1.0),
        _week("2026-07-13", tokens=99.0),  # incomplete; must never enter formal series
    ]
    upstream = [
        _week("2025-07-14", tokens=2.0),
        _week("2026-07-06", tokens=3.0),
    ]
    merged = mod.merge_week_history(
        prior,
        upstream,
        start_date=date(2025, 7, 1),
        as_of=as_of,
    )
    assert [row["date"] for row in merged] == ["2025-07-14", "2026-07-06"]
    assert merged[0]["total_tokens"] == 2.0
    assert "2026-07-13" not in {row["date"] for row in merged}


def test_merge_drops_prior_weeks_before_retention_start_date():
    as_of = date(2026, 7, 14)
    prior = [
        _week("2025-07-07", tokens=1.0),  # before retention start
        _week("2025-07-14", tokens=2.0),
    ]
    upstream = [_week("2026-07-06", tokens=3.0)]
    merged = mod.merge_week_history(
        prior,
        upstream,
        start_date=date(2025, 7, 14),
        as_of=as_of,
    )
    assert [row["date"] for row in merged] == ["2025-07-14", "2026-07-06"]


def test_merge_provider_shares_keeps_prior_only_for_retained_dates():
    prior_shares = [
        {"date": "2025-07-14", "provider": "openai", "tokens": 1.0},
        {"date": "2025-07-21", "provider": "openai", "tokens": 2.0},
        {"date": "2025-07-28", "provider": "openai", "tokens": 3.0},
    ]
    upstream_shares = [
        {"date": "2025-07-21", "provider": "openai", "tokens": 20.0},
        {"date": "2025-07-21", "provider": "Others", "tokens": 1.0},
        {"date": "2026-07-06", "provider": "openai", "tokens": 30.0},
    ]
    week_dates = {"2025-07-14", "2025-07-21", "2026-07-06"}
    merged = mod.merge_provider_shares(prior_shares, upstream_shares, week_dates)
    assert [row["date"] for row in merged] == [
        "2025-07-14",
        "2025-07-21",
        "2025-07-21",
        "2026-07-06",
    ]
    assert merged[0]["tokens"] == 1.0
    assert merged[1]["tokens"] == 20.0
    assert "2025-07-28" not in {row["date"] for row in merged}


def test_load_prior_missing_file_is_empty_first_run(tmp_path):
    prior = mod.load_prior_history(tmp_path / "missing.json")
    assert prior["weeks"] == []
    assert prior["provider_shares"] == []


def test_load_prior_corrupt_json_fails_hard(tmp_path):
    path = tmp_path / "openrouter_cost_index.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="corrupt"):
        mod.load_prior_history(path)


def test_load_prior_schema_mismatch_fails_hard(tmp_path):
    path = tmp_path / "openrouter_cost_index.json"
    path.write_text(json.dumps({"window": {}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing weeks"):
        mod.load_prior_history(path)

    path.write_text(json.dumps({"weeks": "nope"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="weeks must be list"):
        mod.load_prior_history(path)

    path.write_text(json.dumps({"weeks": [{"date": "2025-07-14"}]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing required keys"):
        mod.load_prior_history(path)


def _fixed_datetime(as_of: date):
    class _FixedDateTime:
        @staticmethod
        def now(tz=None):
            class _Now:
                def date(self_inner):
                    return as_of

                def replace(self_inner, **kwargs):
                    class _Replaced:
                        def isoformat(self_inner2):
                            return f"{as_of.isoformat()}T00:00:00+00:00"

                    return _Replaced()

            return _Now()

    return _FixedDateTime


def _chart_payload(week_points: list[tuple[str, float]]) -> dict:
    return {
        "data": {
            "cachedAt": "2026-07-14T00:00:00Z",
            "data": [
                {"x": week_date, "ys": {"openai/a": tokens, "Others": 0.5}}
                for week_date, tokens in week_points
            ],
        }
    }


def _install_build_fakes(monkeypatch, as_of: date, week_points: list[tuple[str, float]]) -> None:
    def _fake_fetch(session, url, **kwargs):
        if "model-rankings-chart" in url:
            payload = _chart_payload(week_points)
            return payload, b'{"ok":true}', url
        if "raw.githubusercontent.com" in url:
            payload = {"openai/a": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}}
            return payload, b'{"openai/a":{}}', url
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(mod, "_fetch_json", _fake_fetch)
    monkeypatch.setattr(
        mod,
        "_commit_before",
        lambda *_a, **_k: {
            "sha": "abc",
            "committed_at": f"{as_of.isoformat()}T00:00:00Z",
            "commit_url": "https://example.test/commit",
        },
    )
    monkeypatch.setattr(mod, "datetime", _fixed_datetime(as_of))


def _prior_artifact(prior_weeks: list[dict]) -> dict:
    return {
        "generated_at": "2026-07-13T00:00:00Z",
        "weeks": prior_weeks,
        "provider_shares": [
            {
                "date": week["date"],
                "provider": "openai",
                "tokens": week["total_tokens"],
                "share_pct": 100.0,
            }
            for week in prior_weeks
        ],
        "sources": {
            "openrouter": {
                "url": "https://openrouter.ai/api/frontend/v1/rankings/model-rankings-chart",
                "raw_sha256": "sha256:prior-openrouter-raw",
            }
        },
    }


def test_build_raises_clearly_when_openrouter_fetch_fails(tmp_path, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(mod, "_fetch_json", _boom)
    with pytest.raises(RuntimeError, match="upstream unavailable"):
        mod.build(date(2025, 7, 1), tmp_path / "missing.json", reuse_commits=True)


def test_build_fails_when_existing_cache_is_corrupt(tmp_path, monkeypatch):
    as_of = date(2026, 7, 14)
    out = tmp_path / "openrouter_cost_index.json"
    out.write_text("{broken", encoding="utf-8")
    _install_build_fakes(
        monkeypatch,
        as_of,
        [(f"2025-07-{d:02d}", 1.0) for d in range(14, 21)] + [("2026-07-06", 2.0)],
    )
    with pytest.raises(RuntimeError, match="corrupt"):
        mod.build(date(2025, 7, 1), out, reuse_commits=True)


def test_build_fails_when_existing_cache_schema_mismatches(tmp_path, monkeypatch):
    as_of = date(2026, 7, 14)
    out = tmp_path / "openrouter_cost_index.json"
    # File exists but lacks weeks — must not silently become empty history and pass.
    out.write_text(json.dumps({"generated_at": "x"}), encoding="utf-8")
    start = date(2025, 7, 14)
    # Upstream alone would have 52 complete weeks if we ignored bad cache.
    prior_weeks = []
    cursor = start
    while cursor + timedelta(days=6) < as_of:
        prior_weeks.append((cursor.isoformat(), 1.0))
        cursor += timedelta(days=7)
    assert len(prior_weeks) == 52
    _install_build_fakes(monkeypatch, as_of, prior_weeks)
    with pytest.raises(RuntimeError, match="schema mismatch"):
        mod.build(start, out, reuse_commits=True)


def test_build_fails_when_merge_cannot_retain_52_complete_weeks(tmp_path, monkeypatch):
    """Do not lower the 52-week floor or invent weeks when history is insufficient."""
    as_of = date(2026, 7, 14)
    _install_build_fakes(
        monkeypatch,
        as_of,
        [
            ("2025-07-21", 1.0),
            ("2026-07-06", 2.0),
            ("2026-07-13", 3.0),  # incomplete on as_of
        ],
    )
    out = tmp_path / "openrouter_cost_index.json"
    with pytest.raises(RuntimeError, match="only 2 weeks after merge"):
        mod.build(date(2025, 7, 1), out, reuse_commits=False)


def test_build_merges_prior_history_to_retain_52_complete_weeks(tmp_path, monkeypatch):
    """Rolling upstream may expose only 51 complete weeks; local history must fill the gap."""
    as_of = date(2026, 7, 14)
    start = date(2025, 7, 14)
    # 52 complete local weeks ending 2026-07-06.
    prior_weeks = []
    cursor = start
    while cursor + timedelta(days=6) < as_of:
        prior_weeks.append(_week(cursor.isoformat(), tokens=float(len(prior_weeks) + 1)))
        cursor += timedelta(days=7)
    assert len(prior_weeks) == 52

    # Upstream rolling window dropped the oldest complete week and added incomplete current week.
    upstream_points = [
        (week["date"], float(week["total_tokens"]))
        for week in prior_weeks[1:]
    ] + [("2026-07-13", 999.0)]
    assert len(upstream_points) == 52  # 51 complete + 1 incomplete

    out = tmp_path / "openrouter_cost_index.json"
    out.write_text(json.dumps(_prior_artifact(prior_weeks)), encoding="utf-8")
    _install_build_fakes(monkeypatch, as_of, upstream_points)
    artifact = mod.build(start, out, reuse_commits=True)

    dates = [row["date"] for row in artifact["weeks"]]
    assert len(dates) == 52
    assert dates[0] == "2025-07-14"  # retained only from local prior history
    assert dates[-1] == "2026-07-06"
    assert "2026-07-13" not in dates
    assert artifact["sources"]["openrouter"]["upstream_complete_weeks"] == 51
    assert artifact["sources"]["openrouter"]["retained_complete_weeks"] == 52
    provenance = artifact["sources"]["openrouter"]["history_provenance"]
    assert provenance["local_only_weeks"] == ["2025-07-14"]
    assert provenance["local_only_week_count"] == 1
    assert provenance["retention_start"] == start.isoformat()
    # Oldest week exists only in prior history; overlapping weeks take upstream totals
    # (fake chart payload includes named tokens + fixed Others=0.5).
    assert artifact["weeks"][0]["total_tokens"] == 1.0
    assert artifact["weeks"][1]["total_tokens"] == 2.5
    assert "history_retention" in artifact["method"]


def test_build_is_idempotent_on_repeat_run_with_same_upstream(tmp_path, monkeypatch):
    as_of = date(2026, 7, 14)
    start = date(2025, 7, 14)
    prior_weeks = []
    cursor = start
    while cursor + timedelta(days=6) < as_of:
        prior_weeks.append(_week(cursor.isoformat(), tokens=float(len(prior_weeks) + 1)))
        cursor += timedelta(days=7)
    upstream_points = [
        (week["date"], float(week["total_tokens"])) for week in prior_weeks[1:]
    ] + [("2026-07-13", 999.0)]

    out = tmp_path / "openrouter_cost_index.json"
    out.write_text(json.dumps(_prior_artifact(prior_weeks)), encoding="utf-8")
    _install_build_fakes(monkeypatch, as_of, upstream_points)

    first = mod.build(start, out, reuse_commits=True)
    second = mod.build(start, out, reuse_commits=True)

    assert [row["date"] for row in first["weeks"]] == [row["date"] for row in second["weeks"]]
    assert [row["total_tokens"] for row in first["weeks"]] == [
        row["total_tokens"] for row in second["weeks"]
    ]
    assert first["sources"]["openrouter"]["history_provenance"]["local_only_weeks"] == (
        second["sources"]["openrouter"]["history_provenance"]["local_only_weeks"]
    )
    assert "2026-07-13" not in {row["date"] for row in second["weeks"]}
    assert len(second["weeks"]) == 52


def test_build_first_run_without_cache_fails_when_upstream_has_only_51_complete(
    tmp_path, monkeypatch
):
    as_of = date(2026, 7, 14)
    start = date(2025, 7, 14)
    prior_weeks = []
    cursor = start
    while cursor + timedelta(days=6) < as_of:
        prior_weeks.append((cursor.isoformat(), 1.0))
        cursor += timedelta(days=7)
    # Drop oldest, add incomplete current week → 51 complete in upstream window.
    upstream_points = prior_weeks[1:] + [("2026-07-13", 9.0)]
    assert len(upstream_points) == 52
    _install_build_fakes(monkeypatch, as_of, upstream_points)
    with pytest.raises(RuntimeError, match="only 51 weeks after merge"):
        mod.build(start, tmp_path / "missing.json", reuse_commits=False)


def test_min_complete_weeks_floor_is_not_lowered():
    assert mod.MIN_COMPLETE_WEEKS == 52


def test_filter_complete_chart_points_drops_points_before_start_date():
    as_of = date(2026, 7, 14)
    points = [
        {"x": "2025-07-07", "ys": {"a": 1}},  # before retention start
        {"x": "2025-07-14", "ys": {"a": 2}},
        {"x": "2026-07-06", "ys": {"a": 3}},
    ]
    filtered = mod.filter_complete_chart_points(
        points,
        start_date=date(2025, 7, 14),
        as_of=as_of,
    )
    assert [point["x"] for point in filtered] == ["2025-07-14", "2026-07-06"]


def test_load_prior_history_requires_price_snapshot_keys(tmp_path):
    path = tmp_path / "openrouter_cost_index.json"
    week = _week("2025-07-14")
    week["price_snapshot"] = {"sha": "abc"}  # missing committed_at, commit_url
    path.write_text(json.dumps({"weeks": [week]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="price_snapshot missing required keys"):
        mod.load_prior_history(path)


def test_load_prior_history_requires_provider_share_schema(tmp_path):
    path = tmp_path / "openrouter_cost_index.json"
    week = _week("2025-07-14")
    path.write_text(
        json.dumps({"weeks": [week], "provider_shares": ["not-an-object"]}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=r"provider_shares\[0\]: must be an object"):
        mod.load_prior_history(path)

    path.write_text(
        json.dumps({"weeks": [week], "provider_shares": [{"date": week["date"]}]}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="missing required keys"):
        mod.load_prior_history(path)


def test_merge_provider_shares_replaces_all_prior_rows_for_overwritten_date():
    prior_shares = [
        {"date": "2025-07-21", "provider": "openai", "tokens": 1.0},
        {"date": "2025-07-21", "provider": "anthropic", "tokens": 2.0},
    ]
    upstream_shares = [
        {"date": "2025-07-21", "provider": "openai", "tokens": 10.0},
    ]
    merged = mod.merge_provider_shares(prior_shares, upstream_shares, {"2025-07-21"})
    assert [row["provider"] for row in merged] == ["openai"]
    assert merged[0]["tokens"] == 10.0


def test_build_requires_traceable_provider_history_for_local_only_week(tmp_path, monkeypatch):
    as_of = date(2026, 7, 14)
    start = date(2025, 7, 14)
    prior_weeks = []
    cursor = start
    while cursor + timedelta(days=6) < as_of:
        prior_weeks.append(_week(cursor.isoformat()))
        cursor += timedelta(days=7)
    upstream_points = [(week["date"], 1.0) for week in prior_weeks[1:]] + [
        ("2026-07-13", 9.0)
    ]
    _install_build_fakes(monkeypatch, as_of, upstream_points)

    missing_shares = _prior_artifact(prior_weeks)
    missing_shares["provider_shares"] = missing_shares["provider_shares"][1:]
    out = tmp_path / "missing-shares.json"
    out.write_text(json.dumps(missing_shares), encoding="utf-8")
    with pytest.raises(RuntimeError, match="lack provider-share history"):
        mod.build(start, out, reuse_commits=True)

    missing_hash = _prior_artifact(prior_weeks)
    missing_hash["sources"]["openrouter"].pop("raw_sha256")
    out = tmp_path / "missing-hash.json"
    out.write_text(json.dumps(missing_hash), encoding="utf-8")
    with pytest.raises(RuntimeError, match="lack prior raw source hash"):
        mod.build(start, out, reuse_commits=True)
