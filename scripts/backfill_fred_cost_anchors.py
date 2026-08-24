#!/usr/bin/env python3
"""Cost anchors from FRED (no API key required): CPI (hardware deflator) + US electricity price.

- CPIAUCSL: 全项目 CPI，用于把名义硬件价格换算实际值
- APU000072620: 美国城市平均电价（USD/kWh，月度）——GPU 推理 OPEX 底座
定位：非阻塞信息源；官方免费公开数据。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "fred_cost_anchors.json"
SERIES = {
    "CPIAUCSL": {"label": "US CPI All Urban Consumers", "unit": "index1982-84=100", "keep_from": "2020-01-01"},
    "APU000072620": {"label": "US City Avg Electricity Price", "unit": "USD per kWh", "keep_from": "2020-01-01"},
}
USER_AGENT = "AIComputeEconomicsTracker/1.0"


def fetch_series(series_id: str) -> list[list[Any]]:
    import subprocess
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    proc = subprocess.run(
        ["curl", "-sS", "--http1.1", "--max-time", "45", url],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode:
        raise RuntimeError(f"curl exit {proc.returncode}: {proc.stderr[:200]}")
    raw = proc.stdout
    lines = raw.strip().splitlines()
    header = lines[0].split(",")
    out: list[list[Any]] = []
    keep_from = SERIES[series_id]["keep_from"]
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2 or not parts[1]:
            continue
        day = parts[0]
        if day < keep_from:
            continue
        out.append([day, round(float(parts[1]), 6)])
    return out


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    datasets: dict[str, list[list[Any]]] = {}
    quality: list[dict[str, str]] = []
    for sid, meta in SERIES.items():
        try:
            datasets[sid] = fetch_series(sid)
        except Exception as exc:
            quality.append({"source": sid, "status": "failed", "message": str(exc)})

    payload = {
        "fetchedAt": fetched_at,
        "refreshStatus": "fresh" if len(datasets) == len(SERIES) else ("partial" if datasets else "failed"),
        "publishable": True,
        "seriesMeta": SERIES,
        "datasets": datasets,
        "quality": quality,
        "blocking": False,
        "notes": ["FRED 公开 CSV 端点，无需 API key。用于名义->实际换算与电力 OPEX 锚。"],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": payload["refreshStatus"],
        "publishable": True,
        "rowsPerSeries": {k: len(v) for k, v in datasets.items()},
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
