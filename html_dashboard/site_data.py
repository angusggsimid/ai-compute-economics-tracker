"""Data slices for the standalone static site.

Every value in these files is derived from the two committed inputs:

* ``full``: ``gpu_landscape.full_landscape(neocloud_rows)`` (own panel, receipts included)
* ``external``: ``gpu_external.load_external()`` (GPU Economy snapshot)

No prices or provider lists are hard-coded here.  The slices are written under
``<public>/data`` so the pages can fetch them with relative URLs.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:  # package import path (html_dashboard.site_data)
    from .gpu_external import CARD_BY_EXT_GPU, build_crosscheck
    from .gpu_landscape import index_slug, public_prices, public_providers
except ImportError:  # script import path used by the test suite
    from gpu_external import CARD_BY_EXT_GPU, build_crosscheck  # type: ignore
    from gpu_landscape import index_slug, public_prices, public_providers  # type: ignore


# Daily series fields kept in the card slice.  Everything else (source market
# id, low/high raw quotes, synthetic-median flag, moving average) is derivable
# or duplicated and made the per-card files needlessly large.
_SERIES_FIELDS = (
    "date",
    "value",
    "p25",
    "p75",
    "providerCount",
    "quoteCount",
    "thin",
    "cheapestValue",
    "cheapestProvider",
    "cheapestProviderId",
    "cheapestSourceUrl",
)

_WEEK_FIELDS = (
    "isoWeek",
    "weekStart",
    "vintage",
    "status",
    "median",
    "p25",
    "p75",
    "providerCount",
    "index",
    "linkPairs",
    "withheldReason",
)

_WEEKLY_INDEX_FIELDS = (
    "weekStart",
    "isoWeek",
    "vintage",
    "status",
    "median",
    "p25",
    "p75",
    "providerCount",
    "index",
    "linkPairs",
    "withheldReason",
    "ageDays",
)


def card_slug(card_id: str) -> str:
    """Stable URL slug for a card (``RTX PRO 6000`` -> ``rtx-pro-6000``)."""
    return index_slug(card_id)


def provider_slug(layer: str, provider_id: str) -> str:
    """``own-runpod`` / ``ext-runpod``; the layer decides the prefix."""
    key = str(layer or "").strip().lower()
    if key == "own":
        prefix = "own"
    elif key in ("gpueconomy", "external", "ext"):
        prefix = "ext"
    else:
        raise ValueError(f"unknown provider layer: {layer!r}")
    slug = re.sub(r"[^a-z0-9]+", "-", str(provider_id or "").lower()).strip("-")
    if not slug:
        raise ValueError(f"empty provider id for layer {layer!r}")
    return f"{prefix}-{slug}"


def _round6(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    return None


def _market_summary(market: Dict[str, Any]) -> Dict[str, Any]:
    latest = market.get("latest") or {}
    return {
        "label": market.get("label"),
        "status": market.get("status") or "no_data",
        "risk": market.get("risk"),
        "price_scope": market.get("scope"),
        "median": _round6(latest.get("value")),
        "p25": _round6(latest.get("p25")),
        "p75": _round6(latest.get("p75")),
        "cheapest": _round6(latest.get("cheapestValue")),
        "cheapest_provider": latest.get("cheapestProvider"),
        "provider_count": int(latest.get("providerCount") or 0),
        "thin": bool(latest.get("thin")) if latest else True,
        "date": latest.get("date"),
        "change_7d_pct": market.get("change7dPct"),
    }


def _weekly_index_summary(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    latest = card.get("weeklyIndex")
    if not latest:
        return None
    return {field: latest.get(field) for field in _WEEKLY_INDEX_FIELDS}


def _card_summary(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": card.get("id"),
        "slug": card_slug(card.get("id") or ""),
        "name": card.get("name"),
        "vram_gb": card.get("vramGb"),
        "family": card.get("family"),
        "as_of": card.get("asOf"),
        "status": card.get("status"),
        "median": _round6(card.get("median")),
        "p25": _round6(card.get("p25")),
        "p75": _round6(card.get("p75")),
        "cheapest": _round6(card.get("cheapest")),
        "cheapest_provider": card.get("cheapestProvider"),
        "provider_count": int(card.get("providerCount") or 0),
        "change_7d_pct": card.get("change7dPct"),
        "weekly_index": _weekly_index_summary(card),
        "markets": {
            market_id: _market_summary(market)
            for market_id, market in (card.get("markets") or {}).items()
        },
    }


def _external_providers(external: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((external.get("providers") or {}).get("providers") or [])


def _external_prices(external: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((external.get("prices") or {}).get("prices") or [])


def _external_cards_by_provider(prices: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    cards: Dict[str, set] = defaultdict(set)
    for row in prices:
        card_id = CARD_BY_EXT_GPU.get(str(row.get("gpu_id") or ""))
        provider_id = str(row.get("provider_id") or "")
        if card_id and provider_id:
            cards[provider_id].add(card_id)
    return {provider_id: sorted(values) for provider_id, values in cards.items()}


def _external_summary(
    provider: Dict[str, Any], cards_by_provider: Dict[str, List[str]]
) -> Dict[str, Any]:
    provider_id = str(provider.get("id") or "")
    return {
        "id": provider_id,
        "slug": provider_slug("gpueconomy", provider_id),
        "name": provider.get("name") or provider_id,
        "type": provider.get("type"),
        "source_kind": provider.get("source_kind"),
        "scraped": bool(provider.get("scraped")),
        "current_quotes": int(provider.get("current_quotes") or 0),
        "cards": cards_by_provider.get(provider_id, []),
        "website": provider.get("website"),
        "pricing_page": provider.get("pricing_page"),
    }


def _external_metadata(external: Dict[str, Any]) -> Dict[str, Any]:
    metadata = external.get("metadata") or {}
    return {
        "source": metadata.get("source") or "gpueconomy",
        "source_url": metadata.get("source_url"),
        "license": metadata.get("license"),
        "license_url": metadata.get("license_url"),
        "attribution": metadata.get("attribution"),
        "methodology_version": metadata.get("methodology_version"),
        "data_updated_at": metadata.get("data_updated_at"),
        "retrieved_at": metadata.get("fetched_at"),
    }


def build_site_index(full: Dict[str, Any], external: Dict[str, Any]) -> Dict[str, Any]:
    """The small index every page loads first: card + provider summaries."""
    prices = _external_prices(external)
    cards_by_provider = _external_cards_by_provider(prices)

    own_prices = public_prices(full)
    own_providers = public_providers(full)["providers"]
    own = [
        {
            "id": provider.get("id"),
            "slug": provider_slug("own", provider.get("id") or ""),
            "name": provider.get("name"),
            "cards": provider.get("cards") or [],
            "markets": provider.get("markets") or [],
            "quotes": int(provider.get("quotes") or 0),
            "cheapest": provider.get("cheapest"),
        }
        for provider in own_providers
    ]

    external_providers = [
        provider
        for provider in _external_providers(external)
        if int(provider.get("current_quotes") or 0) > 0
    ]
    external_summaries = sorted(
        (_external_summary(provider, cards_by_provider) for provider in external_providers),
        key=lambda item: (str(item.get("name") or "").lower(), item.get("id") or ""),
    )

    return {
        "generated_at": full.get("builtAt") or full.get("asOf"),
        "as_of": full.get("asOf"),
        "data_age_days": full.get("dataAgeDays"),
        "methodology_version": full.get("methodologyVersion"),
        "external": _external_metadata(external),
        "counts": {
            "cards": len(full.get("cards") or []),
            "own_providers": len(own),
            "external_providers": len(external_summaries),
            "own_quotes": int(own_prices.get("count") or len(own_prices.get("quotes") or [])),
            "external_quotes": len(prices),
        },
        "markets": [
            {
                "id": market.get("id"),
                "label": market.get("label"),
                "short": market.get("short"),
                "risk": market.get("risk"),
                "scope": market.get("scope"),
                "note": market.get("note"),
            }
            for market in full.get("markets") or []
        ],
        "cards": [_card_summary(card) for card in full.get("cards") or []],
        "providers": {"own": own, "external": external_summaries},
    }


def _trim_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Full card without weekly receipts or duplicated cheapest series."""
    trimmed = {key: value for key, value in card.items() if key != "weekly"}
    markets: Dict[str, Any] = {}
    for market_id, market in (card.get("markets") or {}).items():
        node = {key: value for key, value in market.items() if key != "cheapestSeries"}
        node["series"] = [
            {field: point.get(field) for field in _SERIES_FIELDS if field in point}
            for point in market.get("series") or []
        ]
        latest = market.get("latest")
        if latest:
            latest = dict(latest)
            offers = latest.pop("providers", None)
            if offers is not None:
                latest["offers"] = offers
            node["latest"] = latest
        markets[market_id] = node
    trimmed["markets"] = markets
    return trimmed


