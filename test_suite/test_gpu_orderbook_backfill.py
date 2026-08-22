import sys
from pathlib import Path

import pytest


TRACKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_ROOT))

from scripts.backfill_gpu_orderbook import (  # noqa: E402
    _family,
    _gpuperhour_parse,
    _load_previous,
    _merge,
    _positive,
    _runpod_parse,
    _summary_row,
    _vast_parse,
)


def test_family_detection_covers_variants_and_unknown_fallback():
    assert _family("h100-sxm-80gb") == "H100"
    assert _family("NVIDIA H200 SXM") == "H200"
    assert _family("RTX_5090") == "RTX 5090"
    assert _family("AMD Instinct MI300X OAM") == "MI300X"
    assert _family("mystery-gpu", fallback="unknown") == "unknown"


def test_positive_rejects_zero_negative_and_garbage():
    assert _positive(0) is None
    assert _positive(-1.5) is None
    assert _positive("abc") is None
    assert _positive(None) is None
    assert _positive("2.5") == 2.5


def test_summary_row_quartiles_small_samples_and_truncation_flag():
    row = _summary_row(
        date_iso="2026-08-22",
        source="gpuperhour",
        series="H100",
        unit="offers",
        prices=[4.0, 1.0, 3.0, 2.0],
        gpu_count_total=10,
        server_total=4,
        provider_count=3,
    )
    assert row["offerCount"] == 4
    assert row["truncated"] is False
    assert row["p25Price"] == pytest.approx(1.25)
    assert row["medianPrice"] == pytest.approx(2.5)
    assert row["p75Price"] == pytest.approx(3.75)

    small = _summary_row(
        date_iso="2026-08-22",
        source="vast",
        series="B200",
        unit="offers",
        prices=[3.0, 2.0],
        gpu_count_total=2,
    )
    assert small["p25Price"] == small["medianPrice"] == small["p75Price"] == 2.5
    assert small["serverTotal"] is None
    assert small["truncated"] is False

    truncated = _summary_row(
        date_iso="2026-08-22",
        source="gpuperhour",
        series="A100",
        unit="offers",
        prices=[1.0] * 100,
        gpu_count_total=100,
        server_total=120,
    )
    assert truncated["truncated"] is True


def test_gpuperhour_parse_filters_unavailable_nonusd_wrong_family_and_zero_prices():
    payload = {
        "pagination": {"total": 6},
        "data": [
            {"isAvailable": True, "currency": "USD", "gpu": {"slug": "h100-sxm-80gb", "name": "NVIDIA H100"}, "pricePerGpu": 2.0, "gpuCount": 4, "provider": "Alpha"},
            {"isAvailable": True, "currency": "USD", "gpu": {"slug": "h100-pcie-80gb"}, "pricePerGpu": 0, "gpuCount": 2, "provider": "Beta"},
            {"isAvailable": False, "currency": "USD", "gpu": {"slug": "h100-sxm-80gb"}, "pricePerGpu": 1.0, "gpuCount": 1, "provider": "Gamma"},
            {"isAvailable": True, "currency": "EUR", "gpu": {"slug": "h100-sxm-80gb"}, "pricePerGpu": 1.0, "gpuCount": 1, "provider": "Delta"},
            {"isAvailable": True, "currency": "USD", "gpu": {"slug": "b200"}, "pricePerGpu": 9.0, "gpuCount": 1, "provider": "Epsilon"},
            {"isAvailable": True, "currency": "USD", "gpu": {"slug": "h200-sxm"}, "pricePerGpu": 3.0, "gpuCount": 2, "provider": "Zeta"},
        ],
    }

    prices, gpu_count_total, providers = _gpuperhour_parse(payload, "H100")

    assert prices == [2.0]
    assert gpu_count_total == 4
    assert providers == {"Alpha"}


