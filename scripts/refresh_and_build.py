#!/usr/bin/env python3
"""Refresh public sources, preserve last-known-good data, and build the deployable site."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "tracker_data" / "deploy_refresh_status.json"
PUBLIC_INDEX = ROOT / "public" / "index.html"


def _structured_stdout(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _run(name: str, command: list[str], required_output: Path) -> dict:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    details = _structured_stdout(completed.stdout)
    publishable = bool(details.get("publishable", completed.returncode == 0))
    status = {
        "source": name,
        "status": details.get(
            "refreshStatus",
            "fresh" if completed.returncode == 0 else "failed_using_last_good",
        ),
        "publishable": publishable,
        "returnCode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
        "output": str(required_output.relative_to(ROOT)),
    }
    if "failedSources" in details:
        status["qualityWarnings"] = details["failedSources"]
    if "cacheCoverage" in details:
        status["cacheCoverage"] = details["cacheCoverage"]
    for key in ("staleDays", "lastDataDate", "error"):
        if key in details:
            status[key] = details[key]
    if completed.returncode and not required_output.exists():
        raise RuntimeError(f"{name} failed and has no last-known-good output: {completed.stderr}")
    return status


def main() -> int:
    python = sys.executable
    # 统一 UTC：本地时区在 00:00–08:00 会比 UTC 早一天，370 天窗口可能只剩 51 个完整周
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=370)).isoformat()
    jobs = [
        (
            "openrouter_usage",
            [python, "scripts/backfill_openrouter_cost_index.py", "--start-date", start_date, "--reuse-commits"],
            ROOT / "tracker_data" / "backfills" / "openrouter_cost_index.json",
        ),
        (
            "foundry_signals",
            [python, "scripts/backfill_foundry_signals.py"],
            ROOT / "tracker_data" / "backfills" / "foundry_signals_gpu_history.json",
        ),
        (
            "openrouter_active_prices",
            [python, "scripts/backfill_openrouter_active_prices.py"],
            ROOT / "tracker_data" / "backfills" / "openrouter_active_price_history.json",
        ),
        (
            "sec_capex",
            [python, "scripts/refresh_capex_history.py"],
            ROOT / "tracker_data" / "backfills" / "capex_official_history.json",
        ),
        (
            "gpu_orderbook",
            [python, "scripts/backfill_gpu_orderbook.py"],
            ROOT / "tracker_data" / "backfills" / "gpu_orderbook_history.json",
        ),
        (
            "reference_indices",
            [python, "scripts/backfill_reference_indices.py"],
            ROOT / "tracker_data" / "backfills" / "reference_index_history.json",
        ),
        (
            "neocloud_provider_prices",
            [python, "scripts/backfill_neocloud_prices.py"],
            ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json",
        ),
        (
            "epoch_supply",
            [python, "scripts/backfill_epoch_supply.py"],
            ROOT / "tracker_data" / "backfills" / "epoch_chip_sales.json",
        ),
        (
            "fred_cost_anchors",
            [python, "scripts/backfill_fred_cost_anchors.py"],
            ROOT / "tracker_data" / "backfills" / "fred_cost_anchors.json",
        ),
        (
            "gpu_markets_fixings",
            [python, "scripts/backfill_gpu_markets_fixings.py"],
            ROOT / "tracker_data" / "backfills" / "gpu_markets_fixings.json",
        ),
        (
            "throughput_benchmarks",
            [python, "scripts/backfill_throughput_benchmarks.py"],
            ROOT / "tracker_data" / "backfills" / "throughput_benchmarks.json",
        ),
        (
            "gpufinder_market",
            [python, "scripts/backfill_gpufinder.py"],
            ROOT / "tracker_data" / "backfills" / "gpufinder_market.json",
        ),
    ]
    results = [_run(*job) for job in jobs]
    INFORMATIONAL_SOURCES = {"gpu_orderbook", "reference_indices", "epoch_supply", "fred_cost_anchors", "gpu_markets_fixings", "throughput_benchmarks", "gpufinder_market", "foundry_signals"}
    for row in results:
        if row["source"] in INFORMATIONAL_SOURCES:
            # 积累型信息源（时点观测/外部滚动窗口）：失败必须暴露在状态里，
            # 但当前不阻塞主链路发布；未来接入页面展示或时钟门槛时再升级。
            row["blocking"] = False
            row["publishable"] = True
    publishable = all(row["publishable"] for row in results)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "generatedAt": generated_at,
        "status": "ready" if publishable else "degraded",
        "publishable": publishable,
        "sources": results,
        "publicIndex": str(PUBLIC_INDEX.relative_to(ROOT)),
    }
    # 状态文件必须在构建【之前】落盘：页面顶部的新鲜度徽章由构建时读取该文件生成，
    # 先构建后写会让徽章永远显示上一轮的时间戳（数据是新的、标称时间是旧的）。
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if publishable:
        # 四时钟判断层：读取已通过数据门的 JSON 底表，产出状态报告（阻塞步骤）。
        thesis = subprocess.run(
            [python, "thesis_engine.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if thesis.returncode:
            raise RuntimeError(f"thesis_engine failed: {thesis.stderr or thesis.stdout}")
        build = subprocess.run(
            [python, "html_dashboard/build_time_series_dashboard.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if build.returncode:
            raise RuntimeError(build.stderr or build.stdout)

        PUBLIC_INDEX.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "html_dashboard" / "ai_compute_economics_monitor.html", PUBLIC_INDEX)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if publishable else 1


if __name__ == "__main__":
    raise SystemExit(main())
