"""Normalize committed GPU Economy snapshots and cross-check them against our panel.

External data is a read-only reference layer: nothing in this module may change an
own median, provider count, or index.  The comparable rule is deliberately narrow
(on-demand / live / non-floor / USD, one cheapest rate per provider) because the
published GPU Economy median also includes serverless and FX-converted listings.

All numbers are derived from ``tracker_data/external/gpueconomy/<date>`` only, so
the dashboard build never touches the network.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "tracker_data" / "external" / "gpueconomy"
SNAPSHOT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PRICES_URL = "https://gpueconomy.com/prices.json"
GPUS_URL = "https://gpueconomy.com/gpus.json"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
EXTERNAL_SOURCE = "gpueconomy"
METHODOLOGY_RE = re.compile(r"^\d+\.\d+\.\d+$")
COMPARABLE_RULE = (
    "on_demand 是主口径；spot/serverless 按同一 live/非 floor/USD/每 provider min "
    "规则可计算差值，但不能与整租 on-demand 混读；reserved/community/marketplace "
    "因期限或 floor 语义不可比。"
)
# A card-level diff needs at least eight own providers.  This is deliberately
# stricter than the daily market thin guard (MIN_PROVIDERS=4): four providers
# can describe a market, but not a credible cross-check against 16-48 external ones.
CROSSCHECK_MIN_OWN_PROVIDERS = 8


def latest_snapshot_dir(base: Path | str | None = None) -> Path:
    """Return the newest ``YYYY-MM-DD`` snapshot directory under ``base``."""
    root = Path(base) if base is not None else SNAPSHOT_ROOT
    if not root.is_dir():
        raise FileNotFoundError(f"gpueconomy snapshot root missing: {root}")
    candidates = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir() and SNAPSHOT_DATE_RE.fullmatch(path.name)
        ),
        key=lambda path: path.name,
    )
    if not candidates:
        raise FileNotFoundError(f"no YYYY-MM-DD snapshot directories under {root}")
    return candidates[-1]


try:
    SNAPSHOT_DIR = latest_snapshot_dir()
except FileNotFoundError:  # keep imports usable before the first snapshot is committed
    SNAPSHOT_DIR = SNAPSHOT_ROOT

# Our six markets, in display order.
MARKETS: Tuple[str, ...] = (
    "on_demand",
    "spot",
    "reserved",
    "community",
    "marketplace",
    "serverless",
)

# facts-external.md §8.1.  ``family_ids`` drives coverage overlap; it is NOT a
# median union: H100's h100 and h100-sxm are never merged into one value.
CARD_MAP: Tuple[Dict[str, Any], ...] = (
    {
        "card_id": "H100",
        "match_id": "h100",
        "benchmark_id": "h100-sxm",
        "context_ids": ["h100-pcie", "h100-nvl"],
        "family_ids": ["h100", "h100-sxm", "h100-pcie"],
        "overlap_scope": "h100+h100-sxm+h100-pcie",
        "sku_mismatch": False,
        "mixed_sku": True,
        "note": "我方 H100 同日混 80GB SXM、80GB PCIe 与 94GB NVL；ext 用 h100（形态未标注），h100-sxm 只作独立基准，不合并。",
    },
    {
        "card_id": "H200",
        "match_id": "h200",
        "benchmark_id": None,
        "context_ids": ["h200-nvl"],
        "family_ids": ["h200"],
        "overlap_scope": "h200",
        "sku_mismatch": False,
        "note": "我方 H200 含 141GB SXM 与部分 143GB NVL；ext h200-nvl 只作上下文，不并入主口径。",
    },
    {
        "card_id": "B200",
        "match_id": "b200",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["b200"],
        "overlap_scope": "b200",
        "sku_mismatch": False,
        "note": "B200 名义 192GB，实际实例有 180/186/192GB 变体；仅作卡级参考。",
    },
    {
        "card_id": "B300",
        "match_id": "b300",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["b300"],
        "overlap_scope": "b300",
        "sku_mismatch": False,
        "note": "B300 实例显存有 262/270/280/288GB 变体；仅作卡级参考。",
    },
    {
        "card_id": "A100",
        "match_id": "a100-80",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["a100-80"],
        "overlap_scope": "a100-80",
        "sku_mismatch": True,
        "note": "我方 A100 同日混 40GB 与 80GB，ext 只取 a100-80；型号不一致，仅做覆盖参考，不给差值。",
    },
    {
        "card_id": "L40S",
        "match_id": "l40s",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["l40s"],
        "overlap_scope": "l40s",
        "sku_mismatch": False,
        "note": "L40S 配置单一；provider 级价格仍可能因实例配置与时点不同。",
    },
    {
        "card_id": "RTX PRO 6000",
        "match_id": "rtx-pro-6000",
        "benchmark_id": None,
        "context_ids": ["rtx-pro-6000-max-q"],
        "family_ids": ["rtx-pro-6000"],
        "overlap_scope": "rtx-pro-6000",
        "sku_mismatch": False,
        "note": "ext 将工作站与 Server 合并在 rtx-pro-6000，Max-Q 单列；我方 community 可能混入 Max-Q，on-demand 主口径不含。",
    },
    {
        "card_id": "RTX 4090",
        "match_id": "rtx-4090",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["rtx-4090"],
        "overlap_scope": "rtx-4090",
        "sku_mismatch": False,
        "note": "我方仅少量 provider，样本弱；external 覆盖更广，不改写我方中位。",
    },
    {
        "card_id": "RTX 5090",
        "match_id": "rtx-5090",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["rtx-5090"],
        "overlap_scope": "rtx-5090",
        "sku_mismatch": False,
        "note": "我方仅少量 provider，样本弱；external 覆盖更广，不改写我方中位。",
    },
    {
        "card_id": "MI300X",
        "match_id": "mi300x",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["mi300x"],
        "overlap_scope": "mi300x",
        "sku_mismatch": False,
        "note": "MI300X 配置单一；ext 只有 7 家可比 provider，样本偏薄。",
    },
    {
        "card_id": "GH200",
        "match_id": "gh200",
        "benchmark_id": None,
        "context_ids": [],
        "family_ids": ["gh200"],
        "overlap_scope": "gh200",
        "sku_mismatch": False,
        "note": "GH200 ext 仅 4 家可比 provider，只能作弱参考。",
    },
)

CARD_BY_ID = {item["card_id"]: item for item in CARD_MAP}

# External gpu_id -> our card_id, used when a caller only knows the external id.
CARD_BY_EXT_GPU: Dict[str, str] = {}
for _mapping in CARD_MAP:
    for _gpu_id in [_mapping["match_id"], _mapping.get("benchmark_id"), *_mapping["context_ids"]]:
        if _gpu_id:
            CARD_BY_EXT_GPU[_gpu_id] = _mapping["card_id"]

# Our id -> GPU Economy id.  DigitalOcean is a partition alias: only the
# ``region == "GPU Droplets"`` rows correspond to our DigitalOcean panel.  The
# ``region == "Paperspace"`` rows stay separate and never join our provider.
OUR_TO_EXT = {
    "massedcompute": "massed",
    "ovh": "ovhcloud",
    "gmicloud": "gmi-cloud",
    "thundercompute": "thunder",
    "digitalocean": "paperspace",
}
EXT_TO_OUR = {ext: ours for ours, ext in OUR_TO_EXT.items()}
CANONICAL_OWN = {
    "massed": "massedcompute",
    "massedcompute": "massedcompute",
    "ovh": "ovh",
    "ovhcloud": "ovh",
    "gmicloud": "gmicloud",
    "gmi-cloud": "gmicloud",
    "thundercompute": "thundercompute",
    "thunder": "thundercompute",
    "digitalocean": "digitalocean",
    "paperspace": "digitalocean",
}

ALIAS_ENTRIES: Tuple[Dict[str, str], ...] = (
    {"our_id": "massedcompute", "ext_id": "massed", "match": "alias"},
    {"our_id": "ovh", "ext_id": "ovhcloud", "match": "alias"},
    {"our_id": "gmicloud", "ext_id": "gmi-cloud", "match": "alias"},
    {"our_id": "thundercompute", "ext_id": "thunder", "match": "alias"},
    {
        "our_id": "digitalocean",
        "ext_id": "paperspace",
        "match": "partition",
        "note": "only region == 'GPU Droplets'; region == 'Paperspace' is a separate product line",
    },
)

# How each of our markets is looked up in GPU Economy rows.
# on_demand is the primary comparable rule; spot/serverless reuse the same
# live/non-floor/USD/cheapest-per-provider rule but are never mixed with
# on-demand.  community/marketplace/reserved stay reference-only.
MARKET_VIEWS: Dict[str, Dict[str, Any]] = {
    "on_demand": {
        "ext_markets": ["on_demand"],
        "scope": None,
        "comparable": True,
        "note": "可比口径：market=on_demand、status=live、非 marketplace_floor、USD；每 provider 取最低价后取中位。",
    },
    "spot": {
        "ext_markets": ["spot"],
        "scope": None,
        "comparable": True,
        "note": "可比口径与 on-demand 相同（live、非 floor、USD、每 provider 最低价）；spot 可被收回，不能当 on-demand。",
    },
    "reserved": {
        "ext_markets": ["reserved", "reserved_1y", "reserved_3y"],
        "scope": None,
        "comparable": False,
        "note": "GPU Economy 把 reserved 拆成无期限/1y/3y；我方不保留期限，不能合成一个可比中位。",
    },
    "community": {
        "ext_markets": ["community"],
        "scope": "instance",
        "comparable": False,
        "note": "GPU Economy 的 community 同时包含 marketplace floor 与实例供给；我方把 floor 单列为 marketplace，语义不等价。",
    },
    "marketplace": {
        "ext_markets": ["community"],
        "scope": "marketplace_floor",
        "comparable": False,
        "note": "我方 marketplace 对应 GPU Economy community 中的 marketplace floor 子集；只是子集，不是等号。",
    },
    "serverless": {
        "ext_markets": ["serverless"],
        "scope": None,
        "comparable": True,
        "note": "可比口径与 on-demand 相同；serverless 按秒/共享，不能与整租混读。",
    },
}


# ---------------------------------------------------------------------------
# Loading and integrity checks
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_gz(path: Path) -> bytes:
    with path.open("rb") as raw_handle:
        with gzip.GzipFile(fileobj=raw_handle, mode="rb") as handle:
            return handle.read()


def load_external(
    snapshot_dir: Path | str | None = None,
    verify: bool = True,
) -> Dict[str, Any]:
    """Load a committed snapshot, optionally verifying every checksum and count.

    ``snapshot_dir=None`` selects the newest ``YYYY-MM-DD`` directory under
    ``SNAPSHOT_ROOT``.  Raises ``ValueError`` when metadata, checksums, versions,
    or file counts disagree; a silently corrupted snapshot must fail the build
    instead of degrading to zeros.
    """
    root = Path(snapshot_dir) if snapshot_dir is not None else latest_snapshot_dir()
    metadata_path = root / "metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"gpueconomy snapshot metadata missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for field in (
        "source",
        "source_url",
        "fetched_at",
        "data_updated_at",
        "methodology_version",
        "methodology_changelog",
        "license",
        "attribution",
        "files",
    ):
        if not metadata.get(field):
            raise ValueError(f"gpueconomy metadata missing {field}")
    if metadata["source"] != EXTERNAL_SOURCE:
        raise ValueError(f"unexpected external source: {metadata['source']!r}")
    version = metadata["methodology_version"]
    if not isinstance(version, str) or not METHODOLOGY_RE.match(version):
        raise ValueError(f"gpueconomy metadata has invalid methodology_version: {version!r}")

    documents: Dict[str, Dict[str, Any]] = {}
    for item in metadata["files"]:
        raw_name = Path(str(item.get("path") or "")).name
        name = str(item.get("source") or (raw_name[:-3] if raw_name.endswith(".gz") else raw_name))
        path = root / str(item.get("path") or "")
        if not path.is_file():
            raise FileNotFoundError(f"gpueconomy snapshot file missing: {path}")
        payload = path.read_bytes()
        if verify:
            if len(payload) != item.get("bytes_gz"):
                raise ValueError(f"{path.name}: bytes_gz mismatch")
            if _sha256(payload) != item.get("sha256_gz"):
                raise ValueError(f"{path.name}: sha256_gz mismatch")
        raw = _read_gz(path)
        if verify:
            if len(raw) != item.get("bytes_raw"):
                raise ValueError(f"{path.name}: bytes_raw mismatch")
            if _sha256(raw) != item.get("sha256_raw"):
                raise ValueError(f"{path.name}: sha256_raw mismatch")
        documents[name] = json.loads(raw.decode("utf-8"))

    if "prices.json" not in documents or "gpus.json" not in documents:
        raise ValueError("gpueconomy snapshot must contain prices.json and gpus.json")
    prices_version = documents["prices.json"].get("methodology_version")
    if prices_version != metadata["methodology_version"]:
        raise ValueError(
            "gpueconomy prices.json methodology_version does not match metadata: "
            f"{prices_version!r} != {metadata['methodology_version']!r}"
        )
    if verify:
        declared = (documents["prices.json"].get("count"), documents["gpus.json"].get("count"))
        actual = (len(documents["prices.json"].get("prices") or []), len(documents["gpus.json"].get("gpus") or []))
        if declared != actual:
            raise ValueError(f"gpueconomy snapshot counts disagree: declared={declared} actual={actual}")

    return {
        "metadata": metadata,
        "snapshot_dir": str(root),
        "documents": documents,
        "prices": documents["prices.json"],
        "gpus": documents["gpus.json"],
        "providers": documents.get("providers.json") or {},
        "history": documents.get("history.json") or {},
        "token_cost": documents.get("token-cost.json") or {},
        "changelog": documents.get("changelog.json") or {},
        "price_index": documents.get("price-index.json") or {},
    }


def snapshot_relative_path(snapshot_dir: Path | str | None = None) -> str:
    """Stable repository-relative snapshot path for public payloads."""
    path = (Path(snapshot_dir) if snapshot_dir is not None else latest_snapshot_dir()).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


# ---------------------------------------------------------------------------
# Comparable math
# ---------------------------------------------------------------------------


def _percentiles(values: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    """Linear-interpolated P25/P75, ``(n-1)*p``; null below four providers."""
    if len(values) < 4:
        return None, None

    def quantile(p: float) -> float:
        position = (len(values) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        fraction = position - lower
        return values[lower] + (values[upper] - values[lower]) * fraction

    return round(quantile(0.25), 6), round(quantile(0.75), 6)


def _row_scope_ok(row: Dict[str, Any], scope: Optional[str]) -> bool:
    if scope == "marketplace_floor":
        return row.get("price_scope") == "marketplace_floor"
    if scope:
        return row.get("price_scope") == scope
    return row.get("price_scope") != "marketplace_floor"


def _eligible_rows(
    prices_doc: Dict[str, Any],
    gpu_ids: Iterable[str],
    ext_markets: Iterable[str],
    scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    wanted_gpus = set(gpu_ids)
    wanted_markets = set(ext_markets)
    rows = [
        row
        for row in prices_doc.get("prices") or []
        if row.get("gpu_id") in wanted_gpus
        and row.get("market") in wanted_markets
        and row.get("status") == "live"
        and row.get("listed_currency") == "USD"
        and _row_scope_ok(row, scope)
    ]
    return rows


def _quote_sort_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        float(row.get("usd_per_gpu_hour") or 0),
        str(row.get("provider_id") or ""),
        str(row.get("gpu_id") or ""),
        str(row.get("region") or ""),
        str(row.get("instance") or ""),
        str(row.get("source_url") or ""),
    )


def _our_provider_for_row(row: Dict[str, Any]) -> Optional[str]:
    """Map one external row to our provider id, or None if there is no equivalent."""
    ext_id = str(row.get("provider_id") or "")
    if ext_id == "paperspace":
        return "digitalocean" if row.get("region") == "GPU Droplets" else None
    return EXT_TO_OUR.get(ext_id, ext_id)


def _sku_ambiguous(card_id: str, row: Dict[str, Any], market: str) -> bool:
    if card_id in ("H100", "A100"):
        return True
    if card_id == "H200" and str(row.get("provider_id") or "") == "runpod":
        return True
    if card_id == "RTX PRO 6000" and market == "community":
        return True
    return False


def _quote(row: Dict[str, Any], card_id: str, market: str) -> Dict[str, Any]:
    return {
        "source_layer": EXTERNAL_SOURCE,
        "provider_id": row.get("provider_id"),
        "provider": row.get("provider"),
        "gpu_id": row.get("gpu_id"),
        "market": market,
        "price_scope": row.get("price_scope"),
        "region": row.get("region"),
        "instance": row.get("instance"),
        "usd_per_gpu_hour": round(float(row["usd_per_gpu_hour"]), 6),
        "listed_price_hour": row.get("listed_price_hour"),
        "listed_currency": row.get("listed_currency"),
        "fx_rate": row.get("fx_rate"),
        "fx_date": row.get("fx_date"),
        "gpu_count": row.get("gpu_count"),
        "source_url": row.get("source_url"),
        "scraped_at": row.get("scraped_at"),
        "status": row.get("status"),
        "sku_ambiguous": _sku_ambiguous(card_id, row, market),
    }


def _providers_and_quotes(
    rows: Sequence[Dict[str, Any]], card_id: str, market: str
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """One cheapest eligible row per external provider, plus its quote count."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("provider_id") or ""), []).append(row)
    best: Dict[str, Dict[str, Any]] = {}
    for provider_id, items in grouped.items():
        ordered = sorted(items, key=_quote_sort_key)
        choice = dict(ordered[0])
        choice["_quote_count"] = len(items)
        best[provider_id] = choice
    return best, [best[key] for key in sorted(best)]


