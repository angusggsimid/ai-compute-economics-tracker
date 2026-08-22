#!/usr/bin/env python3
"""Collect GPU rental order book snapshots (GPUPerHour / Vast.ai / RunPod) into a versionable daily history.

订单簿是时点观测：当天抓不到就永远是缺口，无法回填。因此本脚本按日累积
(date, source, series) 粒度的深度汇总，供 Supply Price 时钟未来评估
“价格下降是否伴随订单簿深度扩大”。它是非阻塞信息源：
单源失败记录进 quality，全部失败也只把 refreshStatus 标为 failed，
不阻塞正式页面发布（页面当前不展示该层）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, quantiles
from typing import Any, Optional
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "gpu_orderbook_history.json"
SNAPSHOT_DIR = ROOT / "tracker_snapshots" / "market_facts"
USER_AGENT = "AIComputeEconomicsTracker/1.0"

GPUPERHOUR_OFFERS_API = "https://api.gpuindexes.com/api/offers"
RUNPOD_GRAPHQL_API = "https://api.runpod.io/graphql"
RUNPOD_GRAPHQL_SPEC = "https://graphql-spec.runpod.io/"
VAST_BUNDLES_API = "https://console.vast.ai/api/v0/bundles/"

GPU_FOCUS = ("H100", "H200", "B200", "B300", "A100", "MI300X", "RTX 4090", "RTX 5090", "L40S")
GPUPERHOUR_GPU_QUERIES = {
    "H100": "h100-sxm-80gb,h100-pcie-80gb,h100-nvl",
    "H200": "h200-sxm,h200-nvl",
    "B200": "b200",
    "B300": "b300",
    "A100": "a100-sxm-80gb,a100-pcie-80gb,a100-sxm-40gb,a100-pcie-40gb",
    "MI300X": "mi300x",
    "L40S": "l40s",
    "RTX 4090": "rtx-4090",
    "RTX 5090": "rtx-5090",
}
GPUPERHOUR_LIMIT = 100
VAST_PAYLOAD = {
    "limit": 250,
    "type": "on-demand",
    "verified": {"eq": True},
    "rentable": {"eq": True},
    "rented": {"eq": False},
}
ROW_FIELDS = (
    "date",
    "source",
    "series",
    "unit",
    "offerCount",
    "serverTotal",
    "truncated",
    "gpuCountTotal",
    "minPrice",
    "p25Price",
    "medianPrice",
    "p75Price",
    "maxPrice",
    "providerCount",
)


def _get_json(url: str, params: Optional[dict] = None) -> tuple[dict[str, Any], bytes]:
    if params:
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = f"{url}?{query}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw), raw


def _post_json(url: str, payload: dict) -> tuple[dict[str, Any], bytes]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw), raw


def _family(value: Any, *, fallback: str = "unknown") -> str:
    text = str(value or "").lower().replace("_", " ").replace("-", " ")
    checks = [
        ("rtx 5090", "RTX 5090"),
        ("rtx 4090", "RTX 4090"),
        ("mi300x", "MI300X"),
        ("gh200", "GH200"),
        ("b300", "B300"),
        ("b200", "B200"),
        ("h200", "H200"),
        ("h100", "H100"),
        ("a100", "A100"),
        ("l40s", "L40S"),
    ]
    for needle, family in checks:
        if needle in text:
            return family
    return fallback


def _positive(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _summary_row(
    *,
    date_iso: str,
    source: str,
    series: str,
    unit: str,
    prices: list[float],
    gpu_count_total: Optional[int],
    server_total: Optional[int] = None,
    provider_count: Optional[int] = None,
) -> dict[str, Any]:
    ordered = sorted(prices)
    middle = median(ordered)
    if len(ordered) >= 4:
        quartiles = quantiles(ordered, n=4)
        p25, p75 = quartiles[0], quartiles[2]
    else:
        p25 = p75 = middle
    return {
        "date": date_iso,
        "source": source,
        "series": series,
        "unit": unit,
        "offerCount": len(ordered),
        "serverTotal": server_total,
        "truncated": bool(server_total is not None and server_total > len(ordered)),
        "gpuCountTotal": gpu_count_total,
        "minPrice": round(ordered[0], 6),
        "p25Price": round(p25, 6),
        "medianPrice": round(middle, 6),
        "p75Price": round(p75, 6),
        "maxPrice": round(ordered[-1], 6),
        "providerCount": provider_count,
    }


def _gpuperhour_parse(payload: dict[str, Any], family: str) -> tuple[list[float], int, set[str]]:
    """单次家族查询响应 -> (有效价格列表, 可租 GPU 总数, 提供方集合)。"""
    prices: list[float] = []
    gpu_count_total = 0
    providers: set[str] = set()
    for offer in payload.get("data") or []:
        if offer.get("isAvailable") is not True:
            continue
        if str(offer.get("currency") or "USD").upper() != "USD":
            continue
        if _family(" ".join([
            str((offer.get("gpu") or {}).get("slug") or ""),
            str((offer.get("gpu") or {}).get("name") or ""),
        ])) != family:
            continue
        price = _positive(offer.get("pricePerGpu"))
        if price is None:
            continue
        prices.append(price)
        gpu_count_total += int(offer.get("gpuCount") or 1)
        providers.add(str(offer.get("provider") or "unknown"))
    return prices, gpu_count_total, providers


def collect_gpuperhour(date_iso: str) -> tuple[list[dict[str, Any]], bytes, int]:
    """返回 (汇总行, 原始响应字节, 解析的家族数)。原始字节是拼接前的最后一个响应体。"""
    rows: list[dict[str, Any]] = []
    raw_tail = b""
    parsed_families = 0
    for family, slug_query in GPUPERHOUR_GPU_QUERIES.items():
        payload, raw_tail = _get_json(
            GPUPERHOUR_OFFERS_API,
            {
                "gpu": slug_query,
                "available": "true",
                "limit": GPUPERHOUR_LIMIT,
                "sortBy": "pricePerGpu",
                "sortOrder": "asc",
            },
        )
        prices, gpu_count_total, providers = _gpuperhour_parse(payload, family)
        server_total = int((payload.get("pagination") or {}).get("total") or 0)
        if not prices:
            continue
        parsed_families += 1
        rows.append(_summary_row(
            date_iso=date_iso,
            source="gpuperhour",
            series=family,
            unit="offers",
            prices=prices,
            gpu_count_total=gpu_count_total,
            server_total=server_total,
            provider_count=len(providers),
        ))
    if not rows:
        raise ValueError("GPUPerHour returned no usable family summaries")
    rows.sort(key=lambda row: row["series"])
    return rows, raw_tail, parsed_families


def _vast_parse(payload: dict[str, Any]) -> tuple[dict[str, list[float]], dict[str, int]]:
    grouped: dict[str, list[float]] = {}
    gpu_counts: dict[str, int] = {}
    for offer in payload.get("offers") or []:
        if offer.get("rentable") is not True or offer.get("rented") is True:
            continue
        if str(offer.get("verification") or "").lower() != "verified":
            continue
        family = _family(offer.get("gpu_name"))
        if family not in GPU_FOCUS:
            continue
        try:
            num_gpus = int(offer.get("num_gpus") or 0)
        except (TypeError, ValueError):
            continue
        total_price = _positive(offer.get("dph_total"))
        if not num_gpus or total_price is None:
            continue
        grouped.setdefault(family, []).append(total_price / num_gpus)
        gpu_counts[family] = gpu_counts.get(family, 0) + num_gpus
    return grouped, gpu_counts


def collect_vast(date_iso: str) -> tuple[list[dict[str, Any]], bytes]:
    payload, raw = _post_json(VAST_BUNDLES_API, VAST_PAYLOAD)
    grouped, gpu_counts = _vast_parse(payload)
    rows = [
        _summary_row(
            date_iso=date_iso,
            source="vast",
            series=family,
            unit="offers",
            prices=prices,
            gpu_count_total=gpu_counts.get(family),
        )
        for family, prices in sorted(grouped.items())
    ]
    if not rows:
        raise ValueError("Vast.ai returned no usable verified on-demand offers")
    return rows, raw


RUNPOD_QUERY = """
query gpuTypes($input: GpuTypeFilter) {
  gpuTypes(input: $input) {
    id displayName manufacturer memoryInGb secureCloud communityCloud
    securePrice communityPrice oneWeekPrice oneMonthPrice communitySpotPrice secureSpotPrice throughput
    maxGpuCount maxGpuCountCommunityCloud maxGpuCountSecureCloud
    lowestPrice {
      gpuName gpuTypeId minimumBidPrice uninterruptablePrice stockStatus
    }
  }
}
"""


def _runpod_parse(payload: dict[str, Any]) -> tuple[dict[str, list[float]], dict[str, int]]:
    """型号级解析：MIG 剔除、$0/不可用档抑制；价格取该型号最低可用按需档（secure/community）。"""
    grouped: dict[str, list[float]] = {}
    gpu_counts: dict[str, int] = {}
    for gpu_type in ((payload.get("data") or {}).get("gpuTypes") or []):
        identity = " ".join([str(gpu_type.get("id") or ""), str(gpu_type.get("displayName") or "")])
        if "mig" in identity.lower():
            continue
        family = _family(identity)
        if family not in GPU_FOCUS:
            continue
        tier_prices = []
        if gpu_type.get("secureCloud") is True:
            price = _positive(gpu_type.get("securePrice"))
            if price is not None:
                tier_prices.append(price)
        if gpu_type.get("communityCloud") is True:
            price = _positive(gpu_type.get("communityPrice"))
            if price is not None:
                tier_prices.append(price)
        if not tier_prices:
            continue
        grouped.setdefault(family, []).append(min(tier_prices))
        max_count = gpu_type.get("maxGpuCount")
        if isinstance(max_count, (int, float)):
            gpu_counts[family] = gpu_counts.get(family, 0) + int(max_count)
    return grouped, gpu_counts


def collect_runpod(date_iso: str) -> tuple[list[dict[str, Any]], bytes]:
    """RunPod 是型号级挂牌而非逐 offer 订单簿：unit="types"，价格取该型号最低可用按需档。"""
    payload, raw = _post_json(RUNPOD_GRAPHQL_API, {"query": RUNPOD_QUERY, "variables": {"input": {}}})
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False)[:500])
    grouped, gpu_counts = _runpod_parse(payload)
    rows = [
        _summary_row(
            date_iso=date_iso,
            source="runpod",
            series=family,
            unit="types",
            prices=prices,
            gpu_count_total=gpu_counts.get(family),
        )
        for family, prices in sorted(grouped.items())
    ]
    if not rows:
        raise ValueError("RunPod returned no usable full-GPU on-demand types")
    return rows, raw


def _load_previous(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["rows"]
        if not isinstance(rows, list):
            raise ValueError("rows is not a list")
        for row in rows:
            if not all(row.get(field) for field in ("date", "source", "series")):
                raise ValueError(f"malformed row: {row}")
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"gpu_orderbook_history.json 缓存损坏或 schema 不符（{exc}）；"
            "拒绝静默覆盖累积历史，请人工修复后重跑。"
        )
    return rows


def _merge(previous_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]], date_iso: str) -> list[dict[str, Any]]:
    """按 (date, source, series) 去重；当天的旧观测整体丢弃后写入最新一轮，其余日期保留。"""
    merged: dict[tuple[str, str, str], dict[str, Any]] = {
        (row["date"], row["source"], row["series"]): {field: row.get(field) for field in ROW_FIELDS}
        for row in previous_rows
        if row["date"] != date_iso
    }
    for row in new_rows:
        merged[(row["date"], row["source"], row["series"])] = row
    return sorted(merged.values(), key=lambda row: (row["date"], row["source"], row["series"]))


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    date_iso = fetched_at[:10]

    collectors = {
        "gpuperhour": collect_gpuperhour,
        "vast": collect_vast,
        "runpod": collect_runpod,
    }
    all_rows: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    quality: list[dict[str, str]] = []
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = fetched_at.replace("-", "").replace(":", "").lower()

    for name, collector in collectors.items():
        try:
            rows, raw, *_extra = collector(date_iso)
            all_rows.extend(rows)
            snapshot_path = SNAPSHOT_DIR / f"{stamp}-orderbook-{name}.json"
            snapshot_path.write_bytes(raw)
            sources[name] = {
                "url": collectors_url(name),
                "fetchedAt": fetched_at,
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "snapshotPath": str(snapshot_path.relative_to(ROOT)),
                "status": "fresh",
            }
        except Exception as exc:
            quality.append({"source": name, "status": "failed", "message": str(exc)})
            sources[name] = {
                "url": collectors_url(name),
                "fetchedAt": fetched_at,
                "status": "failed",
                "message": str(exc),
            }

    ok_sources = [name for name in sources if sources[name].get("status") == "fresh"]
    if len(ok_sources) == len(collectors):
        refresh_status = "fresh"
    elif ok_sources:
        refresh_status = "partial"
    else:
        refresh_status = "failed"

    previous_rows = _load_previous(OUTPUT_PATH)
    sorted_rows = _merge(previous_rows, all_rows, date_iso)

    payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": refresh_status,
        "publishable": True,
        "rowSchema": list(ROW_FIELDS),
        "metricNotes": {
            "gpuperhour": "available=true 报价逐条聚合；unit=offers；价格为每 GPU 小时报价。",
            "vast": "verified+rentable+未租用 on-demand bundle；unit=offers；价格=dph_total/num_gpus。",
            "runpod": "非 MIG 完整卡型号挂牌；unit=types；价格=secure/community 两档中较低的可用按需价。",
        },
        "rows": sorted_rows,
        "sources": sources,
        "quality": quality,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)

    today_rows = len(all_rows)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": refresh_status,
        "publishable": True,
        "rowsTotal": len(sorted_rows),
        "todayRows": today_rows,
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


def collectors_url(name: str) -> str:
    return {
        "gpuperhour": GPUPERHOUR_OFFERS_API,
        "vast": VAST_BUNDLES_API,
        "runpod": RUNPOD_GRAPHQL_API,
    }[name]


if __name__ == "__main__":
    raise SystemExit(main())
