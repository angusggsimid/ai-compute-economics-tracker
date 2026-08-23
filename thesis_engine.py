#!/usr/bin/env python3
"""JSON-native four-clock thesis state engine (E1+C1).

读取 tracker_data/backfills/*.json，独立评估四个时钟并产出状态报告：
- 状态机：Unobservable -> Observing -> Trend -> Inflection Watch -> Confirmed
- C1 双向化：每个时钟同时评估 loosening（松动）与 intensifying（紧缩）两套 Watch 条件
- 纪律：证据不足时保持低状态并在 blockers 说明，不用文案升级。

用法：python3 thesis_engine.py [--data-dir tracker_data/backfills] [--out-dir tracker_data/thesis_states]
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


STATES = ("Unobservable", "Observing", "Trend", "Inflection Watch", "Confirmed")
FRONTIER = ("H100", "H200", "B200")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _family_of(series: str) -> str:
    text = str(series or "").lower()
    for needle, family in (("h100", "H100"), ("h200", "H200"), ("b200", "B200"), ("a100", "A100")):
        if needle in text:
            return family
    return str(series)


def _parse_day(value: str) -> Optional[date]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _series_by_key(
    rows: List[Dict[str, Any]], value_field: str
) -> Dict[str, List[tuple[date, float]]]:
    out: Dict[str, List[tuple[date, float]]] = {}
    for row in rows or []:
        day = _parse_day(row.get("date") or "")
        value = row.get(value_field)
        if day is None or not isinstance(value, (int, float)) or value <= 0:
            continue
        out.setdefault(str(row.get("series")), []).append((day, float(value)))
    for series in out:
        out[series].sort()
    return out


def _change_pct_window(
    points: List[tuple[date, float]], days: int, *, tolerance: int = 10, min_points: int = 2
) -> Optional[float]:
    """最新值相对约 N 天前值的百分比变化；窗口内样本不足返回 None。"""
    if len(points) < min_points:
        return None
    latest_day, latest_value = points[-1]
    target_low = latest_day - timedelta(days=days + tolerance)
    target_high = latest_day - timedelta(days=max(1, days - tolerance))
    base = None
    for day, value in reversed(points):
        if target_low <= day <= target_high:
            base = (day, value)
            break
        if day < target_low:
            break
    if base is None or base[1] <= 0:
        return None
    return round((latest_value / base[1] - 1) * 100, 2)


def _panel_summary(
    series_map: Dict[str, List[tuple[date, float]]],
    source_prefix: str = "",
    frontier_only: bool = True,
) -> List[Dict[str, Any]]:
    panels = []
    for series, points in sorted(series_map.items()):
        if frontier_only and _family_of(series) not in FRONTIER:
            continue
        span_days = (points[-1][0] - points[0][0]).days + 1
        panels.append({
            "id": f"{source_prefix}:{series}" if source_prefix else series,
            "family": _family_of(series),
            "series": series,
            "validDays": len(points),
            "first": points[0][0].isoformat(),
            "last": points[-1][0].isoformat(),
            "spanDays": span_days,
            "chartReady": len(points) >= 10,
            "inflectionEligible": len(points) >= 20,
            "confirmed90dEligible": len(points) >= 60,
            "change30dPct": _change_pct_window(points, 30),
            "change90dPct": _change_pct_window(points, 90),
        })
    return panels


def _depth_metrics(orderbook_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    daily: Dict[date, int] = {}
    for row in orderbook_rows or []:
        day = _parse_day(row.get("date") or "")
        offers = row.get("offerCount")
        if day is None or not isinstance(offers, int):
            continue
        daily[day] = daily.get(day, 0) + offers
    dates = sorted(daily)
    metrics: Dict[str, Any] = {
        "depthValidDates": len(dates),
        "depthLatestTotalOffers": daily[dates[-1]] if dates else None,
    }
    if len(dates) >= 4:
        half = max(1, len(dates) // 2)
        early = statistics.mean(daily[d] for d in dates[:half])
        late = statistics.mean(daily[d] for d in dates[half:])
        if early > 0:
            metrics["depthGrowthPct"] = round((late / early - 1) * 100, 2)
    else:
        metrics["depthGrowthPct"] = None
    return metrics


def evaluate_supply(data: Dict[str, Any]) -> Dict[str, Any]:
    """Supply Price：报价层（Foundry）× 成交层（Ornn/SemiAnalysis）× 合约层 × 深度。"""
    composite = _series_by_key(
        (data.get("reference", {}).get("datasets", {}).get("semiComposite")) or [], "indexValue"
    )
    foundry = _series_by_key(
        (data.get("foundry", {}).get("datasets", {}).get("prices")) or [], "value"
    )
    ornn = _series_by_key(
        (data.get("reference", {}).get("datasets", {}).get("ornnOcpi")) or [], "indexValue"
    )

    composite_panels = _panel_summary(composite, "semi")
    ornn_panels = _panel_summary(ornn, "ornn")
    foundry_panels = _panel_summary(foundry, "foundry")
    all_panels = composite_panels + ornn_panels + foundry_panels

    depth = _depth_metrics(data.get("orderbook", {}).get("rows") or [])

    eligible_watch = [p for p in all_panels if p["inflectionEligible"] and p["change30dPct"] is not None]
    declining = sorted({p["family"] for p in eligible_watch if p["change30dPct"] <= -10})
    rising = sorted({p["family"] for p in eligible_watch if p["change30dPct"] >= 10})

    loosening_conditions = [
        {"condition": ">=2 个前沿 GPU 家族 30D 跌幅 >=10%（跨来源去重）", "met": len(declining) >= 2, "evidence": declining},
        {"condition": "订单簿深度增长 >=10%", "met": depth.get("depthGrowthPct") is not None and depth["depthGrowthPct"] >= 10, "evidence": []},
        {"condition": "深度序列 >=20 个有效日", "met": depth["depthValidDates"] >= 20, "evidence": []},
    ]
    intensifying_conditions = [
        {"condition": ">=2 个前沿 GPU 家族 30D 涨幅 >=10%（跨来源去重）", "met": len(rising) >= 2, "evidence": rising},
        {"condition": "订单簿深度收缩 >=10%", "met": depth.get("depthGrowthPct") is not None and depth["depthGrowthPct"] <= -10, "evidence": []},
        {"condition": "深度序列 >=20 个有效日", "met": depth["depthValidDates"] >= 20, "evidence": []},
    ]
    loosening_watch = all(c["met"] for c in loosening_conditions)
    intensifying_watch = all(c["met"] for c in intensifying_conditions)

    chart_ready = [p for p in all_panels if p["chartReady"]]
    confirmed90 = [p for p in all_panels if p["confirmed90dEligible"] and p["change90dPct"] is not None]
    loosening_confirmed = sorted({p["family"] for p in confirmed90 if p["change90dPct"] <= -15})
    intensifying_confirmed = sorted({p["family"] for p in confirmed90 if p["change90dPct"] >= 15})

    blockers: List[str] = []
    if not all_panels:
        state, direction = "Unobservable", None
    elif not chart_ready:
        state, direction = "Observing", None
        blockers.append("insufficient_panel_history")
    elif len(loosening_confirmed) >= 2:
        # 合同：Confirmed 需要方向与持续性（90D 资格且持续 ≥15% 同向）
        state, direction = "Confirmed", "loosening"
    elif len(intensifying_confirmed) >= 2:
        state, direction = "Confirmed", "intensifying"
    elif loosening_watch or intensifying_watch:
        state, direction = "Inflection Watch", ("loosening" if loosening_watch else "intensifying")
    else:
        state, direction = "Trend", None

    contract_rows = (data.get("reference", {}).get("datasets", {}).get("semiContract1y")) or []
    bands = []
    for row in contract_rows:
        if row.get("series") == "H100-1y" and row.get("lowValue") and row.get("highValue"):
            bands.append({
                "label": row.get("label"),
                "midpoint": round((row["lowValue"] + row["highValue"]) / 2, 3),
            })

    return {
        "clock_id": "supply_price",
        "title": "Supply Price",
        "natural_frequency": "daily",
        "state": state,
        "direction": direction,
        "basis": "固定来源价格面板（SemiAnalysis 综合指数/Ornn 成交指数/Foundry 中位价），横截面不连线。",
        "confirms": [
            "松动：≥2 前沿面板 30D 跌幅≥10% 且订单簿深度增长≥10%（≥20 有效日）",
            "紧缩：≥2 前沿面板 30D 涨幅≥10% 且订单簿深度收缩≥10%（≥20 有效日）",
        ],
        "disconfirms": ["变化孤立于单一 GPU 家族", "面板构成变更", "价格与深度方向矛盾"],
        "next_proof_point": f"订单簿深度已积累 {depth['depthValidDates']}/20 有效日；面板 30D 变化每日更新。",
        "watch": {
            "loosening": {"triggered": loosening_watch, "conditions": loosening_conditions},
            "intensifying": {"triggered": intensifying_watch, "conditions": intensifying_conditions},
        },
        "metrics": {
            "chartReadyPanels": len(chart_ready),
            "looseningConfirmedFamilies": loosening_confirmed,
            "intensifyingConfirmedFamilies": intensifying_confirmed,
            "frontierPanels": {
                p["id"]: {"days": p["validDays"], "change30dPct": p["change30dPct"], "change90dPct": p["change90dPct"]}
                for p in all_panels
            },
            "depth": depth,
            "h100Contract1yBands": bands[-6:],
        },
        "blockers": blockers,
        "sources": ["semianalysis_public", "ornn_ocpi", "foundry_signals", "gpu_orderbook"],
    }


def evaluate_capacity(data: Dict[str, Any]) -> Dict[str, Any]:
    """Capacity：订单簿 offer 数与 GPU 总量的扩张/收缩。"""
    rows = data.get("orderbook", {}).get("rows") or []
    depth = _depth_metrics(rows)
    gpu_daily: Dict[date, int] = {}
    for row in rows:
        day = _parse_day(row.get("date") or "")
        gpus = row.get("gpuCountTotal")
        if day is None or not isinstance(gpus, int):
            continue
        gpu_daily[day] = gpu_daily.get(day, 0) + gpus

    providers: Dict[str, int] = {}
    provider_rows = data.get("neocloud", {}).get("rows") or []
    for row in provider_rows:
        providers[str(row.get("provider"))] = providers.get(str(row.get("provider")), 0) + 1

    valid = depth["depthValidDates"]
    if valid == 0:
        state, blockers = "Unobservable", ["no_orderbook_history"]
    elif valid >= 10:
        state, blockers = "Trend", []
    else:
        state, blockers = "Observing", [f"insufficient_orderbook_history_{valid}_of_10"]

    growth = depth.get("depthGrowthPct")
    loosening = bool(growth is not None and growth >= 25 and valid >= 20)
    intensifying = bool(growth is not None and growth <= -25 and valid >= 20)

    return {
        "clock_id": "capacity",
        "title": "Capacity & Utilization",
        "natural_frequency": "daily",
        "state": state,
        "direction": None,
        "basis": "订单簿 offer 数与可租 GPU 总量；供应商覆盖为截面快照。",
        "confirms": [
            "松动：深度扩大 ≥25% 且 ≥20 有效日",
            "紧缩：深度收缩 ≥25% 且 ≥20 有效日",
        ],
        "disconfirms": ["单一来源驱动", "GPU 构成漂移"],
        "next_proof_point": f"积累订单簿至 10/20 有效日（当前 {valid}）。",
        "watch": {
            "loosening": {"triggered": loosening, "conditions": [{"condition": "深度扩大≥25% 且 ≥20 日", "met": loosening}]},
            "intensifying": {"triggered": intensifying, "conditions": [{"condition": "深度收缩≥25% 且 ≥20 日", "met": intensifying}]},
        },
        "metrics": {
            "depthValidDates": valid,
            "latestTotalOffers": depth.get("depthLatestTotalOffers"),
            "depthGrowthPct": growth,
            "latestGpuCapacity": gpu_daily[max(gpu_daily)] if gpu_daily else None,
            "providerSnapshotRows": len(provider_rows),
            "providersCovered": len(providers),
        },
        "blockers": blockers,
        "sources": ["gpu_orderbook", "neocloud_provider_prices"],
    }


def evaluate_demand(data: Dict[str, Any]) -> Dict[str, Any]:
    """Demand：OpenRouter 完整周用量 proxy + 牌价账本调价事件 + OTPI。"""
    cost_index = _load_cost_index(data)
    weeks = cost_index.get("weeks") or []
    complete_weeks = len(weeks)
    latest = weeks[-1] if weeks else {}
    first_of_last8 = weeks[-8] if len(weeks) >= 8 else {}
    output_change = None
    if latest and first_of_last8:
        base = first_of_last8.get("weighted_output_usd_per_1m")
        cur = latest.get("weighted_output_usd_per_1m")
        if base and cur:
            output_change = round((cur / base - 1) * 100, 2)

    cuts = _count_recent_price_cuts(data.get("active_prices", {}).get("data", {}))
    otpi_rows = (data.get("reference", {}).get("datasets", {}).get("ornnOtpi")) or []

    if complete_weeks == 0:
        state, blockers = "Unobservable", ["no_usage_series"]
    elif complete_weeks >= 52:
        state, blockers = "Trend", []
    else:
        state, blockers = "Observing", [f"incomplete_weeks_{complete_weeks}_of_52"]
    # 合同规定：公开 proxy 用量封顶 Trend；Inflection 需要非 proxy usage 序列。
    blockers.append("proxy_ceiling_requires_official_usage_for_inflection")

    return {
        "clock_id": "demand_unit_economics",
        "title": "Demand & Unit Economics",
        "natural_frequency": "weekly/event",
        "state": state,
        "direction": None,
        "basis": "OpenRouter 完整周公开 proxy（封顶 Trend）+ 活跃模型牌价账本真实调价点 + Ornn OTPI 已实现 token 价。",
        "confirms": [
            "Inflection：非 proxy usage 序列出现拐点 + 多个真实 token 降价",
            "Confirmed：两个官方 usage 序列且商业化持续改善",
        ],
        "disconfirms": ["降价未换来用量上升", "重复目录快照冒充连续曲线"],
        "next_proof_point": "获取官方 usage 授权或接入新的非 proxy 用量源；OTPI 继续按日累积。",
        "watch": {
            "loosening": {"triggered": False, "conditions": [{"condition": "受 proxy 天花板限制", "met": False}]},
            "intensifying": {"triggered": False, "conditions": [{"condition": "受 proxy 天花板限制", "met": False}]},
        },
        "metrics": {
            "completeWeeks": complete_weeks,
            "latestWeeklyTokens": latest.get("total_tokens"),
            "weightedOutputPriceChange8wPct": output_change,
            "recentPriceCutModels": cuts,
            "otpiLabsCovered": len({row.get("series") for row in otpi_rows}),
            "otpiLatestDate": max((row["date"] for row in otpi_rows), default=None),
        },
        "blockers": blockers,
        "sources": ["openrouter_cost_index", "openrouter_active_prices", "ornn_otpi"],
    }


def _load_cost_index(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = data.get("cost_index")
    if payload is not None:
        return payload
    return {}


def _count_recent_price_cuts(active_price_data: Dict[str, Any], window_days: int = 90) -> int:
    history = (active_price_data.get("history")) or {}
    cutoff = date.today() - timedelta(days=window_days)
    cut_models = set()
    for model_id, entry in history.items():
        points = entry.get("points") or []
        parsed = []
        for point in points:
            try:
                day = datetime.strptime(str(point[0])[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError, IndexError):
                continue
            if day >= cutoff and len(point) >= 3 and isinstance(point[1], (int, float)) and isinstance(point[2], (int, float)):
                parsed.append((day, float(point[1]), float(point[2])))
        # 按日期稳定排序（保持同日多点的原始时序，禁止按价格重排）
        parsed.sort(key=lambda item: item[0])
        for i in range(1, len(parsed)):
            # output 价下降记为一次真实降价
            if parsed[i][2] < parsed[i - 1][2]:
                cut_models.add(model_id)
                break
    return len(cut_models)


def evaluate_commitment(data: Dict[str, Any]) -> Dict[str, Any]:
    """Commitment：季度 CAPEX 轨迹 + H100 1Y 合约区间方向。"""
    rows = data.get("capex", {}).get("rows") or []
    by_company: Dict[str, List[date]] = {}
    for row in rows:
        company = row.get("company")
        metric = row.get("metric")
        day = _parse_day(row.get("date") or "")
        if not company or metric != "capex actual" or day is None:
            continue
        by_company.setdefault(company, []).append(day)

    qualified = 0
    for company, days in by_company.items():
        quarters = sorted({(d.year, (d.month - 1) // 3 + 1) for d in days})
        consecutive = 1
        best = 1
        for prev, cur in zip(quarters, quarters[1:]):
            expected = (prev[0], prev[1] + 1) if prev[1] < 4 else (prev[0] + 1, 1)
            if cur == expected:
                consecutive += 1
                best = max(best, consecutive)
            else:
                consecutive = 1
        if best >= 3:
            qualified += 1

    if not by_company:
        state, blockers = "Unobservable", ["no_capex_actuals"]
    elif qualified >= 3:
        state, blockers = "Trend", []
    else:
        state, blockers = "Observing", [f"companies_with_3_consecutive_quarters_{qualified}_of_3"]

    bands = []
    for row in (data.get("reference", {}).get("datasets", {}).get("semiContract1y")) or []:
        if row.get("series") == "H100-1y" and row.get("lowValue") and row.get("highValue"):
            bands.append((_parse_day(row.get("date") or ""), (row["lowValue"] + row["highValue"]) / 2))
    bands = sorted(b for b in bands if b[0])
    contract_direction = None
    if len(bands) >= 2:
        delta = bands[-1][1] - bands[0][1]
        contract_direction = "rising" if delta > 0 else ("falling" if delta < 0 else "flat")

    return {
        "clock_id": "commitment_monetization",
        "title": "Commitment & Monetization",
        "natural_frequency": "quarterly/event",
        "state": state,
        "direction": None,
        "basis": "SEC/官方季度 CAPEX actual（原生季度频率，不插值）+ SemiAnalysis H100 1Y 合约区间方向。",
        "confirms": [
            "Inflection：两家公司 guidance 下修（松动）",
            "Confirmed：两家公司后续 actual 同向验证",
        ],
        "disconfirms": ["单季度数据冒充趋势", "混入非 AI 支出口径"],
        "next_proof_point": "下一财报季追加季度行；合约区间每半年更新。",
        "watch": {
            "loosening": {"triggered": False, "conditions": [{"condition": "需要 guidance 下修事件接入", "met": False}]},
            "intensifying": {"triggered": False, "conditions": [{"condition": "需要 guidance 上修事件接入", "met": False}]},
        },
        "metrics": {
            "companiesCovered": len(by_company),
            "companiesWith3ConsecutiveQuarters": qualified,
            "h100ContractDirectionSinceStart": contract_direction,
            "h100ContractFirstMidpoint": round(bands[0][1], 3) if bands else None,
            "h100ContractLatestMidpoint": round(bands[-1][1], 3) if bands else None,
        },
        "blockers": blockers,
        "sources": ["sec_capex", "semianalysis_contract"],
    }


def evaluate_report(data_dir: Path) -> Dict[str, Any]:
    def opt(name: str) -> Dict[str, Any]:
        path = data_dir / name
        return _load(path) if path.exists() else {}

    data = {
        "cost_index": opt("openrouter_cost_index.json"),
        "foundry": opt("foundry_signals_gpu_history.json"),
        "active_prices": opt("openrouter_active_price_history.json"),
        "capex": opt("capex_official_history.json"),
        "orderbook": opt("gpu_orderbook_history.json"),
        "reference": opt("reference_index_history.json"),
        "neocloud": opt("neocloud_provider_price_history.json"),
    }
    clocks = [
        evaluate_supply(data),
        evaluate_capacity(data),
        evaluate_demand(data),
        evaluate_commitment(data),
    ]
    for clock in clocks:
        assert clock["state"] in STATES, clock["clock_id"]
    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "inputs": sorted(p.name for p in data_dir.glob("*.json")),
        "clocks": clocks,
        "methodology": {
            "states": list(STATES),
            "bidirectional": "每个时钟并行评估松动(loosening)与紧缩(intensifying)两套 Watch 条件。",
            "discipline": "证据不足保持低状态；proxy 用量封顶 Trend；季度数据不插值。",
        },
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Thesis State | {report['generatedAt']}",
        "",
        "| 时钟 | 状态 | 方向 | 关键读数 | 下一个证明点 |",
        "|---|---|---|---|---|",
    ]
    for clock in report["clocks"]:
        key = ""
        metrics = clock.get("metrics", {})
        if clock["clock_id"] == "supply_price":
            fp = metrics.get("frontierPanels", {})
            key = "; ".join(
                f"{s} 30D {v['change30dPct']}%" for s, v in sorted(fp.items()) if v.get("change30dPct") is not None
            ) or "30D 变化待积累"
        elif clock["clock_id"] == "capacity":
            key = f"订单簿 {metrics.get('depthValidDates')} 日 · 最新 offers {metrics.get('latestTotalOffers')}"
        elif clock["clock_id"] == "demand_unit_economics":
            key = f"{metrics.get('completeWeeks')} 完整周 · 近90日降价模型 {metrics.get('recentPriceCutModels')}"
        else:
            key = f"{metrics.get('companiesWith3ConsecutiveQuarters')}/{metrics.get('companiesCovered')} 家公司达3连续季度"
        direction = clock.get("direction") or "-"
        lines.append(f"| {clock['title']} | **{clock['state']}** | {direction} | {key} | {clock['next_proof_point']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("tracker_data/backfills"))
    parser.add_argument("--out-dir", type=Path, default=Path("tracker_data/thesis_states"))
    args = parser.parse_args()

    report = evaluate_report(args.data_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "latest-thesis-state.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "latest-thesis-state.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "output": str(args.out_dir / "latest-thesis-state.json"),
        "states": {c["clock_id"]: c["state"] for c in report["clocks"]},
        "publishable": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
