#!/usr/bin/env python3
"""GPU Finder (gpufinder.dev) 市场采集：价格广度 × 可用率 × 报价-在库价差。

免鉴权公开 API。为价格层提供第 6 个独立源，并解锁三类新指标：
1. 市场可用率 = Σavailable/Σtotal（稀缺度连续指标，替代 Foundry 的二元可用率）
2. 报价-在库价差 = cheapestAvailable / cheapestListed - 1（"报价虚低程度"）
3. 供应商/实例数广度（市场参与度）+ 月度历史回补

定位：非阻塞信息源。上游为 7 天滚动窗口，可用率历史从接入日起向前积累。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "gpufinder_market.json"
BASE = "https://gpufinder.dev/api/v1"
USER_AGENT = "AIComputeEconomicsTracker/1.0"
ATTRIBUTION = "Data by GPU Finder (gpufinder.dev), public read-only API; attribution required."
FRONTIER = ("H100", "H200", "B200")


_FETCH_LOG: dict[str, dict[str, Any]] = {}


def _get(path: str) -> dict[str, Any]:
    request = Request(f"{BASE}{path}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        body = response.read()
    payload = json.loads(body)
    if "data" not in payload:
        raise ValueError(f"gpufinder {path}: missing data")
    # 记录真实抓取 URL 与内容哈希，供展示层透传（可追溯性）
    entry = path.split("?")[0]
    slot = _FETCH_LOG.setdefault(entry, {"url": f"{BASE}{path}", "sha256": ""})
    slot["sha256"] = "sha256:" + hashlib.sha256(body).hexdigest()
    return payload["data"]


def _market_availability(availability: dict[str, Any]) -> tuple[float | None, dict[str, list[int]], str | None]:
    """Σavailable/Σtotal（取最新一日）与逐供应商聚合。"""
    latest_date: str | None = None
    totals: dict[str, list[int]] = {}
    for provider in availability.get("providers") or []:
        name = str(provider.get("providerName") or provider.get("providerSlug") or "unknown")
        for count_block in provider.get("counts") or []:
            for cell in count_block.get("cells") or []:
                day = cell.get("date")
                total = cell.get("total")
                if not day or not isinstance(total, (int, float)) or total <= 0:
                    continue
                if latest_date is None or day > latest_date:
                    latest_date = day
    if latest_date is None:
        return None, {}, None
    agg: dict[str, list[int]] = {}
    avail_sum = tot_sum = 0.0
    for provider in availability.get("providers") or []:
        name = str(provider.get("providerName") or provider.get("providerSlug") or "unknown")
        for count_block in provider.get("counts") or []:
            for cell in count_block.get("cells") or []:
                if cell.get("date") != latest_date:
                    continue
                total = cell.get("total") or 0
                available = cell.get("available") or 0
                if total <= 0:
                    continue
                tot_sum += total
                avail_sum += available
                entry = agg.setdefault(name, [0, 0])
                entry[0] += available
                entry[1] += total
    if tot_sum <= 0:
        return None, agg, latest_date
    return round(100 * avail_sum / tot_sum, 2), agg, latest_date


def collect(date_iso: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gpus_index = {str(g.get("canonical")): g for g in (_get("/gpus").get("gpus") or [])}
    daily_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    for gpu in FRONTIER:
        summary = gpus_index.get(gpu) or {}
        row: dict[str, Any] = {
            "date": date_iso,
            "gpu": gpu,
            "providerCount": summary.get("providerCount"),
            "instanceCount": summary.get("instanceCount"),
            "priceMin": summary.get("priceMin"),
            "priceMax": summary.get("priceMax"),
        }
        try:
            snapshot = _get(f"/snapshot?gpu={gpu.lower()}")
            listed = snapshot.get("cheapestListed") or {}
            available = snapshot.get("cheapestAvailable") or {}
            row["cheapestListedPrice"] = listed.get("perGpuHourlyPrice")
            row["cheapestListedProvider"] = listed.get("provider")
            row["cheapestAvailablePrice"] = available.get("perGpuHourlyPrice")
            row["cheapestAvailableProvider"] = available.get("provider")
            lp, ap = row["cheapestListedPrice"], row["cheapestAvailablePrice"]
            if isinstance(lp, (int, float)) and isinstance(ap, (int, float)) and lp > 0:
                row["listedAvailableGapPct"] = round((ap / lp - 1) * 100, 2)
        except Exception as exc:
            row["snapshotError"] = str(exc)[:150]
        try:
            pct, by_provider, day = _market_availability(_get(f"/availability?gpu={gpu.lower()}"))
            row["availabilityPct"] = pct
            row["availabilityDate"] = day
            row["availabilityByProvider"] = by_provider
        except Exception as exc:
            row["availabilityError"] = str(exc)[:150]
        daily_rows.append(row)

        try:
            history = _get(f"/history?gpu={gpu.lower()}").get("history") or []
            for item in history:
                monthly_rows.append({
                    "month": item.get("month"),
                    "gpu": gpu,
                    "provider": item.get("provider"),
                    "onDemandPrice": item.get("onDemandPrice"),
                    "spotPrice": item.get("spotPrice"),
                })
        except Exception as exc:
            row["historyError"] = str(exc)[:150]

    if not any(r.get("availabilityPct") is not None or r.get("cheapestListedPrice") is not None for r in daily_rows):
        raise ValueError("gpufinder 全部端点失败")
    return sorted(daily_rows, key=lambda r: r["gpu"]), sorted(monthly_rows, key=lambda r: (r["gpu"], r["month"], str(r.get("provider"))))


def _load_previous(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.exists():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("daily") or [], payload.get("monthlyHistory") or []
    except (json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"gpufinder_market.json 缓存损坏（{exc}）；拒绝覆盖累积历史。")


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    date_iso = fetched_at[:10]
    quality: list[dict[str, str]] = []
    try:
        fresh_daily, fresh_monthly = collect(date_iso)
        status = "fresh"
    except Exception as exc:
        fresh_daily, fresh_monthly = [], []
        status = "failed"
        quality.append({"source": "gpufinder", "status": "failed", "message": str(exc)})

    prev_daily, prev_monthly = _load_previous(OUTPUT_PATH)
    daily = [r for r in prev_daily if r.get("date") != date_iso] + fresh_daily
    monthly_map = {(r["month"], r["gpu"], str(r.get("provider"))): r for r in prev_monthly}
    for r in fresh_monthly:
        monthly_map[(r["month"], r["gpu"], str(r.get("provider")))] = r
    monthly = sorted(monthly_map.values(), key=lambda r: (r["gpu"], r["month"], str(r.get("provider"))))

    payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": status,
        "publishable": True,
        "attribution": ATTRIBUTION,
        "sources": dict(sorted(_FETCH_LOG.items())),
        "rows": sorted(daily, key=lambda r: (r["date"], r["gpu"])),
        "monthlyHistory": monthly,
        "quality": quality,
        "blocking": False,
        "notes": [
            "availabilityPct = Σavailable/Σtotal（最新一日，7 天滚动窗口，向前积累）。",
            "listedAvailableGapPct = cheapestAvailable/cheapestListed - 1，衡量报价虚低程度。",
        ],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)

    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": status,
        "publishable": True,
        "todayRows": len(fresh_daily),
        "monthlyRows": len(monthly),
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
