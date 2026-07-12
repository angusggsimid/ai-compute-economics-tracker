#!/usr/bin/env python3
"""
AI Compute Scarcity Tracker v2 — 可运行闭环脚本
==========================================================
在 v1 基础上升级：
1. 季度 CAPEX → 日度可解释变量的频率对齐（L1 Raw / L2 Forward Curve / L3 Nowcast）
2. 双时间轴可视化所需的数据支撑（earnings_calendar、guidance_revision、capex_daily_implied）
3. 领先/滞后分析引擎（guidance revision → GPU price, GPU trend → next guidance）
4. 保持与 v1 的向后兼容（共用 DB，保留所有 v1 表结构）

技术栈: Python + DuckDB + yfinance + Streamlit + Plotly
运行方式:
  1. 初始化数据库: python tracker_v2.py init
  2. 每日更新数据: python tracker_v2.py update
  3. 启动看板:    streamlit run dashboard_v2.py

作者: AI Assistant (product_engineer sub-agent)
日期: 2026-07-03
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np
import duckdb
import yfinance as yf
import requests
from bs4 import BeautifulSoup

# Keep collector modules that import `tracker_v2` pointed at this running CLI module.
if __name__ == "__main__":
    sys.modules.setdefault("tracker_v2", sys.modules[__name__])

from company_config import CompanyConfigError, decision_universe_configs, validate_company_configs
from data_sources import (
    PRODUCTION_UPDATE_TARGETS,
    allowed_production_update_values,
    validate_production_update_target,
)

# ============================================================
# 配置
# ============================================================
DEFAULT_DB_PATH = "ai_compute_tracker.db"
PRODUCTION_DB_PATH = "ai_compute_tracker_production.db"
DB_PATH_ENV_VAR = "AI_COMPUTE_TRACKER_DB"
DB_PATH = DEFAULT_DB_PATH
_CLI_DB_PATH_OVERRIDE: Optional[str] = None


def set_default_db_path(db_path: Optional[str]) -> None:
    global _CLI_DB_PATH_OVERRIDE
    _CLI_DB_PATH_OVERRIDE = str(db_path) if db_path else None
    if db_path:
        os.environ[DB_PATH_ENV_VAR] = str(db_path)
    else:
        os.environ.pop(DB_PATH_ENV_VAR, None)


def get_default_db_path() -> str:
    return _CLI_DB_PATH_OVERRIDE or os.environ.get(DB_PATH_ENV_VAR, DEFAULT_DB_PATH)


DATA_DIR = Path("tracker_data")
DATA_DIR.mkdir(exist_ok=True)

HYPERSCALERS = {
    "MSFT": {"name": "Microsoft", "fiscal_year_end": "06-30"},
    "AMZN": {"name": "Amazon", "fiscal_year_end": "12-31"},
    "GOOGL": {"name": "Alphabet", "fiscal_year_end": "12-31"},
    "META": {"name": "Meta", "fiscal_year_end": "12-31"},
}

GPU_MODELS = ["H100", "H200", "A100", "B200", "B300", "MI300X"]
BILLING_TYPES = ["on-demand", "spot", "1yr-reserved"]

# 关键阈值
THRESHOLDS = {
    "h100_price_floor": 2.50,
    "h100_price_peak": 7.00,
    "spot_discount_critical": 0.60,
    "capex_guidance_cut_pct": 0.10,
    "meta_monetization_rate": 0.30,
}

PRODUCTION_SOURCE_TYPES = {
    "official",
    "public_pricing_page",
    "aggregator",
    "manual_verified",
    "licensed_unavailable",
}
PRODUCTION_REJECTED_SOURCE_TYPES = {"seed", "mock"}
PRODUCTION_COLLECTION_METHODS = {
    "sec_companyfacts_api",
    "json_api",
    "csv_http",
    "graphql_api",
    "html_parse",
    "browser_rendered_text",
    "next_data_parse",
    "embedded_json_parse",
    "manual_sourcebacked_yaml",
    "unavailable_marker",
}
PRODUCTION_PROVENANCE_FIELDS = [
    "run_id",
    "source_id",
    "source_url",
    "snapshot_path",
    "source_type",
    "collection_method",
    "observed_at",
    "fetched_at",
    "raw_payload_hash",
    "is_production_eligible",
    "confidence",
    "error_code",
]
PRODUCTION_TABLES = [
    "production_gpu_prices",
    "production_capex_actuals",
    "production_official_events",
    "production_public_proxy_prices",
    "production_market_facts",
    "production_data_quality_events",
    "production_pipeline_runs",
]
PRODUCTION_TABLE_COLUMNS = {
    "production_gpu_prices": [
        "date", "provider", "gpu_model", "gpu_variant", "billing_type",
        "commitment", "gpu_count", "region", "price_per_gpu_hour",
        "currency", "availability_observed",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
    "production_capex_actuals": [
        "ticker", "company", "period_start", "period_end", "fiscal_period",
        "fiscal_year", "xbrl_tag", "accession_no", "capex_value", "unit",
        "filed_at", "form_type",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
    "production_official_events": [
        "ticker", "announcement_date", "event_type", "metric", "value",
        "unit", "description", "fiscal_period",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
    "production_public_proxy_prices": [
        "date", "provider", "proxy_name", "metric", "value", "unit",
        "gpu_model", "region",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
    "production_market_facts": [
        "date", "track", "entity", "sub_entity", "metric", "value", "unit",
        "dimension", "vendor", "source_name", "notes",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
    "production_data_quality_events": [
        "event_id", "table_name", "severity", "message", "affected_key",
        "is_blocking",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
    "production_pipeline_runs": [
        "pipeline_name", "status", "started_at", "completed_at",
        "rows_loaded", "message",
        *PRODUCTION_PROVENANCE_FIELDS,
        "created_at", "updated_at",
    ],
}
PRODUCTION_UPSERT_KEYS = {
    "production_gpu_prices": [
        "date", "provider", "gpu_model", "gpu_variant", "billing_type",
        "commitment", "gpu_count", "region", "source_url",
    ],
    "production_capex_actuals": [
        "ticker", "period_start", "period_end", "fiscal_period",
        "xbrl_tag", "accession_no",
    ],
    "production_official_events": [
        "ticker", "announcement_date", "event_type", "metric", "source_url",
    ],
    "production_public_proxy_prices": [
        "date", "provider", "proxy_name", "metric", "source_url",
    ],
    "production_market_facts": [
        "date", "track", "entity", "sub_entity", "metric", "dimension", "source_url",
    ],
    "production_data_quality_events": ["event_id"],
    "production_pipeline_runs": ["run_id"],
}


class ProductionDataContractError(ValueError):
    """生产数据合同错误：必须暴露，不能降级成 seed/mock。"""


class SchemaMigrationError(RuntimeError):
    """数据库 schema 初始化失败。"""


def validate_production_provenance(record: Dict[str, Any], table_name: str = "production") -> None:
    """统一生产写入门禁，所有 production insert 必须先过这里。"""
    source_type = record.get("source_type")
    if source_type in PRODUCTION_REJECTED_SOURCE_TYPES:
        raise ProductionDataContractError(
            f"PRODUCTION_SOURCE_TYPE_REJECTED: {table_name} rejects seed/mock source_type "
            f"for production insert; got source_type={source_type!r}."
        )
    if source_type not in PRODUCTION_SOURCE_TYPES:
        allowed = ", ".join(sorted(PRODUCTION_SOURCE_TYPES))
        raise ProductionDataContractError(
            f"PRODUCTION_SOURCE_TYPE_INVALID: {table_name} source_type={source_type!r}; "
            f"allowed: {allowed}."
        )

    collection_method = record.get("collection_method")
    if collection_method not in PRODUCTION_COLLECTION_METHODS:
        allowed = ", ".join(sorted(PRODUCTION_COLLECTION_METHODS))
        raise ProductionDataContractError(
            f"PRODUCTION_COLLECTION_METHOD_INVALID: {table_name} collection_method="
            f"{collection_method!r}; allowed: {allowed}."
        )

    missing = [field for field in PRODUCTION_PROVENANCE_FIELDS if field not in record]
    if missing:
        raise ProductionDataContractError(
            f"PRODUCTION_PROVENANCE_MISSING: {table_name} missing fields {missing}."
        )

    confidence = record.get("confidence")
    if confidence is None:
        raise ProductionDataContractError(
            f"PRODUCTION_CONFIDENCE_MISSING: {table_name} requires confidence."
        )
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ProductionDataContractError(
            f"PRODUCTION_CONFIDENCE_INVALID: {table_name} confidence must be numeric."
        ) from exc
    if confidence_value < 0 or confidence_value > 1:
        raise ProductionDataContractError(
            f"PRODUCTION_CONFIDENCE_INVALID: {table_name} confidence must be between 0 and 1."
        )


# ============================================================
# 数据模型（v1 + v2 新增）
# ============================================================
@dataclass
class GPUPriceRecord:
    date: str
    provider: str
    gpu_model: str
    billing_type: str
    price_per_hour: float
    region: str = "US"
    source: str = ""
    def to_dict(self):
        return asdict(self)


@dataclass
class CAPEXRecord:
    quarter_end: str
    ticker: str
    company: str
    capex: float
    revenue: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    guidance_low: Optional[float] = None
    guidance_high: Optional[float] = None
    guidance_changed: bool = False
    source: str = "yahoo_finance"
    def to_dict(self):
        return asdict(self)


@dataclass
class OCPIRecord:
    date: str
    h100_ondemand: Optional[float] = None
    h100_1yr_contract: Optional[float] = None
    h100_spot_low: Optional[float] = None
    h100_spot_high: Optional[float] = None
    h100_spot_median: Optional[float] = None
    volatility_30d: Optional[float] = None
    source: str = ""
    def to_dict(self):
        return asdict(self)


@dataclass
class Signal:
    type: str
    severity: str
    message: str
    impact: str
    timestamp: str
    def to_dict(self):
        return asdict(self)


# ----- v2 新增数据模型 -----
@dataclass
class CAPEXGuidanceRecord:
    """季度/年度 CAPEX 指引记录（支持 revision 跟踪）"""
    quarter_end: str          # 指引对应的季度末
    ticker: str
    company: str
    guidance_low: float
    guidance_high: float
    guidance_mid: float
    guidance_type: str        # 'annual' | 'quarterly'
    fiscal_year: int
    source: str
    revised: bool = False
    previous_low: Optional[float] = None
    previous_high: Optional[float] = None
    revision_pct: Optional[float] = None
    announcement_date: Optional[str] = None
    def to_dict(self):
        return asdict(self)


@dataclass
class EarningsCalendarRecord:
    """财报日历"""
    ticker: str
    quarter: str              # e.g. "Q1 FY2026"
    quarter_end: str
    earnings_date: str
    report_type: str = "earnings"
    def to_dict(self):
        return asdict(self)


@dataclass
class CAPEXDailyImpliedRecord:
    """L2 Forward Curve: 指引线性摊薄到日度"""
    date: str
    ticker: str
    implied_daily: float      # 当日 implied run-rate ($B/day)
    implied_cumulative: float # 季度内累计 implied ($B)
    guidance_quarter: str     # 归属哪个 quarter_end
    source: str = "forward_curve"
    def to_dict(self):
        return asdict(self)


@dataclass
class CAPEXNowcastRecord:
    """L3 Nowcast: 高频代理指标推断的日度 CAPEX"""
    date: str
    ticker: str
    nowcast_value: float      # $B (日度年化或季度累计，这里采用日度 implied 口径)
    nowcast_method: str       # 'gpu_price_proxy' | 'mixed'
    confidence: float         # 0-1
    source: str = "nowcast"
    def to_dict(self):
        return asdict(self)


# ============================================================
# 数据库管理（v1 兼容 + v2 扩展）
# ============================================================
class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or get_default_db_path())
        try:
            self._init_tables()
        except Exception as exc:
            if isinstance(exc, SchemaMigrationError):
                raise
            raise SchemaMigrationError(f"SCHEMA_MIGRATION_FAILED: {exc}") from exc

    def _init_tables(self):
        """初始化数据库表结构（保留全部 v1 表，新增 v2 表）"""
        conn = duckdb.connect(self.db_path)

        # ---- v1 表（保持原样）----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gpu_prices_daily (
                date DATE, provider VARCHAR, gpu_model VARCHAR,
                billing_type VARCHAR, price_per_hour DOUBLE,
                region VARCHAR DEFAULT 'US', source VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capex_quarterly (
                quarter_end DATE, ticker VARCHAR, company VARCHAR,
                capex DOUBLE, revenue DOUBLE, operating_cash_flow DOUBLE,
                guidance_low DOUBLE, guidance_high DOUBLE,
                guidance_changed BOOLEAN DEFAULT FALSE,
                source VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ocpi_daily (
                date DATE, h100_ondemand DOUBLE, h100_1yr_contract DOUBLE,
                h100_spot_low DOUBLE, h100_spot_high DOUBLE,
                h100_spot_median DOUBLE, volatility_30d DOUBLE,
                source VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                timestamp TIMESTAMP, type VARCHAR, severity VARCHAR,
                message VARCHAR, impact VARCHAR, acknowledged BOOLEAN DEFAULT FALSE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS csi_history (
                date DATE, csi DOUBLE, gpu_z DOUBLE, capex_z DOUBLE,
                ocpi_z DOUBLE, regime VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ---- v2 新表 ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capex_guidance (
                quarter_end DATE, ticker VARCHAR, company VARCHAR,
                guidance_low DOUBLE, guidance_high DOUBLE, guidance_mid DOUBLE,
                guidance_type VARCHAR, fiscal_year INTEGER,
                source VARCHAR, revised BOOLEAN DEFAULT FALSE,
                previous_low DOUBLE, previous_high DOUBLE,
                revision_pct DOUBLE, announcement_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                ticker VARCHAR, quarter VARCHAR, quarter_end DATE,
                earnings_date DATE, report_type VARCHAR DEFAULT 'earnings',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capex_daily_implied (
                date DATE, ticker VARCHAR, implied_daily DOUBLE,
                implied_cumulative DOUBLE, guidance_quarter DATE,
                source VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capex_nowcast (
                date DATE, ticker VARCHAR, nowcast_value DOUBLE,
                nowcast_method VARCHAR, confidence DOUBLE,
                source VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._init_production_schema(conn)

        conn.close()
        print("✅ Database v2 initialized successfully")

    def _init_production_schema(self, conn):
        """生产数据合同表。legacy raw 表继续保留，但生产判断只读这些表。"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_gpu_prices (
                date DATE,
                provider VARCHAR,
                gpu_model VARCHAR,
                gpu_variant VARCHAR,
                billing_type VARCHAR,
                commitment VARCHAR,
                gpu_count INTEGER,
                region VARCHAR,
                price_per_gpu_hour DOUBLE,
                currency VARCHAR DEFAULT 'USD',
                availability_observed BOOLEAN,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_capex_actuals (
                ticker VARCHAR,
                company VARCHAR,
                period_start DATE,
                period_end DATE,
                fiscal_period VARCHAR,
                fiscal_year INTEGER,
                xbrl_tag VARCHAR,
                accession_no VARCHAR,
                capex_value DOUBLE,
                unit VARCHAR DEFAULT 'USD',
                filed_at DATE,
                form_type VARCHAR,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_official_events (
                ticker VARCHAR,
                announcement_date DATE,
                event_type VARCHAR,
                metric VARCHAR,
                value DOUBLE,
                unit VARCHAR,
                description VARCHAR,
                fiscal_period VARCHAR,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_public_proxy_prices (
                date DATE,
                provider VARCHAR,
                proxy_name VARCHAR,
                metric VARCHAR,
                value DOUBLE,
                unit VARCHAR,
                gpu_model VARCHAR,
                region VARCHAR,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_market_facts (
                date DATE,
                track VARCHAR,
                entity VARCHAR,
                sub_entity VARCHAR,
                metric VARCHAR,
                value DOUBLE,
                unit VARCHAR,
                dimension VARCHAR,
                vendor VARCHAR,
                source_name VARCHAR,
                notes VARCHAR,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_data_quality_events (
                event_id VARCHAR,
                table_name VARCHAR,
                severity VARCHAR,
                message VARCHAR,
                affected_key VARCHAR,
                is_blocking BOOLEAN,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_pipeline_runs (
                pipeline_name VARCHAR,
                status VARCHAR,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                rows_loaded INTEGER,
                message VARCHAR,
                run_id VARCHAR,
                source_id VARCHAR,
                source_url VARCHAR,
                snapshot_path VARCHAR,
                source_type VARCHAR,
                collection_method VARCHAR,
                observed_at TIMESTAMP,
                fetched_at TIMESTAMP,
                raw_payload_hash VARCHAR,
                is_production_eligible BOOLEAN,
                confidence DOUBLE,
                error_code VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE OR REPLACE VIEW production_gpu_prices_current AS
            SELECT *
            FROM production_gpu_prices
            WHERE is_production_eligible = TRUE
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW production_market_facts_canonical AS
            WITH ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            date, track, entity, sub_entity, metric, value, unit, dimension,
                            vendor, source_name, source_id
                        ORDER BY fetched_at DESC NULLS LAST, updated_at DESC, created_at DESC
                    ) AS canonical_rank
                FROM production_market_facts
            )
            SELECT
                * EXCLUDE (canonical_rank),
                CASE
                    WHEN is_production_eligible IS DISTINCT FROM TRUE THEN FALSE
                    WHEN lower(coalesce(vendor, '')) = 'runpod'
                         AND lower(coalesce(sub_entity, '')) LIKE '%mig%' THEN FALSE
                    WHEN lower(coalesce(metric, '')) LIKE '%price%' AND value <= 0 THEN FALSE
                    ELSE TRUE
                END AS eligible_for_analysis,
                CASE
                    WHEN is_production_eligible IS DISTINCT FROM TRUE THEN 'production_ineligible'
                    WHEN lower(coalesce(vendor, '')) = 'runpod'
                         AND lower(coalesce(sub_entity, '')) LIKE '%mig%' THEN 'runpod_mig_slice'
                    WHEN lower(coalesce(metric, '')) LIKE '%price%' AND value <= 0
                        THEN 'nonpositive_price'
                    ELSE NULL
                END AS analysis_exclusion_reason
            FROM ranked
            WHERE canonical_rank = 1
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW production_data_quality_events_latest AS
            SELECT * EXCLUDE (quality_rank)
            FROM (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY affected_key
                        ORDER BY fetched_at DESC NULLS LAST, updated_at DESC, created_at DESC
                    ) AS quality_rank
                FROM production_data_quality_events
            )
            WHERE quality_rank = 1
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW production_market_facts_analysis AS
            SELECT *
            FROM production_market_facts_canonical
            WHERE eligible_for_analysis = TRUE
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW canonical_market_observation AS
            WITH classified AS (
                SELECT
                    *,
                    CASE
                        WHEN track = 'gpu_rental'
                             AND lower(coalesce(dimension, '')) LIKE '%billing=%'
                             AND lower(coalesce(dimension, '')) LIKE '%variant=%'
                             AND lower(coalesce(dimension, '')) LIKE '%region=%'
                             AND lower(coalesce(dimension, '')) LIKE '%gpu_count=%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%variant=unknown%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%region=unknown%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%gpu_count=0%'
                            THEN 'daily'
                        WHEN track IN ('gpu_rental_trend', 'cloud_instance_price') THEN 'daily'
                        WHEN track = 'openrouter_usage' THEN 'weekly'
                        WHEN track IN ('token_price', 'app_commercialization',
                                       'multimodal_generation_cost', 'china_cloud_capex') THEN 'event'
                        WHEN track IN ('capex_actual', 'cloud_capex') THEN 'quarterly'
                        ELSE 'snapshot'
                    END AS natural_frequency,
                    CASE
                        WHEN track = 'gpu_rental'
                             AND lower(coalesce(dimension, '')) LIKE '%billing=%'
                             AND lower(coalesce(dimension, '')) LIKE '%variant=%'
                             AND lower(coalesce(dimension, '')) LIKE '%region=%'
                             AND lower(coalesce(dimension, '')) LIKE '%gpu_count=%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%variant=unknown%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%region=unknown%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%gpu_count=0%'
                            THEN 'time_series'
                        WHEN track IN ('gpu_rental_trend', 'cloud_instance_price',
                                       'openrouter_usage') THEN 'time_series'
                        WHEN track IN ('token_price', 'app_commercialization',
                                       'multimodal_generation_cost', 'china_cloud_capex',
                                       'capex_actual', 'cloud_capex') THEN 'event'
                        ELSE 'snapshot'
                    END AS observation_type
                    ,CASE
                        WHEN track = 'gpu_rental'
                             AND lower(coalesce(dimension, '')) LIKE '%billing=%'
                             AND lower(coalesce(dimension, '')) LIKE '%variant=%'
                             AND lower(coalesce(dimension, '')) LIKE '%region=%'
                             AND lower(coalesce(dimension, '')) LIKE '%gpu_count=%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%variant=unknown%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%region=unknown%'
                             AND lower(coalesce(dimension, '')) NOT LIKE '%gpu_count=0%'
                            THEN 'matched_venue_series'
                        WHEN track = 'openrouter_usage'
                             OR lower(coalesce(source_id, '')) LIKE '%frontend%'
                             OR lower(coalesce(dimension, '')) LIKE '%proxy%'
                            THEN 'public_proxy'
                        WHEN track = 'gpu_rental_trend' THEN 'aggregated_public_trend'
                        WHEN source_type = 'official' THEN 'official'
                        WHEN track IN ('token_price', 'model_value_score') THEN 'public_catalog'
                        ELSE 'source_backed_public'
                    END AS evidence_class
                FROM production_market_facts_analysis
            ), periodized AS (
                SELECT
                    *,
                    max(cast(fetched_at AS DATE)) OVER (
                        PARTITION BY source_id
                    ) AS source_latest_fetch_date
                FROM classified
            ), identified AS (
                SELECT
                    *,
                    CASE
                        WHEN natural_frequency = 'weekly' THEN
                            date + INTERVAL 6 DAY <= source_latest_fetch_date
                        ELSE TRUE
                    END AS period_complete,
                    'ser_' || substr(md5(concat_ws('|',
                        lower(coalesce(track, '')),
                        lower(coalesce(source_id, '')),
                        lower(coalesce(vendor, '')),
                        lower(coalesce(entity, '')),
                        lower(coalesce(sub_entity, '')),
                        lower(coalesce(metric, '')),
                        lower(coalesce(unit, '')),
                        lower(coalesce(dimension, ''))
                    )), 1, 20) AS series_id
                FROM periodized
            )
            SELECT
                'obs_' || substr(md5(concat_ws('|', series_id, cast(date AS VARCHAR),
                    cast(value AS VARCHAR), coalesce(source_url, ''),
                    coalesce(cast(fetched_at AS VARCHAR), ''))), 1, 24) AS observation_id,
                series_id,
                natural_frequency,
                observation_type,
                evidence_class,
                date, track, entity, sub_entity, metric, value, unit, dimension,
                vendor, source_name, notes, run_id, source_id, source_url,
                snapshot_path, source_type, collection_method, observed_at,
                fetched_at, raw_payload_hash, is_production_eligible, confidence,
                error_code, created_at, updated_at, period_complete
            FROM identified
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW canonical_observation AS
            SELECT * FROM canonical_market_observation
            UNION ALL
            SELECT
                'obs_' || substr(md5(concat_ws('|', 'capex_actual', ticker,
                    cast(period_end AS VARCHAR), cast(capex_value AS VARCHAR),
                    coalesce(accession_no, ''))), 1, 24) AS observation_id,
                'ser_' || substr(md5(concat_ws('|', 'cloud_capex_actual',
                    lower(coalesce(source_id, '')), lower(coalesce(ticker, '')),
                    lower(coalesce(xbrl_tag, '')), lower(coalesce(unit, '')))), 1, 20)
                    AS series_id,
                'quarterly' AS natural_frequency,
                'event' AS observation_type,
                'official' AS evidence_class,
                period_end AS date,
                'cloud_capex_actual' AS track,
                company AS entity,
                ticker AS sub_entity,
                xbrl_tag AS metric,
                capex_value AS value,
                unit,
                'quarterly_actual' AS dimension,
                company AS vendor,
                'SEC companyfacts' AS source_name,
                concat_ws('; ', fiscal_period, form_type, accession_no) AS notes,
                run_id, source_id, source_url, snapshot_path, source_type,
                collection_method, observed_at, fetched_at, raw_payload_hash,
                is_production_eligible, confidence, error_code, created_at, updated_at,
                TRUE AS period_complete
            FROM production_capex_actuals
            WHERE is_production_eligible = TRUE
            UNION ALL
            SELECT
                'obs_' || substr(md5(concat_ws('|', 'official_event', ticker,
                    cast(announcement_date AS VARCHAR), event_type, metric,
                    cast(value AS VARCHAR))), 1, 24) AS observation_id,
                'ser_' || substr(md5(concat_ws('|', 'cloud_official_event',
                    lower(coalesce(ticker, '')),
                    lower(coalesce(event_type, '')), lower(coalesce(metric, '')),
                    lower(coalesce(unit, '')))), 1, 20) AS series_id,
                'event' AS natural_frequency,
                'event' AS observation_type,
                'official' AS evidence_class,
                announcement_date AS date,
                'cloud_official_event' AS track,
                ticker AS entity,
                ticker AS sub_entity,
                metric,
                value,
                unit,
                event_type AS dimension,
                ticker AS vendor,
                'Official company disclosure' AS source_name,
                concat_ws('; ', fiscal_period, description) AS notes,
                run_id, source_id, source_url, snapshot_path, source_type,
                collection_method, observed_at, fetched_at, raw_payload_hash,
                is_production_eligible, confidence, error_code, created_at, updated_at,
                TRUE AS period_complete
            FROM production_official_events
            WHERE is_production_eligible = TRUE
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW series_definition AS
            SELECT
                series_id,
                track,
                source_id,
                vendor,
                entity,
                sub_entity,
                metric,
                unit,
                dimension,
                natural_frequency,
                observation_type,
                evidence_class,
                min(date) FILTER (WHERE period_complete) AS first_date,
                max(date) FILTER (WHERE period_complete) AS last_date,
                count(DISTINCT date) FILTER (WHERE period_complete) AS valid_dates,
                count(*) FILTER (WHERE period_complete) AS observation_count,
                count(DISTINCT source_url) AS source_url_count
            FROM canonical_observation
            GROUP BY
                series_id, track, source_id, vendor, entity, sub_entity, metric,
                unit, dimension, natural_frequency, observation_type, evidence_class
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW series_quality AS
            WITH stats AS (
                SELECT
                    *,
                    date_diff('day', first_date, last_date) AS span_days,
                    CASE
                        WHEN natural_frequency = 'daily' THEN
                            valid_dates::DOUBLE / greatest(date_diff('day', first_date, last_date) + 1, 1)
                        WHEN natural_frequency = 'weekly' THEN
                            valid_dates::DOUBLE / greatest(floor(date_diff('day', first_date, last_date) / 7) + 1, 1)
                        ELSE NULL
                    END AS coverage_ratio
                FROM series_definition
            ), chart_gate AS (
                SELECT
                    *,
                    CASE
                        WHEN track = 'gpu_rental'
                             AND evidence_class <> 'matched_venue_series' THEN FALSE
                        WHEN observation_type = 'event' THEN FALSE
                        WHEN observation_type = 'snapshot' THEN FALSE
                        WHEN natural_frequency = 'daily' AND valid_dates < 10 THEN FALSE
                        WHEN natural_frequency = 'weekly' AND valid_dates < 8 THEN FALSE
                        WHEN natural_frequency IN ('daily', 'weekly') AND coverage_ratio < 0.80 THEN FALSE
                        WHEN natural_frequency IN ('daily', 'weekly') THEN TRUE
                        ELSE FALSE
                    END AS eligible_for_chart,
                    CASE
                        WHEN track = 'gpu_rental'
                             AND evidence_class <> 'matched_venue_series'
                            THEN 'unstable_configuration'
                        WHEN observation_type = 'event' THEN 'event_series_only'
                        WHEN observation_type = 'snapshot' THEN 'snapshot_only'
                        WHEN natural_frequency = 'daily' AND valid_dates < 10 THEN 'insufficient_daily_history'
                        WHEN natural_frequency = 'weekly' AND valid_dates < 8 THEN 'insufficient_weekly_history'
                        WHEN natural_frequency IN ('daily', 'weekly') AND coverage_ratio < 0.80
                            THEN 'insufficient_coverage'
                        WHEN natural_frequency NOT IN ('daily', 'weekly') THEN 'unsupported_frequency'
                        ELSE NULL
                    END AS chart_reason_code
                FROM stats
            )
            SELECT
                *,
                CASE
                    WHEN NOT eligible_for_chart THEN FALSE
                    WHEN evidence_class = 'public_proxy' THEN FALSE
                    WHEN natural_frequency = 'daily'
                         AND valid_dates >= 20 AND span_days >= 24 AND coverage_ratio >= 0.80 THEN TRUE
                    WHEN natural_frequency = 'weekly'
                         AND valid_dates >= 12 AND span_days >= 77 AND coverage_ratio >= 0.80 THEN TRUE
                    ELSE FALSE
                END AS eligible_for_inflection,
                CASE
                    WHEN NOT eligible_for_chart THEN chart_reason_code
                    WHEN evidence_class = 'public_proxy' THEN 'proxy_not_inflection_eligible'
                    WHEN natural_frequency = 'daily'
                         AND (valid_dates < 20 OR span_days < 24) THEN 'insufficient_30d_history'
                    WHEN natural_frequency = 'weekly'
                         AND (valid_dates < 12 OR span_days < 77) THEN 'insufficient_12_week_history'
                    WHEN coverage_ratio < 0.80 THEN 'insufficient_coverage'
                    ELSE NULL
                END AS inflection_reason_code,
                CASE
                    WHEN eligible_for_chart AND evidence_class <> 'public_proxy'
                         AND natural_frequency = 'daily'
                         AND valid_dates >= 60 AND span_days >= 74 AND coverage_ratio >= 0.80
                        THEN TRUE
                    ELSE FALSE
                END AS eligible_for_90d,
                CASE
                    WHEN natural_frequency <> 'daily' THEN 'not_daily_series'
                    WHEN NOT eligible_for_chart THEN chart_reason_code
                    WHEN evidence_class = 'public_proxy' THEN 'proxy_not_inflection_eligible'
                    WHEN valid_dates < 60 OR span_days < 74 THEN 'insufficient_90d_history'
                    WHEN coverage_ratio < 0.80 THEN 'insufficient_coverage'
                    ELSE NULL
                END AS reason_90d_code
            FROM chart_gate
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW line_ready_observation AS
            SELECT
                c.series_id,
                c.date,
                median(c.value) AS value,
                min(c.value) AS value_min,
                max(c.value) AS value_max,
                count(*) AS observations_on_date,
                any_value(c.track) AS track,
                any_value(c.entity) AS entity,
                any_value(c.sub_entity) AS sub_entity,
                any_value(c.metric) AS metric,
                any_value(c.unit) AS unit,
                any_value(c.dimension) AS dimension,
                any_value(c.vendor) AS vendor,
                any_value(c.source_id) AS source_id,
                any_value(c.natural_frequency) AS natural_frequency
            FROM canonical_observation c
            JOIN series_quality q USING (series_id)
            WHERE q.eligible_for_chart = TRUE
              AND c.period_complete = TRUE
            GROUP BY c.series_id, c.date
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW event_observation AS
            WITH daily_event AS (
                SELECT
                    series_id,
                    date,
                    median(value) AS value,
                    count(*) AS observations_on_date,
                    any_value(track) AS track,
                    any_value(entity) AS entity,
                    any_value(sub_entity) AS sub_entity,
                    any_value(metric) AS metric,
                    any_value(unit) AS unit,
                    any_value(dimension) AS dimension,
                    any_value(vendor) AS vendor,
                    any_value(source_id) AS source_id,
                    max(source_url) AS source_url
                FROM canonical_observation
                WHERE observation_type = 'event'
                GROUP BY series_id, date
            ), sequenced AS (
                SELECT
                    *,
                    lag(value) OVER (PARTITION BY series_id ORDER BY date) AS prior_value
                FROM daily_event
            )
            SELECT
                'evt_' || substr(md5(concat_ws('|', series_id, cast(date AS VARCHAR),
                    cast(value AS VARCHAR))), 1, 24) AS event_id,
                series_id,
                date,
                CASE
                    WHEN prior_value IS NULL THEN 'initial_observation'
                    WHEN lower(metric) LIKE '%price%' THEN 'price_change'
                    ELSE 'value_change'
                END AS event_type,
                value,
                prior_value,
                CASE
                    WHEN prior_value IS NULL OR prior_value = 0 THEN NULL
                    ELSE round((value / prior_value - 1) * 100, 6)
                END AS change_pct,
                observations_on_date,
                track, entity, sub_entity, metric, unit, dimension, vendor,
                source_id, source_url
            FROM sequenced
            WHERE prior_value IS NULL OR value IS DISTINCT FROM prior_value
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW matched_panel_candidate AS
            SELECT
                series_id,
                track,
                source_id,
                vendor,
                entity AS gpu_family,
                sub_entity,
                metric,
                unit,
                dimension,
                first_date,
                last_date,
                valid_dates,
                coverage_ratio,
                evidence_class,
                CASE
                    WHEN track = 'gpu_rental_trend' THEN FALSE
                    WHEN track = 'gpu_rental' AND evidence_class <> 'matched_venue_series' THEN FALSE
                    WHEN track = 'gpu_rental' AND eligible_for_chart = TRUE THEN TRUE
                    ELSE FALSE
                END AS eligible_for_matched_panel,
                CASE
                    WHEN track = 'gpu_rental_trend' THEN 'aggregate_composition_not_fixed'
                    WHEN track = 'gpu_rental' AND evidence_class <> 'matched_venue_series'
                        THEN 'missing_exact_configuration'
                    WHEN track = 'gpu_rental' AND eligible_for_chart = FALSE
                        THEN chart_reason_code
                    WHEN track NOT IN ('gpu_rental', 'gpu_rental_trend')
                        THEN 'not_gpu_rental_series'
                    ELSE NULL
                END AS panel_reason_code
            FROM series_quality
            WHERE track IN ('gpu_rental', 'gpu_rental_trend')
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW matched_panel_member AS
            SELECT
                'panel_' || substr(md5(concat_ws('|', 'gpu_rental_trend',
                    lower(coalesce(gpu_family, '')),
                    lower(coalesce(unit, '')),
                    lower(coalesce(dimension, '')))), 1, 20) AS panel_id,
                gpu_family,
                series_id,
                source_id,
                vendor,
                sub_entity,
                metric,
                unit,
                dimension,
                first_date,
                last_date,
                valid_dates,
                coverage_ratio
            FROM matched_panel_candidate
            WHERE eligible_for_matched_panel = TRUE
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW matched_panel_index AS
            WITH member_values AS (
                SELECT
                    m.panel_id,
                    m.gpu_family,
                    m.series_id,
                    l.date,
                    l.value,
                    first_value(l.value) OVER (
                        PARTITION BY m.panel_id, m.series_id ORDER BY l.date
                    ) AS base_value
                FROM matched_panel_member m
                JOIN line_ready_observation l USING (series_id)
            ), normalized AS (
                SELECT
                    *,
                    100.0 * value / nullif(base_value, 0) AS normalized_value
                FROM member_values
            ), registry AS (
                SELECT
                    panel_id,
                    gpu_family,
                    count(*) AS panel_member_count,
                    count(DISTINCT source_id) AS panel_source_count,
                    string_agg(series_id, ',' ORDER BY series_id) AS member_series_ids
                FROM matched_panel_member
                GROUP BY panel_id, gpu_family
            ), panel_daily AS (
                SELECT
                    n.panel_id,
                    n.gpu_family,
                    n.date,
                    round(avg(n.normalized_value), 6) AS index_value,
                    r.panel_member_count,
                    r.panel_source_count,
                    count(DISTINCT n.series_id) AS observed_member_count,
                    count(DISTINCT n.series_id)::DOUBLE / r.panel_member_count AS coverage_ratio,
                    r.member_series_ids
                FROM normalized n
                JOIN registry r USING (panel_id, gpu_family)
                GROUP BY n.panel_id, n.gpu_family, n.date,
                         r.panel_member_count, r.panel_source_count, r.member_series_ids
            ), panel_history AS (
                SELECT
                    *,
                    count(*) OVER (PARTITION BY panel_id) AS valid_dates,
                    date_diff('day', min(date) OVER (PARTITION BY panel_id),
                        max(date) OVER (PARTITION BY panel_id)) AS span_days,
                    lag(index_value, 7) OVER (PARTITION BY panel_id ORDER BY date) AS value_7d_ago,
                    lag(index_value, 30) OVER (PARTITION BY panel_id ORDER BY date) AS value_30d_ago,
                    lag(index_value, 60) OVER (PARTITION BY panel_id ORDER BY date) AS value_90d_ago
                FROM panel_daily
                WHERE coverage_ratio >= 0.80
            )
            SELECT
                *,
                valid_dates >= 10 AS eligible_for_chart,
                valid_dates >= 20 AND span_days >= 24 AS eligible_for_inflection,
                valid_dates >= 60 AND span_days >= 74 AS eligible_for_90d,
                panel_member_count >= 3 AND panel_source_count >= 2
                    AS eligible_for_market_inference,
                CASE
                    WHEN panel_member_count < 2 THEN 'single_source_panel'
                    WHEN panel_member_count < 3 THEN 'insufficient_panel_members'
                    WHEN panel_source_count < 2 THEN 'insufficient_source_diversity'
                    ELSE NULL
                END AS panel_reason_code,
                CASE WHEN value_7d_ago IS NULL THEN NULL
                    ELSE round((index_value / value_7d_ago - 1) * 100, 6) END AS change_7d_pct,
                CASE WHEN value_30d_ago IS NULL THEN NULL
                    ELSE round((index_value / value_30d_ago - 1) * 100, 6) END AS change_30d_pct,
                CASE WHEN value_90d_ago IS NULL THEN NULL
                    ELSE round((index_value / value_90d_ago - 1) * 100, 6) END AS change_90d_pct
            FROM panel_history
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW source_collection_policy AS
            SELECT *
            FROM (VALUES
                ('gpuperhour_daily', 'gpuperhour-offers-%', 'daily', 24, 36, 'core',
                 'forward_snapshot', 'exact GPU offer and depth'),
                ('runpod_daily', 'runpod-gpu-types', 'daily', 24, 36, 'core',
                 'forward_snapshot', 'RunPod price and capacity'),
                ('vast_daily', 'vast-bundles-on-demand-verified', 'daily', 24, 36, 'core',
                 'forward_snapshot', 'Vast verified offer depth'),
                ('computeprices_gpu_daily', 'computeprices-gpu-prices', 'daily', 24, 48,
                 'secondary', 'forward_snapshot', 'public GPU price catalog'),
                ('computeprices_trend_daily', 'computeprices-trend-%', 'daily', 24, 48,
                 'secondary', 'limited_backfill', 'source-published aggregate trend'),
                ('azure_daily', 'azure-retail-prices-gpu', 'daily', 24, 72, 'secondary',
                 'forward_snapshot', 'official Azure VM list price'),
                ('aws_spot_daily', 'aws-ec2-current-spot', 'daily', 24, 72, 'secondary',
                 'forward_snapshot', 'official AWS current spot snapshot'),
                ('openrouter_frontend_weekly', 'openrouter-frontend-rankings-%', 'weekly',
                 168, 216, 'secondary', 'limited_backfill', 'public activity proxy'),
                ('openrouter_models_daily', 'openrouter-models', 'daily', 24, 72,
                 'secondary', 'forward_snapshot', 'model price catalog'),
                ('litellm_catalog_daily', 'litellm-model-prices', 'daily', 24, 72,
                 'secondary', 'git_history_possible', 'model price catalog'),
                ('models_dev_daily', 'models-dev-api', 'daily', 24, 72, 'secondary',
                 'forward_snapshot', 'model price catalog')
            ) AS policy(
                policy_id, source_id_pattern, natural_frequency,
                expected_interval_hours, stale_after_hours, criticality,
                history_strategy, purpose
            )
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW source_freshness AS
            WITH observed AS (
                SELECT
                    p.policy_id,
                    p.source_id_pattern,
                    p.natural_frequency,
                    p.expected_interval_hours,
                    p.stale_after_hours,
                    p.criticality,
                    p.history_strategy,
                    p.purpose,
                    max(c.fetched_at) AS latest_fetched_at,
                    max(c.date) AS latest_observation_date,
                    count(DISTINCT c.source_id) AS matched_source_ids,
                    count(*) AS observation_rows
                FROM source_collection_policy p
                LEFT JOIN canonical_market_observation c
                  ON lower(c.source_id) LIKE lower(p.source_id_pattern)
                GROUP BY
                    p.policy_id, p.source_id_pattern, p.natural_frequency,
                    p.expected_interval_hours, p.stale_after_hours, p.criticality,
                    p.history_strategy, p.purpose
            )
            SELECT
                *,
                CASE WHEN latest_fetched_at IS NULL THEN NULL
                    ELSE date_diff('hour', latest_fetched_at,
                        current_timestamp AT TIME ZONE 'UTC') END AS age_hours,
                CASE
                    WHEN latest_fetched_at IS NULL THEN 'missing'
                    WHEN date_diff('hour', latest_fetched_at,
                        current_timestamp AT TIME ZONE 'UTC') > stale_after_hours
                        THEN 'stale'
                    ELSE 'fresh'
                END AS status,
                CASE
                    WHEN latest_fetched_at IS NULL THEN 'no_successful_observation'
                    WHEN date_diff('hour', latest_fetched_at, current_timestamp) > stale_after_hours
                        THEN 'source_stale'
                    ELSE NULL
                END AS reason_code
            FROM observed
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW pipeline_health_latest AS
            SELECT * EXCLUDE (run_rank)
            FROM (
                SELECT
                    *,
                    row_number() OVER (
                        PARTITION BY pipeline_name
                        ORDER BY completed_at DESC NULLS LAST, created_at DESC
                    ) AS run_rank
                FROM production_pipeline_runs
            )
            WHERE run_rank = 1
        """)
        conn.execute("""
            CREATE OR REPLACE VIEW series_collection_gap AS
            SELECT
                series_id,
                track,
                source_id,
                vendor,
                entity,
                sub_entity,
                metric,
                natural_frequency,
                valid_dates,
                first_date,
                last_date,
                span_days,
                coverage_ratio,
                eligible_for_chart,
                chart_reason_code,
                date_diff('day', last_date, current_date) AS days_since_last_observation,
                CASE
                    WHEN last_date IS NULL THEN 'missing'
                    WHEN natural_frequency = 'daily'
                         AND date_diff('day', last_date, current_date) > 2 THEN 'stale'
                    WHEN natural_frequency = 'weekly'
                         AND date_diff('day', last_date, current_date) > 9 THEN 'stale'
                    WHEN coverage_ratio IS NOT NULL AND coverage_ratio < 0.80 THEN 'gapped'
                    ELSE 'current'
                END AS collection_status
            FROM series_quality
            WHERE observation_type = 'time_series'
        """)

    def get_connection(self):
        return duckdb.connect(self.db_path)

    def _normalise_production_records(self, records: List[Any], table_name: str) -> List[Dict[str, Any]]:
        rows = []
        for record in records:
            row = record.to_dict() if hasattr(record, "to_dict") else dict(record)
            validate_production_provenance(row, table_name)
            missing_key_fields = [
                field for field in PRODUCTION_UPSERT_KEYS[table_name] if field not in row
            ]
            if missing_key_fields:
                raise ProductionDataContractError(
                    f"PRODUCTION_UPSERT_KEY_MISSING: {table_name} missing key fields "
                    f"{missing_key_fields}."
                )
            rows.append(row)
        return rows

    def _delete_by_production_key(self, conn, table_name: str, row: Dict[str, Any]) -> None:
        clauses = []
        params = []
        for field in PRODUCTION_UPSERT_KEYS[table_name]:
            clauses.append(f"({field} = ? OR ({field} IS NULL AND ? IS NULL))")
            params.extend([row.get(field), row.get(field)])
        conn.execute(f"DELETE FROM {table_name} WHERE {' AND '.join(clauses)}", params)

    def _insert_production_records(self, table_name: str, records: List[Any]) -> int:
        rows = self._normalise_production_records(records, table_name)
        if not rows:
            return 0

        conn = self.get_connection()
        columns = PRODUCTION_TABLE_COLUMNS[table_name]
        insert_columns = [col for col in columns if col not in {"created_at", "updated_at"}]
        placeholders = ", ".join(["?"] * len(insert_columns))
        column_sql = ", ".join(insert_columns)
        try:
            for row in rows:
                self._delete_by_production_key(conn, table_name, row)
                values = [row.get(col) for col in insert_columns]
                conn.execute(
                    f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
                    values,
                )
        finally:
            conn.close()
        return len(rows)

    def insert_production_gpu_prices(self, records: List[Any]) -> int:
        return self._insert_production_records("production_gpu_prices", records)

    def insert_production_capex_actuals(self, records: List[Any]) -> int:
        return self._insert_production_records("production_capex_actuals", records)

    def insert_production_official_events(self, records: List[Any]) -> int:
        return self._insert_production_records("production_official_events", records)

    def insert_production_public_proxy_prices(self, records: List[Any]) -> int:
        return self._insert_production_records("production_public_proxy_prices", records)

    def insert_production_market_facts(self, records: List[Any]) -> int:
        return self._insert_production_records("production_market_facts", records)

    def insert_production_data_quality_events(self, records: List[Any]) -> int:
        return self._insert_production_records("production_data_quality_events", records)

    def insert_production_pipeline_runs(self, records: List[Any]) -> int:
        return self._insert_production_records("production_pipeline_runs", records)

    def reset_production_tables(self) -> Dict[str, int]:
        """只清空 production_* 表；legacy/demo 表保留给回归测试和演示。"""
        conn = self.get_connection()
        deleted_counts = {}
        try:
            for table in PRODUCTION_TABLES:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.execute(f"DELETE FROM {table}")
                deleted_counts[table] = int(count)
        finally:
            conn.close()
        return deleted_counts

    def get_production_gpu_prices(
        self,
        gpu_model: Optional[str] = None,
        provider: Optional[str] = None,
        date: Optional[str] = None,
        eligible_only: bool = True,
    ) -> pd.DataFrame:
        """生产查询只读 production_gpu_prices，不回退 legacy seed 表。"""
        clauses = []
        params = []
        if eligible_only:
            clauses.append("is_production_eligible = TRUE")
        if gpu_model:
            clauses.append("gpu_model = ?")
            params.append(gpu_model)
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if date:
            clauses.append("date = CAST(? AS DATE)")
            params.append(date)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = self.get_connection()
        try:
            return conn.execute(
                f"""
                SELECT *
                FROM production_gpu_prices
                {where_sql}
                ORDER BY date, provider, gpu_model, gpu_variant, billing_type, source_url
                """,
                params,
            ).df()
        finally:
            conn.close()

    def get_source_type_quality_counts(self) -> pd.DataFrame:
        conn = self.get_connection()
        rows = []
        legacy_tables = [
            "gpu_prices_daily",
            "capex_quarterly",
            "ocpi_daily",
            "capex_guidance",
            "capex_daily_implied",
            "capex_nowcast",
        ]
        try:
            for table in legacy_tables:
                source_counts = conn.execute(f"""
                    SELECT
                        COALESCE(NULLIF(CAST(source AS VARCHAR), ''), 'legacy_unclassified') AS source_type,
                        COUNT(*) AS row_count
                    FROM {table}
                    GROUP BY 1
                    ORDER BY 1
                """).fetchall()
                for source_type, row_count in source_counts:
                    rows.append({
                        "table_name": table,
                        "source_type": source_type,
                        "row_count": row_count,
                        "eligible_count": None,
                        "path": "legacy_raw",
                    })

            for table in PRODUCTION_TABLES:
                source_counts = conn.execute(f"""
                    SELECT
                        COALESCE(NULLIF(source_type, ''), 'production_unclassified') AS source_type,
                        COUNT(*) AS row_count,
                        SUM(CASE WHEN is_production_eligible THEN 1 ELSE 0 END) AS eligible_count
                    FROM {table}
                    GROUP BY 1
                    ORDER BY 1
                """).fetchall()
                for source_type, row_count, eligible_count in source_counts:
                    rows.append({
                        "table_name": table,
                        "source_type": source_type,
                        "row_count": row_count,
                        "eligible_count": eligible_count,
                        "path": "production",
                    })
        finally:
            conn.close()
        return pd.DataFrame(rows, columns=[
            "path", "table_name", "source_type", "row_count", "eligible_count"
        ])

    # ---- v1 兼容插入方法 ----
    def insert_gpu_prices(self, records: List[GPUPriceRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("DELETE FROM gpu_prices_daily WHERE date IN (SELECT DISTINCT CAST(date AS DATE) FROM df)")
            conn.execute("""
                INSERT INTO gpu_prices_daily (date, provider, gpu_model, billing_type, price_per_hour, region, source)
                SELECT date, provider, gpu_model, billing_type, price_per_hour, region, source FROM df
            """)
        conn.close()

    def insert_capex(self, records: List[CAPEXRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("DELETE FROM capex_quarterly WHERE quarter_end IN (SELECT DISTINCT CAST(quarter_end AS DATE) FROM df) AND ticker IN (SELECT DISTINCT ticker FROM df)")
            conn.execute("""
                INSERT INTO capex_quarterly (quarter_end, ticker, company, capex, revenue, operating_cash_flow, guidance_low, guidance_high, guidance_changed, source)
                SELECT quarter_end, ticker, company, capex, revenue, operating_cash_flow, guidance_low, guidance_high, guidance_changed, source FROM df
            """)
        conn.close()

    def insert_ocpi(self, records: List[OCPIRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("DELETE FROM ocpi_daily WHERE date IN (SELECT DISTINCT CAST(date AS DATE) FROM df)")
            conn.execute("""
                INSERT INTO ocpi_daily (date, h100_ondemand, h100_1yr_contract, h100_spot_low, h100_spot_high, h100_spot_median, volatility_30d, source)
                SELECT date, h100_ondemand, h100_1yr_contract, h100_spot_low, h100_spot_high, h100_spot_median, volatility_30d, source FROM df
            """)
        conn.close()

    def insert_signals(self, signals: List[Signal]):
        conn = self.get_connection()
        df = pd.DataFrame([s.to_dict() for s in signals])
        if not df.empty:
            conn.execute("DELETE FROM signals WHERE date(timestamp) = CURRENT_DATE")
            conn.execute("""
                INSERT INTO signals (timestamp, type, severity, message, impact)
                SELECT timestamp, type, severity, message, impact FROM df
            """)
        conn.close()

    def insert_csi(self, date: str, csi: float, gpu_z: float, capex_z: float,
                   ocpi_z: float, regime: str):
        conn = self.get_connection()
        conn.execute("DELETE FROM csi_history WHERE date = CAST(? AS DATE)", [date])
        conn.execute("""
            INSERT INTO csi_history (date, csi, gpu_z, capex_z, ocpi_z, regime)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [date, csi, gpu_z, capex_z, ocpi_z, regime])
        conn.close()

    # ---- v2 新插入方法 ----
    def insert_capex_guidance(self, records: List[CAPEXGuidanceRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("DELETE FROM capex_guidance WHERE quarter_end IN (SELECT DISTINCT CAST(quarter_end AS DATE) FROM df) AND ticker IN (SELECT DISTINCT ticker FROM df)")
            conn.execute("""
                INSERT INTO capex_guidance (quarter_end, ticker, company, guidance_low, guidance_high, guidance_mid,
                    guidance_type, fiscal_year, source, revised, previous_low, previous_high, revision_pct, announcement_date)
                SELECT quarter_end, ticker, company, guidance_low, guidance_high, guidance_mid,
                    guidance_type, fiscal_year, source, revised, previous_low, previous_high, revision_pct, announcement_date
                FROM df
            """)
        conn.close()

    def insert_earnings_calendar(self, records: List[EarningsCalendarRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("DELETE FROM earnings_calendar WHERE quarter_end IN (SELECT DISTINCT CAST(quarter_end AS DATE) FROM df) AND ticker IN (SELECT DISTINCT ticker FROM df)")
            conn.execute("""
                INSERT INTO earnings_calendar (ticker, quarter, quarter_end, earnings_date, report_type)
                SELECT ticker, quarter, quarter_end, earnings_date, report_type FROM df
            """)
        conn.close()

    def insert_capex_daily_implied(self, records: List[CAPEXDailyImpliedRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("""
                INSERT INTO capex_daily_implied (date, ticker, implied_daily, implied_cumulative, guidance_quarter, source)
                SELECT date, ticker, implied_daily, implied_cumulative, guidance_quarter, source FROM df
            """)
        conn.close()

    def insert_capex_nowcast(self, records: List[CAPEXNowcastRecord]):
        conn = self.get_connection()
        df = pd.DataFrame([r.to_dict() for r in records])
        if not df.empty:
            conn.execute("""
                INSERT INTO capex_nowcast (date, ticker, nowcast_value, nowcast_method, confidence, source)
                SELECT date, ticker, nowcast_value, nowcast_method, confidence, source FROM df
            """)
        conn.close()

    def clear_capex_daily_implied(self, guidance_quarter: Optional[str] = None):
        """清空 implied 表以便重建（可选按 quarter 过滤）"""
        conn = self.get_connection()
        if guidance_quarter:
            conn.execute("DELETE FROM capex_daily_implied WHERE guidance_quarter = ?", [guidance_quarter])
        else:
            conn.execute("DELETE FROM capex_daily_implied")
        conn.close()

    def clear_capex_nowcast(self):
        conn = self.get_connection()
        conn.execute("DELETE FROM capex_nowcast")
        conn.close()


# ============================================================
# 数据采集器（v1 兼容 + v2 扩展）
# ============================================================
class GPUCollector:
    """GPU 价格与 CAPEX 数据采集器（v1 逻辑，v2 兼容）"""

    @staticmethod
    def fetch_yahoo_finance_capex(ticker: str) -> Optional[CAPEXRecord]:
        try:
            stock = yf.Ticker(ticker)
            cf = stock.quarterly_cash_flow
            if cf is None or cf.empty:
                return None
            capex_key = None
            for key in cf.index:
                if "Capital Expenditure" in key or "CapEx" in key:
                    capex_key = key
                    break
            if capex_key is None:
                return None
            latest_col = cf.columns[0]
            capex_val = cf.loc[capex_key, latest_col]
            income = stock.quarterly_income_stmt
            revenue = None
            if income is not None and not income.empty:
                for key in income.index:
                    if "Total Revenue" in key or "Revenue" in key:
                        revenue = income.loc[key, latest_col]
                        break
            ocf = None
            if "Operating Cash Flow" in cf.index:
                ocf = cf.loc["Operating Cash Flow", latest_col]
            quarter_end = latest_col.strftime("%Y-%m-%d") if hasattr(latest_col, 'strftime') else str(latest_col)[:10]
            return CAPEXRecord(
                quarter_end=quarter_end, ticker=ticker,
                company=HYPERSCALERS.get(ticker, {}).get("name", ticker),
                capex=abs(capex_val) / 1e9,
                revenue=revenue / 1e9 if revenue else None,
                operating_cash_flow=ocf / 1e9 if ocf else None,
                source="yahoo_finance"
            )
        except Exception as e:
            print(f"⚠️  Failed to fetch CAPEX for {ticker}: {e}")
            return None

    @staticmethod
    def fetch_all_capex() -> List[CAPEXRecord]:
        records = []
        for ticker in HYPERSCALERS.keys():
            print(f"Fetching CAPEX for {ticker}...")
            record = GPUCollector.fetch_yahoo_finance_capex(ticker)
            if record:
                records.append(record)
        return records

    @staticmethod
    def fetch_capex_history(ticker: str, periods: int = 8) -> pd.DataFrame:
        try:
            stock = yf.Ticker(ticker)
            cf = stock.quarterly_cash_flow
            if cf is None or cf.empty:
                return pd.DataFrame()
            capex_key = None
            for key in cf.index:
                if "Capital Expenditure" in key:
                    capex_key = key
                    break
            if capex_key is None:
                return pd.DataFrame()
            data = []
            for col in cf.columns[:periods]:
                val = cf.loc[capex_key, col]
                qe = col.strftime("%Y-%m-%d") if hasattr(col, 'strftime') else str(col)[:10]
                data.append({
                    "quarter_end": qe, "ticker": ticker,
                    "company": HYPERSCALERS.get(ticker, {}).get("name", ticker),
                    "capex": abs(val) / 1e9
                })
            return pd.DataFrame(data)
        except Exception as e:
            print(f"⚠️  Failed to fetch CAPEX history for {ticker}: {e}")
            return pd.DataFrame()

    @staticmethod
    def fetch_gpu_price_from_providers() -> List[GPUPriceRecord]:
        today = datetime.now().strftime("%Y-%m-%d")
        records = []
        reference_prices = {
            ("CoreWeave", "H100", "on-demand"): 6.155,
            ("CoreWeave", "H100", "spot"): 2.438,
            ("Lambda", "H100", "on-demand"): 2.49,
            ("RunPod", "H100", "on-demand"): 2.69,
            ("Vast.ai", "H100", "on-demand"): 1.99,
            ("Azure", "H100", "on-demand"): 10.00,
            ("AWS", "H100", "on-demand"): 8.50,
            ("Google Cloud", "H100", "on-demand"): 9.00,
            ("CoreWeave", "A100", "on-demand"): 2.70,
            ("CoreWeave", "H200", "on-demand"): 6.305,
            ("CoreWeave", "B200", "on-demand"): 8.60,
        }
        for (provider, model, billing), price in reference_prices.items():
            records.append(GPUPriceRecord(
                date=today, provider=provider, gpu_model=model,
                billing_type=billing, price_per_hour=price,
                region="US", source="direct_pricing"
            ))
        return records

    @staticmethod
    def fetch_ocpi_public() -> OCPIRecord:
        """DEMO/LEGACY ONLY: production must not use this hardcoded OCPI sample."""
        today = datetime.now().strftime("%Y-%m-%d")
        return OCPIRecord(
            date=today, h100_ondemand=2.99, h100_1yr_contract=2.35,
            h100_spot_low=1.38, h100_spot_high=11.01, h100_spot_median=2.20,
            volatility_30d=0.15, source="composite_public"
        )


# ============================================================
# v2 频率对齐引擎（核心升级）
# ============================================================
class FrequencyAlignmentEngine:
    """
    三层频率对齐架构：
      L1 Raw       : CAPEX actuals + guidance（季度事件节点）
      L2 Forward   : guidance 线性摊薄到日度（implied run-rate）
      L3 Nowcast   : 高频代理指标构建日度 nowcast
    """

    def __init__(self, db: Database):
        self.db = db

    # ---------- L2: Forward Curve ----------
    def build_forward_curve(self, days_in_quarter: int = 90, days_in_year: int = 365) -> List[CAPEXDailyImpliedRecord]:
        """
        将 capex_guidance 表中的 guidance 线性摊薄到每日。
        区分 annual / quarterly guidance：
          - annual  : 按全年 365 天均匀摊薄
          - quarterly: 按季度 90 天均匀摊薄
        """
        conn = self.db.get_connection()
        guidance_df = conn.execute("""
            SELECT quarter_end, ticker, guidance_mid, guidance_type
            FROM capex_guidance
            WHERE guidance_mid IS NOT NULL
            ORDER BY quarter_end, ticker
        """).df()
        conn.close()

        if guidance_df.empty:
            print("⚠️  No guidance data found for forward curve. Skipping L2.")
            return []

        records = []
        for _, row in guidance_df.iterrows():
            q_end = pd.to_datetime(row['quarter_end'])
            gtype = row.get('guidance_type', 'quarterly')

            if gtype == 'annual':
                period_days = days_in_year
                q_start = q_end - timedelta(days=days_in_quarter - 1)
            else:
                period_days = days_in_quarter
                q_start = q_end - timedelta(days=days_in_quarter - 1)

            daily_rate = row['guidance_mid'] / period_days

            for i in range(period_days):
                d = q_start + timedelta(days=i)
                records.append(CAPEXDailyImpliedRecord(
                    date=d.strftime("%Y-%m-%d"),
                    ticker=row['ticker'],
                    implied_daily=round(daily_rate, 6),
                    implied_cumulative=round(daily_rate * (i + 1), 6),
                    guidance_quarter=row['quarter_end'].strftime("%Y-%m-%d") if hasattr(row['quarter_end'], 'strftime') else str(row['quarter_end'])[:10],
                    source="forward_curve"
                ))

        return records

    def rebuild_forward_curve(self, days_in_quarter: int = 90, days_in_year: int = 365):
        """重建整张 forward curve（先清空再插入）"""
        print("🏗️  Rebuilding L2 Forward Curve...")
        self.db.clear_capex_daily_implied()
        records = self.build_forward_curve(days_in_quarter=days_in_quarter, days_in_year=days_in_year)
        if records:
            self.db.insert_capex_daily_implied(records)
            print(f"   Inserted {len(records):,} L2 daily implied records")
        return records
    # ---------- L3: Nowcast ----------
    def build_nowcast(self, lookback_days: int = 30) -> List[CAPEXNowcastRecord]:
        """
        用 GPU 价格趋势作为 CAPEX 的日度代理指标（简化版 nowcast）。
        逻辑：
          1. 取各 ticker 最新季度的 actual CAPEX 作为 baseline。
          2. 用最近 lookback_days GPU 价格变化率作为 momentum 调整因子。
          3. nowcast = baseline * (1 + gpu_momentum * sensitivity)，
             sensitivity 设为 0.5（GPU 价格每变化 10%，CAPEX nowcast 调整 5%）。
        """
        conn = self.db.get_connection()

        # 1. 每个 ticker 最新季度 actual
        baseline_df = conn.execute("""
            SELECT ticker, quarter_end, capex
            FROM capex_quarterly
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY quarter_end DESC) = 1
        """).df()

        # 2. 最近日度 GPU 价格（H100 on-demand 中位数）
        gpu_df = conn.execute(f"""
            SELECT date, AVG(price_per_hour) as median_price
            FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
            GROUP BY date
            ORDER BY date
        """).df()

        conn.close()

        if baseline_df.empty or gpu_df.empty:
            print("⚠️  Insufficient data for nowcast. Skipping L3.")
            return []

        gpu_df['date'] = pd.to_datetime(gpu_df['date'])
        gpu_df = gpu_df.sort_values('date')
        gpu_df['price_ma_short'] = gpu_df['median_price'].rolling(window=7, min_periods=1).mean()
        gpu_df['price_ma_long'] = gpu_df['median_price'].rolling(window=lookback_days, min_periods=1).mean()
        gpu_df['momentum'] = (gpu_df['price_ma_short'] - gpu_df['price_ma_long']) / gpu_df['price_ma_long'].replace(0, np.nan)
        gpu_df['momentum'] = gpu_df['momentum'].fillna(0)

        # 只对最近 90 天生成 nowcast
        recent_dates = gpu_df[gpu_df['date'] >= (gpu_df['date'].max() - timedelta(days=90))].copy()

        records = []
        sensitivity = 0.5  # GPU 价格变化 10% → CAPEX 调整 5%

        for _, base in baseline_df.iterrows():
            ticker = base['ticker']
            baseline_capex = base['capex']  # quarterly actual
            baseline_daily = baseline_capex / 90.0  # 转为日度口径

            for _, g in recent_dates.iterrows():
                momentum = g['momentum']
                adjustment = 1 + momentum * sensitivity
                nowcast_val = baseline_daily * adjustment
                # confidence 随 momentum 绝对值增大而降低（偏离越大越不确定）
                confidence = max(0.3, 1.0 - abs(momentum))

                records.append(CAPEXNowcastRecord(
                    date=g['date'].strftime("%Y-%m-%d"),
                    ticker=ticker,
                    nowcast_value=round(nowcast_val, 6),
                    nowcast_method="gpu_price_proxy",
                    confidence=round(confidence, 3),
                    source="nowcast"
                ))

        return records

    def rebuild_nowcast(self):
        print("🔮 Rebuilding L3 Nowcast...")
        self.db.clear_capex_nowcast()
        records = self.build_nowcast()
        if records:
            self.db.insert_capex_nowcast(records)
            print(f"   Inserted {len(records):,} L3 nowcast records")
        return records

    # ---------- 频率对齐总入口 ----------
    def align_all(self):
        """执行完整的 L1→L2→L3 频率对齐流程"""
        conn = self.db.get_connection()
        conn.execute("DELETE FROM capex_daily_implied")
        conn.execute("DELETE FROM capex_nowcast")
        conn.close()
        self.rebuild_forward_curve()
        self.rebuild_nowcast()
        print("✅ Frequency alignment complete (L1 Raw + L2 Forward + L3 Nowcast)")


# ============================================================
# v2 分析引擎（CSI + 领先/滞后 + Forward Gap）
# ============================================================
class AnalysisEngine:
    def __init__(self, db: Database):
        self.db = db

    def calculate_csi(self) -> Dict:
        """legacy/demo only: mixed-frequency CSI is not used for production decision."""
        conn = self.db.get_connection()

        gpu_df = conn.execute("""
            SELECT date, AVG(price_per_hour) as median_price
            FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
            GROUP BY date
            ORDER BY date DESC LIMIT 90
        """).df()

        gpu_z = 0.0
        if len(gpu_df) >= 30:
            recent = gpu_df['median_price'].iloc[0]
            mean = gpu_df['median_price'].mean()
            std = gpu_df['median_price'].std()
            if std > 0:
                gpu_z = (recent - mean) / std

        capex_df = conn.execute("""
            SELECT quarter_end, SUM(capex) as total_capex
            FROM capex_quarterly
            GROUP BY quarter_end
            ORDER BY quarter_end DESC LIMIT 8
        """).df()

        capex_z = 0.0
        if len(capex_df) >= 4:
            recent = capex_df['total_capex'].iloc[0]
            prev = capex_df['total_capex'].iloc[3]
            if prev > 0:
                yoy_growth = (recent - prev) / prev
                capex_z = (yoy_growth - 0.5) / 0.5

        ocpi_df = conn.execute("""
            SELECT date, h100_ondemand FROM ocpi_daily
            ORDER BY date DESC LIMIT 90
        """).df()

        ocpi_z = 0.0
        if len(ocpi_df) >= 30:
            prices = ocpi_df['h100_ondemand'].dropna()
            if len(prices) >= 2:
                returns = prices.pct_change().dropna()
                volatility = returns.std() * np.sqrt(30)
                ocpi_z = (volatility - 0.10) / 0.05

        conn.close()

        raw_score = 0.40 * gpu_z + 0.35 * capex_z + 0.25 * ocpi_z
        csi = 50 + raw_score * 16.67
        csi = max(0, min(100, csi))
        regime = "High Scarcity" if csi > 70 else "Scarcity Easing" if csi < 40 else "Neutral"

        return {
            "csi": round(csi, 2), "gpu_z": round(gpu_z, 2),
            "capex_z": round(capex_z, 2), "ocpi_z": round(ocpi_z, 2),
            "regime": regime, "timestamp": datetime.now().isoformat()
        }

    # ---------- v2 新增：领先/滞后分析 ----------
    def calculate_lead_lag(self) -> Dict:
        """
        计算两个领先/滞后关系：
          A) CAPEX guidance revision → GPU price change 的领先期
          B) GPU price trend → 下一季度 CAPEX guidance 的预测力
        返回 dict，包含最优滞后天数和相关性。
        """
        conn = self.db.get_connection()

        # 获取 guidance revision 事件
        rev_df = conn.execute("""
            SELECT announcement_date, ticker, revision_pct
            FROM capex_guidance
            WHERE revised = TRUE AND announcement_date IS NOT NULL
            ORDER BY announcement_date
        """).df()

        # 获取日度 GPU 价格
        gpu_df = conn.execute("""
            SELECT date, AVG(price_per_hour) as median_price
            FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
            GROUP BY date ORDER BY date
        """).df()

        conn.close()

        result = {
            "guidance_to_gpu": {"optimal_lag_days": None, "correlation": None, "interpretation": ""},
            "gpu_to_guidance": {"correlation": None, "interpretation": ""},
            "note": ""
        }

        if rev_df.empty or gpu_df.empty or len(rev_df) < 2:
            result["note"] = "Insufficient guidance revision or GPU price data for lead-lag analysis."
            return result

        rev_df['announcement_date'] = pd.to_datetime(rev_df['announcement_date'])
        gpu_df['date'] = pd.to_datetime(gpu_df['date'])
        gpu_df = gpu_df.sort_values('date')
        gpu_df['returns'] = gpu_df['median_price'].pct_change()

        # ---- A) Guidance revision → GPU price ----
        # 对每个 revision event，看之后 30/60/90 天的 GPU cumulative return
        lags = [30, 60, 90]
        best_corr = -999
        best_lag = None

        for lag in lags:
            rows = []
            for _, rev in rev_df.iterrows():
                start = rev['announcement_date']
                end = start + timedelta(days=lag)
                mask = (gpu_df['date'] > start) & (gpu_df['date'] <= end)
                subset = gpu_df.loc[mask, 'returns'].dropna()
                if len(subset) > 0:
                    cum_ret = (1 + subset).prod() - 1
                    rows.append({"revision_pct": rev['revision_pct'], "gpu_cumret": cum_ret})
            if len(rows) >= 3:
                df_tmp = pd.DataFrame(rows)
                corr = df_tmp['revision_pct'].corr(df_tmp['gpu_cumret'])
                if pd.notna(corr) and abs(corr) > abs(best_corr):
                    best_corr = corr
                    best_lag = lag

        if best_lag is not None:
            result["guidance_to_gpu"] = {
                "optimal_lag_days": best_lag,
                "correlation": round(best_corr, 3),
                "interpretation": (
                    f"CAPEX guidance revision 领先 GPU 价格变化约 {best_lag} 天，"
                    f"相关系数 {best_corr:.3f}。"
                    f"{'上调指引后 GPU 价格趋于上涨' if best_corr > 0 else '上调指引后 GPU 价格反而下跌/关系不显著'}。"
                )
            }
        else:
            result["guidance_to_gpu"]["interpretation"] = "样本不足，无法估计领先期。"

        # ---- B) GPU price trend → next quarter guidance ----
        # 简化：取每季度末前 30 天 GPU price trend，与下一季度 actual CAPEX 做相关
        conn = self.db.get_connection()
        capex_q = conn.execute("""
            SELECT quarter_end, SUM(capex) as total_capex
            FROM capex_quarterly
            GROUP BY quarter_end ORDER BY quarter_end
        """).df()
        conn.close()

        if not capex_q.empty and len(capex_q) >= 4:
            capex_q['quarter_end'] = pd.to_datetime(capex_q['quarter_end'])
            capex_q['next_capex'] = capex_q['total_capex'].shift(-1)
            rows = []
            for _, row in capex_q.dropna(subset=['next_capex']).iterrows():
                q_end = row['quarter_end']
                start = q_end - timedelta(days=30)
                mask = (gpu_df['date'] >= start) & (gpu_df['date'] <= q_end)
                subset = gpu_df.loc[mask, 'median_price'].dropna()
                if len(subset) >= 2:
                    trend = (subset.iloc[-1] - subset.iloc[0]) / subset.iloc[0]
                    rows.append({"gpu_trend": trend, "next_capex": row['next_capex']})
            if len(rows) >= 3:
                df_tmp = pd.DataFrame(rows)
                corr2 = df_tmp['gpu_trend'].corr(df_tmp['next_capex'])
                if pd.notna(corr2):
                    result["gpu_to_guidance"] = {
                        "correlation": round(corr2, 3),
                        "interpretation": (
                            f"季度末前30天 GPU 价格趋势与下一季度 CAPEX 的相关性为 {corr2:.3f}。"
                            f"{'价格上行预示下一季度 CAPEX 增加' if corr2 > 0 else '价格上行预示下一季度 CAPEX 减少/关系不显著'}。"
                        )
                    }

        return result

    # ---------- v2 新增：Forward Gap 分析 ----------
    def calculate_forward_gap(self) -> Dict:
        """
        比较 Implied CAPEX Run-rate (L2) 与 Actual (L1)，
        以及 Nowcast (L3) 与 Implied (L2) 的偏离。
        """
        conn = self.db.get_connection()

        # L1 Actual (quarterly)
        actual_df = conn.execute("""
            SELECT quarter_end, ticker, capex FROM capex_quarterly
            ORDER BY quarter_end, ticker
        """).df()

        # L2 Implied (daily, aggregate to quarter)
        implied_df = conn.execute("""
            SELECT guidance_quarter as quarter_end, ticker,
                   SUM(implied_daily) as implied_total
            FROM capex_daily_implied
            GROUP BY guidance_quarter, ticker
            ORDER BY quarter_end, ticker
        """).df()

        # L3 Nowcast (daily, aggregate to quarter)
        nowcast_df = conn.execute("""
            SELECT date, ticker, nowcast_value FROM capex_nowcast
            ORDER BY date, ticker
        """).df()

        conn.close()

        result = {
            "implied_vs_actual": [],
            "nowcast_vs_implied": [],
            "summary": ""
        }

        # Implied vs Actual
        if not actual_df.empty and not implied_df.empty:
            merged = pd.merge(actual_df, implied_df, on=["quarter_end", "ticker"], how="inner")
            if not merged.empty:
                merged['gap_pct'] = (merged['implied_total'] - merged['capex']) / merged['capex'].replace(0, np.nan) * 100
                merged['gap_pct'] = merged['gap_pct'].replace([np.inf, -np.inf], np.nan)
                for _, row in merged.iterrows():
                    result["implied_vs_actual"].append({
                        "quarter_end": str(row['quarter_end'])[:10],
                        "ticker": row['ticker'],
                        "actual": round(row['capex'], 2),
                        "implied": round(row['implied_total'], 2),
                        "gap_pct": round(row['gap_pct'], 2) if pd.notna(row['gap_pct']) else None
                    })

        # Nowcast vs Implied (最近30天日均)
        if not nowcast_df.empty and not implied_df.empty:
            nowcast_df['date'] = pd.to_datetime(nowcast_df['date'])
            recent = nowcast_df[nowcast_df['date'] >= nowcast_df['date'].max() - timedelta(days=30)]
            recent_q = recent.groupby('ticker')['nowcast_value'].mean().reset_index()
            recent_q.columns = ['ticker', 'nowcast_daily_avg']
            # 与最新 quarter 的 implied daily 比较
            latest_impl = conn = self.db.get_connection()
            latest_impl_df = latest_impl.execute("""
                SELECT ticker, AVG(implied_daily) as implied_daily_avg
                FROM capex_daily_implied
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY ticker
            """).df()
            latest_impl.close()

            if not latest_impl_df.empty and not recent_q.empty:
                m2 = pd.merge(recent_q, latest_impl_df, on='ticker', how='inner')
                for _, row in m2.iterrows():
                    deviation = (row['nowcast_daily_avg'] - row['implied_daily_avg']) / row['implied_daily_avg'] * 100 if row['implied_daily_avg'] != 0 else None
                    result["nowcast_vs_implied"].append({
                        "ticker": row['ticker'],
                        "nowcast_daily_avg": round(row['nowcast_daily_avg'], 4),
                        "implied_daily_avg": round(row['implied_daily_avg'], 4),
                        "deviation_pct": round(deviation, 2) if deviation is not None else None
                    })

        if result["implied_vs_actual"]:
            avg_gap = np.nanmean([x['gap_pct'] for x in result["implied_vs_actual"] if x['gap_pct'] is not None])
            result["summary"] = f"Average implied-vs-actual gap: {avg_gap:.1f}% (positive = guidance overestimated)"
        else:
            result["summary"] = "Insufficient data to compute forward gap."

        return result

    # ---------- v1 信号生成（兼容）+ v2 新增信号 ----------
    def generate_signals(self) -> List[Signal]:
        signals = []
        conn = self.db.get_connection()
        today = datetime.now().strftime("%Y-%m-%d")

        # 信号1: H100 价格跌破关键阈值
        price_check = conn.execute("""
            SELECT AVG(price_per_hour) as avg_price
            FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
            AND date >= CURRENT_DATE - INTERVAL '30 days'
        """).fetchone()
        if price_check and price_check[0] and price_check[0] < THRESHOLDS["h100_price_floor"]:
            signals.append(Signal(
                type="H100_PRICE_FLOOR_BREACH",
                severity="CRITICAL",
                message=f"H100 on-demand median (${price_check[0]:.2f}/hr) below ${THRESHOLDS['h100_price_floor']} threshold for 30 days",
                impact="NEGATIVE: Scarcity premium easing. Underweight NVDA, SMCI, DELL, HPE. Cloud vendors may benefit if they can monetize idle capacity.",
                timestamp=today
            ))

        # 信号2: Spot 折扣率过大
        spot_check = conn.execute("""
            SELECT 
                AVG(CASE WHEN billing_type = 'on-demand' THEN price_per_hour END) as ondemand,
                AVG(CASE WHEN billing_type = 'spot' THEN price_per_hour END) as spot
            FROM gpu_prices_daily
            WHERE gpu_model = 'H100'
            AND date >= CURRENT_DATE - INTERVAL '7 days'
        """).fetchone()
        if spot_check and spot_check[0] and spot_check[1] and spot_check[1] > 0:
            discount = (spot_check[0] - spot_check[1]) / spot_check[0]
            if discount > THRESHOLDS["spot_discount_critical"]:
                signals.append(Signal(
                    type="SPOT_DISCOUNT_EXPANSION",
                    severity="WARNING",
                    message=f"H100 spot discount expanded to {discount*100:.0f}% (spot: ${spot_check[1]:.2f} vs on-demand: ${spot_check[0]:.2f})",
                    impact="WARNING: Oversupply signal in the spot market. Near-term bearish for GPU rental margins.",
                    timestamp=today
                ))

        # 信号3: CAPEX 增速放缓
        capex_growth = conn.execute("""
            WITH quarterly AS (
                SELECT quarter_end, SUM(capex) as total
                FROM capex_quarterly
                GROUP BY quarter_end
                ORDER BY quarter_end DESC LIMIT 5
            )
            SELECT 
                (total - LAG(total, 4) OVER (ORDER BY quarter_end)) / LAG(total, 4) OVER (ORDER BY quarter_end) as yoy
            FROM quarterly
            ORDER BY quarter_end DESC LIMIT 1
        """).fetchone()
        if capex_growth and capex_growth[0] is not None:
            growth = capex_growth[0]
            if growth < THRESHOLDS["capex_guidance_cut_pct"]:
                signals.append(Signal(
                    type="CAPEX_GROWTH_SLOWDOWN",
                    severity="HIGH",
                    message=f"Hyperscaler combined CAPEX YoY growth slowed to {growth*100:.0f}% (threshold: {THRESHOLDS['capex_guidance_cut_pct']*100:.0f}%)",
                    impact="NEGATIVE: Capital expenditure cycle may be peaking. Negative for semiconductor equipment and memory.",
                    timestamp=today
                ))

        # 信号4: 价格趋势判断
        trend = conn.execute("""
            SELECT 
                AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '30 days' THEN price_per_hour END) as recent,
                AVG(CASE WHEN date < CURRENT_DATE - INTERVAL '30 days' AND date >= CURRENT_DATE - INTERVAL '90 days' THEN price_per_hour END) as prior
            FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
        """).fetchone()
        if trend and trend[0] and trend[1] and trend[1] > 0:
            change = (trend[0] - trend[1]) / trend[1]
            if change < -0.15:
                signals.append(Signal(
                    type="GPU_PRICE_TREND_DOWN",
                    severity="HIGH",
                    message=f"H100 on-demand price declined {abs(change)*100:.0f}% over past 90 days",
                    impact="NEGATIVE: Supply catching up with demand. Re-evaluate AI hardware exposure.",
                    timestamp=today
                ))
            elif change > 0.15:
                signals.append(Signal(
                    type="GPU_PRICE_TREND_UP",
                    severity="INFO",
                    message=f"H100 on-demand price rose {change*100:.0f}% over past 90 days",
                    impact="POSITIVE: Scarcity intensifying. Continue to overweight AI infrastructure plays.",
                    timestamp=today
                ))

        # ---- v2 新增信号：guidance revision ----
        rev_check = conn.execute("""
            SELECT company, revision_pct
            FROM capex_guidance
            WHERE revised = TRUE
            ORDER BY announcement_date DESC LIMIT 4
        """).df()
        if not rev_check.empty:
            for _, row in rev_check.iterrows():
                pct = row['revision_pct'] * 100
                direction = "上调" if pct > 0 else "下调"
                severity = "HIGH" if abs(pct) >= 10 else "WARNING"
                signals.append(Signal(
                    type="CAPEX_GUIDANCE_REVISION",
                    severity=severity,
                    message=f"{row['company']} {direction} CAPEX guidance {abs(pct):.1f}%",
                    impact="Watch for supply response lag. Guidance changes typically lead GPU price by 1-2 quarters." if pct > 0 else "Peak capex cycle signal. Negative for equipment/memory suppliers.",
                    timestamp=today
                ))

        # ---- v2 新增信号：forward gap 异常 ----
        gap = self.calculate_forward_gap()
        if gap["implied_vs_actual"]:
            for item in gap["implied_vs_actual"]:
                if item['gap_pct'] is not None and abs(item['gap_pct']) > 15:
                    direction = "高估" if item['gap_pct'] > 0 else "低估"
                    signals.append(Signal(
                        type="FORWARD_GAP_ANOMALY",
                        severity="WARNING",
                        message=f"{item['ticker']} {item['quarter_end']} guidance {direction} actual by {abs(item['gap_pct']):.1f}%",
                        impact="Guidance credibility issue. Consider adjusting nowcast weights.",
                        timestamp=today
                    ))

        conn.close()
        return signals

    def get_summary_stats(self) -> Dict:
        """v1 汇总统计（兼容）"""
        conn = self.db.get_connection()
        stats = {}
        gpu_latest = conn.execute("""
            SELECT gpu_model, billing_type, AVG(price_per_hour) as price
            FROM gpu_prices_daily
            WHERE date = (SELECT MAX(date) FROM gpu_prices_daily)
            GROUP BY gpu_model, billing_type
        """).df()
        stats["gpu_latest"] = gpu_latest

        capex_latest = conn.execute("""
            SELECT company, capex, revenue, capex/revenue as capex_ratio
            FROM capex_quarterly
            WHERE quarter_end = (SELECT MAX(quarter_end) FROM capex_quarterly)
        """).df()
        stats["capex_latest"] = capex_latest

        ocpi_latest = conn.execute("""
            SELECT * FROM ocpi_daily ORDER BY date DESC LIMIT 1
        """).df()
        stats["ocpi_latest"] = ocpi_latest

        csi_history = conn.execute("""
            SELECT * FROM csi_history ORDER BY date DESC LIMIT 90
        """).df()
        stats["csi_history"] = csi_history

        # v2 新增
        guidance_latest = conn.execute("""
            SELECT * FROM capex_guidance
            ORDER BY announcement_date DESC LIMIT 4
        """).df()
        stats["guidance_latest"] = guidance_latest

        implied_latest = conn.execute("""
            SELECT ticker, AVG(implied_daily) as avg_implied_daily,
                   MAX(implied_cumulative) as max_cumulative
            FROM capex_daily_implied
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY ticker
        """).df()
        stats["implied_latest"] = implied_latest

        nowcast_latest = conn.execute("""
            SELECT ticker, AVG(nowcast_value) as avg_nowcast,
                   AVG(confidence) as avg_confidence
            FROM capex_nowcast
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY ticker
        """).df()
        stats["nowcast_latest"] = nowcast_latest

        conn.close()
        return stats


# ============================================================
# v2 报告生成器
# ============================================================
class ReportGenerator:
    @staticmethod
    def generate_daily_report(db: Database) -> str:
        engine = AnalysisEngine(db)
        csi = engine.calculate_csi()
        signals = engine.generate_signals()
        stats = engine.get_summary_stats()
        lead_lag = engine.calculate_lead_lag()
        forward_gap = engine.calculate_forward_gap()
        today = datetime.now().strftime("%Y-%m-%d")

        report = f"""
╔══════════════════════════════════════════════════════════════════════╗
║     AI COMPUTE SCARCITY TRACKER v2 — DAILY BRIEFING                 ║
║     {today}                                                          ║
╚══════════════════════════════════════════════════════════════════════╝

📊 COMPOSITE SCARCITY INDEX (CSI): {csi['csi']}/100
   Regime: {csi['regime']}
   Components: GPU_Z={csi['gpu_z']:.2f} | CAPEX_Z={csi['capex_z']:.2f} | OCPI_Z={csi['ocpi_z']:.2f}

"""

        # GPU 价格摘要
        report += "💻 GPU PRICE SNAPSHOT:\n"
        if not stats["gpu_latest"].empty:
            for _, row in stats["gpu_latest"].iterrows():
                report += f"   {row['gpu_model']} ({row['billing_type']}): ${row['price']:.2f}/hr\n"
        report += f"   Key threshold: ${THRESHOLDS['h100_price_floor']:.2f}/hr (floor)\n"
        report += f"   Historical peak: ${THRESHOLDS['h100_price_peak']:.2f}/hr (2024)\n\n"

        # CAPEX 摘要
        report += "🏢 HYPERSCALER CAPEX (L1 Actual):\n"
        if not stats["capex_latest"].empty:
            total = stats["capex_latest"]["capex"].sum()
            report += f"   Combined latest quarter: ${total:.1f}B\n"
            for _, row in stats["capex_latest"].iterrows():
                ratio = f" ({row['capex_ratio']*100:.0f}% of revenue)" if pd.notna(row['capex_ratio']) else ""
                report += f"   {row['company']}: ${row['capex']:.1f}B{ratio}\n"
        report += "\n"

        # Guidance 摘要
        report += "📋 CAPEX GUIDANCE (L1 Events):\n"
        if not stats["guidance_latest"].empty:
            for _, row in stats["guidance_latest"].iterrows():
                rev_flag = " [REVISED]" if row.get('revised', False) else ""
                report += f"   {row['company']} FY{row['fiscal_year']}: ${row['guidance_low']:.1f}B - ${row['guidance_high']:.1f}B{rev_flag}\n"
        else:
            report += "   (No guidance data loaded)\n"
        report += "\n"

        # L2 Forward Curve 摘要
        report += "📈 IMPLIED CAPEX RUN-RATE (L2 Forward Curve):\n"
        if not stats["implied_latest"].empty:
            for _, row in stats["implied_latest"].iterrows():
                report += f"   {row['ticker']}: ${row['avg_implied_daily']:.3f}B/day (quarter cum: ${row['max_cumulative']:.1f}B)\n"
        else:
            report += "   (Forward curve not yet built — run 'align')\n"
        report += "\n"

        # L3 Nowcast 摘要
        report += "🔮 CAPEX NOWCAST (L3 High-Frequency Proxy):\n"
        if not stats["nowcast_latest"].empty:
            for _, row in stats["nowcast_latest"].iterrows():
                report += f"   {row['ticker']}: ${row['avg_nowcast']:.3f}B/day (confidence: {row['avg_confidence']:.0%})\n"
        else:
            report += "   (Nowcast not yet built — run 'align')\n"
        report += "\n"

        # OCPI 摘要
        report += "📊 ORNN OCPI:\n"
        if not stats["ocpi_latest"].empty:
            row = stats["ocpi_latest"].iloc[0]
            report += f"   H100 on-demand: ${row['h100_ondemand']:.2f}/hr\n"
            report += f"   H100 1yr contract: ${row['h100_1yr_contract']:.2f}/hr\n"
            report += f"   Spot range: ${row['h100_spot_low']:.2f} - ${row['h100_spot_high']:.2f}/hr\n"
        report += "\n"

        # Forward Gap 摘要
        report += "⚖️  FORWARD GAP ANALYSIS:\n"
        report += f"   {forward_gap['summary']}\n"
        if forward_gap["implied_vs_actual"]:
            for item in forward_gap["implied_vs_actual"][-4:]:
                gap_str = f"{item['gap_pct']:+.1f}%" if item['gap_pct'] is not None else "N/A"
                report += f"   {item['ticker']} {item['quarter_end']}: implied={item['implied']:.1f}B vs actual={item['actual']:.1f}B (gap {gap_str})\n"
        report += "\n"

        # Lead/Lag 摘要
        report += "⏱️  LEAD/LAG ANALYSIS:\n"
        if lead_lag["guidance_to_gpu"]["optimal_lag_days"]:
            report += f"   Guidance→GPU: {lead_lag['guidance_to_gpu']['interpretation']}\n"
        else:
            report += "   Guidance→GPU: (insufficient revision events)\n"
        if lead_lag["gpu_to_guidance"]["correlation"]:
            report += f"   GPU→Next Guidance: {lead_lag['gpu_to_guidance']['interpretation']}\n"
        else:
            report += "   GPU→Next Guidance: (insufficient data)\n"
        report += "\n"

        # 信号
        report += "📡 SIGNALS:\n"
        if signals:
            for sig in signals:
                emoji = "🔴" if sig.severity == "CRITICAL" else "🟡" if sig.severity == "HIGH" else "⚠️ " if sig.severity == "WARNING" else "ℹ️ "
                report += f"{emoji} [{sig.type}] {sig.message}\n"
                report += f"   → Impact: {sig.impact}\n\n"
        else:
            report += "   ✅ No abnormal signals detected. Market regime unchanged.\n\n"

        # 投资映射
        report += "🎯 REGIME-BASED POSITIONING:\n"
        if csi["regime"] == "High Scarcity":
            report += "   OVERWEIGHT: AI Hardware (NVDA, SMCI, AVGO, TSM)\n"
            report += "   OVERWEIGHT: Memory (Hynix, Samsung, MU)\n"
            report += "   NEUTRAL: Cloud vendors (pricing power but high capex)\n"
        elif csi["regime"] == "Scarcity Easing":
            report += "   UNDERWEIGHT: AI Hardware (capex cycle peaking)\n"
            report += "   OVERWEIGHT: AI Application (software monetization)\n"
            report += "   OVERWEIGHT: Cloud vendors with idle monetization (META pivot)\n"
        else:
            report += "   NEUTRAL: Maintain balanced AI exposure\n"
            report += "   WATCH: META idle GPU monetization rate\n"
            report += "   WATCH: CAPEX guidance for Q3/Q4 revisions\n"

        report += "\n" + "="*70 + "\n"
        return report


# ============================================================
# CLI 命令
# ============================================================
def cmd_init(demo_seed: bool = False):
    print("🚀 Initializing AI Compute Scarcity Tracker v2...")
    db = Database()

    if not demo_seed:
        print("✅ Schema only initialization complete.")
        print("   NO_PRODUCTION_DATA: no seed/demo rows loaded and no production rows inserted.")
        print("   Next: run production collectors with `python3 tracker_v2.py update --production` once implemented.")
        print("   Demo only: use `python3 tracker_v2.py init --demo-seed` for legacy sample data.")
        print(f"✅ Database ready at: {db.db_path}")
        return

    print("DEMO ONLY: Loading legacy seed data for local demos/tests.")
    # 种子 GPU 价格数据
    seed_gpu = []
    base_date = datetime(2024, 9, 1)
    for i in range(300):
        date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        trend = 7.5 - (i / 300) * 4.5 + np.random.normal(0, 0.3)
        seed_gpu.append(GPUPriceRecord(
            date=date, provider="composite_median", gpu_model="H100",
            billing_type="on-demand", price_per_hour=max(trend, 2.0),
            source="seed_data"
        ))

    # 种子 CAPEX 数据
    seed_capex = []
    quarters = [
        ("2024-09-30", "MSFT", 20.0), ("2024-09-30", "AMZN", 19.0),
        ("2024-09-30", "GOOGL", 13.0), ("2024-09-30", "META", 9.0),
        ("2024-12-31", "MSFT", 22.0), ("2024-12-31", "AMZN", 21.0),
        ("2024-12-31", "GOOGL", 15.0), ("2024-12-31", "META", 11.0),
        ("2025-03-31", "MSFT", 25.0), ("2025-03-31", "AMZN", 24.0),
        ("2025-03-31", "GOOGL", 18.0), ("2025-03-31", "META", 13.0),
        ("2025-06-30", "MSFT", 28.0), ("2025-06-30", "AMZN", 27.0),
        ("2025-06-30", "GOOGL", 21.0), ("2025-06-30", "META", 15.0),
        ("2025-09-30", "MSFT", 32.0), ("2025-09-30", "AMZN", 30.0),
        ("2025-09-30", "GOOGL", 25.0), ("2025-09-30", "META", 18.0),
        ("2025-12-31", "MSFT", 35.0), ("2025-12-31", "AMZN", 33.0),
        ("2025-12-31", "GOOGL", 28.0), ("2025-12-31", "META", 20.0),
        ("2026-03-31", "MSFT", 37.5), ("2026-03-31", "AMZN", 43.2),
        ("2026-03-31", "GOOGL", 35.7), ("2026-03-31", "META", 28.0),
    ]
    for qe, ticker, capex in quarters:
        seed_capex.append(CAPEXRecord(
            quarter_end=qe, ticker=ticker,
            company=HYPERSCALERS[ticker]["name"],
            capex=capex, source="seed_data"
        ))

    # 种子 OCPI 数据
    seed_ocpi = []
    for i in range(300):
        date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        trend = 7.5 - (i / 300) * 4.5 + np.random.normal(0, 0.2)
        seed_ocpi.append(OCPIRecord(
            date=date, h100_ondemand=max(trend, 2.0),
            h100_1yr_contract=max(trend * 0.85, 1.7),
            h100_spot_low=max(trend * 0.6, 1.0),
            h100_spot_high=max(trend * 1.8, 5.0),
            source="seed_data"
        ))

    # 种子 Guidance 数据（v2）
    seed_guidance = []
    guidance_data = [
        # FY2025 guidance (annual, announced around Q4 2024 or Q1 2025)
        ("2025-06-30", "MSFT", 95.0, 100.0, 2025, "annual", "2024-10-25", False),
        ("2025-06-30", "AMZN", 90.0, 95.0, 2025, "annual", "2024-10-25", False),
        ("2025-06-30", "GOOGL", 70.0, 75.0, 2025, "annual", "2024-10-25", False),
        ("2025-06-30", "META", 45.0, 50.0, 2025, "annual", "2024-10-25", False),
        # FY2026 guidance (annual, announced around Q4 2025)
        ("2026-06-30", "MSFT", 140.0, 150.0, 2026, "annual", "2025-10-24", False),
        ("2026-06-30", "AMZN", 130.0, 140.0, 2026, "annual", "2025-10-24", False),
        ("2026-06-30", "GOOGL", 110.0, 120.0, 2026, "annual", "2025-10-24", False),
        ("2026-06-30", "META", 80.0, 90.0, 2026, "annual", "2025-10-24", False),
        # FY2026 guidance revision (Q2 2026)
        ("2026-06-30", "MSFT", 150.0, 160.0, 2026, "annual", "2026-04-25", True, 140.0, 150.0, 0.071),
        ("2026-06-30", "AMZN", 135.0, 145.0, 2026, "annual", "2026-04-25", True, 130.0, 140.0, 0.037),
    ]
    for g in guidance_data:
        if len(g) == 8:
            qe, ticker, low, high, fy, gtype, ad, revised = g
            prev_low, prev_high, rev_pct = None, None, None
        else:
            qe, ticker, low, high, fy, gtype, ad, revised, prev_low, prev_high, rev_pct = g
        seed_guidance.append(CAPEXGuidanceRecord(
            quarter_end=qe, ticker=ticker, company=HYPERSCALERS[ticker]["name"],
            guidance_low=low, guidance_high=high, guidance_mid=(low+high)/2,
            guidance_type=gtype, fiscal_year=fy, source="seed_guidance",
            revised=revised, previous_low=prev_low, previous_high=prev_high,
            revision_pct=rev_pct, announcement_date=ad
        ))

    # 种子 Earnings Calendar（v2）
    seed_earnings = []
    earnings_data = [
        ("MSFT", "Q1 FY2025", "2024-09-30", "2024-10-25"),
        ("AMZN", "Q3 CY2024", "2024-09-30", "2024-10-25"),
        ("GOOGL", "Q3 CY2024", "2024-09-30", "2024-10-23"),
        ("META", "Q3 CY2024", "2024-09-30", "2024-10-24"),
        ("MSFT", "Q2 FY2025", "2024-12-31", "2025-01-30"),
        ("AMZN", "Q4 CY2024", "2024-12-31", "2025-02-07"),
        ("GOOGL", "Q4 CY2024", "2024-12-31", "2025-02-05"),
        ("META", "Q4 CY2024", "2024-12-31", "2025-02-03"),
        ("MSFT", "Q3 FY2025", "2025-03-31", "2025-04-25"),
        ("AMZN", "Q1 CY2025", "2025-03-31", "2025-05-02"),
        ("GOOGL", "Q1 CY2025", "2025-03-31", "2025-04-25"),
        ("META", "Q1 CY2025", "2025-03-31", "2025-04-24"),
        ("MSFT", "Q4 FY2025", "2025-06-30", "2025-07-30"),
        ("AMZN", "Q2 CY2025", "2025-06-30", "2025-08-01"),
        ("GOOGL", "Q2 CY2025", "2025-06-30", "2025-07-25"),
        ("META", "Q2 CY2025", "2025-06-30", "2025-07-31"),
        ("MSFT", "Q1 FY2026", "2025-09-30", "2025-10-24"),
        ("AMZN", "Q3 CY2025", "2025-09-30", "2025-10-31"),
        ("GOOGL", "Q3 CY2025", "2025-09-30", "2025-10-29"),
        ("META", "Q3 CY2025", "2025-09-30", "2025-10-30"),
        ("MSFT", "Q2 FY2026", "2025-12-31", "2026-01-28"),
        ("AMZN", "Q4 CY2025", "2025-12-31", "2026-02-06"),
        ("GOOGL", "Q4 CY2025", "2025-12-31", "2026-02-04"),
        ("META", "Q4 CY2025", "2025-12-31", "2026-02-02"),
        ("MSFT", "Q3 FY2026", "2026-03-31", "2026-04-25"),
        ("AMZN", "Q1 CY2026", "2026-03-31", "2026-05-01"),
        ("GOOGL", "Q1 CY2026", "2026-03-31", "2026-04-24"),
        ("META", "Q1 CY2026", "2026-03-31", "2026-04-23"),
    ]
    for ticker, quarter, qe, ed in earnings_data:
        seed_earnings.append(EarningsCalendarRecord(
            ticker=ticker, quarter=quarter, quarter_end=qe,
            earnings_date=ed, report_type="earnings"
        ))

    db.insert_gpu_prices(seed_gpu)
    db.insert_capex(seed_capex)
    db.insert_ocpi(seed_ocpi)
    db.insert_capex_guidance(seed_guidance)
    db.insert_earnings_calendar(seed_earnings)

    # 自动构建 L2/L3
    print("🏗️  Building L2 Forward Curve and L3 Nowcast from seed data...")
    align_engine = FrequencyAlignmentEngine(db)
    align_engine.align_all()

    # 计算初始 CSI
    engine = AnalysisEngine(db)
    csi = engine.calculate_csi()
    db.insert_csi(
        date=datetime.now().strftime("%Y-%m-%d"),
        csi=csi["csi"], gpu_z=csi["gpu_z"],
        capex_z=csi["capex_z"], ocpi_z=csi["ocpi_z"], regime=csi["regime"]
    )

    print(f"DEMO ONLY: Loaded seed data + built L2/L3 alignment.")
    print(f"   GPU records: {len(seed_gpu)}, CAPEX records: {len(seed_capex)}, OCPI records: {len(seed_ocpi)}")
    print(f"   Guidance records: {len(seed_guidance)}, Earnings events: {len(seed_earnings)}")
    print(f"   Initial CSI = {csi['csi']:.1f} ({csi['regime']})")
    print(f"✅ Demo database ready at: {db.db_path}")


def cmd_update_production(only: Optional[str] = None):
    run_full_closure = only is None
    if only:
        try:
            validate_production_update_target(only)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        targets = [only]
    else:
        targets = list(PRODUCTION_UPDATE_TARGETS)

    handled = []
    target_results = []
    if "gpu-prices" in targets:
        from data_sources.gpu_pricing import update_production_gpu_prices

        started_at = _utc_now_iso()
        result = update_production_gpu_prices()
        handled.append("gpu-prices")
        status = "SUCCESS" if result.observations else "FAILED"
        target_results.append(_production_target_result("gpu-prices", status, len(result.observations), result.quality_events))
        if result.observations or result.quality_events:
            _record_production_pipeline_run(
                pipeline_name="gpu-prices",
                started_at=started_at,
                rows_loaded=len(result.observations),
                quality_events=len(result.quality_events),
                status=status,
                message="production gpu prices update",
                run_id=_first_run_id(result.observations, result.quality_events),
            )
        print("production gpu prices update")
        print(f"   inserted_gpu_prices={len(result.observations)}")
        print(f"   quality_events={len(result.quality_events)}")
        for event in result.quality_events:
            print(f"   {event.error_code}: {event.source_url} snapshot={event.snapshot_path}")
        if not run_full_closure and not result.observations and result.quality_events:
            sys.exit(1)

    if "capex-actuals" in targets:
        from data_sources.sec_capex import update_sec_capex_actuals

        started_at = _utc_now_iso()
        result = update_sec_capex_actuals()
        handled.append("capex-actuals")
        status = "SUCCESS" if result.actuals else "FAILED"
        target_results.append(_production_target_result("capex-actuals", status, len(result.actuals), result.quality_events))
        if result.actuals or result.quality_events:
            _record_production_pipeline_run(
                pipeline_name="capex-actuals",
                started_at=started_at,
                rows_loaded=len(result.actuals),
                quality_events=len(result.quality_events),
                status=status,
                message="production capex actuals update",
                run_id=_first_run_id(result.actuals, result.quality_events),
            )
        print("production capex actuals update")
        print(f"   inserted_actuals={len(result.actuals)}")
        print(f"   quality_events={len(result.quality_events)}")
        if result.trend_availability:
            for ticker, trend in sorted(result.trend_availability.items()):
                print(
                    "   trend_quarter_count | "
                    f"{ticker} | sequential_quarters={trend['sequential_quarter_count']} | "
                    f"can_evaluate_trend={trend['can_evaluate_trend']}"
                )
        for event in result.quality_events:
            print(f"   {event.error_code}: {event.affected_key} | {event.message}")
        if not run_full_closure and not result.actuals and result.quality_events:
            sys.exit(1)

    if "official-events" in targets:
        from data_sources.official_events import collect_and_insert_official_events, event_type_counts

        started_at = _utc_now_iso()
        result, counts = collect_and_insert_official_events()
        handled.append("official-events")
        represented_types = event_type_counts(result.production_events)
        status = "SUCCESS" if result.production_events else "FAILED"
        target_results.append(_production_target_result("official-events", status, counts["events_inserted"], result.quality_events))
        if result.production_events or result.quality_events:
            _record_production_pipeline_run(
                pipeline_name="official-events",
                started_at=started_at,
                rows_loaded=counts["events_inserted"],
                quality_events=counts["quality_events_inserted"],
                status=status,
                message="production official events update",
                run_id=_first_run_id(result.production_events, result.quality_events),
            )
        print("production official events update")
        print(
            "   OFFICIAL_EVENTS_LOADED: "
            f"events_inserted={counts['events_inserted']} "
            f"quality_events_inserted={counts['quality_events_inserted']} "
            f"rejected_events={len(result.rejected_events)} "
            f"event_types={sorted(represented_types)}"
        )
        for rejected in result.rejected_events:
            print(
                f"   quality | {rejected.event_id} | {rejected.reason} | {rejected.source_url}"
            )
        for event in result.quality_events:
            print(f"   quality | {event.error_code} | {event.affected_key} | {event.message}")
        if not run_full_closure and not result.production_events and result.quality_events:
            sys.exit(1)

    if "public-proxy-prices" in targets:
        from data_sources.ocpi_policy import PUBLIC_PROXY_NAME, update_ocpi_policy

        started_at = _utc_now_iso()
        result = update_ocpi_policy()
        handled.append("public-proxy-prices")
        status = "SUCCESS" if result.public_proxy_rows else "FAILED"
        target_results.append(_production_target_result("public-proxy-prices", status, len(result.public_proxy_rows), result.quality_events))
        if result.public_proxy_rows or result.quality_events:
            _record_production_pipeline_run(
                pipeline_name="public-proxy-prices",
                started_at=started_at,
                rows_loaded=len(result.public_proxy_rows),
                quality_events=len(result.quality_events),
                status=status,
                message="production OCPI/public proxy policy update",
                run_id=_first_run_id(result.public_proxy_rows, result.quality_events),
            )
        print("production OCPI/public proxy policy update")

        ocpi_unavailable = [
            event for event in result.quality_events
            if event.affected_key == "ornn_ocpi" and event.error_code == "DATA_SOURCE_UNAVAILABLE"
        ]
        if ocpi_unavailable:
            print("   OCPI unavailable | DATA_SOURCE_UNAVAILABLE | no fallback value inserted")
        else:
            print("   OCPI status | authorized feed configured or no unavailable marker emitted")

        if result.public_proxy_rows:
            gpu_models = sorted({row.gpu_model for row in result.public_proxy_rows})
            metrics = sorted({row.metric for row in result.public_proxy_rows})
            print(
                f"   {PUBLIC_PROXY_NAME} available | rows_inserted={len(result.public_proxy_rows)} "
                f"| gpu_models={gpu_models} | metrics={metrics}"
            )
        else:
            print(f"   {PUBLIC_PROXY_NAME} unavailable | PUBLIC_PROXY_SOURCE_MISSING")

        print(f"   quality_events={len(result.quality_events)}")
        for event in result.quality_events:
            print(f"   quality | {event.error_code} | {event.affected_key} | {event.message}")
        if not run_full_closure and not result.public_proxy_rows:
            sys.exit(1)

    if "market-facts" in targets:
        from data_sources.market_facts import update_market_facts

        started_at = _utc_now_iso()
        result = update_market_facts()
        handled.append("market-facts")
        status = "SUCCESS" if result.facts else "FAILED"
        target_results.append(_production_target_result("market-facts", status, len(result.facts), result.quality_events))
        if result.facts or result.quality_events:
            _record_production_pipeline_run(
                pipeline_name="market-facts",
                started_at=started_at,
                rows_loaded=len(result.facts),
                quality_events=len(result.quality_events),
                status=status,
                message="production four-track market facts update",
                run_id=_first_run_id(result.facts, result.quality_events),
            )
        print("production four-track market facts update")
        print(f"   inserted_market_facts={len(result.facts)}")
        print(f"   quality_events={len(result.quality_events)}")
        if result.facts:
            tracks = sorted({row.track for row in result.facts})
            print(f"   tracks={tracks}")
        for event in result.quality_events:
            print(f"   quality | {event.error_code} | {event.affected_key} | {event.message}")
        if not run_full_closure and not result.facts:
            sys.exit(1)

    remaining = [target for target in targets if target not in handled]
    if not remaining:
        if run_full_closure:
            _run_production_closure(target_results)
        return

    print(
        "NOT_IMPLEMENTED_COLLECTOR: production collectors are not implemented for "
        f"{', '.join(remaining)}.",
        file=sys.stderr,
    )
    print(
        f"allowed values: {allowed_production_update_values()}",
        file=sys.stderr,
    )
    sys.exit(1)


def _production_target_result(target: str, status: str, rows_loaded: int, quality_events: List[Any]) -> Dict[str, Any]:
    return {
        "target": target,
        "status": status,
        "rows_loaded": int(rows_loaded),
        "failure_codes": [
            str(getattr(event, "error_code", "") or "")
            for event in quality_events
            if getattr(event, "error_code", None)
        ],
    }


def _run_production_closure(target_results: List[Dict[str, Any]]) -> None:
    print("\nproduction closure summary")
    for item in target_results:
        codes = ", ".join(item["failure_codes"]) if item["failure_codes"] else "none"
        print(
            f"   {item['target']}: status={item['status']} "
            f"rows_loaded={item['rows_loaded']} failure_codes={codes}"
        )

    try:
        validate_company_configs()
    except CompanyConfigError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    from data_quality import FAIL as QUALITY_FAIL, evaluate_quality_gate, format_quality_gate

    db = Database()
    quality_result = evaluate_quality_gate(db)
    decision_universe = ", ".join(config.ticker for config in decision_universe_configs())
    print("\nproduction data validation")
    print(f"   COMPANY_CONFIG_OK: {decision_universe}")
    print(format_quality_gate(quality_result))

    print("\nproduction source-backed report")
    report_result, exit_label = _generate_cli_production_report(db)
    print(f"cli_exit_semantics={exit_label}")
    if quality_result.status == QUALITY_FAIL or report_result.exit_code:
        sys.exit(report_result.exit_code or quality_result.exit_code)


def _generate_cli_production_report(db: Optional[Database] = None):
    from reports import ReportGenerationError, generate_production_decision_brief

    db = db or Database()
    try:
        result = generate_production_decision_brief(db, output_dir=DATA_DIR)
    except ReportGenerationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    exit_label = _production_exit_label(result)
    content = _safe_cli_report_content(result.content, result, exit_label)
    if result.output_path is not None and content != result.content:
        result.output_path.write_text(content, encoding="utf-8")

    print(content)
    if result.output_path is not None:
        print(f"report_path={result.output_path}")
    return result, exit_label


def _production_exit_label(report_result: Any) -> str:
    from data_quality import FAIL as QUALITY_FAIL, PASS as QUALITY_PASS

    status = report_result.quality_gate.status
    if status == QUALITY_FAIL:
        if "FAIL_SEED_ONLY" in report_result.content:
            return "FAIL_SEED_ONLY"
        return "FAIL"
    if status == QUALITY_PASS:
        return "PASS"

    reason_codes = set(getattr(report_result.quality_gate, "reason_codes", []))
    decision = report_result.decision
    missing_codes = {
        str(item.get("code"))
        for item in (getattr(decision, "missing_data", []) if decision is not None else [])
    }
    evidence_layers = {
        str(item.get("layer"))
        for item in (getattr(decision, "evidence", []) if decision is not None else [])
    }
    official_evidence = any(layer in {"L1_actual_event", "L2_commitment"} for layer in evidence_layers)

    if "CAPEX_CONFIRMATION_MISSING" in missing_codes or "OFFICIAL_EVENT_MISSING" in reason_codes:
        return "WARN_CAPEX_CONFIRMATION_MISSING"
    if evidence_layers and not official_evidence:
        return "WARN_GPU_ONLY"
    return "WARN"


def _safe_cli_report_content(content: str, report_result: Any, exit_label: str) -> str:
    if report_result.quality_gate.status != "WARN":
        return content
    safe_content = content
    if "Scarcity Premium Cracking" in safe_content:
        safe_content = safe_content.replace("Scarcity Premium Cracking", "Watch")
        safe_content = safe_content.replace(
            "method=gate-based source-backed decision, not a blended legacy index",
            "cli_decision_cap=quality WARN blocks cracking regime call\n"
            "method=gate-based source-backed decision, not a blended legacy index",
        )
    if "cli_exit_semantics=" not in safe_content:
        safe_content = safe_content.replace(
            "## Current decision state\n\n",
            f"## Current decision state\n\ncli_exit_semantics={exit_label}\n",
            1,
        )
    return safe_content


def cmd_update(production: bool = False, only: Optional[str] = None, demo: bool = False):
    if production:
        cmd_update_production(only=only)
        return

    if not demo:
        print(
            "DEMO_UPDATE_REQUIRED: default update no longer runs legacy hardcoded demo collectors. "
            "Use `python3 tracker_v2.py update --production` for production or "
            "`python3 tracker_v2.py update --demo` for the legacy demo path.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("DEMO ONLY: Updating legacy AI Compute Scarcity Tracker v2 sample data...")
    db = Database()
    collector = GPUCollector()

    # 1. 更新 GPU 价格
    print("DEMO ONLY: Collecting hardcoded GPU reference prices...")
    gpu_records = collector.fetch_gpu_price_from_providers()
    if gpu_records:
        db.insert_gpu_prices(gpu_records)
        print(f"   Inserted {len(gpu_records)} GPU price records")

    # 2. 更新 CAPEX
    print("DEMO ONLY: Collecting legacy CAPEX comparison data...")
    capex_records = collector.fetch_all_capex()
    if capex_records:
        db.insert_capex(capex_records)
        print(f"   Inserted {len(capex_records)} CAPEX records")

    # 3. 更新 OCPI
    print("DEMO ONLY: Collecting hardcoded OCPI composite sample...")
    ocpi_record = collector.fetch_ocpi_public()
    db.insert_ocpi([ocpi_record])
    print("   Inserted 1 OCPI record")

    # 4. 重新构建 L2/L3（因为 GPU 价格变了，nowcast 会变）
    print("🏗️  Rebuilding frequency alignment (L2 + L3)...")
    align_engine = FrequencyAlignmentEngine(db)
    align_engine.align_all()

    # 5. 计算 CSI
    print("🧮 Calculating Composite Scarcity Index...")
    engine = AnalysisEngine(db)
    csi = engine.calculate_csi()
    db.insert_csi(
        date=datetime.now().strftime("%Y-%m-%d"),
        csi=csi["csi"], gpu_z=csi["gpu_z"],
        capex_z=csi["capex_z"], ocpi_z=csi["ocpi_z"], regime=csi["regime"]
    )
    print(f"   CSI = {csi['csi']:.1f} ({csi['regime']})")

    # 6. 生成信号
    print("📡 Generating signals...")
    signals = engine.generate_signals()
    if signals:
        db.insert_signals(signals)
        for sig in signals:
            emoji = "🔴" if sig.severity == "CRITICAL" else "🟡"
            print(f"   {emoji} {sig.type}: {sig.message}")
    else:
        print("   ✅ No signals")

    # 7. 生成报告
    print("📝 Generating report...")
    report = ReportGenerator.generate_daily_report(db)
    report_path = DATA_DIR / f"report_v2_{datetime.now().strftime('%Y%m%d')}.txt"
    report_path.write_text(report, encoding='utf-8')
    print(f"   Report saved to: {report_path}")
    print("\n" + report)


def _print_source_type_quality_counts(db: Database):
    quality_counts = db.get_source_type_quality_counts()
    print("\nsource_type data quality counts:")
    if quality_counts.empty:
        print("   (no source-bearing rows)")
    else:
        for _, row in quality_counts.iterrows():
            eligible = row["eligible_count"]
            eligible_text = "legacy" if pd.isna(eligible) else f"eligible={int(eligible)}"
            print(
                f"   {row['path']:14s} | {row['table_name']:34s} | "
                f"{row['source_type']:24s} | rows={int(row['row_count']):8,} | {eligible_text}"
            )


def _ocpi_public_proxy_status(db: Database) -> Dict[str, Any]:
    conn = db.get_connection()
    try:
        proxy_count, proxy_latest, proxy_sources = conn.execute(
            """
            SELECT COUNT(*), MAX(date), COUNT(DISTINCT source_url)
            FROM production_public_proxy_prices
            WHERE proxy_name = 'public_gpu_price_proxy'
              AND is_production_eligible = TRUE
            """
        ).fetchone()
        ocpi_event = conn.execute(
            """
            SELECT error_code, fetched_at, message
            FROM production_data_quality_events
            WHERE affected_key = 'ornn_ocpi'
              AND error_code = 'DATA_SOURCE_UNAVAILABLE'
            ORDER BY fetched_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    return {
        "proxy_count": int(proxy_count or 0),
        "proxy_latest": proxy_latest,
        "proxy_sources": int(proxy_sources or 0),
        "ocpi_event": ocpi_event,
    }


def _print_ocpi_public_proxy_status(db: Database):
    status = _ocpi_public_proxy_status(db)
    print("\nOCPI / public proxy status:")
    if status["ocpi_event"]:
        error_code, fetched_at, _message = status["ocpi_event"]
        print(f"   OCPI unavailable | {error_code} | latest_event={fetched_at}")
    elif not (os.getenv("ORNN_OCPI_FEED_URL") and os.getenv("ORNN_OCPI_FEED_TOKEN")):
        print("   OCPI unavailable | no licensed feed configured | marker not recorded yet")
    else:
        print("   OCPI status | licensed feed config present; collector not enabled in T6")

    if status["proxy_count"] > 0:
        print(
            "   public_gpu_price_proxy available | "
            f"rows={status['proxy_count']} | latest={status['proxy_latest']} | "
            f"source_urls={status['proxy_sources']}"
        )
    else:
        print("   public_gpu_price_proxy unavailable | no production proxy rows")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_run_id(*collections) -> Optional[str]:
    for collection in collections:
        for item in collection or []:
            run_id = getattr(item, "run_id", None)
            if run_id:
                return run_id
    return None


def _record_production_pipeline_run(
    *,
    pipeline_name: str,
    started_at: str,
    rows_loaded: int,
    quality_events: int,
    status: str,
    message: str,
    run_id: Optional[str] = None,
) -> None:
    from data_quality import record_pipeline_run
    from production_store import ProductionStore

    record_pipeline_run(
        ProductionStore(),
        pipeline_name=pipeline_name,
        status=status,
        rows_loaded=rows_loaded,
        message=f"{message}; quality_events={quality_events}",
        started_at=started_at,
        completed_at=_utc_now_iso(),
        run_id=run_id,
    )


def cmd_validate_data(production: bool = False):
    if not production:
        print("VALIDATE_DATA_MODE_REQUIRED: use --production for the production data contract.", file=sys.stderr)
        sys.exit(2)

    try:
        validate_company_configs()
    except CompanyConfigError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    from data_quality import FAIL as QUALITY_FAIL, evaluate_quality_gate, format_quality_gate

    db = Database()
    result = evaluate_quality_gate(db)
    decision_universe = ", ".join(config.ticker for config in decision_universe_configs())
    print("production data validation")
    print(f"   COMPANY_CONFIG_OK: {decision_universe}")
    print(format_quality_gate(result))
    if result.status == QUALITY_FAIL:
        sys.exit(result.exit_code)


def cmd_report_production():
    db = Database()
    result, exit_label = _generate_cli_production_report(db)
    print(f"cli_exit_semantics={exit_label}")
    if result.exit_code:
        sys.exit(result.exit_code)


def cmd_report(production: bool = False):
    if production:
        cmd_report_production()
        return

    db = Database()
    report = ReportGenerator.generate_daily_report(db)
    print(report)


def cmd_state_report(production: bool = False, output_dir: Optional[str] = None):
    if not production:
        print("STATE_REPORT_MODE_REQUIRED: use --production.", file=sys.stderr)
        sys.exit(2)
    from thesis_state import write_state_report

    db = Database()
    target = output_dir or str(Path(__file__).resolve().parent / "tracker_data" / "thesis_states")
    paths = write_state_report(db.db_path, target)
    print("independent thesis state report")
    print("   mixed_frequency_weighting=false")
    print("   composite_score=disabled")
    for key, value in paths.items():
        print(f"   {key}={value}")


def cmd_status(quality_only: bool = False):
    db = Database()
    if quality_only:
        from data_quality import evaluate_quality_gate, format_quality_gate

        print("production quality status")
        print(f"db_path={db.db_path}")
        _print_source_type_quality_counts(db)
        _print_ocpi_public_proxy_status(db)
        print("\nquality gate:")
        print(format_quality_gate(evaluate_quality_gate(db)))
        return

    conn = db.get_connection()
    print("📊 AI Compute Scarcity Tracker v2 Status")
    print("=" * 60)
    print(f"db_path={db.db_path}")

    table_date_cols = {
        "gpu_prices_daily": "date",
        "capex_quarterly": "quarter_end",
        "ocpi_daily": "date",
        "csi_history": "date",
        "signals": "timestamp",
        "capex_guidance": "quarter_end",
        "earnings_calendar": "earnings_date",
        "capex_daily_implied": "date",
        "capex_nowcast": "date",
        "production_gpu_prices": "date",
        "production_capex_actuals": "period_end",
        "production_official_events": "announcement_date",
        "production_public_proxy_prices": "date",
        "production_data_quality_events": "observed_at",
        "production_pipeline_runs": "observed_at",
    }
    for table, date_col in table_date_cols.items():
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        latest = conn.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()[0]
        print(f"   {table:28s}: {count:8,} records | latest: {latest}")

    conn.close()
    _print_source_type_quality_counts(db)
    _print_ocpi_public_proxy_status(db)


def cmd_reset_production_db(confirm_real_data_reset: bool = False):
    if not confirm_real_data_reset:
        print(
            "RESET_REQUIRES_CONFIRMATION: refusing to clear production tables without "
            "`--confirm-real-data-reset`.",
            file=sys.stderr,
        )
        sys.exit(2)

    db = Database()
    deleted_counts = db.reset_production_tables()
    deleted_total = sum(deleted_counts.values())
    print(f"PRODUCTION_DB_RESET: cleared {deleted_total} rows from production tables only.")
    for table, count in deleted_counts.items():
        print(f"   {table}: {count}")


def cmd_align():
    """手动触发频率对齐（L2/L3 重建）"""
    db = Database()
    align_engine = FrequencyAlignmentEngine(db)
    align_engine.align_all()


def main():
    parser = argparse.ArgumentParser(description="AI Compute Scarcity Tracker v2")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument(
        "--db",
        help=(
            "DuckDB path for this command. Production runs should use "
            f"{PRODUCTION_DB_PATH}; env fallback: {DB_PATH_ENV_VAR}."
        ),
    )

    init_parser = subparsers.add_parser("init", parents=[db_parent], help="Initialize database schema")
    init_parser.add_argument("--demo-seed", action="store_true", help="DEMO ONLY: load legacy seed data + build L2/L3")

    update_parser = subparsers.add_parser("update", parents=[db_parent], help="Update all data sources and rebuild L2/L3")
    update_parser.add_argument("--production", action="store_true", help="Use production collector skeleton")
    update_parser.add_argument("--only", help="Production update target")
    update_parser.add_argument("--demo", action="store_true", help="DEMO ONLY: run legacy hardcoded sample update")

    validate_parser = subparsers.add_parser("validate-data", parents=[db_parent], help="Validate production data contract")
    validate_parser.add_argument("--production", action="store_true", help="Validate production tables only")

    report_parser = subparsers.add_parser("report", parents=[db_parent], help="Generate current v2 report")
    report_parser.add_argument("--production", action="store_true", help="Generate production-only report")

    state_parser = subparsers.add_parser("state-report", parents=[db_parent], help="Generate independent-frequency thesis states")
    state_parser.add_argument("--production", action="store_true", help="Use production canonical views only")
    state_parser.add_argument("--output-dir", help="Directory for versioned JSON and Markdown state files")

    status_parser = subparsers.add_parser("status", parents=[db_parent], help="Show database status (v1 + v2 tables)")
    status_parser.add_argument("--quality", action="store_true", help="Show source_type quality counts")

    reset_parser = subparsers.add_parser(
        "reset-production-db",
        parents=[db_parent],
        help="Clear production tables after explicit confirmation",
    )
    reset_parser.add_argument(
        "--confirm-real-data-reset",
        action="store_true",
        help="Required confirmation flag for clearing production tables",
    )

    subparsers.add_parser("align", parents=[db_parent], help="Rebuild L2 Forward Curve and L3 Nowcast")

    args = parser.parse_args()
    if getattr(args, "db", None):
        set_default_db_path(args.db)

    try:
        if args.command == "init":
            cmd_init(demo_seed=args.demo_seed)
        elif args.command == "update":
            cmd_update(production=args.production, only=args.only, demo=args.demo)
        elif args.command == "validate-data":
            cmd_validate_data(production=args.production)
        elif args.command == "report":
            cmd_report(production=args.production)
        elif args.command == "state-report":
            cmd_state_report(production=args.production, output_dir=args.output_dir)
        elif args.command == "status":
            cmd_status(quality_only=args.quality)
        elif args.command == "reset-production-db":
            cmd_reset_production_db(confirm_real_data_reset=args.confirm_real_data_reset)
        elif args.command == "align":
            cmd_align()
        else:
            parser.print_help()
    except SchemaMigrationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
