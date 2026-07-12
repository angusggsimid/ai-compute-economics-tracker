from __future__ import annotations

import hashlib
import csv
import io
import json
import os
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

from production_store import DataQualityEvent, MarketFactObservation, ProductionStore


SNAPSHOT_DIR = Path("tracker_snapshots") / "market_facts"
USER_AGENT = "tracker-v2-market-facts/0.1 contact: local-research"

COMPUTEPRICES_GPU_API = "https://computeprices.com/api/v1/gpu-prices"
COMPUTEPRICES_GPU_TREND_API_TEMPLATE = "https://computeprices.com/api/v1/trends/gpu/{slug}"
COMPUTEPRICES_LLM_API = "https://computeprices.com/api/v1/llm-prices"
OPENROUTER_MODELS_API = "https://openrouter.ai/api/v1/models"
OPENROUTER_RANKINGS_DAILY_API = "https://openrouter.ai/api/v1/datasets/rankings-daily"
OPENROUTER_APP_RANKINGS_API = "https://openrouter.ai/api/v1/datasets/app-rankings"
OPENROUTER_MODEL_RANKINGS_CHART = "https://openrouter.ai/api/frontend/v1/rankings/model-rankings-chart"
OPENROUTER_FRONTEND_RANKINGS = {
    "tool_call_count": "https://openrouter.ai/api/frontend/v1/rankings/tools",
    "image_processing_count": "https://openrouter.ai/api/frontend/v1/rankings/images",
}
LITELLM_MODEL_PRICES_JSON = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
MODELS_DEV_API = "https://models.dev/api.json"
LLM_API_COSTGOAT = "https://costgoat.com/compare/llm-api"
GPUPERHOUR_OFFERS_API = "https://api.gpuindexes.com/api/offers"
GPUMARKETS_FIXINGS_CSV = "https://gpumarkets.dev/data/fixings.csv"
RUNPOD_GRAPHQL_API = "https://api.runpod.io/graphql"
RUNPOD_GRAPHQL_SPEC = "https://graphql-spec.runpod.io/"
VAST_BUNDLES_API = "https://console.vast.ai/api/v0/bundles/"
ARR_CLUB_HOME = "https://www.arr.club/"
AZURE_RETAIL_PRICES_API = "https://prices.azure.com/api/retail/prices"
AWS_EC2_SPOT_CURRENT_JSON = "https://website.spot.ec2.aws.a2z.com/spot.json"
RAMP_AI_INDEX_MAY_2026 = "https://econlab.substack.com/p/anthropic-beats-openai"
BYTEPLUS_MODELARK_PRICING = "https://docs.byteplus.com/en/docs/ModelArk/1544106"
SEEDANCE2_AI_PRICING = "https://seedance2.ai/pricing"
GPUS_IO_TRENDS = "https://gpus.io/en/trends"
AIMULTIPLE_GPU_INDEX = "https://aimultiple.com/gpu-index"
ALIBABA_AI_CLOUD_CAPEX = "https://www.alibabagroup.com/en-US/document-1930116148192346112"
TENCENT_Q1_2026_RESULTS = "https://www.prnewswire.com/apac/news-releases/tencent-announces-2026-first-quarter-results-302770779.html"
BAIDU_Q1_2026_RESULTS = "https://ir.baidu.com/news-releases/news-release-details/baidu-announces-first-quarter-2026-results/"
HUAWEI_2025_ANNUAL_REPORT = "https://www.huawei.com/en/annual-report/2025"
GETDEPLOYING_GPU_PAGES = {
    "H100": "https://getdeploying.com/gpus/nvidia-h100",
    "H200": "https://getdeploying.com/gpus/nvidia-h200",
    "B200": "https://getdeploying.com/gpus/nvidia-b200",
    "B300": "https://getdeploying.com/gpus/nvidia-b300",
    "A100": "https://getdeploying.com/gpus/nvidia-a100",
    "L40S": "https://getdeploying.com/gpus/nvidia-l40s",
    "RTX 4090": "https://getdeploying.com/gpus/nvidia-rtx-4090",
    "RTX 5090": "https://getdeploying.com/gpus/nvidia-rtx-5090",
    "MI300X": "https://getdeploying.com/gpus/amd-mi300x",
}

GPU_FOCUS = ("H100", "H200", "B200", "B300", "A100", "MI300X", "RTX 4090", "RTX 5090", "L40S")
COMPUTEPRICES_GPU_TRENDS = {"h100": "H100", "h200": "H200", "b200": "B200"}
GPUPERHOUR_GPU_QUERIES = {
    "H100": "h100-sxm-80gb,h100-pcie-80gb,h100-nvl",
    "H200": "h200-sxm,h200-nvl",
    "B200": "b200",
    "B300": "b300",
    "A100": "a100-sxm-80gb,a100-pcie-80gb,a100-sxm-40gb,a100-pcie-40gb",
    "MI300X": "mi300x",
    "L40S": "l40s",
    "RTX 4090": "rtx-4090",
    "RTX 5090": "rtx-5090",
}
AZURE_GPU_TERMS = ("H100", "H200", "A100", "MI300", "T4", "RTX")
AZURE_US_REGIONS = ("eastus", "eastus2", "westus2", "westus3", "southcentralus", "northcentralus")
AWS_GPU_INSTANCE_PREFIXES = ("p2.", "p3.", "p4", "p5", "p6", "g4dn.", "g5.", "g6.", "g6e.")
CREATOR_FOCUS = (
    "OpenAI",
    "Anthropic",
    "Google",
    "Gemini",
    "DeepSeek",
    "ByteDance",
    "Moonshot",
    "xAI",
    "x-ai",
    "Mistral",
    "Meta",
    "Alibaba",
    "Qwen",
)

BYTEPLUS_SEEDANCE_TOKEN_PRICES = [
    ("480p/720p", "input_without_video", 7.0, "For 480p and 720p outputs", "Input without video: 7.0"),
    ("480p/720p", "input_with_video", 4.3, "For 480p and 720p outputs", "Input with video: 4.3"),
    ("1080p", "input_without_video", 7.7, "For 1080p outputs", "Input without video: 7.7"),
    ("1080p", "input_with_video", 4.7, "For 1080p outputs", "Input with video: 4.7"),
    ("4K", "input_without_video", 4.0, "For 4k outputs", "Input without video: 4.0"),
    ("4K", "input_with_video", 2.4, "For 4k outputs", "Input with video: 2.4"),
]

SEEDANCE2_CREDIT_PRICES = [
    ("Seedance 2.0", "480p", "without_video_input", 6, 30),
    ("Seedance 2.0", "480p", "with_video_input", 4, 32),
    ("Seedance 2.0", "720p", "without_video_input", 12, 60),
    ("Seedance 2.0", "720p", "with_video_input", 8, 64),
    ("Seedance 2.0", "1080p", "without_video_input", 30, 150),
    ("Seedance 2.0", "1080p", "with_video_input", 20, 160),
    ("Seedance 2.0", "4K", "without_video_input", 70, 350),
    ("Seedance 2.0", "4K", "with_video_input", 40, 320),
    ("Seedance 2.0 Fast", "480p", "without_video_input", 5, 25),
    ("Seedance 2.0 Fast", "480p", "with_video_input", 3, 24),
    ("Seedance 2.0 Fast", "720p", "without_video_input", 10, 50),
    ("Seedance 2.0 Fast", "720p", "with_video_input", 6, 48),
    ("Seedance 2.0 Mini", "480p", "without_video_input", 3, 15),
    ("Seedance 2.0 Mini", "480p", "with_video_input", 2, 16),
    ("Seedance 2.0 Mini", "720p", "without_video_input", 6, 30),
    ("Seedance 2.0 Mini", "720p", "with_video_input", 4, 32),
]

GPUS_IO_RECOMMENDATIONS = {"Trending up", "Buying opportunity"}

CHINA_CLOUD_CAPEX_DISCLOSURES = [
    {
        "entity": "Alibaba Cloud",
        "ticker": "BABA / 9988.HK",
        "date": "2025-11-25",
        "metric": "ai_cloud_capex_ttm",
        "value": 120.0,
        "unit": "CNY_B",
        "dimension": "ttm_ai_cloud_infrastructure",
        "vendor": "Alibaba Group",
        "source_name": "Alibaba Group AI + Cloud investment update",
        "source_url": ALIBABA_AI_CLOUD_CAPEX,
        "observed_at": "2025-11-25T00:00:00Z",
        "markers": ["RMB120 billion", "AI and cloud infrastructure"],
        "notes": "Over the past four quarters, Alibaba deployed approximately RMB120 billion in capital expenditure to advance AI and cloud infrastructure.",
    },
    {
        "entity": "Tencent Cloud",
        "ticker": "0700.HK / TCEHY",
        "date": "2026-03-31",
        "metric": "capex_quarterly",
        "value": 31.9,
        "unit": "CNY_B",
        "dimension": "q1_2026_total_capex",
        "vendor": "Tencent",
        "source_name": "Tencent 1Q2026 results",
        "source_url": TENCENT_Q1_2026_RESULTS,
        "observed_at": "2026-05-13T00:00:00Z",
        "markers": ["Capital expenditure", "RMB31.9 billion"],
        "notes": "Tencent disclosed 1Q2026 capital expenditure of RMB31.9 billion, up 16% YoY; not cloud-only.",
    },
    {
        "entity": "Baidu AI Cloud",
        "ticker": "BIDU / 9888.HK",
        "date": "2026-03-31",
        "metric": "capex_quarterly",
        "value": 5.916,
        "unit": "CNY_B",
        "dimension": "q1_2026_consolidated_capex",
        "vendor": "Baidu",
        "source_name": "Baidu 1Q2026 results",
        "source_url": BAIDU_Q1_2026_RESULTS,
        "observed_at": "2026-05-18T00:00:00Z",
        "markers": ["Less: Capital expenditures", "AI Cloud Infra", "GPU Cloud"],
        "manual_fallback_text": (
            "Baidu Announces First Quarter 2026 Results. AI Cloud Infra revenue was RMB 8.8 billion "
            "in the first quarter of 2026, up 79% year over year. Revenue from GPU Cloud increased "
            "by 184% year over year. Less: Capital expenditures ... March 31, 2026 Baidu, Inc. "
            "(5,916) RMB million."
        ),
        "notes": "Baidu disclosed 1Q2026 consolidated capital expenditures of RMB5.916 billion; AI Cloud Infra revenue was RMB8.8 billion and GPU Cloud revenue grew 184% YoY.",
    },
    {
        "entity": "Huawei Cloud",
        "ticker": "private",
        "date": "2025-12-31",
        "metric": "cloud_revenue_including_other_segments",
        "value": 72.075,
        "unit": "CNY_B",
        "dimension": "cloud_context_not_capex",
        "vendor": "Huawei",
        "source_name": "Huawei 2025 Annual Report",
        "source_url": HUAWEI_2025_ANNUAL_REPORT,
        "observed_at": "2026-03-31T00:00:00Z",
        "markers": ["Cloud Computing", "CNY72,075 million", "R&D spending reached CNY192.3 billion"],
        "notes": "Huawei reports cloud-computing revenue context and R&D spending, but does not disclose a cloud CAPEX line in the public annual-report summary.",
    },
    {
        "entity": "Huawei",
        "ticker": "private",
        "date": "2025-12-31",
        "metric": "rd_spending",
        "value": 192.3,
        "unit": "CNY_B",
        "dimension": "annual_rd_context_not_capex",
        "vendor": "Huawei",
        "source_name": "Huawei 2025 Annual Report",
        "source_url": HUAWEI_2025_ANNUAL_REPORT,
        "observed_at": "2026-03-31T00:00:00Z",
        "markers": ["R&D spending reached CNY192.3 billion", "21.8%"],
        "notes": "Huawei disclosed 2025 R&D spending of CNY192.3 billion; this is context, not CAPEX.",
    },
]

CHINA_CLOUD_CAPEX_GAPS = [
    {
        "source_id": "bytedance-volcano-engine-capex-gap",
        "source_url": "https://www.volcengine.com/",
        "affected_key": "ByteDance Volcano Engine|china_cloud_capex",
        "message": "ByteDance is private and has no audited official CAPEX disclosure comparable with listed cloud vendors; dashboard excludes media estimates from official CAPEX rows.",
    }
]


@dataclass
class MarketFactsCollectionResult:
    facts: List[MarketFactObservation] = field(default_factory=list)
    quality_events: List[DataQualityEvent] = field(default_factory=list)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_from_iso(value: str) -> str:
    return value.split("T", 1)[0]


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value)).strip("-").lower() or "market-fact"


