from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from company_config import decision_universe_configs
from production_store import DataQualityEvent, PipelineRun, ProductionStore


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

EVIDENCE_TABLES = (
    "production_gpu_prices",
    "production_capex_actuals",
    "production_official_events",
    "production_public_proxy_prices",
    "production_market_facts",
)
LEGACY_SOURCE_TABLES = (
    "gpu_prices_daily",
    "capex_quarterly",
    "ocpi_daily",
    "capex_guidance",
    "capex_daily_implied",
    "capex_nowcast",
)
FAIL_REASON_CODES = {
    "NO_PRODUCTION_DATA",
    "SEED_ROWS_PRESENT",
    "SOURCE_STALE",
    "CAPEX_COMPANY_MISSING",
    "PRODUCTION_TABLE_QUERY_FAILED",
}
SOURCE_FAILURE_CODES = {
    "GPU_PROVIDER_PARSE_FAILED",
    "SOURCE_TIMEOUT",
    "SEC_SOURCE_UNAVAILABLE",
    "DATA_SOURCE_UNAVAILABLE",
    "SOURCE_UNAVAILABLE",
    "SEC_TAG_NOT_FOUND",
    "PUBLIC_PROXY_SOURCE_MISSING",
    "MISSING_SOURCE_PROOF",
    "SOURCE_PROOF_NOT_FOUND",
}


@dataclass(frozen=True)
class QualityReason:
    table_name: str
    reason_code: str
    severity: str
    message: str
    affected_key: str = ""
    row_count: int = 0
    latest_at: str = ""
    source_url: str = ""
    snapshot_path: str = ""


@dataclass
class QualityGateResult:
    status: str
    reasons: List[QualityReason] = field(default_factory=list)
    table_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 1 if self.status == FAIL else 0

    @property
    def reason_codes(self) -> List[str]:
        return [reason.reason_code for reason in self.reasons]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "table_counts": dict(self.table_counts),
            "reasons": [asdict(reason) for reason in self.reasons],
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text[:10])
            except ValueError:
                return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: Any) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return ""
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _payload_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_slug(value: str) -> str:
    keep = []
    for char in str(value):
        if char.isalnum() or char in "-_.":
            keep.append(char)
        else:
            keep.append("-")
    return "".join(keep).strip("-").lower() or "pipeline-run"


def _write_json_snapshot(snapshot_dir: Path, filename_stem: str, payload: Dict[str, Any]) -> tuple[str, str]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    raw_hash = _payload_hash(payload)
    path = snapshot_dir / f"{_safe_slug(filename_stem)}_{raw_hash.split(':', 1)[1][:12]}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(path), raw_hash


def record_pipeline_run(
    store: ProductionStore,
    *,
    pipeline_name: str,
    status: str,
    rows_loaded: int,
    message: str,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    run_id: Optional[str] = None,
    snapshot_dir: Path | str = Path("tracker_snapshots") / "pipeline_runs",
) -> str:
    started_at = started_at or utc_now_iso()
    completed_at = completed_at or utc_now_iso()
    run_id = run_id or f"{pipeline_name}-{_safe_slug(started_at)}"
    payload = {
        "run_id": run_id,
        "pipeline_name": pipeline_name,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "rows_loaded": int(rows_loaded),
        "message": message,
    }
    snapshot_path, raw_hash = _write_json_snapshot(Path(snapshot_dir), run_id, payload)
    store.insert_pipeline_runs(
        [
            PipelineRun(
                pipeline_name=pipeline_name,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                rows_loaded=int(rows_loaded),
                message=message,
                run_id=run_id,
                source_id=f"pipeline:{pipeline_name}",
                source_url=f"internal://pipeline-runs/{pipeline_name}",
                snapshot_path=snapshot_path,
                source_type="manual_verified",
                collection_method="unavailable_marker",
                observed_at=completed_at,
                fetched_at=completed_at,
                raw_payload_hash=raw_hash,
                is_production_eligible=False,
                confidence=1.0 if status in {PASS, "SUCCESS"} else 0.5,
                error_code=None if status in {PASS, "SUCCESS"} else status,
            )
        ]
    )
    return run_id


