import sys
from pathlib import Path

import pytest
import requests

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from production_store import GpuPriceObservation, ProductionStore  # noqa: E402
from tracker_v2 import Database  # noqa: E402
from data_sources.gpu_pricing import (  # noqa: E402
    GpuPricingCollectionResult,
    GpuPricingSource,
    collect_gpu_pricing_observations,
    parse_computeprices_html,
    parse_lambda_official_html,
    parse_runpod_official_html,
)


FIXTURES = TRACKER_V2 / "test_suite" / "fixtures" / "gpu_pricing"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _meta(source_url: str, source_id: str = "fixture-source", source_type: str = "public_pricing_page"):
    return {
        "run_id": "test-run-20260705",
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": "tracker_snapshots/test/fixture.html",
        "raw_payload_hash": "sha256:" + ("a" * 64),
        "fetched_at": "2026-07-05T00:00:00Z",
        "source_type": source_type,
    }


def _assert_production_observation(row: GpuPriceObservation):
    assert isinstance(row, GpuPriceObservation)
    assert row.provider
    assert row.gpu_model
    assert row.gpu_variant
    assert row.billing_type
    assert row.commitment
    assert row.gpu_count >= 1
    assert row.price_per_gpu_hour > 0
    assert row.source_url.startswith("https://")
    assert row.snapshot_path
    assert row.raw_payload_hash.startswith("sha256:")
    assert row.fetched_at
    assert row.observed_at
    assert row.collection_method == "html_parse"
    assert row.source_type in {"public_pricing_page", "aggregator"}


def test_runpod_official_parser_returns_sourcebacked_rows():
    rows = parse_runpod_official_html(
        _html("runpod_pricing.html"),
        **_meta("https://www.runpod.io/pricing", source_id="runpod-pricing"),
    )

    assert len(rows) >= 3
    _assert_production_observation(rows[0])

    prices = {(row.gpu_model, row.gpu_variant): row.price_per_gpu_hour for row in rows}
    assert prices[("H100", "PCIe")] == pytest.approx(2.89)
    assert prices[("H100", "SXM")] == pytest.approx(3.29)
    assert prices[("H200", "H200")] == pytest.approx(4.39)
    assert {row.provider for row in rows} == {"RunPod"}


def test_lambda_official_parser_keeps_cluster_and_instance_shapes_separate():
    rows = parse_lambda_official_html(
        _html("lambda_pricing.html"),
        **_meta("https://lambda.ai/pricing", source_id="lambda-pricing"),
    )

    assert len(rows) >= 5
    for row in rows:
        _assert_production_observation(row)
        assert row.provider == "Lambda"

    clusters = [row for row in rows if row.billing_type == "1-click-cluster"]
    assert {(row.gpu_count, row.price_per_gpu_hour) for row in clusters} >= {
        (16, 6.16),
        (64, 5.85),
        (256, 5.54),
    }

    instance = next(
        row for row in rows
        if row.billing_type == "on-demand" and row.gpu_model == "H100" and row.gpu_variant == "PCIe"
    )
    assert instance.gpu_count == 1
    assert instance.price_per_gpu_hour == pytest.approx(3.29)


def test_computeprices_h100_parser_preserves_aggregator_row_metadata_without_from_price():
    rows = parse_computeprices_html(
        _html("computeprices_h100.html"),
        gpu_model="H100",
        source_url="https://computeprices.com/gpus/h100",
        source_id="computeprices-h100",
        snapshot_path="tracker_snapshots/test/computeprices_h100.html",
        raw_payload_hash="sha256:" + ("b" * 64),
        fetched_at="2026-07-05T00:00:00Z",
        run_id="test-run-20260705",
    )

    assert len(rows) >= 5
    assert all(row.source_type == "aggregator" for row in rows)
    assert all(row.provider != "ComputePrices" for row in rows)
    assert all("quote_date=" in row.commitment for row in rows)
    assert all("quote_age_days=" in row.commitment for row in rows)
    assert all(row.source_url == "https://computeprices.com/gpus/h100" for row in rows)
    assert 0.02 not in {row.price_per_gpu_hour for row in rows}
    assert rows[0].provider == "Modal"
    assert rows[0].observed_at.startswith("2026-06-30")


