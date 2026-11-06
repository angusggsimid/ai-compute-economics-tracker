"""Tests for the P2-3 compare / spread / cheapest tool pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_external import build_crosscheck, load_external  # noqa: E402
from gpu_landscape import full_landscape, public_prices  # noqa: E402
from site_data import write_site_data  # noqa: E402
from site_shell import NAV  # noqa: E402
from site_tools import (  # noqa: E402
    _effective_external_count,
    _external_view_market,
    _nonfloor_external_count,
    write_tool_pages,
)


BACKFILL_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    raw = json.loads(BACKFILL_PATH.read_text(encoding="utf-8"))
    full = full_landscape(raw.get("rows") or [])
    external = load_external()
    public = tmp_path_factory.mktemp("site-tools")
    write_site_data(public, full, external)
    (public / "data" / "prices.json").write_text(
        json.dumps(public_prices(full), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    (public / "data" / "crosscheck.json").write_text(
        json.dumps(build_crosscheck(full, external), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    written = write_tool_pages(public)
    return public, written


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _external_counts(public: Path) -> tuple[int, int]:
    doc = json.loads((public / "data" / "external" / "prices.json").read_text(encoding="utf-8"))
    return _effective_external_count(doc), _nonfloor_external_count(doc)


def _check_shell(html: str, active: str) -> None:
    assert html.startswith("<!doctype html>")
    assert '<body data-base=".">' in html
    assert 'href="./assets/site.css"' in html
    assert 'src="./assets/site.js"' in html
    assert f'href="./{active}" class="active" aria-current="page"' in html
    for href, _label in NAV:
        assert f'href="./{href}"' in html, href
    assert '"/data/' not in html
    assert "file://" not in html
    assert "公开挂牌价，非成交价" in html


def test_external_market_view_mapping_matches_crosscheck_contract():
    assert _external_view_market({"market": "on_demand", "price_scope": "instance"}) == "on_demand"
    assert _external_view_market({"market": "spot", "price_scope": "instance"}) == "spot"
    assert _external_view_market({"market": "reserved_1y", "price_scope": "instance"}) == "reserved"
    assert _external_view_market({"market": "community", "price_scope": "instance"}) == "community"
    assert _external_view_market({"market": "community", "price_scope": "marketplace_floor"}) == "marketplace"
    assert _external_view_market({"market": "community", "price_scope": "advertised_from"}) == ""
    assert _external_view_market({"market": "serverless", "price_scope": "serverless"}) == "serverless"
    assert _external_view_market({"market": "shared", "price_scope": "instance"}) == ""


def test_three_files_are_written(generated):
    public, written = generated
    assert [Path(path).name for path in written] == [
        "compare.html",
        "spread.html",
        "cheapest.html",
    ]
    assert all(Path(path).is_absolute() for path in written)
    for path in written:
        assert Path(path).parent == public
        assert Path(path).is_file()
        assert Path(path).stat().st_size > 8000


def test_compare_page_contract(generated):
    public, _written = generated
    html = _read(public / "compare.html")
    _check_shell(html, "compare.html")
    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))

    assert 'id="compare-card-options"' in html
    assert html.count('type="checkbox" data-card-toggle') == len(index["cards"])
    assert 'id="compare-chart"' in html
    assert 'id="compare-table"' in html
    assert 'CC.get("cards/"' in html
    assert "CC.lineChart(" in html
    assert "weeks" in html
    assert "共同起点" in html
    assert "请选择 2–4 张卡" in html
    assert "最多选择 4 张卡" in html
    assert "最新 median" in html
    assert "Providers" in html
    assert "Weeks" in html
    assert "Status" in html
    assert "覆盖不足" in html
    assert "coverage_status" in html
    assert "data/cards/" in html
    assert "周指数" in html

    # The card selector is rendered from site-index.json, not hard-coded.
    for card in index["cards"]:
        assert f'value="{card["id"]}"' in html, card["id"]


def test_spread_page_contract(generated):
    public, _written = generated
    html = _read(public / "spread.html")
    _check_shell(html, "spread.html")

    assert 'id="spread-table"' in html
    assert 'id="spread-count"' in html
    assert 'CC.get("prices.json")' in html
    assert 'CC.get("external/prices.json")' in html
    for filter_name in ("card", "market", "layer"):
        assert f'data-filter="{filter_name}"' in html
    assert "externalDoc.prices" in html
    assert 'row.status !== "live"' in html
    assert 'scope === "marketplace_floor"' in html
    assert 'row.listed_currency !== "USD"' in html
    assert "spread" in html.lower()
    assert "P25–P75" in html
    assert "样本偏薄" in html
    assert "不是成交价" in html
    assert 'value="gpueconomy"' in html
    assert "populateCardOptions" in html
    assert "（外部）" in html
    assert "外部参考 · 无单卡页" in html
    assert "card: row.card_key" in html
    assert "cheapest && dearest && cheapest.price > 0" in html
    assert "effectiveExternalRows" in html
    assert "externalMarketView" in html
    assert "marketViews" in html
    assert "providerRows" in html
    assert "floor，不是 rate card" in html
    mappable, nonfloor = _external_counts(public)
    assert (
        f'<div class="label">外部 live+USD 可映射</div><div class="value">{mappable:,}</div>'
        in html
    )
    assert (
        f'<div class="label">非 floor 可比</div><div class="value">{nonfloor:,}</div>'
        in html
    )
    assert "外部有效报价" not in html

    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    for market in index["markets"]:
        assert f'value="{market["id"]}"' in html, market["id"]


def test_cheapest_page_contract(generated):
    public, _written = generated
    html = _read(public / "cheapest.html")
    _check_shell(html, "cheapest.html")

    assert 'id="cheapest-table"' in html
    assert 'id="cheapest-count"' in html
    assert 'CC.get("prices.json")' in html
    assert 'CC.get("external/prices.json")' in html
    for filter_name in ("card", "market", "layer"):
        assert f'data-filter="{filter_name}"' in html
    assert "Cheapest provider" in html
    assert "Price" in html
    assert "Source" in html
    assert "Date" in html
    assert "Risk" in html
    assert 'gpu/" + encodeURIComponent' in html
    assert 'providers/" + encodeURIComponent' in html
    assert 'row.status !== "live"' in html
    assert 'scope === "marketplace_floor"' in html
    assert 'row.listed_currency !== "USD"' in html
    assert "不是成交价" in html
    assert "没有匹配的 cheapest 行" in html
    assert "populateCardOptions" in html
    assert "（外部）" in html
    assert "外部参考 · 无单卡页" in html
    assert "card: row.card_key" in html
    assert "effectiveExternalRows" in html
    assert "externalMarketView" in html
    assert "marketViews" in html
    assert "providerRows" in html
    assert "floor，不是 rate card" in html
    mappable, nonfloor = _external_counts(public)
    assert (
        f'<div class="label">外部 live+USD 可映射</div><div class="value">{mappable:,}</div>'
        in html
    )
    assert (
        f'<div class="label">非 floor 可比</div><div class="value">{nonfloor:,}</div>'
        in html
    )
    assert "外部有效报价" not in html


def test_tool_pages_fail_loudly_without_data(tmp_path):
    with pytest.raises(FileNotFoundError, match="site-index.json"):
        write_tool_pages(tmp_path)
