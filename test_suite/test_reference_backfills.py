import json
import sys
from pathlib import Path

import pytest


TRACKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_ROOT))

from scripts.backfill_neocloud_prices import _merge as _provider_merge
from scripts.backfill_neocloud_prices import _load_previous, _normalize_series, normalize  # noqa: E402
from scripts.backfill_reference_indices import _merge_datasets  # noqa: E402
from scripts.backfill_reference_indices import _parse_semianalysis  # noqa: E402


def test_normalize_series_matches_focus_families():
    assert _normalize_series("rtx_5090") == "RTX 5090"
    assert _normalize_series("h100-sxm") == "H100"
    assert _normalize_series("nvidia_h200_141gb") == "H200"
    assert _normalize_series("mystery_xl") == "mystery_xl"


def test_provider_dataset_normalization_filters_and_dedups():
    payload = {
        "date": "2026-08-22",
        "offers": [
            {"provider": "RunPod", "gpu": "mi300x", "vram_gb": 192, "usd_hr": 2.39, "kind": "secure", "source_url": "https://x"},
            {"provider": "runpod", "gpu": "mi300x", "vram_gb": 192, "usd_hr": 2.39, "kind": "secure", "source_url": "https://x"},
            {"provider": "lambda", "gpu": "h100", "vram_gb": 80, "usd_hr": 0, "kind": "on-demand", "source_url": "https://y"},
            {"provider": "lambda", "gpu": "b200", "vram_gb": 180, "usd_hr": "abc", "kind": "on-demand", "source_url": "https://z"},
        ],
    }

    rows = normalize(payload)

    assert len(rows) == 1
    row = rows[0]
    assert (row["provider"], row["series"], row["usdPerGpuHour"]) == ("runpod", "MI300X", 2.39)


def test_semianalysis_public_payload_parses_composite_and_contract():
    payload = {
        "status": "ok",
        "index": [
            {"date": "Mon, 03 Aug 2026 00:00:00 GMT", "h100": 3.15, "a100": None, "b200": 5.4},
            {"date": "bad-date", "h100": 9.9},
            {"date": "Tue, 04 Aug 2026 00:00:00 GMT", "h100": -1, "a100": 0, "b200": 5.5},
        ],
        "contract": [
            {
                "data": [
                    {"period": "1H 2026", "period_start": "Thu, 01 Jan 2026 00:00:00 GMT", "1y": [2.7, 3.4]},
                    {"period": "bad", "period_start": "", "1y": [1]},
                ]
            }
        ],
    }

    composite, contract = _parse_semianalysis(payload)

    assert [(row["date"], row["series"], row["indexValue"]) for row in composite] == [
        ("2026-08-03", "B200", 5.4),
        ("2026-08-03", "H100", 3.15),
        # h100=-1 与 a100=0 被字段级过滤，同行的有效 b200 必须保留
        ("2026-08-04", "B200", 5.5),
    ]
    assert contract == [
        {
            "date": "2026-01-01",
            "series": "H100-1y",
            "lowValue": 2.7,
            "highValue": 3.4,
            "unit": "USD/GPU-hr",
            "basis": "survey_validated_contract_range",
            "label": "1H 2026",
        }
    ]


def test_merge_datasets_replaces_same_key_and_keeps_history():
    merged = _merge_datasets(
        {
            "ornnOcpi": [{"date": "2026-08-01", "series": "H100 SXM", "indexValue": 3.0}],
        },
        {
            "ornnOcpi": [{"date": "2026-08-01", "series": "H100 SXM", "indexValue": 3.2}],
            "semiComposite": [{"date": "2026-08-02", "series": "H100", "indexValue": 3.21}],
        },
    )
    assert merged["ornnOcpi"][0]["indexValue"] == 3.2
    assert merged["semiComposite"][0]["indexValue"] == 3.21


def test_provider_merge_replaces_whole_day(tmp_path):
    previous = [
        {"date": "2026-08-21", "provider": "runpod", "series": "H100", "vramGb": 80, "kind": "secure", "usdPerGpuHour": 2.59, "sourceUrl": "u"},
        {"date": "2026-08-22", "provider": "lambda", "series": "B200", "vramGb": 180, "kind": "on-demand", "usdPerGpuHour": 5.0, "sourceUrl": "u"},
    ]
    fresh = [
        {"date": "2026-08-22", "provider": "coreweave", "series": "H100", "vramGb": 80, "kind": "on-demand", "usdPerGpuHour": 3.0, "sourceUrl": "u"},
    ]

    merged = _provider_merge(previous, fresh, "2026-08-22")

    providers_today = [row["provider"] for row in merged if row["date"] == "2026-08-22"]
    assert providers_today == ["coreweave"]
    assert any(row["date"] == "2026-08-21" and row["provider"] == "runpod" for row in merged)


def test_load_previous_hard_fails_on_corrupted_cache(tmp_path):
    corrupted = tmp_path / "history.json"
    corrupted.write_text("{oops", encoding="utf-8")
    with pytest.raises(SystemExit):
        _load_previous(corrupted)

    missing_keys = tmp_path / "schema.json"
    missing_keys.write_text(json.dumps({"rows": [{"date": "2026-08-22"}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        _load_previous(missing_keys)