def _hash_text(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_snapshot(payload: str, source_id: str, fetched_at: str, suffix: str) -> tuple[str, str]:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _safe_slug(fetched_at.replace(":", ""))
    path = SNAPSHOT_DIR / f"{stamp}-{_safe_slug(source_id)}{suffix}"
    path.write_text(payload, encoding="utf-8")
    return str(path), _hash_text(payload)


def _base_kwargs(
    *,
    run_id: str,
    source_id: str,
    source_url: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    collection_method: str,
    source_type: str = "aggregator",
    observed_at: Optional[str] = None,
    confidence: float = 0.75,
    error_code: Optional[str] = None,
    is_production_eligible: bool = True,
) -> dict:
    return {
        "run_id": run_id,
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": snapshot_path,
        "source_type": source_type,
        "collection_method": collection_method,
        "observed_at": observed_at or fetched_at,
        "fetched_at": fetched_at,
        "raw_payload_hash": raw_payload_hash,
        "is_production_eligible": is_production_eligible,
        "confidence": confidence,
        "error_code": error_code,
    }


def _fact(
    *,
    date: str,
    track: str,
    entity: str,
    sub_entity: str,
    metric: str,
    value: float,
    unit: str,
    dimension: str,
    vendor: str,
    source_name: str,
    notes: str,
    provenance: dict,
) -> MarketFactObservation:
    return MarketFactObservation(
        date=date,
        track=track,
        entity=entity,
        sub_entity=sub_entity,
        metric=metric,
        value=float(value),
        unit=unit,
        dimension=dimension,
        vendor=vendor,
        source_name=source_name,
        notes=notes,
        **provenance,
    )


def _quality_event(
    *,
    run_id: str,
    source_id: str,
    source_url: str,
    reason_code: str,
    message: str,
    affected_key: str,
    fetched_at: str,
    severity: str = "warning",
) -> DataQualityEvent:
    payload = {
        "source_id": source_id,
        "source_url": source_url,
        "reason_code": reason_code,
        "message": message,
        "affected_key": affected_key,
        "fetched_at": fetched_at,
    }
    raw_hash = _hash_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return DataQualityEvent(
        event_id=f"{run_id}:{source_id}:{reason_code}",
        table_name="production_market_facts",
        severity=severity,
        message=message,
        affected_key=affected_key,
        is_blocking=False,
        run_id=run_id,
        source_id=source_id,
        source_url=source_url,
        snapshot_path=f"unavailable_marker://{source_id}/{reason_code}",
        source_type="manual_verified",
        collection_method="unavailable_marker",
        observed_at=fetched_at,
        fetched_at=fetched_at,
        raw_payload_hash=raw_hash,
        is_production_eligible=False,
        confidence=0.0,
        error_code=reason_code,
    )


def _fetch_json(url: str) -> tuple[dict, str]:
    response = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json(), response.text


def _env_value(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value:
        return value.strip()
    for env_path in (Path.cwd() / ".env", Path.cwd().parent / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, raw_value = text.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"').strip("'")
    return None


def _openrouter_auth_headers() -> Optional[dict]:
    token = _env_value("OPENROUTER_API_KEY") or _env_value("OPENROUTER_KEY")
    if not token:
        return None
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _fetch_json_with_headers(url: str, *, params: Optional[dict] = None, headers: Optional[dict] = None) -> tuple[dict, str, str]:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    response = requests.get(url, params=params, timeout=45, headers=request_headers)
    response.raise_for_status()
    return response.json(), response.text, response.url


def _fetch_json_with_params(url: str, params: dict) -> tuple[dict, str, str]:
    response = requests.get(url, params=params, timeout=30, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json(), response.text, response.url


def _post_json(url: str, payload: dict, *, timeout: int = 35) -> tuple[dict, str, str]:
    response = requests.post(
        url,
        json=payload,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json(), response.text, response.url


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _quantile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _fetch_browser_rendered_text(url: str, *, wait_ms: int = 10_000) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(f"Python Playwright is unavailable: {exc}") from exc

    chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    with sync_playwright() as playwright:
        launch_kwargs = {"headless": True}
        if chrome_path.exists():
            launch_kwargs["executable_path"] = str(chrome_path)
        browser = playwright.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 1600},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(wait_ms)
            return page.locator("body").inner_text(timeout=60_000)
        finally:
            browser.close()


def _gpu_family(value: str) -> str:
    text = str(value)
    for family in GPU_FOCUS:
        if family.lower() in text.lower():
            return family
    return text.split()[0] if text else "unknown"


def _normalize_tenor(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "spot" in text:
        return "spot"
    if "reserved" in text or "1-year" in text or "1 year" in text or "r1y" in text:
        return "one_year_reserved"
    if "demand" in text or "od" == text:
        return "on_demand"
    return text.replace(" ", "_").replace("-", "_") or "unknown"


def _parse_gpumarkets_fixings_csv(csv_text: str) -> List[dict]:
    rows: List[dict] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        series_id = str(row.get("series_id") or "").strip()
        chip = str(row.get("chip") or "").strip()
        date = str(row.get("fix_date_utc") or "").strip()
        fix_time = str(row.get("fix_time_utc") or "00:00").strip() or "00:00"
        price = _optional_float(row.get("price_usd_per_gpu_hr"))
        if not series_id or not chip or not date or price is None:
            continue
        rows.append(
            {
                "series_id": series_id,
                "gpu": _gpu_family(chip),
                "chip": chip,
                "tier": str(row.get("tier") or "").strip(),
                "vram": str(row.get("vram") or "").strip(),
                "tenor": _normalize_tenor(row.get("tenor")),
                "price": price,
                "delta_1d": _optional_float(row.get("delta_1d_pct")),
                "delta_7d": _optional_float(row.get("delta_7d_pct")),
                "delta_30d": _optional_float(row.get("delta_30d_pct")),
                "observations": _optional_float(row.get("observations")),
                "venues_eligible": _optional_float(row.get("venues_eligible")),
                "venues_total": _optional_float(row.get("venues_total")),
                "cw_price": _optional_float(row.get("price_cw_usd_per_gpu_hr")),
                "cw_delta": _optional_float(row.get("delta_cw_vs_fix_pct")),
                "venue_tier_breakdown": str(row.get("venue_tier_breakdown") or "").strip(),
                "cw_suppressed_reason": str(row.get("cw_suppressed_reason") or "").strip(),
                "date": date,
                "observed_at": f"{date}T{fix_time}:00Z" if len(fix_time) <= 5 else f"{date}T{fix_time}Z",
            }
        )
    return rows


def _gpuperhour_offer_family(row: dict) -> str:
    gpu = row.get("gpu") or {}
    text = " ".join(str(gpu.get(key) or "") for key in ("slug", "name"))
    normalized = text.lower().replace("-", " ")
    checks = [
        ("rtx 5090", "RTX 5090"),
        ("rtx 4090", "RTX 4090"),
        ("mi300x", "MI300X"),
        ("gh200", "GH200"),
        ("b300", "B300"),
        ("b200", "B200"),
        ("h200", "H200"),
        ("h100", "H100"),
        ("a100", "A100"),
        ("l40s", "L40S"),
    ]
    for needle, family in checks:
        if needle in normalized:
            return family
    return str(gpu.get("name") or gpu.get("slug") or "unknown")


def _vast_offer_family(row: dict) -> str:
    text = str(row.get("gpu_name") or "").lower().replace("_", " ")
    checks = [
        ("rtx 5090", "RTX 5090"),
        ("rtx 4090", "RTX 4090"),
        ("mi300x", "MI300X"),
        ("b300", "B300"),
        ("b200", "B200"),
        ("h200", "H200"),
        ("h100", "H100"),
        ("a100", "A100"),
        ("l40s", "L40S"),
    ]
    for needle, family in checks:
        if needle in text:
            return family
    return str(row.get("gpu_name") or "unknown")


def _parse_vast_bundle_offers(payload: dict) -> List[dict]:
    parsed: List[dict] = []
    for row in payload.get("offers") or []:
        if row.get("rentable") is not True or row.get("rented") is True:
            continue
        if str(row.get("verification") or "").lower() != "verified":
            continue
        gpu = _vast_offer_family(row)
        if gpu not in GPU_FOCUS:
            continue
        num_gpus = int(row.get("num_gpus") or 0)
        total_price = _optional_float(row.get("dph_total"))
        if not num_gpus or total_price is None:
            continue
        min_bid = _optional_float(row.get("min_bid"))
        parsed.append(
            {
                "id": str(row.get("id") or row.get("ask_contract_id") or ""),
                "entity": gpu,
                "gpu_name": str(row.get("gpu_name") or gpu),
                "num_gpus": num_gpus,
                "price_per_gpu": total_price / num_gpus,
                "min_bid_per_gpu": (min_bid / num_gpus) if min_bid is not None else None,
                "dlperf": _optional_float(row.get("dlperf")),
                "dlperf_per_dollar": _optional_float(row.get("dlperf_per_dphtotal")),
                "reliability": _optional_float(row.get("reliability")),
                "geolocation": str(row.get("geolocation") or ""),
                "machine_id": row.get("machine_id"),
                "host_id": row.get("host_id"),
                "cuda_max_good": row.get("cuda_max_good"),
                "gpu_ram": row.get("gpu_ram"),
            }
        )
    return parsed


def _runpod_gpu_family(value: Any) -> str:
    text = str(value or "").lower()
    checks = [
        ("rtx 5090", "RTX 5090"),
        ("rtx 4090", "RTX 4090"),
        ("mi300x", "MI300X"),
        ("b300", "B300"),
        ("b200", "B200"),
        ("h200", "H200"),
        ("h100", "H100"),
        ("a100", "A100"),
        ("l40s", "L40S"),
    ]
    for needle, family in checks:
        if needle in text:
            return family
    return str(value or "unknown")


def _parse_runpod_gpu_types(payload: dict, diagnostics: Optional[dict] = None) -> List[dict]:
    diagnostics = diagnostics if diagnostics is not None else {}

    def price(value: Any, *, tier_available: bool = True) -> Optional[float]:
        parsed_value = _optional_float(value)
        if parsed_value is not None and parsed_value <= 0:
            diagnostics["suppressed_nonpositive_prices"] = (
                diagnostics.get("suppressed_nonpositive_prices", 0) + 1
            )
        if not tier_available and parsed_value is not None:
            diagnostics["suppressed_unavailable_tier_prices"] = (
                diagnostics.get("suppressed_unavailable_tier_prices", 0) + 1
            )
        if parsed_value is None or parsed_value <= 0 or not tier_available:
            return None
        return parsed_value

    parsed: List[dict] = []
    for row in ((payload.get("data") or {}).get("gpuTypes") or []):
        identity = " ".join([str(row.get("id") or ""), str(row.get("displayName") or "")])
        if "mig" in identity.lower():
            diagnostics["rejected_mig"] = diagnostics.get("rejected_mig", 0) + 1
            continue
        gpu = _runpod_gpu_family(identity)
        if gpu not in GPU_FOCUS:
            continue
        lowest = row.get("lowestPrice") or {}
        secure_available = row.get("secureCloud") is True
        community_available = row.get("communityCloud") is True
        parsed.append(
            {
                "id": str(row.get("id") or ""),
                "entity": gpu,
                "display_name": str(row.get("displayName") or gpu),
                "memory_gb": _optional_float(row.get("memoryInGb")),
                "secure_cloud": secure_available,
                "community_cloud": community_available,
                "secure_price": price(row.get("securePrice"), tier_available=secure_available),
                "community_price": price(row.get("communityPrice"), tier_available=community_available),
                "secure_spot_price": price(row.get("secureSpotPrice"), tier_available=secure_available),
                "community_spot_price": price(
                    row.get("communitySpotPrice"), tier_available=community_available
                ),
                "one_week_price": price(row.get("oneWeekPrice")),
                "one_month_price": price(row.get("oneMonthPrice")),
                "max_gpu_count": _optional_float(row.get("maxGpuCount")),
                "max_gpu_count_community": _optional_float(row.get("maxGpuCountCommunityCloud")),
                "max_gpu_count_secure": _optional_float(row.get("maxGpuCountSecureCloud")),
                "lowest_minimum_bid_price": price(lowest.get("minimumBidPrice")),
                "lowest_uninterruptable_price": price(lowest.get("uninterruptablePrice")),
                "lowest_stock_status": str(lowest.get("stockStatus") or ""),
            }
        )
    return parsed


def _parse_gpuperhour_available_offers(payload: dict, *, expected_entity: str) -> tuple[str, int, List[dict]]:
    observed_at = str(payload.get("lastUpdated") or "")
    pagination = payload.get("pagination") or {}
    total = int(pagination.get("total") or 0)
    parsed: List[dict] = []
    for row in payload.get("data") or []:
        if row.get("isAvailable") is not True:
            continue
        if str(row.get("currency") or "USD").upper() != "USD":
            continue
        entity = _gpuperhour_offer_family(row)
        if entity != expected_entity:
            continue
        try:
            price_per_gpu = float(row.get("pricePerGpu"))
        except (TypeError, ValueError):
            continue
        gpu = row.get("gpu") or {}
        specs = row.get("specs") or {}
        region_info = row.get("regionInfo") or {}
        parsed.append(
            {
                "id": str(row.get("id") or ""),
                "entity": entity,
                "gpu_name": str(gpu.get("name") or entity),
                "gpu_slug": str(gpu.get("slug") or ""),
                "vram_gb": gpu.get("vramGB"),
                "provider": str(row.get("provider") or "unknown"),
                "provider_url": str(row.get("providerUrl") or ""),
                "region": str(row.get("region") or ""),
                "country": str(region_info.get("countryName") or ""),
                "continent": str(region_info.get("continent") or ""),
                "price_per_gpu": price_per_gpu,
                "price_hourly": row.get("priceHourly"),
                "gpu_count": int(row.get("gpuCount") or 1),
                "pricing_type": str(row.get("pricingType") or "unknown").replace("-", "_"),
                "deployment_type": str(row.get("deploymentType") or "unknown"),
                "security_tier": str(row.get("securityTier") or "unknown"),
                "last_seen": str(row.get("lastSeen") or ""),
                "vcpu_count": specs.get("vcpuCount"),
                "ram_gb": specs.get("ramGB"),
                "disk_gb": specs.get("diskGB"),
                "inet_down_mbps": specs.get("inetDownMbps"),
                "inet_up_mbps": specs.get("inetUpMbps"),
            }
        )
    return observed_at, total, parsed


def _aggregate_gpuperhour_exact_configs(offers: List[dict]) -> List[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for offer in offers:
        price = _optional_float(offer.get("price_per_gpu"))
        if price is None or price <= 0:
            continue
        provider = str(offer.get("provider") or "unknown").strip()
        variant = str(offer.get("gpu_slug") or "unknown").strip().lower()
        region = str(offer.get("region") or "unknown").strip().lower()
        billing = str(offer.get("pricing_type") or "unknown").strip().lower()
        security = str(offer.get("security_tier") or "unknown").strip().lower()
        deployment = str(offer.get("deployment_type") or "unknown").strip().lower()
        gpu_count = int(offer.get("gpu_count") or 0)
        key = (
            str(offer.get("entity") or "unknown"), provider, variant, region,
            gpu_count, billing, security, deployment,
        )
        grouped.setdefault(key, []).append(offer)

    aggregated: List[dict] = []
    for key, rows in grouped.items():
        entity, provider, variant, region, gpu_count, billing, security, deployment = key
        prices = sorted(float(row["price_per_gpu"]) for row in rows)
        dimension = (
            f"billing={billing}|variant={variant}|region={region}|gpu_count={gpu_count}|"
            f"security={security}|deployment={deployment}"
        )
        aggregated.append(
            {
                "entity": entity,
                "sub_entity": provider,
                "vendor": provider,
                "dimension": dimension,
                "median_price": float(statistics.median(prices)),
                "min_price": min(prices),
                "max_price": max(prices),
                "offer_count": len(rows),
                "offer_ids": sorted(str(row.get("id") or "") for row in rows),
            }
        )
    return sorted(aggregated, key=lambda row: (row["entity"], row["vendor"], row["dimension"]))


def _gpuperhour_exact_config_facts(
    offers: List[dict],
    *,
    observed_date: str,
    provenance: dict,
) -> List[MarketFactObservation]:
    facts: List[MarketFactObservation] = []
    for config in _aggregate_gpuperhour_exact_configs(offers):
        facts.append(
            _fact(
                date=observed_date,
                track="gpu_rental",
                entity=config["entity"],
                sub_entity=config["sub_entity"],
                metric="price_per_gpu_hour",
                value=config["median_price"],
                unit="USD/GPU hr",
                dimension=config["dimension"],
                vendor=config["vendor"],
                source_name="GPUPerHour exact-config daily offers",
                notes=(
                    f"offer_count={config['offer_count']}; min_price={config['min_price']}; "
                    f"max_price={config['max_price']}; offer_ids={','.join(config['offer_ids'])}; "
                    "aggregation=daily_median_same_exact_configuration"
                ),
                provenance=provenance,
            )
        )
    return facts


def _azure_gpu_family(row: dict) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("skuName", "meterName", "armSkuName", "productName"))
    checks = [
        ("MI300X", "MI300X"),
        ("H200", "H200"),
        ("H100", "H100"),
        ("A100", "A100"),
        ("RTX PRO 6000", "RTX PRO 6000"),
        ("RTX6K", "RTX PRO 6000"),
        ("T4", "T4"),
        ("V100", "V100"),
    ]
    upper = text.upper()
    for needle, label in checks:
        if needle in upper:
            return label
    return "Azure GPU VM"


def _azure_billing_type(row: dict) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("skuName", "meterName")).lower()
    if "spot" in text:
        return "spot"
    if "low priority" in text or "low-priority" in text:
        return "low_priority"
    return "on_demand"


def _aws_gpu_family(instance_type: str) -> str:
    value = str(instance_type or "").lower()
    if value.startswith("p6"):
        return "Blackwell GPU"
    if value.startswith("p5e") or value.startswith("p5en"):
        return "H200"
    if value.startswith("p5"):
        return "H100"
    if value.startswith("p4"):
        return "A100"
    if value.startswith("p3"):
        return "V100"
    if value.startswith("p2"):
        return "K80"
    if value.startswith("g6e"):
        return "L40S"
    if value.startswith("g6"):
        return "L4"
    if value.startswith("g5"):
        return "A10G"
    if value.startswith("g4dn"):
        return "T4"
    return "AWS GPU instance"


def _is_gpusio_gpu_name(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith(("NVIDIA ", "AMD ", "Intel "))


def _parse_percent(value: str) -> Optional[float]:
    match = re.search(r"([+-]?\d+(?:\.\d+)?)%", str(value or ""))
    return None if not match else float(match.group(1))


def _parse_gpusio_price(value: str) -> Optional[float]:
    match = re.search(r"\$([\d.]+)(?:/GPU/hr)?", str(value or ""))
    return None if not match else float(match.group(1))


def _parse_gpusio_price_range(value: str) -> tuple[Optional[float], Optional[float]]:
    matches = re.findall(r"\$([\d.]+)", str(value or ""))
    if len(matches) < 2:
        return None, None
    return float(matches[0]), float(matches[1])


def _parse_gpusio_trend_rows(text: str) -> List[dict]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    try:
        start = lines.index("All movers")
    except ValueError:
        return []

    rows: List[dict] = []
    i = start + 1
    while i < len(lines):
        if not _is_gpusio_gpu_name(lines[i]):
            i += 1
            continue
        name = lines[i]
        j = i + 1
        block: List[str] = []
        while j < len(lines) and not _is_gpusio_gpu_name(lines[j]):
            if lines[j] in {"Data last updated", "GPUs.io"}:
                break
            block.append(lines[j])
            j += 1

        price_idx = next((idx for idx, line in enumerate(block) if re.match(r"^\$[\d.]+/GPU/hr$", line)), None)
        if price_idx is None:
            i = j
            continue
        current_price = _parse_gpusio_price(block[price_idx])
        percent_values = [_parse_percent(line) for line in block[price_idx + 1 :] if _parse_percent(line) is not None]
        if current_price is None or len(percent_values) < 2:
            i = j
            continue

        range_line = next((line for line in block[price_idx + 1 :] if re.search(r"\$[\d.]+\s*[–-]\s*\$[\d.]+", line)), "")
        range_low, range_high = _parse_gpusio_price_range(range_line)
        rows.append(
            {
                "gpu": name,
                "vram": next((line for line in block[:price_idx] if re.match(r"^\d+\s?GB$", line)), ""),
                "providers": next((line for line in block[:price_idx] if re.match(r"^\d+\s+providers$", line)), ""),
                "category": next((line for line in block[:price_idx] if line in {"Datacenter", "Consumer"}), ""),
                "current_price": current_price,
                "delta_30d_pct": percent_values[0],
                "delta_90d_pct": percent_values[1],
                "range_low": range_low,
                "range_high": range_high,
                "recommendation": next((line for line in block[price_idx + 1 :] if line in GPUS_IO_RECOMMENDATIONS), ""),
            }
        )
        i = j
    return rows


def _parse_getdeploying_aggregate_offer(html_text: str) -> Optional[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    script = soup.find("script", attrs={"type": "application/ld+json"})
    if script is None or not script.string:
        return None
    try:
        payload = json.loads(script.string)
    except json.JSONDecodeError:
        return None
    graph = payload.get("@graph") if isinstance(payload, dict) else None
    if not isinstance(graph, list):
        return None
    product = next((item for item in graph if isinstance(item, dict) and item.get("@type") == "Product"), None)
    if not product:
        return None
    offers = product.get("offers") or {}
    try:
        low = float(offers.get("lowPrice"))
        high = float(offers.get("highPrice"))
        count = float(offers.get("offerCount"))
    except (TypeError, ValueError):
        return None
    return {
        "name": str(product.get("name") or ""),
        "description": str(product.get("description") or ""),
        "low": low,
        "high": high,
        "count": count,
        "currency": str(offers.get("priceCurrency") or "USD"),
        "availability": str(offers.get("availability") or ""),
    }


def _parse_aimultiple_gpu_index_text(text: str) -> List[dict]:
    plain = " ".join(str(text or "").split())
    rows: List[dict] = []
    patterns = [
        ("H100", r"H100 is listed by (?P<count>\d+) providers.*?median is now around \$(?P<median>\d+(?:\.\d+)?)/GPU-hour"),
        ("H200", r"H200(?:’s|'s) range runs from \$(?P<low>\d+(?:\.\d+)?).*?to \$(?P<high>\d+(?:\.\d+)?).*?median around \$(?P<median>\d+(?:\.\d+)?)"),
        ("A100", r"A100 holds a tight neocloud band around \$(?P<median>\d+(?:\.\d+)?)"),
        ("L40S", r"L40S has settled around \$(?P<median>\d+(?:\.\d+)?) median.*?AWS at \$(?P<high>\d+(?:\.\d+)?)"),
        ("RTX 4090", r"RTX 4090 .*? at \$(?P<median>\d+(?:\.\d+)?) median.*?Salad at \$(?P<low>\d+(?:\.\d+)?).*?Beam at \$(?P<high>\d+(?:\.\d+)?)"),
        ("B200", r"B200 median \$(?P<median>\d+(?:\.\d+)?), range \$(?P<low>\d+(?:\.\d+)?).*?to \$(?P<high>\d+(?:\.\d+)?)"),
        ("B300", r"B300 median \$(?P<median>\d+(?:\.\d+)?), range \$(?P<low>\d+(?:\.\d+)?).*?to \$(?P<high>\d+(?:\.\d+)?)"),
        ("MI300X", r"MI300X median \$(?P<median>\d+(?:\.\d+)?), range \$(?P<low>\d+(?:\.\d+)?).*?to \$(?P<high>\d+(?:\.\d+)?)"),
        ("RTX 5090", r"RTX 5090 median \$(?P<median>\d+(?:\.\d+)?), range \$(?P<low>\d+(?:\.\d+)?).*?to \$(?P<high>\d+(?:\.\d+)?)"),
    ]
    for gpu, pattern in patterns:
        match = re.search(pattern, plain, flags=re.I)
        if not match:
            continue
        row = {"gpu": gpu}
        for field in ["median", "low", "high", "count"]:
            value = match.groupdict().get(field)
            row[field] = None if value is None else float(value)
        rows.append(row)
    return rows


def _creator_in_focus(value: Any) -> bool:
    creator = str(value or "")
    return any(name.lower() in creator.lower() for name in CREATOR_FOCUS)


def _model_text_in_focus(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values)
    return any(name.lower() in text.lower() for name in CREATOR_FOCUS)


def _canonical_model_name(model_id: Any, display_name: Any = "") -> str:
    raw = str(display_name or model_id or "").strip()
    key = str(model_id or raw).strip().lower()
    key = key.replace("openrouter/", "").replace("azure_ai/", "").replace("vertex_ai/", "")
    key = key.replace("gemini/", "").replace("xai/", "").replace("x-ai/", "")
    key = key.replace("deepseek/", "").replace("anthropic/", "").replace("openai/", "")
    key = key.replace("~", "")
    checks = [
        ("claude-3-5-sonnet", "Claude 3.5 Sonnet"),
        ("claude-3.5-sonnet", "Claude 3.5 Sonnet"),
        ("claude-3-5-haiku", "Claude 3.5 Haiku"),
        ("claude-3.5-haiku", "Claude 3.5 Haiku"),
        ("gemini-3-flash", "Gemini 3 Flash"),
        ("gemini-3.1-flash", "Gemini 3.1 Flash"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("deepseek-v4-pro", "DeepSeek V4 Pro"),
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
        ("kimi-k2", "Kimi K2"),
        ("gpt-oss-120b", "GPT-OSS-120B"),
        ("gpt-5.4", "GPT-5.4"),
        ("gpt-5.2", "GPT-5.2"),
        ("gpt-5.1", "GPT-5.1"),
        ("gpt-5", "GPT-5"),
        ("grok-4", "Grok 4"),
    ]
    for needle, canonical in checks:
        if needle in key:
            return canonical
    if raw:
        return raw
    return str(model_id or "unknown")


def _provider_from_model_source(provider: Any, model_id: Any) -> str:
    text = " ".join([str(provider or ""), str(model_id or "")]).lower()
    if "anthropic" in text or "claude" in text:
        return "Anthropic"
    if "openai" in text or "gpt" in text:
        return "OpenAI"
    if "google" in text or "gemini" in text:
        return "Google"
    if "deepseek" in text:
        return "DeepSeek"
    if "xai" in text or "x-ai" in text or "grok" in text:
        return "xAI"
    if "mistral" in text or "codestral" in text:
        return "Mistral"
    if "moonshot" in text or "kimi" in text:
        return "Moonshot"
    if "alibaba" in text or "qwen" in text:
        return "Alibaba"
    return str(provider or "unknown")


def _per_token_to_per_1m(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def _parse_costgoat_models_from_next_data(html_text: str) -> tuple[str, List[dict]]:
    soup = BeautifulSoup(html_text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return "", []
    payload = json.loads(script.string)
    page_props = (payload.get("props") or {}).get("pageProps") or {}
    observed_at = str(page_props.get("currentDateIso") or "")
    models = page_props.get("models") or []
    parsed = []
    for row in models:
        model_id = str(row.get("id") or "").strip()
        output_price = row.get("outputPrice")
        quality = row.get("quality")
        if not model_id or output_price in (None, "") or quality in (None, ""):
            continue
        try:
            quality_value = float(quality)
            output_price_value = float(output_price)
        except (TypeError, ValueError):
            continue
        value_score = quality_value / output_price_value if output_price_value > 0 else None
        parsed.append(
            {
                "id": model_id,
                "name": str(row.get("name") or model_id),
                "provider": str(row.get("provider") or model_id.split("/", 1)[0]),
                "context_length": row.get("contextLength"),
                "input_price": row.get("inputPrice"),
                "output_price": output_price_value,
                "quality": quality_value,
                "value_score": value_score,
            }
        )
    return observed_at, parsed


def _collect_gpumarkets_fixings(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(GPUMARKETS_FIXINGS_CSV, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        raw = response.text
        snapshot_path, raw_hash = _write_snapshot(raw, "gpumarkets-fixings", fetched_at, ".csv")
        rows = _parse_gpumarkets_fixings_csv(raw)
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="gpumarkets-fixings",
                source_url=GPUMARKETS_FIXINGS_CSV,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"GPUMarkets fixings CSV unavailable or unparseable: {exc}",
                affected_key="gpu_market_fixing",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    if not rows:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="gpumarkets-fixings",
                source_url=GPUMARKETS_FIXINGS_CSV,
                reason_code="PARSE_CONFIDENCE_LOW",
                message="GPUMarkets fixings CSV fetched, but no fixing rows were parsed.",
                affected_key="gpu_market_fixing",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="gpumarkets-fixings",
        source_url=GPUMARKETS_FIXINGS_CSV,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="csv_http",
        source_type="aggregator",
        confidence=0.86,
    )
    metric_specs = [
        ("price_usd_per_gpu_hr", "price", "USD/GPU hr"),
        ("delta_1d_pct", "delta_1d", "percent"),
        ("delta_7d_pct", "delta_7d", "percent"),
        ("delta_30d_pct", "delta_30d", "percent"),
        ("observations", "observations", "observations"),
        ("venues_eligible", "venues_eligible", "venues"),
        ("venues_total", "venues_total", "venues"),
        ("price_cw_usd_per_gpu_hr", "cw_price", "USD/GPU hr"),
        ("delta_cw_vs_fix_pct", "cw_delta", "percent"),
    ]
    for row in rows:
        row_provenance = dict(provenance)
        row_provenance["observed_at"] = row["observed_at"]
        for metric, source_key, unit in metric_specs:
            value = row.get(source_key)
            if value is None:
                continue
            facts.append(
                _fact(
                    date=row["date"],
                    track="gpu_market_fixing",
                    entity=row["gpu"],
                    sub_entity=row["series_id"],
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension=row["tenor"],
                    vendor="GPUMarkets",
                    source_name="GPUMarkets fixings CSV",
                    notes=(
                        f"chip={row['chip']}; tier={row['tier']}; vram={row['vram']}; "
                        f"venue_tier_breakdown={row['venue_tier_breakdown']}; "
                        f"cw_suppressed_reason={row['cw_suppressed_reason']}; "
                        "fixing/delta data, not full historical time series unless multiple fixing dates are present"
                    ),
                    provenance=row_provenance,
                )
            )
    return facts, quality


def _collect_vast_bundle_offers(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    payload = {
        "limit": 250,
        "type": "on-demand",
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
    }
    try:
        response_payload, raw, request_url = _post_json(VAST_BUNDLES_API, payload)
        snapshot_path, raw_hash = _write_snapshot(raw, "vast-bundles-on-demand-verified", fetched_at, ".json")
        offers = _parse_vast_bundle_offers(response_payload)
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="vast-bundles-on-demand-verified",
                source_url=VAST_BUNDLES_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"Vast.ai bundles search unavailable or unparseable: {exc}",
                affected_key="gpu_orderbook_vast",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="vast-bundles-on-demand-verified",
        source_url=request_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        source_type="official",
        confidence=0.80,
    )

    grouped: dict[str, list[dict]] = {}
    for offer in offers:
        grouped.setdefault(offer["entity"], []).append(offer)

    for gpu, gpu_offers in grouped.items():
        prices = [offer["price_per_gpu"] for offer in gpu_offers if offer.get("price_per_gpu") is not None]
        min_bids = [offer["min_bid_per_gpu"] for offer in gpu_offers if offer.get("min_bid_per_gpu") is not None]
        dlperf = [offer["dlperf"] for offer in gpu_offers if offer.get("dlperf") is not None]
        dlperf_per_dollar = [offer["dlperf_per_dollar"] for offer in gpu_offers if offer.get("dlperf_per_dollar") is not None]
        reliability = [offer["reliability"] for offer in gpu_offers if offer.get("reliability") is not None]
        top_offer = min(gpu_offers, key=lambda item: item["price_per_gpu"])
        notes = (
            f"verified=true; rentable=true; rented=false; offer_count={len(gpu_offers)}; "
            f"lowest_offer_id={top_offer['id']}; lowest_gpu_name={top_offer['gpu_name']}; "
            f"lowest_geolocation={top_offer['geolocation']}; source_raw_snapshot stores full offer payload"
        )
        metrics = [
            ("offer_count", float(len(gpu_offers)), "offers"),
            ("price_min_per_gpu_hour", min(prices), "USD/GPU hr"),
            ("price_p25_per_gpu_hour", _quantile(prices, 0.25), "USD/GPU hr"),
            ("price_median_per_gpu_hour", statistics.median(prices), "USD/GPU hr"),
            ("price_p75_per_gpu_hour", _quantile(prices, 0.75), "USD/GPU hr"),
        ]
        if min_bids:
            metrics.append(("min_bid_min_per_gpu_hour", min(min_bids), "USD/GPU hr"))
        if dlperf:
            metrics.append(("dlperf_median", statistics.median(dlperf), "dlperf"))
        if dlperf_per_dollar:
            metrics.append(("dlperf_per_dollar_median", statistics.median(dlperf_per_dollar), "dlperf/USD_hr"))
        if reliability:
            metrics.append(("reliability_median", statistics.median(reliability), "ratio"))
        for metric, value, unit in metrics:
            if value is None:
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="vast_offer_snapshot",
                    entity=gpu,
                    sub_entity="Vast verified on-demand bundles",
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension="on_demand_verified_available",
                    vendor="Vast.ai",
                    source_name="Vast.ai bundles API",
                    notes=notes,
                    provenance=provenance,
                )
            )

    if not facts:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="vast-bundles-on-demand-verified",
                source_url=VAST_BUNDLES_API,
                reason_code="NO_TARGET_GPU_MATCH",
                message="Vast.ai bundles API returned offers, but no target GPU families matched the tracker focus list.",
                affected_key="gpu_orderbook_vast",
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _collect_runpod_gpu_prices(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    query = """
    query gpuTypes($input: GpuTypeFilter) {
      gpuTypes(input: $input) {
        id displayName manufacturer memoryInGb secureCloud communityCloud
        securePrice communityPrice oneWeekPrice oneMonthPrice communitySpotPrice secureSpotPrice throughput
        maxGpuCount maxGpuCountCommunityCloud maxGpuCountSecureCloud
        lowestPrice {
          gpuName gpuTypeId minimumBidPrice uninterruptablePrice stockStatus
        }
      }
    }
    """
    try:
        payload, raw, request_url = _post_json(RUNPOD_GRAPHQL_API, {"query": query, "variables": {"input": {}}})
        if payload.get("errors"):
            raise RuntimeError(json.dumps(payload.get("errors"), ensure_ascii=False)[:500])
        snapshot_path, raw_hash = _write_snapshot(raw, "runpod-gpu-types", fetched_at, ".json")
        diagnostics: dict = {}
        rows = _parse_runpod_gpu_types(payload, diagnostics=diagnostics)
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="runpod-gpu-types",
                source_url=RUNPOD_GRAPHQL_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"RunPod gpuTypes GraphQL unavailable or unparseable: {exc}",
                affected_key="gpu_orderbook_runpod",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="runpod-gpu-types",
        source_url=request_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="graphql_api",
        source_type="official",
        confidence=0.82,
    )
    if diagnostics:
        details = ", ".join(f"{key}={value}" for key, value in sorted(diagnostics.items()))
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="runpod-gpu-types",
                source_url=RUNPOD_GRAPHQL_API,
                reason_code="SOURCE_ROWS_QUARANTINED",
                message=f"RunPod rows or fields excluded from analytical output: {details}.",
                affected_key="gpu_orderbook_runpod_quarantine",
                fetched_at=fetched_at,
            )
        )
    metric_specs = [
        ("secure_price_per_gpu_hour", "secure_price", "USD/GPU hr", "secure_cloud"),
        ("community_price_per_gpu_hour", "community_price", "USD/GPU hr", "community_cloud"),
        ("secure_spot_price_per_gpu_hour", "secure_spot_price", "USD/GPU hr", "secure_spot"),
        ("community_spot_price_per_gpu_hour", "community_spot_price", "USD/GPU hr", "community_spot"),
        ("one_week_price_per_gpu_hour", "one_week_price", "USD/GPU hr", "one_week_reserved"),
        ("one_month_price_per_gpu_hour", "one_month_price", "USD/GPU hr", "one_month_reserved"),
        ("lowest_minimum_bid_price_per_gpu_hour", "lowest_minimum_bid_price", "USD/GPU hr", "lowest_bid"),
        ("lowest_uninterruptable_price_per_gpu_hour", "lowest_uninterruptable_price", "USD/GPU hr", "lowest_uninterruptable"),
        ("max_gpu_count", "max_gpu_count", "GPUs", "capacity"),
        ("max_gpu_count_community", "max_gpu_count_community", "GPUs", "capacity_community"),
        ("max_gpu_count_secure", "max_gpu_count_secure", "GPUs", "capacity_secure"),
    ]
    for row in rows:
        notes = (
            f"id={row['id']}; display_name={row['display_name']}; memory_gb={row['memory_gb']}; "
            f"secure_cloud={row['secure_cloud']}; community_cloud={row['community_cloud']}; "
            f"stock_status={row['lowest_stock_status']}; spec={RUNPOD_GRAPHQL_SPEC}"
        )
        for metric, key, unit, dimension in metric_specs:
            value = row.get(key)
            if value is None:
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="runpod_gpu_price_snapshot",
                    entity=row["entity"],
                    sub_entity=row["display_name"],
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension=dimension,
                    vendor="RunPod",
                    source_name="RunPod gpuTypes GraphQL",
                    notes=notes,
                    provenance=provenance,
                )
            )

    if not facts:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="runpod-gpu-types",
                source_url=RUNPOD_GRAPHQL_API,
                reason_code="NO_TARGET_GPU_MATCH",
                message="RunPod gpuTypes GraphQL returned data, but no focused GPU price rows were parsed.",
                affected_key="gpu_orderbook_runpod",
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _collect_computeprices_gpu(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        payload, raw = _fetch_json(COMPUTEPRICES_GPU_API)
        snapshot_path, raw_hash = _write_snapshot(raw, "computeprices-gpu-prices", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="computeprices-gpu-prices",
                source_url=COMPUTEPRICES_GPU_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"ComputePrices GPU API unavailable: {exc}",
                affected_key="gpu_rental",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="computeprices-gpu-prices",
        source_url=COMPUTEPRICES_GPU_API,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        confidence=0.78,
    )
    for row in payload.get("data", []):
        gpu = str(row.get("gpu") or "")
        gpu_model = _gpu_family(gpu)
        if gpu_model not in GPU_FOCUS:
            continue
        price = row.get("price_per_hour_usd")
        if price is None:
            continue
        observed_at = str(row.get("last_updated") or fetched_at)
        row_provenance = dict(provenance)
        row_provenance["observed_at"] = observed_at
        row_provenance["source_url"] = str(row.get("source_url") or COMPUTEPRICES_GPU_API)
        facts.append(
            _fact(
                date=_date_from_iso(observed_at),
                track="gpu_rental",
                entity=gpu_model,
                sub_entity=str(row.get("provider") or "unknown"),
                metric="price_per_gpu_hour",
                value=float(price),
                unit="USD/hr",
                dimension=str(row.get("pricing_type") or "unknown"),
                vendor=str(row.get("provider") or "unknown"),
                source_name="ComputePrices GPU API",
                notes=f"gpu={gpu}; vram_gb={row.get('vram_gb')}; gpu_count={row.get('gpu_count')}",
                provenance=row_provenance,
            )
        )
    return facts, quality


def _collect_gpuperhour_available_offers(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []

    for entity, query in GPUPERHOUR_GPU_QUERIES.items():
        params = {
            "gpu": query,
            "available": "true",
            "limit": 50,
            "sortBy": "pricePerGpu",
            "sortOrder": "asc",
        }
        source_id = f"gpuperhour-offers-{_safe_slug(entity)}"
        try:
            payload, raw, source_url = _fetch_json_with_params(GPUPERHOUR_OFFERS_API, params)
            snapshot_path, raw_hash = _write_snapshot(raw, source_id, fetched_at, ".json")
            observed_at, total, offers = _parse_gpuperhour_available_offers(payload, expected_entity=entity)
        except Exception as exc:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=GPUPERHOUR_OFFERS_API,
                    reason_code="SOURCE_UNAVAILABLE",
                    message=f"GPUPerHour offers API unavailable for {entity}: {exc}",
                    affected_key="gpuperhour_available_offers",
                    fetched_at=fetched_at,
                )
            )
            continue

        provenance = _base_kwargs(
            run_id=run_id,
            source_id=source_id,
            source_url=source_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            collection_method="json_api",
            source_type="aggregator",
            observed_at=observed_at or fetched_at,
            confidence=0.8,
        )

        facts.append(
            _fact(
                date=_date_from_iso(observed_at or fetched_at),
                track="gpu_available_offer",
                entity=entity,
                sub_entity="GPUPerHour API",
                metric="available_offer_count",
                value=float(total),
                unit="offers",
                dimension="available_true",
                vendor="GPUPerHour",
                source_name="GPUPerHour offers API",
                notes="API pagination total for available=true query; top offer rows are stored separately.",
                provenance=provenance,
            )
        )
        if total > 0 and not offers:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=source_url,
                    reason_code="PARSE_CONFIDENCE_LOW",
                    message=f"GPUPerHour returned {total} available {entity} offers, but none passed parser filters.",
                    affected_key=f"gpuperhour_available_offers_{_safe_slug(entity)}",
                    fetched_at=fetched_at,
                )
            )
            continue

        facts.extend(
            _gpuperhour_exact_config_facts(
                offers,
                observed_date=_date_from_iso(observed_at or fetched_at),
                provenance=provenance,
            )
        )

        for offer in offers:
            notes = (
                f"offer_id={offer['id']}; gpu_slug={offer['gpu_slug']}; gpu_count={offer['gpu_count']}; "
                f"total_price_hourly={offer['price_hourly']}; region={offer['region']}; country={offer['country']}; "
                f"continent={offer['continent']}; deployment={offer['deployment_type']}; security={offer['security_tier']}; "
                f"last_seen={offer['last_seen']}; vcpu={offer['vcpu_count']}; ram_gb={offer['ram_gb']}; "
                f"disk_gb={offer['disk_gb']}; inet_down_mbps={offer['inet_down_mbps']}; inet_up_mbps={offer['inet_up_mbps']}; "
                "available=true; sorted by GPUPerHour pricePerGpu asc"
            )
            facts.append(
                _fact(
                    date=_date_from_iso(observed_at or fetched_at),
                    track="gpu_available_offer",
                    entity=offer["entity"],
                    sub_entity=(
                        f"{offer['provider']} | {offer['gpu_name']} | {offer['region']} | "
                        f"{offer['pricing_type']} | {offer['security_tier']} | {offer['id'][:8]}"
                    ),
                    metric="available_price_per_gpu_hour",
                    value=offer["price_per_gpu"],
                    unit="USD/GPU hr",
                    dimension=offer["pricing_type"],
                    vendor=offer["provider"],
                    source_name="GPUPerHour offers API",
                    notes=notes,
                    provenance=provenance,
                )
            )
    return facts, quality


def _collect_computeprices_gpu_trends(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    for slug, gpu_model in COMPUTEPRICES_GPU_TRENDS.items():
        source_url = COMPUTEPRICES_GPU_TREND_API_TEMPLATE.format(slug=slug)
        try:
            payload, raw = _fetch_json(source_url)
            snapshot_path, raw_hash = _write_snapshot(raw, f"computeprices-trend-{slug}", fetched_at, ".json")
        except Exception as exc:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=f"computeprices-trend-{slug}",
                    source_url=source_url,
                    reason_code="SOURCE_UNAVAILABLE",
                    message=f"ComputePrices GPU trend API unavailable for {gpu_model}: {exc}",
                    affected_key=f"gpu_rental_trend_{gpu_model.lower()}",
                    fetched_at=fetched_at,
                )
            )
            continue

        meta = payload.get("meta") or {}
        provenance = _base_kwargs(
            run_id=run_id,
            source_id=f"computeprices-trend-{slug}",
            source_url=source_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            collection_method="json_api",
            confidence=0.72,
        )
        for row in payload.get("data", []):
            day = row.get("day")
            avg_price = row.get("avg_price_per_hour_usd")
            if not day or avg_price is None:
                continue
            observed_at = f"{day}T00:00:00Z"
            row_provenance = dict(provenance)
            row_provenance["observed_at"] = observed_at
            facts.append(
                _fact(
                    date=str(day),
                    track="gpu_rental_trend",
                    entity=gpu_model,
                    sub_entity="ComputePrices public trend",
                    metric="avg_price_per_gpu_hour",
                    value=float(avg_price),
                    unit="USD/hr",
                    dimension="public_tier_7d",
                    vendor="ComputePrices",
                    source_name="ComputePrices GPU Trend API",
                    notes=(
                        f"provider_count={row.get('provider_count')}; tier={meta.get('tier')}; "
                        f"days_returned={meta.get('days_returned')}; tier_cap_days={meta.get('tier_cap_days')}"
                    ),
                    provenance=row_provenance,
                )
            )
    return facts, quality


def _collect_computeprices_llm(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        payload, raw = _fetch_json(COMPUTEPRICES_LLM_API)
        snapshot_path, raw_hash = _write_snapshot(raw, "computeprices-llm-prices", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="computeprices-llm-prices",
                source_url=COMPUTEPRICES_LLM_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"ComputePrices LLM API unavailable: {exc}",
                affected_key="token_price",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="computeprices-llm-prices",
        source_url=COMPUTEPRICES_LLM_API,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        confidence=0.76,
    )
    metrics = [
        ("price_per_1m_input_usd", "input_price_per_1m_tokens"),
        ("price_per_1m_output_usd", "output_price_per_1m_tokens"),
        ("price_per_1m_cached_input_usd", "cached_input_price_per_1m_tokens"),
    ]
    for row in payload.get("data", []):
        if not _creator_in_focus(row.get("creator")):
            continue
        observed_at = str(row.get("last_updated") or fetched_at)
        row_provenance = dict(provenance)
        row_provenance["observed_at"] = observed_at
        row_provenance["source_url"] = str(row.get("source_url") or COMPUTEPRICES_LLM_API)
        for source_key, metric in metrics:
            value = row.get(source_key)
            if value is None:
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(observed_at),
                    track="token_price",
                    entity=str(row.get("model") or "unknown"),
                    sub_entity=str(row.get("provider") or "unknown"),
                    metric=metric,
                    value=float(value),
                    unit="USD/1M tokens",
                    dimension=str(row.get("pricing_type") or "standard"),
                    vendor=str(row.get("creator") or ""),
                    source_name="ComputePrices LLM API",
                    notes=f"context_window={row.get('context_window')}; modalities={row.get('modalities')}",
                    provenance=row_provenance,
                )
            )
    return facts, quality


