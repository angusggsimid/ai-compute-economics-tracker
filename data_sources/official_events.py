from __future__ import annotations

import hashlib
import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests
import yaml

from company_config import CompanyConfigError, get_company_config
from production_store import DataQualityEvent, OfficialEventObservation, ProductionStore


DEFAULT_YAML_PATH = Path(__file__).resolve().parents[1] / "data" / "manual_official_events.yml"
DEFAULT_SNAPSHOT_DIR = Path("tracker_snapshots") / "official_events"
COLLECTOR_NAME = "manual_sourcebacked_yaml"
SOURCE_UNAVAILABLE_STATUS = {403, 408, 409, 425, 429, 500, 502, 503, 504}
ALLOWED_EVENT_TYPES = {
    "capex_guidance_range",
    "capex_guidance_revision",
    "rpo",
    "capacity_comment",
    "supply_constraint_comment",
    "management_capacity_comment",
}
REQUIRED_SOURCE_PROOF_FIELDS = {
    "source_url",
    "announcement_date",
    "ticker",
    "company",
    "event_type",
    "metric",
    "unit",
    "value",
    "source_excerpt",
    "collector_name",
}
RANGE_VALUE_KEYS = ("low", "high", "previous_low", "previous_high")


@dataclass
class SourceFetchResult:
    status_code: int
    final_url: str
    body: bytes
    content_type: str = ""
    error: Optional[str] = None


@dataclass
class SourceBackedEvent:
    event_id: str
    ticker: str
    company: str
    announcement_date: str
    event_type: str
    metric: str
    unit: str
    source_url: str
    source_excerpt: str
    collector_name: str
    snapshot_path: str
    raw_payload_hash: str


@dataclass
class RejectedOfficialEvent:
    event_id: str
    ticker: str
    source_url: str
    reason: str
    message: str
    snapshot_path: str = ""
    raw_payload_hash: str = ""


@dataclass
class OfficialEventsLoadResult:
    production_events: List[OfficialEventObservation]
    quality_events: List[DataQualityEvent]
    rejected_events: List[RejectedOfficialEvent]
    source_backed_events: List[SourceBackedEvent]


