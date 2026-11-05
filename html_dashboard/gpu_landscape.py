"""GPU supply landscape: per-card, per-market aggregates with weekly evidence.

The module is intentionally pure: it reads the neocloud row list and returns JSON-ready
structures.  The dashboard build embeds a trimmed copy; the public data files keep the
full weekly receipts.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import re
from statistics import median, quantiles
from typing import Any, Dict, List, Optional, Tuple


METHODOLOGY_VERSION = "2026-11-04.1"
MIN_PROVIDERS = 4
INDEX_MIN_PROVIDERS = 4
INDEX_PUBLISH_MIN = 8
INDEX_CONFIRM_DAYS = 2
MONTHLY_PANEL_WINDOW_DAYS = 14
MONTHLY_PANEL_MIN_DAYS = 13
MONTHLY_MIN_PROVIDERS = 8
MONTHLY_MIN_COVERAGE = 0.75

CARDS: List[Dict[str, Any]] = [
    {"id": "H100", "name": "H100 80GB", "vramGb": 80, "family": "Hopper"},
    {"id": "H200", "name": "H200 141GB", "vramGb": 141, "family": "Hopper"},
    {"id": "B200", "name": "B200 192GB", "vramGb": 192, "family": "Blackwell"},
    {"id": "B300", "name": "B300 288GB", "vramGb": 288, "family": "Blackwell"},
    {"id": "A100", "name": "A100 80GB", "vramGb": 80, "family": "Ampere"},
    {"id": "L40S", "name": "L40S 48GB", "vramGb": 48, "family": "Ada"},
    {"id": "RTX PRO 6000", "name": "RTX PRO 6000 96GB", "vramGb": 96, "family": "Blackwell"},
    {"id": "RTX 4090", "name": "RTX 4090 24GB", "vramGb": 24, "family": "Ada"},
    {"id": "RTX 5090", "name": "RTX 5090 32GB", "vramGb": 32, "family": "Blackwell"},
    {"id": "MI300X", "name": "MI300X 192GB", "vramGb": 192, "family": "CDNA 3"},
    {"id": "GH200", "name": "GH200 96GB", "vramGb": 96, "family": "Hopper"},
    {"id": "MI355X", "name": "MI355X 288GB", "vramGb": 288, "family": "CDNA 4"},
]

MARKETS: List[Dict[str, Any]] = [
    {
        "id": "on_demand",
        "label": "正规 on-demand",
        "short": "On-demand",
        "kinds": ("on-demand", "secure"),
        "risk": "low",
        "scope": "rate_card",
        "note": "可长期持有的挂牌价；不含 community、spot、marketplace floor。",
    },
    {
        "id": "spot",
        "label": "Spot",
        "short": "Spot",
        "kinds": ("spot",),
        "risk": "high",
        "scope": "rate_card",
        "note": "可被中途收回；价格低不等于可规划。",
    },
    {
        "id": "reserved",
        "label": "Reserved",
        "short": "Reserved",
        "kinds": ("reserved",),
        "risk": "low",
        "scope": "rate_card",
        "note": "承诺期价格；未运行也计费。",
    },
    {
        "id": "community",
        "label": "Community",
        "short": "Community",
        "kinds": ("community",),
        "risk": "high",
        "scope": "rate_card",
        "note": "第三方主机容量，可被收回；不进主中位数。",
    },
    {
        "id": "marketplace",
        "label": "Marketplace floor",
        "short": "Marketplace",
        "kinds": ("marketplace",),
        "risk": "high",
        "scope": "marketplace_floor",
        "note": "市场最低报价，随供给移动；不是 rate card。",
    },
    {
        "id": "serverless",
        "label": "Serverless",
        "short": "Serverless",
        "kinds": ("serverless",),
        "risk": "medium",
        "scope": "serverless",
        "note": "按调用/秒计费，共享容量；与整租不可直接比。",
    },
]

MARKET_BY_ID = {m["id"]: m for m in MARKETS}
KIND_TO_MARKET = {kind: m["id"] for m in MARKETS for kind in m["kinds"]}

PROVIDER_LABELS = {
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "Google Cloud",
    "oracle": "Oracle Cloud",
    "runpod": "RunPod",
    "lambda": "Lambda",
    "together": "Together AI",
    "coreweave": "CoreWeave",
    "crusoe": "Crusoe",
    "nebius": "Nebius",
    "paperspace": "Paperspace",
    "hyperstack": "Hyperstack",
    "civo": "Civo",
    "vultr": "Vultr",
    "datacrunch": "Verda",
    "massed": "Massed Compute",
    "massedcompute": "Massed Compute",
    "jarvislabs": "JarvisLabs",
    "vastai": "Vast.ai",
    "vast-ai": "Vast.ai",
    "salad": "Salad",
    "modal": "Modal",
    "baseten": "Baseten",
    "fal": "fal",
    "replicate": "Replicate",
    "hyperbolic": "Hyperbolic",
    "thundercompute": "Thunder Compute",
    "thunder": "Thunder Compute",
    "spheron": "Spheron",
    "voltagepark": "Voltage Park",
    "fluidstack": "FluidStack",
    "cerebrium": "Cerebrium",
    "daytona": "Daytona",
    "digitalocean": "DigitalOcean",
    "fireworks": "Fireworks AI",
    "gmicloud": "GMI Cloud",
    "hotaisle": "Hot Aisle",
    "hyperai": "Hyper.ai",
    "impossiblecloud": "Impossible Cloud",
    "koyeb": "Koyeb",
    "latitude": "Latitude.sh",
    "lium": "Lium",
    "ovh": "OVHcloud",
    "primeintellect": "Prime Intellect",
    "scaleway": "Scaleway",
    "sfcompute": "SF Compute",
    "synteq": "Synteq",
    "tensordock": "TensorDock",
}


def provider_label(provider: str) -> str:
    key = str(provider or "").strip().lower()
    return PROVIDER_LABELS.get(key, str(provider or "").replace("-", " ").title())


def index_slug(card_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(card_id).lower()).strip("-")


def _iso_week(day: str) -> Tuple[str, str, str]:
    d = date.fromisoformat(day)
    iso = d.isocalendar()
    week_start = d - timedelta(days=d.weekday())
    return week_start.isoformat(), f"{iso.year}-W{iso.week:02d}", (week_start + timedelta(days=6)).isoformat()


def _valid_row(row: Dict[str, Any]) -> bool:
    price = row.get("usdPerGpuHour")
    return (
        isinstance(price, (int, float))
        and price > 0
        and len(str(row.get("date") or "")) == 10
        and bool(row.get("provider"))
        and bool(row.get("series"))
    )


def _provider_medians(entries: Dict[str, List[float]]) -> Dict[str, float]:
    return {provider: round(median(values), 6) for provider, values in entries.items() if values}


def _quartiles(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if len(values) < 4:
        return None, None
    q = quantiles(values, n=4)
    return round(q[0], 6), round(q[2], 6)


def _moving_average(rows: List[Dict[str, Any]], field: str = "value", window: int = 30) -> None:
    for index, row in enumerate(rows):
        sample = rows[max(0, index - window + 1): index + 1]
        row[f"movingAverage{window}d"] = round(sum(float(item[field]) for item in sample) / len(sample), 6)


def _status_for(last_day: str, as_of: str) -> str:
    delta = (date.fromisoformat(as_of) - date.fromisoformat(last_day)).days
    if delta <= 2:
        return "live"
    if delta <= 7:
        return "unconfirmed"
    return "stopped"


def _market_series(
    rows: List[Dict[str, Any]],
    market: Dict[str, Any],
    as_of: str,
) -> Dict[str, Any]:
    quotes_by_day_provider: Dict[str, Dict[str, List[Tuple[float, str]]]] = defaultdict(lambda: defaultdict(list))
    counts_by_day: Dict[str, int] = defaultdict(int)
    for row in rows:
        kind = str(row.get("kind") or "").lower()
        if kind not in market["kinds"]:
            continue
        day = str(row["date"])
        provider = str(row["provider"])
        quotes_by_day_provider[day][provider].append((
            float(row["usdPerGpuHour"]),
            str(row.get("sourceUrl") or ""),
        ))
        counts_by_day[day] += 1

    daily: List[Dict[str, Any]] = []
    cheapest_series: List[Dict[str, Any]] = []
    for day in sorted(quotes_by_day_provider):
        provider_quotes = quotes_by_day_provider[day]
        per_provider = _provider_medians({
            provider: [price for price, _ in quotes]
            for provider, quotes in provider_quotes.items()
        })
        values = sorted(per_provider.values())
        p25, p75 = _quartiles(values)
        raw_items = [
            (provider, price, source_url)
            for provider, quotes in provider_quotes.items()
            for price, source_url in quotes
        ]
        raw_values = sorted(price for _, price, _ in raw_items)
        cheapest_provider, cheapest_value, cheapest_source = min(raw_items, key=lambda item: item[1])
        daily.append({
            "date": day,
            "series": market["id"],
            "value": round(median(values), 6),
            "p25": p25,
            "p75": p75,
            "low": round(raw_values[0], 6),
            "high": round(raw_values[-1], 6),
            "providerCount": len(values),
            "quoteCount": len(raw_items),
            "thin": len(values) < MIN_PROVIDERS,
            "medianSynthetic": len(values) % 2 == 0,
            "cheapestProvider": provider_label(cheapest_provider),
            "cheapestProviderId": cheapest_provider,
            "cheapestValue": round(cheapest_value, 6),
            "cheapestSourceUrl": cheapest_source,
        })
        cheapest_series.append({
            "date": day,
            "value": round(cheapest_value, 6),
            "provider": provider_label(cheapest_provider),
            "providerId": cheapest_provider,
            "sourceUrl": cheapest_source,
        })
    _moving_average(daily)

    if not daily:
        return {
            "label": market["label"],
            "short": market["short"],
            "risk": market["risk"],
            "scope": market["scope"],
            "note": market["note"],
            "status": "no_data",
            "series": [],
            "cheapestSeries": [],
            "latest": None,
            "change7dPct": None,
            "change7dBaseDate": None,
            "coverageDays": 0,
        }

    latest = daily[-1]
    last_day = latest["date"]
    latest_quotes = quotes_by_day_provider[last_day]
    per_provider = _provider_medians({
        provider: [price for price, _ in quotes]
        for provider, quotes in latest_quotes.items()
    })
    providers = []
    for provider, value in sorted(per_provider.items(), key=lambda item: item[1]):
        quotes = latest_quotes[provider]
        # The provider value is a median across its same-day configurations;
        # point the source at the configuration closest to that median.
        source_url = min(quotes, key=lambda item: (abs(item[0] - value), item[0]))[1]
        providers.append({
            "provider": provider_label(provider),
            "providerId": provider,
            "value": round(value, 6),
            "sourceUrl": source_url,
            "quotes": len(quotes),
        })
    latest["providers"] = providers

    cutoff = (date.fromisoformat(as_of) - timedelta(days=7)).isoformat()
    base = next((row for row in reversed(daily) if row["date"] <= cutoff), None)
    change = None
    if base and base["value"]:
        change = round((latest["value"] / base["value"] - 1) * 100, 2)

    return {
        "label": market["label"],
        "short": market["short"],
        "risk": market["risk"],
        "scope": market["scope"],
        "note": market["note"],
        "status": _status_for(last_day, as_of),
        "series": daily,
        "cheapestSeries": cheapest_series,
        "latest": latest,
        "change7dPct": change,
        "change7dBaseDate": base["date"] if base else None,
        "coverageDays": len(daily),
        "quoteRows": sum(counts_by_day.values()),
    }


def _monthly_index(rows: List[Dict[str, Any]], as_of: str) -> List[Dict[str, Any]]:
    """Monthly on-demand summary on a fixed, pre-committed provider panel.

    This is a daily-frequency approximation of the hourly monthly panel used by
    other trackers, so it is not directly comparable to an hourly index:

    * Months are calendar months in UTC.
    * The panel for a month is fixed before that month starts.  A provider
      qualifies when it has at least one valid on-demand quote on at least 13
      of the 14 calendar days immediately before the month starts (from
      ``month_start - 14 days`` through ``month_start - 1 day``), i.e. >=90%
      day coverage.  No data from inside the month is used to select the panel.
    * The monthly value is the arithmetic mean of the valid daily values.  A
      daily value is the median of that day's provider medians inside the
      fixed panel; only days with at least 8 panel providers quoting are valid.
    * A month is published only when the panel has at least 8 providers and
      valid days cover at least 75% of the calendar days.  Otherwise it is
      withheld with a reason and no value is emitted.
    * ``vintage`` is provisional for the calendar month containing ``as_of``
      and final for earlier months; ``isComplete`` mirrors that distinction.
    * The first month in a dataset has no prior window, so it is withheld; no
      future data is used to backfill a panel.

    ``as_of`` is accepted for interface symmetry with the other index
    builders; months are derived from the rows themselves.
    """
    on_demand_kinds = MARKET_BY_ID["on_demand"]["kinds"]
    daily_provider_prices: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if str(row.get("kind") or "").lower() not in on_demand_kinds:
            continue
        price = row.get("usdPerGpuHour")
        if not isinstance(price, (int, float)) or float(price) <= 0:
            continue
        daily_provider_prices[str(row["date"])][str(row["provider"])].append(float(price))

    months = sorted({day[:7] for day in daily_provider_prices})
    current_month = as_of[:7]
    output: List[Dict[str, Any]] = []
    for month in months:
        year, month_number = (int(part) for part in month.split("-"))
        days_in_month = calendar.monthrange(year, month_number)[1]
        month_start = date(year, month_number, 1)
        window_end = month_start - timedelta(days=1)
        window_start = month_start - timedelta(days=MONTHLY_PANEL_WINDOW_DAYS)
        presence: Dict[str, int] = defaultdict(int)
        for offset in range(MONTHLY_PANEL_WINDOW_DAYS):
            day = (window_start + timedelta(days=offset)).isoformat()
            for provider in daily_provider_prices.get(day, {}):
                presence[provider] += 1
        panel = sorted(provider for provider, days in presence.items() if days >= MONTHLY_PANEL_MIN_DAYS)
        panel_set = set(panel)

        valid_days = 0
        daily_values: List[float] = []
        for day_number in range(1, days_in_month + 1):
            day = f"{month}-{day_number:02d}"
            per_provider = _provider_medians(daily_provider_prices.get(day, {}))
            panel_values = [value for provider, value in per_provider.items() if provider in panel_set]
            if len(panel_values) >= MONTHLY_MIN_PROVIDERS:
                valid_days += 1
                daily_values.append(median(panel_values))

        coverage_pct = round(valid_days * 100.0 / days_in_month, 1)
        value: Optional[float] = None
        if not panel:
            status = "withheld"
            withheld_reason = (
                f"no provider met the {MONTHLY_PANEL_MIN_DAYS}/{MONTHLY_PANEL_WINDOW_DAYS}-day panel test "
                f"in {window_start.isoformat()}..{window_end.isoformat()}"
            )
        elif len(panel) < MONTHLY_MIN_PROVIDERS:
            status = "withheld"
            withheld_reason = f"panel has {len(panel)} providers (needs >={MONTHLY_MIN_PROVIDERS})"
        elif valid_days / days_in_month < MONTHLY_MIN_COVERAGE:
            status = "withheld"
            withheld_reason = (
                f"valid days {valid_days}/{days_in_month} ({coverage_pct}%) "
                f"below {int(MONTHLY_MIN_COVERAGE * 100)}% coverage"
            )
        else:
            status = "published"
            withheld_reason = None
            value = round(sum(daily_values) / len(daily_values), 6)

        vintage = "provisional" if month >= current_month else "final"
        output.append({
            "month": month,
            "value": value,
            "panelCount": len(panel),
            "coverageDays": valid_days,
            "daysInMonth": days_in_month,
            "coveragePct": coverage_pct,
            "status": status,
            "vintage": vintage,
            "isComplete": vintage == "final",
            "withheldReason": withheld_reason,
            "methodologyVersion": METHODOLOGY_VERSION,
            "panel": panel,
        })
    return output


def _weekly_index(rows: List[Dict[str, Any]], as_of: str) -> Dict[str, Any]:
    """Weekly on-demand index per card, with chain-linked base-100 and receipts."""
    by_week_provider: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    excluded_by_week: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        kind = str(row.get("kind") or "").lower()
        day = str(row["date"])
        _, iso_week, _ = _iso_week(day)
        if kind not in MARKET_BY_ID["on_demand"]["kinds"]:
            market_id = KIND_TO_MARKET.get(kind)
            if market_id:
                excluded_by_week[iso_week].append({
                    "provider": provider_label(str(row["provider"])),
                    "providerId": str(row["provider"]),
                    "market": market_id,
                    "value": round(float(row["usdPerGpuHour"]), 6),
                    "date": day,
                    "sourceUrl": str(row.get("sourceUrl") or ""),
                    "rule": "market_not_on_demand",
                })
            continue
        provider = str(row["provider"])
        slot = by_week_provider[iso_week].setdefault(provider, {
            "provider": provider,
            "values": [],
            "date": day,
            "sourceUrl": str(row.get("sourceUrl") or ""),
        })
        if day > slot["date"]:
            # 周度指数取该周最新一天的 provider 报价；同一天多个配置再取中位。
            slot["values"] = [float(row["usdPerGpuHour"])]
            slot["date"] = day
            slot["sourceUrl"] = str(row.get("sourceUrl") or "")
        elif day == slot["date"]:
            slot["values"].append(float(row["usdPerGpuHour"]))

    weeks: List[Dict[str, Any]] = []
    receipts: Dict[str, Dict[str, Any]] = {}
    last_index: Optional[float] = None
    last_published_providers: Dict[str, float] = {}
    for iso_week in sorted(by_week_provider):
        entries = by_week_provider[iso_week]
        week_last_day = max(item["date"] for item in entries.values())
        week_start, _, week_end = _iso_week(week_last_day)
        confirmed: Dict[str, Dict[str, Any]] = {}
        stale: List[Dict[str, Any]] = []
        for provider, item in entries.items():
            age = (date.fromisoformat(week_last_day) - date.fromisoformat(item["date"])).days
            if age <= INDEX_CONFIRM_DAYS:
                confirmed[provider] = item
            else:
                stale.append({
                    "provider": provider_label(provider),
                    "providerId": provider,
                    "market": "on_demand",
                    "value": round(median(item["values"]), 6),
                    "date": item["date"],
                    "sourceUrl": item["sourceUrl"],
                    "rule": "not_confirmed_48h",
                })
        provider_values = {provider: round(median(item["values"]), 6) for provider, item in confirmed.items()}
        values = sorted(provider_values.values())
        p25, p75 = _quartiles(values)
        vintage = "final" if week_end < as_of else "provisional"
        if len(values) >= INDEX_PUBLISH_MIN:
            status = "published"
        elif len(values) >= INDEX_MIN_PROVIDERS:
            status = "thin"
        else:
            status = "withheld"
        withheld_reason = None if status != "withheld" else f"only {len(values)} confirmed providers (needs >={INDEX_MIN_PROVIDERS})"
        median_value = round(median(values), 6) if values else None
        index: Optional[float] = None
        link_pairs = 0
        if status != "withheld":
            if last_index is None:
                index = 100.0
            else:
                shared = set(provider_values) & set(last_published_providers)
                link_pairs = len(shared)
                if link_pairs >= 2:
                    ratios = [provider_values[p] / last_published_providers[p] for p in shared]
                    geom = 1.0
                    for ratio in ratios:
                        geom *= ratio
                    geom = geom ** (1.0 / len(ratios))
                    index = round(last_index * geom, 4)
            if index is not None:
                last_index = index
                last_published_providers = provider_values

        included = [
            {
                "provider": provider_label(provider),
                "providerId": provider,
                "value": value,
                "date": confirmed[provider]["date"],
                "sourceUrl": confirmed[provider]["sourceUrl"],
                "quotes": len(confirmed[provider]["values"]),
            }
            for provider, value in sorted(provider_values.items(), key=lambda item: item[1])
        ]
        excluded = sorted(
            excluded_by_week.get(iso_week, []) + stale,
            key=lambda item: (item["date"], item["providerId"], item["market"]),
        )
        excluded_counts: Dict[str, int] = defaultdict(int)
        for item in excluded_by_week.get(iso_week, []):
            excluded_counts[str(item["market"])] += 1
        receipts[iso_week] = {
            "weekStart": week_start,
            "weekEnd": week_end,
            "vintage": vintage,
            "status": status,
            "methodologyVersion": METHODOLOGY_VERSION,
            "median": median_value,
            "p25": p25,
            "p75": p75,
            "providerCount": len(values),
            "index": index,
            "linkPairs": link_pairs,
            "withheldReason": withheld_reason,
            "notConfirmed48h": len(stale),
            "included": included,
            "excluded": excluded,
            "excludedQuoteRowsByMarket": dict(excluded_counts),
        }
        weeks.append({
            "weekStart": week_start,
            "isoWeek": iso_week,
            "vintage": vintage,
            "status": status,
            "methodologyVersion": METHODOLOGY_VERSION,
            "median": median_value,
            "p25": p25,
            "p75": p75,
            "providerCount": len(values),
            "index": index,
            "linkPairs": link_pairs,
            "withheldReason": withheld_reason,
            "receipt": iso_week,
        })

    published = [week for week in weeks if week["index"] is not None]
    latest = published[-1] if published else None
    if latest is not None:
        latest["ageDays"] = (date.fromisoformat(as_of) - date.fromisoformat(latest["weekStart"])).days
    return {
        "weeks": weeks,
        "receipts": receipts,
        "latest": latest,
        "minProviders": INDEX_MIN_PROVIDERS,
        "publishMin": INDEX_PUBLISH_MIN,
        "confirmDays": INDEX_CONFIRM_DAYS,
    }


def build_landscape(rows: List[Dict[str, Any]], as_of: Optional[str] = None) -> Dict[str, Any]:
    """Page payload: full aggregates without weekly receipts."""
    return trim_landscape(full_landscape(rows, as_of))


def full_landscape(rows: List[Dict[str, Any]], as_of: Optional[str] = None, built_at: Optional[str] = None) -> Dict[str, Any]:
    """Full landscape including weekly receipts, used for public data files."""
    valid = [row for row in rows if _valid_row(row)]
    if not valid:
        raise ValueError("no valid neocloud rows")
    as_of = as_of or max(str(row["date"]) for row in valid)
    built_at = built_at or datetime.now(timezone.utc).date().isoformat()
    data_age_days = max(0, (date.fromisoformat(built_at) - date.fromisoformat(as_of)).days)
    cards: List[Dict[str, Any]] = []
    for card in CARDS:
        card_rows = [row for row in valid if str(row["series"]) == card["id"]]
        if not card_rows:
            continue
        markets = {market["id"]: _market_series(card_rows, market, as_of) for market in MARKETS}
        weekly = _weekly_index(card_rows, as_of)
        on_demand = markets["on_demand"]
        cards.append({
            "id": card["id"],
            "name": card["name"],
            "vramGb": card["vramGb"],
            "family": card["family"],
            "asOf": on_demand["latest"]["date"] if on_demand["latest"] else None,
            "status": on_demand["status"],
            "median": on_demand["latest"]["value"] if on_demand["latest"] else None,
            "p25": on_demand["latest"]["p25"] if on_demand["latest"] else None,
            "p75": on_demand["latest"]["p75"] if on_demand["latest"] else None,
            "cheapest": on_demand["latest"]["cheapestValue"] if on_demand["latest"] else None,
            "cheapestProvider": on_demand["latest"]["cheapestProvider"] if on_demand["latest"] else None,
            "providerCount": on_demand["latest"]["providerCount"] if on_demand["latest"] else 0,
            "change7dPct": on_demand["change7dPct"],
            "weeklyIndex": weekly["latest"],
            "weekly": weekly,
            "monthly": _monthly_index(card_rows, as_of),
            "markets": markets,
        })
    if not cards:
        raise ValueError("no landscape cards matched the neocloud dataset")
    return {
        "asOf": as_of,
        "builtAt": built_at,
        "dataAgeDays": data_age_days,
        "dataFreshness": "current" if data_age_days <= 2 else "stale",
        "methodologyVersion": METHODOLOGY_VERSION,
        "minProviders": MIN_PROVIDERS,
        "indexMinProviders": INDEX_MIN_PROVIDERS,
        "indexPublishMin": INDEX_PUBLISH_MIN,
        "indexConfirmDays": INDEX_CONFIRM_DAYS,
        "cards": cards,
        "markets": MARKETS,
    }


def trim_landscape(full: Dict[str, Any]) -> Dict[str, Any]:
    """Payload embedded in the page: no receipts; cheapest line derives from series.

    Every ``series`` point carries ``cheapestValue``, ``cheapestProvider`` and
    ``cheapestSourceUrl``, so the page can draw the cheapest line without a
    duplicate ``cheapestSeries`` array.  The full payload keeps
    ``cheapestSeries`` for machine-readable exports.
    """
    cards = []
    for card in full["cards"]:
        markets = {}
        for market_id, market in card["markets"].items():
            latest = market.get("latest")
            if latest:
                latest = dict(latest)
                offers = latest.pop("providers", None)
                if offers is not None:
                    latest["offers"] = offers
            markets[market_id] = {
                "label": market["label"],
                "short": market["short"],
                "risk": market["risk"],
                "scope": market["scope"],
                "note": market["note"],
                "status": market["status"],
                "series": market["series"],
                "latest": latest,
                "change7dPct": market["change7dPct"],
                "change7dBaseDate": market["change7dBaseDate"],
                "coverageDays": market["coverageDays"],
                "quoteRows": market.get("quoteRows", 0),
            }
        cards.append({
            "id": card["id"],
            "name": card["name"],
            "vramGb": card["vramGb"],
            "family": card["family"],
            "asOf": card["asOf"],
            "status": card["status"],
            "median": card["median"],
            "p25": card["p25"],
            "p75": card["p75"],
            "cheapest": card["cheapest"],
            "cheapestProvider": card["cheapestProvider"],
            "providerCount": card["providerCount"],
            "change7dPct": card["change7dPct"],
            "weeklyIndex": card["weeklyIndex"],
            "monthly": card.get("monthly", []),
            "markets": markets,
        })
    return {
        "asOf": full["asOf"],
        "builtAt": full.get("builtAt"),
        "dataAgeDays": full.get("dataAgeDays"),
        "dataFreshness": full.get("dataFreshness"),
        "methodologyVersion": full["methodologyVersion"],
        "minProviders": full["minProviders"],
        "indexMinProviders": full["indexMinProviders"],
        "indexPublishMin": full.get("indexPublishMin"),
        "indexConfirmDays": full.get("indexConfirmDays"),
        "cards": cards,
        "markets": full["markets"],
    }


def public_prices(full: Dict[str, Any]) -> Dict[str, Any]:
    """One row per provider / card / market, latest reading only."""
    quotes: List[Dict[str, Any]] = []
    for card in full["cards"]:
        for market_id, market in card["markets"].items():
            latest = market.get("latest")
            if not latest:
                continue
            for provider in latest.get("providers", []):
                quotes.append({
                    "provider": provider["provider"],
                    "provider_id": provider["providerId"],
                    "card": card["name"],
                    "card_id": card["id"],
                    "vram_gb": card["vramGb"],
                    "market": market_id,
                    "market_label": market["label"],
                    "risk": market["risk"],
                    "price_scope": market["scope"],
                    "usd_per_gpu_hour": provider["value"],
                    "date": latest["date"],
                    "status": market["status"],
                    "source_url": provider["sourceUrl"],
                    "quotes": provider.get("quotes", 1),
                    "source_layer": "own",
                    "region": None,
                    "gpu_count": None,
                    "listed_price": None,
                    "listed_currency": "USD",
                    "fx_rate": 1.0,
                    "fx_date": None,
                    "listed_unit": "USD/GPU-hour",
                    "scraped_at": None,
                    "last_confirmed_at": latest["date"],
                    "listed_since": None,
                    "change_7d_pct": None,
                    "source_kind": None,
                })
    return {
        "name": "AI Compute Economics - latest GPU supply quotes",
        "unit": "USD per GPU per hour",
        "description": "Latest reading per provider, GPU and market, normalized to one GPU. A provider's value is the median of its same-day configurations; quotes records how many rows it rests on. Node prices in the source dataset are already normalized to one GPU; community, spot and marketplace floors are kept separate from the main on-demand median. Every row is source_layer='own'. Fields the underlying rows do not carry are null instead of estimated: region, gpu_count, listed_price, fx_date, scraped_at, listed_since, source_kind and per-quote change_7d_pct. listed_currency='USD', fx_rate=1.0 and listed_unit='USD/GPU-hour' describe the USD normalization of the source; last_confirmed_at is the quote date used as a proxy because the source has no confirmation timestamp.",
        "as_of": full["asOf"],
        "methodology_version": full["methodologyVersion"],
        "count": len(quotes),
        "quotes": sorted(quotes, key=lambda row: (row["card_id"], row["market"], row["usd_per_gpu_hour"])),
    }


def _columnar_cheapest_series(points: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Columnar cheapest series with a per-market source URL dictionary.

    Repeating ``{"date": ..., "value": ..., "providerId": ..., "sourceUrl": ...}``
    for every day and every market made gpus.json too large.  The columnar form
    keeps the same information for every market while sharing repeated URLs.
    """
    dates: List[str] = []
    values: List[float] = []
    provider_ids: List[str] = []
    source_urls: List[str] = []
    source_idx: List[int] = []
    url_index: Dict[str, int] = {}
    for point in points:
        value = point.get("value")
        if not isinstance(value, (int, float)):
            continue
        source_url = str(point.get("sourceUrl") or "")
        if source_url not in url_index:
            url_index[source_url] = len(source_urls)
            source_urls.append(source_url)
        dates.append(str(point["date"]))
        values.append(value)
        provider_ids.append(str(point.get("providerId") or ""))
        source_idx.append(url_index[source_url])
    return {
        "dates": dates,
        "values": values,
        "provider_ids": provider_ids,
        "source_urls": source_urls,
        "source_idx": source_idx,
    }


