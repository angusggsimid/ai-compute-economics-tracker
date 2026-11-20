"""Tests for the committed GPU Economy snapshot and the external reference layer."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import shutil
import sys
import urllib.error
from pathlib import Path
from statistics import median

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

import gpu_external  # noqa: E402
from gpu_external import (  # noqa: E402
    CROSSCHECK_MIN_OWN_PROVIDERS,
    SNAPSHOT_DIR,
    _coverage,
    build_crosscheck,
    ext_market_summary,
    latest_snapshot_dir,
    load_external,
    public_external,
    write_external_data,
)
from gpu_landscape import full_landscape  # noqa: E402


BACKFILL_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"


@pytest.fixture(scope="module")
def external():
    return load_external(SNAPSHOT_DIR)


@pytest.fixture(scope="module")
def full():
    raw = json.loads(BACKFILL_PATH.read_text(encoding="utf-8"))
    return full_landscape(raw.get("rows") or [])


def _load_ingest_module():
    spec = importlib.util.spec_from_file_location(
        "worker_c_ingest_gpueconomy", ROOT / "scripts" / "ingest_gpueconomy.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _committed_snapshot_payloads():
    metadata = json.loads((SNAPSHOT_DIR / "metadata.json").read_text(encoding="utf-8"))
    return metadata, {
        item["source"]: gzip.decompress((SNAPSHOT_DIR / item["path"]).read_bytes())
        for item in metadata["files"]
    }


def _extract_committed_snapshot(destination: Path) -> Path:
    _metadata, payloads = _committed_snapshot_payloads()
    source = destination / "source"
    source.mkdir()
    for name, raw in payloads.items():
        (source / name).write_bytes(raw)
    return source


def _official_rate_card_median(prices, gpu_id):
    """GPU Economy's published rule: on_demand+serverless, all currencies, live."""
    rows = [
        row
        for row in prices
        if row.get("gpu_id") == gpu_id
        and row.get("status") == "live"
        and row.get("price_scope") != "marketplace_floor"
        and row.get("market") in ("on_demand", "serverless")
    ]
    per_provider = {}
    for row in rows:
        provider = row["provider_id"]
        value = float(row["usd_per_gpu_hour"])
        per_provider[provider] = min(per_provider.get(provider, value), value)
    values = sorted(per_provider.values())
    return (len(values), median(values)) if values else (0, None)


def _expected_diff_pct(row):
    """diff_pct 的唯一定义：own_median / ext_median - 1（与 build_crosscheck 同一条口径）。

    own median 每天随采集变动，所以测试只能锁这条恒等式，不能锁某天的结果值；
    把 -8.4% 这类历史数字写进断言，等于给自己埋一颗随行情引爆的定时炸弹。
    """
    if not row["comparable"] or row["own_median"] is None or not row["ext_median"]:
        return None
    return round((float(row["own_median"]) / float(row["ext_median"]) - 1) * 100, 2)