def _openrouter_price_to_1m(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def _collect_openrouter_models(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        payload, raw = _fetch_json(OPENROUTER_MODELS_API)
        snapshot_path, raw_hash = _write_snapshot(raw, "openrouter-models", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="openrouter-models",
                source_url=OPENROUTER_MODELS_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"OpenRouter models API unavailable: {exc}",
                affected_key="token_price",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="openrouter-models",
        source_url=OPENROUTER_MODELS_API,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        confidence=0.82,
    )
    metric_map = {
        "prompt": "input_price_per_1m_tokens",
        "completion": "output_price_per_1m_tokens",
        "input_cache_read": "cached_input_price_per_1m_tokens",
    }
    for row in payload.get("data", []):
        name = str(row.get("name") or row.get("id") or "")
        vendor_hint = str(row.get("id") or "").split("/", 1)[0]
        if not any(hint.lower() in (name + " " + vendor_hint).lower() for hint in CREATOR_FOCUS):
            continue
        created = row.get("created")
        observed_at = datetime.fromtimestamp(created, tz=timezone.utc).isoformat().replace("+00:00", "Z") if created else fetched_at
        for source_key, metric in metric_map.items():
            price = _openrouter_price_to_1m((row.get("pricing") or {}).get(source_key))
            if price is None:
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="token_price",
                    entity=name,
                    sub_entity="OpenRouter",
                    metric=metric,
                    value=price,
                    unit="USD/1M tokens",
                    dimension="router_current",
                    vendor=vendor_hint,
                    source_name="OpenRouter Models API",
                    notes=f"context_length={row.get('context_length')}; observed_model_created={observed_at}",
                    provenance=provenance,
                )
            )
    return facts, quality


