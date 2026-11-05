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
    market = next(card for card in full["cards"] if card["id"] == "H100")["markets"]["on_demand"]
    latest = market["latest"]
    assert latest["value"] == 5.5  # provider medians 2,5,6,7
    assert latest["cheapestValue"] == 1.0
    assert latest["cheapestProvider"] == "A"
    assert latest["low"] == 1.0
    assert latest["high"] == 7.0
    assert latest["thin"] is False
    # The cheapest series is the raw quote minimum, not a provider median.
    assert market["cheapestSeries"] == [{
        "date": "2026-09-27",
        "value": 1.0,
        "provider": "A",
        "providerId": "a",
        "sourceUrl": "https://example.com/a",
    }]
    provider_a = next(offer for offer in latest["providers"] if offer["providerId"] == "a")
    assert provider_a["value"] == 2.0  # median of 1,2,3: must not be used by cheapest


def test_cheapest_source_url_matches_the_lowest_raw_quote():
    low = {**_offer("2026-09-27", "a", 1.0), "sourceUrl": "https://example.com/a-low"}
    mid = {**_offer("2026-09-27", "a", 2.0), "sourceUrl": "https://example.com/a-mid"}
    high = {**_offer("2026-09-27", "a", 9.0), "sourceUrl": "https://example.com/a-high"}
    rows = [
        low, mid, high,
        _offer("2026-09-27", "b", 4.0),
        _offer("2026-09-27", "c", 6.0),
        _offer("2026-09-27", "d", 7.0),
    ]
    full = full_landscape(rows, as_of="2026-09-27")
    market = next(card for card in full["cards"] if card["id"] == "H100")["markets"]["on_demand"]
    latest = market["latest"]

    assert latest["cheapestValue"] == 1.0
    assert latest["cheapestSourceUrl"] == "https://example.com/a-low"
    assert market["cheapestSeries"][0]["sourceUrl"] == "https://example.com/a-low"

    provider_a = next(offer for offer in latest["providers"] if offer["providerId"] == "a")
    assert provider_a["value"] == 2.0
    assert provider_a["sourceUrl"] == "https://example.com/a-mid"


def test_trim_landscape_moves_providers_to_offers_and_keeps_new_series():
    rows = []
    for day in ("2026-08-10", "2026-08-11"):
        rows.append(_offer(day, "a", 4.0))
        rows.append(_offer(day, "b", 6.0))
    full = full_landscape(rows, as_of="2026-08-11")
    full_card = next(card for card in full["cards"] if card["id"] == "H100")
    trimmed = trim_landscape(full)
    card = next(item for item in trimmed["cards"] if item["id"] == "H100")
    market = card["markets"]["on_demand"]

    assert "providers" not in market["latest"]
    assert [offer["providerId"] for offer in market["latest"]["offers"]] == ["a", "b"]
    assert market["latest"]["offers"] == full_card["markets"]["on_demand"]["latest"]["providers"]
    # The page derives the cheapest line from series points; no duplicate array.
    assert "cheapestSeries" not in market
    assert [point["cheapestValue"] for point in market["series"]] == [4.0, 4.0]
    assert "cheapestSeries" not in json.dumps(trimmed)
    assert card["monthly"] == full_card["monthly"]

    assert card["markets"]["serverless"]["latest"] is None

    # The full payload still feeds public prices/providers from providers.
    assert "providers" in full_card["markets"]["on_demand"]["latest"]
    assert "offers" not in full_card["markets"]["on_demand"]["latest"]


