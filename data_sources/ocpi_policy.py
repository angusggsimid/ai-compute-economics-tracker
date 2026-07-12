from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
from statistics import median
from typing import List, Optional

import pandas as pd

from production_store import DataQualityEvent, ProductionStore, PublicProxyPriceObservation


ORNN_OCPI_SOURCE_ID = "ornn-ocpi"
ORNN_OCPI_SOURCE_URL = "https://www.ornn.ai/"
PUBLIC_PROXY_NAME = "public_gpu_price_proxy"
COMPUTEPRICES_SOURCE_IDS = {"computeprices-h100", "computeprices-h200"}
COMPUTEPRICES_SOURCE_URLS = {
    "https://computeprices.com/gpus/h100",
    "https://computeprices.com/gpus/h200",
}


@dataclass
class OcpiPolicyUpdateResult:
    public_proxy_rows: List[PublicProxyPriceObservation] = field(default_factory=list)
    quality_events: List[DataQualityEvent] = field(default_factory=list)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _payload_hash(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _date_string(value) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value).split(" ", 1)[0]


def _timestamp_string(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return _utc_now_iso()
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(microsecond=0).isoformat() + "Z"
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _has_authorized_ocpi_feed() -> bool:
    return bool(os.getenv("ORNN_OCPI_FEED_URL") and os.getenv("ORNN_OCPI_FEED_TOKEN"))


def _quality_event(
    *,
    run_id: str,
    event_id: str,
    table_name: str,
    source_id: str,
    source_url: str,
    source_type: str,
    collection_method: str,
    message: str,
    affected_key: str,
    error_code: str,
    fetched_at: str,
    severity: str = "warning",
    is_blocking: bool = True,
) -> DataQualityEvent:
    marker_payload = "\n".join(
        [
            f"event_id={event_id}",
            f"source_id={source_id}",
            f"source_url={source_url}",
            f"error_code={error_code}",
            f"message={message}",
            f"fetched_at={fetched_at}",
        ]
    )
    return DataQualityEvent(
        event_id=event_id,
        table_name=table_name,
        severity=severity,
        message=message,
        affected_key=affected_key,
        is_blocking=is_blocking,
        run_id=run_id,
        source_id=source_id,
        source_url=source_url,
        snapshot_path=f"unavailable_marker://{source_id}/{error_code}",
        source_type=source_type,
        collection_method=collection_method,
        observed_at=fetched_at,
        fetched_at=fetched_at,
        raw_payload_hash=_payload_hash(marker_payload),
        is_production_eligible=False,
        confidence=0.0,
        error_code=error_code,
    )


def build_ocpi_unavailable_event(*, run_id: str, fetched_at: str) -> DataQualityEvent:
    return _quality_event(
        run_id=run_id,
        event_id=f"{run_id}:{ORNN_OCPI_SOURCE_ID}:DATA_SOURCE_UNAVAILABLE",
        table_name="ornn_ocpi_feed",
        source_id=ORNN_OCPI_SOURCE_ID,
        source_url=ORNN_OCPI_SOURCE_URL,
        source_type="licensed_unavailable",
        collection_method="unavailable_marker",
        message=(
            "OCPI unavailable: no authorized ORNN/OCPI, Bloomberg, ICE, or equivalent "
            "licensed feed is configured; no fallback value was inserted."
        ),
        affected_key="ornn_ocpi",
        error_code="DATA_SOURCE_UNAVAILABLE",
        fetched_at=fetched_at,
    )


def build_public_proxy_missing_event(*, run_id: str, fetched_at: str) -> DataQualityEvent:
    return _quality_event(
        run_id=run_id,
        event_id=f"{run_id}:{PUBLIC_PROXY_NAME}:PUBLIC_PROXY_SOURCE_MISSING",
        table_name="production_public_proxy_prices",
        source_id=PUBLIC_PROXY_NAME,
        source_url="https://computeprices.com/gpus/h100",
        source_type="aggregator",
        collection_method="unavailable_marker",
        message=(
            "public_gpu_price_proxy unavailable: no eligible ComputePrices H100/H200 "
            "aggregator rows exist in production_gpu_prices."
        ),
        affected_key=PUBLIC_PROXY_NAME,
        error_code="PUBLIC_PROXY_SOURCE_MISSING",
        fetched_at=fetched_at,
    )


def _load_computeprices_rows(store: ProductionStore) -> pd.DataFrame:
    conn = store.database.get_connection()
    try:
        return conn.execute(
            """
            SELECT *
            FROM production_gpu_prices
            WHERE is_production_eligible = TRUE
              AND source_type = 'aggregator'
              AND (
                    source_id IN ('computeprices-h100', 'computeprices-h200')
                 OR source_url IN ('https://computeprices.com/gpus/h100', 'https://computeprices.com/gpus/h200')
              )
              AND gpu_model IN ('H100', 'H200')
              AND price_per_gpu_hour IS NOT NULL
            ORDER BY gpu_model, date, source_url, fetched_at, provider
            """
        ).df()
    finally:
        conn.close()


def build_public_proxy_rows(
    store: ProductionStore,
    *,
    run_id: str,
) -> List[PublicProxyPriceObservation]:
    rows = _load_computeprices_rows(store)
    if rows.empty:
        return []

    proxy_rows: List[PublicProxyPriceObservation] = []
    group_keys = ["date", "gpu_model", "source_id", "source_url"]
    for _, group in rows.groupby(group_keys, dropna=False):
        latest_fetched_at = group["fetched_at"].max()
        latest_group = group[group["fetched_at"] == latest_fetched_at]
        if latest_group.empty:
            latest_group = group
        representative = latest_group.iloc[0]
        prices = [
            float(value)
            for value in latest_group["price_per_gpu_hour"].tolist()
            if value is not None and not pd.isna(value)
        ]
        if not prices:
            continue

        date = _date_string(representative["date"])
        fetched_at = _timestamp_string(representative["fetched_at"])
        observed_at = f"{date}T00:00:00Z"
        source_url = str(representative["source_url"])
        snapshot_path = str(representative["snapshot_path"])
        raw_payload_hash = str(representative["raw_payload_hash"])
        source_id = str(representative["source_id"])
        gpu_model = str(representative["gpu_model"])

        metrics = [
            ("computeprices_row_count_proxy", float(len(prices)), "rows"),
            ("computeprices_row_min_price_per_gpu_hour_proxy", min(prices), "USD_per_gpu_hour"),
            ("computeprices_row_median_price_per_gpu_hour_proxy", float(median(prices)), "USD_per_gpu_hour"),
        ]
        for metric, value, unit in metrics:
            proxy_rows.append(
                PublicProxyPriceObservation(
                    date=date,
                    provider="ComputePrices",
                    proxy_name=PUBLIC_PROXY_NAME,
                    metric=metric,
                    value=value,
                    unit=unit,
                    gpu_model=gpu_model,
                    region="aggregator_rows",
                    run_id=run_id,
                    source_id=source_id,
                    source_url=source_url,
                    snapshot_path=snapshot_path,
                    source_type="aggregator",
                    collection_method="html_parse",
                    observed_at=observed_at,
                    fetched_at=fetched_at,
                    raw_payload_hash=raw_payload_hash,
                    is_production_eligible=True,
                    confidence=0.65,
                    error_code=None,
                )
            )
    return proxy_rows


def update_ocpi_policy(
    *,
    store: Optional[ProductionStore] = None,
    run_id: Optional[str] = None,
    fetched_at: Optional[str] = None,
) -> OcpiPolicyUpdateResult:
    store = store or ProductionStore()
    fetched_at = fetched_at or _utc_now_iso()
    run_id = run_id or f"ocpi-policy-{fetched_at.replace(':', '').replace('+', '')}"
    result = OcpiPolicyUpdateResult()

    if not _has_authorized_ocpi_feed():
        result.quality_events.append(build_ocpi_unavailable_event(run_id=run_id, fetched_at=fetched_at))

    result.public_proxy_rows = build_public_proxy_rows(store, run_id=run_id)
    if not result.public_proxy_rows:
        result.quality_events.append(build_public_proxy_missing_event(run_id=run_id, fetched_at=fetched_at))

    if result.public_proxy_rows:
        store.insert_public_proxy_prices(result.public_proxy_rows)
    if result.quality_events:
        store.insert_quality_events(result.quality_events)

    return result