def public_gpus(full: Dict[str, Any]) -> Dict[str, Any]:
    cards = []
    for card in full["cards"]:
        markets = {}
        for market_id, market in card["markets"].items():
            latest = market.get("latest")
            series = _columnar_cheapest_series(market.get("cheapestSeries", []))
            if not latest:
                markets[market_id] = {
                    "status": "no_data",
                    "cheapest": None,
                    "cheapest_series": series,
                }
                continue
            markets[market_id] = {
                "label": market["label"],
                "status": market["status"],
                "risk": market["risk"],
                "price_scope": market["scope"],
                "median": latest["value"],
                "p25": latest["p25"],
                "p75": latest["p75"],
                "cheapest": latest["cheapestValue"],
                "cheapest_provider": latest["cheapestProvider"],
                "provider_count": latest["providerCount"],
                "thin": bool(latest.get("thin")),
                "date": latest["date"],
                "cheapest_series": series,
            }
        cards.append({
            "id": card["id"],
            "name": card["name"],
            "vram_gb": card["vramGb"],
            "family": card["family"],
            "as_of": card["asOf"],
            "status": card["status"],
            "median": card["median"],
            "p25": card["p25"],
            "p75": card["p75"],
            "cheapest": card["cheapest"],
            "cheapest_provider": card["cheapestProvider"],
            "provider_count": card["providerCount"],
            "change_7d_pct": card["change7dPct"],
            "weekly_index": card["weeklyIndex"],
            "monthly": card.get("monthly", []),
            "markets": markets,
        })
    return {
        "name": "AI Compute Economics - GPU landscape",
        "as_of": full["asOf"],
        "methodology_version": full["methodologyVersion"],
        "min_providers": full["minProviders"],
        "count": len(cards),
        "gpus": cards,
    }