def test_public_prices_have_honest_null_schema_fields():
    rows = [_offer("2026-09-27", "a", 4.0), _offer("2026-09-27", "b", 5.0)]
    full = full_landscape(rows, as_of="2026-09-27")
    quotes = public_prices(full)["quotes"]
    assert quotes
    expected_keys = {
        "source_layer", "region", "gpu_count", "listed_price", "listed_currency",
        "fx_rate", "fx_date", "listed_unit", "scraped_at", "last_confirmed_at",
        "listed_since", "change_7d_pct", "source_kind",
    }
    for quote in quotes:
        assert expected_keys <= set(quote)
        assert quote["source_layer"] == "own"
        assert quote["listed_currency"] == "USD"
        assert quote["fx_rate"] == 1.0
        assert quote["listed_unit"] == "USD/GPU-hour"
        assert quote["last_confirmed_at"] == "2026-09-27"
        for key in (
            "region", "gpu_count", "listed_price", "fx_date", "scraped_at",
            "listed_since", "change_7d_pct", "source_kind",
        ):
            assert quote[key] is None, f"{key} must stay null when the source has no value"


EMPTY_CHEAPEST_SERIES = {
    "dates": [],
    "values": [],
    "provider_ids": [],
    "source_urls": [],
    "source_idx": [],
}


def _assert_cheapest_series_matches(full_market, public_market):
    expected = full_market.get("cheapestSeries", [])
    series = public_market["cheapest_series"]
    assert set(series) == {"dates", "values", "provider_ids", "source_urls", "source_idx"}
    assert len(series["dates"]) == len(series["values"]) == len(series["provider_ids"]) == len(series["source_idx"]) == len(expected)
    assert series["dates"] == [point["date"] for point in expected]
    assert series["values"] == [point["value"] for point in expected]
    assert series["provider_ids"] == [point["providerId"] for point in expected]
    assert [series["source_urls"][index] for index in series["source_idx"]] == [point["sourceUrl"] for point in expected]


def test_public_gpus_cheapest_series_covers_every_data_market():
    rows = [
        _offer("2026-09-26", "a", 4.0),
        _offer("2026-09-27", "a", 3.0),
        _offer("2026-09-27", "b", 5.0),
        _offer("2026-09-27", "c", 0.5, kind="spot"),
    ]
    full = full_landscape(rows, as_of="2026-09-27")
    gpus = public_gpus(full)
    h100 = next(card for card in gpus["gpus"] if card["id"] == "H100")

    on_demand = h100["markets"]["on_demand"]
    assert on_demand["cheapest"] == 3.0
    assert on_demand["cheapest_series"] == {
        "dates": ["2026-09-26", "2026-09-27"],
        "values": [4.0, 3.0],
        "provider_ids": ["a", "a"],
        "source_urls": ["https://example.com/a"],
        "source_idx": [0, 0],
    }

    spot = h100["markets"]["spot"]
    assert spot["cheapest"] == 0.5
    assert spot["cheapest_series"] == {
        "dates": ["2026-09-27"],
        "values": [0.5],
        "provider_ids": ["c"],
        "source_urls": ["https://example.com/c"],
        "source_idx": [0],
    }

    for market_id in ("reserved", "community", "marketplace", "serverless"):
        market = h100["markets"][market_id]
        assert market["cheapest"] is None
        assert market["cheapest_series"] == EMPTY_CHEAPEST_SERIES
    assert "cheapest_series_scope" not in gpus


def test_public_manifest_documents_field_availability_and_new_definitions():
    full = full_landscape([_offer("2026-09-27", "a", 4.0)], as_of="2026-09-27")
    manifest = public_manifest(full, "2026-11-04T00:00:00Z")
    availability = manifest["field_availability"]
    assert set(availability) == {"native", "derived", "unavailable"}
    assert {"date", "provider_id", "series", "usd_per_gpu_hour", "source_url"} <= set(availability["native"])
    for key in ("region", "gpu_count", "listed_price", "fx_date", "scraped_at", "listed_since", "source_kind"):
        assert key in availability["unavailable"]
    assert "monthly" in manifest["definitions"]
    assert "cheapest_series" in manifest["definitions"]
    assert "keep their last reading" in manifest["definitions"]["status"]
    assert "weekly index only includes readings confirmed within 2 days" in manifest["definitions"]["status"]
    assert manifest["methodology_version"] == "2026-11-04.1"


