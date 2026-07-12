import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from dashboard_v2 import get_first_view_summary, get_gpu_price_trend, get_public_proxy_history, load_dashboard_data  # noqa: E402
from production_store import (  # noqa: E402
    CapexActualObservation,
    GpuPriceObservation,
    MarketFactObservation,
    OfficialEventObservation,
    PublicProxyPriceObservation,
)
from tracker_v2 import Database  # noqa: E402


def _base_provenance(
    *,
    source_id="runpod-pricing",
    source_url="https://www.runpod.io/pricing",
    snapshot_path="tracker_snapshots/test/source.html",
    source_type="public_pricing_page",
    collection_method="html_parse",
    observed_at="2026-07-05T00:00:00Z",
    fetched_at=None,
):
    fetched_at = fetched_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "run_id": "dashboard-test",
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": snapshot_path,
        "source_type": source_type,
        "collection_method": collection_method,
        "observed_at": observed_at,
        "fetched_at": fetched_at,
        "raw_payload_hash": "sha256:" + ("d" * 64),
        "is_production_eligible": True,
        "confidence": 0.95,
        "error_code": None,
    }


def _gpu(
    provider,
    model,
    variant,
    price,
    source_type="public_pricing_page",
    date="2026-07-05",
    source_url_suffix=None,
):
    source_url_suffix = source_url_suffix or variant
    return GpuPriceObservation(
        date=date,
        provider=provider,
        gpu_model=model,
        gpu_variant=variant,
        billing_type="on-demand",
        commitment="per-hour",
        gpu_count=1,
        region="global_public_page",
        price_per_gpu_hour=price,
        currency="USD",
        availability_observed=True,
        **_base_provenance(
            source_id=f"{provider}-{model}",
            source_url=f"https://example.com/{provider}/{model}/{source_url_suffix}",
            snapshot_path=f"tracker_snapshots/test/{provider}-{model}-{source_url_suffix}.html",
            source_type=source_type,
            observed_at=f"{date}T00:00:00Z",
        ),
    )


def _capex(ticker, company, period_end, fiscal_period, value):
    return CapexActualObservation(
        ticker=ticker,
        company=company,
        period_start="2026-01-01",
        period_end=period_end,
        fiscal_period=fiscal_period,
        fiscal_year=2026,
        xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        accession_no=f"{ticker}-2026",
        capex_value=value,
        unit="USD_B",
        filed_at="2026-04-30",
        form_type="10-Q",
        **_base_provenance(
            source_id=f"sec-{ticker}",
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/{ticker}.json",
            snapshot_path=f"tracker_snapshots/test/sec-{ticker}.json",
            source_type="official",
            collection_method="sec_companyfacts_api",
            observed_at=f"{period_end}T00:00:00Z",
        ),
    )


def _event(ticker):
    return OfficialEventObservation(
        ticker=ticker,
        announcement_date="2026-07-01",
        event_type="capacity_comment",
        metric="management_capacity_comment",
        value=1.0,
        unit="evidence_flag",
        description=f"{ticker} official capacity comment.",
        fiscal_period="FY2026",
        **_base_provenance(
            source_id=f"official-{ticker}",
            source_url=f"https://investors.example.com/{ticker}/event",
            snapshot_path=f"tracker_snapshots/test/{ticker}-event.html",
            source_type="official",
            collection_method="manual_sourcebacked_yaml",
            observed_at="2026-07-01T00:00:00Z",
        ),
    )


def _proxy(
    gpu_model,
    metric,
    value,
    date="2026-07-05",
    source_url_suffix=None,
):
    source_url_suffix = source_url_suffix or gpu_model.lower()
    provenance = _base_provenance(
        source_id=f"computeprices-{gpu_model}",
        source_url=f"https://computeprices.example.com/gpus/{source_url_suffix}",
        snapshot_path=f"tracker_snapshots/test/computeprices-{source_url_suffix}.html",
        source_type="aggregator",
        collection_method="html_parse",
        observed_at=f"{date}T00:00:00Z",
    )
    provenance["confidence"] = 0.65
    return PublicProxyPriceObservation(
        date=date,
        provider="ComputePrices",
        proxy_name="public_gpu_price_proxy",
        metric=metric,
        value=value,
        unit="rows" if metric.endswith("_count_proxy") else "USD_per_gpu_hour",
        gpu_model=gpu_model,
        region="aggregator_rows",
        **provenance,
    )