def _external_card_summary(crosscheck: Dict[str, Any], card_id: str) -> Dict[str, Any]:
    rows = [
        row
        for row in crosscheck.get("rows") or []
        if row.get("card_id") == card_id
    ]
    markets = {
        row.get("market"): {
            "ext_gpu_id": row.get("match_id"),
            "ext_median": row.get("ext_median"),
            "ext_providers": row.get("ext_providers"),
            "ext_scraped_at": row.get("ext_scraped_at"),
            "ext_median_published": row.get("ext_median_published"),
            "ext_benchmark_id": row.get("ext_benchmark_id"),
            "ext_benchmark_median": row.get("ext_benchmark_median"),
            "diff_pct": row.get("diff_pct"),
            "overlap_count": row.get("overlap_count"),
            "coverage": row.get("coverage"),
            "comparable": row.get("comparable"),
            "note": row.get("note"),
        }
        for row in rows
    }
    metadata = {
        "source": crosscheck.get("source") or "gpueconomy",
        "source_url": crosscheck.get("source_url"),
        "prices_source_url": crosscheck.get("prices_source_url"),
        "license": crosscheck.get("license"),
        "license_url": crosscheck.get("license_url"),
        "attribution": crosscheck.get("attribution"),
        "citation": crosscheck.get("citation"),
        "methodology_version": crosscheck.get("methodology_version"),
        "data_updated_at": crosscheck.get("data_updated_at"),
        "retrieved_at": crosscheck.get("retrieved_at"),
        "as_of": crosscheck.get("as_of"),
        "ext_as_of": crosscheck.get("ext_as_of"),
    }
    return {**metadata, "markets": markets}