def _panel_window_rows(providers, window_days):
    rows = []
    for index in range(providers):
        for day in window_days[:-1]:  # 13 of 14 days clears the >=13/14 test
            rows.append(_offer(day, f"p{index}", 2.0 + index))
    return rows


def test_monthly_panel_is_fixed_and_first_month_withheld():
    rows = []
    # The August panel window is the 14 days immediately before Aug 1.
    window_days = [f"2026-07-{day:02d}" for day in range(18, 32)]  # Jul 18..Jul 31
    rows.extend(_panel_window_rows(9, window_days))
    # p9 only covers 10 window days, so it never enters the fixed panel.
    for day in window_days[-10:]:
        rows.append(_offer(day, "p9", 0.1))
    # August: the nine panel providers quote every day, p9 keeps quoting low.
    for day_number in range(1, 32):
        for index in range(9):
            rows.append(_offer(f"2026-08-{day_number:02d}", f"p{index}", 2.0 + index))
        rows.append(_offer(f"2026-08-{day_number:02d}", "p9", 0.1))

    full = full_landscape(rows, as_of="2026-08-31")
    monthly = next(card for card in full["cards"] if card["id"] == "H100")["monthly"]
    assert [item["month"] for item in monthly] == ["2026-07", "2026-08"]

    july = monthly[0]
    assert july["status"] == "withheld"
    assert july["value"] is None
    assert july["panel"] == []
    assert "2026-06-17..2026-06-30" in july["withheldReason"]
    assert july["vintage"] == "final"
    assert july["isComplete"] is True

    august = monthly[1]
    assert august["status"] == "published"
    assert august["panelCount"] == 9
    assert august["panel"] == [f"p{index}" for index in range(9)]
    assert "p9" not in august["panel"]
    assert august["coverageDays"] == 31
    assert august["coveragePct"] == 100.0
    # Median of the fixed panel 2..10 is 6.0; including the low p9 quote would give 5.5.
    assert august["value"] == pytest.approx(6.0)
    assert august["withheldReason"] is None
    assert august["vintage"] == "provisional"
    assert august["isComplete"] is False
    assert august["methodologyVersion"] == "2026-11-04.1"


@pytest.mark.parametrize("valid_days, expected_status", [(22, "withheld"), (23, "published")])
def test_monthly_coverage_threshold(valid_days, expected_status):
    window_days = [f"2026-08-{day:02d}" for day in range(18, 32)]  # Aug 18..31
    rows = _panel_window_rows(9, window_days)
    for day_number in range(1, valid_days + 1):
        for index in range(9):
            rows.append(_offer(f"2026-09-{day_number:02d}", f"p{index}", 4.0))

    full = full_landscape(rows, as_of="2026-09-30")
    monthly = next(card for card in full["cards"] if card["id"] == "H100")["monthly"]
    august = next(item for item in monthly if item["month"] == "2026-08")
    september = next(item for item in monthly if item["month"] == "2026-09")
    assert august["vintage"] == "final"
    assert august["isComplete"] is True
    assert september["vintage"] == "provisional"
    assert september["isComplete"] is False
    assert september["panelCount"] == 9
    assert september["coverageDays"] == valid_days
    assert september["daysInMonth"] == 30
    assert september["coveragePct"] == round(valid_days * 100.0 / 30, 1)
    assert september["status"] == expected_status
    if expected_status == "withheld":
        assert september["value"] is None
        assert "below 75%" in september["withheldReason"]
    else:
        assert september["value"] == 4.0
        assert september["withheldReason"] is None


