#!/usr/bin/env python3
"""GrabGPU (grabgpu.com) 市场库存采集：provider 在库率 × 报价-在库价差 × 供应商广度。

背景（2026-11-21）：GPU Finder 免费档只有 60 次/月，而原轨道预算约 55 次/月，
任何一次重试就整月 429——2026-11-08 起 `snapshot` 全灭，`listed_gap` 序列一个点都没有。
GrabGPU 的 `/api/offers.json` **一次请求**返回全市场（29 家 / 73 型号 / 约 296 条报价），
每小时刷新，且每条报价自带 provider 上报的在库状态，因此以它为主源、GPU Finder 降频保底。

口径（与 GPU Finder 的差异必须显式记录，不允许拼成同一条线）：
- `availabilityPct`：**有报价的 provider 中报告有库存的占比**（分母只算状态已知的 provider）。
  GPU Finder 是「实例数加权 Σavailable/Σtotal」——分母（总容量）本就无人公开，
  故新口径不叫同一指标，页面图注与 source definition 都要写明切换日。
- `listedAvailableGapPct`：`最低在库价 ÷ 最低报价 − 1`，与 GPU Finder 公式完全一致，可直接接续。
- `breadthProviders`：报告在库库存的 provider 家数（与 breadth 面板文案一致）。
- `monthlyHistory`：本脚本不生产；月度价格走自有 neocloud 日度底表聚合。

非阻塞信息源：失败保留上次成功数据并如实写 `refreshStatus=failed`。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "gpu_market_stock.json"
OFFERS_API = "https://grabgpu.com/api/offers.json"
USER_AGENT = "AIComputeEconomicsTracker/1.0"
ATTRIBUTION = "Data by GrabGPU (grabgpu.com), indexed from public provider APIs; attribution + link required."
LICENSE_NOTE = "GrabGPU 公开索引：引用需署名并链接 grabgpu.com；生产级嵌入/转售需与其另行约定。"

# 只取与页面一致的三张主力卡；grabgpu 的 slug 是稳定的 kebab-case。
MODELS = {"nvidia-h100": "H100", "nvidia-h200": "H200", "nvidia-b200": "B200"}
KNOWN_STATES = ("in_stock", "out_of_stock")
ROW_FIELDS = (
    "date",
    "gpu",
    "capturedAt",
    "providers",
    "providersInStock",
    "providersKnown",
    "providersOutOfStock",
    "availabilityPct",
    "breadthProviders",
    "cheapestListed",
    "cheapestInStock",
    "listedAvailableGapPct",
    "availabilityByProvider",
)


def _fetch_offers() -> tuple[dict[str, Any], str, str]:
    """返回 (payload, sha256, captured_at)。密钥只进请求头，绝不落进 URL/日志。"""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    api_key = os.environ.get("GRABGPU_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    request = Request(OFFERS_API, headers=headers)
    with urlopen(request, timeout=30) as response:
        body = response.read()
    payload = json.loads(body)
    offers = payload.get("offers")
    if not isinstance(offers, list) or not offers:
        raise ValueError("grabgpu offers.json: empty or missing offers")
    return payload, "sha256:" + hashlib.sha256(body).hexdigest(), str(payload.get("captured_at") or "")


def _model_metrics(offers: list[dict[str, Any]]) -> dict[str, Any]:
    """把同一型号的全部报价折成 provider 口径的库存与价差。

    同一 provider 可能有多条报价（不同套餐/代际）：库存按 provider 去重（任一在库即算在库），
    价格分别取公司级最低挂牌与最低在库挂牌——与 GrabGPU 自己的 `cheapest` /
    `cheapest_in_stock` 字段一致（2026-11-20 实测逐项对齐）。
    """
    in_stock: set[str] = set()
    known: set[str] = set()
    prices: list[float] = []
    in_stock_prices: list[float] = []
    by_provider: dict[str, list[int]] = {}
    for offer in offers:
        provider = str(offer.get("provider") or "").strip()
        state = str(offer.get("availability") or "").strip()
        if not provider:
            continue
        price = offer.get("usd_per_gpu_hour")
        if isinstance(price, (int, float)) and price > 0:
            prices.append(float(price))
            if state == "in_stock":
                in_stock_prices.append(float(price))
        if state not in KNOWN_STATES:
            continue
        known.add(provider)
        slot = by_provider.setdefault(provider, [0, 0])
        slot[1] = 1
        if state == "in_stock":
            in_stock.add(provider)
            slot[0] = 1
    providers = {str(o.get("provider") or "").strip() for o in offers} - {""}
    cheapest_listed = round(min(prices), 4) if prices else None
    cheapest_in_stock = round(min(in_stock_prices), 4) if in_stock_prices else None
    gap = None
    if cheapest_listed and cheapest_in_stock:
        gap = round((cheapest_in_stock / cheapest_listed - 1) * 100, 2)
    availability = None
    if known:
        availability = round(100 * len(in_stock) / len(known), 2)
    return {
        "providers": len(providers),
        "providersInStock": len(in_stock),
        "providersKnown": len(known),
        "providersOutOfStock": len(known) - len(in_stock),
        "availabilityPct": availability,
        "breadthProviders": len(in_stock) or None,
        "cheapestListed": cheapest_listed,
        "cheapestInStock": cheapest_in_stock,
        "listedAvailableGapPct": gap,
        "availabilityByProvider": {p: v for p, v in sorted(by_provider.items())},
    }


def build_rows(payload: dict[str, Any], captured_at: str) -> tuple[list[dict[str, Any]], list[str]]:
    """把一次 offers 快照折成 (date, gpu) 行。返回 (rows, 质量事件)。"""
    offers = payload.get("offers") or []
    stamp = captured_at or datetime.now(timezone.utc).isoformat()
    try:
        day = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        day = datetime.now(timezone.utc).date().isoformat()
    quality: list[str] = []
    rows: list[dict[str, Any]] = []
    for slug, card in MODELS.items():
        subset = [o for o in offers if str(o.get("gpu") or "") == slug]
        if not subset:
            quality.append(f"grabgpu: 型号缺失 {slug}")
            continue
        metrics = _model_metrics(subset)
        if metrics["providersKnown"] == 0:
            quality.append(f"grabgpu: {card} 无 provider 报告库存状态")
        rows.append(
            {
                "date": day,
                "gpu": card,
                "capturedAt": stamp,
                **{k: metrics[k] for k in ROW_FIELDS if k in metrics and k not in ("date", "gpu", "capturedAt")},
            }
        )
    return rows, quality


def _load_previous() -> dict[str, Any]:
    if not OUTPUT_PATH.exists():
        return {}
    try:
        return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def merge_rows(previous: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按时点覆盖同 (date, gpu)，其余历史原样保留——每日累积，不插值。"""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in previous:
        if row.get("date") and row.get("gpu"):
            merged[(str(row["date"]), str(row["gpu"]))] = row
    for row in fresh:
        merged[(row["date"], row["gpu"])] = row
    return [merged[key] for key in sorted(merged)]