def build_card_slice(
    full: Dict[str, Any], card: Dict[str, Any], crosscheck: Dict[str, Any]
) -> Dict[str, Any]:
    """One card page payload: trimmed card, weekly weeks, crosscheck, external."""
    card_id = card.get("id")
    weeks = [
        {field: week.get(field) for field in _WEEK_FIELDS}
        for week in (card.get("weekly") or {}).get("weeks") or []
    ]
    return {
        "id": card_id,
        "slug": card_slug(card_id or ""),
        "as_of": card.get("asOf") or full.get("asOf"),
        "methodology_version": full.get("methodologyVersion"),
        "card": _trim_card(card),
        "weeks": weeks,
        "crosscheck": [
            row
            for row in crosscheck.get("rows") or []
            if row.get("card_id") == card_id
        ],
        "external": _external_card_summary(crosscheck, card_id or ""),
    }


def build_own_provider_slice(full: Dict[str, Any], provider: Dict[str, Any]) -> Dict[str, Any]:
    """Own provider summary plus every latest quote for that provider."""
    provider_id = provider.get("id")
    quotes = [
        dict(quote)
        for quote in public_prices(full).get("quotes") or []
        if quote.get("provider_id") == provider_id
    ]
    quotes.sort(
        key=lambda row: (
            str(row.get("card_id") or ""),
            str(row.get("market") or ""),
            float(row.get("usd_per_gpu_hour") or 0),
        )
    )
    return {
        "layer": "own",
        "as_of": full.get("asOf"),
        "provider": provider,
        "quotes": quotes,
    }


def _external_quote(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_layer": "gpueconomy",
        "provider_id": row.get("provider_id"),
        "provider": row.get("provider"),
        "gpu_id": row.get("gpu_id"),
        "gpu": row.get("gpu"),
        "market": row.get("market"),
        "price_type": row.get("price_type"),
        "price_scope": row.get("price_scope"),
        "risk": row.get("risk"),
        "usd_per_gpu_hour": _round6(row.get("usd_per_gpu_hour")),
        "listed_currency": row.get("listed_currency"),
        "fx_rate": row.get("fx_rate"),
        "gpu_count": row.get("gpu_count"),
        "region": row.get("region"),
        "source_url": row.get("source_url"),
        "scraped_at": row.get("scraped_at"),
        "status": row.get("status"),
    }


def build_ext_provider_slice(
    external: Dict[str, Any], provider: Dict[str, Any]
) -> Dict[str, Any]:
    """GPU Economy provider record plus every current quote for that provider."""
    provider_id = provider.get("id")
    quotes = [
        _external_quote(row)
        for row in _external_prices(external)
        if row.get("provider_id") == provider_id
    ]
    quotes.sort(
        key=lambda row: (
            str(row.get("gpu_id") or ""),
            str(row.get("market") or ""),
            float(row.get("usd_per_gpu_hour") or 0),
        )
    )
    return {
        "layer": "gpueconomy",
        "external": _external_metadata(external),
        "provider": provider,
        "quotes": quotes,
    }