def record_quality_event(
    store: ProductionStore,
    *,
    table_name: str,
    reason_code: str,
    message: str,
    affected_key: str,
    source_id: str,
    source_url: str,
    snapshot_path: str = "",
    run_id: Optional[str] = None,
    severity: str = "warning",
    source_type: str = "public_pricing_page",
    collection_method: str = "html_parse",
    fetched_at: Optional[str] = None,
    is_blocking: bool = True,
) -> str:
    fetched_at = fetched_at or utc_now_iso()
    run_id = run_id or f"quality-{_safe_slug(fetched_at)}"
    event_id = f"{run_id}:{source_id}:{reason_code}"
    marker = {
        "event_id": event_id,
        "table_name": table_name,
        "reason_code": reason_code,
        "message": message,
        "affected_key": affected_key,
        "source_id": source_id,
        "source_url": source_url,
        "fetched_at": fetched_at,
    }
    raw_hash = _payload_hash(marker)
    if not snapshot_path:
        snapshot_path = f"unavailable_marker://{source_id}/{reason_code}"
    store.insert_quality_events(
        [
            DataQualityEvent(
                event_id=event_id,
                table_name=table_name,
                severity=severity.lower(),
                message=message,
                affected_key=affected_key,
                is_blocking=is_blocking,
                run_id=run_id,
                source_id=source_id,
                source_url=source_url,
                snapshot_path=snapshot_path,
                source_type=source_type,
                collection_method=collection_method,
                observed_at=fetched_at,
                fetched_at=fetched_at,
                raw_payload_hash=raw_hash,
                is_production_eligible=False,
                confidence=0.0,
                error_code=reason_code,
            )
        ]
    )
    return event_id


def _table_counts(conn) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table_name in (
        "production_gpu_prices",
        "production_capex_actuals",
        "production_official_events",
        "production_public_proxy_prices",
        "production_market_facts",
        "production_data_quality_events",
        "production_pipeline_runs",
    ):
        counts[table_name] = int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] or 0)
    return counts


def _eligible_evidence_count(conn) -> int:
    total = 0
    for table_name in EVIDENCE_TABLES:
        total += int(
            conn.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE is_production_eligible = TRUE"
            ).fetchone()[0]
            or 0
        )
    return total


def _production_seed_reasons(conn) -> List[QualityReason]:
    reasons: List[QualityReason] = []
    for table_name in EVIDENCE_TABLES:
        rows = conn.execute(
            f"""
            SELECT LOWER(COALESCE(source_type, '')) AS source_type, COUNT(*)
            FROM {table_name}
            WHERE LOWER(COALESCE(source_type, '')) IN ('seed', 'mock')
            GROUP BY 1
            """
        ).fetchall()
        for source_type, row_count in rows:
            reasons.append(
                QualityReason(
                    table_name=table_name,
                    reason_code="SEED_ROWS_PRESENT",
                    severity=FAIL,
                    row_count=int(row_count),
                    affected_key=str(source_type),
                    message=(
                        f"{table_name} has seed/mock rows in production evidence; "
                        "production decision must not use them."
                    ),
                )
            )
    return reasons


def _legacy_seed_reasons(conn) -> List[QualityReason]:
    reasons: List[QualityReason] = []
    for table_name in LEGACY_SOURCE_TABLES:
        rows = conn.execute(
            f"""
            SELECT COALESCE(CAST(source AS VARCHAR), 'legacy_unclassified') AS source_value, COUNT(*)
            FROM {table_name}
            WHERE LOWER(COALESCE(CAST(source AS VARCHAR), '')) LIKE '%seed%'
               OR LOWER(COALESCE(CAST(source AS VARCHAR), '')) IN ('direct_pricing', 'composite_public')
            GROUP BY 1
            """
        ).fetchall()
        for source_value, row_count in rows:
            reasons.append(
                QualityReason(
                    table_name=table_name,
                    reason_code="LEGACY_SEED_ROWS_PRESENT",
                    severity=WARN,
                    row_count=int(row_count),
                    affected_key=str(source_value),
                    message=(
                        f"{table_name} contains legacy/demo seed rows; ignored by production gate."
                    ),
                )
            )
    return reasons


