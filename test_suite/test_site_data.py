"""Tests for P2-3 static-site data slices and shared shell assets."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_external import load_external  # noqa: E402
from gpu_landscape import full_landscape, public_prices, public_providers  # noqa: E402
from site_data import (  # noqa: E402
    build_site_index,
    card_slug,
    provider_slug,
    write_site_data,
)
from site_shell import NAV, page, write_assets  # noqa: E402


BACKFILL_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    raw = json.loads(BACKFILL_PATH.read_text(encoding="utf-8"))
    full = full_landscape(raw.get("rows") or [])
    external = load_external()
    public = tmp_path_factory.mktemp("public")
    written = write_site_data(public, full, external)
    write_assets(public)
    return public, written, full, external


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_counts(full: dict, external: dict) -> dict:
    """Counts derived from the same source layers, never from today's volume."""
    return {
        "cards": len(full["cards"]),
        "own_providers": len(public_providers(full)["providers"]),
        "external_providers": sum(
            1
            for provider in external["providers"]["providers"]
            if int(provider.get("current_quotes") or 0) > 0
        ),
        "own_quotes": public_prices(full)["count"],
        "external_quotes": len(external["prices"]["prices"]),
    }


def test_slug_contract():
    assert card_slug("H100") == "h100"
    assert card_slug("RTX PRO 6000") == "rtx-pro-6000"
    assert provider_slug("own", "RunPod") == "own-runpod"
    assert provider_slug("gpueconomy", "gmi-cloud") == "ext-gmi-cloud"
    with pytest.raises(ValueError):
        provider_slug("unknown", "runpod")


def test_site_index_counts_and_summaries(generated):
    public, written, full, external = generated
    index = _read(public / "data" / "site-index.json")
    expected = _expected_counts(full, external)
    assert index["counts"] == expected
    assert index["as_of"] == full["asOf"]
    assert index["methodology_version"] == full["methodologyVersion"]
    assert index["external"]["source"] == "gpueconomy"
    assert len(index["cards"]) == expected["cards"]
    assert len(index["providers"]["own"]) == expected["own_providers"]
    assert len(index["providers"]["external"]) == expected["external_providers"]
    assert len(index["providers"]["own"]) + len(index["providers"]["external"]) == (
        expected["own_providers"] + expected["external_providers"]
    )
    assert all(item["current_quotes"] > 0 for item in index["providers"]["external"])
    assert all(item["slug"].startswith("ext-") for item in index["providers"]["external"])
    assert all(item["slug"].startswith("own-") for item in index["providers"]["own"])

    market_ids = {market["id"] for market in index["markets"]}
    assert market_ids
    h100 = next(card for card in index["cards"] if card["id"] == "H100")
    full_h100 = next(card for card in full["cards"] if card["id"] == "H100")
    assert h100["slug"] == "h100"
    assert h100["vram_gb"] == full_h100["vramGb"]
    assert set(h100["markets"]) == market_ids
    for market in h100["markets"].values():
        assert {
            "label", "status", "risk", "price_scope", "median", "p25", "p75",
            "cheapest", "cheapest_provider", "provider_count", "thin", "date",
        } <= set(market)

    # The index must be the same summary object the public provider file uses.
    same = build_site_index(full, external)
    assert same["counts"] == index["counts"]
    assert written["data/site-index.json"].endswith("site-index.json")