def _market_fact(entity, metric, value, date="2026-07-06"):
    return MarketFactObservation(
        date=date,
        track="gpu_market_trend",
        entity=entity,
        sub_entity="global_public_market",
        metric=metric,
        value=value,
        unit="percent",
        dimension="gpusio_90d_window",
        vendor="GPUs.io",
        source_name="GPUs.io trends",
        notes="test trend row",
        **_base_provenance(
            source_id=f"gpusio-{entity}-{metric}",
            source_url="https://gpus.io/en/trends",
            snapshot_path=f"tracker_snapshots/test/gpusio-{entity}-{metric}.txt",
            source_type="aggregator",
            collection_method="browser_rendered_text",
            observed_at=f"{date}T00:00:00Z",
        ),
    )


def _market_fact_row(track, entity, metric, value, *, sub_entity="", dimension="", vendor="test", unit="", date="2026-07-06"):
    return MarketFactObservation(
        date=date,
        track=track,
        entity=entity,
        sub_entity=sub_entity or entity,
        metric=metric,
        value=value,
        unit=unit,
        dimension=dimension,
        vendor=vendor,
        source_name=f"{vendor} source",
        notes="test market fact row",
        **_base_provenance(
            source_id=f"{track}-{entity}-{metric}-{sub_entity}",
            source_url=f"https://example.com/{track}/{entity}/{metric}",
            snapshot_path=f"tracker_snapshots/test/{track}-{entity}-{metric}.json",
            source_type="aggregator",
            collection_method="json_api",
            observed_at=f"{date}T00:00:00Z",
        ),
    )


def _insert_complete_production_sample(db):
    db.insert_production_gpu_prices(
        [
            _gpu("RunPod", "H100", "PCIe", 2.89),
            _gpu("Lambda", "H100", "SXM", 3.99),
            _gpu("ComputePrices", "H100", "SXM", 1.89, source_type="aggregator"),
        ]
    )
    db.insert_production_capex_actuals(
        [
            _capex("MSFT", "Microsoft", "2026-03-31", "FY2026 Q3", 30.876),
            _capex("AMZN", "Amazon", "2026-03-31", "FY2026 Q1", 44.203),
            _capex("GOOGL", "Alphabet", "2026-03-31", "FY2026 Q1", 35.674),
            _capex("META", "Meta", "2026-03-31", "FY2026 Q1", 18.997),
            _capex("ORCL", "Oracle", "2026-05-31", "FY2026", 55.663),
        ]
    )
    db.insert_production_official_events([_event(ticker) for ticker in ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]])
    db.insert_production_public_proxy_prices(
        [
            _proxy("H100", "computeprices_row_count_proxy", 3.0, date="2026-07-04"),
            _proxy("H100", "computeprices_row_min_price_per_gpu_hour_proxy", 1.0, date="2026-07-04"),
            _proxy("H100", "computeprices_row_median_price_per_gpu_hour_proxy", 2.0, date="2026-07-04"),
            _proxy("H100", "computeprices_row_count_proxy", 4.0, date="2026-07-05"),
            _proxy("H100", "computeprices_row_min_price_per_gpu_hour_proxy", 1.2, date="2026-07-05"),
            _proxy("H100", "computeprices_row_median_price_per_gpu_hour_proxy", 2.4, date="2026-07-05"),
        ]
    )


def test_first_view_market_regime_surfaces_gpusio_generation_split(tmp_path):
    db_path = tmp_path / "market_regime.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)
    db.insert_production_market_facts(
        [
            _market_fact("NVIDIA A100 80GB", "price_delta_90d_pct", -36.9),
            _market_fact("NVIDIA H200", "price_delta_90d_pct", 8.1),
            _market_fact("NVIDIA B200", "price_delta_90d_pct", 7.1),
        ]
    )

    data = load_dashboard_data(str(db_path))
    explanation = data["tables"]["market_facts"]

    assert len(explanation) == 3
    from dashboard_v2 import _decision_explanation, _market_regime_summary  # noqa: PLC0415

    regime = _market_regime_summary(data["tables"]["market_facts"])
    assert regime["label"] == "代际分化"
    assert "A100 80GB 90d -36.9%" in regime["evidence"]
    assert "H200 90d 8.1%" in regime["evidence"]
    assert "B200 90d 7.1%" in regime["evidence"]
    assert "代际分化 / No Signal" in _decision_explanation(data)


