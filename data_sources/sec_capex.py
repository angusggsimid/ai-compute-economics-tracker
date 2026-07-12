from __future__ import annotations

import json
import os
import re
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

from company_config import CompanyConfig, decision_universe_configs
from production_store import CapexActualObservation, DataQualityEvent, ProductionStore


SEC_TAG_NOT_FOUND = "SEC_TAG_NOT_FOUND"
SEC_SOURCE_UNAVAILABLE = "SEC_SOURCE_UNAVAILABLE"
SEC_PERIOD_AMBIGUOUS = "SEC_PERIOD_AMBIGUOUS"

SEC_CAPEX_SNAPSHOT_DIR = Path("tracker_snapshots") / "sec_capex"
DEFAULT_SEC_USER_AGENT = (
    "AI-Compute-Scarcity-Tracker/2.0 contact: agg@example.com"
)


class SecCompanyfactsUnavailable(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int], source_url: str):
        super().__init__(message)
        self.status_code = status_code
        self.source_url = source_url


@dataclass(frozen=True)
class SecCapexFact:
    raw: Dict[str, Any]
    raw_unit: str
    raw_value: float
    period_start: str
    period_end: str
    fiscal_year: int
    fiscal_period: str
    accession_no: str
    filed_at: str
    form_type: str


@dataclass
class SecCapexCollectionResult:
    actuals: List[CapexActualObservation]
    quality_events: List[DataQualityEvent]
    trend_availability: Dict[str, Dict[str, Any]]


