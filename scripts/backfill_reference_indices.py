#!/usr/bin/env python3
"""Collect external transaction-based reference indices into a versionable daily history.

三个外部锚（均为免费公开层）：
- Ornn OCPI：成交型 GPU 租赁指数（public-3mo 滚动窗口，日线），每日快照累积历史
- Ornn OTPI：已实现 token 价格指数（public-1mo，按 lab）
- SemiAnalysis 公开数据：H100/A100/B200 综合现货指数（2023 起全历史）+ H100 1Y 合约价区间

定位：非阻塞信息源，作为自采报价层的成交价交叉验证基准；不阻塞正式页面发布。
许可：引用需署名来源（见 sources 元数据）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "reference_index_history.json"
SNAPSHOT_DIR = ROOT / "tracker_snapshots" / "market_facts"
USER_AGENT = "AIComputeEconomicsTracker/1.0"

ORNN_BASE = "https://index.ornn.com/api"
ORNN_GPUS = ("H100 SXM", "H200", "A100 SXM4", "B200", "RTX 5090")
ORNN_LICENSE = "Ornn free reference tier (public-3mo/public-1mo); attribution required"
SEMIANALYSIS_URL = "https://gpu-index.semianalysis.com/api/public-data"
SEMIANALYSIS_LICENSE = "SemiAnalysis public GPU pricing index page; attribution required"


def _get_json(url: str) -> tuple[dict[str, Any], bytes]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw), raw


def _collect_ornn_ocpi() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for gpu in ORNN_GPUS:
        payload, _ = _get_json(f"{ORNN_BASE}/gpu/{gpu.replace(' ', '%20')}/index-history?days=100")
        if not payload.get("success"):
            raise ValueError(f"Ornn OCPI {gpu}: unexpected response")
        for point in payload.get("data") or []:
            timestamp = str(point.get("timestamp") or "")
            value = point.get("index_value")
            if len(timestamp) < 10 or not isinstance(value, (int, float)) or value <= 0:
                continue
            date_iso = timestamp[:10]
            key = (date_iso, gpu)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "date": date_iso,
                "series": gpu,
                "indexValue": round(float(value), 6),
                "unit": "USD/GPU-hr",
                "basis": "transaction_index",
            })
    if not rows:
        raise ValueError("Ornn OCPI returned no usable rows")
    return sorted(rows, key=lambda row: (row["date"], row["series"]))


def _collect_ornn_otpi() -> list[dict[str, Any]]:
    payload, _ = _get_json(f"{ORNN_BASE}/otpi")
    if not payload.get("success"):
        raise ValueError("Ornn OTPI: unexpected response")
    rows: list[dict[str, Any]] = []
    for point in payload.get("data") or []:
        date_iso = str(point.get("date") or "")
        lab = str(point.get("lab") or "")
        value = point.get("indexPerMtok")
        if len(date_iso) != 10 or not lab or not isinstance(value, (int, float)) or value <= 0:
            continue
        rows.append({
            "date": date_iso,
            "series": lab,
            "indexValue": round(float(value), 6),
            "unit": "USD/Mtok",
            "basis": "realized_token_price",
        })
    if not rows:
        raise ValueError("Ornn OTPI returned no usable rows")
    return sorted(rows, key=lambda row: (row["date"], row["series"]))


def _parse_semianalysis(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if payload.get("status") != "ok":
        raise ValueError("SemiAnalysis public-data status not ok")

    composite: list[dict[str, Any]] = []
    for point in payload.get("index") or []:
        raw_date = str(point.get("date") or "")
        try:
            parsed = datetime.strptime(raw_date[:16].strip(), "%a, %d %b %Y")
        except ValueError:
            continue
        date_iso = parsed.date().isoformat()
        for series, field in (("H100", "h100"), ("A100", "a100"), ("B200", "b200")):
            value = point.get(field)
            if isinstance(value, (int, float)) and value > 0:
                composite.append({
                    "date": date_iso,
                    "series": series,
                    "indexValue": round(float(value), 6),
                    "unit": "USD/GPU-hr",
                    "basis": "composite_spot_contract_index",
                })

    contract_rows: list[dict[str, Any]] = []
    contract_blocks = payload.get("contract") or []
    for block in contract_blocks:
        for item in block.get("data") or []:
            period = str(item.get("period") or "")
            period_start = str(item.get("period_start") or "")
            try:
                start_iso = datetime.strptime(period_start[:16].strip(), "%a, %d %b %Y").date().isoformat()
            except ValueError:
                start_iso = ""
            for tenor, band in item.items():
                if not isinstance(band, list) or len(band) != 2:
                    continue
                low, high = band
                if not all(isinstance(v, (int, float)) and v > 0 for v in (low, high)):
                    continue
                contract_rows.append({
                    "date": start_iso,
                    "series": f"H100-{str(tenor)}",
                    "lowValue": round(float(low), 4),
                    "highValue": round(float(high), 4),
                    "unit": "USD/GPU-hr",
                    "basis": "survey_validated_contract_range",
                    "label": period,
                })
    if not composite:
        raise ValueError("SemiAnalysis returned no usable composite index rows")
    return (
        sorted(composite, key=lambda row: (row["date"], row["series"])),
        sorted(contract_rows, key=lambda row: (row["date"], row["series"])),
    )


def _collect_semianalysis() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload, _ = _get_json(SEMIANALYSIS_URL)
    return _parse_semianalysis(payload)


def _merge_datasets(
    previous: dict[str, list[dict[str, Any]]],
    fresh: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """按 (date, series) 合并；新值覆盖同键旧值，其余日期保留。"""
    merged: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for dataset, rows in previous.items():
        merged[dataset] = {
            (row["date"], row["series"]): row for row in rows
        }
    for dataset, rows in fresh.items():
        target = merged.setdefault(dataset, {})
        for row in rows:
            target[(row["date"], row["series"])] = row
    return {
        dataset: sorted(rows.values(), key=lambda row: (row["date"], row["series"]))
        for dataset, rows in merged.items()
    }


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = fetched_at.replace("-", "").replace(":", "").lower()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    collectors: dict[str, Any] = {}
    sources: dict[str, dict[str, Any]] = {}
    quality: list[dict[str, str]] = []

    def run(name: str, fn, url: str, license_note: str):
        try:
            result = fn()
            raw = json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
            snapshot_path = SNAPSHOT_DIR / f"{stamp}-refidx-{name}.json"
            snapshot_path.write_bytes(raw)
            collectors[name] = result
            sources[name] = {
                "url": url,
                "fetchedAt": fetched_at,
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "snapshotPath": str(snapshot_path.relative_to(ROOT)),
                "license": license_note,
                "status": "fresh",
            }
        except Exception as exc:
            quality.append({"source": name, "status": "failed", "message": str(exc)})
            sources[name] = {"url": url, "fetchedAt": fetched_at, "status": "failed", "message": str(exc)}

    ocpi = lambda: {"rows": _collect_ornn_ocpi()}
    otpi = lambda: {"rows": _collect_ornn_otpi()}
    semi = lambda: {"composite": _collect_semianalysis()[0]}

    def semi_all():
        composite, contract = _collect_semianalysis()
        return {"composite": composite, "contract1y": contract}

    run("ornn_ocpi", ocpi, f"{ORNN_BASE}/gpu/*/index-history", ORNN_LICENSE)
    run("ornn_otpi", otpi, f"{ORNN_BASE}/otpi", ORNN_LICENSE)
    run("semianalysis_public", semi_all, SEMIANALYSIS_URL, SEMIANALYSIS_LICENSE)

    ok_sources = [name for name in sources if sources[name].get("status") == "fresh"]
    if len(ok_sources) == 3:
        refresh_status = "fresh"
    elif ok_sources:
        refresh_status = "partial"
    else:
        refresh_status = "failed"

    fresh_datasets: dict[str, list[dict[str, Any]]] = {}
    if "ornn_ocpi" in collectors:
        fresh_datasets["ornnOcpi"] = collectors["ornn_ocpi"]["rows"]
    if "ornn_otpi" in collectors:
        fresh_datasets["ornnOtpi"] = collectors["ornn_otpi"]["rows"]
    if "semianalysis_public" in collectors:
        fresh_datasets["semiComposite"] = collectors["semianalysis_public"]["composite"]
        fresh_datasets["semiContract1y"] = collectors["semianalysis_public"]["contract1y"]

    previous_datasets: dict[str, list[dict[str, Any]]] = {}
    if OUTPUT_PATH.exists():
        try:
            stored = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            previous_datasets = stored.get("datasets") or {}
            if not isinstance(previous_datasets, dict):
                raise ValueError("datasets is not a dict")
        except (json.JSONDecodeError, ValueError) as exc:
            raise SystemExit(
                f"reference_index_history.json 缓存损坏或 schema 不符（{exc}）；拒绝静默覆盖累积历史。"
            )

    merged = _merge_datasets(previous_datasets, fresh_datasets)

    payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": refresh_status,
        "publishable": True,
        "datasets": merged,
        "sources": sources,
        "quality": quality,
        "notes": [
            "Ornn 免费层为滚动窗口（GPU 3mo/lab 1mo），必须每日快照累积，缺口无法回填。",
            "本层为成交型/调查型外部基准，用于交叉验证自采报价层，不进入主图。",
        ],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)

    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": refresh_status,
        "publishable": True,
        "datasetRows": {name: len(rows) for name, rows in merged.items()},
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