def test_single_page_trend_helpers_surface_time_series_and_capex_disclosure(tmp_path):
    db_path = tmp_path / "single_page_trends.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)
    db.insert_production_market_facts(
        [
            _market_fact_row(
                "token_price",
                "GPT-5",
                "output_price_per_1m_tokens",
                15.0,
                sub_entity="openrouter-2026-06-23",
                vendor="OpenRouter",
                unit="USD/1M tokens",
                date="2026-06-23",
            ),
            _market_fact_row(
                "token_price",
                "GPT-5",
                "output_price_per_1m_tokens",
                12.5,
                sub_entity="openrouter-2026-07-06",
                vendor="OpenRouter",
                unit="USD/1M tokens",
                date="2026-07-06",
            ),
            _market_fact_row(
                "gpu_rental_index",
                "H100",
                "median_price_per_gpu_hour",
                2.75,
                sub_entity="AIMultiple H100",
                dimension="aimultiple_monthly_index_text",
                vendor="AIMultiple",
                unit="USD/GPU hr",
                date="2026-07-06",
            ),
            _market_fact_row(
                "gpu_rental_index",
                "H100",
                "aggregate_low_price_per_gpu_hour",
                1.25,
                sub_entity="GetDeploying H100",
                dimension="getdeploying_gpu_page",
                vendor="GetDeploying",
                unit="USD/GPU hr",
                date="2026-07-06",
            ),
        ]
    )

    data = load_dashboard_data(str(db_path))
    from dashboard_v2 import _gpu_rental_index_figure, _latest_capex_actual_table, _token_output_trend_frame  # noqa: PLC0415

    token_trend = _token_output_trend_frame(data["tables"]["market_facts"])
    assert token_trend["date"].nunique() == 2
    assert token_trend["price"].tolist() == [15.0, 12.5]
    fig, caption = _gpu_rental_index_figure(data["tables"]["market_facts"])
    assert fig is not None
    assert "AIMultiple / GetDeploying index" in caption

    capex_table = _latest_capex_actual_table(data["tables"]["capex_actuals"], data["tables"]["official_events"])
    assert set(["MSFT", "AMZN", "GOOGL", "META", "ORCL"]).issubset(set(capex_table["Ticker"]))
    assert "Alibaba Cloud" in set(capex_table["公司"])
    assert "未披露官方 CAPEX" in set(capex_table["最新 CAPEX"])


def test_official_signal_summary_surfaces_capex_rpo_layer():
    from dashboard_v2 import _official_signal_summary  # noqa: PLC0415

    summary = _official_signal_summary(
        pd.DataFrame(
            [
                {"ticker": "META", "metric": "fy2026_capex_guidance_low", "value": 125},
                {"ticker": "META", "metric": "fy2026_capex_guidance_high", "value": 145},
                {"ticker": "META", "metric": "fy2026_capex_guidance_previous_low", "value": 115},
                {"ticker": "META", "metric": "fy2026_capex_guidance_previous_high", "value": 135},
                {"ticker": "GOOGL", "metric": "cloud_backlog", "value": 460},
                {"ticker": "ORCL", "metric": "remaining_performance_obligations", "value": 638},
                {"ticker": "AMZN", "metric": "ttm_capex_increase_reflects_ai_investment", "value": 59.3},
                {"ticker": "MSFT", "metric": "customer_demand_exceeds_supply", "value": 1},
            ]
        )
    )

    assert summary["coverage"] == "5/5 hyperscalers"
    assert "META capex 125B-145B vs prior 115B-135B" in summary["evidence"]
    assert "GOOGL Cloud backlog >460B" in summary["evidence"]
    assert "ORCL RPO 638B" in summary["evidence"]
    assert "AMZN TTM PPE increase 59.3B tied to AI" in summary["evidence"]
    assert "不支持把旧卡降价直接解释成云厂商 CAPEX 下修" in summary["implication"]


