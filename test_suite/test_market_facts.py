import sys
from pathlib import Path

import pytest

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from data_sources.market_facts import (  # noqa: E402
    BYTEPLUS_SEEDANCE_TOKEN_PRICES,
    SEEDANCE2_CREDIT_PRICES,
    _aws_gpu_family,
    _azure_billing_type,
    _canonical_model_name,
    _parse_aimultiple_gpu_index_text,
    _openrouter_price_to_1m,
    _parse_openrouter_model_rankings_chart,
    _parse_costgoat_models_from_next_data,
    _parse_getdeploying_aggregate_offer,
    _parse_gpumarkets_fixings_csv,
    _parse_gpuperhour_available_offers,
    _aggregate_gpuperhour_exact_configs,
    _parse_gpusio_trend_rows,
    _parse_money_to_usd_billion,
    _parse_runpod_gpu_types,
    _parse_vast_bundle_offers,
    _per_token_to_per_1m,
)
from production_store import MarketFactObservation  # noqa: E402
from tracker_v2 import Database, ProductionDataContractError  # noqa: E402


def _market_fact(source_type="aggregator"):
    return MarketFactObservation(
        date="2026-07-06",
        track="token_price",
        entity="OpenAI: GPT-5",
        sub_entity="OpenRouter",
        metric="output_price_per_1m_tokens",
        value=30.0,
        unit="USD/1M tokens",
        dimension="router_current",
        vendor="openai",
        source_name="OpenRouter Models API",
        notes="test row",
        run_id="market-facts-test",
        source_id="openrouter-models",
        source_url="https://openrouter.ai/api/v1/models",
        snapshot_path="tracker_snapshots/test/openrouter-models.json",
        source_type=source_type,
        collection_method="json_api",
        observed_at="2026-07-06T00:00:00Z",
        fetched_at="2026-07-06T00:01:00Z",
        raw_payload_hash="sha256:" + ("a" * 64),
        is_production_eligible=True,
        confidence=0.82,
        error_code=None,
    )


def test_market_fact_schema_accepts_source_backed_json_api(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))

    db.insert_production_market_facts([_market_fact()])

    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT track, entity, metric, value, unit, source_name
        FROM production_market_facts
        """
    ).fetchall()
    conn.close()

    assert rows == [("token_price", "OpenAI: GPT-5", "output_price_per_1m_tokens", 30.0, "USD/1M tokens", "OpenRouter Models API")]


def test_market_fact_rejects_seed_source_type(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))

    with pytest.raises(ProductionDataContractError):
        db.insert_production_market_facts([_market_fact(source_type="seed")])


def test_openrouter_prices_are_converted_from_per_token_to_per_1m_tokens():
    assert _openrouter_price_to_1m("0.00003") == 30.0
    assert _openrouter_price_to_1m("0") == 0.0
    assert _openrouter_price_to_1m(None) is None


def test_openrouter_model_rankings_chart_parser_keeps_weekly_model_token_rows():
    payload = {
        "data": {
            "cachedAt": 1783825744227,
            "data": [
                {
                    "x": "2026-07-06",
                    "ys": {
                        "anthropic/claude-sonnet": 1200,
                        "deepseek/deepseek-chat": 800,
                        "Others": 400,
                    },
                }
            ],
        }
    }

    observed_at, rows = _parse_openrouter_model_rankings_chart(payload)

    assert observed_at == "2026-07-12T03:09:04.227000Z"
    assert rows == [
        {"date": "2026-07-06", "model_slug": "anthropic/claude-sonnet", "tokens": 1200.0},
        {"date": "2026-07-06", "model_slug": "deepseek/deepseek-chat", "tokens": 800.0},
        {"date": "2026-07-06", "model_slug": "Others", "tokens": 400.0},
    ]


def test_catalog_model_names_and_prices_are_normalized_for_trends():
    assert _per_token_to_per_1m(0.00001) == 10.0
    assert _canonical_model_name("openrouter/openai/gpt-5") == "GPT-5"
    assert _canonical_model_name("gemini/gemini-2.5-flash") == "Gemini 2.5 Flash"
    assert _canonical_model_name("deepseek/deepseek-v4-pro") == "DeepSeek V4 Pro"


def test_costgoat_next_data_parser_extracts_quality_price_and_value_score():
    html = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"currentDateIso":"2026-07-06T00:58:38.656Z","models":[
{"id":"openai/gpt-5.5","name":"OpenAI: GPT-5.5","provider":"OpenAI","contextLength":1050000,"inputPrice":5,"outputPrice":30,"quality":100},
{"id":"minimax/minimax-m2.7","name":"MiniMax: M2.7","provider":"MiniMax","contextLength":205000,"inputPrice":0.18,"outputPrice":0.72,"quality":82}
]}}}
</script>
</body></html>
"""
    observed_at, rows = _parse_costgoat_models_from_next_data(html)

    assert observed_at == "2026-07-06T00:58:38.656Z"
    assert rows[0]["id"] == "openai/gpt-5.5"
    assert rows[0]["quality"] == 100.0
    assert rows[0]["value_score"] == pytest.approx(3.3333333333)
    assert rows[1]["value_score"] == pytest.approx(113.8888888889)