def test_computeprices_h200_parser_returns_minimum_sourcebacked_rows():
    rows = parse_computeprices_html(
        _html("computeprices_h200.html"),
        gpu_model="H200",
        source_url="https://computeprices.com/gpus/h200",
        source_id="computeprices-h200",
        snapshot_path="tracker_snapshots/test/computeprices_h200.html",
        raw_payload_hash="sha256:" + ("c" * 64),
        fetched_at="2026-07-05T00:00:00Z",
        run_id="test-run-20260705",
    )

    assert len(rows) >= 3
    for row in rows:
        _assert_production_observation(row)
        assert row.gpu_model == "H200"
        assert row.source_type == "aggregator"


def test_collection_timeout_returns_quality_event_and_error_snapshot(tmp_path):
    def timeout_fetcher(url: str, timeout: int):
        raise requests.Timeout("timed out")

    source = GpuPricingSource(
        source_id="runpod-pricing",
        source_url="https://www.runpod.io/pricing",
        parser="runpod",
    )
    result = collect_gpu_pricing_observations(
        sources=[source],
        snapshot_dir=tmp_path,
        fetcher=timeout_fetcher,
        run_id="timeout-test",
        fetched_at="2026-07-05T00:00:00Z",
    )

    assert result.observations == []
    assert len(result.quality_events) == 1
    event = result.quality_events[0]
    assert event.error_code == "SOURCE_TIMEOUT"
    assert event.source_url == "https://www.runpod.io/pricing"
    assert Path(event.snapshot_path).exists()


def test_layout_change_returns_parse_failed_quality_event(tmp_path):
    def fetcher(url: str, timeout: int):
        return "<html><body><h1>Pricing changed</h1></body></html>"

    source = GpuPricingSource(
        source_id="lambda-pricing",
        source_url="https://lambda.ai/pricing",
        parser="lambda",
    )
    result = collect_gpu_pricing_observations(
        sources=[source],
        snapshot_dir=tmp_path,
        fetcher=fetcher,
        run_id="parse-fail-test",
        fetched_at="2026-07-05T00:00:00Z",
    )

    assert result.observations == []
    assert len(result.quality_events) == 1
    event = result.quality_events[0]
    assert event.error_code == "GPU_SOURCE_PARSE_FAILED"
    assert event.source_url == "https://lambda.ai/pricing"
    assert Path(event.snapshot_path).exists()


def test_parser_rows_can_be_inserted_through_production_store(tmp_path):
    rows = []
    rows.extend(
        parse_runpod_official_html(
            _html("runpod_pricing.html"),
            **_meta("https://www.runpod.io/pricing", source_id="runpod-pricing"),
        )
    )
    rows.extend(
        parse_computeprices_html(
            _html("computeprices_h200.html"),
            gpu_model="H200",
            source_url="https://computeprices.com/gpus/h200",
            source_id="computeprices-h200",
            snapshot_path="tracker_snapshots/test/computeprices_h200.html",
            raw_payload_hash="sha256:" + ("d" * 64),
            fetched_at="2026-07-05T00:00:00Z",
            run_id="test-run-20260705",
        )
    )

    db = Database(str(tmp_path / "tracker.db"))
    store = ProductionStore(db)
    assert store.insert_gpu_prices(rows) == len(rows)
    production = db.get_production_gpu_prices(eligible_only=False)
    assert len(production) == len(rows)
    assert set(production["source_type"]) == {"public_pricing_page", "aggregator"}


def test_production_gpu_update_does_not_call_legacy_reference_price_collector(monkeypatch):
    import tracker_v2  # noqa: E402
    import data_sources.gpu_pricing as gpu_pricing  # noqa: E402

    called = {"legacy": False, "production": False}

    def forbidden_legacy_collector():
        called["legacy"] = True
        raise AssertionError("production gpu-prices must not call hardcoded reference_prices")

    def fake_production_update():
        called["production"] = True
        return GpuPricingCollectionResult()

    monkeypatch.setattr(
        tracker_v2.GPUCollector,
        "fetch_gpu_price_from_providers",
        staticmethod(forbidden_legacy_collector),
    )
    monkeypatch.setattr(gpu_pricing, "update_production_gpu_prices", fake_production_update)

    tracker_v2.cmd_update(production=True, only="gpu-prices")

    assert called == {"legacy": False, "production": True}