def test_model_value_summary_uses_high_quality_value_leader():
    from dashboard_v2 import _model_value_summary  # noqa: PLC0415

    rows = []
    for entity, vendor, quality, output_price in [
        ("openai/gpt-5.5", "OpenAI", 100, 30),
        ("xiaomi/mimo-v2.5", "Xiaomi", 81, 0.28),
        ("cheap/low-quality", "Cheap", 50, 0.01),
    ]:
        rows.extend(
            [
                {
                    "track": "model_value_score",
                    "entity": entity,
                    "vendor": vendor,
                    "sub_entity": entity,
                    "metric": "quality_score",
                    "value": quality,
                },
                {
                    "track": "model_value_score",
                    "entity": entity,
                    "vendor": vendor,
                    "sub_entity": entity,
                    "metric": "output_price_per_1m_tokens",
                    "value": output_price,
                },
                {
                    "track": "model_value_score",
                    "entity": entity,
                    "vendor": vendor,
                    "sub_entity": entity,
                    "metric": "value_score_per_output_dollar",
                    "value": quality / output_price,
                },
            ]
        )

    summary = _model_value_summary(pd.DataFrame(rows))

    assert summary["models"] == 3
    assert summary["top_value_model"] == "xiaomi/mimo-v2.5"
    assert summary["top_value_score"] == pytest.approx(289.2857142857)
    assert summary["top_quality_model"] == "openai/gpt-5.5"
    assert "CostGoat high-quality value leader" in summary["evidence"]


def test_token_change_table_uses_discrete_model_vendor_history():
    from dashboard_v2 import _render_token_change_visual, _token_change_table  # noqa: PLC0415

    facts = pd.DataFrame(
        [
            {
                "date": "2026-06-23",
                "track": "token_price",
                "entity": "GPT-5",
                "vendor": "OpenAI",
                "metric": "output_price_per_1m_tokens",
                "value": 15.0,
                "source_name": "OpenRouter",
                "source_type": "aggregator",
            },
            {
                "date": "2026-07-06",
                "track": "token_price",
                "entity": "GPT-5",
                "vendor": "OpenAI",
                "metric": "output_price_per_1m_tokens",
                "value": 12.5,
                "source_name": "OpenRouter",
                "source_type": "aggregator",
            },
            {
                "date": "2026-06-13",
                "track": "token_price",
                "entity": "Claude 3.5 Sonnet",
                "vendor": "Anthropic",
                "metric": "output_price_per_1m_tokens",
                "value": 11.25,
                "source_name": "ComputePrices",
                "source_type": "aggregator",
            },
            {
                "date": "2026-07-06",
                "track": "token_price",
                "entity": "Claude 3.5 Sonnet",
                "vendor": "Anthropic",
                "metric": "output_price_per_1m_tokens",
                "value": 11.25,
                "source_name": "ComputePrices",
                "source_type": "aggregator",
            },
            {
                "date": "2026-07-06",
                "track": "token_price",
                "entity": "Single Snapshot",
                "vendor": "Test",
                "metric": "output_price_per_1m_tokens",
                "value": 1.0,
                "source_name": "Test",
                "source_type": "aggregator",
            },
            {
                "date": "2026-07-06",
                "track": "model_value_score",
                "entity": "GPT-5",
                "vendor": "OpenAI",
                "metric": "output_price_per_1m_tokens",
                "value": 30.0,
                "source_name": "CostGoat",
                "source_type": "aggregator",
            },
        ]
    )

    table = _token_change_table(facts)

    assert list(table["模型"]) == ["GPT-5", "Claude 3.5 Sonnet"]
    assert table.loc[0, "变化"] == pytest.approx(-16.6666667)
    assert table.loc[0, "快照数"] == 2
    assert "Single Snapshot" not in set(table["模型"])

    html = _render_token_change_visual(facts)
    assert "Token" not in html
    assert "GPT-5" in html
    assert "-16.7%" in html
    assert "离散快照" in html


