import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from build_time_series_dashboard import build_html, build_snapshot, write_public_data  # noqa: E402
from gpu_landscape import (  # noqa: E402
    full_landscape,
    public_changelog,
    public_gpus,
    public_index,
    public_manifest,
    public_prices,
    public_providers,
    trim_landscape,
)


@pytest.fixture(scope="module")
def snapshot():
    return build_snapshot()


def _offer(day, provider, price, series="H100", kind="on-demand"):
    return {"date": day, "provider": provider, "series": series, "kind": kind, "usdPerGpuHour": price, "sourceUrl": f"https://example.com/{provider}"}


def test_landscape_has_cards_markets_and_matches_gpu_price(snapshot):
    landscape = snapshot["gpuLandscape"]
    assert len(landscape["cards"]) >= 8
    ids = {card["id"] for card in landscape["cards"]}
    assert {"H100", "H200", "B200", "A100", "L40S", "RTX PRO 6000"} <= ids
    assert {m["id"] for m in landscape["markets"]} == {
        "on_demand", "spot", "reserved", "community", "marketplace", "serverless"
    }
    h100 = next(card for card in landscape["cards"] if card["id"] == "H100")
    old = [row for row in snapshot["datasets"]["gpuPrice"] if row["series"] == "H100"][-1]
    assert h100["median"] == pytest.approx(old["value"], abs=1e-3)
    assert h100["providerCount"] == old["providerCount"]
    assert h100["status"] == "live"
    assert h100["weeklyIndex"]["vintage"] in ("provisional", "final")
    assert h100["weeklyIndex"]["providerCount"] >= landscape["indexMinProviders"]
    assert landscape["dataAgeDays"] >= 0
    assert landscape["dataFreshness"] in ("current", "stale")


def test_on_demand_market_does_not_mix_community_or_spot():
    rows = [
        _offer("2026-09-27", "a", 5.0),
        _offer("2026-09-27", "b", 1.0, kind="community"),
        _offer("2026-09-27", "c", 0.5, kind="spot"),
        _offer("2026-09-27", "d", 0.2, kind="marketplace"),
    ]
    full = full_landscape(rows, as_of="2026-09-27")
    h100 = next(card for card in full["cards"] if card["id"] == "H100")
    assert h100["markets"]["on_demand"]["latest"]["value"] == 5.0
    assert h100["markets"]["on_demand"]["latest"]["providerCount"] == 1
    assert h100["markets"]["on_demand"]["latest"]["thin"] is True
    assert h100["markets"]["community"]["latest"]["value"] == 1.0
    assert h100["markets"]["spot"]["latest"]["value"] == 0.5
    assert h100["markets"]["marketplace"]["latest"]["value"] == 0.2


def test_weekly_index_has_receipts_and_chain_link():
    rows = []
    for week_day, base in (("2026-09-21", 4.0), ("2026-09-28", 5.0)):
        for i, provider in enumerate(("a", "b", "c", "d", "e")):
            rows.append(_offer(week_day, provider, base + i))
    rows.append(_offer("2026-09-21", "community", 1.0, kind="community"))
    full = full_landscape(rows, as_of="2026-10-05")
    h100 = next(card for card in full["cards"] if card["id"] == "H100")
    weeks = h100["weekly"]["weeks"]
    assert len(weeks) == 2
    assert weeks[0]["index"] == 100.0
    assert weeks[0]["vintage"] == "final"
    assert weeks[0]["status"] == "thin"  # 5 providers: computed but not headline-grade
    assert weeks[1]["index"] > 100.0  # all five matched prices rose
    assert weeks[1]["linkPairs"] == 5
    receipt = h100["weekly"]["receipts"][weeks[0]["isoWeek"]]
    assert len(receipt["included"]) == 5
    assert receipt["excludedQuoteRowsByMarket"] == {"community": 1}
    assert any(item["rule"] == "market_not_on_demand" for item in receipt["excluded"])
    assert all(item["sourceUrl"].startswith("https://example.com/") for item in receipt["included"])


def test_weekly_index_excludes_provider_not_confirmed_within_48h():
    rows = [
        _offer("2026-09-21", "a", 4.0),
        _offer("2026-09-24", "b", 5.0),
        _offer("2026-09-24", "c", 6.0),
        _offer("2026-09-24", "d", 7.0),
        _offer("2026-09-24", "e", 8.0),
    ]
    full = full_landscape(rows, as_of="2026-09-28")
    h100 = next(card for card in full["cards"] if card["id"] == "H100")
    receipt = h100["weekly"]["receipts"]["2026-W39"]
    assert all(item["providerId"] != "a" for item in receipt["included"])
    assert receipt["notConfirmed48h"] == 1
    assert any(item["providerId"] == "a" and item["rule"] == "not_confirmed_48h" for item in receipt["excluded"])
    assert receipt["providerCount"] == 4