def _openrouter_vendor_from_slug(slug: str) -> str:
    if not slug or slug == "Others" or slug == "other":
        return "OpenRouter"
    return slug.split("/", 1)[0]


def _parse_openrouter_model_rankings_chart(payload: dict[str, Any]) -> tuple[Optional[str], list[dict[str, Any]]]:
    chart = payload.get("data") or {}
    points = chart.get("data") or []
    cached_at = chart.get("cachedAt")
    observed_at = None
    if cached_at is not None:
        try:
            observed_at = datetime.fromtimestamp(float(cached_at) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError, OSError):
            observed_at = None

    rows: list[dict[str, Any]] = []
    for point in points:
        date_value = str(point.get("x") or "").strip()
        values = point.get("ys") or {}
        if not date_value or not isinstance(values, dict):
            continue
        for model_slug, raw_value in values.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if value < 0:
                continue
            rows.append({"date": date_value, "model_slug": str(model_slug), "tokens": value})
    return observed_at, rows


def _collect_openrouter_model_rankings_chart(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    source_id = "openrouter-model-rankings-chart"
    try:
        payload, raw, request_url = _fetch_json_with_headers(OPENROUTER_MODEL_RANKINGS_CHART)
        snapshot_path, raw_hash = _write_snapshot(raw, source_id, fetched_at, ".json")
        observed_at, rows = _parse_openrouter_model_rankings_chart(payload)
    except Exception as exc:
        return [], [
            _quality_event(
                run_id=run_id,
                source_id=source_id,
                source_url=OPENROUTER_MODEL_RANKINGS_CHART,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"OpenRouter public weekly model token chart unavailable: {exc}",
                affected_key="openrouter_usage:model_total_tokens",
                fetched_at=fetched_at,
            )
        ]

    provenance = _base_kwargs(
        run_id=run_id,
        source_id=source_id,
        source_url=request_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        observed_at=observed_at or fetched_at,
        collection_method="json_api",
        source_type="official",
        confidence=0.86,
    )
    facts = [
        _fact(
            date=row["date"],
            track="openrouter_usage",
            entity=row["model_slug"],
            sub_entity="weekly_model_token_rankings",
            metric="model_total_tokens",
            value=row["tokens"],
            unit="tokens",
            dimension="weekly_public_top_models_plus_others",
            vendor=_openrouter_vendor_from_slug(row["model_slug"]),
            source_name="OpenRouter public model rankings chart",
            notes=(
                "Weekly prompt plus completion token volume shown by openrouter.ai/rankings; "
                "top visible model rows plus the source-provided Others bucket."
            ),
            provenance=provenance,
        )
        for row in rows
    ]
    if not facts:
        return [], [
            _quality_event(
                run_id=run_id,
                source_id=source_id,
                source_url=request_url,
                reason_code="EMPTY_SOURCE_PAYLOAD",
                message="OpenRouter public weekly model token chart returned no usable rows.",
                affected_key="openrouter_usage:model_total_tokens",
                fetched_at=fetched_at,
            )
        ]
    return facts, []


def _collect_openrouter_frontend_rankings(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    for metric, url in OPENROUTER_FRONTEND_RANKINGS.items():
        source_id = f"openrouter-frontend-rankings-{metric.replace('_', '-')}"
        try:
            payload, raw, request_url = _fetch_json_with_headers(url)
            snapshot_path, raw_hash = _write_snapshot(raw, source_id, fetched_at, ".json")
        except Exception as exc:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=url,
                    reason_code="SOURCE_UNAVAILABLE",
                    message=f"OpenRouter public frontend rankings unavailable for {metric}: {exc}",
                    affected_key=f"openrouter_usage:{metric}",
                    fetched_at=fetched_at,
                )
            )
            continue

        provenance = _base_kwargs(
            run_id=run_id,
            source_id=source_id,
            source_url=request_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            collection_method="json_api",
            source_type="official",
            confidence=0.74,
        )
        for point in payload.get("data", []):
            date = str(point.get("x") or "").strip()
            ys = point.get("ys") or {}
            if not date or not isinstance(ys, dict):
                continue
            for model_slug, raw_value in ys.items():
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                facts.append(
                    _fact(
                        date=date,
                        track="openrouter_usage",
                        entity=str(model_slug),
                        sub_entity="weekly_public_rankings",
                        metric=metric,
                        value=value,
                        unit="count",
                        dimension="weekly_frontend_public",
                        vendor=_openrouter_vendor_from_slug(str(model_slug)),
                        source_name="OpenRouter public rankings frontend API",
                        notes=(
                            "Public OpenRouter rankings endpoint used by openrouter.ai/rankings; "
                            "weekly activity proxy by model. Tool and image counts are not total text requests."
                        ),
                        provenance=provenance,
                    )
                )
    return facts, quality