def test_market_track_summary_keeps_gpuperhour_available_offers_separate():
    from dashboard_v2 import _market_track_summary  # noqa: PLC0415

    rows = [
        {
            "track": "gpu_available_offer",
            "entity": "H100",
            "metric": "available_price_per_gpu_hour",
            "value": 1.07,
            "dimension": "spot",
            "vendor": "Vast.ai",
            "fetched_at": "2026-07-06T12:34:09Z",
        },
        {
            "track": "gpu_available_offer",
            "entity": "H100",
            "metric": "available_price_per_gpu_hour",
            "value": 2.0,
            "dimension": "spot",
            "vendor": "Vast.ai",
            "fetched_at": "2026-07-06T12:34:09Z",
        },
        {
            "track": "gpu_available_offer",
            "entity": "H200",
            "metric": "available_price_per_gpu_hour",
            "value": 2.45,
            "dimension": "on_demand",
            "vendor": "Nebius",
            "fetched_at": "2026-07-06T12:34:09Z",
        },
        {
            "track": "gpu_available_offer",
            "entity": "H100",
            "metric": "available_offer_count",
            "value": 48,
            "dimension": "available_true",
            "vendor": "GPUPerHour",
            "fetched_at": "2026-07-06T12:34:09Z",
        },
        {
            "track": "gpu_rental",
            "entity": "H100",
            "metric": "price_per_gpu_hour",
            "value": 9.99,
            "dimension": "spot",
            "vendor": "ComputePrices",
            "fetched_at": "2026-07-06T12:34:09Z",
        },
    ]
    for row in rows:
        row.setdefault("sub_entity", "")
        row.setdefault("source_name", "")
        row.setdefault("source_url", "")
        row.setdefault("notes", "")

    summary = _market_track_summary(pd.DataFrame(rows))

    assert summary["gpu_available_offer_rows"] == 3
    assert summary["gpu_available_offer_entities"] == 2
    assert summary["h100_available_min"] == pytest.approx(1.07)
    assert summary["h200_available_min"] == pytest.approx(2.45)
    assert summary["h100_available_count"] == 48
    assert summary["h100_spot_median"] == pytest.approx(9.99)


def test_core_evidence_snapshot_keeps_homepage_decision_focused(tmp_path):
    db_path = tmp_path / "core_evidence.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)
    db.insert_production_market_facts(
        [
            _market_fact("NVIDIA A100 80GB", "price_delta_90d_pct", -36.9),
            _market_fact("NVIDIA H200", "price_delta_90d_pct", 8.1),
            _market_fact("NVIDIA B200", "price_delta_90d_pct", 7.1),
            _market_fact_row("gpu_available_offer", "H100", "available_price_per_gpu_hour", 1.07, dimension="spot", vendor="GPUPerHour", unit="USD/GPU hr"),
            _market_fact_row("gpu_available_offer", "H100", "available_offer_count", 48, dimension="available_true", vendor="GPUPerHour", unit="offers"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "quality_score", 81, vendor="CostGoat", unit="score"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "output_price_per_1m_tokens", 0.28, vendor="CostGoat", unit="USD/1M tokens"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "value_score_per_output_dollar", 289.3, vendor="CostGoat", unit="score/USD"),
        ]
    )

    data = load_dashboard_data(str(db_path))
    from dashboard_v2 import _core_evidence_snapshot, _decision_headline  # noqa: PLC0415

    snapshot = _core_evidence_snapshot(data)

    assert "代际分化 / No Signal" in _decision_headline(data)
    assert snapshot["regime"]["label"] == "代际分化"
    assert snapshot["official_summary"]["coverage"] == "5/5 hyperscalers"
    assert snapshot["summary"]["h100_available_min"] == pytest.approx(1.07)
    assert snapshot["summary"]["h100_available_count"] == 48
    assert snapshot["model_value_summary"]["top_value_model"] == "xiaomi/mimo-v2.5"
    assert list(snapshot["evidence_table"]["证据层"])[:3] == ["价格层", "官方层", "应用/API层"]


def test_signal_readiness_exposes_usable_layers_and_hard_gaps(tmp_path):
    db_path = tmp_path / "signal_readiness.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)
    db.insert_production_market_facts(
        [
            _market_fact("NVIDIA A100 80GB", "price_delta_90d_pct", -36.9),
            _market_fact("NVIDIA H200", "price_delta_90d_pct", 8.1),
            _market_fact("NVIDIA B200", "price_delta_90d_pct", 7.1),
            _market_fact_row("gpu_available_offer", "H100", "available_price_per_gpu_hour", 1.07, dimension="spot", vendor="GPUPerHour", unit="USD/GPU hr"),
            _market_fact_row("gpu_available_offer", "H100", "available_offer_count", 48, dimension="available_true", vendor="GPUPerHour", unit="offers"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "quality_score", 81, vendor="CostGoat", unit="score"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "output_price_per_1m_tokens", 0.28, vendor="CostGoat", unit="USD/1M tokens"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "value_score_per_output_dollar", 289.3, vendor="CostGoat", unit="score/USD"),
            _market_fact_row("token_price", "GPT-5", "output_price_per_1m_tokens", 15.0, vendor="OpenAI", unit="USD/1M tokens", date="2026-06-23"),
            _market_fact_row("token_price", "GPT-5", "output_price_per_1m_tokens", 12.5, vendor="OpenAI", unit="USD/1M tokens", date="2026-07-06"),
            _market_fact_row("app_commercialization", "Anthropic", "business_adoption_share", 34.4, vendor="Ramp", unit="percent"),
            _market_fact_row("multimodal_generation_cost", "Seedance 2.0", "input_price_per_1m_tokens", 7.7, vendor="BytePlus", unit="USD/1M tokens"),
        ]
    )

    data = load_dashboard_data(str(db_path))
    from dashboard_v2 import _signal_readiness_table  # noqa: PLC0415

    readiness = _signal_readiness_table(data).set_index("信号")

    assert readiness.loc["GPU租赁价格", "状态"] == "可观察"
    assert "不能推出全市场算力过剩" in readiness.loc["GPU租赁价格", "决策读法"]
    assert readiness.loc["云厂商CAPEX/RPO", "状态"] == "反证层已接入"
    assert readiness.loc["模型/API成本", "状态"] == "离散趋势可观察"
    assert "离散快照" in readiness.loc["模型/API成本", "仍缺什么"]
    assert readiness.loc["应用商业化", "状态"] == "弱信号"
    assert readiness.loc["授权指数/硬件成交", "状态"] == "缺口"
    assert "ORNN/OCPI" in readiness.loc["授权指数/硬件成交", "仍缺什么"]


