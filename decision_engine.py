from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from data_quality import evaluate_quality_gate


STATE_NO_SIGNAL = "No Signal"
STATE_WATCH = "Watch"
STATE_PRESSURE = "Pressure Building"
STATE_CRACKING = "Scarcity Premium Cracking"
STATE_TIGHT = "Scarcity Still Tight"

STATE_RANK = {
    STATE_NO_SIGNAL: 0,
    STATE_WATCH: 1,
    STATE_PRESSURE: 2,
    STATE_CRACKING: 3,
    STATE_TIGHT: 3,
}


@dataclass
class DecisionResult:
    state: str
    confidence: int
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    counter_evidence: List[Dict[str, Any]] = field(default_factory=list)
    missing_data: List[Dict[str, Any]] = field(default_factory=list)
    quality_gate: Dict[str, Any] = field(default_factory=dict)
    source_references: List[Dict[str, Any]] = field(default_factory=list)
    legacy_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
        if not text or text.lower() in {"nat", "none", "nan"}:
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


def _parse_date(value: Any) -> Optional[date]:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.date()


def _as_float(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percent_change(current: float, base: float) -> Optional[float]:
    if base == 0:
        return None
    return (current - base) / base * 100.0


def _quote_age_days(row: pd.Series, as_of_date: date) -> Optional[int]:
    commitment = str(row.get("commitment") or "")
    match = re.search(r"quote_age_days=(\d+)", commitment)
    if match:
        return int(match.group(1))
    row_date = _parse_date(row.get("date"))
    if row_date is None:
        return None
    return (as_of_date - row_date).days


def _source_from_row(row: Optional[pd.Series]) -> Dict[str, Any]:
    if row is None:
        return {}
    return {
        "source_id": str(row.get("source_id") or ""),
        "source_url": str(row.get("source_url") or ""),
        "snapshot_path": str(row.get("snapshot_path") or ""),
        "observed_at": str(row.get("observed_at") or ""),
        "fetched_at": str(row.get("fetched_at") or ""),
    }


def _item(
    *,
    layer: str,
    code: str,
    message: str,
    value: Optional[float] = None,
    threshold: str = "",
    row: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "layer": layer,
        "code": code,
        "message": message,
        "threshold": threshold,
    }
    if value is not None:
        payload["value"] = round(float(value), 4)
    payload.update(_source_from_row(row))
    return payload


def _unique_sources(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    refs: List[Dict[str, Any]] = []
    for item in items:
        source_url = str(item.get("source_url") or "")
        snapshot_path = str(item.get("snapshot_path") or "")
        if not source_url and not snapshot_path:
            continue
        key = (source_url, snapshot_path)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "source_id": str(item.get("source_id") or ""),
                "source_url": source_url,
                "snapshot_path": snapshot_path,
                "observed_at": str(item.get("observed_at") or ""),
                "fetched_at": str(item.get("fetched_at") or ""),
            }
        )
    return refs


