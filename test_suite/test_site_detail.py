"""Tests for the static card and provider detail pages (P2-3 / W3).

The fixture runs the real data pipeline into ``tmp_path`` and derives every
expected count from the generated ``site-index.json`` / card and provider
slices.  It never hard-codes daily-refresh quantities such as provider or
offer counts.  Browser behaviour is covered separately by
``scripts/browser_smoke.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_external import load_external  # noqa: E402
from gpu_landscape import full_landscape  # noqa: E402
from site_data import write_site_data  # noqa: E402
from site_detail import (  # noqa: E402
    _http_link,
    _http_url,
    write_card_pages,
    write_provider_pages,
)
from site_shell import write_assets  # noqa: E402


BACKFILL_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    raw = json.loads(BACKFILL_PATH.read_text(encoding="utf-8"))
    full = full_landscape(raw.get("rows") or [])
    external = load_external()
    public = tmp_path_factory.mktemp("public-detail")
    write_site_data(public, full, external)
    write_assets(public)
    cards = write_card_pages(public)
    providers = write_provider_pages(public)
    index = _read_json(public / "data" / "site-index.json")
    return public, cards, providers, index


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _html(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _live_stats(quotes) -> tuple[int, int]:
    """Independent mirror of the public live-quote definition."""
    live = [
        quote
        for quote in quotes or []
        if quote.get("status") == "live"
        and quote.get("price_scope") != "marketplace_floor"
        and quote.get("listed_currency") == "USD"
    ]
    gpu_ids = {
        str(quote.get("gpu_id"))
        for quote in live
        if quote.get("gpu_id")
    }
    return len(live), len(gpu_ids)


def _market_panel(html: str, market_id: str) -> str:
    marker = f'data-market-panel="{market_id}"'
    assert marker in html
    return html.split(marker, 1)[1].split("data-market-panel=", 1)[0]


def test_page_counts(built):
    public, cards, providers, index = built
    index_cards = index["cards"]
    own_providers = index["providers"]["own"]
    ext_providers = index["providers"]["external"]
    expected_provider_count = len(own_providers) + len(ext_providers)

    card_files = sorted((public / "gpu").glob("*.html"))
    provider_files = sorted((public / "providers").glob("*.html"))
    assert len(card_files) == len(index_cards)
    assert len(provider_files) == expected_provider_count
    assert len(list((public / "providers").glob("own-*.html"))) == len(own_providers)
    assert len(list((public / "providers").glob("ext-*.html"))) == len(ext_providers)

    assert {path.stem for path in card_files} == {
        card["slug"] for card in index_cards
    }
    assert {path.stem for path in provider_files} == {
        provider["slug"] for provider in own_providers + ext_providers
    }

    assert len(set(cards)) == len(index_cards)
    assert len(set(providers)) == expected_provider_count
    assert all((public / path).is_file() for path in cards + providers)


def test_h100_card_page_contract(built):
    public, _cards, _providers, index = built
    card = next(item for item in index["cards"] if item["id"] == "H100")
    slug = card["slug"]
    market_ids = [market["id"] for market in index["markets"]]
    html = _html(public / "gpu" / f"{slug}.html")

    assert '<body data-base="..">' in html
    assert f"cards/{slug}.json" in html
    assert html.count('data-market-panel="') == len(market_ids)
    assert html.count('data-market-tab="') == len(market_ids)
    assert html.count('class="js-host" data-chart="') == len(market_ids)
    assert html.count('class="js-host" data-offers="') == len(market_ids)
    assert 'data-market-panel="on_demand"' in html
    assert 'aria-selected="true" class="tab active">On-demand<' in html
    for market in market_ids:
        assert f'data-market-panel="{market}"' in html
        assert f'data-market-tab="{market}"' in html

    # Chart series and the dynamic table hosts the page script fills.
    for needle in ("CC.lineChart", '"P25"', '"P75"', '"Cheapest"', 'kind: "price"'):
        assert needle in html
    for column in ('key: "value"', 'key: "status"', 'key: "index"', 'key: "own_median"', 'key: "coverage"'):
        assert column in html
    for tone in ('tone: "ok"', 'tone: "high sku_mismatch"', 'tone: "none"'):
        assert tone in html
    for element_id in ("monthly-table", "weekly-table", "crosscheck-table"):
        assert f'id="{element_id}"' in html
    for column in ("ISO week", "Index", "Providers", "Vintage", "Coverage"):
        assert column in html

    # Downloads and attribution use relative paths.
    assert f'href="../data/cards/{slug}.json"' in html
    assert f'href="../data/price-index/{slug}.json"' in html
    assert 'href="../data/receipts/index.json"' in html
    assert "GPU Economy" in html
    assert "CC BY 4.0" in html
    assert '"/data/' not in html


def test_provider_pages(built):
    public, _cards, _providers, index = built
    own_provider = next(
        provider for provider in index["providers"]["own"] if provider["id"] == "runpod"
    )
    ext_provider = next(
        provider for provider in index["providers"]["external"] if provider["id"] == "runpod"
    )
    own = _html(public / "providers" / f"{own_provider['slug']}.html")
    ext = _html(public / "providers" / f"{ext_provider['slug']}.html")

    assert '<body data-base="..">' in own
    assert f"providers/{own_provider['slug']}.json" in own
    assert "自有供给" in own
    assert "公开挂牌价" in own
    assert '"/data/' not in own

    assert '<body data-base="..">' in ext
    assert f"providers/{ext_provider['slug']}.json" in ext
    assert "GPU Economy · CC BY 4.0" in ext
    assert "https://gpueconomy.com/data" in ext
    assert "https://creativecommons.org/licenses/by/4.0/" in ext
    assert "not published" in ext
    assert 'key: "field"' in ext
    assert "外部参考" in ext
    assert "报价明细" in ext
    assert '"/data/' not in ext

    # Every external page keeps the attribution and fetches only its own file.
    for provider in index["providers"]["external"]:
        page_html = _html(public / "providers" / f"{provider['slug']}.html")
        assert "GPU Economy · CC BY 4.0" in page_html
        assert f"providers/{provider['slug']}.json" in page_html
        assert '"/data/' not in page_html
        assert "target=\"_blank\" rel=\"noopener\"" in page_html

    # Own pages never fetch an ext file and vice versa.
    assert "providers/ext-" not in own
    assert "providers/own-" not in ext


def test_external_live_counts_are_not_stopped_records(built):
    public, _cards, _providers, index = built
    for provider in index["providers"]["external"]:
        payload = _read_json(
            public / "data" / "providers" / f"{provider['slug']}.json"
        )
        live_quotes, live_cards = _live_stats(payload.get("quotes") or [])
        raw = int(payload["provider"].get("current_quotes") or 0)
        html = _html(public / "providers" / f"{provider['slug']}.html")

        assert f'id="ext-live-quotes">{live_quotes:,}<' in html
        assert f'id="ext-live-cards">{live_cards:,}<' in html
        assert f"raw {raw:,} 条记录（含 stopped" in html
        assert "Current quotes" not in html

    edgevana = next(
        (provider for provider in index["providers"]["external"] if provider["id"] == "edgevana"),
        None,
    )
    if edgevana is None:
        pytest.skip("Edgevana not present in the current external index")
    payload = _read_json(public / "data" / "providers" / f"{edgevana['slug']}.json")
    live_quotes, live_cards = _live_stats(payload.get("quotes") or [])
    raw = int(payload["provider"].get("current_quotes") or 0)
    html = _html(public / "providers" / f"{edgevana['slug']}.html")
    assert f'id="ext-live-quotes">{live_quotes:,}<' in html
    assert f'id="ext-live-cards">{live_cards:,}<' in html
    if live_quotes == 0:
        assert "0 live" in html
        assert f"raw {raw:,} 条记录（含 stopped）" in html
        assert "条当前报价" not in html


def test_empty_market_shows_no_own_quotes_not_thin(built):
    public, _cards, _providers, index = built
    checked = 0
    for card in index["cards"]:
        payload = _read_json(
            public / "data" / "cards" / f"{card['slug']}.json"
        )
        for market_id, market in (payload["card"].get("markets") or {}).items():
            if market.get("status") != "no_data" and market.get("series"):
                continue
            html = _html(public / "gpu" / f"{card['slug']}.html")
            block = _market_panel(html, market_id)
            assert "无自有报价" in block
            assert "样本偏薄" not in block
            checked += 1
            break
        if checked:
            break
    if not checked:
        pytest.skip("no empty card×market in the current dataset")


def test_every_card_page_uses_its_own_slice(built):
    public, _cards, _providers, index = built
    market_count = len(index["markets"])
    for card in index["cards"]:
        slug = card["slug"]
        html = _html(public / "gpu" / f"{slug}.html")
        assert f"cards/{slug}.json" in html
        assert f'href="../data/cards/{slug}.json"' in html
        assert f'href="../data/price-index/{slug}.json"' in html
        assert html.count('data-market-panel="') == market_count
        assert '"/data/' not in html


def test_http_url_guard():
    assert _http_url("https://example.com/pricing") == "https://example.com/pricing"
    assert _http_url("http://example.com") == "http://example.com"
    assert _http_url("javascript:alert(1)") == ""
    assert _http_url("data:text/html,hi") == ""
    assert _http_url("//example.com/x") == ""
    assert _http_url(None) == ""
    assert "href=" not in _http_link("javascript:alert(1)")
    assert 'href="https://example.com/x"' in _http_link("https://example.com/x", "来源")