def public_providers(full: Dict[str, Any]) -> Dict[str, Any]:
    by_provider: Dict[str, Dict[str, Any]] = {}
    for card in full["cards"]:
        for market_id, market in card["markets"].items():
            latest = market.get("latest")
            if not latest:
                continue
            for quote in latest.get("providers", []):
                provider_id = quote["providerId"]
                item = by_provider.setdefault(provider_id, {
                    "id": provider_id,
                    "name": quote["provider"],
                    "cards": set(),
                    "markets": set(),
                    "quotes": 0,
                    "cheapest": None,
                })
                item["cards"].add(card["id"])
                item["markets"].add(market_id)
                item["quotes"] += 1
                if item["cheapest"] is None or quote["value"] < item["cheapest"]["usd_per_gpu_hour"]:
                    item["cheapest"] = {
                        "card": card["id"],
                        "market": market_id,
                        "usd_per_gpu_hour": quote["value"],
                        "source_url": quote["sourceUrl"],
                    }
            raw_provider = latest.get("cheapestProviderId")
            raw_value = latest.get("cheapestValue")
            if raw_provider and isinstance(raw_value, (int, float)):
                item = by_provider.setdefault(raw_provider, {
                    "id": raw_provider,
                    "name": latest.get("cheapestProvider") or raw_provider,
                    "cards": set(),
                    "markets": set(),
                    "quotes": 0,
                    "cheapest": None,
                })
                item["cards"].add(card["id"])
                item["markets"].add(market_id)
                if item["cheapest"] is None or raw_value < item["cheapest"]["usd_per_gpu_hour"]:
                    item["cheapest"] = {
                        "card": card["id"],
                        "market": market_id,
                        "usd_per_gpu_hour": raw_value,
                        "source_url": latest.get("cheapestSourceUrl", ""),
                    }
    providers = []
    for item in by_provider.values():
        providers.append({
            **item,
            "cards": sorted(item["cards"]),
            "markets": sorted(item["markets"]),
        })
    return {
        "name": "AI Compute Economics - provider coverage",
        "as_of": full["asOf"],
        "methodology_version": full["methodologyVersion"],
        "count": len(providers),
        "providers": sorted(providers, key=lambda row: (-len(row["cards"]), row["name"])),
    }