def ext_market_summary(
    prices_doc: Dict[str, Any],
    gpu_id: str,
    market: str,
    *,
    include_quotes: bool = False,
    card_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Summary for one of our markets, using the matching GPU Economy market view.

    ``card_id`` is our display id (``H100``, ``RTX PRO 6000``).  When omitted it is
    inferred from the external gpu id; passing it explicitly avoids treating
    ``h100-sxm`` as a separate card for quote-level SKU warnings.
    """
    view = MARKET_VIEWS[market]
    resolved_card = card_id or CARD_BY_EXT_GPU.get(gpu_id)
    rows = _eligible_rows(prices_doc, [gpu_id], view["ext_markets"], view["scope"])
    best, ordered = _providers_and_quotes(rows, gpu_id, market)
    values = sorted(float(row["usd_per_gpu_hour"]) for row in best.values())
    p25, p75 = _percentiles(values)
    scraped = [str(row.get("scraped_at")) for row in rows if row.get("scraped_at")]
    payload: Dict[str, Any] = {
        "providers": len(values),
        "rows": len(rows),
        "median": round(median(values), 6) if values else None,
        "p25": p25,
        "p75": p75,
        "min": round(values[0], 6) if values else None,
        "max": round(values[-1], 6) if values else None,
        "source_url": PRICES_URL,
        "scraped_at": max(scraped) if scraped else None,
        "comparable": bool(view["comparable"]),
        "note": view["note"],
    }
    if include_quotes:
        payload["quotes"] = [
            {**_quote(row, resolved_card or "", market), "quotes": int(row["_quote_count"])}
            for row in ordered
        ]
    return payload


def _round_or_none(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    return None


def _published(gpus_doc: Dict[str, Any], gpu_id: str) -> Dict[str, Any]:
    for item in gpus_doc.get("gpus") or []:
        if item.get("id") == gpu_id:
            return {
                "rate_cards": item.get("rate_cards"),
                "median": _round_or_none(item.get("rate_card_median_usd_per_gpu_hour")),
                "p25": _round_or_none(item.get("rate_card_p25_usd_per_gpu_hour")),
                "p75": _round_or_none(item.get("rate_card_p75_usd_per_gpu_hour")),
            }
    return {"rate_cards": None, "median": None, "p25": None, "p75": None}


def _excluded_counts(prices_doc: Dict[str, Any], gpu_id: str) -> Dict[str, int]:
    counts = {"not_live": 0, "marketplace_floor": 0, "market_not_on_demand": 0, "non_usd": 0}
    for row in prices_doc.get("prices") or []:
        if row.get("gpu_id") != gpu_id:
            continue
        if row.get("status") != "live":
            counts["not_live"] += 1
        elif row.get("price_scope") == "marketplace_floor":
            counts["marketplace_floor"] += 1
        elif row.get("market") != "on_demand":
            counts["market_not_on_demand"] += 1
        elif row.get("listed_currency") != "USD":
            counts["non_usd"] += 1
    return counts


def _family_provider_set(
    prices_doc: Dict[str, Any],
    gpu_ids: Sequence[str],
    market: str,
) -> set[str]:
    view = MARKET_VIEWS[market]
    rows = _eligible_rows(prices_doc, gpu_ids, view["ext_markets"], view["scope"])
    return {
        provider
        for provider in (_our_provider_for_row(row) for row in rows)
        if provider
    }


# ---------------------------------------------------------------------------
# Cross-check
# ---------------------------------------------------------------------------


def _own_card(full: Dict[str, Any], card_id: str) -> Optional[Dict[str, Any]]:
    for card in full.get("cards") or []:
        if card.get("id") == card_id:
            return card
    return None


def _own_market_state(card: Optional[Dict[str, Any]], market: str) -> Dict[str, Any]:
    if not card:
        return {"median": None, "providers": 0, "provider_ids": set(), "as_of": None}
    node = (card.get("markets") or {}).get(market) or {}
    latest = node.get("latest") or {}
    provider_ids = {
        str(item.get("providerId"))
        for item in latest.get("providers") or []
        if item.get("providerId")
    }
    count = latest.get("providerCount")
    if count is None:
        count = len(provider_ids) if provider_ids else 0
    return {
        "median": latest.get("value"),
        "providers": int(count),
        "provider_ids": provider_ids,
        "as_of": latest.get("date") or card.get("asOf"),
    }


def _coverage(
    ext_providers: int,
    overlap_count: int,
    own_providers: int,
    sku_mismatch: bool = False,
    mixed_sku: bool = False,
    stale: bool = False,
) -> str:
    """Coverage priority: own thin wins even over SKU/mixed warnings."""
    if ext_providers <= 0:
        return "none"
    if own_providers < CROSSCHECK_MIN_OWN_PROVIDERS:
        return "thin"
    if sku_mismatch:
        return "sku_mismatch"
    if mixed_sku:
        return "mixed"
    if stale:
        return "stale"
    if ext_providers < 4 or overlap_count < 2:
        return "thin"
    return "ok"


def _is_stale(own_as_of: Optional[str], ext_as_of: Optional[str]) -> bool:
    if not own_as_of or not ext_as_of:
        return False
    try:
        return (date.fromisoformat(own_as_of) - date.fromisoformat(ext_as_of)).days > 7
    except ValueError:
        return False


def build_crosscheck(full: Dict[str, Any], external: Dict[str, Any]) -> Dict[str, Any]:
    """Build 11 cards × 6 markets of own-vs-external reference rows.

    Only comparable markets carry ``diff_pct``: on-demand is primary, while
    spot/serverless reuse the same live/non-floor/USD rule.  A100 is
    ``sku_mismatch`` and never receives a diff.  H100 keeps ``match_id`` (h100)
    and ``benchmark_id`` (h100-sxm) as two separate values; its card-level diff
    is retained with ``coverage="mixed"`` and never implies provider equivalence.
    """
    metadata = external["metadata"]
    prices_doc = external["prices"]
    gpus_doc = external["gpus"]
    ext_as_of = str(metadata.get("data_updated_at") or "")[:10] or None
    own_as_of_default = full.get("asOf")

    rows: List[Dict[str, Any]] = []
    for mapping in CARD_MAP:
        card = _own_card(full, mapping["card_id"])
        published = _published(gpus_doc, mapping["match_id"])
        benchmark_median = None
        if mapping["benchmark_id"]:
            benchmark_median = ext_market_summary(
                prices_doc,
                mapping["benchmark_id"],
                "on_demand",
                card_id=mapping["card_id"],
            )["median"]

        for market in MARKETS:
            own = _own_market_state(card, market)
            own_as_of = own["as_of"] or own_as_of_default
            ext_summary = ext_market_summary(
                prices_doc,
                mapping["match_id"],
                market,
                card_id=mapping["card_id"],
            )
            view = MARKET_VIEWS[market]

            family = _family_provider_set(prices_doc, mapping["family_ids"], market)
            match_only = _family_provider_set(prices_doc, [mapping["match_id"]], market)
            # Keep our own provider id/label in the payload; canonical ids only join.
            own_actual = {
                CANONICAL_OWN.get(provider, provider): provider for provider in own["provider_ids"]
            }
            overlap_family = sorted(
                own_actual[canonical]
                for canonical in family
                if canonical in own_actual
            )
            overlap_match = sorted(
                own_actual[canonical]
                for canonical in match_only
                if canonical in own_actual
            )

            stale = _is_stale(own_as_of, ext_as_of)
            own_providers = int(own["providers"] or 0)
            own_thin = own_providers < CROSSCHECK_MIN_OWN_PROVIDERS
            coverage = _coverage(
                int(ext_summary["providers"] or 0),
                len(overlap_family),
                own_providers,
                sku_mismatch=bool(mapping["sku_mismatch"]),
                mixed_sku=bool(mapping.get("mixed_sku")),
                stale=stale,
            )
            # H100 keeps a card-level diff even though its SKU mix prevents
            # provider-level equivalence; A100 (sku_mismatch) never gets a diff.
            # A thin own panel never gets a diff.
            comparable = bool(
                view["comparable"]
                and coverage in ("ok", "mixed")
                and own_providers >= CROSSCHECK_MIN_OWN_PROVIDERS
            )
            own_median = own["median"]
            ext_median = ext_summary["median"]
            diff_pct = None
            if comparable and own_median is not None and ext_median:
                diff_pct = round((float(own_median) / float(ext_median) - 1) * 100, 2)

            notes: List[str] = []
            if mapping["note"]:
                notes.append(mapping["note"])
            if market != "on_demand" and view["note"]:
                notes.append(view["note"])
            if own["providers"] > 0 and not own["provider_ids"]:
                notes.append(
                    "own provider 列表不可用（trimmed payload）；crosscheck 应传入 trim 前的 full_landscape 结果。"
                )
            if coverage == "none":
                notes.append("该 market 没有可比 external 报价。")
            elif ext_summary["providers"] < 4 or len(overlap_family) < 2:
                notes.append(
                    f"external 覆盖偏薄（ext {ext_summary['providers']} 家，重叠 {len(overlap_family)} 家）。"
                )
            if stale:
                notes.append(f"external 数据比我方旧（{ext_as_of} vs {own_as_of}）。")
            if mapping["sku_mismatch"] and "型号不一致" not in mapping["note"]:
                notes.append("型号不一致，仅覆盖参考，不计算差值。")

            rows.append(
                {
                    "card_id": mapping["card_id"],
                    "market": market,
                    "match_id": mapping["match_id"],
                    "benchmark_id": mapping["benchmark_id"] if market == "on_demand" else None,
                    "context_ids": list(mapping["context_ids"]),
                    "own_median": own_median,
                    "own_providers": own["providers"],
                    "own_thin": own_thin,
                    "ext_median": ext_median,
                    "ext_providers": ext_summary["providers"],
                    "ext_source_url": PRICES_URL,
                    "ext_scraped_at": ext_summary["scraped_at"],
                    "ext_median_published": published["median"],
                    "ext_benchmark_median": benchmark_median if market == "on_demand" else None,
                    "ext_benchmark_id": mapping["benchmark_id"] if market == "on_demand" else None,
                    "mixed_sku": bool(mapping.get("mixed_sku")),
                    "diff_pct": diff_pct,
                    "overlap_count": len(overlap_family),
                    "overlap_count_match": len(overlap_match),
                    "overlap_scope": mapping["overlap_scope"],
                    "overlap_providers": overlap_family,
                    "coverage": coverage,
                    "comparable": comparable,
                    "as_of": own_as_of,
                    "ext_as_of": ext_as_of,
                    "note": " ".join(notes).strip() or None,
                }
            )

    return {
        "source": EXTERNAL_SOURCE,
        "source_url": metadata.get("source_url"),
        "license": metadata.get("license"),
        "license_url": metadata.get("license_url") or LICENSE_URL,
        "attribution": metadata.get("attribution"),
        "methodology_version": metadata.get("methodology_version"),
        "own_methodology_version": full.get("methodologyVersion"),
        "ext_methodology_version": metadata.get("methodology_version"),
        "methodology_changelog": metadata.get("methodology_changelog"),
        "data_updated_at": metadata.get("data_updated_at"),
        "retrieved_at": metadata.get("fetched_at"),
        "citation": (
            f"{metadata.get('attribution')} · {metadata.get('license')} · "
            f"methodology {metadata.get('methodology_version')} · "
            f"data {str(metadata.get('data_updated_at') or '')[:10]}"
        ),
        "prices_source_url": PRICES_URL,
        "published_source_url": GPUS_URL,
        "as_of": full.get("asOf"),
        "ext_as_of": ext_as_of,
        "rules": {
            "comparable": COMPARABLE_RULE,
            "quartiles": "linear interpolation (n-1)*p; P25/P75 published only when n>=4",
            "published": "gpus.json rate_card_median (includes serverless and non-USD); audit only, never used for diff",
            "dedup": "one value per provider, taking the cheapest eligible rate",
            "diff": "diff_pct = own_median / ext_median - 1; this is a methodology/sample gap, not a transaction price spread",
            "overlap_definition": (
                "overlap = intersection of our latest-day on-demand provider set for the card "
                "and GPU Economy's family provider set (H100 family = h100+h100-sxm+h100-pcie); "
                "overlap_count_match uses match_id only. Because this is a latest-day panel, "
                "H100/H200/A100 counts (16/12/12) differ from facts-external §9.4's "
                "historical-provider-pool counts (17/14/13)."
            ),
            "methodology_versions": (
                "own_methodology_version is AI Compute Economics'; methodology_version and "
                "ext_methodology_version refer to GPU Economy."
            ),
            "changes": "filtered and recomputed by AI Compute Economics; not the GPU Economy published figure",
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Public payload
# ---------------------------------------------------------------------------


def _card_public(
    external: Dict[str, Any],
    mapping: Dict[str, Any],
) -> Dict[str, Any]:
    prices_doc = external["prices"]
    gpus_doc = external["gpus"]
    markets: Dict[str, Any] = {}
    for market in MARKETS:
        node = ext_market_summary(
            prices_doc,
            mapping["match_id"],
            market,
            include_quotes=(market == "on_demand"),
            card_id=mapping["card_id"],
        )
        node["ext_gpu_id"] = mapping["match_id"]
        if mapping["sku_mismatch"]:
            node["comparable"] = False
        # The per-market caveat is identical for every card; keep it once in
        # ``market_notes`` instead of repeating it eleven times.
        node.pop("note", None)
        markets[market] = node

    benchmark = None
    if mapping["benchmark_id"]:
        benchmark = ext_market_summary(
            prices_doc,
            mapping["benchmark_id"],
            "on_demand",
            card_id=mapping["card_id"],
        )
        benchmark["ext_gpu_id"] = mapping["benchmark_id"]
        benchmark["market"] = "on_demand"
        benchmark["usage"] = "benchmark_only_on_demand"

    context = []
    for gpu_id in mapping["context_ids"]:
        node = ext_market_summary(
            prices_doc, gpu_id, "on_demand", card_id=mapping["card_id"]
        )
        node["ext_gpu_id"] = gpu_id
        context.append(node)

    published = _published(gpus_doc, mapping["match_id"])
    published["source_url"] = GPUS_URL
    published["data_updated_at"] = external["metadata"].get("data_updated_at")

    return {
        "card_id": mapping["card_id"],
        "match_id": mapping["match_id"],
        "benchmark_id": mapping["benchmark_id"],
        "context_ids": list(mapping["context_ids"]),
        "sku_mismatch": bool(mapping["sku_mismatch"]),
        "mixed_sku": bool(mapping.get("mixed_sku")),
        "note": mapping["note"],
        "published": published,
        "benchmark": benchmark,
        "context": context,
        "markets": markets,
        "excluded_counts": _excluded_counts(prices_doc, mapping["match_id"]),
    }


def public_external(external: Dict[str, Any], crosscheck: Dict[str, Any]) -> Dict[str, Any]:
    """Page-facing external payload: 11 cards, market summaries, included quotes.

    Changelog and history stay out of the page payload; they live in the archived
    snapshot only.  ``crosscheck`` supplies our own methodology version and its
    rows still belong in the separate ``crosscheck.json`` file.
    """
    metadata = external["metadata"]
    cards = [_card_public(external, mapping) for mapping in CARD_MAP]
    return {
        "name": "GPU Economy external reference",
        "source": EXTERNAL_SOURCE,
        "source_url": metadata.get("source_url"),
        "license": metadata.get("license"),
        "license_url": metadata.get("license_url") or LICENSE_URL,
        "attribution": metadata.get("attribution"),
        "methodology_version": metadata.get("methodology_version"),
        "own_methodology_version": crosscheck.get("own_methodology_version"),
        "methodology_changelog": metadata.get("methodology_changelog"),
        "data_updated_at": metadata.get("data_updated_at"),
        "retrieved_at": metadata.get("fetched_at"),
        "citation": (
            f"{metadata.get('attribution')} · {metadata.get('license')} · "
            f"methodology {metadata.get('methodology_version')} · "
            f"data {str(metadata.get('data_updated_at') or '')[:10]}"
        ),
        "snapshot": snapshot_relative_path(external.get("snapshot_dir") or SNAPSHOT_DIR),
        "rules": {
            "comparable": COMPARABLE_RULE,
            "published": "gpus.json rate_card_median (includes serverless and non-USD); audit only",
            "dedup": "one value per provider, taking the cheapest eligible rate",
            "quotes": "included quotes cover all market views; on_demand is the primary comparison",
            "methodology_versions": (
                "own_methodology_version is AI Compute Economics'; methodology_version is "
                "GPU Economy's external methodology version."
            ),
            "changes": "filtered and recomputed by AI Compute Economics; not the GPU Economy published figure",
            "scope": "reference layer only; own medians and indexes are never replaced",
        },
        "market_notes": {market: MARKET_VIEWS[market]["note"] for market in MARKETS},
        "cards": cards,
        "providers": [dict(item) for item in ALIAS_ENTRIES],
    }


# ---------------------------------------------------------------------------
# Build integration
# ---------------------------------------------------------------------------


def write_external_data(
    full: Dict[str, Any],
    out_dir: Path | str,
    snapshot_dir: Path | str | None = None,
) -> Dict[str, Any]:
    """Write ``external/gpueconomy.json`` and ``crosscheck.json`` under ``out_dir``.

    ``out_dir`` is the public data directory (normally ``public/data``).  The
    caller owns that directory; tests pass a temporary directory.  ``snapshot_dir``
    defaults to the newest committed ``YYYY-MM-DD`` snapshot.
    """
    external = load_external(snapshot_dir)
    crosscheck = build_crosscheck(full, external)
    external_payload = public_external(external, crosscheck)
    target = Path(out_dir)
    external_dir = target / "external"
    external_dir.mkdir(parents=True, exist_ok=True)
    external_path = external_dir / "gpueconomy.json"
    crosscheck_path = target / "crosscheck.json"
    external_path.write_text(
        json.dumps(external_payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    crosscheck_path.write_text(
        json.dumps(crosscheck, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return {
        "external": str(external_path),
        "crosscheck": str(crosscheck_path),
        "cards": len(external_payload["cards"]),
        "rows": len(crosscheck["rows"]),
        "external_bytes": external_path.stat().st_size,
        "crosscheck_bytes": crosscheck_path.stat().st_size,
    }