class SecCompanyfactsClient:
    def __init__(
        self,
        user_agent: Optional[str] = None,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
    ):
        self.user_agent = user_agent or os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT
        self._validate_user_agent(self.user_agent)
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    @staticmethod
    def _validate_user_agent(user_agent: str) -> None:
        value = (user_agent or "").strip()
        lower = value.lower()
        if not value or "python-requests" in lower:
            raise ValueError("SEC_USER_AGENT_REQUIRED: configure a clear SEC User-Agent.")
        if "@" not in value and "contact" not in lower:
            raise ValueError(
                "SEC_USER_AGENT_REQUIRED: SEC User-Agent must identify the app and contact."
            )

    def fetch_companyfacts(self, config: CompanyConfig) -> Dict[str, Any]:
        url = companyfacts_url(config.cik)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SecCompanyfactsUnavailable(
                f"SEC request failed for {config.ticker}: {exc}",
                status_code=None,
                source_url=url,
            ) from exc

        if response.status_code in (403, 429):
            raise SecCompanyfactsUnavailable(
                f"SEC_SOURCE_UNAVAILABLE: HTTP {response.status_code} for {config.ticker}",
                status_code=response.status_code,
                source_url=url,
            )
        if response.status_code >= 400:
            raise SecCompanyfactsUnavailable(
                f"SEC request failed: HTTP {response.status_code} for {config.ticker}",
                status_code=response.status_code,
                source_url=url,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SecCompanyfactsUnavailable(
                f"SEC response was not valid JSON for {config.ticker}",
                status_code=response.status_code,
                source_url=url,
            ) from exc


def normalize_cik(cik: str) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    return digits.zfill(10)


def companyfacts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json"


def hash_raw_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def collect_sec_capex_actuals(
    configs: Optional[Iterable[CompanyConfig]] = None,
    client: Optional[Any] = None,
    snapshot_dir: Path = SEC_CAPEX_SNAPSHOT_DIR,
    run_id: Optional[str] = None,
    fetched_at: Optional[str] = None,
) -> SecCapexCollectionResult:
    run_id = run_id or f"sec-capex-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    fetched_at = fetched_at or utc_now_iso()
    configs = list(configs) if configs is not None else decision_universe_configs()
    client = client if client is not None else SecCompanyfactsClient()

    actuals: List[CapexActualObservation] = []
    quality_events: List[DataQualityEvent] = []
    trend_availability: Dict[str, Dict[str, Any]] = {}

    for config in configs:
        source_url = companyfacts_url(config.cik)
        try:
            payload = client.fetch_companyfacts(config)
        except SecCompanyfactsUnavailable as exc:
            error_payload = {
                "ticker": config.ticker,
                "cik": normalize_cik(config.cik),
                "source_url": exc.source_url or source_url,
                "status_code": exc.status_code,
                "error": str(exc),
            }
            raw_hash = hash_raw_payload(error_payload)
            snapshot_path = write_sec_capex_snapshot(
                snapshot_dir=snapshot_dir,
                config=config,
                raw_payload=error_payload,
                raw_payload_hash=raw_hash,
                fetched_at=fetched_at,
                selected_fact=None,
                metadata_extra={"error_code": SEC_SOURCE_UNAVAILABLE},
            )
            quality_events.append(
                build_quality_event(
                    config=config,
                    error_code=SEC_SOURCE_UNAVAILABLE,
                    message=(
                        f"{SEC_SOURCE_UNAVAILABLE}: HTTP {exc.status_code} for "
                        f"{config.ticker}; retry later and do not synthesize CAPEX."
                    ),
                    run_id=run_id,
                    fetched_at=fetched_at,
                    snapshot_path=snapshot_path,
                    raw_payload_hash=raw_hash,
                    source_url=exc.source_url or source_url,
                )
            )
            trend_availability[config.ticker] = trend_summary(0)
            continue

        parsed = parse_companyfacts_capex(
            config=config,
            payload=payload,
            snapshot_dir=snapshot_dir,
            run_id=run_id,
            fetched_at=fetched_at,
        )
        if parsed.actuals:
            actuals.extend(parsed.actuals)
        quality_events.extend(parsed.quality_events)
        trend_availability[config.ticker] = parsed.trend_availability.get(
            config.ticker,
            trend_summary(0),
        )

    return SecCapexCollectionResult(
        actuals=actuals,
        quality_events=quality_events,
        trend_availability=trend_availability,
    )


def parse_companyfacts_capex(
    config: CompanyConfig,
    payload: Dict[str, Any],
    snapshot_dir: Path,
    run_id: str,
    fetched_at: str,
) -> SecCapexCollectionResult:
    raw_hash = hash_raw_payload(payload)
    facts = extract_capex_facts(payload, config.capex_xbrl_tag)

    if not facts:
        snapshot_path = write_sec_capex_snapshot(
            snapshot_dir=snapshot_dir,
            config=config,
            raw_payload=payload,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            selected_fact=None,
            metadata_extra={
                "error_code": SEC_TAG_NOT_FOUND,
                "candidate_capex_tags": candidate_capex_tags(payload),
            },
        )
        return SecCapexCollectionResult(
            actuals=[],
            quality_events=[
                build_quality_event(
                    config=config,
                    error_code=SEC_TAG_NOT_FOUND,
                    message=(
                        f"{SEC_TAG_NOT_FOUND}: {config.ticker} CIK {config.cik} "
                        f"does not contain tag {config.capex_xbrl_tag}."
                    ),
                    run_id=run_id,
                    fetched_at=fetched_at,
                    snapshot_path=snapshot_path,
                    raw_payload_hash=raw_hash,
                    source_url=companyfacts_url(config.cik),
                )
            ],
            trend_availability={config.ticker: trend_summary(0)},
        )

    selected = select_latest_capex_fact(facts)
    if selected is None:
        snapshot_path = write_sec_capex_snapshot(
            snapshot_dir=snapshot_dir,
            config=config,
            raw_payload=payload,
            raw_payload_hash=raw_hash,
            fetched_at=fetched_at,
            selected_fact=None,
            metadata_extra={"error_code": SEC_PERIOD_AMBIGUOUS},
        )
        return SecCapexCollectionResult(
            actuals=[],
            quality_events=[
                build_quality_event(
                    config=config,
                    error_code=SEC_PERIOD_AMBIGUOUS,
                    message=(
                        f"{SEC_PERIOD_AMBIGUOUS}: {config.ticker} facts lack enough "
                        "period, filing, or value fields for production CAPEX."
                    ),
                    run_id=run_id,
                    fetched_at=fetched_at,
                    snapshot_path=snapshot_path,
                    raw_payload_hash=raw_hash,
                    source_url=companyfacts_url(config.cik),
                )
            ],
            trend_availability={config.ticker: trend_summary(0)},
        )

    quarter_count = count_latest_sequential_quarters(facts)
    snapshot_path = write_sec_capex_snapshot(
        snapshot_dir=snapshot_dir,
        config=config,
        raw_payload=payload,
        raw_payload_hash=raw_hash,
        fetched_at=fetched_at,
        selected_fact=selected,
        metadata_extra={
            "quarter_count_available": quarter_count,
            "raw_unit": selected.raw_unit,
            "raw_value": selected.raw_value,
        },
    )
    actual = build_capex_observation(
        config=config,
        fact=selected,
        run_id=run_id,
        fetched_at=fetched_at,
        snapshot_path=snapshot_path,
        raw_payload_hash=raw_hash,
    )
    return SecCapexCollectionResult(
        actuals=[actual],
        quality_events=[],
        trend_availability={config.ticker: trend_summary(quarter_count)},
    )


def extract_capex_facts(payload: Dict[str, Any], xbrl_tag: str) -> List[SecCapexFact]:
    tag_payload = (
        payload.get("facts", {})
        .get("us-gaap", {})
        .get(xbrl_tag)
    )
    if not tag_payload:
        return []

    facts: List[SecCapexFact] = []
    for raw_unit, rows in tag_payload.get("units", {}).items():
        for row in rows:
            fact = build_fact(row, raw_unit)
            if fact is not None:
                facts.append(fact)
    return facts


def build_fact(row: Dict[str, Any], raw_unit: str) -> Optional[SecCapexFact]:
    required = ("start", "end", "val", "accn", "fy", "fp", "form", "filed")
    if any(row.get(field) in (None, "") for field in required):
        return None
    try:
        raw_value = float(row["val"])
        fiscal_year = int(row["fy"])
    except (TypeError, ValueError):
        return None

    fp = str(row["fp"]).strip().upper()
    fiscal_period = f"FY{fiscal_year}" if fp == "FY" else f"FY{fiscal_year} {fp}"
    return SecCapexFact(
        raw=dict(row),
        raw_unit=raw_unit,
        raw_value=raw_value,
        period_start=str(row["start"]),
        period_end=str(row["end"]),
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        accession_no=str(row["accn"]),
        filed_at=str(row["filed"]),
        form_type=str(row["form"]),
    )


def select_latest_capex_fact(facts: List[SecCapexFact]) -> Optional[SecCapexFact]:
    if not facts:
        return None
    return sorted(
        facts,
        key=lambda fact: (
            parse_date(fact.period_end),
            is_quarter_fact(fact),
            parse_date(fact.filed_at),
            parse_date(fact.period_start),
        ),
    )[-1]


def count_latest_sequential_quarters(facts: List[SecCapexFact]) -> int:
    by_end: Dict[date, SecCapexFact] = {}
    for fact in facts:
        if not is_quarter_fact(fact):
            continue
        end = parse_date(fact.period_end)
        existing = by_end.get(end)
        if existing is None or parse_date(fact.filed_at) >= parse_date(existing.filed_at):
            by_end[end] = fact

    quarter_ends = sorted(by_end)
    if not quarter_ends:
        return 0

    count = 1
    latest = quarter_ends[-1]
    for previous in reversed(quarter_ends[:-1]):
        gap = (latest - previous).days
        if 80 <= gap <= 100:
            count += 1
            latest = previous
            continue
        break
    return count


def trend_summary(sequential_quarter_count: int) -> Dict[str, Any]:
    return {
        "sequential_quarter_count": sequential_quarter_count,
        "can_evaluate_trend": sequential_quarter_count >= 4,
        "trend_label": None,
    }


def build_capex_observation(
    config: CompanyConfig,
    fact: SecCapexFact,
    run_id: str,
    fetched_at: str,
    snapshot_path: Path,
    raw_payload_hash: str,
) -> CapexActualObservation:
    return CapexActualObservation(
        ticker=config.ticker,
        company=config.company_name,
        period_start=fact.period_start,
        period_end=fact.period_end,
        fiscal_period=fact.fiscal_period,
        fiscal_year=fact.fiscal_year,
        xbrl_tag=config.capex_xbrl_tag,
        accession_no=fact.accession_no,
        capex_value=round(abs(fact.raw_value) / 1_000_000_000, 6),
        unit="USD_B",
        filed_at=fact.filed_at,
        form_type=fact.form_type,
        run_id=run_id,
        source_id=source_id(config),
        source_url=companyfacts_url(config.cik),
        snapshot_path=str(snapshot_path),
        source_type="official",
        collection_method="sec_companyfacts_api",
        observed_at=f"{fact.filed_at}T00:00:00Z",
        fetched_at=fetched_at,
        raw_payload_hash=raw_payload_hash,
        is_production_eligible=True,
        confidence=1.0,
        error_code=None,
    )


def build_quality_event(
    config: CompanyConfig,
    error_code: str,
    message: str,
    run_id: str,
    fetched_at: str,
    snapshot_path: Path,
    raw_payload_hash: str,
    source_url: str,
) -> DataQualityEvent:
    event_suffix = raw_payload_hash.replace("sha256:", "")[:12]
    return DataQualityEvent(
        event_id=f"{run_id}:{config.ticker}:{error_code}:{event_suffix}",
        table_name="production_capex_actuals",
        severity="error",
        message=message,
        affected_key=f"{config.ticker}:{normalize_cik(config.cik)}:{config.capex_xbrl_tag}",
        is_blocking=True,
        run_id=run_id,
        source_id=source_id(config),
        source_url=source_url,
        snapshot_path=str(snapshot_path),
        source_type="official",
        collection_method="sec_companyfacts_api",
        observed_at=fetched_at,
        fetched_at=fetched_at,
        raw_payload_hash=raw_payload_hash,
        is_production_eligible=False,
        confidence=0.0,
        error_code=error_code,
    )


def update_sec_capex_actuals(
    store: Optional[ProductionStore] = None,
    configs: Optional[Iterable[CompanyConfig]] = None,
    client: Optional[Any] = None,
    snapshot_dir: Path = SEC_CAPEX_SNAPSHOT_DIR,
    run_id: Optional[str] = None,
    fetched_at: Optional[str] = None,
) -> SecCapexCollectionResult:
    store = store if store is not None else ProductionStore()
    result = collect_sec_capex_actuals(
        configs=configs,
        client=client,
        snapshot_dir=snapshot_dir,
        run_id=run_id,
        fetched_at=fetched_at,
    )
    store.insert_capex_actuals(result.actuals)
    store.insert_quality_events(result.quality_events)
    return result


def write_sec_capex_snapshot(
    snapshot_dir: Path,
    config: CompanyConfig,
    raw_payload: Dict[str, Any],
    raw_payload_hash: str,
    fetched_at: str,
    selected_fact: Optional[SecCapexFact],
    metadata_extra: Optional[Dict[str, Any]] = None,
) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = re.sub(r"[^0-9A-Za-z]+", "-", fetched_at).strip("-")
    hash_suffix = raw_payload_hash.replace("sha256:", "")[:12]
    path = snapshot_dir / f"{config.ticker}_{normalize_cik(config.cik)}_{safe_ts}_{hash_suffix}.json"
    metadata: Dict[str, Any] = {
        "ticker": config.ticker,
        "company": config.company_name,
        "cik": normalize_cik(config.cik),
        "xbrl_tag": config.capex_xbrl_tag,
        "source_url": companyfacts_url(config.cik),
        "fetched_at": fetched_at,
        "raw_payload_hash": raw_payload_hash,
    }
    if selected_fact is not None:
        metadata.update({
            "raw_unit": selected_fact.raw_unit,
            "raw_value": selected_fact.raw_value,
        })
    if metadata_extra:
        metadata.update(metadata_extra)

    snapshot = {
        "metadata": metadata,
        "selected_fact": selected_fact.raw if selected_fact is not None else None,
        "raw_companyfacts": raw_payload,
    }
    path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def candidate_capex_tags(payload: Dict[str, Any]) -> List[str]:
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    return sorted(
        tag
        for tag in us_gaap
        if "PaymentsToAcquire" in tag or "CapitalExpenditure" in tag
    )


def source_id(config: CompanyConfig) -> str:
    return f"sec-companyfacts-CIK{normalize_cik(config.cik)}-{config.capex_xbrl_tag}"


def is_quarter_fact(fact: SecCapexFact) -> bool:
    try:
        duration = (parse_date(fact.period_end) - parse_date(fact.period_start)).days + 1
    except ValueError:
        return False
    return 75 <= duration <= 110 and " Q" in fact.fiscal_period


def parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])