def _external_prices_payload(external: Dict[str, Any]) -> Dict[str, Any]:
    rows = [_external_quote(row) for row in _external_prices(external)]
    rows.sort(
        key=lambda row: (
            str(row.get("provider_id") or ""),
            str(row.get("gpu_id") or ""),
            str(row.get("market") or ""),
            float(row.get("usd_per_gpu_hour") or 0),
        )
    )
    return {
        "name": "AI Compute Economics - GPU Economy external quotes",
        **_external_metadata(external),
        "as_of": str((external.get("metadata") or {}).get("data_updated_at") or "")[:10] or None,
        "count": len(rows),
        "fields": list(_external_quote({}).keys()),
        "prices": rows,
    }


def _external_providers_payload(external: Dict[str, Any]) -> Dict[str, Any]:
    cards_by_provider = _external_cards_by_provider(_external_prices(external))
    providers = []
    for provider in _external_providers(external):
        base = _external_summary(provider, cards_by_provider)
        providers.append(
            {
                **base,
                "fees": provider.get("fees") or [],
                "notes": provider.get("notes"),
                "models_tracked": provider.get("models_tracked"),
                "summary": provider.get("summary"),
                "regions": provider.get("regions") or [],
            }
        )
    providers.sort(key=lambda item: (str(item.get("name") or "").lower(), item.get("id") or ""))
    return {
        "name": "AI Compute Economics - GPU Economy external providers",
        **_external_metadata(external),
        "count": len(providers),
        "providers": providers,
    }


def _dump(path: Path, payload: Any, compact: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=1)
    path.write_text(text + "\n", encoding="utf-8")
    return str(path)


def _prune_stale_json(directory: Path, expected: set[str]) -> List[str]:
    """Remove generated ``*.json`` files that are absent from ``expected``.

    The caller passes only the two generated directories (``data/cards`` and
    ``data/providers``); non-JSON files, subdirectories and every other data
    directory are left untouched.  Deleting the set difference makes a shrink
    in the source data remove its old slices instead of leaving them fetchable.
    """
    if not directory.is_dir():
        return []
    existing = {
        path.name
        for path in directory.glob("*.json")
        if path.is_file()
    }
    removed: List[str] = []
    for name in sorted(existing - expected):
        path = directory / name
        path.unlink()
        removed.append(str(path))
    return removed


def write_site_data(
    public_dir: Path, full: Dict[str, Any], external: Dict[str, Any]
) -> Dict[str, str]:
    """Write every static-site data slice under ``<public_dir>/data``.

    Stale ``*.json`` files in the generated ``data/cards`` and ``data/providers``
    directories are removed before writing, so a shrinking source snapshot does
    not leave fetchable old slices behind.  Other files and directories are not
    touched.

    Returns ``{relative_path: absolute_path}`` for the written files.
    """
    public_dir = Path(public_dir)
    data_dir = public_dir / "data"
    cards_dir = data_dir / "cards"
    providers_dir = data_dir / "providers"
    external_dir = data_dir / "external"

    written: Dict[str, str] = {}

    def record(path: Path | str) -> None:
        path = Path(path)
        written[path.relative_to(public_dir).as_posix()] = str(path)

    crosscheck = build_crosscheck(full, external)
    index = build_site_index(full, external)
    expected_cards = {
        f"{card_slug(summary['id'])}.json" for summary in index["cards"]
    }
    expected_providers = {
        f"{provider['slug']}.json" for provider in index["providers"]["own"]
    }
    expected_providers.update(
        f"{provider['slug']}.json" for provider in index["providers"]["external"]
    )
    _prune_stale_json(cards_dir, expected_cards)
    _prune_stale_json(providers_dir, expected_providers)
    record(_dump(data_dir / "site-index.json", index))

    cards_by_id = {card.get("id"): card for card in full.get("cards") or []}
    for summary in index["cards"]:
        card = cards_by_id[summary["id"]]
        path = cards_dir / f"{card_slug(summary['id'])}.json"
        record(_dump(path, build_card_slice(full, card, crosscheck)))

    for provider in index["providers"]["own"]:
        path = providers_dir / f"{provider['slug']}.json"
        record(_dump(path, build_own_provider_slice(full, provider)))

    full_external_providers = {
        str(provider.get("id")): provider for provider in _external_providers(external)
    }
    for provider in index["providers"]["external"]:
        source = dict(full_external_providers[provider["id"]])
        source["slug"] = provider["slug"]
        source["cards"] = provider["cards"]
        path = providers_dir / f"{provider['slug']}.json"
        record(_dump(path, build_ext_provider_slice(external, source)))

    record(_dump(external_dir / "prices.json", _external_prices_payload(external), compact=True))
    record(_dump(external_dir / "providers.json", _external_providers_payload(external)))

    return written
