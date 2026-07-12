from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from data_quality import FAIL, EVIDENCE_TABLES, QualityGateResult, evaluate_quality_gate
from decision_engine import DecisionEngine, DecisionResult


REPORT_UNCITED_VALUE = "REPORT_UNCITED_VALUE"


class ReportGenerationError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class ProductionDecisionBriefResult:
    content: str
    output_path: Optional[Path]
    quality_gate: QualityGateResult
    decision: Optional[DecisionResult]

    @property
    def exit_code(self) -> int:
        return self.quality_gate.exit_code


def generate_production_decision_brief(
    database: Any,
    *,
    output_dir: Path | str = Path("tracker_data"),
    as_of: Optional[Any] = None,
    write: bool = True,
) -> ProductionDecisionBriefResult:
    as_of_dt = _parse_datetime(as_of) or datetime.now(timezone.utc)
    as_of_iso = _format_datetime(as_of_dt)
    quality_gate = evaluate_quality_gate(database, as_of=as_of_iso)

    if quality_gate.status == FAIL:
        content = _render_failed_quality_brief(database, quality_gate, as_of_iso)
        output_path = _write_report(content, output_dir, as_of_dt) if write else None
        return ProductionDecisionBriefResult(
            content=content,
            output_path=output_path,
            quality_gate=quality_gate,
            decision=None,
        )

    decision = DecisionEngine(database).evaluate(as_of=as_of_iso)
    tables = _load_evidence_tables(database)
    _validate_evidence_citations(tables)
    content = _render_source_backed_brief(
        quality_gate=quality_gate,
        decision=decision,
        tables=tables,
        as_of_iso=as_of_iso,
    )
    output_path = _write_report(content, output_dir, as_of_dt) if write else None
    return ProductionDecisionBriefResult(
        content=content,
        output_path=output_path,
        quality_gate=quality_gate,
        decision=decision,
    )


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        value = value.to_pydatetime()
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
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_report(content: str, output_dir: Path | str, as_of_dt: datetime) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = as_of_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}-production-source-backed-decision-brief.md"
    path.write_text(content, encoding="utf-8")
    return path


def _load_evidence_tables(database: Any) -> Dict[str, pd.DataFrame]:
    conn = database.get_connection()
    try:
        return {
            "gpu_prices": conn.execute(
                """
                SELECT date, provider, gpu_model, gpu_variant, billing_type,
                       commitment, gpu_count, region, price_per_gpu_hour,
                       currency, availability_observed, source_type, source_id,
                       source_url, snapshot_path, observed_at, fetched_at
                FROM production_gpu_prices
                WHERE is_production_eligible = TRUE
                ORDER BY date DESC, source_type DESC, provider, gpu_model, gpu_variant,
                         billing_type, price_per_gpu_hour
                """
            ).df(),
            "capex_actuals": conn.execute(
                """
                SELECT ticker, company, fiscal_period, fiscal_year, period_start,
                       period_end, capex_value, unit, xbrl_tag, accession_no,
                       filed_at, form_type, source_type, source_id, source_url,
                       snapshot_path, observed_at, fetched_at
                FROM production_capex_actuals
                WHERE is_production_eligible = TRUE
                  AND source_type = 'official'
                ORDER BY ticker, period_end DESC, accession_no
                """
            ).df(),
            "official_events": conn.execute(
                """
                SELECT ticker, announcement_date, event_type, metric, value,
                       unit, description, fiscal_period, source_type, source_id,
                       source_url, snapshot_path, observed_at, fetched_at
                FROM production_official_events
                WHERE is_production_eligible = TRUE
                  AND source_type = 'official'
                ORDER BY announcement_date DESC, ticker, event_type, metric
                """
            ).df(),
            "public_proxy_prices": conn.execute(
                """
                SELECT date, provider, proxy_name, metric, value, unit, gpu_model,
                       region, source_type, source_id, source_url, snapshot_path,
                       observed_at, fetched_at
                FROM production_public_proxy_prices
                WHERE is_production_eligible = TRUE
                ORDER BY date DESC, provider, proxy_name, metric
                """
            ).df(),
        }
    finally:
        conn.close()


def _validate_evidence_citations(tables: Dict[str, pd.DataFrame]) -> None:
    numeric_fields = {
        "gpu_prices": ["price_per_gpu_hour"],
        "capex_actuals": ["capex_value"],
        "official_events": ["value"],
        "public_proxy_prices": ["value"],
    }
    key_fields = {
        "gpu_prices": ["date", "provider", "gpu_model", "gpu_variant", "billing_type"],
        "capex_actuals": ["ticker", "fiscal_period", "period_end", "accession_no"],
        "official_events": ["ticker", "announcement_date", "event_type", "metric"],
        "public_proxy_prices": ["date", "provider", "proxy_name", "metric"],
    }
    for table_name, df in tables.items():
        fields = numeric_fields.get(table_name, [])
        for _, row in df.iterrows():
            if not any(_has_numeric_value(row.get(field)) for field in fields):
                continue
            if _citation(row):
                continue
            key = "|".join(str(row.get(field, "")) for field in key_fields.get(table_name, []))
            raise ReportGenerationError(
                REPORT_UNCITED_VALUE,
                f"{table_name} row has numeric evidence without source_url or snapshot_path: {key}",
            )