def test_inflection_watchlist_keeps_current_state_as_observation_not_trigger(tmp_path):
    db_path = tmp_path / "inflection_watchlist.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)
    db.insert_production_market_facts(
        [
            _market_fact("NVIDIA A100 80GB", "price_delta_90d_pct", -36.9),
            _market_fact("NVIDIA H200", "price_delta_90d_pct", 8.1),
            _market_fact("NVIDIA B200", "price_delta_90d_pct", 7.2),
            _market_fact_row("gpu_available_offer", "H100", "available_price_per_gpu_hour", 1.07, dimension="spot", vendor="GPUPerHour", unit="USD/GPU hr"),
            _market_fact_row("gpu_available_offer", "H100", "available_offer_count", 48, dimension="available_true", vendor="GPUPerHour", unit="offers"),
            _market_fact_row("cloud_instance_price", "H100", "instance_price_per_hour", 1.396, sub_entity="Standard_NC40ads_H100_v5", dimension="spot", vendor="Azure", unit="USD/VM hr"),
            _market_fact_row("cloud_instance_price", "H100", "instance_price_per_hour", 2.5318, sub_entity="p5.4xlarge", dimension="spot", vendor="AWS", unit="USD/VM hr"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "quality_score", 81, vendor="CostGoat", unit="score"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "output_price_per_1m_tokens", 0.28, vendor="CostGoat", unit="USD/1M tokens"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "value_score_per_output_dollar", 289.3, vendor="CostGoat", unit="score/USD"),
            _market_fact_row("app_commercialization", "Anthropic", "business_adoption_share", 34.4, vendor="Ramp", unit="percent"),
            _market_fact_row("app_commercialization", "OpenAI", "business_adoption_share", 32.3, vendor="Ramp", unit="percent"),
        ]
    )

    data = load_dashboard_data(str(db_path))
    from dashboard_v2 import _inflection_watchlist_table  # noqa: PLC0415

    watchlist = _inflection_watchlist_table(data).set_index("拐点")

    assert watchlist.loc["硬件链转负", "当前状态"] == "未触发"
    assert "H200/B200 90日价格同步转负" in watchlist.loc["硬件链转负", "触发条件"]
    assert watchlist.loc["云厂商由压制转受益", "当前状态"] == "反向约束"
    assert watchlist.loc["应用层价值接棒", "当前状态"] == "观察中"
    assert "优先寻找应用/API routing" in watchlist.loc["应用层价值接棒", "二级市场动作"]


