from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup

from production_store import DataQualityEvent, GpuPriceObservation, ProductionStore


SNAPSHOT_DIR = Path("tracker_snapshots") / "gpu_prices"
USER_AGENT = "tracker-v2-gpu-pricing/0.1 contact: local-research"


@dataclass(frozen=True)
class GpuPricingSource:
    source_id: str
    source_url: str
    parser: str
    gpu_model: Optional[str] = None
    source_type: str = "public_pricing_page"


@dataclass
class GpuPricingCollectionResult:
    observations: List[GpuPriceObservation] = field(default_factory=list)
    quality_events: List[DataQualityEvent] = field(default_factory=list)


DEFAULT_GPU_PRICING_SOURCES = (
    GpuPricingSource(
        source_id="runpod-pricing",
        source_url="https://www.runpod.io/pricing",
        parser="runpod",
        source_type="public_pricing_page",
    ),
    GpuPricingSource(
        source_id="lambda-pricing",
        source_url="https://lambda.ai/pricing",
        parser="lambda",
        source_type="public_pricing_page",
    ),
    GpuPricingSource(
        source_id="computeprices-h100",
        source_url="https://computeprices.com/gpus/h100",
        parser="computeprices",
        gpu_model="H100",
        source_type="aggregator",
    ),
    GpuPricingSource(
        source_id="computeprices-h200",
        source_url="https://computeprices.com/gpus/h200",
        parser="computeprices",
        gpu_model="H200",
        source_type="aggregator",
    ),
)


RUNPOD_GPU_LABELS = {
    "H100 PCIe": ("H100", "PCIe"),
    "H100 SXM": ("H100", "SXM"),
    "H100 NVL": ("H100", "NVL"),
    "H200": ("H200", "H200"),
    "B200": ("B200", "B200"),
    "B300": ("B300", "B300"),
}


LAMBDA_CLUSTER_LABELS = {
    "NVIDIA H100": ("H100", "H100 cluster"),
    "NVIDIA HGX B200": ("B200", "HGX B200 cluster"),
}


LAMBDA_INSTANCE_RE = re.compile(r"^NVIDIA\s+(?P<model>H100|H200|B200|A100|GH200)\s*(?P<variant>.*)$")
PRICE_RE = re.compile(r"^\$?\s*(?P<price>\d+(?:\.\d+)?)$")
DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_from_iso(value: str) -> str:
    return value.split("T", 1)[0]


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()


