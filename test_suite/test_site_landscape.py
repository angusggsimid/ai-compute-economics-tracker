"""Tests for the P2-3 landscape and provider index pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_external import build_crosscheck, load_external  # noqa: E402
from gpu_landscape import full_landscape  # noqa: E402
from site_data import write_site_data  # noqa: E402
from site_landscape import write_landscape_page, write_providers_page  # noqa: E402
from site_shell import NAV, write_assets  # noqa: E402


BACKFILL_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    raw = json.loads(BACKFILL_PATH.read_text(encoding="utf-8"))
    full = full_landscape(raw.get("rows") or [])
    external = load_external()
    public = tmp_path_factory.mktemp("site-landscape")
    write_site_data(public, full, external)
    crosscheck = build_crosscheck(full, external)
    data = public / "data"
    (data / "crosscheck.json").write_text(
        json.dumps(crosscheck, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    write_assets(public)
    landscape = write_landscape_page(public)
    providers = write_providers_page(public)
    return public, landscape, providers, full, external, crosscheck


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _count_text(value) -> str:
    return f"{int(value):,}"


def _is_effective_external_quote(quote) -> bool:
    return (
        quote.get("status") == "live"
        and quote.get("price_scope") != "marketplace_floor"
        and quote.get("listed_currency") == "USD"
    )


def test_pages_are_written(generated):
    public, landscape, providers, _full, _external, _crosscheck = generated
    assert Path(landscape) == public / "landscape.html"
    assert Path(providers) == public / "providers.html"
    assert (public / "landscape.html").is_file()
    assert (public / "providers.html").is_file()
    assert (public / "landscape.html").stat().st_size > 5000
    assert (public / "providers.html").stat().st_size > 5000


def test_landscape_page_contract(generated):
    public, _landscape, _providers, _full, _external, crosscheck = generated
    html = _read(public / "landscape.html")

    assert html.startswith("<!doctype html>")
    assert '<body data-base=".">' in html
    assert 'id="landscape-table"' in html
    assert 'id="landscape-table" aria-live="polite" aria-busy="true"' in html
    assert 'href="./assets/site.css"' in html
    assert 'src="./assets/site.js"' in html
    assert 'href="./index.html"' in html
    for href, _label in NAV:
        assert f'href="./{href}"' in html, href
    assert 'href="./landscape.html" class="active" aria-current="page"' in html
    assert '"/data/' not in html
    assert "file://" not in html

    # The table is built in the browser from both committed slices.
    assert "CC.get(\"site-index.json\")" in html
    assert "CC.get(\"crosscheck.json\")" in html
    assert "CC.table(" in html
    assert "CC.empty(" in html
    assert 'gpu/" + row.card_slug + ".html"' in html
    assert "没有匹配的 card × market 行" in html

    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    assert len(crosscheck["rows"]) == len(index["cards"]) * len(index["markets"])
    for card in index["cards"]:
        assert f'<option value="{card["id"]}">' in html, card["id"]
    for market in index["markets"]:
        assert f'<option value="{market["id"]}">' in html, market["id"]
    for filter_name in ("card", "market", "coverage", "search"):
        assert f'data-filter="{filter_name}"' in html
    assert '<option value="sku_mismatch">' in html

    # Hero numbers and attribution are rendered from site-index.json.
    counts = index["counts"]
    assert (
        '<div class="label">关键卡</div><div class="value">'
        f'{_count_text(counts["cards"])}</div>'
    ) in html
    assert (
        '<div class="label">自有 provider</div><div class="value">'
        f'{_count_text(counts["own_providers"])}</div>'
    ) in html
    assert (
        '<div class="label">外部 provider</div><div class="value">'
        f'{_count_text(counts["external_providers"])}</div>'
    ) in html
    assert (
        '<div class="label">外部报价</div><div class="value">'
        f'{_count_text(counts["external_quotes"])}</div>'
    ) in html
    assert index["as_of"] in html
    assert "GPU Economy" in html
    assert "CC BY 4.0" in html

    # Coverage tones and thin-sample wording are present in the renderer.
    assert '"SKU mismatch"' in html
    assert "样本偏薄" in html
    assert "无外部对照" in html
    assert "仅参考" in html
    assert "可算差值" in html


def test_providers_page_contract(generated):
    public, _landscape, _providers, _full, _external, _crosscheck = generated
    html = _read(public / "providers.html")

    assert html.startswith("<!doctype html>")
    assert '<body data-base=".">' in html
    assert 'id="providers-table"' in html
    assert 'id="providers-table" aria-live="polite" aria-busy="true"' in html
    assert 'href="./assets/site.css"' in html
    assert 'src="./assets/site.js"' in html
    assert 'href="./index.html"' in html
    for href, _label in NAV:
        assert f'href="./{href}"' in html, href
    assert 'href="./providers.html" class="active" aria-current="page"' in html
    assert '"/data/' not in html
    assert "file://" not in html

    assert "CC.get(\"site-index.json\")" in html
    assert "CC.get(\"external/prices.json\")" in html
    assert "CC.table(" in html
    assert "CC.empty(" in html
    assert 'providers/" + row.slug + ".html"' in html
    assert "没有匹配的 provider" in html

    for filter_name in ("layer", "type", "search"):
        assert f'data-filter="{filter_name}"' in html
    assert '<option value="own">' in html
    assert '<option value="gpueconomy">' in html
    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    external = index["providers"]["external"]
    for type_value in sorted({str(item.get("type") or "external") for item in external}):
        assert f'<option value="{type_value}">' in html

    own_n = len(index["providers"]["own"])
    ext_n = len(external)
    assert (
        '<div class="label">Provider 总数</div><div class="value">'
        f'{_count_text(own_n + ext_n)}</div>'
    ) in html
    assert f"自有 {_count_text(own_n)} 家 + 外部 {_count_text(ext_n)} 家" in html
    assert "外部报价记录" in html
    assert index["as_of"] in html
    assert "GPU Economy" in html
    assert "CC BY 4.0" in html
    assert 'class="badge ext"' in html
    assert '"Live coverage"' in html
    assert '"Live quotes"' in html
    assert "key cards" in html
    assert "GPU ids" in html


def test_external_live_scope_filters_stopped_floor_and_non_usd(generated):
    public, _landscape, _providers, _full, _external, _crosscheck = generated
    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    prices = json.loads(
        (public / "data" / "external" / "prices.json").read_text(encoding="utf-8")
    )["prices"]
    external = index["providers"]["external"]

    live_quotes = {}
    live_gpus = {}
    live_without_usd = {}
    live_usd_with_floor = {}
    for quote in prices:
        provider_id = quote.get("provider_id")
        if not provider_id:
            continue
        if quote.get("status") == "live" and quote.get("price_scope") != "marketplace_floor":
            live_without_usd[provider_id] = live_without_usd.get(provider_id, 0) + 1
        if quote.get("status") == "live" and quote.get("listed_currency") == "USD":
            live_usd_with_floor[provider_id] = live_usd_with_floor.get(provider_id, 0) + 1
        if not _is_effective_external_quote(quote):
            continue
        live_quotes[provider_id] = live_quotes.get(provider_id, 0) + 1
        gpu_key = quote.get("gpu_id") or quote.get("gpu") or ""
        if gpu_key:
            live_gpus.setdefault(provider_id, set()).add(gpu_key)

    # At least one external provider's raw current_quotes is not live coverage.
    assert external
    assert any(
        live_quotes.get(provider["id"], 0) < provider["current_quotes"]
        for provider in external
    )
    edgevana = next(
        (provider for provider in external if provider["id"] == "edgevana"), None
    )
    if (
        edgevana is not None
        and live_quotes.get("edgevana", 0) < edgevana["current_quotes"]
    ):
        assert len(live_gpus.get("edgevana", set())) < len(edgevana["cards"])

    # The USD and marketplace-floor clauses each remove real live quotes.
    assert any(
        live_without_usd.get(provider["id"], 0) > live_quotes.get(provider["id"], 0)
        for provider in external
    )
    assert any(
        live_usd_with_floor.get(provider["id"], 0) > live_quotes.get(provider["id"], 0)
        for provider in external
    )

    html = _read(public / "providers.html")
    assert 'quote.status !== "live"' in html
    assert 'quote.price_scope === "marketplace_floor"' in html
    assert 'quote.listed_currency !== "USD"' in html
    assert "isEffectiveExternalQuote" in html
    assert "live_quotes" in html
    assert "live_key_cards" in html
    assert "live_gpu_ids" in html
    assert "0 live" in html


def test_landscape_empty_market_semantics(generated):
    public, _landscape, _providers, _full, _external, crosscheck = generated
    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    mi300x = next(card for card in index["cards"] if card["id"] == "MI300X")
    empty_markets = {
        market_id: node
        for market_id, node in mi300x["markets"].items()
        if node["provider_count"] == 0
    }
    assert empty_markets
    assert all(node["status"] == "no_data" for node in empty_markets.values())
    empty_rows = [
        row
        for row in crosscheck["rows"]
        if row["card_id"] == "MI300X" and row["own_providers"] == 0
    ]
    assert empty_rows
    assert all(row["own_thin"] for row in empty_rows)

    html = _read(public / "landscape.html")
    status_start = html.index('{ label: "状态", key: "status"')
    status_end = html.index("  ];", status_start)
    status_block = html[status_start:status_end]
    assert 'CC.badge("无自有报价", "none")' in status_block
    assert 'CC.badge("无可用报价", "none")' in status_block
    assert 'CC.badge("样本偏薄", "thin")' in status_block
    assert (
        status_block.index('row.own_n === 0')
        < status_block.index('row.status === "no_data"')
        < status_block.index('else if (row.own_thin)')
    )
    assert "thin（仅外部）" in html
    assert (
        'row.market !== "on_demand" || row.status === "no_data" || row.own_n === 0'
        in html
    )
    assert '"Weekly idx (on-demand)"' in html


def test_provider_live_coverage_units(generated):
    public, _landscape, _providers, _full, _external, _crosscheck = generated
    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    prices = json.loads(
        (public / "data" / "external" / "prices.json").read_text(encoding="utf-8")
    )["prices"]
    html = _read(public / "providers.html")

    assert '"Live coverage"' in html
    assert '"Live cards"' not in html
    assert "live_key_cards: (provider.cards || []).length" in html
    assert "live_gpu_ids: live.live_gpus.length" in html
    assert 'live_coverage_unit: "key cards"' in html
    assert 'live_coverage_unit: "GPU ids"' in html
    assert "live_cards" not in html

    own = {provider["id"]: provider for provider in index["providers"]["own"]}
    external = {provider["id"]: provider for provider in index["providers"]["external"]}
    shared = sorted(set(own).intersection(external))
    assert shared
    provider_id = "runpod" if "runpod" in shared else shared[0]
    own_key_cards = len(own[provider_id]["cards"])
    external_gpu_ids = {
        quote["gpu_id"]
        for quote in prices
        if quote.get("provider_id") == provider_id
        and _is_effective_external_quote(quote)
        and quote.get("gpu_id")
    }
    card_ids = {card["id"] for card in index["cards"]}
    assert own_key_cards > 0
    assert external_gpu_ids
    assert own_key_cards <= len(card_ids)
    assert any(gpu_id not in card_ids for gpu_id in external_gpu_ids)


def test_pages_fail_loudly_without_data(tmp_path):
    with pytest.raises(FileNotFoundError, match="site-index.json"):
        write_landscape_page(tmp_path)
    with pytest.raises(FileNotFoundError, match="site-index.json"):
        write_providers_page(tmp_path)