def test_getdeploying_aggregate_offer_parser_extracts_index_bounds():
    html = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
{"@type":"Product","name":"Nvidia H100 Cloud GPU","description":"test",
"offers":{"@type":"AggregateOffer","offerCount":"308","lowPrice":"0.34","highPrice":"14.90","priceCurrency":"USD","availability":"https://schema.org/InStock"}}
]}
</script></head><body></body></html>
"""
    parsed = _parse_getdeploying_aggregate_offer(html)

    assert parsed["name"] == "Nvidia H100 Cloud GPU"
    assert parsed["low"] == 0.34
    assert parsed["high"] == 14.90
    assert parsed["count"] == 308


def test_aimultiple_gpu_index_text_parser_extracts_median_ranges():
    text = """
H100 is listed by 46 providers. The cohort median is now around $2.99/GPU-hour, down from above $7 in early 2024.
H200’s range runs from $2.30 (FluidStack) to $13.78 (Microsoft Azure), with a cohort median around $4.00.
A100 holds a tight neocloud band around $1.79.
L40S has settled around $1.56 median, with AWS at $7.58 setting the ceiling.
RTX 4090 is the cheapest training-class card on the index at $0.52 median, with Salad at $0.18 and Beam at $1.61 bracketing the spread.
B200 median $6.11, range $3.44 (Vast.ai) to $16.11 (Google Cloud). B300 median $7.92, range $5.44 (Vast.ai) to $18.00 (Oracle Cloud).
MI300X median $2.72, range $1.99 (DigitalOcean) to $7.86 (Microsoft Azure). RTX 5090 median $0.66, range $0.27 (Salad) to $2.00 (Vast.ai).
"""
    rows = {row["gpu"]: row for row in _parse_aimultiple_gpu_index_text(text)}

    assert rows["H100"]["median"] == 2.99
    assert rows["H100"]["count"] == 46
    assert rows["H200"]["low"] == 2.30
    assert rows["B200"]["high"] == 16.11
    assert rows["RTX 5090"]["median"] == 0.66


def test_gpuperhour_parser_keeps_only_available_target_gpu_offers():
    payload = {
        "lastUpdated": "2026-07-06T12:34:09.613Z",
        "pagination": {"total": 3},
        "data": [
            {
                "id": "available-h200",
                "provider": "Nebius",
                "providerUrl": "https://example.com/nebius",
                "gpu": {"slug": "h200-sxm", "name": "NVIDIA H200 SXM", "vramGB": 141},
                "region": "Europe",
                "regionInfo": {"countryName": "Netherlands", "continent": "Europe"},
                "priceHourly": 2.45,
                "pricePerGpu": 2.45,
                "currency": "USD",
                "isAvailable": True,
                "gpuCount": 1,
                "pricingType": "on-demand",
                "deploymentType": "virtual",
                "securityTier": "secure",
                "lastSeen": "2026-07-06T12:30:56Z",
                "specs": {"vcpuCount": 16, "ramGB": 200, "diskGB": 1000, "inetDownMbps": 1000, "inetUpMbps": 800},
            },
            {
                "id": "wrong-family",
                "provider": "Vultr",
                "gpu": {"slug": "gh200", "name": "NVIDIA GH200 Grace Hopper", "vramGB": 96},
                "pricePerGpu": 1.99,
                "currency": "USD",
                "isAvailable": True,
                "gpuCount": 1,
                "pricingType": "on-demand",
                "specs": {},
            },
            {
                "id": "unavailable-h200",
                "provider": "RunPod",
                "gpu": {"slug": "h200-sxm", "name": "NVIDIA H200 SXM", "vramGB": 141},
                "pricePerGpu": 1.0,
                "currency": "USD",
                "isAvailable": False,
                "gpuCount": 1,
                "pricingType": "spot",
                "specs": {},
            },
        ],
    }

    observed_at, total, rows = _parse_gpuperhour_available_offers(payload, expected_entity="H200")

    assert observed_at == "2026-07-06T12:34:09.613Z"
    assert total == 3
    assert len(rows) == 1
    assert rows[0]["id"] == "available-h200"
    assert rows[0]["provider"] == "Nebius"
    assert rows[0]["price_per_gpu"] == 2.45
    assert rows[0]["pricing_type"] == "on_demand"


def test_gpuperhour_exact_config_aggregation_keeps_identity_and_daily_distribution():
    offers = [
        {
            "id": "offer-a",
            "entity": "H100",
            "gpu_name": "NVIDIA H100 SXM 80GB",
            "gpu_slug": "h100-sxm-80gb",
            "provider": "Provider A",
            "region": "US-East",
            "price_per_gpu": 2.4,
            "gpu_count": 1,
            "pricing_type": "on_demand",
            "deployment_type": "virtual",
            "security_tier": "secure",
        },
        {
            "id": "offer-b",
            "entity": "H100",
            "gpu_name": "NVIDIA H100 SXM 80GB",
            "gpu_slug": "h100-sxm-80gb",
            "provider": "Provider A",
            "region": "US-East",
            "price_per_gpu": 2.6,
            "gpu_count": 1,
            "pricing_type": "on_demand",
            "deployment_type": "virtual",
            "security_tier": "secure",
        },
        {
            "id": "offer-c",
            "entity": "H100",
            "gpu_name": "NVIDIA H100 SXM 80GB",
            "gpu_slug": "h100-sxm-80gb",
            "provider": "Provider A",
            "region": "US-West",
            "price_per_gpu": 2.8,
            "gpu_count": 1,
            "pricing_type": "on_demand",
            "deployment_type": "virtual",
            "security_tier": "secure",
        },
    ]

    configs = _aggregate_gpuperhour_exact_configs(offers)

    assert len(configs) == 2
    east = next(row for row in configs if "region=us-east" in row["dimension"])
    assert east["sub_entity"] == "Provider A"
    assert east["median_price"] == 2.5
    assert east["min_price"] == 2.4
    assert east["max_price"] == 2.6
    assert east["offer_count"] == 2
    assert east["dimension"] == (
        "billing=on_demand|variant=h100-sxm-80gb|region=us-east|gpu_count=1|"
        "security=secure|deployment=virtual"
    )


def test_gpumarkets_fixings_parser_extracts_price_deltas_and_frequency_fields():
    csv_text = """series_id,tier,chip,vram,tenor,price_usd_per_gpu_hr,delta_1d_pct,delta_7d_pct,delta_30d_pct,observations,venues_eligible,venues_total,price_cw_usd_per_gpu_hr,delta_cw_vs_fix_pct,venue_tier_breakdown,cw_suppressed_reason,fix_date_utc,fix_time_utc