def test_weekly_index_status_thin_and_published():
    thin = full_landscape([_offer("2026-09-27", f"p{i}", 5.0) for i in range(4)], as_of="2026-09-28")
    thin_week = next(card for card in thin["cards"] if card["id"] == "H100")["weekly"]["latest"]
    assert thin_week["status"] == "thin"
    assert thin_week["index"] == 100.0

    published = full_landscape([_offer("2026-09-27", f"p{i}", 5.0) for i in range(8)], as_of="2026-09-28")
    published_week = next(card for card in published["cards"] if card["id"] == "H100")["weekly"]["latest"]
    assert published_week["status"] == "published"


def test_weekly_index_uses_latest_day_not_week_median():
    """A provider that moved mid-week must enter the week at its latest read, not a week-wide median."""
    rows = [
        _offer("2026-09-21", "a", 4.0),
        _offer("2026-09-22", "a", 6.0),
        _offer("2026-09-21", "b", 5.0),
        _offer("2026-09-21", "c", 6.0),
        _offer("2026-09-21", "d", 7.0),
        _offer("2026-09-21", "e", 8.0),
    ]
    full = full_landscape(rows, as_of="2026-09-28")
    h100 = next(card for card in full["cards"] if card["id"] == "H100")
    receipt = h100["weekly"]["receipts"]["2026-W39"]
    a = next(item for item in receipt["included"] if item["providerId"] == "a")
    assert a["value"] == 6.0
    assert a["date"] == "2026-09-22"
    assert a["quotes"] == 1


def test_cheapest_and_range_use_raw_quotes_not_provider_medians():
    rows = [
        _offer("2026-09-27", "a", 1.0),
        _offer("2026-09-27", "a", 2.0),
        _offer("2026-09-27", "a", 3.0),
        _offer("2026-09-27", "b", 5.0),
        _offer("2026-09-27", "c", 6.0),
        _offer("2026-09-27", "d", 7.0),
    ]
    full = full_landscape(rows, as_of="2026-09-27")
    latest = next(card for card in full["cards"] if card["id"] == "H100")["markets"]["on_demand"]["latest"]
    assert latest["value"] == 5.5  # provider medians 2,5,6,7
    assert latest["cheapestValue"] == 1.0
    assert latest["cheapestProvider"] == "A"
    assert latest["low"] == 1.0
    assert latest["high"] == 7.0
    assert latest["thin"] is False


def test_old_index_age_is_visible():
    """Use a synthetic old week; do not tie this test to the current GH200 snapshot."""
    rows = []
    for day in ("2026-07-13", "2026-07-20"):
        for provider in ("a", "b", "c", "d"):
            rows.append(_offer(day, provider, 5.0))
    full = full_landscape(rows, as_of="2026-10-29", built_at="2026-10-29")
    h100 = next(card for card in full["cards"] if card["id"] == "H100")
    assert h100["weeklyIndex"]["ageDays"] > 28
    assert h100["weeklyIndex"]["weekStart"] < "2026-10-01"


def test_source_urls_never_include_sha256(snapshot):
    for source in snapshot["sources"].values():
        for url in source.get("urls") or []:
            assert str(url).startswith(("http://", "https://")), f"bad source URL: {url}"


def test_public_payloads_are_machine_readable(snapshot):
    full = full_landscape(json.loads((ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json").read_text(encoding="utf-8"))["rows"])
    prices = public_prices(full)
    assert prices["count"] == len(prices["quotes"]) > 0
    assert all({"card_id", "market", "risk", "price_scope", "usd_per_gpu_hour", "source_url", "quotes"} <= set(row) for row in prices["quotes"])
    gpus = public_gpus(full)
    assert gpus["count"] == len(gpus["gpus"]) >= 8
    assert "thin" in next(card for card in gpus["gpus"] if card["id"] == "H100")["markets"]["on_demand"]
    providers = public_providers(full)
    assert providers["count"] == len(providers["providers"]) > 0
    index = public_index(full)
    assert index["receipt_retention"] == "latest_week_only"
    assert len(index["cards"]["H100"]["receipts"]) == 1
    receipt = next(iter(index["cards"]["H100"]["receipts"].values()))
    assert receipt["methodologyVersion"] == index["methodology_version"]
    change = public_changelog(full)
    assert change["count"] > 0
    manifest = public_manifest(full, "2026-11-03T00:00:00Z")
    assert {item["path"] for item in manifest["files"]} >= {"prices.json", "price-index.json", "changelog.json"}
    trimmed = trim_landscape(full)
    assert "receipts" not in json.dumps(trimmed)


def test_write_public_data(tmp_path, snapshot):
    written = write_public_data(snapshot, out_dir=tmp_path)
    for name in ("prices.json", "gpus.json", "providers.json", "price-index.json", "changelog.json", "manifest.json"):
        path = tmp_path / name
        assert path.exists() and path.stat().st_size > 0
        assert written[name].endswith(name)
    assert (tmp_path / "price-index" / "h100.json").exists()
    assert (tmp_path / "price-index" / "rtx-pro-6000.json").exists()
    assert json.loads((tmp_path / "prices.json").read_text(encoding="utf-8"))["count"] > 0


def test_landscape_is_embedded_in_the_page(snapshot):
    html = build_html(snapshot)
    assert 'id="landscape"' in html
    assert 'id="landscape-card"' in html
    assert 'id="landscape-market"' in html
    assert "gpuLandscape" in html
    assert "data/price-index.json" in html
