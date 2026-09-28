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


def _availability_series(availability: dict[str, Any]) -> list[dict[str, Any]]:
    """逐日 Σavailable/Σtotal。

    上游 /availability 返回的是 **7 天滚动窗口**——必须逐日全部落盘。
    只取最新一天的话，上游一滚过去这些日子就永久丢失了。
    """
    agg: dict[str, list[float]] = {}
    by_prov: dict[str, dict[str, list[int]]] = {}
    for provider in availability.get("providers") or []:
        name = str(provider.get("providerName") or provider.get("providerSlug") or "unknown")
        for count_block in provider.get("counts") or []:
            for cell in count_block.get("cells") or []:
                day, total, available = cell.get("date"), cell.get("total") or 0, cell.get("available") or 0
                if not day or not isinstance(total, (int, float)) or total <= 0:
                    continue
                slot = agg.setdefault(day, [0.0, 0.0])
                slot[0] += available
                slot[1] += total
                entry = by_prov.setdefault(day, {}).setdefault(name, [0, 0])
                entry[0] += available
                entry[1] += total
    out: list[dict[str, Any]] = []
    for day in sorted(agg):
        avail_sum, tot_sum = agg[day]
        if tot_sum <= 0:
            continue
        out.append({
            "date": day,
            "availabilityPct": round(100 * avail_sum / tot_sum, 2),
            "availabilityByProvider": by_prov[day],
        })
    return out


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
            series = _availability_series(_get(f"/availability?gpu={gpu.lower()}"))
            if series:
                latest = series[-1]
                row["availabilityPct"] = latest["availabilityPct"]
                row["availabilityDate"] = latest["date"]
                row["availabilityByProvider"] = latest["availabilityByProvider"]
                # 滚动窗口里的历史日一并落盘（只有可用率类字段，其余为 None）
                for hist in series[:-1]:
                    daily_rows.append({
                        "date": hist["date"],
                        "gpu": gpu,
                        "availabilityPct": hist["availabilityPct"],
                        "availabilityByProvider": hist["availabilityByProvider"],
                    })
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
        # 写入键是 "rows"；只读 "daily" 会让每天都把之前累积的行丢掉，
        # 累积永远停在 1 天（曾导致稀缺度/广度图长期卡在"已积累 1/10 天"）。
        return payload.get("rows") or payload.get("daily") or [], payload.get("monthlyHistory") or []
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
    # 按 (date, gpu) 去重：本期抓到的行字段更全，覆盖历史行。
    # 只按 date != today 过滤会让回补的历史日重复运行两次就产生重复行。
    _by_key: dict[tuple[Any, Any], dict[str, Any]] = {
        (r.get("date"), r.get("gpu")): r for r in prev_daily if r.get("date") and r.get("gpu")
    }
    for r in fresh_daily:
        _by_key[(r.get("date"), r.get("gpu"))] = r
    daily = list(_by_key.values())
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