def public_index(full: Dict[str, Any]) -> Dict[str, Any]:
    cards = {}
    for card in full["cards"]:
        weekly = card["weekly"]
        latest_week = (weekly.get("latest") or {}).get("receipt")
        # Public receipts are evidence for the current headline week only.
        # Keeping every historical week made the file ~3MB and multiplied the
        # per-card slices; the full history stays in tracker_data.
        receipts = (
            {latest_week: weekly["receipts"][latest_week]}
            if latest_week in weekly.get("receipts", {})
            else {}
        )
        weeks = []
        for week in weekly["weeks"]:
            item = dict(week)
            if item.get("receipt") != latest_week:
                item.pop("receipt", None)
            weeks.append(item)
        cards[card["id"]] = {
            "name": card["name"],
            "as_of": card["asOf"],
            "min_providers": weekly["minProviders"],
            "latest": weekly["latest"],
            "weeks": weeks,
            "receipts": receipts,
            "monthly": card.get("monthly", []),
        }
    return {
        "name": "AI Compute Economics - weekly GPU supply index",
        "description": "Weekly on-demand median per card, chain-linked base-100 over providers present in both weeks; one provider once per week. Weeks below the provider guard are withheld, not backfilled. Public receipts retain the latest published week only. Monthly values use a fixed pre-committed provider panel and a daily-frequency approximation; see monthly_method.",
        "unit": "USD per GPU per hour; base-100 index",
        "as_of": full["asOf"],
        "methodology_version": full["methodologyVersion"],
        "index_min_providers": full["indexMinProviders"],
        "index_publish_min": full.get("indexPublishMin"),
        "index_confirm_days": full.get("indexConfirmDays"),
        "receipt_retention": "latest_week_only",
        "monthly_method": "Calendar month UTC. The panel is fixed before the month starts: providers need at least one on-demand quote on >=13 of the 14 days immediately before the month starts (month_start - 14 days through month_start - 1 day). The monthly value is the mean of daily median-of-panel-provider-medians over days with >=8 panel providers quoting. A month is published only with >=8 panel providers and >=75% valid-day coverage; otherwise it is withheld with a reason. vintage is provisional for the month containing the data as-of and final for earlier months. Daily-frequency approximation, not an hourly panel.",
        "cards": cards,
    }


