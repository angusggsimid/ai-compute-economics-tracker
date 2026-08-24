#!/usr/bin/env python3
"""Ingest RightNow-AI/inference-cost-truth self-host throughput benchmarks (CC BY 4.0).

676 行带完整引用（engine/precision/并发/序列长度/来源 URL）的吞吐数据点，
补齐 Demand 单位经济缺失的半边：每 token 成本 = 价格 ÷ 吞吐。
静态数据集（上游标注验证日期），每次整表刷新幂等覆盖。非阻塞信息源。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "tracker_data" / "backfills" / "throughput_benchmarks.json"
SOURCE_URL = "https://raw.githubusercontent.com/RightNow-AI/inference-cost-truth/main/data/self-host.json"
ATTRIBUTION = "Data by RightNow-AI/inference-cost-truth, CC BY 4.0; 每行保留上游引用字段。"
USER_AGENT = "AIComputeEconomicsTracker/1.0"


def main() -> int:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    quality: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    formula = ""
    try:
        request = Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("rows") or []
        formula = str(payload.get("formula") or "")
        if not rows:
            raise ValueError("上游 rows 为空")
    except Exception as exc:
        quality.append({"source": "throughput_benchmarks", "status": "failed", "message": str(exc)})

    output = {
        "fetchedAt": fetched_at,
        "refreshStatus": "fresh" if rows else "failed",
        "publishable": True,
        "attribution": ATTRIBUTION,
        "sourceUrl": SOURCE_URL,
        "formula": formula,
        "utilizationLevels": [0.1, 0.3, 0.6, 0.9] if not quality else [],
        "rows": rows,
        "quality": quality,
        "blocking": False,
        "notes": ["每行含 engine/precision/并发/序列长度与 throughput_source_url；无引用的吞吐上游拒绝发布。"],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "refreshStatus": output["refreshStatus"],
        "publishable": True,
        "rowsTotal": len(rows),
        "failedSources": quality,
        "blocking": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