def _collect_openrouter_rankings_daily(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    headers = _openrouter_auth_headers()
    if headers is None:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="openrouter-rankings-daily",
                source_url=OPENROUTER_RANKINGS_DAILY_API,
                reason_code="AUTH_REQUIRED",
                message="OpenRouter daily token rankings require OPENROUTER_API_KEY; no token-volume rows were inserted.",
                affected_key="openrouter_usage:model_total_tokens",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    end_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00")).date() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=90)
    params = {"start_date": start_dt.isoformat(), "end_date": end_dt.isoformat()}
    try:
        payload, raw, request_url = _fetch_json_with_headers(OPENROUTER_RANKINGS_DAILY_API, params=params, headers=headers)
        snapshot_path, raw_hash = _write_snapshot(raw, "openrouter-rankings-daily", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="openrouter-rankings-daily",
                source_url=OPENROUTER_RANKINGS_DAILY_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"OpenRouter authenticated daily token rankings unavailable: {exc}",
                affected_key="openrouter_usage:model_total_tokens",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    meta = payload.get("meta") or {}
    provenance = _base_kwargs(
        run_id=run_id,
        source_id="openrouter-rankings-daily",
        source_url=request_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        observed_at=str(meta.get("as_of") or fetched_at),
        collection_method="json_api",
        source_type="official",
        confidence=0.88,
    )
    for row in payload.get("data", []):
        date = str(row.get("date") or "").strip()
        model_slug = str(row.get("model_permaslug") or "").strip()
        if not date or not model_slug:
            continue
        try:
            tokens = float(row.get("total_tokens"))
        except (TypeError, ValueError):
            continue
        facts.append(
            _fact(
                date=date,
                track="openrouter_usage",
                entity=model_slug,
                sub_entity="daily_model_token_rankings",
                metric="model_total_tokens",
                value=tokens,
                unit="tokens",
                dimension="daily_public_top50_plus_other",
                vendor=_openrouter_vendor_from_slug(model_slug),
                source_name="OpenRouter datasets/rankings-daily API",
                notes=(
                    f"OpenRouter daily public model token rankings; meta_start={meta.get('start_date')}; "
                    f"meta_end={meta.get('end_date')}; token totals are prompt_tokens + completion_tokens."
                ),
                provenance=provenance,
            )
        )
    return facts, quality


def _collect_openrouter_app_rankings(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    headers = _openrouter_auth_headers()
    if headers is None:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="openrouter-app-rankings",
                source_url=OPENROUTER_APP_RANKINGS_API,
                reason_code="AUTH_REQUIRED",
                message="OpenRouter app request/token rankings require OPENROUTER_API_KEY; no app usage rows were inserted.",
                affected_key="openrouter_app_usage",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    base_end = datetime.fromisoformat(fetched_at.replace("Z", "+00:00")).date() - timedelta(days=1)
    for window_index in range(12, 0, -1):
        end_dt = base_end - timedelta(days=(window_index - 1) * 7)
        start_dt = end_dt - timedelta(days=6)
        params = {
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "sort": "popular",
            "limit": "20",
        }
        source_id = f"openrouter-app-rankings-{start_dt.isoformat()}-{end_dt.isoformat()}"
        try:
            payload, raw, request_url = _fetch_json_with_headers(OPENROUTER_APP_RANKINGS_API, params=params, headers=headers)
            snapshot_path, raw_hash = _write_snapshot(raw, source_id, fetched_at, ".json")
        except Exception as exc:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=OPENROUTER_APP_RANKINGS_API,
                    reason_code="SOURCE_UNAVAILABLE",
                    message=f"OpenRouter app rankings unavailable for {start_dt.isoformat()} - {end_dt.isoformat()}: {exc}",
                    affected_key="openrouter_app_usage",
                    fetched_at=fetched_at,
                )
            )
            continue
        meta = payload.get("meta") or {}
        provenance = _base_kwargs(
            run_id=run_id,
            source_id=source_id,
            source_url=request_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            observed_at=str(meta.get("as_of") or fetched_at),
            collection_method="json_api",
            source_type="official",
            confidence=0.86,
        )
        for row in payload.get("data", []):
            app_name = str(row.get("app_name") or row.get("app_id") or "").strip()
            if not app_name:
                continue
            app_id = str(row.get("app_id") or "")
            rank = row.get("rank")
            for metric, raw_value, unit in [
                ("app_total_tokens", row.get("total_tokens"), "tokens"),
                ("app_total_requests", row.get("total_requests"), "requests"),
            ]:
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                facts.append(
                    _fact(
                        date=end_dt.isoformat(),
                        track="openrouter_app_usage",
                        entity=app_name,
                        sub_entity=app_id,
                        metric=metric,
                        value=value,
                        unit=unit,
                        dimension="weekly_popular_apps",
                        vendor="OpenRouter",
                        source_name="OpenRouter datasets/app-rankings API",
                        notes=f"popular app ranking; rank={rank}; window={start_dt.isoformat()} - {end_dt.isoformat()}",
                        provenance=provenance,
                    )
                )
    return facts, quality


def _collect_litellm_model_prices(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        payload, raw = _fetch_json(LITELLM_MODEL_PRICES_JSON)
        snapshot_path, raw_hash = _write_snapshot(raw, "litellm-model-prices", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="litellm-model-prices",
                source_url=LITELLM_MODEL_PRICES_JSON,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"LiteLLM model_prices JSON unavailable: {exc}",
                affected_key="token_price_litellm",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="litellm-model-prices",
        source_url=LITELLM_MODEL_PRICES_JSON,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        source_type="aggregator",
        confidence=0.70,
    )
    metric_map = [
        ("input_cost_per_token", "input_price_per_1m_tokens"),
        ("output_cost_per_token", "output_price_per_1m_tokens"),
        ("cache_read_input_token_cost", "cached_input_price_per_1m_tokens"),
    ]
    for model_id, row in payload.items():
        if not isinstance(row, dict) or model_id == "sample_spec":
            continue
        provider = _provider_from_model_source(row.get("litellm_provider"), model_id)
        if not _model_text_in_focus(provider, model_id):
            continue
        entity = _canonical_model_name(model_id, row.get("display_name") or row.get("model_name"))
        notes = (
            f"model_key={model_id}; litellm_provider={row.get('litellm_provider')}; "
            f"max_input_tokens={row.get('max_input_tokens')}; max_output_tokens={row.get('max_output_tokens')}; "
            f"source={row.get('source') or 'LiteLLM community model_prices'}"
        )
        row_provenance = dict(provenance)
        if row.get("source"):
            row_provenance["source_url"] = str(row.get("source"))
        for source_key, metric in metric_map:
            price = _per_token_to_per_1m(row.get(source_key))
            if price is None:
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="token_price",
                    entity=entity,
                    sub_entity=str(model_id),
                    metric=metric,
                    value=price,
                    unit="USD/1M tokens",
                    dimension="litellm_catalog",
                    vendor=provider,
                    source_name="LiteLLM model_prices JSON",
                    notes=notes,
                    provenance=row_provenance,
                )
            )
    if not facts:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="litellm-model-prices",
                source_url=LITELLM_MODEL_PRICES_JSON,
                reason_code="PARSE_CONFIDENCE_LOW",
                message="LiteLLM model_prices JSON fetched, but no focused token price rows were parsed.",
                affected_key="token_price_litellm",
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _collect_models_dev_prices(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        payload, raw = _fetch_json(MODELS_DEV_API)
        snapshot_path, raw_hash = _write_snapshot(raw, "models-dev-api", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="models-dev-api",
                source_url=MODELS_DEV_API,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"models.dev API unavailable: {exc}",
                affected_key="token_price_models_dev",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="models-dev-api",
        source_url=MODELS_DEV_API,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        source_type="aggregator",
        confidence=0.72,
    )
    metric_map = [
        ("input", "input_price_per_1m_tokens"),
        ("output", "output_price_per_1m_tokens"),
        ("cache_read", "cached_input_price_per_1m_tokens"),
    ]
    for provider_key, provider_payload in payload.items():
        if not isinstance(provider_payload, dict):
            continue
        provider_name = _provider_from_model_source(provider_payload.get("name") or provider_key, provider_key)
        models = provider_payload.get("models") or {}
        if not isinstance(models, dict):
            continue
        for model_id, row in models.items():
            if not isinstance(row, dict):
                continue
            if not _model_text_in_focus(provider_name, model_id, row.get("name")):
                continue
            cost = row.get("cost") or {}
            if not isinstance(cost, dict):
                continue
            entity = _canonical_model_name(model_id, row.get("name"))
            notes = (
                f"provider_key={provider_key}; model_id={model_id}; release_date={row.get('release_date')}; "
                f"last_updated={row.get('last_updated')}; context={((row.get('limit') or {}).get('context'))}; "
                "models.dev cost fields are already USD per 1M tokens"
            )
            row_provenance = dict(provenance)
            if provider_payload.get("doc"):
                row_provenance["source_url"] = str(provider_payload.get("doc"))
            for source_key, metric in metric_map:
                value = cost.get(source_key)
                if value in (None, ""):
                    continue
                try:
                    price = float(value)
                except (TypeError, ValueError):
                    continue
                facts.append(
                    _fact(
                        date=_date_from_iso(fetched_at),
                        track="token_price",
                        entity=entity,
                        sub_entity=str(model_id),
                        metric=metric,
                        value=price,
                        unit="USD/1M tokens",
                        dimension="models_dev_catalog",
                        vendor=provider_name,
                        source_name="models.dev API",
                        notes=notes,
                        provenance=row_provenance,
                    )
                )
    if not facts:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="models-dev-api",
                source_url=MODELS_DEV_API,
                reason_code="PARSE_CONFIDENCE_LOW",
                message="models.dev API fetched, but no focused token price rows were parsed.",
                affected_key="token_price_models_dev",
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _collect_costgoat_llm_value(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(LLM_API_COSTGOAT, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        raw = response.text
        snapshot_path, raw_hash = _write_snapshot(raw, "costgoat-llm-api-comparison", fetched_at, ".html")
        observed_at, models = _parse_costgoat_models_from_next_data(raw)
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="costgoat-llm-api-comparison",
                source_url=LLM_API_COSTGOAT,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"CostGoat LLM comparison page unavailable or unparseable: {exc}",
                affected_key="model_value_score",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    if len(models) < 50:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="costgoat-llm-api-comparison",
                source_url=LLM_API_COSTGOAT,
                reason_code="PARSE_CONFIDENCE_LOW",
                message=f"CostGoat parsed only {len(models)} models; expected a broad public model list.",
                affected_key="model_value_score",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    observed_at = observed_at or fetched_at
    provenance = _base_kwargs(
        run_id=run_id,
        source_id="costgoat-llm-api-comparison",
        source_url=LLM_API_COSTGOAT,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        observed_at=observed_at,
        collection_method="next_data_parse",
        source_type="aggregator",
        confidence=0.72,
    )
    for row in models:
        provider = row["provider"]
        model_id = row["id"]
        notes = (
            f"name={row['name']}; context_length={row.get('context_length')}; "
            "quality source described by CostGoat as independent Theozard benchmark; "
            "value_score=quality/output_price_per_1m_tokens"
        )
        metric_rows = [
            ("quality_score", row["quality"], "score_0_100"),
            ("value_score_per_output_dollar", row["value_score"], "quality_points_per_USD_output_1M"),
            ("input_price_per_1m_tokens", row.get("input_price"), "USD/1M tokens"),
            ("output_price_per_1m_tokens", row.get("output_price"), "USD/1M tokens"),
        ]
        for metric, value, unit in metric_rows:
            if value in (None, ""):
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(observed_at),
                    track="model_value_score",
                    entity=model_id,
                    sub_entity=row["name"],
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension="public_quality_price_snapshot",
                    vendor=provider,
                    source_name="CostGoat LLM API comparison",
                    notes=notes,
                    provenance=provenance,
                )
            )
    return facts, quality


def _fetch_azure_retail_pages(filter_expr: str, *, top: int = 100) -> tuple[list[dict], str]:
    items: list[dict] = []
    urls: list[str] = []
    url = AZURE_RETAIL_PRICES_API
    params: Optional[dict] = {"$filter": filter_expr, "$top": str(top)}
    while url:
        response = requests.get(url, params=params, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        urls.append(response.url)
        payload = response.json()
        items.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
        params = None
        if len(items) >= 500:
            break
    return items, urls[0] if urls else AZURE_RETAIL_PRICES_API


def _collect_azure_retail_gpu_prices(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    all_items: list[dict] = []
    first_url = AZURE_RETAIL_PRICES_API
    errors: list[str] = []
    for region in AZURE_US_REGIONS:
        for term in AZURE_GPU_TERMS:
            filter_expr = (
                "serviceName eq 'Virtual Machines' "
                f"and armRegionName eq '{region}' "
                f"and contains(skuName, '{term}')"
            )
            try:
                items, request_url = _fetch_azure_retail_pages(filter_expr)
                first_url = request_url or first_url
                all_items.extend(items)
            except Exception as exc:
                errors.append(f"{region}/{term}: {exc}")

    if errors and not all_items:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="azure-retail-prices-gpu",
                source_url=AZURE_RETAIL_PRICES_API,
                reason_code="SOURCE_UNAVAILABLE",
                message="Azure Retail Prices GPU queries unavailable: " + "; ".join(errors[:4]),
                affected_key="cloud_instance_price",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    deduped: dict[tuple, dict] = {}
    for row in all_items:
        if row.get("currencyCode") != "USD":
            continue
        if row.get("unitOfMeasure") != "1 Hour":
            continue
        if row.get("type") != "Consumption":
            continue
        price = row.get("retailPrice")
        if price is None:
            continue
        key = (
            row.get("armRegionName"),
            row.get("skuId"),
            row.get("meterId"),
            row.get("skuName"),
            row.get("type"),
            row.get("effectiveStartDate"),
            row.get("retailPrice"),
        )
        deduped[key] = row

    raw_payload = json.dumps(
        {
            "fetched_at": fetched_at,
            "source_url": AZURE_RETAIL_PRICES_API,
            "regions": AZURE_US_REGIONS,
            "terms": AZURE_GPU_TERMS,
            "items": list(deduped.values()),
            "query_errors": errors,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    snapshot_path, raw_hash = _write_snapshot(raw_payload, "azure-retail-prices-gpu", fetched_at, ".json")
    provenance = _base_kwargs(
        run_id=run_id,
        source_id="azure-retail-prices-gpu",
        source_url=first_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        source_type="official",
        confidence=0.90,
    )
    for row in deduped.values():
        observed_at = str(row.get("effectiveStartDate") or fetched_at)
        row_provenance = dict(provenance)
        row_provenance["observed_at"] = observed_at
        row_provenance["source_url"] = AZURE_RETAIL_PRICES_API
        billing_type = _azure_billing_type(row)
        gpu_family = _azure_gpu_family(row)
        region = str(row.get("armRegionName") or "")
        facts.append(
            _fact(
                date=_date_from_iso(observed_at),
                track="cloud_instance_price",
                entity=gpu_family,
                sub_entity=str(row.get("armSkuName") or row.get("skuName") or "Azure GPU VM"),
                metric="instance_price_per_hour",
                value=float(row["retailPrice"]),
                unit="USD/VM hr",
                dimension=billing_type,
                vendor="Azure",
                source_name="Azure Retail Prices API",
                notes=(
                    f"region={region}; location={row.get('location')}; skuName={row.get('skuName')}; "
                    f"meterName={row.get('meterName')}; productName={row.get('productName')}; "
                    "price is VM instance-hour, not normalized per GPU"
                ),
                provenance=row_provenance,
            )
        )

    if errors:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="azure-retail-prices-gpu-partial",
                source_url=AZURE_RETAIL_PRICES_API,
                reason_code="PARTIAL_SOURCE_FAILURE",
                message="Some Azure Retail Prices GPU queries failed: " + "; ".join(errors[:4]),
                affected_key="cloud_instance_price",
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _collect_aws_current_spot_prices(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        payload, raw = _fetch_json(AWS_EC2_SPOT_CURRENT_JSON)
        snapshot_path, raw_hash = _write_snapshot(raw, "aws-ec2-current-spot", fetched_at, ".json")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="aws-ec2-current-spot",
                source_url=AWS_EC2_SPOT_CURRENT_JSON,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"AWS current Spot price JSON unavailable: {exc}",
                affected_key="cloud_spot_aws_current",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="aws-ec2-current-spot",
        source_url=AWS_EC2_SPOT_CURRENT_JSON,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="json_api",
        source_type="official",
        confidence=0.86,
    )
    regions = ((payload.get("config") or {}).get("regions") or [])
    for region in regions:
        region_name = str(region.get("region") or "")
        for family in region.get("instanceTypes") or []:
            for size in family.get("sizes") or []:
                instance_type = str(size.get("size") or "")
                if not instance_type.startswith(AWS_GPU_INSTANCE_PREFIXES):
                    continue
                for price_col in size.get("valueColumns") or []:
                    os_name = str(price_col.get("name") or "")
                    if os_name != "linux":
                        continue
                    price_text = (price_col.get("prices") or {}).get("USD")
                    if price_text is None:
                        continue
                    try:
                        price = float(price_text)
                    except (TypeError, ValueError):
                        continue
                    facts.append(
                        _fact(
                            date=_date_from_iso(fetched_at),
                            track="cloud_instance_price",
                            entity=_aws_gpu_family(instance_type),
                            sub_entity=instance_type,
                            metric="instance_price_per_hour",
                            value=price,
                            unit="USD/VM hr",
                            dimension="spot",
                            vendor="AWS",
                            source_name="AWS EC2 current Spot JSON",
                            notes=(
                                f"region={region_name}; os={os_name}; instance_type={instance_type}; "
                                "current spot only, not historical; price is VM instance-hour, not normalized per GPU"
                            ),
                            provenance=provenance,
                        )
                    )
    if not facts:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="aws-ec2-current-spot",
                source_url=AWS_EC2_SPOT_CURRENT_JSON,
                reason_code="NO_GPU_SKU_MATCH",
                message="AWS current Spot JSON was reachable, but no GPU instance prefixes matched the collector allowlist.",
                affected_key="cloud_spot_aws_current",
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _parse_money_to_usd_billion(text: str) -> Optional[float]:
    match = re.search(r"\$?\s*([\d.]+)\s*([KMB])", text.strip(), flags=re.I)
    if not match:
        return None
    value = float(match.group(1))
    suffix = match.group(2).upper()
    if suffix == "K":
        return value / 1_000_000
    if suffix == "M":
        return value / 1_000
    return value


def _collect_arr_club_public(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(ARR_CLUB_HOME, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.text
        snapshot_path, raw_hash = _write_snapshot(html, "arr-club-home", fetched_at, ".html")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="arr-club-home",
                source_url=ARR_CLUB_HOME,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"ARR.club public page unavailable: {exc}",
                affected_key="app_arr_public",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="arr-club-home",
        source_url=ARR_CLUB_HOME,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="html_parse",
        confidence=0.68,
    )
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".hp-leader-row")
    for row in rows:
        name_el = row.select_one(".hp-leader-name")
        value_el = row.select_one(".hp-leader-value")
        rank_el = row.select_one(".hp-leader-rank")
        if not name_el or not value_el:
            continue
        value = _parse_money_to_usd_billion(value_el.get_text(" ", strip=True))
        if value is None:
            continue
        company = name_el.get_text(" ", strip=True)
        href = row.get("href") or ""
        source_url = f"https://www.arr.club{href}" if str(href).startswith("/") else ARR_CLUB_HOME
        row_provenance = dict(provenance)
        row_provenance["source_url"] = source_url
        facts.append(
            _fact(
                date=_date_from_iso(fetched_at),
                track="app_commercialization",
                entity=company,
                sub_entity="public_arr_ranking",
                metric="arr",
                value=value,
                unit="USD_B_ARR",
                dimension="public_homepage_ranking",
                vendor="ARR.club",
                source_name="ARR.club public homepage",
                notes=f"rank={rank_el.get_text(' ', strip=True) if rank_el else ''}; value_text={value_el.get_text(' ', strip=True)}",
                provenance=row_provenance,
            )
        )
    quality.extend(_licensed_gap_events(run_id=run_id, fetched_at=fetched_at))
    return facts, quality


def _collect_ramp_ai_index_public(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(RAMP_AI_INDEX_MAY_2026, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.text
        snapshot_path, raw_hash = _write_snapshot(html, "ramp-ai-index-may-2026", fetched_at, ".html")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="ramp-ai-index-may-2026",
                source_url=RAMP_AI_INDEX_MAY_2026,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"Ramp AI Index public article unavailable: {exc}",
                affected_key="enterprise_ai_adoption",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    expected = {
        "Anthropic": 34.4,
        "OpenAI": 32.3,
        "Overall AI adoption": 50.6,
    }
    missing = [name for name, value in expected.items() if f"{value:.1f}%" not in text and str(value) not in text]
    if missing:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="ramp-ai-index-may-2026",
                source_url=RAMP_AI_INDEX_MAY_2026,
                reason_code="PARSE_CONFIDENCE_LOW",
                message=f"Ramp AI Index article fetched, but expected public values were not all found: {', '.join(missing)}.",
                affected_key="enterprise_ai_adoption",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="ramp-ai-index-may-2026",
        source_url=RAMP_AI_INDEX_MAY_2026,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="html_parse",
        source_type="manual_verified",
        observed_at="2026-05-13T00:00:00Z",
        confidence=0.70,
    )
    notes = "Ramp AI Index May 2026 update; corporate card and invoice-based business payments; public article values."
    for entity, value in expected.items():
        facts.append(
            _fact(
                date="2026-05-13",
                track="app_commercialization",
                entity=entity,
                sub_entity="Ramp AI Index May 2026",
                metric="business_adoption_share",
                value=float(value),
                unit="percent_of_businesses",
                dimension="corporate_payment_adoption",
                vendor="Ramp AI Index",
                source_name="Ramp Economics Lab public article",
                notes=notes,
                provenance=provenance,
            )
        )
    return facts, quality


def _collect_byteplus_seedance_pricing(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(BYTEPLUS_MODELARK_PRICING, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.text
        snapshot_path, raw_hash = _write_snapshot(html, "byteplus-modelark-seedance-pricing", fetched_at, ".html")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="byteplus-modelark-seedance-pricing",
                source_url=BYTEPLUS_MODELARK_PRICING,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"BytePlus ModelArk Seedance pricing page unavailable: {exc}",
                affected_key="seedance_official_pricing",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    missing = [
        marker
        for _, _, _, section_marker, value_marker in BYTEPLUS_SEEDANCE_TOKEN_PRICES
        for marker in (section_marker, value_marker)
        if marker not in html
    ]
    if missing:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="byteplus-modelark-seedance-pricing",
                source_url=BYTEPLUS_MODELARK_PRICING,
                reason_code="PARSE_CONFIDENCE_LOW",
                message="BytePlus Seedance pricing page fetched, but expected pricing markers were missing: "
                + ", ".join(sorted(set(missing))[:8]),
                affected_key="seedance_official_pricing",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="byteplus-modelark-seedance-pricing",
        source_url=BYTEPLUS_MODELARK_PRICING,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="embedded_json_parse",
        source_type="official",
        confidence=0.88,
    )
    for resolution, input_mode, price, section_marker, _ in BYTEPLUS_SEEDANCE_TOKEN_PRICES:
        facts.append(
            _fact(
                date=_date_from_iso(fetched_at),
                track="multimodal_generation_cost",
                entity="Dreamina Seedance 2.0",
                sub_entity=resolution,
                metric="video_generation_price_per_1m_tokens",
                value=float(price),
                unit="USD/1M tokens",
                dimension=input_mode,
                vendor="BytePlus ModelArk",
                source_name="BytePlus ModelArk pricing",
                notes=(
                    f"{section_marker}; {input_mode}; pricing varies by output resolution and whether video input is included; "
                    "token consumption determines final video cost"
                ),
                provenance=provenance,
            )
        )
    return facts, quality


def _collect_seedance2_credit_pricing(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(SEEDANCE2_AI_PRICING, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.text
        snapshot_path, raw_hash = _write_snapshot(html, "seedance2-ai-credit-pricing", fetched_at, ".html")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="seedance2-ai-credit-pricing",
                source_url=SEEDANCE2_AI_PRICING,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"seedance2.ai pricing page unavailable: {exc}",
                affected_key="seedance_wrapper_credit_pricing",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    expected_markers = [
        "Seedance 2.0 Series",
        "Credits/sec",
        "Seedance 2.0 Fast",
        "Seedance 2.0 Mini",
        "4K 70 350 credits 40 320 credits",
    ]
    missing = [marker for marker in expected_markers if marker not in text]
    if missing:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="seedance2-ai-credit-pricing",
                source_url=SEEDANCE2_AI_PRICING,
                reason_code="PARSE_CONFIDENCE_LOW",
                message="seedance2.ai pricing page fetched, but expected credit pricing markers were missing: "
                + ", ".join(missing),
                affected_key="seedance_wrapper_credit_pricing",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="seedance2-ai-credit-pricing",
        source_url=SEEDANCE2_AI_PRICING,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method="html_parse",
        source_type="aggregator",
        confidence=0.74,
    )
    for model, resolution, input_mode, credits_per_second, five_second_credits in SEEDANCE2_CREDIT_PRICES:
        for metric, value, unit in [
            ("video_generation_credits_per_second", credits_per_second, "credits/sec"),
            ("video_generation_5s_example_credits", five_second_credits, "credits/5s example"),
        ]:
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="multimodal_generation_cost",
                    entity=model,
                    sub_entity=resolution,
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension=input_mode,
                    vendor="seedance2.ai",
                    source_name="seedance2.ai public pricing",
                    notes=(
                        "Third-party wrapper credit schedule; with-video 5s example assumes 3s video input; "
                        "credits are not USD and must not be mixed with BytePlus USD token prices"
                    ),
                    provenance=provenance,
                )
            )
    return facts, quality


def _collect_china_cloud_capex_disclosures(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    for disclosure in CHINA_CLOUD_CAPEX_DISCLOSURES:
        source_url = disclosure["source_url"]
        source_id = f"china-cloud-capex-{_safe_slug(disclosure['entity'])}-{_safe_slug(disclosure['metric'])}"
        used_manual_fallback = False
        try:
            response = requests.get(source_url, timeout=18, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            raw = response.text
            snapshot_path, raw_hash = _write_snapshot(raw, source_id, fetched_at, ".html")
        except Exception as exc:
            fallback = disclosure.get("manual_fallback_text")
            if not fallback:
                quality.append(
                    _quality_event(
                        run_id=run_id,
                        source_id=source_id,
                        source_url=source_url,
                        reason_code="SOURCE_UNAVAILABLE",
                        message=f"China cloud CAPEX disclosure source unavailable for {disclosure['entity']}: {exc}",
                        affected_key=f"china_cloud_capex:{disclosure['entity']}",
                        fetched_at=fetched_at,
                    )
                )
                continue
            raw = json.dumps(
                {
                    "source_url": source_url,
                    "retrieval_error": str(exc),
                    "manual_verified_excerpt": fallback,
                    "fetched_at": fetched_at,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            snapshot_path, raw_hash = _write_snapshot(raw, f"{source_id}-manual-verified", fetched_at, ".json")
            used_manual_fallback = True
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=f"{source_id}-fetch-warning",
                    source_url=source_url,
                    reason_code="SOURCE_FETCH_FAILED_USING_MANUAL_VERIFIED_EXCERPT",
                    message=(
                        f"Direct fetch failed for {disclosure['entity']}; inserted a lower-confidence manual-verified "
                        f"official-source excerpt instead. Error: {exc}"
                    ),
                    affected_key=f"china_cloud_capex:{disclosure['entity']}",
                    fetched_at=fetched_at,
                )
            )

        text = raw if used_manual_fallback else BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        missing = [marker for marker in disclosure.get("markers", []) if marker not in text and marker not in raw]
        if missing:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=source_url,
                    reason_code="PARSE_CONFIDENCE_LOW",
                    message=(
                        f"China cloud CAPEX disclosure fetched for {disclosure['entity']}, "
                        f"but expected markers were missing: {', '.join(missing[:5])}."
                    ),
                    affected_key=f"china_cloud_capex:{disclosure['entity']}",
                    fetched_at=fetched_at,
                )
            )
            continue

        provenance = _base_kwargs(
            run_id=run_id,
            source_id=source_id,
            source_url=source_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            observed_at=disclosure["observed_at"],
            collection_method="manual_sourcebacked_yaml" if used_manual_fallback else "html_parse",
            source_type="manual_verified" if used_manual_fallback else "official",
            confidence=(0.70 if used_manual_fallback else 0.80) if disclosure["metric"].startswith("capex") or "capex" in disclosure["metric"] else (0.66 if used_manual_fallback else 0.72),
        )
        facts.append(
            _fact(
                date=disclosure["date"],
                track="china_cloud_capex",
                entity=disclosure["entity"],
                sub_entity=disclosure["ticker"],
                metric=disclosure["metric"],
                value=float(disclosure["value"]),
                unit=disclosure["unit"],
                dimension=disclosure["dimension"],
                vendor=disclosure["vendor"],
                source_name=disclosure["source_name"],
                notes=disclosure["notes"],
                provenance=provenance,
            )
        )

    for gap in CHINA_CLOUD_CAPEX_GAPS:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id=gap["source_id"],
                source_url=gap["source_url"],
                reason_code="NO_OFFICIAL_CAPEX_DISCLOSURE",
                message=gap["message"],
                affected_key=gap["affected_key"],
                fetched_at=fetched_at,
            )
        )
    return facts, quality


def _collect_gpusio_trends(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    collection_method = "html_parse"
    try:
        response = requests.get(GPUS_IO_TRENDS, timeout=30, headers={"User-Agent": USER_AGENT})
        if response.status_code == 403 or "Just a moment" in response.text:
            text = _fetch_browser_rendered_text(GPUS_IO_TRENDS)
            collection_method = "browser_rendered_text"
        else:
            response.raise_for_status()
            text = BeautifulSoup(response.text, "html.parser").get_text("\n", strip=True)
        snapshot_path, raw_hash = _write_snapshot(text, "gpus-io-trends-rendered-text", fetched_at, ".txt")
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="gpus-io-trends",
                source_url=GPUS_IO_TRENDS,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"GPUs.io trends page unavailable: {exc}",
                affected_key="gpu_market_trend",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    rows = _parse_gpusio_trend_rows(text)
    if not rows:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="gpus-io-trends",
                source_url=GPUS_IO_TRENDS,
                reason_code="PARSE_CONFIDENCE_LOW",
                message="GPUs.io trends page fetched, but no all-movers rows were parsed.",
                affected_key="gpu_market_trend",
                fetched_at=fetched_at,
            )
        )
        return facts, quality

    provenance = _base_kwargs(
        run_id=run_id,
        source_id="gpus-io-trends",
        source_url=GPUS_IO_TRENDS,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        collection_method=collection_method,
        source_type="aggregator",
        confidence=0.78,
    )
    for row in rows:
        notes = (
            f"vram={row['vram']}; providers={row['providers']}; category={row['category']}; "
            f"recommendation={row['recommendation']}; GPUs.io 90-day rolling window; median on-demand price"
        )
        metrics = [
            ("median_price_per_gpu_hour", row["current_price"], "USD/GPU hr"),
            ("price_delta_30d_pct", row["delta_30d_pct"], "percent"),
            ("price_delta_90d_pct", row["delta_90d_pct"], "percent"),
        ]
        if row["range_low"] is not None:
            metrics.append(("price_range_low_per_gpu_hour", row["range_low"], "USD/GPU hr"))
        if row["range_high"] is not None:
            metrics.append(("price_range_high_per_gpu_hour", row["range_high"], "USD/GPU hr"))
        for metric, value, unit in metrics:
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="gpu_market_trend",
                    entity=row["gpu"],
                    sub_entity=row["category"] or "unknown",
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension="gpusio_90d_window",
                    vendor="GPUs.io",
                    source_name="GPUs.io trends",
                    notes=notes,
                    provenance=provenance,
                )
            )
    return facts, quality


def _collect_getdeploying_gpu_index(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    for gpu, url in GETDEPLOYING_GPU_PAGES.items():
        source_id = f"getdeploying-{_safe_slug(gpu)}"
        try:
            response = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            html = response.text
            snapshot_path, raw_hash = _write_snapshot(html, source_id, fetched_at, ".html")
            offer = _parse_getdeploying_aggregate_offer(html)
        except Exception as exc:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=url,
                    reason_code="SOURCE_UNAVAILABLE",
                    message=f"GetDeploying GPU page unavailable for {gpu}: {exc}",
                    affected_key="gpu_rental_index_getdeploying",
                    fetched_at=fetched_at,
                )
            )
            continue
        if offer is None:
            quality.append(
                _quality_event(
                    run_id=run_id,
                    source_id=source_id,
                    source_url=url,
                    reason_code="PARSE_CONFIDENCE_LOW",
                    message=f"GetDeploying page fetched for {gpu}, but AggregateOffer low/high/count could not be parsed.",
                    affected_key="gpu_rental_index_getdeploying",
                    fetched_at=fetched_at,
                )
            )
            continue
        provenance = _base_kwargs(
            run_id=run_id,
            source_id=source_id,
            source_url=url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            collection_method="embedded_json_parse",
            source_type="aggregator",
            confidence=0.72,
        )
        metrics = [
            ("aggregate_low_price_per_gpu_hour", offer["low"], "USD/GPU hr"),
            ("aggregate_high_price_per_gpu_hour", offer["high"], "USD/GPU hr"),
            ("aggregate_offer_count", offer["count"], "offers"),
        ]
        for metric, value, unit in metrics:
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="gpu_rental_index",
                    entity=gpu,
                    sub_entity="AggregateOffer",
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension="getdeploying_gpu_page",
                    vendor="GetDeploying",
                    source_name="GetDeploying GPU page",
                    notes=(
                        f"name={offer['name']}; currency={offer['currency']}; availability={offer['availability']}; "
                        "AggregateOffer is page-level listing distribution, not a transaction price"
                    ),
                    provenance=provenance,
                )
            )
    return facts, quality