def default_fetcher(url: str) -> SourceFetchResult:
    headers = {
        "User-Agent": os.environ.get(
            "TRACKER_USER_AGENT",
            "ai-compute-tracker/0.1 official-events verifier agg@example.invalid",
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        return SourceFetchResult(
            status_code=response.status_code,
            final_url=response.url,
            body=response.content,
            content_type=response.headers.get("content-type", ""),
        )
    except requests.RequestException as exc:
        return SourceFetchResult(
            status_code=0,
            final_url=url,
            body=f"REQUEST_ERROR: {type(exc).__name__}: {exc}".encode("utf-8", "replace"),
            content_type="text/plain",
            error=str(exc),
        )


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-").lower()
    return slug[:120] or "official-event"


def _normalise_text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", "ignore")
    else:
        text = value
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _contains_proof(body: bytes, source_excerpt: str) -> bool:
    return _normalise_text(source_excerpt) in _normalise_text(body)


def _hash_payload(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def _write_snapshot(
    snapshot_dir: Path,
    event_id: str,
    announcement_date: str,
    ticker: str,
    event_type: str,
    fetch_result: SourceFetchResult,
) -> Tuple[str, str]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    body = fetch_result.body or b""
    digest = _hash_payload(body)
    digest_short = digest.split(":", 1)[1][:12]
    suffix = ".html" if "html" in (fetch_result.content_type or "").lower() else ".txt"
    filename = (
        f"{announcement_date}_{_safe_slug(ticker)}_{_safe_slug(event_type)}_"
        f"{_safe_slug(event_id)}_{digest_short}{suffix}"
    )
    snapshot_path = snapshot_dir / filename
    snapshot_path.write_bytes(body)
    return str(snapshot_path), digest


def _load_yaml_events(yaml_path: Path) -> List[Dict[str, Any]]:
    if not yaml_path.exists():
        raise FileNotFoundError(f"OFFICIAL_EVENTS_YAML_MISSING: {yaml_path}")
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    events = payload.get("events", [])
    if not isinstance(events, list):
        raise ValueError("OFFICIAL_EVENTS_YAML_INVALID: top-level events must be a list.")
    return events


def _missing_source_proof_fields(entry: Dict[str, Any]) -> List[str]:
    missing = []
    for field in sorted(REQUIRED_SOURCE_PROOF_FIELDS):
        if field not in entry or entry.get(field) in (None, ""):
            missing.append(field)
    if entry.get("collector_name") != COLLECTOR_NAME:
        missing.append("collector_name=manual_sourcebacked_yaml")
    return missing


def _value_parts(metric: str, value: Any) -> List[Tuple[str, float]]:
    if isinstance(value, dict):
        parts = []
        for key in RANGE_VALUE_KEYS:
            if key in value and value[key] not in (None, ""):
                parts.append((f"{metric}_{key}", float(value[key])))
        if not parts:
            raise ValueError("range value must contain at least one numeric low/high field")
        return parts
    return [(metric, float(value))]


def _quality_event(
    *,
    event_id: str,
    entry: Dict[str, Any],
    reason: str,
    message: str,
    fetched_at: str,
    snapshot_path: str = "",
    raw_payload_hash: str = "sha256:missing-source-proof",
) -> DataQualityEvent:
    source_url = entry.get("source_url") or f"missing://official-events/{event_id}"
    affected_key = "|".join(
        [
            str(entry.get("ticker") or "UNKNOWN"),
            str(entry.get("event_type") or "UNKNOWN"),
            str(entry.get("metric") or "UNKNOWN"),
            str(entry.get("announcement_date") or "UNKNOWN"),
        ]
    )
    return DataQualityEvent(
        event_id=f"official-events:{event_id}:{reason}",
        table_name="production_official_events",
        severity="warning",
        message=message,
        affected_key=affected_key,
        is_blocking=True,
        run_id=f"official-events-{fetched_at.replace('-', '').replace(':', '')}",
        source_id=f"{COLLECTOR_NAME}:{event_id}",
        source_url=source_url,
        snapshot_path=snapshot_path,
        source_type="official" if entry.get("source_url") else "manual_verified",
        collection_method=COLLECTOR_NAME,
        observed_at=f"{entry.get('announcement_date') or fetched_at[:10]}T00:00:00Z",
        fetched_at=fetched_at,
        raw_payload_hash=raw_payload_hash,
        is_production_eligible=False,
        confidence=0.0,
        error_code=reason,
    )


def _reject(
    result: OfficialEventsLoadResult,
    *,
    event_id: str,
    entry: Dict[str, Any],
    reason: str,
    message: str,
    fetched_at: str,
    snapshot_path: str = "",
    raw_payload_hash: str = "",
) -> None:
    result.rejected_events.append(
        RejectedOfficialEvent(
            event_id=event_id,
            ticker=str(entry.get("ticker") or ""),
            source_url=str(entry.get("source_url") or ""),
            reason=reason,
            message=message,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash,
        )
    )
    result.quality_events.append(
        _quality_event(
            event_id=event_id,
            entry=entry,
            reason=reason,
            message=message,
            fetched_at=fetched_at,
            snapshot_path=snapshot_path,
            raw_payload_hash=raw_payload_hash or "sha256:missing-source-proof",
        )
    )


def _build_observations(
    *,
    entry: Dict[str, Any],
    snapshot_path: str,
    raw_payload_hash: str,
    fetched_at: str,
) -> List[OfficialEventObservation]:
    value_parts = _value_parts(str(entry["metric"]), entry["value"])
    event_id = str(entry["event_id"])
    description = f"{entry['company']}: {entry['source_excerpt']}"
    return [
        OfficialEventObservation(
            ticker=str(entry["ticker"]).upper(),
            announcement_date=str(entry["announcement_date"]),
            event_type=str(entry["event_type"]),
            metric=metric,
            value=value,
            unit=str(entry["unit"]),
            description=description,
            fiscal_period=str(entry.get("fiscal_period") or ""),
            run_id=f"official-events-{fetched_at.replace('-', '').replace(':', '')}",
            source_id=f"{COLLECTOR_NAME}:{event_id}",
            source_url=str(entry["source_url"]),
            snapshot_path=snapshot_path,
            source_type="official",
            collection_method=COLLECTOR_NAME,
            observed_at=f"{entry['announcement_date']}T00:00:00Z",
            fetched_at=fetched_at,
            raw_payload_hash=raw_payload_hash,
            is_production_eligible=True,
            confidence=0.95,
            error_code=None,
        )
        for metric, value in value_parts
    ]


def collect_official_events(
    *,
    yaml_path: Path | str = DEFAULT_YAML_PATH,
    snapshot_dir: Path | str = DEFAULT_SNAPSHOT_DIR,
    fetcher: Optional[Callable[[str], SourceFetchResult]] = None,
    fetched_at: Optional[str] = None,
) -> OfficialEventsLoadResult:
    yaml_path = Path(yaml_path)
    snapshot_dir = Path(snapshot_dir)
    fetcher = fetcher or default_fetcher
    fetched_at = fetched_at or os.environ.get("TRACKER_FETCHED_AT") or _utc_now()

    result = OfficialEventsLoadResult(
        production_events=[],
        quality_events=[],
        rejected_events=[],
        source_backed_events=[],
    )

    for entry in _load_yaml_events(yaml_path):
        event_id = str(entry.get("event_id") or _safe_slug(entry.get("metric") or "event"))
        missing = _missing_source_proof_fields(entry)
        if missing:
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason="MISSING_SOURCE_PROOF",
                message=f"Missing required source-backed fields: {', '.join(missing)}.",
                fetched_at=fetched_at,
            )
            continue

        if entry["event_type"] not in ALLOWED_EVENT_TYPES:
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason="INVALID_EVENT_TYPE",
                message=f"Unsupported official event_type={entry['event_type']!r}.",
                fetched_at=fetched_at,
            )
            continue

        try:
            config = get_company_config(str(entry["ticker"]))
        except CompanyConfigError as exc:
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason="COMPANY_CONFIG_MISSING",
                message=str(exc),
                fetched_at=fetched_at,
            )
            continue
        if config.company_name.lower() != str(entry["company"]).lower():
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason="COMPANY_TICKER_MISMATCH",
                message=f"YAML company={entry['company']!r} does not match config {config.company_name!r}.",
                fetched_at=fetched_at,
            )
            continue

        try:
            _value_parts(str(entry["metric"]), entry["value"])
        except (TypeError, ValueError) as exc:
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason="INVALID_EVENT_VALUE",
                message=f"Official event value must be numeric or a numeric range: {exc}.",
                fetched_at=fetched_at,
            )
            continue

        fetch_result = fetcher(str(entry["source_url"]))
        snapshot_path, raw_payload_hash = _write_snapshot(
            snapshot_dir,
            event_id,
            str(entry["announcement_date"]),
            str(entry["ticker"]),
            str(entry["event_type"]),
            fetch_result,
        )

        if fetch_result.status_code < 200 or fetch_result.status_code >= 300:
            reason = "SOURCE_UNAVAILABLE"
            status = fetch_result.status_code
            if status in SOURCE_UNAVAILABLE_STATUS or status == 0:
                message = f"Official source unavailable during re-fetch: HTTP {status}."
            else:
                message = f"Official source returned unexpected HTTP {status}."
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason=reason,
                message=message,
                fetched_at=fetched_at,
                snapshot_path=snapshot_path,
                raw_payload_hash=raw_payload_hash,
            )
            continue

        if not _contains_proof(fetch_result.body, str(entry["source_excerpt"])):
            _reject(
                result,
                event_id=event_id,
                entry=entry,
                reason="SOURCE_PROOF_NOT_FOUND",
                message="Official page was reachable but the required source_excerpt was not found.",
                fetched_at=fetched_at,
                snapshot_path=snapshot_path,
                raw_payload_hash=raw_payload_hash,
            )
            continue

        result.source_backed_events.append(
            SourceBackedEvent(
                event_id=event_id,
                ticker=str(entry["ticker"]).upper(),
                company=str(entry["company"]),
                announcement_date=str(entry["announcement_date"]),
                event_type=str(entry["event_type"]),
                metric=str(entry["metric"]),
                unit=str(entry["unit"]),
                source_url=str(entry["source_url"]),
                source_excerpt=str(entry["source_excerpt"]),
                collector_name=str(entry["collector_name"]),
                snapshot_path=snapshot_path,
                raw_payload_hash=raw_payload_hash,
            )
        )
        result.production_events.extend(
            _build_observations(
                entry=entry,
                snapshot_path=snapshot_path,
                raw_payload_hash=raw_payload_hash,
                fetched_at=fetched_at,
            )
        )

    return result