def _has_numeric_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip()
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def _citation(row: Any) -> str:
    source_url = str(row.get("source_url", "") or "").strip()
    snapshot_path = str(row.get("snapshot_path", "") or "").strip()
    if source_url:
        return source_url
    return snapshot_path


def _render_source_backed_brief(
    *,
    quality_gate: QualityGateResult,
    decision: DecisionResult,
    tables: Dict[str, pd.DataFrame],
    as_of_iso: str,
) -> str:
    lines: List[str] = [
        "# Production Source-Backed Decision Brief",
        "",
        "source-backed decision",
        f"as_of={as_of_iso}",
        "",
    ]
    _append_quality_section(lines, quality_gate)
    _append_decision_section(lines, decision)
    _append_gpu_table(lines, tables["gpu_prices"])
    _append_capex_event_tables(lines, tables["capex_actuals"], tables["official_events"])
    _append_missing_and_failed_sources(lines, quality_gate, decision)
    _append_investment_implication(lines, quality_gate, decision)
    _append_legacy_note(lines)
    return "\n".join(lines).rstrip() + "\n"


def _render_failed_quality_brief(database: Any, quality_gate: QualityGateResult, as_of_iso: str) -> str:
    seed_status = _seed_only_status(database, quality_gate)
    lines: List[str] = [
        "# Production Source-Backed Decision Brief",
        "",
        f"as_of={as_of_iso}",
        "",
    ]
    _append_quality_section(lines, quality_gate)
    if seed_status:
        lines.extend([seed_status, ""])
    lines.extend(
        [
            "## Current decision state",
            "",
            "blocked_by_quality_gate=YES",
            "regime_call=not emitted",
            "reason=quality gate failed, so no production decision state is printed.",
            "",
            "## GPU price evidence table",
            "",
            "Not emitted because the quality gate failed.",
            "",
            "## CAPEX actual/guidance/RPO evidence table",
            "",
            "Not emitted because the quality gate failed.",
            "",
            "## Missing data and failed sources",
            "",
        ]
    )
    _append_reason_table(lines, quality_gate.reasons)
    lines.extend(
        [
            "",
            "## Investment implication by layer",
            "",
            "| layer | implication |",
            "|---|---|",
            "| L3 market proxy | Blocked until source-backed production pricing exists. |",
            "| L1 actual/event | Blocked until source-backed official actuals and events exist. |",
            "| L2 commitment | Blocked until source-backed guidance or RPO evidence exists. |",
            "",
        ]
    )
    _append_legacy_note(lines)
    return "\n".join(lines).rstrip() + "\n"


def _seed_only_status(database: Any, quality_gate: QualityGateResult) -> str:
    evidence_rows = sum(quality_gate.table_counts.get(table_name, 0) for table_name in EVIDENCE_TABLES)
    if evidence_rows != 0 or not hasattr(database, "get_source_type_quality_counts"):
        return ""
    counts = database.get_source_type_quality_counts()
    if counts.empty:
        return "NO_PRODUCTION_DATA"
    legacy_rows = counts.loc[
        (counts["path"] == "legacy_raw") & (counts["row_count"] > 0),
        "row_count",
    ].sum()
    if int(legacy_rows or 0) > 0:
        return "FAIL_SEED_ONLY"
    return "NO_PRODUCTION_DATA"


def _append_quality_section(lines: List[str], quality_gate: QualityGateResult) -> None:
    reason_codes = sorted({reason.reason_code for reason in quality_gate.reasons})
    lines.extend(
        [
            "## Data quality verdict",
            "",
            f"quality_gate={quality_gate.status}",
            "reason_codes=" + (", ".join(reason_codes) if reason_codes else "none"),
            "",
        ]
    )


def _append_decision_section(lines: List[str], decision: DecisionResult) -> None:
    lines.extend(
        [
            "## Current decision state",
            "",
            f"decision_state={decision.state}",
            f"quality_gate={decision.quality_gate.get('status', 'UNKNOWN')}",
            "method=gate-based source-backed decision, not a blended legacy index",
            "",
        ]
    )