def test_vast_parse_keeps_only_verified_rentable_on_demand_focus_offers():
    payload = {
        "offers": [
            {"gpu_name": "RTX_5090", "rentable": True, "rented": False, "verification": "verified", "num_gpus": 2, "dph_total": 1.0},
            {"gpu_name": "RTX_4090", "rentable": True, "rented": False, "verification": "unverified", "num_gpus": 1, "dph_total": 0.5},
            {"gpu_name": "RTX_4090", "rentable": True, "rented": True, "verification": "verified", "num_gpus": 1, "dph_total": 0.5},
            {"gpu_name": "RTX_4090", "rentable": False, "rented": False, "verification": "verified", "num_gpus": 1, "dph_total": 0.5},
            {"gpu_name": "Mystery_XL", "rentable": True, "rented": False, "verification": "verified", "num_gpus": 8, "dph_total": 4.0},
            {"gpu_name": "H100 SXM", "rentable": True, "rented": False, "verification": "verified", "num_gpus": 3, "dph_total": 0},
        ],
    }

    grouped, gpu_counts = _vast_parse(payload)

    assert grouped == {"RTX 5090": [0.5]}
    assert gpu_counts == {"RTX 5090": 2}


def test_runpod_parse_rejects_mig_and_picks_lowest_available_on_demand_tier():
    payload = {
        "data": {
            "gpuTypes": [
                {
                    "id": "NVIDIA H100 80GB MIG 3xg.40gb",
                    "displayName": "H100",
                    "secureCloud": True,
                    "communityCloud": True,
                    "securePrice": 1.0,
                    "communityPrice": 0.9,
                },
                {
                    "id": "NVIDIA H100 80GB",
                    "displayName": "H100",
                    "secureCloud": False,
                    "communityCloud": True,
                    "securePrice": 99.0,
                    "communityPrice": 2.0,
                    "maxGpuCount": 8,
                },
                {
                    # secure 档标价 $0、community 云不可用：两档都不可用，整型排除
                    "id": "NVIDIA H200 141GB",
                    "displayName": "H200",
                    "secureCloud": True,
                    "communityCloud": False,
                    "securePrice": 0,
                    "communityPrice": 3.9,
                    "maxGpuCount": 4,
                },
                {
                    "id": "NVIDIA B200",
                    "displayName": "B200",
                    "secureCloud": False,
                    "communityCloud": False,
                    "securePrice": 5.0,
                    "maxGpuCount": 8,
                },
            ]
        }
    }

    grouped, gpu_counts = _runpod_parse(payload)

    assert grouped == {"H100": [2.0]}
    assert gpu_counts == {"H100": 8}


def _row(date_iso: str, source: str, series: str, price: float) -> dict:
    return {
        "date": date_iso,
        "source": source,
        "series": series,
        "unit": "offers",
        "offerCount": 1,
        "serverTotal": None,
        "truncated": False,
        "gpuCountTotal": 1,
        "minPrice": price,
        "p25Price": price,
        "medianPrice": price,
        "p75Price": price,
        "maxPrice": price,
        "providerCount": None,
    }


def test_merge_replaces_whole_current_day_and_preserves_history():
    previous = [
        _row("2026-08-21", "gpuperhour", "H100", 3.0),
        _row("2026-08-21", "vast", "H100", 2.5),
        _row("2026-08-22", "gpuperhour", "H100", 3.2),
        _row("2026-08-22", "vast", "A100", 1.4),
    ]
    new_day = [
        _row("2026-08-22", "gpuperhour", "H100", 3.1),
        _row("2026-08-22", "runpod", "H100", 2.6),
    ]

    merged = _merge(previous, new_day, "2026-08-22")

    keys = [(row["date"], row["source"], row["series"]) for row in merged]
    assert ("2026-08-22", "vast", "A100") not in keys
    assert ("2026-08-22", "gpuperhour", "H100") in keys
    assert ("2026-08-22", "runpod", "H100") in keys
    assert ("2026-08-21", "gpuperhour", "H100") in keys
    assert ("2026-08-21", "vast", "H100") in keys

    h100_today = next(row for row in merged if row["date"] == "2026-08-22" and row["source"] == "gpuperhour")
    assert h100_today["medianPrice"] == 3.1


def test_load_previous_returns_empty_for_missing_file(tmp_path):
    assert _load_previous(tmp_path / "missing.json") == []


def test_load_previous_hard_fails_on_corrupted_cache(tmp_path):
    corrupted = tmp_path / "history.json"
    corrupted.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        _load_previous(corrupted)

    bad_schema = tmp_path / "schema.json"
    bad_schema.write_text('{"rows": [{"date": "2026-08-22"}]}', encoding="utf-8")
    with pytest.raises(SystemExit):
        _load_previous(bad_schema)