def insert_official_events(
    result: OfficialEventsLoadResult,
    store: Optional[ProductionStore] = None,
) -> Dict[str, int]:
    store = store or ProductionStore()
    events_inserted = store.insert_official_events(result.production_events)
    quality_events_inserted = store.insert_quality_events(result.quality_events)
    return {
        "events_inserted": events_inserted,
        "quality_events_inserted": quality_events_inserted,
    }


def collect_and_insert_official_events(
    *,
    yaml_path: Optional[Path | str] = None,
    snapshot_dir: Optional[Path | str] = None,
    store: Optional[ProductionStore] = None,
) -> Tuple[OfficialEventsLoadResult, Dict[str, int]]:
    yaml_path = Path(
        yaml_path
        or os.environ.get("TRACKER_OFFICIAL_EVENTS_YAML")
        or DEFAULT_YAML_PATH
    )
    snapshot_dir = Path(
        snapshot_dir
        or os.environ.get("TRACKER_OFFICIAL_EVENTS_SNAPSHOT_DIR")
        or DEFAULT_SNAPSHOT_DIR
    )
    result = collect_official_events(yaml_path=yaml_path, snapshot_dir=snapshot_dir)
    counts = insert_official_events(result, store=store)
    return result, counts


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_type_counts(events: Iterable[OfficialEventObservation]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for event in events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return counts