def _collect_aimultiple_gpu_index(*, run_id: str, fetched_at: str) -> tuple[List[MarketFactObservation], List[DataQualityEvent]]:
    facts: List[MarketFactObservation] = []
    quality: List[DataQualityEvent] = []
    try:
        response = requests.get(AIMULTIPLE_GPU_INDEX, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.text
        snapshot_path, raw_hash = _write_snapshot(html, "aimultiple-gpu-index", fetched_at, ".html")
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        rows = _parse_aimultiple_gpu_index_text(text)
    except Exception as exc:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="aimultiple-gpu-index",
                source_url=AIMULTIPLE_GPU_INDEX,
                reason_code="SOURCE_UNAVAILABLE",
                message=f"AIMultiple GPU index page unavailable: {exc}",
                affected_key="gpu_rental_index_aimultiple",
                fetched_at=fetched_at,
            )
        )
        return facts, quality
    if len(rows) < 5:
        quality.append(
            _quality_event(
                run_id=run_id,
                source_id="aimultiple-gpu-index",
                source_url=AIMULTIPLE_GPU_INDEX,
                reason_code="PARSE_CONFIDENCE_LOW",
                message=f"AIMultiple GPU index page fetched, but only {len(rows)} GPU median/range rows were parsed.",
                affected_key="gpu_rental_index_aimultiple",
                fetched_at=fetched_at,
            )
        )
        return facts, quality
    provenance = _base_kwargs(
        run_id=run_id,
        source_id="aimultiple-gpu-index",
        source_url=AIMULTIPLE_GPU_INDEX,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
            collection_method="html_parse",
        source_type="aggregator",
        confidence=0.66,
    )
    for row in rows:
        metrics = [("median_price_per_gpu_hour", row.get("median"), "USD/GPU hr")]
        if row.get("low") is not None:
            metrics.append(("range_low_price_per_gpu_hour", row.get("low"), "USD/GPU hr"))
        if row.get("high") is not None:
            metrics.append(("range_high_price_per_gpu_hour", row.get("high"), "USD/GPU hr"))
        if row.get("count") is not None:
            metrics.append(("provider_count", row.get("count"), "providers"))
        for metric, value, unit in metrics:
            if value is None:
                continue
            facts.append(
                _fact(
                    date=_date_from_iso(fetched_at),
                    track="gpu_rental_index",
                    entity=row["gpu"],
                    sub_entity="AIMultiple index article",
                    metric=metric,
                    value=float(value),
                    unit=unit,
                    dimension="aimultiple_monthly_index_text",
                    vendor="AIMultiple",
                    source_name="AIMultiple GPU Index",
                    notes=(
                        "Parsed from article text; monthly index across providers and tiers; "
                        "not provider-level quote and not transaction price"
                    ),
                    provenance=provenance,
                )
            )
    return facts, quality