def test_home_visuals_keep_real_price_and_orderbook_values(tmp_path):
    db_path = tmp_path / "home_visuals.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)
    db.insert_production_market_facts(
        [
            _market_fact("NVIDIA A100 80GB", "price_delta_90d_pct", -36.9),
            _market_fact("NVIDIA H200", "price_delta_90d_pct", 8.1),
            _market_fact("NVIDIA B200", "price_delta_90d_pct", 7.2),
            _market_fact_row("gpu_available_offer", "H100", "available_price_per_gpu_hour", 1.07, dimension="spot", vendor="GPUPerHour", unit="USD/GPU hr"),
            _market_fact_row("gpu_available_offer", "H100", "available_offer_count", 48, dimension="available_true", vendor="GPUPerHour", unit="offers"),
            _market_fact_row("cloud_instance_price", "H100", "instance_price_per_hour", 1.396, sub_entity="Standard_NC40ads_H100_v5", dimension="spot", vendor="Azure", unit="USD/VM hr"),
            _market_fact_row("cloud_instance_price", "H100", "instance_price_per_hour", 2.5318, sub_entity="p5.4xlarge", dimension="spot", vendor="AWS", unit="USD/VM hr"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "quality_score", 81, vendor="CostGoat", unit="score"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "output_price_per_1m_tokens", 0.28, vendor="CostGoat", unit="USD/1M tokens"),
            _market_fact_row("model_value_score", "xiaomi/mimo-v2.5", "value_score_per_output_dollar", 289.3, vendor="CostGoat", unit="score/USD"),
            _market_fact_row("app_commercialization", "Anthropic", "arr", 47, vendor="ARR.club", unit="USD_B_ARR"),
            _market_fact_row("app_commercialization", "OpenAI", "arr", 25, vendor="ARR.club", unit="USD_B_ARR"),
            _market_fact_row("app_commercialization", "Overall AI adoption", "business_adoption_share", 50.6, vendor="Ramp", unit="percent"),
            _market_fact_row("app_commercialization", "Anthropic", "business_adoption_share", 34.4, vendor="Ramp", unit="percent"),
            _market_fact_row("app_commercialization", "OpenAI", "business_adoption_share", 32.3, vendor="Ramp", unit="percent"),
        ]
    )

    data = load_dashboard_data(str(db_path))
    from dashboard_v2 import _core_evidence_snapshot, _render_home_commercialization_visual, _render_home_model_value_visual, _render_home_orderbook_visual, _render_home_price_visual  # noqa: PLC0415

    snapshot = _core_evidence_snapshot(data)
    price_html = _render_home_price_visual(snapshot)
    orderbook_html = _render_home_orderbook_visual(snapshot)
    model_html = _render_home_model_value_visual(data["tables"]["market_facts"])
    commercialization_html = _render_home_commercialization_visual(data["tables"]["market_facts"])

    assert "A100 80GB" in price_html
    assert "-36.9%" in price_html
    assert "B200" in price_html
    assert "7.2%" in price_html
    assert "H100" in orderbook_html
    assert "$1.07" in orderbook_html
    assert "Azure H100 spot" in orderbook_html
    assert "$1.40/VM hr" in orderbook_html
    assert "AWS H100 spot" in orderbook_html
    assert "$2.53/VM hr" in orderbook_html
    assert "xiaomi/mimo-v2.5" in model_html
    assert "289.3" in model_html
    assert "Overall AI adoption" in commercialization_html
    assert "50.6%" in commercialization_html
    assert "Anthropic $47.00B" in commercialization_html


def test_dashboard_empty_production_db_blocks_first_view(tmp_path):
    db_path = tmp_path / "empty.db"
    Database(str(db_path))

    summary = get_first_view_summary(str(db_path))

    assert summary["quality_gate"] == "FAIL"
    assert summary["decision_state"] == "Blocked"
    assert summary["production_counts"]["production_gpu_prices"] == 0
    assert "NO_PRODUCTION_DATA" in set(summary["missing_or_failed"]["reason_code"])
    assert summary["gpu_price_trend_rows"] == 0
    assert summary["gpu_price_trend"].empty
    assert get_gpu_price_trend(str(db_path)).empty
    assert get_public_proxy_history(str(db_path)).empty


