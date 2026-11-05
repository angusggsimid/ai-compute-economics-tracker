"""Page/build contract for the landscape UI additions.

These tests deliberately use the real backfill payloads through
``build_snapshot`` / ``write_public_data`` instead of copying a large fixture.
They only assert the page hooks and the machine-readable files the page fetches.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from build_time_series_dashboard import build_html, build_snapshot, write_public_data  # noqa: E402

LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


@pytest.fixture(scope="module")
def page_html() -> str:
    return build_html(build_snapshot())


def test_page_has_landscape_ui_hooks(page_html: str):
    for hook in (
        'id="landscape-offers"',
        'id="landscape-offers-body"',
        'id="landscape-monthly"',
        'id="landscape-monthly-body"',
        'id="landscape-crosscheck"',
        'id="landscape-crosscheck-body"',
        'id="landscape-crosscheck-selected"',
        'id="landscape-crosscheck-meta"',
        'id="landscape-crosscheck-note"',
        'id="landscape-cheapest-toggle"',
    ):
        assert hook in page_html, hook
    assert "showCheapest" in page_html
    assert "fetch('data/crosscheck.json'" in page_html
    assert "外部对照暂不可用" in page_html
    assert "该市场暂无报价" in page_html
    assert "日频近似，非 gpueconomy 的 hourly panel" in page_html
    assert "口径差" in page_html and "不是价差" in page_html
    assert "<th>市场</th>" in page_html and "<th>市场风险</th>" in page_html
    assert "日期与市场风险为市场级" in page_html
    assert "<th>阶段</th>" in page_html
    assert "进行中 · 暂定" in page_html and "已结束 · 按当前底表" in page_html
    assert "历史月会随底表回填重算，不是不可变快照；只有周指数有 final 冻结" in page_html
    assert "<th>我方/外部</th>" in page_html
    assert "重叠 <b>" in page_html
    assert "stopped 保留最后读数" in page_html and "不参与新周指数" in page_html
    assert LICENSE_URL in page_html
    assert page_html.count(LICENSE_URL) >= 2
    assert 'href="https://gpueconomy.com/data"' in page_html
    assert 'href="data/receipts/index.json"' in page_html
    assert 'href="data/crosscheck.json"' in page_html
    assert 'href="data/external/gpueconomy.json"' in page_html

    # Attribution is rendered from crosscheck.json at runtime.  Static HTML may
    # only carry the generic fallback, never a frozen methodology/date pair.
    assert "methodology 1.33.63" not in page_html
    assert "data 2026-11-03" not in page_html
    assert "d.methodology_version" in page_html
    assert "d.data_updated_at" in page_html
    assert "d.license_url" in page_html
    assert "CROSSCHECK_LICENSE_FALLBACK" in page_html
    assert "SKU 混合" in page_html


def test_write_public_data_emits_receipts_external_crosscheck(tmp_path: Path):
    written = write_public_data(
        {"meta": {"generatedAt": "2026-11-04T00:00:00Z"}},
        out_dir=tmp_path,
        freeze=False,
        snapshot_dir=tmp_path / "snapshots",
    )

    for rel in ("receipts/index.json", "external/gpueconomy.json", "crosscheck.json"):
        path = tmp_path / rel
        assert path.exists() and path.stat().st_size > 0, rel
        assert written[rel].endswith(rel)
    assert not (tmp_path / "snapshots").exists(), "freeze=False must not write index snapshots"

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in manifest["files"]}
    assert {"receipts/index.json", "external/gpueconomy.json", "crosscheck.json"} <= paths
    external = manifest["external_sources"]["gpueconomy"]
    assert external["license"] == "CC BY 4.0"
    assert external["license_url"] == LICENSE_URL
    assert external["own_methodology_version"]
    assert external["methodology_version"] == external["ext_methodology_version"]
    assert "secondary reference" in external["role"]

    receipts = json.loads((tmp_path / "receipts" / "index.json").read_text(encoding="utf-8"))
    assert receipts["count"] == len(receipts["weeks"]) >= 196
    assert receipts["commands"]["reproduce_receipt"]
    assert {row["available_via"] for row in receipts["weeks"]} <= {"page_latest", "cli"}

    crosscheck = json.loads((tmp_path / "crosscheck.json").read_text(encoding="utf-8"))
    assert len(crosscheck["rows"]) == 66
    assert crosscheck["license"] == "CC BY 4.0"
    assert crosscheck["license_url"] == LICENSE_URL
    assert crosscheck["methodology_version"] == crosscheck["ext_methodology_version"]
    assert crosscheck["own_methodology_version"]
    assert "latest-day" in crosscheck["rules"]["overlap_definition"]
    assert "historical-provider-pool" in crosscheck["rules"]["overlap_definition"]

    h100 = next(row for row in crosscheck["rows"] if row["card_id"] == "H100" and row["market"] == "on_demand")
    assert h100["match_id"] == "h100"
    assert h100["benchmark_id"] == "h100-sxm"
    assert h100["ext_benchmark_median"] is not None
    assert h100["coverage"] == "mixed"
    assert h100["coverage"] != "ok"
    assert h100["own_providers"] > 0
    assert h100["own_thin"] is False
    for card_id in ("GH200", "RTX 4090", "RTX 5090", "MI300X"):
        thin = next(
            row for row in crosscheck["rows"]
            if row["card_id"] == card_id and row["market"] == "on_demand"
        )
        assert thin["coverage"] == "thin"
        assert thin["own_thin"] is True
        assert thin["comparable"] is False
        assert thin["diff_pct"] is None
        assert thin["own_providers"] < 8
    h100_reserved = next(
        row for row in crosscheck["rows"]
        if row["card_id"] == "H100" and row["market"] == "reserved"
    )
    assert h100_reserved["coverage"] == "thin"
    assert h100_reserved["own_thin"] is True
    assert h100_reserved["diff_pct"] is None
    assert all(row.get("own_providers") is not None for row in crosscheck["rows"])
    h100_spot = next(row for row in crosscheck["rows"] if row["card_id"] == "H100" and row["market"] == "spot")
    assert h100_spot["ext_benchmark_median"] is None
    a100 = next(row for row in crosscheck["rows"] if row["card_id"] == "A100" and row["market"] == "on_demand")
    assert a100["coverage"] == "sku_mismatch"
    assert a100["comparable"] is False
    assert a100["diff_pct"] is None
    assert all(
        row["ext_benchmark_median"] is None
        for row in crosscheck["rows"]
        if row["market"] != "on_demand"
    )

    gpus = json.loads((tmp_path / "gpus.json").read_text(encoding="utf-8"))
    h100_gpus = next(card for card in gpus["gpus"] if card["id"] == "H100")
    for market in h100_gpus["markets"].values():
        series = market["cheapest_series"]
        assert set(series) == {"dates", "values", "provider_ids", "source_urls", "source_idx"}
        assert len(series["dates"]) == len(series["values"]) > 0
    mi300x = next(card for card in gpus["gpus"] if card["id"] == "MI300X")
    empty_spot = mi300x["markets"]["spot"]
    assert empty_spot["status"] == "no_data"
    assert empty_spot["cheapest_series"] == {
        "dates": [],
        "values": [],
        "provider_ids": [],
        "source_urls": [],
        "source_idx": [],
    }
    assert h100_gpus["monthly"][-1]["vintage"] == "provisional"
    assert h100_gpus["monthly"][-1]["isComplete"] is False
    assert h100_gpus["monthly"][0]["vintage"] == "final"
    assert h100_gpus["monthly"][0]["isComplete"] is True