GPUM.H100.SXM.SPOT,training,NVIDIA H100 SXM,80GB,Spot,2.1432,-0.78,-0.99,-7.72,2847,9,12,2.1687,1.19,2 T1 · 4 T2 · 1 T3,,2026-04-18,00:30
"""
    rows = _parse_gpumarkets_fixings_csv(csv_text)

    assert len(rows) == 1
    assert rows[0]["series_id"] == "GPUM.H100.SXM.SPOT"
    assert rows[0]["gpu"] == "H100"
    assert rows[0]["tenor"] == "spot"
    assert rows[0]["price"] == 2.1432
    assert rows[0]["delta_30d"] == -7.72
    assert rows[0]["observations"] == 2847
    assert rows[0]["observed_at"] == "2026-04-18T00:30:00Z"


def test_vast_bundle_parser_keeps_verified_available_target_gpu_and_normalizes_per_gpu_price():
    payload = {
        "offers": [
            {
                "id": 40971294,
                "gpu_name": "H100 SXM",
                "num_gpus": 2,
                "dph_total": 4.0,
                "min_bid": 3.0,
                "dlperf": 500.0,
                "dlperf_per_dphtotal": 125.0,
                "reliability": 0.991,
                "geolocation": "California, US",
                "machine_id": 123,
                "host_id": 456,
                "rentable": True,
                "rented": False,
                "verification": "verified",
            },
            {
                "id": 1,
                "gpu_name": "RTX 3090",
                "num_gpus": 1,
                "dph_total": 0.3,
                "rentable": True,
                "rented": False,
                "verification": "verified",
            },
        ]
    }

    rows = _parse_vast_bundle_offers(payload)

    assert len(rows) == 1
    assert rows[0]["entity"] == "H100"
    assert rows[0]["price_per_gpu"] == 2.0
    assert rows[0]["min_bid_per_gpu"] == 1.5
    assert rows[0]["reliability"] == 0.991


def test_runpod_gpu_types_parser_extracts_price_and_capacity_fields():
    payload = {
        "data": {
            "gpuTypes": [
                {
                    "id": "NVIDIA H100 80GB HBM3",
                    "displayName": "H100 SXM",
                    "memoryInGb": 80,
                    "secureCloud": True,
                    "communityCloud": True,
                    "securePrice": 2.69,
                    "communityPrice": 2.39,
                    "secureSpotPrice": 2.49,
                    "communitySpotPrice": 2.19,
                    "oneWeekPrice": None,
                    "oneMonthPrice": None,
                    "maxGpuCount": 8,
                    "maxGpuCountCommunityCloud": 4,
                    "maxGpuCountSecureCloud": 8,
                    "lowestPrice": {
                        "minimumBidPrice": 2.19,
                        "uninterruptablePrice": 2.39,
                        "stockStatus": "Medium",
                    },
                }
            ]
        }
    }

    rows = _parse_runpod_gpu_types(payload)

    assert len(rows) == 1
    assert rows[0]["entity"] == "H100"
    assert rows[0]["display_name"] == "H100 SXM"
    assert rows[0]["secure_price"] == 2.69
    assert rows[0]["community_spot_price"] == 2.19
    assert rows[0]["max_gpu_count"] == 8
    assert rows[0]["lowest_stock_status"] == "Medium"


def test_runpod_gpu_types_parser_quarantines_mig_and_unavailable_prices():
    payload = {
        "data": {
            "gpuTypes": [
                {
                    "id": "NVIDIA B300 MIG 1g.24gb",
                    "displayName": "B300 MIG slice",
                    "secureCloud": True,
                    "communityCloud": True,
                    "securePrice": 0.42,
                    "communityPrice": 0.35,
                },
                {
                    "id": "NVIDIA H100 80GB HBM3",
                    "displayName": "H100 SXM",
                    "secureCloud": True,
                    "communityCloud": False,
                    "securePrice": 2.69,
                    "communityPrice": 0,
                    "secureSpotPrice": 0,
                    "communitySpotPrice": 1.99,
                    "lowestPrice": {
                        "minimumBidPrice": 0,
                        "uninterruptablePrice": 2.69,
                    },
                },
            ]
        }
    }
    diagnostics = {}

    rows = _parse_runpod_gpu_types(payload, diagnostics=diagnostics)

    assert len(rows) == 1
    assert rows[0]["entity"] == "H100"
    assert rows[0]["secure_price"] == 2.69
    assert rows[0]["community_price"] is None
    assert rows[0]["secure_spot_price"] is None
    assert rows[0]["community_spot_price"] is None
    assert rows[0]["lowest_minimum_bid_price"] is None
    assert diagnostics == {
        "rejected_mig": 1,
        "suppressed_nonpositive_prices": 3,
        "suppressed_unavailable_tier_prices": 2,
    }


def test_arr_club_money_text_normalizes_to_usd_billions():
    assert _parse_money_to_usd_billion("$47B") == 47.0
    assert _parse_money_to_usd_billion("$500M") == 0.5
    assert _parse_money_to_usd_billion("$750K") == 0.00075


def test_azure_billing_type_detects_spot_low_priority_and_on_demand():
    assert _azure_billing_type({"skuName": "NC40adsH100v5 Spot"}) == "spot"
    assert _azure_billing_type({"skuName": "Standard_NC48ads_A100_v4 Low Priority"}) == "low_priority"
    assert _azure_billing_type({"skuName": "ND96isrH100v5"}) == "on_demand"


def test_aws_gpu_family_maps_common_gpu_instance_families():
    assert _aws_gpu_family("p5.48xlarge") == "H100"
    assert _aws_gpu_family("p5e.48xlarge") == "H200"
    assert _aws_gpu_family("p4d.24xlarge") == "A100"
    assert _aws_gpu_family("g6e.12xlarge") == "L40S"


def test_seedance_pricing_constants_keep_official_tokens_separate_from_wrapper_credits():
    official = {(resolution, mode): value for resolution, mode, value, *_ in BYTEPLUS_SEEDANCE_TOKEN_PRICES}
    wrapper = {(model, resolution, mode): (credits_per_sec, five_second_credits) for model, resolution, mode, credits_per_sec, five_second_credits in SEEDANCE2_CREDIT_PRICES}

    assert official[("1080p", "input_without_video")] == 7.7
    assert official[("4K", "input_with_video")] == 2.4
    assert wrapper[("Seedance 2.0", "720p", "without_video_input")] == (12, 60)
    assert wrapper[("Seedance 2.0 Mini", "480p", "with_video_input")] == (2, 16)


def test_gpusio_trend_parser_extracts_30d_90d_and_range():
    text = """
All movers
GPU
NOW
30D
90D
90D TREND
RECOMMENDATION
NVIDIA A100 80GB
80GB
·
10 providers
·
Datacenter
$1.13/GPU/hr
+5.6%
-36.9%
$1.00 – $1.79
Buying opportunity
View offers
NVIDIA H200
141GB
·
6 providers
·
Datacenter
$4.00/GPU/hr
+6.5%
+8.1%
$3.44 – $4.32
Trending up
View offers
"""
    rows = {row["gpu"]: row for row in _parse_gpusio_trend_rows(text)}

    assert rows["NVIDIA A100 80GB"]["current_price"] == 1.13
    assert rows["NVIDIA A100 80GB"]["delta_30d_pct"] == 5.6
    assert rows["NVIDIA A100 80GB"]["delta_90d_pct"] == -36.9
    assert rows["NVIDIA A100 80GB"]["range_low"] == 1.0
    assert rows["NVIDIA A100 80GB"]["range_high"] == 1.79
    assert rows["NVIDIA H200"]["recommendation"] == "Trending up"