def _licensed_gap_events(*, run_id: str, fetched_at: str) -> List[DataQualityEvent]:
    gaps = [
        (
            "arr-club-pro",
            "https://www.arr.club/pricing",
            "AUTH_REQUIRED",
            "ARR.club full database, source links, and ARR history require Pro access; public homepage rows were collected instead.",
            "app_arr_history",
        ),
        (
            "sacra-private-company-financials",
            "https://sacra.com/",
            "AUTH_REQUIRED",
            "Sacra private-company financials require subscription access; no estimates were inserted.",
            "private_company_financials",
        ),
        (
            "artificial-analysis-api",
            "https://artificialanalysis.ai/api-reference",
            "AUTH_REQUIRED",
            "Artificial Analysis API requires an account/API key; CostGoat public quality/value rows were collected as a lower-confidence public proxy, but Artificial Analysis benchmark rows were not inserted.",
            "model_quality_price",
        ),
        (
            "semianalysis-gpu-pricing-index",
            "https://semianalysis.com/",
            "AUTH_REQUIRED",
            "SemiAnalysis GPU Pricing Index is subscription research; no index value was inserted.",
            "gpu_contract_index",
        ),
        (
            "vast-ai-host-market-metrics-history",
            "https://docs.vast.ai/host/market-metrics",
            "AUTH_REQUIRED",
            "Vast.ai public bundles search is collected, but host market metrics history requires a host API key; no Vast.ai historical P10/median/P90 rows were inserted.",
            "gpu_marketplace_vast_ai_history",
        ),
        (
            "aws-ec2-spot-price-history",
            "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSpotPriceHistory.html",
            "AUTH_REQUIRED",
            "AWS current Spot JSON is collected, but EC2 Spot Price History requires signed AWS API access; no 90-day AWS spot history was inserted.",
            "cloud_spot_aws_history",
        ),
        (
            "gcp-cloud-billing-catalog",
            "https://cloud.google.com/billing/docs/reference/pricing-api",
            "AUTH_REQUIRED",
            "Google Cloud Pricing/Cloud Billing Catalog access requires Google Cloud credentials or API enablement; no GCP spot rows were inserted.",
            "cloud_spot_gcp",
        ),
        (
            "oci-gpu-pricing",
            "https://www.oracle.com/cloud/price-list/",
            "SOURCE_NOT_NORMALIZED",
            "Oracle Cloud public price list is not yet normalized into GPU spot/on-demand instance rows; no OCI rows were inserted in this collector.",
            "cloud_spot_oci",
        ),
    ]
    return [
        _quality_event(
            run_id=run_id,
            source_id=source_id,
            source_url=source_url,
            reason_code=reason,
            message=message,
            affected_key=affected_key,
            fetched_at=fetched_at,
        )
        for source_id, source_url, reason, message, affected_key in gaps
    ]