def test_card_files(generated):
    public, _written, full, _external = generated
    index = _read(public / "data" / "site-index.json")
    market_ids = {market["id"] for market in index["markets"]}
    card_files = sorted((public / "data" / "cards").glob("*.json"))
    assert len(card_files) == len(index["cards"])
    assert {path.stem for path in card_files} == {
        card_slug(card["id"]) for card in full["cards"]
    }

    for path in card_files:
        payload = _read(path)
        assert {"id", "slug", "card", "weeks", "crosscheck", "external"} <= set(payload)
        assert payload["card"]["id"] == payload["id"]
        assert "weekly" not in payload["card"]
        assert len(payload["card"]["markets"]) == len(market_ids)
        for node in payload["card"]["markets"].values():
            assert "cheapestSeries" not in node
            assert isinstance(node["series"], list)
            if node["latest"]:
                assert "offers" in node["latest"]
                assert "providers" not in node["latest"]
        assert len(payload["crosscheck"]) == len(market_ids)
        assert {row["market"] for row in payload["crosscheck"]} == market_ids
        assert set(payload["external"]["markets"]) == market_ids
        assert payload["weeks"]
        assert all(
            {
                "isoWeek", "weekStart", "vintage", "status", "median", "p25",
                "p75", "providerCount", "index", "linkPairs", "withheldReason",
            } <= set(week)
            for week in payload["weeks"]
        )

    h100 = _read(public / "data" / "cards" / "h100.json")
    full_h100 = next(card for card in full["cards"] if card["id"] == "H100")
    expected_offers = full_h100["markets"]["on_demand"]["latest"]["providers"]
    assert len(h100["card"]["markets"]["on_demand"]["latest"]["offers"]) == len(expected_offers)
    assert len(h100["card"]["markets"]) == len(market_ids)
    assert next(
        row for row in h100["crosscheck"] if row["market"] == "on_demand"
    )["coverage"] == "mixed"

    a100 = _read(public / "data" / "cards" / "a100.json")
    assert next(
        row for row in a100["crosscheck"] if row["market"] == "on_demand"
    )["coverage"] == "sku_mismatch"


def test_own_provider_files(generated):
    public, _written, full, _external = generated
    index = _read(public / "data" / "site-index.json")
    expected = len(public_providers(full)["providers"])
    files = sorted((public / "data" / "providers").glob("own-*.json"))
    assert len(files) == expected
    assert len(files) == len(index["providers"]["own"])
    for path in files:
        payload = _read(path)
        assert payload["layer"] == "own"
        assert payload["provider"]["id"]
        assert path.stem == payload["provider"]["slug"]
        assert payload["quotes"], path
        assert len(payload["quotes"]) == payload["provider"]["quotes"]
        for quote in payload["quotes"]:
            assert quote["provider_id"] == payload["provider"]["id"]
            assert {
                "card", "market", "risk", "price_scope", "date",
                "source_url", "usd_per_gpu_hour", "quotes",
            } <= set(quote)


def test_external_provider_files(generated):
    public, _written, _full, external = generated
    index = _read(public / "data" / "site-index.json")
    expected = sum(
        1
        for provider in external["providers"]["providers"]
        if int(provider.get("current_quotes") or 0) > 0
    )
    files = sorted((public / "data" / "providers").glob("ext-*.json"))
    assert len(files) == expected
    assert len(files) == len(index["providers"]["external"])
    providers_by_id = {
        provider["id"]: provider
        for provider in external["providers"]["providers"]
    }
    for path in files:
        payload = _read(path)
        assert payload["layer"] == "gpueconomy"
        assert payload["external"]["source"] == "gpueconomy"
        assert payload["external"]["license"] == "CC BY 4.0"
        provider = payload["provider"]
        assert provider["current_quotes"] > 0
        assert path.stem == provider["slug"]
        assert provider["id"] in providers_by_id
        assert "fees" in provider
        assert len(payload["quotes"]) == provider["current_quotes"]
        for quote in payload["quotes"]:
            assert quote["source_layer"] == "gpueconomy"
            assert quote["provider_id"] == provider["id"]
            assert {
                "gpu_id", "gpu", "market", "price_type", "price_scope", "risk",
                "usd_per_gpu_hour", "listed_currency", "fx_rate", "gpu_count",
                "region", "source_url", "scraped_at", "status",
            } <= set(quote)


def test_external_price_and_provider_files(generated):
    public, written, _full, external = generated
    expected_prices = len(external["prices"]["prices"])
    expected_providers = len(external["providers"]["providers"])
    prices = _read(public / "data" / "external" / "prices.json")
    assert prices["count"] == expected_prices
    assert len(prices["prices"]) == expected_prices
    assert prices["source"] == "gpueconomy"
    assert prices["license"] == "CC BY 4.0"
    assert written["data/external/prices.json"].endswith("prices.json")
    required = {
        "provider_id", "provider", "gpu_id", "gpu", "market", "price_type",
        "price_scope", "risk", "usd_per_gpu_hour", "listed_currency", "fx_rate",
        "gpu_count", "region", "source_url", "scraped_at", "status",
        "source_layer",
    }
    for row in prices["prices"]:
        assert required <= set(row)
        assert row["source_layer"] == "gpueconomy"
        assert row["provider_id"]
        assert row["status"]

    providers = _read(public / "data" / "external" / "providers.json")
    assert providers["count"] == expected_providers
    assert len(providers["providers"]) == expected_providers
    for provider in providers["providers"]:
        assert {
            "id", "slug", "name", "type", "source_kind", "scraped",
            "current_quotes", "cards", "website", "pricing_page", "fees",
            "notes", "models_tracked",
        } <= set(provider)
        assert isinstance(provider["fees"], list)