def test_snapshot_metadata_checksums_and_counts():
    metadata = json.loads((SNAPSHOT_DIR / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["source"] == "gpueconomy"
    assert metadata["license"] == "CC BY 4.0"
    assert metadata["attribution"] == "GPU Economy (https://gpueconomy.com)"
    assert metadata["methodology_version"] == "1.33.63"
    assert metadata["methodology_version_source"] == "prices.json"
    assert metadata["methodology_version_format"] == "N.N.N"
    assert metadata["data_updated_at"].startswith("2026-11-03")
    assert metadata["files"]
    assert len(metadata["files"]) == 7

    total_gz = 0
    for item in metadata["files"]:
        packed = (SNAPSHOT_DIR / item["path"]).read_bytes()
        raw = gzip.decompress(packed)
        assert len(packed) == item["bytes_gz"]
        assert len(raw) == item["bytes_raw"]
        assert hashlib.sha256(packed).hexdigest() == item["sha256_gz"]
        assert hashlib.sha256(raw).hexdigest() == item["sha256_raw"]
        assert item["count"] > 0
        total_gz += len(packed)
    assert total_gz == metadata["total_bytes_gz"]
    assert 500_000 < total_gz < 600_000  # facts-external: ~534KB including changelog


def test_load_external_verifies_snapshot(external):
    assert external["prices"]["count"] == 1399
    assert len(external["prices"]["prices"]) == 1399
    assert len(external["gpus"]["gpus"]) == 82
    assert external["metadata"]["license"] == "CC BY 4.0"


def test_latest_snapshot_dir_and_explicit_old(tmp_path, monkeypatch, full):
    base = tmp_path / "gpueconomy"
    base.mkdir()
    old = base / "2026-11-03"
    new = base / "2026-11-05"
    shutil.copytree(SNAPSHOT_DIR, old)
    shutil.copytree(SNAPSHOT_DIR, new)

    assert latest_snapshot_dir(base) == new
    monkeypatch.setattr(gpu_external, "SNAPSHOT_ROOT", base)

    default = load_external()
    assert Path(default["snapshot_dir"]).name == "2026-11-05"

    explicit = load_external(old)
    assert Path(explicit["snapshot_dir"]).name == "2026-11-03"

    write_external_data(full, tmp_path / "out")
    payload = json.loads(
        (tmp_path / "out" / "external" / "gpueconomy.json").read_text(encoding="utf-8")
    )
    assert payload["snapshot"].endswith("2026-11-05")


def test_official_published_medians_reproduce(external):
    """The 51 non-null gpus.json medians must match the published rule exactly."""
    checked = 0
    matched = 0
    mismatches = []
    for card in external["gpus"]["gpus"]:
        published = card.get("rate_card_median_usd_per_gpu_hour")
        if published is None:
            continue
        checked += 1
        count, value = _official_rate_card_median(external["prices"]["prices"], card["id"])
        if count and value is not None and abs(value - published) <= 5e-4:
            matched += 1
        else:
            mismatches.append((card["id"], count, value, published))
    assert checked == 51
    assert matched == checked, mismatches
    assert not mismatches


def test_comparable_h100_keeps_match_and_benchmark_separate(external):
    match = ext_market_summary(external["prices"], "h100", "on_demand")
    benchmark = ext_market_summary(external["prices"], "h100-sxm", "on_demand")
    assert match["providers"] == 18
    assert match["median"] == pytest.approx(3.97, abs=5e-4)
    assert match["p25"] == pytest.approx(2.7425, abs=5e-4)
    assert match["p75"] == pytest.approx(5.26, abs=5e-4)
    assert benchmark["providers"] == 37
    assert benchmark["median"] == pytest.approx(3.29, abs=5e-4)
    assert benchmark["median"] != match["median"]


def test_sku_ambiguous_uses_our_card_id(external):
    h100 = ext_market_summary(
        external["prices"], "h100", "on_demand", include_quotes=True
    )
    assert h100["quotes"] and all(quote["sku_ambiguous"] is True for quote in h100["quotes"])

    a100 = ext_market_summary(
        external["prices"], "a100-80", "on_demand", include_quotes=True
    )
    assert a100["quotes"] and all(quote["sku_ambiguous"] is True for quote in a100["quotes"])

    h200 = ext_market_summary(
        external["prices"], "h200", "on_demand", include_quotes=True
    )
    runpod = next(quote for quote in h200["quotes"] if quote["provider_id"] == "runpod")
    assert runpod["sku_ambiguous"] is True
    assert any(quote["sku_ambiguous"] is False for quote in h200["quotes"])

    rtx = ext_market_summary(
        external["prices"], "rtx-pro-6000", "community", include_quotes=True
    )
    assert rtx["quotes"] and all(quote["sku_ambiguous"] is True for quote in rtx["quotes"])


def test_crosscheck_h100_and_a100_rules(full, external):
    crosscheck = build_crosscheck(full, external)
    rows = crosscheck["rows"]
    assert len(rows) == 11 * 6

    required_fields = {
        "card_id",
        "market",
        "own_median",
        "own_providers",
        "own_thin",
        "ext_median",
        "ext_providers",
        "ext_median_published",
        "ext_benchmark_median",
        "ext_benchmark_id",
        "mixed_sku",
        "diff_pct",
        "overlap_count",
        "overlap_count_match",
        "overlap_scope",
        "overlap_providers",
        "coverage",
        "comparable",
        "as_of",
        "ext_as_of",
        "note",
    }
    assert required_fields <= set(rows[0])

    h100 = next(row for row in rows if row["card_id"] == "H100" and row["market"] == "on_demand")
    assert h100["match_id"] == "h100"
    assert h100["benchmark_id"] == "h100-sxm"
    assert h100["ext_median"] == pytest.approx(3.97, abs=5e-4)
    assert h100["ext_benchmark_median"] == pytest.approx(3.29, abs=5e-4)
    assert h100["ext_median"] != h100["ext_benchmark_median"]
    assert h100["ext_median_published"] == pytest.approx(3.7415, abs=5e-4)
    assert 1 <= h100["overlap_count_match"] <= h100["overlap_count"]
    assert h100["coverage"] == "mixed"
    assert h100["coverage"] != "ok"
    assert h100["mixed_sku"] is True
    assert h100["comparable"] is True, f"H100 on-demand own 样本跌破门槛：{h100}"
    # diff 不能写死：own median 每天随采集变化（2026-11-04 是 -8.4%，
    # 2026-11-08 变成 -6.93%，2026-11-20 变成 -12.09%）。只校验口径本身：
    # 用 ext_median，而不是只作审计的 rate_card_median。
    assert h100["diff_pct"] == pytest.approx(_expected_diff_pct(h100), abs=1e-9)
    published_basis = round(
        (float(h100["own_median"]) / float(h100["ext_median_published"]) - 1) * 100, 2
    )
    if published_basis != h100["diff_pct"]:
        assert h100["diff_pct"] != pytest.approx(published_basis, abs=1e-9)
    assert h100["ext_source_url"].endswith("/prices.json")
    assert h100["ext_scraped_at"].startswith("2026-11-03")

    spot = next(row for row in rows if row["card_id"] == "H100" and row["market"] == "spot")
    assert spot["comparable"] is True, f"H100 spot own 样本跌破门槛：{spot}"
    assert spot["diff_pct"] is not None
    assert spot["diff_pct"] == pytest.approx(_expected_diff_pct(spot), abs=1e-9)
    assert spot["ext_benchmark_median"] is None
    assert spot["ext_benchmark_id"] is None
    assert spot["benchmark_id"] is None
    reserved = next(row for row in rows if row["card_id"] == "H100" and row["market"] == "reserved")
    assert reserved["comparable"] is False
    assert reserved["diff_pct"] is None
    assert reserved["coverage"] == "thin"
    assert reserved["own_thin"] is True
    assert reserved["own_providers"] < CROSSCHECK_MIN_OWN_PROVIDERS
    assert reserved["ext_benchmark_median"] is None
    assert reserved["note"]

    assert crosscheck["own_methodology_version"] == full["methodologyVersion"]
    assert crosscheck["ext_methodology_version"] == "1.33.63"
    assert crosscheck["methodology_version"] == "1.33.63"
    overlap_rule = crosscheck["rules"]["overlap_definition"]
    assert "latest-day" in overlap_rule
    assert "historical-provider-pool" in overlap_rule

    a100 = next(row for row in rows if row["card_id"] == "A100" and row["market"] == "on_demand")
    assert a100["coverage"] == "sku_mismatch"
    assert a100["comparable"] is False
    assert a100["diff_pct"] is None
    assert a100["ext_median"] == pytest.approx(1.765, abs=5e-4)
    assert a100["overlap_count"] > 0
    assert "型号" in (a100["note"] or "")

    gh200 = next(row for row in rows if row["card_id"] == "GH200" and row["market"] == "on_demand")
    # 只锁"样本薄 → 不给差值"的规则，不锁具体家数：provider 进出不该让 CI 挂。
    assert 0 < gh200["own_providers"] < CROSSCHECK_MIN_OWN_PROVIDERS
    assert gh200["own_thin"] is True
    assert gh200["coverage"] == "thin"
    assert gh200["diff_pct"] is None
    assert gh200["comparable"] is False

    for card_id in ("RTX 4090", "RTX 5090"):
        row = next(
            item for item in rows if item["card_id"] == card_id and item["market"] == "on_demand"
        )
        assert 0 < row["own_providers"] < CROSSCHECK_MIN_OWN_PROVIDERS
        assert row["own_thin"] is True
        assert row["coverage"] == "thin"
        assert row["diff_pct"] is None
        assert row["comparable"] is False


def test_crosscheck_rows_are_price_drift_safe(full, external):
    """全量 66 行的口径恒等式：行情怎么走都应该成立。

    定时任务先刷新真实价格再跑测试，own median/家数每天都会变。这里只锁
    "口径之间不许自相矛盾"的部分，把某一天的数字留给 FIX_LOG 记录。
    """
    rows = build_crosscheck(full, external)["rows"]
    assert len(rows) == 66
    assert len({(row["card_id"], row["market"]) for row in rows}) == 66

    for row in rows:
        label = f'{row["card_id"]}/{row["market"]}'
        own = int(row["own_providers"] or 0)
        ext = int(row["ext_providers"] or 0)

        # thin 闸门与 comparable 派生关系
        assert row["own_thin"] is (own < CROSSCHECK_MIN_OWN_PROVIDERS), label
        if row["comparable"]:
            assert own >= CROSSCHECK_MIN_OWN_PROVIDERS, label
            assert row["coverage"] in ("ok", "mixed"), label
            assert row["diff_pct"] is not None, label
        else:
            assert row["diff_pct"] is None, label
        if own < CROSSCHECK_MIN_OWN_PROVIDERS and ext > 0:
            assert row["coverage"] == "thin", label

        # diff 只能来自 ext_median 口径
        assert row["diff_pct"] == _expected_diff_pct(row), label
        if row["diff_pct"] is not None:
            assert row["own_median"] > 0 and row["ext_median"] > 0, label

        # overlap 结构
        assert row["overlap_count_match"] <= row["overlap_count"], label
        assert row["overlap_count"] == len(row["overlap_providers"]), label
        assert row["overlap_providers"] == sorted(set(row["overlap_providers"])), label

        # benchmark 字段只在 on_demand 上存在
        if row["market"] != "on_demand":
            assert row["benchmark_id"] is None, label
            assert row["ext_benchmark_median"] is None, label


def test_coverage_priority_puts_own_thin_first():
    assert _coverage(0, 0, 1, sku_mismatch=True, mixed_sku=True) == "none"
    # H100 reserved in this snapshot has only a few own providers: thin wins
    # over mixed_sku, so the machine-readable coverage tells the sample story.
    assert _coverage(10, 5, 1, mixed_sku=True) == "thin"
    assert _coverage(10, 5, CROSSCHECK_MIN_OWN_PROVIDERS, mixed_sku=True) == "mixed"
    assert _coverage(10, 5, CROSSCHECK_MIN_OWN_PROVIDERS, sku_mismatch=True) == "sku_mismatch"
    assert _coverage(2, 1, CROSSCHECK_MIN_OWN_PROVIDERS) == "thin"
    assert _coverage(10, 5, CROSSCHECK_MIN_OWN_PROVIDERS) == "ok"


def test_external_never_changes_own_medians(full, external):
    before = {
        card["id"]: card["markets"]["on_demand"]["latest"]["value"]
        for card in full["cards"]
        if card["markets"]["on_demand"].get("latest")
    }
    raw_before = json.dumps(full, ensure_ascii=False, sort_keys=True)
    build_crosscheck(full, external)
    after = {
        card["id"]: card["markets"]["on_demand"]["latest"]["value"]
        for card in full["cards"]
        if card["markets"]["on_demand"].get("latest")
    }
    assert after == before
    assert json.dumps(full, ensure_ascii=False, sort_keys=True) == raw_before


def test_public_external_has_attribution_but_no_changelog_data(full, external):
    crosscheck = build_crosscheck(full, external)
    payload = public_external(external, crosscheck)
    assert payload["license"] == "CC BY 4.0"
    assert payload["license_url"].startswith("https://creativecommons.org/licenses/by/4.0/")
    assert payload["attribution"] == "GPU Economy (https://gpueconomy.com)"
    assert payload["methodology_version"] == "1.33.63"
    assert payload["own_methodology_version"] == full["methodologyVersion"]
    assert "own_methodology_version" in payload["rules"]["methodology_versions"]
    assert payload["rules"]["comparable"] == crosscheck["rules"]["comparable"]
    assert payload["rules"]["quotes"] == (
        "included quotes cover all market views; on_demand is the primary comparison"
    )
    assert payload["data_updated_at"].startswith("2026-11-03")
    assert len(payload["cards"]) == 11
    assert "changelog" not in payload
    assert "history" not in payload
    assert "changelog.json" not in json.dumps(payload)
    assert "moves" not in json.dumps(payload)
    h100_card = next(card for card in payload["cards"] if card["card_id"] == "H100")
    assert h100_card["mixed_sku"] is True
    assert h100_card["sku_mismatch"] is False
    a100_card = next(card for card in payload["cards"] if card["card_id"] == "A100")
    assert a100_card["sku_mismatch"] is True
    assert a100_card["markets"]["on_demand"]["comparable"] is False
    for card in payload["cards"]:
        quotes = card["markets"]["on_demand"]["quotes"]
        assert quotes, card["card_id"]
        for quote in quotes:
            assert quote["source_layer"] == "gpueconomy"
            assert quote["source_url"].startswith("https://")
            assert quote["scraped_at"]
            assert quote["listed_currency"] == "USD"
            if card["card_id"] in ("H100", "A100"):
                assert quote["sku_ambiguous"] is True


def test_write_external_data_creates_both_payloads(tmp_path, full):
    out_dir = tmp_path / "public-data"
    result = write_external_data(full, out_dir)
    external_path = out_dir / "external" / "gpueconomy.json"
    crosscheck_path = out_dir / "crosscheck.json"
    assert external_path.is_file()
    assert crosscheck_path.is_file()
    assert result["cards"] == 11
    assert result["rows"] == 66

    external_payload = json.loads(external_path.read_text(encoding="utf-8"))
    crosscheck_payload = json.loads(crosscheck_path.read_text(encoding="utf-8"))
    assert external_payload["attribution"] == "GPU Economy (https://gpueconomy.com)"
    assert len(crosscheck_payload["rows"]) == 66
    assert crosscheck_payload["rows"][0]["card_id"] == "H100"
    comparable_rule = crosscheck_payload["rules"]["comparable"]
    assert comparable_rule.startswith("on_demand")
    assert "spot/serverless" in comparable_rule
    assert "reserved/community/marketplace" in comparable_rule


def test_ingest_script_roundtrips_real_snapshot(tmp_path):
    module = _load_ingest_module()
    committed, _payloads = _committed_snapshot_payloads()
    source = _extract_committed_snapshot(tmp_path)

    result = module.ingest_from_dir(
        source, tmp_path / "out", "2026-11-03", "2026-11-03T13:05:00Z"
    )
    assert result["file_count"] == 7
    generated = json.loads(
        (tmp_path / "out" / "2026-11-03" / "metadata.json").read_text(encoding="utf-8")
    )
    assert generated["license"] == "CC BY 4.0"
    assert generated["attribution"] == "GPU Economy (https://gpueconomy.com)"
    assert generated["fetched_at"] == "2026-11-03T13:05:00Z"
    assert generated["total_bytes_gz"] < 600_000
    for item in generated["files"]:
        source_item = next(entry for entry in committed["files"] if entry["source"] == item["source"])
        assert item["sha256_raw"] == source_item["sha256_raw"]
        assert item["count"] == source_item["count"]

    verified = module.verify_snapshot(tmp_path / "out" / "2026-11-03")
    assert verified["file_count"] == 7
    assert verified["total_bytes_gz"] == generated["total_bytes_gz"]


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("methodology_version", "9.99.99", "methodology_version"),
        ("methodology_version", "1.33", "not N.N.N"),
        ("license", "MIT", "CC BY 4.0"),
    ],
)
def test_verify_snapshot_rejects_bad_metadata(tmp_path, field, value, needle):
    module = _load_ingest_module()
    snapshot = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_DIR, snapshot)
    metadata_path = snapshot / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        module.verify_snapshot(snapshot)
    assert needle in str(excinfo.value)