def _payload_hash(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snapshot_path(snapshot_dir: Path, source_id: str, fetched_at: str, suffix: str) -> Path:
    stamp = _safe_slug(fetched_at.replace(":", "").replace("+", ""))
    return snapshot_dir / f"{stamp}-{_safe_slug(source_id)}{suffix}"


def _write_snapshot(payload: str, snapshot_dir: Path, source_id: str, fetched_at: str, suffix: str = ".html") -> Tuple[str, str]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(snapshot_dir, source_id, fetched_at, suffix)
    path.write_text(payload, encoding="utf-8")
    return str(path), _payload_hash(payload)


def _tokens(html: str) -> List[str]:
    return [token.strip() for token in BeautifulSoup(html, "html.parser").stripped_strings if token.strip()]


def _parse_price_token(token: str) -> Optional[float]:
    compact = token.strip().replace(",", "")
    match = PRICE_RE.match(compact)
    if not match:
        return None
    return float(match.group("price"))


def _parse_money_token(token: str) -> Optional[float]:
    compact = token.strip().replace(",", "")
    if not compact.startswith("$"):
        return None
    return _parse_price_token(compact)


def _parse_gpu_count(value: str) -> Optional[int]:
    match = re.search(r"\d+", value.replace(",", ""))
    if not match:
        return None
    return int(match.group(0))


def _quote_date_to_iso(value: str) -> str:
    parsed = datetime.strptime(value, "%m/%d/%Y")
    return parsed.strftime("%Y-%m-%d")


def _quote_age_days(quote_date: str, fetched_at: str) -> int:
    fetched_date = datetime.fromisoformat(fetched_at.replace("Z", "+00:00")).date()
    quote = datetime.strptime(quote_date, "%Y-%m-%d").date()
    return (fetched_date - quote).days


def _base_kwargs(
    *,
    run_id: str,
    source_id: str,
    source_url: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    source_type: str,
    observed_at: Optional[str] = None,
    confidence: float = 0.9,
    is_production_eligible: bool = True,
    error_code: Optional[str] = None,
) -> dict:
    return {
        "run_id": run_id,
        "source_id": source_id,
        "source_url": source_url,
        "snapshot_path": snapshot_path,
        "source_type": source_type,
        "collection_method": "html_parse",
        "observed_at": observed_at or fetched_at,
        "fetched_at": fetched_at,
        "raw_payload_hash": raw_payload_hash,
        "is_production_eligible": is_production_eligible,
        "confidence": confidence,
        "error_code": error_code,
    }


def _gpu_row(
    *,
    date: str,
    provider: str,
    gpu_model: str,
    gpu_variant: str,
    billing_type: str,
    commitment: str,
    gpu_count: int,
    region: str,
    price_per_gpu_hour: float,
    availability_observed: bool,
    provenance: dict,
) -> GpuPriceObservation:
    return GpuPriceObservation(
        date=date,
        provider=provider,
        gpu_model=gpu_model,
        gpu_variant=gpu_variant,
        billing_type=billing_type,
        commitment=commitment,
        gpu_count=gpu_count,
        region=region,
        price_per_gpu_hour=price_per_gpu_hour,
        currency="USD",
        availability_observed=availability_observed,
        **provenance,
    )


def parse_runpod_official_html(
    html: str,
    *,
    run_id: str,
    source_id: str,
    source_url: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    source_type: str = "public_pricing_page",
) -> List[GpuPriceObservation]:
    tokens = _tokens(html)
    rows: List[GpuPriceObservation] = []
    seen = set()
    provenance = _base_kwargs(
        run_id=run_id,
        source_id=source_id,
        source_url=source_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_payload_hash,
        fetched_at=fetched_at,
        source_type=source_type,
        confidence=0.9,
    )

    for idx, token in enumerate(tokens):
        if token not in RUNPOD_GPU_LABELS or token in seen:
            continue
        price = None
        for cursor in range(idx + 1, min(len(tokens) - 1, idx + 12)):
            if tokens[cursor] == "$" and cursor + 2 < len(tokens):
                parsed = _parse_price_token(tokens[cursor + 1])
                if parsed is not None and tokens[cursor + 2].lower() in {"/hr", "/hour"}:
                    price = parsed
                    break
            parsed_money = _parse_money_token(tokens[cursor])
            if parsed_money is not None and cursor + 1 < len(tokens) and tokens[cursor + 1].lower() in {"/hr", "/hour"}:
                price = parsed_money
                break
        if price is None:
            continue
        model, variant = RUNPOD_GPU_LABELS[token]
        rows.append(
            _gpu_row(
                date=_date_from_iso(fetched_at),
                provider="RunPod",
                gpu_model=model,
                gpu_variant=variant,
                billing_type="on-demand",
                commitment="per-hour; pricing_page=community_or_secure_cloud",
                gpu_count=1,
                region="global_public_page",
                price_per_gpu_hour=price,
                availability_observed=True,
                provenance=provenance,
            )
        )
        seen.add(token)

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    for label, (model, variant) in RUNPOD_GPU_LABELS.items():
        if label in seen:
            continue
        match = re.search(
            rf"\b{re.escape(label)}\b[^$]{{0,180}}\$\s*(\d+(?:\.\d+)?)\s*/\s*(?:hr|hour)",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        rows.append(
            _gpu_row(
                date=_date_from_iso(fetched_at),
                provider="RunPod",
                gpu_model=model,
                gpu_variant=variant,
                billing_type="on-demand",
                commitment="per-hour; pricing_page=community_or_secure_cloud",
                gpu_count=1,
                region="global_public_page",
                price_per_gpu_hour=float(match.group(1)),
                availability_observed=True,
                provenance=provenance,
            )
        )
        seen.add(label)
    return rows


def _lambda_gpu_parts(plan: str) -> Optional[Tuple[str, str]]:
    if plan in LAMBDA_CLUSTER_LABELS:
        return LAMBDA_CLUSTER_LABELS[plan]
    match = LAMBDA_INSTANCE_RE.match(plan)
    if not match:
        return None
    model = match.group("model")
    variant = match.group("variant").strip() or model
    return model, variant


def _lambda_instance_gpu_count(vcpus: int) -> int:
    if vcpus <= 0:
        return 1
    return max(1, round(vcpus / 26))


def _append_lambda_cluster_row(
    rows: List[GpuPriceObservation],
    seen: set,
    plan: str,
    duration: str,
    count_value: str,
    price_value: str,
    provenance: dict,
    fetched_at: str,
) -> None:
    parts = _lambda_gpu_parts(plan)
    price = _parse_money_token(price_value)
    gpu_count = _parse_gpu_count(count_value)
    if parts is None or price is None or gpu_count is None:
        return
    model, variant = parts
    key = ("cluster", model, variant, gpu_count, price)
    if key in seen:
        return
    rows.append(
        _gpu_row(
            date=_date_from_iso(fetched_at),
            provider="Lambda",
            gpu_model=model,
            gpu_variant=variant,
            billing_type="1-click-cluster",
            commitment=duration.replace("–", "-"),
            gpu_count=gpu_count,
            region="global_public_page",
            price_per_gpu_hour=price,
            availability_observed=True,
            provenance=provenance,
        )
    )
    seen.add(key)


def _append_lambda_instance_row(
    rows: List[GpuPriceObservation],
    seen: set,
    plan: str,
    vcpus_value: str,
    price_value: str,
    provenance: dict,
    fetched_at: str,
) -> None:
    parts = _lambda_gpu_parts(plan)
    price = _parse_money_token(price_value)
    if parts is None or price is None or not vcpus_value.replace(",", "").isdigit():
        return
    model, variant = parts
    vcpus = int(vcpus_value.replace(",", ""))
    gpu_count = _lambda_instance_gpu_count(vcpus)
    key = ("instance", model, variant, gpu_count, price)
    if key in seen:
        return
    rows.append(
        _gpu_row(
            date=_date_from_iso(fetched_at),
            provider="Lambda",
            gpu_model=model,
            gpu_variant=variant,
            billing_type="on-demand",
            commitment="instance; price_per_gpu_hour",
            gpu_count=gpu_count,
            region="global_public_page",
            price_per_gpu_hour=price,
            availability_observed=True,
            provenance=provenance,
        )
    )
    seen.add(key)


def parse_lambda_official_html(
    html: str,
    *,
    run_id: str,
    source_id: str,
    source_url: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    source_type: str = "public_pricing_page",
) -> List[GpuPriceObservation]:
    provenance = _base_kwargs(
        run_id=run_id,
        source_id=source_id,
        source_url=source_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_payload_hash,
        fetched_at=fetched_at,
        source_type=source_type,
        confidence=0.9,
    )
    rows: List[GpuPriceObservation] = []
    seen = set()
    soup = BeautifulSoup(html, "html.parser")

    for tr in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
        if len(cells) >= 4:
            _append_lambda_cluster_row(rows, seen, cells[0], cells[1], cells[2], cells[3], provenance, fetched_at)
        if len(cells) >= 6:
            _append_lambda_instance_row(rows, seen, cells[0], cells[2], cells[5], provenance, fetched_at)

    tokens = _tokens(html)
    for idx in range(0, max(0, len(tokens) - 4)):
        _append_lambda_cluster_row(
            rows,
            seen,
            tokens[idx],
            tokens[idx + 1],
            tokens[idx + 2],
            tokens[idx + 3],
            provenance,
            fetched_at,
        )
    for idx in range(0, max(0, len(tokens) - 5)):
        _append_lambda_instance_row(
            rows,
            seen,
            tokens[idx],
            tokens[idx + 2],
            tokens[idx + 5],
            provenance,
            fetched_at,
        )

    return rows


def _computeprices_variant(html: str, gpu_model: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find(["h1", "title"])
    title_text = title.get_text(" ", strip=True) if title else ""
    if gpu_model == "H100" and "H100 SXM" in title_text:
        return "SXM"
    if gpu_model == "A100" and "A100 SXM" in title_text:
        return "SXM"
    return gpu_model


def _build_computeprices_row(
    *,
    provider: str,
    config: str,
    price: float,
    updated: str,
    gpu_model: str,
    gpu_variant: str,
    source_url: str,
    source_id: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    run_id: str,
) -> Optional[GpuPriceObservation]:
    try:
        quote_date = _quote_date_to_iso(updated)
    except ValueError:
        return None

    quote_age = _quote_age_days(quote_date, fetched_at)
    config_counts = [int(value) for value in re.findall(r"\d+", config)]
    gpu_count = config_counts[0] if config_counts else 1
    config_text = ",".join(f"{count}x" for count in config_counts) if config_counts else "unknown"
    commitment = (
        f"aggregator_quote; config={config_text}; quote_date={quote_date}; "
        f"quote_age_days={quote_age}; availability=listed"
    )
    provenance = _base_kwargs(
        run_id=run_id,
        source_id=source_id,
        source_url=source_url,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_payload_hash,
        fetched_at=fetched_at,
        source_type="aggregator",
        observed_at=f"{quote_date}T00:00:00Z",
        confidence=0.7,
    )
    return _gpu_row(
        date=quote_date,
        provider=provider,
        gpu_model=gpu_model,
        gpu_variant=gpu_variant,
        billing_type="aggregator-public-quote",
        commitment=commitment,
        gpu_count=gpu_count,
        region="unknown",
        price_per_gpu_hour=price,
        availability_observed=True,
        provenance=provenance,
    )


def _parse_computeprices_table_rows(
    html: str,
    *,
    gpu_model: str,
    source_url: str,
    source_id: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    run_id: str,
) -> List[GpuPriceObservation]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[GpuPriceObservation] = []
    gpu_variant = _computeprices_variant(html, gpu_model)
    for tr in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
        if len(cells) < 4 or cells[0].lower() == "provider":
            continue
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", cells[2])
        if not price_match:
            continue
        row = _build_computeprices_row(
            provider=cells[0],
            config=cells[1],
            price=float(price_match.group(1)),
            updated=cells[3],
            gpu_model=gpu_model,
            gpu_variant=gpu_variant,
            source_url=source_url,
            source_id=source_id,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
            fetched_at=fetched_at,
            run_id=run_id,
        )
        if row is not None:
            rows.append(row)
    return rows


def _parse_computeprices_token_rows(
    html: str,
    *,
    gpu_model: str,
    source_url: str,
    source_id: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    run_id: str,
) -> List[GpuPriceObservation]:
    tokens = _tokens(html)
    gpu_variant = _computeprices_variant(html, gpu_model)
    rows: List[GpuPriceObservation] = []
    try:
        start = tokens.index("Source") + 1
    except ValueError:
        return rows

    cursor = start
    while cursor < len(tokens):
        provider_tokens = []
        while cursor < len(tokens):
            if cursor + 1 < len(tokens) and tokens[cursor].replace(",", "").isdigit() and tokens[cursor + 1] in {"×", "x", "X"}:
                break
            if tokens[cursor].startswith("$") or tokens[cursor] in {"About", "Features", "Use Cases", "API"}:
                return rows
            provider_tokens.append(tokens[cursor])
            cursor += 1
        if not provider_tokens or cursor >= len(tokens):
            break

        config_tokens = []
        while cursor + 1 < len(tokens) and tokens[cursor].replace(",", "").isdigit() and tokens[cursor + 1] in {"×", "x", "X"}:
            config_tokens.append(tokens[cursor])
            cursor += 2

        if cursor >= len(tokens):
            break
        price = _parse_money_token(tokens[cursor])
        if price is None:
            break
        cursor += 1
        if cursor < len(tokens) and tokens[cursor].lower() in {"/hr", "/hour"}:
            cursor += 1

        commitment_tokens = []
        while cursor < len(tokens) and not DATE_RE.match(tokens[cursor]):
            commitment_tokens.append(tokens[cursor])
            cursor += 1
        if cursor >= len(tokens):
            break
        updated = tokens[cursor]
        cursor += 1

        config = " x ".join(config_tokens)
        if commitment_tokens:
            config = f"{config} {' '.join(commitment_tokens)}".strip()
        row = _build_computeprices_row(
            provider=" ".join(provider_tokens),
            config=config,
            price=price,
            updated=updated,
            gpu_model=gpu_model,
            gpu_variant=gpu_variant,
            source_url=source_url,
            source_id=source_id,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
            fetched_at=fetched_at,
            run_id=run_id,
        )
        if row is not None:
            rows.append(row)
    return rows


def parse_computeprices_html(
    html: str,
    *,
    gpu_model: str,
    source_url: str,
    source_id: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
    run_id: str,
) -> List[GpuPriceObservation]:
    table_rows = _parse_computeprices_table_rows(
        html,
        gpu_model=gpu_model,
        source_url=source_url,
        source_id=source_id,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_payload_hash,
        fetched_at=fetched_at,
        run_id=run_id,
    )
    if table_rows:
        return table_rows
    return _parse_computeprices_token_rows(
        html,
        gpu_model=gpu_model,
        source_url=source_url,
        source_id=source_id,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_payload_hash,
        fetched_at=fetched_at,
        run_id=run_id,
    )


def _quality_event(
    *,
    run_id: str,
    source: GpuPricingSource,
    code: str,
    message: str,
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
) -> DataQualityEvent:
    return DataQualityEvent(
        event_id=f"{run_id}:{source.source_id}:{code}",
        table_name="production_gpu_prices",
        severity="error",
        message=message,
        affected_key=source.source_id,
        is_blocking=True,
        **_base_kwargs(
            run_id=run_id,
            source_id=source.source_id,
            source_url=source.source_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
            fetched_at=fetched_at,
            source_type=source.source_type,
            is_production_eligible=False,
            confidence=0.0,
            error_code=code,
        ),
    )


def _default_fetcher(url: str, timeout: int) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def _parse_source_html(source: GpuPricingSource, html: str, snapshot_path: str, raw_payload_hash: str, fetched_at: str, run_id: str) -> List[GpuPriceObservation]:
    if source.parser == "runpod":
        return parse_runpod_official_html(
            html,
            run_id=run_id,
            source_id=source.source_id,
            source_url=source.source_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
            fetched_at=fetched_at,
            source_type=source.source_type,
        )
    if source.parser == "lambda":
        return parse_lambda_official_html(
            html,
            run_id=run_id,
            source_id=source.source_id,
            source_url=source.source_url,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
            fetched_at=fetched_at,
            source_type=source.source_type,
        )
    if source.parser == "computeprices" and source.gpu_model:
        return parse_computeprices_html(
            html,
            gpu_model=source.gpu_model,
            source_url=source.source_url,
            source_id=source.source_id,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
            fetched_at=fetched_at,
            run_id=run_id,
        )
    raise ValueError(f"GPU_SOURCE_PARSE_FAILED: unknown parser {source.parser!r} for {source.source_id}")


def collect_gpu_pricing_observations(
    *,
    sources: Sequence[GpuPricingSource] = DEFAULT_GPU_PRICING_SOURCES,
    snapshot_dir: Path = SNAPSHOT_DIR,
    fetcher: Callable[[str, int], str] = _default_fetcher,
    timeout: int = 20,
    run_id: Optional[str] = None,
    fetched_at: Optional[str] = None,
) -> GpuPricingCollectionResult:
    fetched_at = fetched_at or _utc_now_iso()
    run_id = run_id or f"gpu-prices-{_safe_slug(fetched_at)}"
    result = GpuPricingCollectionResult()

    for source in sources:
        try:
            html = fetcher(source.source_url, timeout)
            snapshot_path, raw_hash = _write_snapshot(html, snapshot_dir, source.source_id, fetched_at)
            rows = _parse_source_html(source, html, snapshot_path, raw_hash, fetched_at, run_id)
            if not rows:
                result.quality_events.append(
                    _quality_event(
                        run_id=run_id,
                        source=source,
                        code="GPU_SOURCE_PARSE_FAILED",
                        message=f"GPU_SOURCE_PARSE_FAILED: no pricing rows parsed from {source.source_url}",
                        snapshot_path=snapshot_path,
                        raw_payload_hash=raw_hash,
                        fetched_at=fetched_at,
                    )
                )
            else:
                result.observations.extend(rows)
        except requests.Timeout as exc:
            payload = f"SOURCE_TIMEOUT\nurl={source.source_url}\nerror={exc}\n"
            snapshot_path, raw_hash = _write_snapshot(payload, snapshot_dir, source.source_id, fetched_at, suffix=".error.txt")
            result.quality_events.append(
                _quality_event(
                    run_id=run_id,
                    source=source,
                    code="SOURCE_TIMEOUT",
                    message=f"SOURCE_TIMEOUT: {source.source_url} timed out.",
                    snapshot_path=snapshot_path,
                    raw_payload_hash=raw_hash,
                    fetched_at=fetched_at,
                )
            )
        except Exception as exc:
            payload = f"GPU_SOURCE_PARSE_FAILED\nurl={source.source_url}\nerror={type(exc).__name__}: {exc}\n"
            try:
                snapshot_path, raw_hash = _write_snapshot(payload, snapshot_dir, source.source_id, fetched_at, suffix=".error.txt")
            except Exception:
                snapshot_path, raw_hash = "", _payload_hash(payload)
            result.quality_events.append(
                _quality_event(
                    run_id=run_id,
                    source=source,
                    code="GPU_SOURCE_PARSE_FAILED",
                    message=f"GPU_SOURCE_PARSE_FAILED: {source.source_url}: {type(exc).__name__}: {exc}",
                    snapshot_path=snapshot_path,
                    raw_payload_hash=raw_hash,
                    fetched_at=fetched_at,
                )
            )

    return result


def update_production_gpu_prices(
    *,
    store: Optional[ProductionStore] = None,
    snapshot_dir: Path = SNAPSHOT_DIR,
    timeout: int = 20,
    run_id: Optional[str] = None,
) -> GpuPricingCollectionResult:
    store = store or ProductionStore()
    result = collect_gpu_pricing_observations(
        snapshot_dir=snapshot_dir,
        timeout=timeout,
        run_id=run_id,
    )
    if result.observations:
        store.insert_gpu_prices(result.observations)
    if result.quality_events:
        store.insert_quality_events(result.quality_events)
    return result