class DecisionEngine:
    """Production decision engine that keeps L1/L2/L3 frequencies separate."""

    def __init__(self, database: Any):
        self.database = database

    def evaluate(self, *, as_of: Optional[Any] = None) -> DecisionResult:
        as_of_dt = _parse_datetime(as_of) or datetime.now(timezone.utc)
        as_of_date = as_of_dt.date()
        quality_gate = evaluate_quality_gate(self.database, as_of=as_of_dt.isoformat())
        tables = self._load_tables()

        evidence: List[Dict[str, Any]] = []
        counter: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []

        market = self._evaluate_market_layer(tables["gpu_prices"], as_of_date)
        evidence.extend(market["evidence"])
        counter.extend(market["counter_evidence"])
        missing.extend(market["missing_data"])

        official = self._evaluate_official_layer(
            tables["capex_actuals"],
            tables["official_events"],
        )
        evidence.extend(official["evidence"])
        counter.extend(official["counter_evidence"])
        missing.extend(official["missing_data"])

        state = self._choose_state(
            market_easing=market["market_easing"],
            official_price_easing=market["official_price_easing"],
            aggregator_weakening=market["aggregator_weakening"],
            price_firming=market["price_firming"],
            official_confirmation=official["official_confirmation"],
            tight_confirmation=official["tight_confirmation"],
            official_layer_missing=official["official_layer_missing"],
            counter_evidence=counter,
        )
        confidence = self._confidence(
            state=state,
            quality_status=quality_gate.status,
            source_count=self._source_count(evidence, counter),
            official_layer_missing=official["official_layer_missing"],
            price_only=market["market_easing"] and not official["official_confirmation"] and official["official_layer_missing"],
        )

        if official["official_layer_missing"] and STATE_RANK[state] > STATE_RANK[STATE_WATCH]:
            state = STATE_WATCH
            confidence = min(confidence, 40)

        if market["market_easing"] and not official["official_confirmation"]:
            confidence = min(confidence, 40)

        return DecisionResult(
            state=state,
            confidence=max(0, min(100, int(round(confidence)))),
            evidence=evidence,
            counter_evidence=counter,
            missing_data=missing,
            quality_gate=quality_gate.to_dict(),
            source_references=_unique_sources([*evidence, *counter, *missing]),
            legacy_metrics={
                "csi": {
                    "available": "legacy/demo only",
                    "used_for_production_decision": False,
                    "message": "Mixed-frequency weighted CSI is not used for production decisions.",
                }
            },
        )

    def _load_tables(self) -> Dict[str, pd.DataFrame]:
        conn = self.database.get_connection()
        try:
            return {
                "gpu_prices": conn.execute(
                    """
                    SELECT *
                    FROM production_gpu_prices
                    WHERE is_production_eligible = TRUE
                    ORDER BY date, provider, gpu_model, gpu_variant, source_id
                    """
                ).df(),
                "capex_actuals": conn.execute(
                    """
                    SELECT *
                    FROM production_capex_actuals
                    WHERE is_production_eligible = TRUE
                      AND source_type = 'official'
                    ORDER BY ticker, period_end
                    """
                ).df(),
                "official_events": conn.execute(
                    """
                    SELECT *
                    FROM production_official_events
                    WHERE is_production_eligible = TRUE
                      AND source_type = 'official'
                    ORDER BY ticker, announcement_date
                    """
                ).df(),
            }
        finally:
            conn.close()

    def _evaluate_market_layer(self, gpu_prices: pd.DataFrame, as_of_date: date) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        counter: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []

        official_result = self._evaluate_official_gpu_trend(gpu_prices)
        evidence.extend(official_result["evidence"])
        counter.extend(official_result["counter_evidence"])
        missing.extend(official_result["missing_data"])

        aggregator_result = self._evaluate_aggregator_breadth(gpu_prices, as_of_date)
        evidence.extend(aggregator_result["evidence"])
        missing.extend(aggregator_result["missing_data"])

        return {
            "evidence": evidence,
            "counter_evidence": counter,
            "missing_data": missing,
            "official_price_easing": official_result["official_price_easing"],
            "aggregator_weakening": aggregator_result["aggregator_weakening"],
            "market_easing": official_result["official_price_easing"] or aggregator_result["aggregator_weakening"],
            "price_firming": official_result["price_firming"],
        }

    def _evaluate_official_gpu_trend(self, gpu_prices: pd.DataFrame) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        counter: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        if gpu_prices.empty:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_TREND_INSUFFICIENT",
                    message="No production GPU pricing rows are available.",
                )
            )
            return {
                "evidence": evidence,
                "counter_evidence": counter,
                "missing_data": missing,
                "official_price_easing": False,
                "price_firming": False,
            }

        official = gpu_prices[
            (gpu_prices["source_type"] == "public_pricing_page")
            & (gpu_prices["gpu_model"] == "H100")
        ].copy()
        if official.empty:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_TREND_INSUFFICIENT",
                    message="No official H100 comparable public pricing rows are available.",
                )
            )
            return {
                "evidence": evidence,
                "counter_evidence": counter,
                "missing_data": missing,
                "official_price_easing": False,
                "price_firming": False,
            }

        official["_date"] = official["date"].map(_parse_date)
        official = official.dropna(subset=["_date"])
        if official["_date"].nunique() < 2:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_TREND_INSUFFICIENT",
                    message="Official H100 pricing has only one snapshot date; no 30d/90d trend is inferred.",
                    row=official.iloc[-1] if not official.empty else None,
                )
            )
            return {
                "evidence": evidence,
                "counter_evidence": counter,
                "missing_data": missing,
                "official_price_easing": False,
                "price_firming": False,
            }

        latest_date = official["_date"].max()
        latest_rows = official[official["_date"] == latest_date]
        latest_price = median([float(v) for v in latest_rows["price_per_gpu_hour"].dropna().tolist()])
        latest_row = latest_rows.iloc[0]

        trend_30 = self._trend_change(official, latest_date, latest_price, days=30)
        trend_90 = self._trend_change(official, latest_date, latest_price, days=90)

        official_easing = False
        if trend_30 is not None and trend_30 <= -10:
            official_easing = True
            evidence.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_EASING",
                    value=trend_30,
                    threshold="official H100 comparable quote 30d <= -10%",
                    message=f"Official H100 comparable median quote fell {trend_30:.1f}% over at least 30 days.",
                    row=latest_row,
                )
            )
        elif trend_90 is not None and trend_90 <= -20:
            official_easing = True
            evidence.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_EASING",
                    value=trend_90,
                    threshold="official H100 comparable quote 90d <= -20%",
                    message=f"Official H100 comparable median quote fell {trend_90:.1f}% over at least 90 days.",
                    row=latest_row,
                )
            )
        elif trend_30 is None and trend_90 is None:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_TREND_INSUFFICIENT",
                    message="Official H100 pricing lacks a 30d or 90d comparable baseline.",
                    row=latest_row,
                )
            )

        price_firming = bool(trend_30 is not None and trend_30 >= 10)
        if price_firming:
            counter.append(
                _item(
                    layer="L3_market_proxy",
                    code="GPU_OFFICIAL_FIRMING",
                    value=trend_30,
                    threshold="official H100 comparable quote 30d >= +10%",
                    message=f"Official H100 comparable median quote rose {trend_30:.1f}% over at least 30 days.",
                    row=latest_row,
                )
            )

        return {
            "evidence": evidence,
            "counter_evidence": counter,
            "missing_data": missing,
            "official_price_easing": official_easing,
            "price_firming": price_firming,
        }

    def _trend_change(
        self,
        df: pd.DataFrame,
        latest_date: date,
        latest_price: float,
        *,
        days: int,
    ) -> Optional[float]:
        baseline_cutoff = latest_date - timedelta(days=days)
        baseline = df[df["_date"] <= baseline_cutoff]
        if baseline.empty:
            return None
        baseline_date = baseline["_date"].max()
        baseline_rows = baseline[baseline["_date"] == baseline_date]
        baseline_price = median([float(v) for v in baseline_rows["price_per_gpu_hour"].dropna().tolist()])
        return _percent_change(latest_price, baseline_price)

    def _evaluate_aggregator_breadth(self, gpu_prices: pd.DataFrame, as_of_date: date) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        if gpu_prices.empty:
            return {"evidence": evidence, "missing_data": missing, "aggregator_weakening": False}

        aggregator = gpu_prices[
            (gpu_prices["source_type"] == "aggregator")
            & (gpu_prices["gpu_model"].isin(["H100", "H200"]))
        ].copy()
        if aggregator.empty:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="AGGREGATOR_BREADTH_MISSING",
                    message="No eligible ComputePrices H100/H200 aggregator quotes are available.",
                )
            )
            return {"evidence": evidence, "missing_data": missing, "aggregator_weakening": False}

        aggregator["_date"] = aggregator["date"].map(_parse_date)
        aggregator = aggregator.dropna(subset=["_date"])
        latest_date = aggregator["_date"].max()
        latest_rows = aggregator[aggregator["_date"] == latest_date].copy()
        latest_rows["_quote_age_days"] = latest_rows.apply(lambda row: _quote_age_days(row, as_of_date), axis=1)
        current_rows = latest_rows[
            latest_rows["_quote_age_days"].notna()
            & (latest_rows["_quote_age_days"] < 14)
        ]
        if len(current_rows) < 8:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="AGGREGATOR_CURRENT_BREADTH_INSUFFICIENT",
                    value=len(current_rows),
                    threshold="current ComputePrices H100/H200 quotes >= 8 and quote age <14d",
                    message=f"Only {len(current_rows)} fresh current ComputePrices quotes are available.",
                    row=latest_rows.iloc[0] if not latest_rows.empty else None,
                )
            )
            return {"evidence": evidence, "missing_data": missing, "aggregator_weakening": False}

        baseline = aggregator[aggregator["_date"] <= latest_date - timedelta(days=30)]
        if baseline.empty:
            missing.append(
                _item(
                    layer="L3_market_proxy",
                    code="AGGREGATOR_TREND_INSUFFICIENT",
                    threshold="ComputePrices comparable median 30d trend",
                    message="ComputePrices has a current breadth snapshot but no 30d comparable baseline; trend is not inferred.",
                    row=current_rows.iloc[0],
                )
            )
            return {"evidence": evidence, "missing_data": missing, "aggregator_weakening": False}

        baseline_date = baseline["_date"].max()
        baseline_rows = baseline[baseline["_date"] == baseline_date]
        current_median = median([float(v) for v in current_rows["price_per_gpu_hour"].dropna().tolist()])
        baseline_median = median([float(v) for v in baseline_rows["price_per_gpu_hour"].dropna().tolist()])
        change = _percent_change(current_median, baseline_median)
        if change is not None and change <= -15:
            evidence.append(
                _item(
                    layer="L3_market_proxy",
                    code="AGGREGATOR_BREADTH_WEAKENING",
                    value=change,
                    threshold="ComputePrices H100/H200 median 30d <= -15%, current quotes >=8, quote age <14d",
                    message=f"ComputePrices H100/H200 median fell {change:.1f}% with {len(current_rows)} fresh current quotes.",
                    row=current_rows.iloc[0],
                )
            )
            return {"evidence": evidence, "missing_data": missing, "aggregator_weakening": True}

        return {"evidence": evidence, "missing_data": missing, "aggregator_weakening": False}

    def _evaluate_official_layer(self, capex_actuals: pd.DataFrame, official_events: pd.DataFrame) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        counter: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []

        official_layer_missing = capex_actuals.empty or official_events.empty
        if official_layer_missing:
            missing.append(
                _item(
                    layer="L1_actual_event",
                    code="CAPEX_CONFIRMATION_MISSING",
                    message="CAPEX actuals or official guidance/RPO events are missing; decision state is capped at Watch.",
                )
            )

        capex_result = self._evaluate_capex_trend(capex_actuals)
        evidence.extend(capex_result["evidence"])
        counter.extend(capex_result["counter_evidence"])
        missing.extend(capex_result["missing_data"])

        event_result = self._evaluate_official_events(official_events)
        evidence.extend(event_result["evidence"])
        counter.extend(event_result["counter_evidence"])
        missing.extend(event_result["missing_data"])

        official_confirmation = bool(capex_result["deceleration"] or event_result["negative_revision"] or event_result["rpo_deceleration"])
        tight_confirmation = bool(capex_result["acceleration"] or event_result["positive_revision"] or event_result["supply_tight_comment"] or event_result["rpo_acceleration"])

        return {
            "evidence": evidence,
            "counter_evidence": counter,
            "missing_data": missing,
            "official_layer_missing": official_layer_missing,
            "official_confirmation": official_confirmation,
            "tight_confirmation": tight_confirmation,
        }

    def _evaluate_capex_trend(self, capex_actuals: pd.DataFrame) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        counter: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        deceleration = False
        acceleration = False

        if capex_actuals.empty:
            return {
                "evidence": evidence,
                "counter_evidence": counter,
                "missing_data": missing,
                "deceleration": False,
                "acceleration": False,
            }

        for ticker, group in capex_actuals.groupby("ticker"):
            ordered = group.copy()
            ordered["_period_end"] = ordered["period_end"].map(_parse_date)
            ordered = ordered.dropna(subset=["_period_end"]).sort_values("_period_end")
            if len(ordered) < 4:
                missing.append(
                    _item(
                        layer="L1_actual_event",
                        code="CAPEX_TREND_DISPLAY_ONLY",
                        value=len(ordered),
                        threshold="at least 4 sequential quarters per company",
                        message=f"{ticker} has only {len(ordered)} official CAPEX actual period(s); trend is display-only.",
                        row=ordered.iloc[-1] if not ordered.empty else None,
                    )
                )
                continue

            latest = ordered.iloc[-1]
            previous = ordered.iloc[-2]
            first = ordered.iloc[0]
            latest_value = _as_float(latest.get("capex_value"))
            previous_value = _as_float(previous.get("capex_value"))
            first_value = _as_float(first.get("capex_value"))
            if latest_value is None or previous_value is None or first_value is None:
                continue
            qoq = _percent_change(latest_value, previous_value)
            four_q = _percent_change(latest_value, first_value)
            if qoq is not None and four_q is not None and qoq <= -5 and four_q <= -5:
                deceleration = True
                evidence.append(
                    _item(
                        layer="L1_actual_event",
                        code="CAPEX_DECELERATION",
                        value=four_q,
                        threshold="QoQ and 4-quarter trend <= -5% with >=4 sequential quarters",
                        message=f"{ticker} official CAPEX actuals decelerated on comparable sequential history.",
                        row=latest,
                    )
                )
            elif qoq is not None and four_q is not None and qoq >= 5 and four_q >= 5:
                acceleration = True
                counter.append(
                    _item(
                        layer="L1_actual_event",
                        code="CAPEX_ACCELERATION",
                        value=four_q,
                        threshold="QoQ and 4-quarter trend >= +5% with >=4 sequential quarters",
                        message=f"{ticker} official CAPEX actuals accelerated on comparable sequential history.",
                        row=latest,
                    )
                )

        return {
            "evidence": evidence,
            "counter_evidence": counter,
            "missing_data": missing,
            "deceleration": deceleration,
            "acceleration": acceleration,
        }

    def _evaluate_official_events(self, official_events: pd.DataFrame) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        counter: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        negative_revision = False
        positive_revision = False
        rpo_deceleration = False
        rpo_acceleration = False
        supply_tight_comment = False

        if official_events.empty:
            return {
                "evidence": evidence,
                "counter_evidence": counter,
                "missing_data": missing,
                "negative_revision": False,
                "positive_revision": False,
                "rpo_deceleration": False,
                "rpo_acceleration": False,
                "supply_tight_comment": False,
            }

        revision_rows = official_events[official_events["event_type"] == "capex_guidance_revision"]
        for _, row in revision_rows.iterrows():
            value = _as_float(row.get("value"))
            if value is None:
                continue
            metric = str(row.get("metric") or "").lower()
            if "revision" not in metric and "change" not in metric and str(row.get("unit") or "").lower() not in {"pct", "%"}:
                continue
            if value < 0:
                negative_revision = True
                evidence.append(
                    _item(
                        layer="L2_commitment",
                        code="GUIDANCE_NEGATIVE_REVISION",
                        value=value,
                        threshold="official guidance revision < 0",
                        message=f"{row.get('ticker')} official CAPEX guidance revision is negative.",
                        row=row,
                    )
                )
            elif value > 0:
                positive_revision = True
                counter.append(
                    _item(
                        layer="L2_commitment",
                        code="GUIDANCE_POSITIVE_REVISION",
                        value=value,
                        threshold="official guidance revision > 0",
                        message=f"{row.get('ticker')} official CAPEX guidance revision is positive.",
                        row=row,
                    )
                )

        rpo_rows = official_events[
            (official_events["event_type"].str.lower() == "rpo")
            | (official_events["metric"].str.lower().str.contains("rpo|backlog", na=False))
        ].copy()
        if not rpo_rows.empty:
            for ticker, group in rpo_rows.groupby("ticker"):
                ordered = group.copy()
                ordered["_announcement_date"] = ordered["announcement_date"].map(_parse_date)
                ordered = ordered.dropna(subset=["_announcement_date"]).sort_values("_announcement_date")
                if len(ordered) < 2:
                    missing.append(
                        _item(
                            layer="L2_commitment",
                            code="RPO_DISPLAY_ONLY",
                            threshold="comparable sequential or YoY official RPO/backlog",
                            message=f"{ticker} has only one official RPO/backlog value; it is display-only.",
                            row=ordered.iloc[-1] if not ordered.empty else None,
                        )
                    )
                    continue
                latest = ordered.iloc[-1]
                previous = ordered.iloc[-2]
                latest_value = _as_float(latest.get("value"))
                previous_value = _as_float(previous.get("value"))
                change = _percent_change(latest_value, previous_value) if latest_value is not None and previous_value is not None else None
                if change is None:
                    continue
                if change <= -5:
                    rpo_deceleration = True
                    evidence.append(
                        _item(
                            layer="L2_commitment",
                            code="RPO_DECELERATION",
                            value=change,
                            threshold="comparable sequential or YoY official RPO/backlog <= -5%",
                            message=f"{ticker} official RPO/backlog decelerated on comparable data.",
                            row=latest,
                        )
                    )
                elif change >= 5:
                    rpo_acceleration = True
                    counter.append(
                        _item(
                            layer="L2_commitment",
                            code="RPO_ACCELERATION",
                            value=change,
                            threshold="comparable sequential or YoY official RPO/backlog >= +5%",
                            message=f"{ticker} official RPO/backlog accelerated on comparable data.",
                            row=latest,
                        )
                    )

        supply_rows = official_events[
            official_events["event_type"].isin(["capacity_comment", "supply_constraint_comment", "management_capacity_comment"])
        ]
        for _, row in supply_rows.iterrows():
            text = f"{row.get('metric') or ''} {row.get('description') or ''}".lower()
            if any(token in text for token in ["demand exceeds", "supply constraint", "constrained", "shortage", "tight"]):
                supply_tight_comment = True
                counter.append(
                    _item(
                        layer="L1_actual_event",
                        code="SUPPLY_TIGHT_COMMENT",
                        message=f"{row.get('ticker')} official comment indicates AI capacity remains constrained.",
                        row=row,
                    )
                )

        return {
            "evidence": evidence,
            "counter_evidence": counter,
            "missing_data": missing,
            "negative_revision": negative_revision,
            "positive_revision": positive_revision,
            "rpo_deceleration": rpo_deceleration,
            "rpo_acceleration": rpo_acceleration,
            "supply_tight_comment": supply_tight_comment,
        }

    def _choose_state(
        self,
        *,
        market_easing: bool,
        official_price_easing: bool,
        aggregator_weakening: bool,
        price_firming: bool,
        official_confirmation: bool,
        tight_confirmation: bool,
        official_layer_missing: bool,
        counter_evidence: List[Dict[str, Any]],
    ) -> str:
        if price_firming or (tight_confirmation and not market_easing):
            state = STATE_TIGHT
        elif market_easing and official_confirmation:
            state = STATE_CRACKING
        elif official_price_easing and aggregator_weakening and not any(item["code"] == "CAPEX_ACCELERATION" for item in counter_evidence):
            state = STATE_PRESSURE
        elif market_easing:
            state = STATE_WATCH
        else:
            state = STATE_NO_SIGNAL

        if official_layer_missing and STATE_RANK[state] > STATE_RANK[STATE_WATCH]:
            return STATE_WATCH
        return state

    def _source_count(self, evidence: List[Dict[str, Any]], counter: List[Dict[str, Any]]) -> int:
        refs = _unique_sources([*evidence, *counter])
        return len(refs)

    def _confidence(
        self,
        *,
        state: str,
        quality_status: str,
        source_count: int,
        official_layer_missing: bool,
        price_only: bool,
    ) -> int:
        base = {
            STATE_NO_SIGNAL: 15,
            STATE_WATCH: 35,
            STATE_PRESSURE: 55,
            STATE_CRACKING: 72,
            STATE_TIGHT: 55,
        }[state]
        if quality_status == "PASS":
            base += 10
        elif quality_status == "FAIL":
            base -= 10
        base += min(8, source_count * 2)
        if official_layer_missing:
            base = min(base, 40)
        if price_only:
            base = min(base, 40)
        return base


def format_decision_result(result: DecisionResult) -> str:
    lines = [
        "source-backed decision",
        f"   decision_state={result.state}",
        f"   confidence={result.confidence}%",
        f"   quality_gate={result.quality_gate.get('status', 'UNKNOWN')}",
    ]

    def add_section(title: str, rows: List[Dict[str, Any]]) -> None:
        lines.append(f"{title}:")
        if not rows:
            lines.append("   (none)")
            return
        for row in rows:
            value = f" | value={row['value']}" if "value" in row else ""
            source = f" | source_url={row['source_url']}" if row.get("source_url") else ""
            lines.append(
                f"   {row['layer']} | {row['code']}{value} | {row['message']}{source}"
            )

    add_section("evidence", result.evidence)
    add_section("counter_evidence", result.counter_evidence)
    add_section("missing_data", result.missing_data)

    lines.append("source_references:")
    if not result.source_references:
        lines.append("   (none)")
    else:
        for ref in result.source_references:
            lines.append(
                f"   {ref.get('source_id', '')} | {ref.get('source_url', '')} | "
                f"snapshot={ref.get('snapshot_path', '')}"
            )
    lines.append("legacy_metrics:")
    lines.append("   csi=legacy/demo only; not used for production decision")
    return "\n".join(lines)