@pytest.mark.parametrize(
    ("source_name", "field", "value"),
    [
        ("changelog.json", "methodology_version", "9.99.99"),
        ("token-cost.json", "license", "MIT"),
        ("history.json", "data_updated_at", "2026-11-04T00:00:00+00:00"),
    ],
)
def test_verify_snapshot_rejects_file_metadata_mismatch(tmp_path, source_name, field, value):
    module = _load_ingest_module()
    snapshot = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_DIR, snapshot)
    metadata_path = snapshot / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    entry = next(item for item in metadata["files"] if item["source"] == source_name)
    payload_path = snapshot / entry["path"]
    document = json.loads(gzip.decompress(payload_path.read_bytes()).decode("utf-8"))
    document[field] = value
    new_raw = json.dumps(document, ensure_ascii=False).encode("utf-8")
    new_gz = module._gzip_bytes(new_raw)

    payload_path.write_bytes(new_gz)
    entry["bytes_raw"] = len(new_raw)
    entry["bytes_gz"] = len(new_gz)
    entry["sha256_raw"] = hashlib.sha256(new_raw).hexdigest()
    entry["sha256_gz"] = hashlib.sha256(new_gz).hexdigest()
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        module.verify_snapshot(snapshot)
    message = str(excinfo.value)
    assert entry["path"] in message
    assert value in message