def public_manifest(full: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    return {
        "name": "AI Compute Economics - public GPU supply data",
        "generated_at": generated_at,
        "data_as_of": full["asOf"],
        "data_age_days": full.get("dataAgeDays"),
        "methodology_version": full["methodologyVersion"],
        "license": "Project data. Underlying neocloud rows are CC BY 4.0; see the dashboard source panel.",
        "attribution": "AI Compute Economics; underlying provider prices from the tracked provider pages.",
        "files": [
            {"path": "prices.json", "description": "Latest provider x card x market quote, normalized to USD/GPU-hour."},
            {"path": "gpus.json", "description": f"{len(full['cards'])}-card landscape summary and per-market latest."},
            {"path": "providers.json", "description": "Provider coverage and cheapest observed quote."},
            {"path": "price-index.json", "description": "Weekly per-card index with chain-linked base-100; latest-week receipt only."},
            {"path": "price-index/{gpu}.json", "description": "Per-card slice of price-index.json, used by the receipt download; latest-week receipt only."},
            {"path": "changelog.json", "description": "Weekly index and median changes by card."},
        ],
        "field_availability": {
            "native": {
                "date": "source row date (UTC day)",
                "provider_id": "source provider id",
                "series": "source GPU series label",
                "kind": "source market kind (on-demand, secure, spot, community, ...)",
                "usd_per_gpu_hour": "source price already normalized to USD per GPU-hour",
                "source_url": "per-row provider source URL",
                "venue_grade": "source venue class; present in the rows but not used by the landscape",
            },
            "derived": {
                "provider": "display label derived from provider_id",
                "card": "card display name mapped from series through the card catalog",
                "card_id": "card catalog id mapped from series",
                "vram_gb": "card catalog memory size; the source row's vramGb is not used to split cards",
                "market": "market id mapped from kind",
                "market_label": "market display label mapped from kind",
                "risk": "market risk label mapped from kind",
                "price_scope": "market scope mapped from kind",
                "quotes": "count of same-day source rows behind the provider value",
                "source_layer": "'own' for every row in this dataset; external reference layers are published separately",
                "median": "median of same-day per-provider medians; one provider one vote",
                "p25_p75": "quartiles of same-day provider medians; null below 4 providers",
                "cheapest": "minimum raw same-day quote before per-provider aggregation",
                "cheapest_series": "one daily minimum raw quote with its provider and source URL",
                "monthly": "fixed-panel monthly summary from daily on-demand quotes; see definitions.monthly",
                "status": "live/unconfirmed/stopped derived from quote age against the data as-of",
                "change_7d_pct (market)": "market-level change against the last reading at or before as-of minus 7 days",
                "last_confirmed_at": "quote date used as a confirmation proxy; the source has no per-row confirmation timestamp",
                "listed_currency": "'USD' declared because the source dataset is already normalized to USD",
                "fx_rate": "1.0 sentinel because no per-row FX conversion is retained",
                "listed_unit": "'USD/GPU-hour', the unit of the normalized source price",
            },
            "unavailable": {
                "region": "null: source rows carry no region dimension",
                "gpu_count": "null: source rows carry no GPU count and the node-to-GPU normalization cannot be re-derived",
                "listed_price": "null: only the normalized per-GPU price is retained, not the original listing price",
                "fx_date": "null: no per-row FX date exists",
                "scraped_at": "null: only a dataset-level fetchedAt exists, not a per-row scrape time",
                "listed_since": "null: source rows have no first-listed date",
                "source_kind": "null: source rows have no source-kind field (venueGrade is not equivalent)",
                "change_7d_pct (per quote)": "null: no per-quote 7-day history is retained; only the market-level change is derived",
            },
        },
        "definitions": {
            "on_demand": "kinds on-demand and secure; community, spot, reserved, marketplace and serverless excluded from this median",
            "median": "each provider once per day; median across providers",
            "p25_p75": "quartiles across provider medians; omitted when fewer than 4 providers",
            "status": "live if within 2 days of data as-of; unconfirmed within 7 days; stopped otherwise. Stopped markets keep their last reading and are still used for daily medians and cheapest values; the weekly index only includes readings confirmed within 2 days of the week's last day.",
            "vintage": "provisional for the current ISO week; final after the week closes",
            "index": "published at >=8 confirmed providers; thin at 4-7; withheld below 4; only the provider's latest day in the week, confirmed within 2 days of the week's last day",
            "receipts": "public price-index.json and per-card slices retain the latest published week only; full history stays in tracker_data",
            "monthly": "calendar month UTC; panel fixed before the month starts from providers with on-demand quotes on >=13 of the 14 days immediately before the month starts (month_start - 14 days through month_start - 1 day); value is the arithmetic mean of daily median-of-panel-provider-medians over days with >=8 panel providers; published at >=75% valid-day coverage and >=8 panel providers, withheld otherwise; vintage is provisional for the month containing the data as-of and final for earlier months; a daily-frequency approximation, not an hourly panel",
            "cheapest_series": "one point per day: the minimum raw quoted USD/GPU-hour among that day's quotes, with the provider and source URL of that quote; not a provider median and not the market median",
            "risk": "low for on-demand/reserved; medium for serverless/shared; high for spot/community/marketplace floor",
            "price_scope": "rate_card is a listed rate normalized to one GPU; instance vs GPU-only scope is not retained in this version; marketplace_floor and serverless are separate",
        },
    }


def public_changelog(full: Dict[str, Any]) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    for card in full["cards"]:
        previous_index: Optional[float] = None
        for week in card["weekly"]["weeks"]:
            index = week.get("index")
            if index is None:
                continue
            change = round((index / previous_index - 1) * 100, 3) if previous_index else None
            events.append({
                "card": card["id"],
                "card_name": card["name"],
                "week_start": week["weekStart"],
                "iso_week": week["isoWeek"],
                "vintage": week["vintage"],
                "status": week["status"],
                "median": week["median"],
                "p25": week["p25"],
                "p75": week["p75"],
                "index": index,
                "index_change_pct": change,
                "provider_count": week["providerCount"],
                "link_pairs": week["linkPairs"],
            })
            previous_index = index
    return {
        "name": "AI Compute Economics - weekly supply index changelog",
        "as_of": full["asOf"],
        "methodology_version": full["methodologyVersion"],
        "count": len(events),
        "events": sorted(events, key=lambda row: (row["week_start"], row["card"])),
    }