def _append_gpu_table(lines: List[str], gpu_prices: pd.DataFrame) -> None:
    lines.extend(
        [
            "## GPU price evidence table",
            "",
            "| date | provider | gpu | variant | billing | price_per_gpu_hour | currency | source_type | source_url | snapshot |",
            "|---|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    if gpu_prices.empty:
        lines.append("|  |  |  |  |  |  |  |  |  |  |")
    else:
        for _, row in gpu_prices.iterrows():
            lines.append(
                "| {date} | {provider} | {gpu_model} | {gpu_variant} | {billing_type} | "
                "{price} | {currency} | {source_type} | source_url={source_url} | snapshot={snapshot_path} |".format(
                    date=_fmt(row.get("date")),
                    provider=_fmt(row.get("provider")),
                    gpu_model=_fmt(row.get("gpu_model")),
                    gpu_variant=_fmt(row.get("gpu_variant")),
                    billing_type=_fmt(row.get("billing_type")),
                    price=_fmt_number(row.get("price_per_gpu_hour")),
                    currency=_fmt(row.get("currency")),
                    source_type=_fmt(row.get("source_type")),
                    source_url=_fmt(row.get("source_url")),
                    snapshot_path=_fmt(row.get("snapshot_path")),
                )
            )
    lines.append("")


def _append_capex_event_tables(lines: List[str], capex_actuals: pd.DataFrame, official_events: pd.DataFrame) -> None:
    lines.extend(
        [
            "## CAPEX actual/guidance/RPO evidence table",
            "",
            "CAPEX actuals:",
            "",
            "| ticker | company | fiscal_period | period_end | capex_value | unit | xbrl_tag | accession_no | source_url | snapshot |",
            "|---|---|---|---|---:|---|---|---|---|---|",
        ]
    )
    if capex_actuals.empty:
        lines.append("|  |  |  |  |  |  |  |  |  |  |")
    else:
        for _, row in capex_actuals.iterrows():
            lines.append(
                "| {ticker} | {company} | {fiscal_period} | {period_end} | {capex_value} | "
                "{unit} | {xbrl_tag} | {accession_no} | source_url={source_url} | snapshot={snapshot_path} |".format(
                    ticker=_fmt(row.get("ticker")),
                    company=_fmt(row.get("company")),
                    fiscal_period=_fmt(row.get("fiscal_period")),
                    period_end=_fmt(row.get("period_end")),
                    capex_value=_fmt_number(row.get("capex_value")),
                    unit=_fmt(row.get("unit")),
                    xbrl_tag=_fmt(row.get("xbrl_tag")),
                    accession_no=_fmt(row.get("accession_no")),
                    source_url=_fmt(row.get("source_url")),
                    snapshot_path=_fmt(row.get("snapshot_path")),
                )
            )

    lines.extend(
        [
            "",
            "Guidance/RPO/official events:",
            "",
            "| ticker | announcement_date | event_type | metric | value | unit | fiscal_period | source_url | snapshot |",
            "|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    if official_events.empty:
        lines.append("|  |  |  |  |  |  |  |  |  |")
    else:
        for _, row in official_events.iterrows():
            lines.append(
                "| {ticker} | {announcement_date} | {event_type} | {metric} | {value} | "
                "{unit} | {fiscal_period} | source_url={source_url} | snapshot={snapshot_path} |".format(
                    ticker=_fmt(row.get("ticker")),
                    announcement_date=_fmt(row.get("announcement_date")),
                    event_type=_fmt(row.get("event_type")),
                    metric=_fmt(row.get("metric")),
                    value=_fmt_number(row.get("value")),
                    unit=_fmt(row.get("unit")),
                    fiscal_period=_fmt(row.get("fiscal_period")),
                    source_url=_fmt(row.get("source_url")),
                    snapshot_path=_fmt(row.get("snapshot_path")),
                )
            )
    lines.append("")


def _append_missing_and_failed_sources(
    lines: List[str],
    quality_gate: QualityGateResult,
    decision: DecisionResult,
) -> None:
    lines.extend(["## Missing data and failed sources", ""])
    rows: List[Dict[str, Any]] = []
    seen = set()
    for reason in quality_gate.reasons:
        if reason.reason_code in {"LEGACY_SEED_ROWS_PRESENT"}:
            continue
        _append_unique_row(
            rows,
            seen,
            {
                "type": "quality_gate",
                "layer": reason.table_name,
                "code": reason.reason_code,
                "affected_key": reason.affected_key,
                "message": reason.message,
                "source_url": reason.source_url,
                "snapshot_path": reason.snapshot_path,
            },
        )
    for item in decision.missing_data:
        _append_unique_row(
            rows,
            seen,
            {
                "type": "decision_missing",
                "layer": item.get("layer", ""),
                "code": item.get("code", ""),
                "affected_key": "",
                "message": item.get("message", ""),
                "source_url": item.get("source_url", ""),
                "snapshot_path": item.get("snapshot_path", ""),
            },
        )
    _append_dict_table(
        lines,
        rows,
        ["type", "layer", "code", "affected_key", "message", "source_url", "snapshot_path"],
    )
    lines.append("")


def _append_reason_table(lines: List[str], reasons: Iterable[Any]) -> None:
    rows = [
        {
            "severity": reason.severity,
            "table": reason.table_name,
            "code": reason.reason_code,
            "affected_key": reason.affected_key,
            "message": reason.message,
            "source_url": reason.source_url,
            "snapshot_path": reason.snapshot_path,
        }
        for reason in reasons
    ]
    _append_dict_table(lines, rows, ["severity", "table", "code", "affected_key", "message", "source_url", "snapshot_path"])


def _append_investment_implication(
    lines: List[str],
    quality_gate: QualityGateResult,
    decision: DecisionResult,
) -> None:
    evidence_codes = {item.get("code") for item in decision.evidence}
    counter_codes = {item.get("code") for item in decision.counter_evidence}
    missing_codes = {item.get("code") for item in decision.missing_data}

    l3 = "No actionable price-layer call; use as monitor until comparable trend evidence appears."
    if {"GPU_OFFICIAL_EASING", "AGGREGATOR_BREADTH_WEAKENING"} & evidence_codes:
        l3 = "Price layer supports Watch, but it cannot carry the thesis alone."
    if "GPU_OFFICIAL_FIRMING" in counter_codes:
        l3 = "Price layer is counter-evidence for scarcity-premium cracking."
    if {"GPU_OFFICIAL_TREND_INSUFFICIENT", "AGGREGATOR_TREND_INSUFFICIENT"} & missing_codes:
        l3 = "Price layer has source-backed rows, but comparable trend history is still insufficient."

    l1 = "Official actual/event layer is display-only until enough comparable company history exists."
    if {"CAPEX_DECELERATION"} & evidence_codes:
        l1 = "Official CAPEX actuals confirm deceleration."
    if {"CAPEX_ACCELERATION", "SUPPLY_TIGHT_COMMENT"} & counter_codes:
        l1 = "Official actual/event layer is counter-evidence or still points to tight capacity."

    l2 = "Commitment layer has no source-backed negative guidance or comparable RPO deceleration."
    if {"GUIDANCE_NEGATIVE_REVISION", "RPO_DECELERATION"} & evidence_codes:
        l2 = "Commitment layer confirms weaker forward demand or backlog."
    if {"GUIDANCE_POSITIVE_REVISION", "RPO_ACCELERATION"} & counter_codes:
        l2 = "Commitment layer is counter-evidence against cracking."

    lines.extend(
        [
            "## Investment implication by layer",
            "",
            "| layer | implication |",
            "|---|---|",
            f"| L3 market proxy | {_escape(l3)} |",
            f"| L1 actual/event | {_escape(l1)} |",
            f"| L2 commitment | {_escape(l2)} |",
            f"| quality gate | {_escape('Decision may be read as source-backed, but not as final completion.' if quality_gate.status != FAIL else 'Blocked.') } |",
            "",
        ]
    )


def _append_legacy_note(lines: List[str]) -> None:
    lines.extend(
        [
            "## Legacy/demo notes",
            "",
            "legacy_metrics/demo: csi=legacy/demo only; not used for production decision.",
            "",
        ]
    )


def _append_unique_row(rows: List[Dict[str, Any]], seen: set, row: Dict[str, Any]) -> None:
    key = tuple(row.get(field, "") for field in ("type", "layer", "code", "affected_key", "source_url", "snapshot_path"))
    if key in seen:
        return
    seen.add(key)
    rows.append(row)


def _append_dict_table(lines: List[str], rows: List[Dict[str, Any]], columns: List[str]) -> None:
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    if not rows:
        lines.append("| " + " | ".join([""] * len(columns)) + " |")
        return
    for row in rows:
        lines.append("| " + " | ".join(_escape(_fmt(row.get(column))) for column in columns) + " |")


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    if isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
        if parsed.tzinfo is None:
            return parsed.date().isoformat() if parsed.time().isoformat() == "00:00:00" else parsed.isoformat()
        return _format_datetime(parsed)[:10] if parsed.time().isoformat() == "00:00:00" else _format_datetime(parsed)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date().isoformat() if value.time().isoformat() == "00:00:00" else value.isoformat()
        return _format_datetime(value)[:10] if value.time().isoformat() == "00:00:00" else _format_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    if text.endswith(" 00:00:00"):
        return text[:10]
    return _escape(text)


def _fmt_number(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _fmt(value)
    return f"{numeric:.6g}"


def _escape(value: str) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")