@pytest.mark.parametrize("bad_version", [None, "1.33", "v1.33.63"])
def test_ingest_rejects_bad_prices_methodology_version(tmp_path, bad_version):
    module = _load_ingest_module()
    source = _extract_committed_snapshot(tmp_path)
    prices_path = source / "prices.json"
    prices = json.loads(prices_path.read_text(encoding="utf-8"))
    if bad_version is None:
        prices.pop("methodology_version", None)
    else:
        prices["methodology_version"] = bad_version
    prices_path.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        module.ingest_from_dir(source, tmp_path / "out", "2026-11-03", "2026-11-03T13:05:00Z")
    assert "methodology_version" in str(excinfo.value)


def test_ingest_rejects_mismatched_file_methodology_version(tmp_path):
    module = _load_ingest_module()
    source = _extract_committed_snapshot(tmp_path)
    index_path = source / "price-index.json"
    index_doc = json.loads(index_path.read_text(encoding="utf-8"))
    index_doc["methodology_version"] = "9.99.99"
    index_path.write_text(json.dumps(index_doc, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        module.ingest_from_dir(source, tmp_path / "out", "2026-11-03", "2026-11-03T13:05:00Z")
    assert "methodology_version" in str(excinfo.value)


@pytest.mark.parametrize("bad_version", [None, "1.33", "1.33.64"])
def test_load_external_rejects_bad_metadata_methodology_version(tmp_path, bad_version):
    snapshot = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_DIR, snapshot)
    metadata_path = snapshot / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if bad_version is None:
        metadata.pop("methodology_version", None)
    else:
        metadata["methodology_version"] = bad_version
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="methodology_version"):
        load_external(snapshot)


