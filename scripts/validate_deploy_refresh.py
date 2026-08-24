#!/usr/bin/env python3
"""验证静态发布状态是否满足自动部署门槛。"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "tracker_data" / "deploy_refresh_status.json"
EXPECTED_SOURCES = {
    "openrouter_usage",
    "foundry_signals",
    "openrouter_active_prices",
    "sec_capex",
    "gpu_orderbook",
    "reference_indices",
    "neocloud_provider_prices",
    "epoch_supply",
}
CAPEX_READY_STATUSES = {"fresh", "current_for_frequency"}
INFORMATIONAL_SOURCES = {"gpu_orderbook", "reference_indices", "neocloud_provider_prices", "epoch_supply"}
INFORMATIONAL_STATUSES = {"fresh", "partial", "failed"}


def validate(payload: dict, expected_date: date) -> list[str]:
    errors: list[str] = []
    try:
        generated_at = datetime.fromisoformat(str(payload["generatedAt"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        errors.append("generatedAt 无效")
    else:
        if generated_at.astimezone(timezone.utc).date() != expected_date:
            errors.append(f"generatedAt 不是 {expected_date.isoformat()}")

    if payload.get("status") != "ready" or payload.get("publishable") is not True:
        errors.append("发布状态不是 ready/publishable")

    sources = {row.get("source"): row for row in payload.get("sources") or []}
    if set(sources) != EXPECTED_SOURCES:
        errors.append("来源集合不完整")
        return errors

    for name in EXPECTED_SOURCES - {"sec_capex"} - INFORMATIONAL_SOURCES:
        row = sources[name]
        if row.get("status") != "fresh" or row.get("publishable") is not True:
            errors.append(f"{name} 不是 fresh")

    for name in sorted(INFORMATIONAL_SOURCES):
        status = sources[name].get("status")
        if status not in INFORMATIONAL_STATUSES:
            errors.append(f"{name} 状态未知（应为 fresh/partial/failed 之一）")
        elif status == "failed":
            print(
                json.dumps(
                    {"warning": f"{name} 全部来源失败，今日为缺口（不阻塞发布）"},
                    ensure_ascii=False,
                )
            )

    capex = sources["sec_capex"]
    if capex.get("status") not in CAPEX_READY_STATUSES or capex.get("publishable") is not True:
        errors.append("sec_capex 不满足季度频率发布门槛")
    if capex.get("status") == "current_for_frequency":
        coverage = capex.get("cacheCoverage") or {}
        if not coverage or not all(item.get("current") is True for item in coverage.values()):
            errors.append("sec_capex 缓存覆盖不完整或已过期")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    payload = json.loads(args.status.read_text(encoding="utf-8"))
    errors = validate(payload, args.date)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "generatedAt": payload["generatedAt"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
