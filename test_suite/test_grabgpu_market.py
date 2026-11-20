"""GrabGPU 库存采集的口径与累积正确性。

为什么存在：GPU Finder 免费档 60 次/月被轨道预算吃到 55 次/月，2026-11-08 起 429 整月，
供给端三图从那天开始停更。GrabGPU 的 `/api/offers.json` 一次请求给全市场，
所以 2026-11-21 起它做主源，GPU Finder 降为每周一轮的保底。

这里锁三件事：
1. provider 口径去重（同一家多条报价只算一票，任一在库即算在库）；
2. 价差公式与 GPU Finder 完全一致（最低在库 ÷ 最低挂牌 − 1），可直接接续；
3. 按日累积不被覆盖（同一天重跑只替换当天、历史不丢）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backfill_grabgpu_market import (  # noqa: E402
    MODELS,
    OUTPUT_PATH,
    ROW_FIELDS,
    _model_metrics,
    build_rows,
    merge_rows,
)


def _offer(provider, gpu="nvidia-h100", price=2.0, availability="in_stock"):
    return {
        "gpu": gpu,
        "gpu_name": "Nvidia H100",
        "provider": provider,
        "usd_per_gpu_hour": price,
        "availability": availability,
    }


def test_provider_dedup_both_directions():
    """同一家多条报价：一票进分母、任一在库即算在库；价格仍按公司级最低取。"""
    offers = [
        _offer("a", price=2.0, availability="out_of_stock"),
        _offer("a", price=3.0, availability="in_stock"),
        _offer("b", price=1.5, availability="in_stock"),
    ]
    m = _model_metrics(offers)
    assert m["providers"] == 2
    assert m["providersInStock"] == 2, "a 有一条在库，就应算作在库 provider"
    assert m["providersKnown"] == 2
    assert m["providersOutOfStock"] == 0
    assert m["cheapestListed"] == pytest.approx(1.5)
    assert m["cheapestInStock"] == pytest.approx(1.5)


def test_gap_formula_matches_gpufinder():
    """low_stock / low_listed - 1：与 GPU Finder 同名指标同一公式，可直接接续。"""
    offers = [
        _offer("cheap", price=1.66, availability="out_of_stock"),
        _offer("stocked", price=1.69, availability="in_stock"),
    ]
    m = _model_metrics(offers)
    assert m["cheapestListed"] == pytest.approx(1.66)
    assert m["cheapestInStock"] == pytest.approx(1.69)
    assert m["listedAvailableGapPct"] == pytest.approx(round((1.69 / 1.66 - 1) * 100, 2))


def test_unknown_excluded_from_denominator_only():
    """状态未知的 provider 不进分母，但它的挂牌价仍可成为「最低报价」。"""
    offers = [
        _offer("u", price=0.9, availability="unknown"),
        _offer("x", price=2.0, availability="out_of_stock"),
        _offer("y", price=2.2, availability="in_stock"),
    ]
    m = _model_metrics(offers)
    assert m["providers"] == 3
    assert m["providersKnown"] == 2, "unknown 不得进分母"
    assert m["availabilityPct"] == pytest.approx(50.0)
    assert m["cheapestListed"] == pytest.approx(0.9), "unknown 的挂牌价仍是最低报价"


def test_availability_is_provider_share_not_capacity_weight():
    """分母是 provider 家数，不是卡数：这是与 GPU Finder 实例数加权口径的显式差异。"""
    offers = [
        _offer("big", price=2.0, availability="out_of_stock"),
        _offer("small", price=2.1, availability="in_stock"),
        _offer("tiny", price=2.2, availability="in_stock"),
    ]
    assert _model_metrics(offers)["availabilityPct"] == pytest.approx(round(2 / 3 * 100, 2))


def test_build_rows_keeps_only_frontier_gpus_and_reports_gaps():
    captured = "2026-11-20T15:11:50.728207Z"
    payload = {
        "captured_at": captured,
        "offers": [
            _offer("a", gpu="nvidia-h100"),
            _offer("a", gpu="nvidia-h200"),
            _offer("b", gpu="nvidia-b200"),
            _offer("c", gpu="amd-mi300x"),
        ],
    }
    rows, quality = build_rows(payload, captured)
    assert {r["gpu"] for r in rows} == set(MODELS.values())
    assert all(r["date"] == "2026-11-20" for r in rows), "日期取上游 captured_at，不用本地时钟"
    assert quality == [], "三张卡都在时不应有质量事件"
    for row in rows:
        assert set(ROW_FIELDS) <= set(row)

    empty, quality2 = build_rows({"captured_at": captured, "offers": [_offer("c", gpu="amd-mi300x")]}, captured)
    assert empty == []
    assert len(quality2) == 3, "缺型号必须逐条记录，不能静默补零"


def test_merge_rows_is_idempotent_and_append_only():
    day1 = {"date": "2026-11-20", "gpu": "H100", "availabilityPct": 33.33}
    day2 = {"date": "2026-11-21", "gpu": "H100", "availabilityPct": 40.0}
    rerun = {"date": "2026-11-20", "gpu": "H100", "availabilityPct": 35.0}
    merged = merge_rows([day1], [rerun, day2])
    assert len(merged) == 2, "同一天只保留一行"
    assert {r["date"]: r["availabilityPct"] for r in merged} == {"2026-11-20": 35.0, "2026-11-21": 40.0}
    assert merged == merge_rows(merged, [rerun, day2]), "重复运行不得改变结果"


def test_committed_artifact_shape_is_sane():
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    assert payload["sourceUrl"].endswith("/api/offers.json")
    assert payload["sourceSha256"].startswith("sha256:")
    assert "grabgpu.com" in payload["attribution"]
    assert payload["rows"], "rows 不应为空"
    seen = set()
    for row in payload["rows"]:
        assert row["gpu"] in MODELS.values()
        assert len(row["date"]) == 10
        assert 0 <= row["availabilityPct"] <= 100
        assert row["providersInStock"] <= row["providersKnown"] <= row["providers"]
        assert row["breadthProviders"] == row["providersInStock"]
        if row.get("cheapestInStock") and row.get("cheapestListed"):
            expected = round((row["cheapestInStock"] / row["cheapestListed"] - 1) * 100, 2)
            assert row["listedAvailableGapPct"] == pytest.approx(expected, abs=1e-9)
        key = (row["date"], row["gpu"])
        assert key not in seen, "同一 (date, gpu) 不得重复"
        seen.add(key)
