#!/usr/bin/env python3
"""GPU Finder (gpufinder.dev) 市场采集：价格广度 × 可用率 × 报价-在库价差。

上游 2026-10-09 起要求 Bearer API Key（免费额度 60 次/月）。为守住额度，采集按**轨道**到期触发：
- availability（≤6 天一轮）：/availability 每次返回 **7 天滚动窗口的逐日 cells**，
  低频轮询即可保证"市场稀缺度/广度"日序列零丢失——单次跨度大，正是不缺额度的取数方式；
- snapshot（~2.5 天一轮）：/snapshot 只有"当下"，没有历史可回补，密度=采集频率（额度内最优）；
- history（~28 天）、catalog（~30 天）：月度/目录数据，低频即可。
未到期日零请求跳过；`GPUFINDER_API_KEY` 未配置时匿名请求并如实降级。
手动验证：本地 `--force`/`--dry-run`，云端 workflow_dispatch 的 force_gpufinder 输入。

为价格层提供第 6 个独立源：
1. 市场可用率 = Σavailable/Σtotal（稀缺度连续指标，替代 Foundry 的二元可用率）
2. 报价-在库价差 = cheapestAvailable / cheapestListed - 1（"报价虚低程度"）
3. 供应商/实例数广度（市场参与度）+ 月度历史回补

定位：非阻塞信息源。上游为 7 天滚动窗口，可用率历史从接入日起向前积累。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
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
# 免费额度 60 次/月。每轮成本：availability/snapshot/history 各 3 次（3 个 GPU），catalog 1 次。
# 预算：availability 5 轮×3=15 + snapshot 10 轮×3=30 + history 3 + catalog 1 ≈ 49 次/月，其余为重试余量。
TRACK_DUE_DAYS = {
    "availability": 6.0,   # 7 天滚动窗口：≤6 天一轮逐日零丢失（窗口每少采一天就永久缺一天）
    "snapshot": 2.5,       # 无历史可回补：密度=频率，额度内最优节奏
    "history": 28.0,       # 月度地板价
    "catalog": 30.0,       # 目录字段（providerCount/价格区间等）
}


def _sweep_due(last_success_at: str | None, now: datetime, interval_days: float = 6.0) -> bool:
    """到期制：距上次成功抓取达到间隔才允许再扫；从未成功过则视为到期。"""
    if not last_success_at:
        return True
    try:
        last = datetime.fromisoformat(str(last_success_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last).total_seconds() >= interval_days * 86400


def _due_tracks(cadence: dict[str, Any], now: datetime, force: bool = False) -> list[str]:
    """返回本轮到期、需要抓取的轨道。"""
    if force:
        return list(TRACK_DUE_DAYS)
    return [t for t, days in TRACK_DUE_DAYS.items() if _sweep_due((cadence or {}).get(t), now, days)]


_FETCH_LOG: dict[str, dict[str, Any]] = {}


def _get(path: str) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    api_key = os.environ.get("GPUFINDER_API_KEY", "").strip()
    if api_key:
        # 密钥只进请求头，绝不落入 URL/日志
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{BASE}{path}", headers=headers)
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


def collect(date_iso: str, tracks: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], dict[str, bool]]:
    """按到期轨道抓取，返回 (daily_rows, monthly_rows, errors, ok_by_track)。"""
    ok: dict[str, bool] = {t: True for t in tracks}
    errors: list[dict[str, str]] = []
    daily_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    gpus_index: dict[str, dict[str, Any]] = {}
    if "catalog" in tracks:
        try:
            gpus_index = {str(g.get("canonical")): g for g in (_get("/gpus").get("gpus") or [])}
        except Exception as exc:
            ok["catalog"] = False
            errors.append({"source": "gpufinder:/gpus", "status": "failed", "message": str(exc)[:200]})

    for gpu in FRONTIER:
        summary = gpus_index.get(gpu) or {}
        row: dict[str, Any] = {"date": date_iso, "gpu": gpu}
        if summary:
            row.update({
                "providerCount": summary.get("providerCount"),
                "instanceCount": summary.get("instanceCount"),
                "priceMin": summary.get("priceMin"),
                "priceMax": summary.get("priceMax"),
            })
        if "snapshot" in tracks:
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
                ok["snapshot"] = False
                row["snapshotError"] = str(exc)[:150]
                errors.append({"source": f"gpufinder:/snapshot?gpu={gpu.lower()}", "status": "failed", "message": str(exc)[:200]})
        if "availability" in tracks:
            try:
                series = _availability_series(_get(f"/availability?gpu={gpu.lower()}"))
                if series:
                    latest = series[-1]
                    row["availabilityPct"] = latest["availabilityPct"]
                    row["availabilityDate"] = latest["date"]
                    row["availabilityByProvider"] = latest["availabilityByProvider"]
                    # 滚动窗口里的历史日一并落盘（只有可用率类字段）
                    for hist in series[:-1]:
                        daily_rows.append({
                            "date": hist["date"],
                            "gpu": gpu,
                            "availabilityPct": hist["availabilityPct"],
                            "availabilityByProvider": hist["availabilityByProvider"],
                        })
            except Exception as exc:
                ok["availability"] = False
                row["availabilityError"] = str(exc)[:150]
                errors.append({"source": f"gpufinder:/availability?gpu={gpu.lower()}", "status": "failed", "message": str(exc)[:200]})
        if "history" in tracks:
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
                ok["history"] = False
                errors.append({"source": f"gpufinder:/history?gpu={gpu.lower()}", "status": "failed", "message": str(exc)[:200]})
        daily_rows.append(row)

    return (
        sorted(daily_rows, key=lambda r: r["gpu"]),
        sorted(monthly_rows, key=lambda r: (r["gpu"], r["month"], str(r.get("provider")))),
        errors,
        ok,
    )


def _merge_daily(prev_daily: list[dict[str, Any]], fresh_daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (date, gpu) 做**字段级**合并：本期抓到的字段覆盖同键历史，未抓到的字段原样保留。

    滚动窗口回写的历史行只带可用率字段；整行覆盖会把该日此前抓到的价格/家数字段
    （快照只在当天能取到、无法回补）整日抹掉——历史上 gap/广度因此每天只剩最后一个点
    （每个提交里都只有 1 天有值，2026-10-11 复盘确认）。字段级合并根治该静默丢失。
    """
    by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    for r in prev_daily:
        key = (r.get("date"), r.get("gpu"))
        if key[0] and key[1]:
            by_key[key] = dict(r)
    for r in fresh_daily:
        key = (r.get("date"), r.get("gpu"))
        if not key[0] or not key[1]:
            continue
        merged = dict(by_key.get(key) or {})
        for field, value in r.items():
            # 显式 None 也要覆盖："今日无在库报价"是事实，不能沿用旧价
            merged[field] = value
        if "cheapestListedPrice" in r:
            # 本轮快照成功拍摄：价格组以本轮为准，清掉旧错误与已不可计算的价差
            merged.pop("snapshotError", None)
            if "listedAvailableGapPct" not in r:
                merged.pop("listedAvailableGapPct", None)
        by_key[key] = merged
    return list(by_key.values())