def collect_market_facts(*, run_id: Optional[str] = None) -> MarketFactsCollectionResult:
    fetched_at = _utc_now_iso()
    run_id = run_id or f"market-facts-{_safe_slug(fetched_at)}"
    result = MarketFactsCollectionResult()
    collectors = [
        _collect_gpumarkets_fixings,
        _collect_vast_bundle_offers,
        _collect_runpod_gpu_prices,
        _collect_computeprices_gpu,
        _collect_gpuperhour_available_offers,
        _collect_computeprices_gpu_trends,
        _collect_computeprices_llm,
        _collect_openrouter_models,
        _collect_openrouter_model_rankings_chart,
        _collect_openrouter_frontend_rankings,
        _collect_openrouter_rankings_daily,
        _collect_openrouter_app_rankings,
        _collect_litellm_model_prices,
        _collect_models_dev_prices,
        _collect_costgoat_llm_value,
        _collect_azure_retail_gpu_prices,
        _collect_aws_current_spot_prices,
        _collect_arr_club_public,
        _collect_ramp_ai_index_public,
        _collect_byteplus_seedance_pricing,
        _collect_seedance2_credit_pricing,
        _collect_china_cloud_capex_disclosures,
        _collect_gpusio_trends,
        _collect_getdeploying_gpu_index,
        _collect_aimultiple_gpu_index,
    ]
    for collector in collectors:
        facts, quality = collector(run_id=run_id, fetched_at=fetched_at)
        result.facts.extend(facts)
        result.quality_events.extend(quality)
    return result


def update_market_facts(*, store: Optional[ProductionStore] = None) -> MarketFactsCollectionResult:
    store = store or ProductionStore()
    result = collect_market_facts()
    if result.facts:
        store.insert_market_facts(result.facts)
    if result.quality_events:
        store.insert_quality_events(result.quality_events)
    return result
