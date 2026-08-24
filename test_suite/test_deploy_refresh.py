import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from company_config import decision_universe_configs
from scripts import refresh_and_build
from scripts.refresh_capex_history import refresh
from scripts.validate_deploy_refresh import validate


class FailingSecClient:
    def fetch_companyfacts(self, config):
        raise RuntimeError(f"HTTP 403 for {config.ticker}")


def _cached_rows(observed_date: str):
    return [
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
    ]


def test_capex_failures_use_current_quarterly_cache_without_claiming_fresh(tmp_path):
    output = tmp_path / "capex.json"
    output.write_text(json.dumps({"rows": _cached_rows("2026-03-31")}), encoding="utf-8")

    payload = refresh(
        output,
        client=FailingSecClient(),
        as_of=date(2026, 7, 13),
    )

    assert payload["refreshStatus"] == "current_for_frequency"
    assert payload["publishable"] is True
    assert len(payload["quality"]) == 5
    assert all(item["current"] for item in payload["cacheCoverage"].values())


def test_capex_failures_block_publish_when_quarterly_cache_is_stale(tmp_path):
    output = tmp_path / "capex.json"
    output.write_text(json.dumps({"rows": _cached_rows("2025-12-31")}), encoding="utf-8")

    payload = refresh(
        output,
        client=FailingSecClient(),
        as_of=date(2026, 7, 13),
    )

    assert payload["refreshStatus"] == "blocked"
    assert payload["publishable"] is False


def test_refresh_runner_preserves_structured_source_status(monkeypatch, tmp_path):
    required_output = tmp_path / "capex.json"
    required_output.write_text("{}", encoding="utf-8")
    result = {
        "refreshStatus": "current_for_frequency",
        "publishable": True,
        "failedSources": 5,
        "cacheCoverage": {"MSFT": {"current": True}},
    }
    monkeypatch.setattr(refresh_and_build, "ROOT", tmp_path)
    monkeypatch.setattr(
        refresh_and_build.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(result),
            stderr="",
        ),
    )

    row = refresh_and_build._run("sec_capex", ["python", "refresh.py"], required_output)

    assert row["status"] == "current_for_frequency"
    assert row["publishable"] is True
    assert row["qualityWarnings"] == 5


def test_deploy_validator_accepts_current_quarterly_capex():
    payload = {
        "generatedAt": "2026-07-13T08:00:00Z",
        "status": "ready",
        "publishable": True,
        "sources": [
            {"source": name, "status": "fresh", "publishable": True}
            for name in ("openrouter_usage", "foundry_signals", "openrouter_active_prices")
        ]
        + [
            {
                "source": "sec_capex",
                "status": "current_for_frequency",
                "publishable": True,
                "cacheCoverage": {"MSFT": {"current": True}},
            },
            {"source": "gpu_orderbook", "status": "fresh", "publishable": True},
            {"source": "reference_indices", "status": "fresh", "publishable": True},
            {"source": "neocloud_provider_prices", "status": "fresh", "publishable": True},
            {"source": "epoch_supply", "status": "fresh", "publishable": True},
            {"source": "fred_cost_anchors", "status": "fresh", "publishable": True},
            {"source": "gpu_markets_fixings", "status": "fresh", "publishable": True},
            {"source": "throughput_benchmarks", "status": "fresh", "publishable": True},
        ],
    }

    assert validate(payload, date(2026, 7, 13)) == []


def test_deploy_validator_rejects_false_freshness():
    payload = {
        "generatedAt": "2026-07-13T08:00:00Z",
        "status": "ready",
        "publishable": True,
        "sources": [
            {"source": name, "status": "fresh", "publishable": True}
            for name in ("openrouter_usage", "foundry_signals", "openrouter_active_prices")
        ]
        + [
            {
                "source": "sec_capex",
                "status": "current_for_frequency",
                "publishable": True,
                "cacheCoverage": {"MSFT": {"current": False}},
            },
            {"source": "gpu_orderbook", "status": "fresh", "publishable": True},
            {"source": "reference_indices", "status": "fresh", "publishable": True},
            {"source": "neocloud_provider_prices", "status": "fresh", "publishable": True},
            {"source": "epoch_supply", "status": "fresh", "publishable": True},
            {"source": "fred_cost_anchors", "status": "fresh", "publishable": True},
            {"source": "gpu_markets_fixings", "status": "fresh", "publishable": True},
            {"source": "throughput_benchmarks", "status": "fresh", "publishable": True},
        ],
    }

    assert "sec_capex 缓存覆盖不完整或已过期" in validate(payload, date(2026, 7, 13))