def _gpu_freshness_reasons(conn, as_of_dt: datetime) -> List[QualityReason]:
    row = conn.execute(
        """
        SELECT COUNT(*), MAX(fetched_at), COUNT(DISTINCT source_id)
        FROM production_gpu_prices
        WHERE is_production_eligible = TRUE
        """
    ).fetchone()
    row_count = int(row[0] or 0)
    latest = _parse_timestamp(row[1])
    source_count = int(row[2] or 0)
    if row_count == 0:
        return [
            QualityReason(
                table_name="production_gpu_prices",
                reason_code="SOURCE_STALE",
                severity=FAIL,
                row_count=0,
                affected_key="gpu-prices",
                message="No eligible production GPU price row exists.",
            )
        ]
    if latest is None or latest < as_of_dt - timedelta(days=3):
        return [
            QualityReason(
                table_name="production_gpu_prices",
                reason_code="SOURCE_STALE",
                severity=FAIL,
                row_count=row_count,
                latest_at=_format_timestamp(latest),
                affected_key="gpu-prices",
                message=(
                    "No production GPU price source was fetched within 3 days; "
                    f"eligible_sources={source_count}."
                ),
            )
        ]
    return []


def _capex_coverage_reasons(conn) -> List[QualityReason]:
    reasons: List[QualityReason] = []
    for config in decision_universe_configs():
        row = conn.execute(
            """
            SELECT COUNT(*), MAX(period_end), MAX(fetched_at)
            FROM production_capex_actuals
            WHERE is_production_eligible = TRUE
              AND source_type = 'official'
              AND ticker = ?
            """,
            [config.ticker],
        ).fetchone()
        row_count = int(row[0] or 0)
        if row_count == 0:
            reasons.append(
                QualityReason(
                    table_name="production_capex_actuals",
                    reason_code="CAPEX_COMPANY_MISSING",
                    severity=FAIL,
                    row_count=0,
                    affected_key=config.ticker,
                    message=f"{config.ticker} latest official CAPEX actual is missing.",
                )
            )
    return reasons


def _official_event_reasons(conn) -> List[QualityReason]:
    reasons: List[QualityReason] = []
    for config in decision_universe_configs():
        row = conn.execute(
            """
            SELECT COUNT(*), MAX(announcement_date), MAX(fetched_at)
            FROM production_official_events
            WHERE is_production_eligible = TRUE
              AND source_type = 'official'
              AND ticker = ?
            """,
            [config.ticker],
        ).fetchone()
        row_count = int(row[0] or 0)
        if row_count == 0:
            reasons.append(
                QualityReason(
                    table_name="production_official_events",
                    reason_code="OFFICIAL_EVENT_MISSING",
                    severity=WARN,
                    row_count=0,
                    affected_key=config.ticker,
                    message=(
                        f"{config.ticker} has no source-backed guidance/RPO/official event; "
                        "do not synthesize guidance."
                    ),
                )
            )
    return reasons