def test_ingest_url_mode_uses_same_validation(tmp_path, monkeypatch):
    module = _load_ingest_module()
    _metadata, payloads = _committed_snapshot_payloads()
    calls = []

    def fake_fetch(url, timeout):
        calls.append((url, timeout))
        return payloads[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(module, "_fetch_url", fake_fetch)
    code = module.main(
        [
            "--url",
            "https://gpueconomy.com/data",
            "--date",
            "2026-11-03",
            "--out",
            str(tmp_path / "out"),
            "--fetched-at",
            "2026-11-03T13:05:00Z",
            "--timeout",
            "5",
        ]
    )
    assert code == 0
    expected = [f"https://gpueconomy.com/{name}" for name in module.REQUIRED_FILES]
    assert [url for url, _timeout in calls] == expected
    assert all(timeout == 5 for _url, timeout in calls)

    generated = json.loads(
        (tmp_path / "out" / "2026-11-03" / "metadata.json").read_text(encoding="utf-8")
    )
    assert generated["source_url"] == "https://gpueconomy.com/data"
    assert generated["methodology_version"] == "1.33.63"
    assert module.verify_snapshot(tmp_path / "out" / "2026-11-03")["file_count"] == 7


def test_ingest_url_failure_is_explicit(tmp_path, monkeypatch):
    module = _load_ingest_module()

    def fail_fetch(url, timeout):
        raise urllib.error.URLError("HTTP 403")

    monkeypatch.setattr(module, "_fetch_url", fail_fetch)
    with pytest.raises(SystemExit) as excinfo:
        module.main(
            [
                "--url",
                "https://example.test/data",
                "--out",
                str(tmp_path / "out"),
            ]
        )
    assert "failed to download" in str(excinfo.value)
    assert "403" in str(excinfo.value)


def test_fetch_url_sets_user_agent_and_timeout(monkeypatch):
    module = _load_ingest_module()
    captured = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    assert module._fetch_url("https://example.test/prices.json", 7) == b'{"ok": true}'
    assert captured["timeout"] == 7
    assert "ai-compute-economics" in (captured["request"].get_header("User-agent") or "")
    assert captured["request"].full_url == "https://example.test/prices.json"