def _write(payload: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    previous = _load_previous()
    prior_rows = [r for r in previous.get("rows") or [] if isinstance(r, dict)]

    try:
        raw, sha, captured_at = _fetch_offers()
    except Exception as exc:  # noqa: BLE001 - 任何抓取失败都要如实降级
        payload = {
            **{k: v for k, v in previous.items() if k not in ("fetchedAt", "refreshStatus", "sources")},
            "fetchedAt": now,
            "refreshStatus": "failed",
            "publishable": bool(prior_rows),
            "blocking": False,
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "rows": prior_rows,
        }
        if prior_rows:
            _write(payload)
        print(json.dumps({
            "output": str(OUTPUT_PATH),
            "refreshStatus": "failed",
            "publishable": bool(prior_rows),
            "rowsTotal": len(prior_rows),
            "failedSources": [{"source": OFFERS_API, "status": "failed", "message": payload["error"]}],
            "blocking": False,
        }, ensure_ascii=False))
        return 1

    fresh_rows, quality = build_rows(raw, captured_at)
    rows = merge_rows(prior_rows, fresh_rows)
    total_offers = len(raw.get("offers") or [])
    payload = {
        "fetchedAt": now,
        "lastSuccessAt": now,
        "refreshStatus": "fresh" if fresh_rows else "failed",
        "publishable": bool(rows),
        "blocking": False,
        "attribution": ATTRIBUTION,
        "licenseNote": LICENSE_NOTE,
        "sourceUrl": OFFERS_API,
        "sourceSha256": sha,
        "capturedAt": captured_at,
        "rowSchema": list(ROW_FIELDS),
        "definition": {
            "availabilityPct": "有报价的 provider 中，报告有库存的占比（分母只算状态已知的 provider）。2026-11-21 起替代 GPU Finder 的实例数加权口径。",
            "listedAvailableGapPct": "最低在库价 ÷ 最低挂牌价 − 1，衡量报价虚低程度；与 GPU Finder 同名指标公式一致。",
            "breadthProviders": "报告在库库存的 provider 家数（同一 provider 多条报价只算一次）。",
            "dedup": "库存按 provider 去重（任一报价在库即算在库）；价格取 provider 级最低挂牌与最低在库挂牌。",
            "unknown": "availability=unknown 的报价不计入分母，但仍参与最低挂牌价。",
        },
        "coverage": {
            "providers": len({str(o.get("provider") or "") for o in raw.get("offers") or []} - {""}),
            "models": len({str(o.get("gpu") or "") for o in raw.get("offers") or []} - {""}),
            "offers": total_offers,
        },
        "rows": rows,
        "quality": quality,
    }
    _write(payload)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": payload["refreshStatus"],
        "publishable": payload["publishable"],
        "capturedAt": captured_at,
        "rowsTotal": len(rows),
        "todayRows": len(fresh_rows),
        "offers": total_offers,
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