def _official_source_failure_is_superseded(conn, affected_key: str, fetched_at: Any) -> bool:
    ticker = str(affected_key or "").split("|", 1)[0].strip().upper()
    if not ticker:
        return False
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM production_official_events
        WHERE is_production_eligible = TRUE
          AND source_type = 'official'
          AND ticker = ?
          AND fetched_at >= ?
        """,
        [ticker, fetched_at],
    ).fetchone()
    return int(row[0] or 0) > 0


def _source_failure_reasons(conn) -> List[QualityReason]:
    rows = conn.execute(
        """
        SELECT table_name, error_code, severity, message, affected_key,
               source_type, fetched_at, source_url, snapshot_path, COUNT(*) AS row_count
        FROM production_data_quality_events
        WHERE error_code IS NOT NULL
          AND error_code <> ''
        GROUP BY table_name, error_code, severity, message, affected_key,
                 source_type, fetched_at, source_url, snapshot_path
        ORDER BY fetched_at DESC, table_name, error_code
        """
    ).fetchall()
    reasons: List[QualityReason] = []
    for row in rows:
        table_name, error_code, severity, message, affected_key, source_type, fetched_at, source_url, snapshot_path, row_count = row
        code = str(error_code)
        if code not in SOURCE_FAILURE_CODES:
            continue
        if (
            str(table_name) == "production_official_events"
            and code in {"SOURCE_UNAVAILABLE", "SOURCE_PROOF_NOT_FOUND"}
            and _official_source_failure_is_superseded(conn, str(affected_key or ""), fetched_at)
        ):
            continue
        mapped_severity = WARN
        if str(source_type) == "licensed_unavailable" and code == "DATA_SOURCE_UNAVAILABLE":
            mapped_severity = WARN
        reasons.append(
            QualityReason(
                table_name=str(table_name),
                reason_code=code,
                severity=mapped_severity,
                row_count=int(row_count or 0),
                affected_key=str(affected_key or ""),
                latest_at=_format_timestamp(fetched_at),
                source_url=str(source_url or ""),
                snapshot_path=str(snapshot_path or ""),
                message=str(message or f"{code} recorded by source collector."),
            )
        )
    return reasons


def _gate_status(reasons: Iterable[QualityReason]) -> str:
    severities = {reason.severity for reason in reasons}
    if FAIL in severities:
        return FAIL
    if WARN in severities:
        return WARN
    return PASS


def evaluate_quality_gate(database: Any = None, *, db_path: Optional[str] = None, as_of: Optional[Any] = None) -> QualityGateResult:
    if database is None:
        from tracker_v2 import DB_PATH, Database

        database = Database(db_path or DB_PATH)

    as_of_dt = _parse_timestamp(as_of or utc_now_iso()) or datetime.now(timezone.utc)
    conn = database.get_connection()
    reasons: List[QualityReason] = []
    try:
        counts = _table_counts(conn)
        eligible_evidence_rows = _eligible_evidence_count(conn)
        if eligible_evidence_rows == 0:
            reasons.append(
                QualityReason(
                    table_name="production_*",
                    reason_code="NO_PRODUCTION_DATA",
                    severity=FAIL,
                    row_count=0,
                    affected_key="production_evidence",
                    message="No eligible production evidence rows exist.",
                )
            )

        reasons.extend(_production_seed_reasons(conn))
        reasons.extend(_legacy_seed_reasons(conn))
        reasons.extend(_gpu_freshness_reasons(conn, as_of_dt))
        reasons.extend(_capex_coverage_reasons(conn))
        reasons.extend(_official_event_reasons(conn))
        reasons.extend(_source_failure_reasons(conn))
    except Exception as exc:
        counts = {}
        reasons.append(
            QualityReason(
                table_name="production_*",
                reason_code="PRODUCTION_TABLE_QUERY_FAILED",
                severity=FAIL,
                affected_key=type(exc).__name__,
                message=str(exc),
            )
        )
    finally:
        conn.close()

    return QualityGateResult(status=_gate_status(reasons), reasons=reasons, table_counts=counts)


def format_quality_gate(result: QualityGateResult) -> str:
    lines = [
        f"quality_gate={result.status}",
        f"exit_code={result.exit_code}",
        "table_counts:",
    ]
    for table_name, row_count in sorted(result.table_counts.items()):
        lines.append(f"   {table_name}: {row_count}")
    lines.append("reason_table:")
    if not result.reasons:
        lines.append("   (none)")
    else:
        for reason in result.reasons:
            latest = f" | latest={reason.latest_at}" if reason.latest_at else ""
            rows = f" | rows={reason.row_count}" if reason.row_count else ""
            source = f" | source={reason.source_url}" if reason.source_url else ""
            lines.append(
                f"   {reason.severity} | {reason.table_name} | {reason.reason_code} | "
                f"{reason.affected_key}{rows}{latest}{source} | {reason.message}"
            )
    return "\n".join(lines)