def test_written_manifest(generated):
    public, written, _full, _external = generated
    index = _read(public / "data" / "site-index.json")
    expected = {
        "data/site-index.json",
        "data/external/prices.json",
        "data/external/providers.json",
    }
    expected.update(f"data/cards/{card['slug']}.json" for card in index["cards"])
    expected.update(
        f"data/providers/{provider['slug']}.json"
        for provider in index["providers"]["own"]
    )
    expected.update(
        f"data/providers/{provider['slug']}.json"
        for provider in index["providers"]["external"]
    )
    assert set(written) == expected
    assert all(Path(path).is_file() for path in written.values())

    card_files = {path.name for path in (public / "data" / "cards").glob("*.json")}
    provider_files = {path.name for path in (public / "data" / "providers").glob("*.json")}
    assert card_files == {f"{card['slug']}.json" for card in index["cards"]}
    assert provider_files == {
        f"{provider['slug']}.json"
        for provider in index["providers"]["own"] + index["providers"]["external"]
    }
    assert len(provider_files) == (
        len(index["providers"]["own"]) + len(index["providers"]["external"])
    )


def test_shell_assets_and_relative_links(generated):
    public, _written, _full, _external = generated
    css = (public / "assets" / "site.css").read_text(encoding="utf-8")
    js = (public / "assets" / "site.js").read_text(encoding="utf-8")
    assert ".topbar{position:sticky" in css
    assert "@media(max-width:820px)" in css
    assert "@media(max-width:560px)" in css
    assert "CC.base" in js
    assert 'base + "/data/"' in js
    assert "CC.table" in js
    assert "CC.lineChart" in js
    assert "fetch(" in js
    assert "https://cdn" not in css and "https://cdn" not in js

    body = '<section class="hero"><h1>测试页</h1></section>'
    root = page("测试页", "描述", ".", "landscape", body, "window.pageReady = true;")
    assert root.startswith("<!doctype html>")
    assert '<body data-base=".">' in root
    assert 'href="./assets/site.css"' in root
    assert 'src="./assets/site.js"' in root
    assert 'href="./index.html"' in root
    for href, _label in NAV:
        assert f'href="./{href}"' in root
    assert 'href="./landscape.html" class="active" aria-current="page"' in root
    assert "window.pageReady = true;" in root
    assert '<footer class="footer">' in root
    assert '"/data/' not in root

    nested = page("卡页", "描述", "..", "gpu", body)
    assert '<body data-base="..">' in nested
    assert 'href="../assets/site.css"' in nested
    assert 'src="../assets/site.js"' in nested
    assert 'href="../index.html"' in nested
    for href, _label in NAV:
        assert f'href="../{href}"' in nested
    assert 'href="../landscape.html" class="active" aria-current="page"' in nested
    assert '"/data/' not in nested
    assert '<script></script>' not in root