def test_monthly_withholds_panel_below_eight():
    window_days = [f"2026-08-{day:02d}" for day in range(18, 32)]  # Aug 18..31
    rows = _panel_window_rows(5, window_days)
    for day_number in range(1, 31):
        for index in range(5):
            rows.append(_offer(f"2026-09-{day_number:02d}", f"p{index}", 4.0))

    full = full_landscape(rows, as_of="2026-09-30")
    monthly = next(card for card in full["cards"] if card["id"] == "H100")["monthly"]
    september = next(item for item in monthly if item["month"] == "2026-09")
    assert september["panelCount"] == 5
    assert september["status"] == "withheld"
    assert september["value"] is None
    assert "needs >=8" in september["withheldReason"]


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
    h100_gpus = next(card for card in gpus["gpus"] if card["id"] == "H100")
    assert "thin" in h100_gpus["markets"]["on_demand"]
    assert h100_gpus["monthly"]
    assert h100_gpus["markets"]["on_demand"]["cheapest_series"]["dates"]
    assert h100_gpus["markets"]["spot"]["cheapest_series"]["dates"]
    assert "cheapest_series_scope" not in gpus

    full_cards = {card["id"]: card for card in full["cards"]}
    data_markets = 0
    for card in gpus["gpus"]:
        full_card = full_cards[card["id"]]
        for market_id, full_market in full_card["markets"].items():
            public_market = card["markets"][market_id]
            _assert_cheapest_series_matches(full_market, public_market)
            if full_market.get("latest"):
                data_markets += 1
                assert public_market["cheapest_series"]["dates"]
            else:
                assert public_market["cheapest_series"] == EMPTY_CHEAPEST_SERIES
    assert data_markets >= 50  # current snapshot has 53 data card x market combinations
    providers = public_providers(full)
    assert providers["count"] == len(providers["providers"]) > 0
    index = public_index(full)
    assert index["receipt_retention"] == "latest_week_only"
    assert len(index["cards"]["H100"]["receipts"]) == 1
    assert index["cards"]["H100"]["monthly"] == h100_gpus["monthly"]
    assert "immediately before" in index["monthly_method"]
    assert "24th" not in index["monthly_method"]
    receipt = next(iter(index["cards"]["H100"]["receipts"].values()))
    assert receipt["methodologyVersion"] == index["methodology_version"]
    change = public_changelog(full)
    assert change["count"] > 0
    manifest = public_manifest(full, "2026-11-03T00:00:00Z")
    assert {item["path"] for item in manifest["files"]} >= {"prices.json", "price-index.json", "changelog.json"}
    assert set(manifest["field_availability"]) == {"native", "derived", "unavailable"}
    trimmed = trim_landscape(full)
    assert "receipts" not in json.dumps(trimmed)
    trimmed_h100 = next(card for card in trimmed["cards"] if card["id"] == "H100")
    assert trimmed_h100["monthly"] == h100_gpus["monthly"]
    assert trimmed_h100["markets"]["on_demand"]["latest"]["offers"]
    assert "providers" not in trimmed_h100["markets"]["on_demand"]["latest"]


def test_write_public_data(tmp_path, snapshot):
    written = write_public_data(snapshot, out_dir=tmp_path)
    for name in ("prices.json", "gpus.json", "providers.json", "price-index.json", "changelog.json", "manifest.json"):
        path = tmp_path / name
        assert path.exists() and path.stat().st_size > 0
        assert written[name].endswith(name)
    assert (tmp_path / "price-index" / "h100.json").exists()
    assert (tmp_path / "price-index" / "rtx-pro-6000.json").exists()
    assert json.loads((tmp_path / "prices.json").read_text(encoding="utf-8"))["count"] > 0
    h100_slice = json.loads((tmp_path / "price-index" / "h100.json").read_text(encoding="utf-8"))
    assert h100_slice["cards"]["H100"]["monthly"]
    assert "monthly_method" in h100_slice


def test_landscape_is_embedded_in_the_page(snapshot):
    html = build_html(snapshot)
    assert 'id="landscape"' in html
    assert 'id="landscape-card"' in html
    assert 'id="landscape-market"' in html
    assert "gpuLandscape" in html
    assert "data/price-index.json" in html