def test_dashboard_seed_only_db_does_not_show_false_green(tmp_path):
    db_path = tmp_path / "seed_only.db"
    result = subprocess.run(
        [sys.executable, str(TRACKER_V2 / "tracker_v2.py"), "init", "--demo-seed", "--db", str(db_path)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr

    data = load_dashboard_data(str(db_path))
    summary = get_first_view_summary(str(db_path))

    assert summary["quality_gate"] == "FAIL"
    assert summary["decision_state"] == "Blocked"
    assert summary["production_counts"]["production_gpu_prices"] == 0
    assert data["legacy_counts"]["rows"].sum() > 0
    assert summary["gpu_price_trend_rows"] == 0
    assert data["gpu_price_trend"].empty
    assert data["public_proxy_history"].empty


def test_dashboard_source_backed_db_uses_production_tables_and_labels_sources(tmp_path):
    db_path = tmp_path / "production.db"
    db = Database(str(db_path))
    _insert_complete_production_sample(db)

    data = load_dashboard_data(str(db_path))
    summary = get_first_view_summary(str(db_path))
    coverage = data["source_coverage"]

    assert summary["quality_gate"] in {"PASS", "WARN"}
    assert summary["decision_state"] != "Blocked"
    assert summary["production_counts"]["production_gpu_prices"] == 3
    assert summary["public_proxy_history_rows"] == 2
    assert {"public_pricing_page", "aggregator"}.issubset(set(data["tables"]["gpu_prices"]["source_type"]))
    assert "GPU price" in set(coverage["layer"])
    assert "SEC CAPEX actual" in set(coverage["layer"])


def test_gpu_price_trend_uses_public_proxy_history_not_raw_quote_rows(tmp_path):
    db_path = tmp_path / "trend.db"
    db = Database(str(db_path))
    db.insert_production_gpu_prices(
        [
            _gpu("RunPod", "H100", "PCIe", 2.0, date="2026-07-04", source_url_suffix="runpod-pcie"),
            _gpu("Lambda", "H100", "SXM", 4.0, date="2026-07-04", source_url_suffix="lambda-sxm"),
            _gpu("CoreWeave", "H100", "SXM", 10.0, date="2026-07-04", source_url_suffix="coreweave-sxm"),
            _gpu("ComputeA", "H100", "SXM", 1.0, source_type="aggregator", date="2026-07-04"),
            _gpu("ComputeB", "H100", "SXM", 3.0, source_type="aggregator", date="2026-07-04"),
            _gpu("ComputeC", "H100", "SXM", 5.0, source_type="aggregator", date="2026-07-04"),
            _gpu("ComputeD", "H200", "SXM", 6.0, source_type="aggregator", date="2026-07-04"),
            _gpu("RunPod", "H100", "PCIe", 99.0, date="2026-07-05", source_url_suffix="runpod-next-day"),
        ]
    )
    db.insert_production_public_proxy_prices(
        [
            _proxy("H100", "computeprices_row_count_proxy", 3.0, date="2026-07-04", source_url_suffix="h100-0704"),
            _proxy("H100", "computeprices_row_min_price_per_gpu_hour_proxy", 1.0, date="2026-07-04", source_url_suffix="h100-0704"),
            _proxy("H100", "computeprices_row_median_price_per_gpu_hour_proxy", 3.0, date="2026-07-04", source_url_suffix="h100-0704"),
            _proxy("H100", "computeprices_row_count_proxy", 1.0, date="2026-07-05", source_url_suffix="h100-0705"),
            _proxy("H100", "computeprices_row_min_price_per_gpu_hour_proxy", 99.0, date="2026-07-05", source_url_suffix="h100-0705"),
            _proxy("H100", "computeprices_row_median_price_per_gpu_hour_proxy", 99.0, date="2026-07-05", source_url_suffix="h100-0705"),
            _proxy("H200", "computeprices_row_count_proxy", 4.0, date="2026-07-04", source_url_suffix="h200-0704"),
            _proxy("H200", "computeprices_row_min_price_per_gpu_hour_proxy", 6.0, date="2026-07-04", source_url_suffix="h200-0704"),
            _proxy("H200", "computeprices_row_median_price_per_gpu_hour_proxy", 7.0, date="2026-07-04", source_url_suffix="h200-0704"),
        ]
    )

    trend = load_dashboard_data(str(db_path))["gpu_price_trend"]

    assert list(trend.columns) == [
        "date",
        "gpu_model",
        "median_price_per_gpu_hour",
        "min_price_per_gpu_hour",
        "quote_count",
        "coverage_quality",
        "source_url",
        "snapshot_path",
    ]

    assert len(trend) == 3
    assert "source_type" not in trend.columns

    h100_0704 = trend[(trend["date"].astype(str) == "2026-07-04") & (trend["gpu_model"] == "H100")].iloc[0]
    assert h100_0704["quote_count"] == 3
    assert h100_0704["coverage_quality"] == "adequate"
    assert h100_0704["median_price_per_gpu_hour"] == 3.0

    h100_0705 = trend[(trend["date"].astype(str) == "2026-07-05") & (trend["gpu_model"] == "H100")].iloc[0]
    assert h100_0705["quote_count"] == 1
    assert h100_0705["coverage_quality"] == "thin"
    assert h100_0705["median_price_per_gpu_hour"] == 99.0