NODE_CHART_HARNESS = r'''
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const timers = [];
const fakeWindow = {
  addEventListener: function (name, handler) { listeners[name] = handler; }
};
const body = {
  getAttribute: function () { return "."; },
  contains: function () { return true; }
};
const context = {
  window: fakeWindow,
  document: { body: body },
  console: console,
  setTimeout: function (handler) { timers.push(handler); return timers.length; },
  clearTimeout: function () {},
  fetch: function () { return Promise.reject(new Error("not used")); }
};
vm.createContext(context);
vm.runInContext(source, context);

const CC = fakeWindow.CC;
if (!CC || typeof CC.lineChart !== "function") { throw new Error("CC.lineChart missing"); }
if (typeof listeners.resize !== "function") { throw new Error("resize listener missing"); }

function host(width) {
  return {
    clientWidth: width,
    classList: { add: function () {} },
    _html: "",
    set innerHTML(value) { this._html = value; },
    get innerHTML() { return this._html; },
    querySelector: function (selector) {
      if (selector === ".chart-plot") {
        return { getBoundingClientRect: function () { return { width: 390, left: 0, top: 0 }; } };
      }
      if (selector === ".chart-tooltip") {
        return {
          classList: { add: function () {}, remove: function () {} },
          style: {},
          offsetWidth: 0,
          offsetHeight: 0
        };
      }
      return null;
    },
    querySelectorAll: function () { return []; }
  };
}

const chart = host(390);
CC.lineChart(chart, [{ name: "x", points: [
  { date: "2026-01-01", value: 2 },
  { date: "2026-01-02", value: null },
  { date: "2026-01-03", value: 4 },
  { date: "2026-01-04", value: 6 }
]}], { kind: "price", height: 240 });

if (!/viewBox="0 0 390 /.test(chart._html)) {
  throw new Error("viewBox is not based on host.clientWidth: " + chart._html.slice(0, 120));
}
if (chart._html.indexOf("$0.00") >= 0 || chart._html.indexOf("$0.000") >= 0) {
  throw new Error("null was rendered as zero");
}
const paths = (chart._html.match(/<path /g) || []).length;
if (paths !== 2) { throw new Error("null should split the line into 2 segments, got " + paths); }
const points = (chart._html.match(/<circle cx=/g) || []).length;
if (points !== 3) { throw new Error("null should not create a visible point, got " + points); }
const hits = (chart._html.match(/class="chart-hit"/g) || []).length;
if (hits !== 3) { throw new Error("null should not create a hover point, got " + hits); }

const gap = host(390);
CC.lineChart(gap, [{ name: "gap", points: [
  { date: "2026-01-01", value: 2 },
  { date: "2026-01-20", value: 4 }
]}], { kind: "price" });
if ((gap._html.match(/<path /g) || []).length !== 2) {
  throw new Error("a >14-day date gap should split the line");
}

const empty = host(390);
CC.lineChart(empty, [{ name: "none", points: [
  { date: "2026-01-01", value: null },
  { date: "2026-01-02", value: "" },
  { date: "2026-01-03", value: " " }
]}], {});
if (empty._html.indexOf('class="empty"') < 0) {
  throw new Error("an all-null series should render the empty state");
}

chart.clientWidth = 520;
listeners.resize();
timers.forEach(function (handler) { handler(); });
if (!/viewBox="0 0 520 /.test(chart._html)) {
  throw new Error("resize redraw did not use the new container width");
}
console.log("ok");
'''


def test_line_chart_null_breaks_and_container_width(generated, tmp_path):
    public, _written, _full, _external = generated
    js_path = public / "assets" / "site.js"
    js = js_path.read_text(encoding="utf-8")
    # Static contract checks remain useful even when Node is unavailable.
    assert "finiteValue" in js
    assert "clientWidth" in js
    assert "segmentsFor" in js
    assert 'point.value === null' in js
    assert 'addEventListener("resize"' in js
    assert "window.ResizeObserver" in js

    if shutil.which("node") is None:
        pytest.skip("node is required for the lineChart behavior test")

    harness = tmp_path / "chart_null_test.js"
    harness.write_text(NODE_CHART_HARNESS, encoding="utf-8")
    result = subprocess.run(
        ["node", str(harness), str(js_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "ok"


def test_write_site_data_prunes_only_stale_generated_json(generated, tmp_path):
    _public, _written, full, external = generated
    public = tmp_path / "public"
    cards_dir = public / "data" / "cards"
    providers_dir = public / "data" / "providers"
    external_dir = public / "data" / "external"
    for directory in (cards_dir, providers_dir, external_dir):
        directory.mkdir(parents=True)

    stale_cards = [cards_dir / "old-card.json"]
    stale_providers = [
        providers_dir / "own-old.json",
        providers_dir / "ext-old.json",
    ]
    for path in stale_cards + stale_providers:
        path.write_text('{"stale": true}', encoding="utf-8")
    keep_txt = [
        cards_dir / "keep.txt",
        providers_dir / "keep.txt",
        external_dir / "stale-but-not-in-scope.json",
    ]
    for path in keep_txt:
        path.write_text("keep", encoding="utf-8")

    write_site_data(public, full, external)

    assert all(not path.exists() for path in stale_cards + stale_providers)
    assert all(path.exists() for path in keep_txt)
    index = _read(public / "data" / "site-index.json")
    assert {path.name for path in cards_dir.glob("*.json")} == {
        f"{card['slug']}.json" for card in index["cards"]
    }
    assert {path.name for path in providers_dir.glob("*.json")} == {
        f"{provider['slug']}.json"
        for provider in index["providers"]["own"] + index["providers"]["external"]
    }