def _merge_sources(prev_sources: dict[str, Any], fresh_sources: dict[str, Any], prev_fetched_at: str | None) -> dict[str, Any]:
    """来源元数据按端点合并：本期抓到的覆盖同键历史。

    断供时（本期全失败）必须沿用上一次成功抓取的 URL/sha——面板仍展示累积数据，
    来源链接不能因此消失（发布门会按"来源缺真实 URL"拦截）。carriedFrom 记录该条目
    实际来自哪一轮抓取，避免把历史抓取误读成本轮成功。
    """
    merged: dict[str, Any] = {}
    for key, entry in (prev_sources or {}).items():
        if not isinstance(entry, dict):
            continue
        carried = dict(entry)
        if prev_fetched_at and "carriedFrom" not in carried:
            carried["carriedFrom"] = prev_fetched_at
        merged[key] = carried
    for key, entry in (fresh_sources or {}).items():
        merged[key] = entry
    return merged


def _load_previous(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], [], {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        # 写入键是 "rows"；只读 "daily" 会让每天都把之前累积的行丢掉，
        # 累积永远停在 1 天（曾导致稀缺度/广度图长期卡在"已积累 1/10 天"）。
        meta = {
            "sources": payload.get("sources") or {},
            "fetchedAt": payload.get("fetchedAt"),
            # 旧格式没有 lastSuccessAt：仅当上一轮确实成功时退回 fetchedAt 作为最后成功时间
            "lastSuccessAt": payload.get("lastSuccessAt")
            or (payload.get("fetchedAt") if payload.get("refreshStatus") == "fresh" else None),
            "cadence": payload.get("cadence") or {},
        }
        return payload.get("rows") or payload.get("daily") or [], payload.get("monthlyHistory") or [], meta
    except (json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"gpufinder_market.json 缓存损坏（{exc}）；拒绝覆盖累积历史。")


def main() -> int:
    now = datetime.now(timezone.utc)
    fetched_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    date_iso = fetched_at[:10]
    prev_daily, prev_monthly, prev_meta = _load_previous(OUTPUT_PATH)

    cadence: dict[str, str] = dict(prev_meta.get("cadence") or {})
    if not cadence and prev_meta.get("lastSuccessAt"):
        # 旧格式迁移：上一轮是完整成功扫（含全部轨道），以其时间为各轨道基准
        cadence = {t: prev_meta["lastSuccessAt"] for t in TRACK_DUE_DAYS}

    # 手动验证：本地 --force，或云端 workflow_dispatch 的 force_gpufinder 输入
    force_requested = "--force" in sys.argv[1:] or os.environ.get("GPUFINDER_FORCE", "").strip().lower() in ("1", "true", "yes")
    due = _due_tracks(cadence, now, force=force_requested)

    if "--dry-run" in sys.argv[1:]:
        print(json.dumps({"dryRun": True, "dueTracks": due, "cadence": cadence}, ensure_ascii=False))
        return 0

    if not due:
        # 未到采集窗口：不发请求、不动文件（守住免费额度）
        print(json.dumps({
            "output": str(OUTPUT_PATH),
            "refreshStatus": "current_for_frequency",
            "publishable": True,
            "skipped": "tracks-not-due",
            "cadence": cadence,
            "blocking": False,
        }, ensure_ascii=False))
        return 0

    tracks = set(due)
    try:
        fresh_daily, fresh_monthly, errors, ok = collect(date_iso, tracks)
    except Exception as exc:
        fresh_daily, fresh_monthly = [], []
        errors = [{"source": "gpufinder", "status": "failed", "message": str(exc)[:200]}]
        ok = {t: False for t in tracks}
    failed_tracks = sorted(t for t, v in ok.items() if not v)
    status = "fresh" if not failed_tracks else ("failed" if len(failed_tracks) == len(ok) else "partial")
    quality: list[dict[str, str]] = list(errors)

    daily = _merge_daily(prev_daily, fresh_daily)
    monthly_map = {(r["month"], r["gpu"], str(r.get("provider"))): r for r in prev_monthly}
    for r in fresh_monthly:
        monthly_map[(r["month"], r["gpu"], str(r.get("provider")))] = r
    monthly = sorted(monthly_map.values(), key=lambda r: (r["gpu"], r["month"], str(r.get("provider"))))

    for t in tracks:
        if ok.get(t):
            cadence[t] = fetched_at

    # 断供时沿用上一次成功的时间与来源元数据（面板仍展示累积数据，URL/sha 不能丢）
    last_success_at = fetched_at if status in ("fresh", "partial") else (prev_meta.get("lastSuccessAt") or prev_meta.get("fetchedAt"))
    sources = _merge_sources(prev_meta.get("sources") or {}, _FETCH_LOG, prev_meta.get("fetchedAt"))

    payload = {
        "fetchedAt": fetched_at,
        "lastSuccessAt": last_success_at,
        "refreshStatus": status,
        "publishable": True,
        "attribution": ATTRIBUTION,
        "sources": dict(sorted(sources.items())),
        "cadence": dict(sorted(cadence.items())),
        "rows": sorted(daily, key=lambda r: (r["date"], r["gpu"])),
        "monthlyHistory": monthly,
        "quality": quality,
        "blocking": False,
        "notes": [
            "availabilityPct = Σavailable/Σtotal（最新一日，7 天滚动窗口，向前积累）。",
            "listedAvailableGapPct = cheapestAvailable/cheapestListed - 1，衡量报价虚低程度。",
            "轨道化到期采集（免费额度 60 次/月）：availability ≤6 天一轮（7 天窗口→逐日零丢失）、snapshot ~2.5 天、history ~28 天、catalog ~30 天；未到期日零请求跳过。",
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
        "fetchedTracks": sorted(tracks),
        "failedTracks": failed_tracks,
        "monthlyRows": len(monthly),
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
