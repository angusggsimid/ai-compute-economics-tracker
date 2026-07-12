#!/usr/bin/env python3
"""
ARCHIVED Streamlit interface for reference only.

The canonical product is html_dashboard/ai_compute_trend_board.html. This file
still contains reusable UI ideas, but its legacy CSI/DecisionEngine output is
not valid for the current production_market_facts_analysis data layer.

Run:
  streamlit run dashboard_v2.py
  AI_COMPUTE_TRACKER_DB=ai_compute_tracker_production.db streamlit run dashboard_v2.py
"""

from __future__ import annotations

import os
from html import escape
from typing import Any, Dict

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data_quality import FAIL, evaluate_quality_gate
from decision_engine import DecisionEngine
from tracker_v2 import Database, PRODUCTION_DB_PATH


DB_PATH = os.environ.get("AI_COMPUTE_TRACKER_DB", PRODUCTION_DB_PATH)


st.set_page_config(
    page_title="AI Compute Scarcity Tracker v2",
    page_icon="AI",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
<style>
.stApp { background: #eceef2; }
.block-container { padding-top: 3.25rem; max-width: 1280px; }
h1 {
    font-size: 2.45rem !important;
    line-height: 1.12 !important;
    margin-bottom: 0.35rem !important;
}
[data-testid="stCaptionContainer"] { font-size: 0.88rem; }
[data-testid="stMetric"] {
    background: #f7f8fa;
    border: 1px solid #e3e6ea;
    border-radius: 8px;
    padding: 8px 10px;
}
[data-testid="stMetricLabel"] { font-size: 0.86rem; }
[data-testid="stMetricValue"] { font-size: 1.85rem; line-height: 1.1; }
[data-testid="stMetricDelta"] { font-size: 0.78rem; }
.decision-note {
    background: #eef6ff;
    border: 1px solid #cfe5ff;
    border-left: 5px solid #2774d9;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 8px 0 12px;
    color: #163b63;
}
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
    gap: 10px;
    margin: 10px 0 12px;
}
.metric-card {
    background: #f7f8fa;
    border: 1px solid #e3e6ea;
    border-radius: 8px;
    padding: 9px 11px;
}
.metric-label { color: #667085; font-size: 0.82rem; }
.metric-value { color: #1f2430; font-size: 1.45rem; font-weight: 700; line-height: 1.15; margin-top: 4px; }
.metric-note { color: #667085; font-size: 0.78rem; margin-top: 3px; }
.compact-card {
    background: #ffffff;
    border: 1px solid #e3e6ea;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 88px;
}
.card-label { color: #667085; font-size: 0.82rem; margin-bottom: 6px; }
.card-value { font-size: 1.12rem; font-weight: 700; color: #1f2430; }
.card-note { color: #667085; font-size: 0.86rem; margin-top: 6px; }
.readout-card {
    border: 1px solid #e3e6ea;
    border-radius: 8px;
    padding: 12px 14px;
    margin: 8px 0;
    background: #ffffff;
}
.readout-title { font-weight: 800; color: #1f2430; margin-bottom: 6px; }
.readout-line { color: #344054; font-size: 0.92rem; line-height: 1.45; margin: 3px 0; }
.readout-label { color: #667085; font-weight: 700; }
.small-note { color: #667085; font-size: 0.9rem; }
.section-title { margin-top: 1rem; }
.evidence-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 10px;
    margin: 10px 0 14px;
}
.evidence-card {
    border: 1px solid #d7dee8;
    border-radius: 8px;
    padding: 12px 14px;
    background: #ffffff;
    min-height: 126px;
}
.evidence-layer { color: #667085; font-size: 0.82rem; font-weight: 700; }
.evidence-verdict { color: #1f2430; font-size: 1.08rem; font-weight: 800; margin: 5px 0; }
.evidence-body { color: #344054; font-size: 0.9rem; line-height: 1.45; }
.tracker-header {
    display: grid;
    grid-template-columns: minmax(280px, 1.2fr) minmax(420px, 1fr);
    gap: 16px;
    align-items: end;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px 18px;
    margin: 8px 0 10px;
}
.tracker-title { color: #6e6e73; font-size: 0.88rem; font-weight: 800; }
.tracker-action { color: #1d1d1f; font-size: 2.2rem; font-weight: 850; line-height: 1.05; margin: 4px 0 2px; }
.tracker-reason { color: #424245; font-size: 0.96rem; }
.pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #f2f2f4;
    border: 1px solid #e4e4e7;
    border-radius: 999px;
    padding: 6px 10px;
    color: #3a3a3c;
    font-size: 0.86rem;
}
.status-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(86px, 1fr));
    gap: 8px;
}
.status-tile {
    background: #f5f5f7;
    border: 1px solid #e6e6ea;
    border-radius: 8px;
    padding: 9px 10px;
}
.status-label { color: #86868b; font-size: 0.76rem; font-weight: 750; }
.status-value { color: #1d1d1f; font-size: 1rem; font-weight: 850; margin-top: 3px; line-height: 1.15; }
.status-note { color: #6e6e73; font-size: 0.75rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.section-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 14px 16px;
    min-height: 116px;
}
.section-card-title { color: #6e6e73; font-size: 0.82rem; font-weight: 700; }
.section-card-value { color: #1d1d1f; font-size: 1.5rem; font-weight: 800; margin: 4px 0; line-height: 1.15; }
.section-card-note { color: #515154; font-size: 0.9rem; line-height: 1.42; }
.decision-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
    gap: 14px;
    margin: 12px 0 8px;
}
.decision-panel {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px 18px;
}
.panel-label { color: #6e6e73; font-size: 0.82rem; font-weight: 800; margin-bottom: 7px; }
.panel-title { color: #1d1d1f; font-size: 1.15rem; font-weight: 800; margin-bottom: 7px; }
.panel-body { color: #515154; font-size: 0.92rem; line-height: 1.48; }
.rule-list { display: grid; gap: 8px; margin-top: 10px; }
.rule-item {
    border-top: 1px solid #ececf0;
    padding-top: 8px;
    color: #424245;
    font-size: 0.9rem;
    line-height: 1.42;
}
.signal-row {
    display: grid;
    grid-template-columns: 120px 92px 1fr;
    gap: 12px;
    align-items: start;
    border-top: 1px solid #ececf0;
    padding: 10px 0;
}
.signal-row:first-child { border-top: 0; padding-top: 0; }
.signal-name { color: #1d1d1f; font-weight: 800; font-size: 0.92rem; }
.signal-state { color: #1d1d1f; font-weight: 800; font-size: 0.88rem; }
.signal-detail { color: #515154; font-size: 0.88rem; line-height: 1.42; }
.watch-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 10px;
    margin: 12px 0;
}
.watch-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 13px 15px;
    min-height: 118px;
}
.watch-label { color: #6e6e73; font-size: 0.8rem; font-weight: 800; margin-bottom: 6px; }
.watch-title { color: #1d1d1f; font-size: 1.02rem; font-weight: 800; margin-bottom: 6px; }
.watch-status { color: #1d1d1f; font-size: 1.55rem; font-weight: 800; margin: 4px 0 8px; }
.watch-body { color: #515154; font-size: 0.9rem; line-height: 1.32; }
.bridge-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-left: 4px solid #d1d5db;
    border-radius: 8px;
    padding: 13px 15px;
    min-height: 132px;
}
.bridge-card.support { border-left-color: #1677c8; }
.bridge-card.contra { border-left-color: #f05a5f; }
.bridge-card.watch { border-left-color: #0f9f8f; }
.bridge-card.block { border-left-color: #6e6e73; }
.bridge-label { color: #6e6e73; font-size: 0.78rem; font-weight: 850; margin-bottom: 5px; }
.bridge-call { color: #1d1d1f; font-size: 1.25rem; font-weight: 850; margin-bottom: 6px; line-height: 1.12; }
.bridge-readout { color: #515154; font-size: 0.88rem; line-height: 1.36; }
.bridge-action { color: #1d1d1f; font-size: 0.86rem; font-weight: 800; margin-top: 8px; }
.bridge-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 10px;
    margin-top: 12px;
}
.visual-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(360px, 1fr));
    gap: 12px;
    margin: 10px 0;
}
.visual-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px 18px;
    min-height: 244px;
}
.visual-card.wide { grid-column: span 2; min-height: 210px; }
.visual-title { color: #1d1d1f; font-size: 1.02rem; font-weight: 850; margin-bottom: 12px; }
.bar-row, .dot-row {
    display: grid;
    grid-template-columns: 82px 1fr 72px;
    align-items: center;
    gap: 10px;
    margin: 12px 0;
}
.bar-label, .dot-label { color: #1d1d1f; font-size: 0.88rem; font-weight: 800; }
.bar-value, .dot-value { color: #515154; font-size: 0.84rem; text-align: right; }
.bar-track, .dot-track {
    position: relative;
    height: 12px;
    background: #f1f2f4;
    border-radius: 999px;
    overflow: hidden;
}
.bar-zero {
    position: absolute;
    left: 50%;
    top: 0;
    width: 1px;
    height: 100%;
    background: #a1a1aa;
}
.bar-neg, .bar-pos {
    position: absolute;
    top: 2px;
    height: 8px;
    border-radius: 999px;
}
.bar-neg { right: 50%; background: #1677c8; }
.bar-pos { left: 50%; background: #f05a5f; }
.dot {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 999px;
    background: #2563eb;
    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.12);
}
.visual-footnote { color: #86868b; font-size: 0.78rem; margin-top: 10px; }
.source-caption {
    color: #86868b;
    font-size: 0.76rem;
    line-height: 1.35;
    margin-top: 10px;
    padding-top: 9px;
    border-top: 1px solid #f0f0f2;
}
.trend-hero {
    background: #0a0a0a;
    border-left: 10px solid #002FA7;
    padding: 20px 22px 18px;
    margin: 4px 0 18px;
}
.trend-title { color: #fafaf8; font-size: 1.78rem; font-weight: 650; line-height: 1.12; letter-spacing: 0; }
.trend-meta { color: #d4d4d2; font-size: 0.9rem; margin-top: 7px; }
.trend-section {
    background: #f0f0ee;
    border-top: 6px solid #002FA7;
    border-bottom: 1px solid #d4d4d2;
    display: grid;
    grid-template-columns: 1fr;
    gap: 7px;
    padding: 15px 16px 14px;
    margin: 28px 0 12px;
}
.trend-section-kicker {
    color: #002FA7;
    font-size: 0.76rem;
    font-weight: 850;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.trend-section-title {
    color: #0a0a0a;
    font-size: 1.2rem;
    font-weight: 750;
    line-height: 1.15;
}
.trend-section-note {
    color: #515154;
    font-size: 0.9rem;
    line-height: 1.38;
}
.trend-card-title {
    color: #0a0a0a;
    font-size: 1.02rem;
    font-weight: 800;
    line-height: 1.2;
    margin: 2px 0 2px;
}
.trend-card-subtitle {
    color: #515154;
    font-size: 0.84rem;
    font-weight: 500;
    line-height: 1.35;
    margin: 0 0 8px;
}
.trend-caption {
    color: #737373;
    font-size: 0.8rem;
    line-height: 1.3;
    margin-top: -4px;
    border-top: 1px solid #eeeeef;
    padding-top: 7px;
}
.trend-capex-note {
    color: #515154;
    font-size: 0.88rem;
    line-height: 1.35;
    margin: -4px 0 8px;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fafaf8;
    border: 1px solid #d4d4d2;
    border-radius: 0;
}
.missing-tile {
    color: #86868b;
    background: #fafaf8;
    border: 1px solid #d4d4d2;
    border-radius: 0;
    padding: 24px 18px;
    min-height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-size: 0.92rem;
}
@media (max-width: 600px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 2.25rem; }
    .trend-hero { padding: 14px 16px; margin-top: 2px; }
    .trend-title { font-size: 1.12rem; line-height: 1.2; overflow-wrap: anywhere; }
    .trend-meta { font-size: 0.76rem; line-height: 1.45; }
    .trend-section { gap: 6px; margin-top: 22px; padding: 12px 13px; }
    .trend-section-title { font-size: 1rem; }
    .trend-section-note { font-size: 0.82rem; }
    .trend-card-title { font-size: 0.9rem; }
    .trend-card-subtitle { font-size: 0.78rem; }
}
.value-row, .commercial-row {
    display: grid;
    grid-template-columns: minmax(118px, 1fr) 1.35fr 64px;
    align-items: center;
    gap: 10px;
    margin: 11px 0;
}
.value-label, .commercial-label { color: #1d1d1f; font-size: 0.86rem; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.value-track, .commercial-track { position: relative; height: 12px; background: #f1f2f4; border-radius: 999px; overflow: hidden; }
.value-bar, .commercial-bar { position: absolute; left: 0; top: 2px; height: 8px; border-radius: 999px; background: #7c5cff; }
.commercial-bar { background: #0f9f8f; }
.value-score, .commercial-score { color: #515154; font-size: 0.84rem; text-align: right; }
.token-row {
    display: grid;
    grid-template-columns: minmax(130px, 1fr) 1.25fr 74px;
    align-items: center;
    gap: 10px;
    margin: 10px 0;
}
.token-label { color: #1d1d1f; font-size: 0.84rem; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.token-track { position: relative; height: 12px; background: #f1f2f4; border-radius: 999px; overflow: hidden; }
.token-zero { position: absolute; left: 50%; top: 0; width: 1px; height: 100%; background: #a1a1aa; }
.token-down, .token-up, .token-flat { position: absolute; top: 2px; height: 8px; border-radius: 999px; }
.token-down { right: 50%; background: #1677c8; }
.token-up { left: 50%; background: #f05a5f; }
.token-flat { left: 49%; width: 2%; background: #86868b; }
.token-score { color: #515154; font-size: 0.82rem; text-align: right; }
.token-note { color: #86868b; font-size: 0.72rem; margin: -6px 0 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.readiness-row {
    display: grid;
    grid-template-columns: minmax(92px, 0.8fr) 1.4fr 74px;
    align-items: center;
    gap: 10px;
    margin: 10px 0;
}
.readiness-label { color: #1d1d1f; font-size: 0.86rem; font-weight: 800; }
.readiness-track { position: relative; height: 12px; background: #f1f2f4; border-radius: 999px; overflow: hidden; }
.readiness-bar { position: absolute; left: 0; top: 2px; height: 8px; border-radius: 999px; background: #2563eb; }
.readiness-bar.weak { background: #f59f00; }
.readiness-bar.missing { background: #86868b; }
.readiness-score { color: #515154; font-size: 0.84rem; text-align: right; }
.gap-bar { background: #f05a5f; }
.commercial-note {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 12px;
}
.commercial-chip, .cloud-chip {
    background: #f5f5f7;
    border: 1px solid #e6e6ea;
    border-radius: 8px;
    padding: 8px 10px;
}
.commercial-chip-label, .cloud-chip-label { color: #86868b; font-size: 0.74rem; font-weight: 750; }
.commercial-chip-value, .cloud-chip-value { color: #1d1d1f; font-size: 0.95rem; font-weight: 850; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.layer-row {
    display: grid;
    grid-template-columns: 106px 1fr 150px;
    gap: 14px;
    align-items: start;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 13px 15px;
    margin: 8px 0;
}
.layer-name { color: #6e6e73; font-size: 0.86rem; font-weight: 800; }
.layer-title { color: #1d1d1f; font-size: 1.04rem; font-weight: 800; margin-bottom: 4px; }
.layer-detail { color: #515154; font-size: 0.9rem; line-height: 1.42; }
.layer-state { color: #1d1d1f; font-weight: 800; text-align: right; }
.quiet-caption { color: #6e6e73; font-size: 0.86rem; line-height: 1.45; }
.top-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    background: #ececf0;
    border: 1px solid #dedee3;
    border-radius: 8px;
    padding: 4px;
    margin-bottom: 14px;
}
.top-nav a {
    color: #1d1d1f;
    text-decoration: none;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 0.93rem;
    font-weight: 700;
}
.top-nav a:hover {
    background: #ffffff;
}
.top-nav a.active {
    background: #ffffff;
    color: #000000;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
[data-testid="stExpander"] {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    box-shadow: none;
}
[data-testid="stExpander"] summary p {
    color: #1d1d1f !important;
    font-weight: 800;
}
[data-testid="stExpander"] summary svg {
    color: #6e6e73 !important;
}
.room-header {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 14px 17px;
    margin: 8px 0 12px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
}
.room-title { color: #1d1d1f; font-size: 1.45rem; font-weight: 850; line-height: 1.1; }
.room-subtitle { color: #515154; font-size: 0.93rem; margin-top: 4px; line-height: 1.35; }
.room-meta {
    color: #6e6e73;
    background: #f5f5f7;
    border: 1px solid #e6e6ea;
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 0.82rem;
    font-weight: 750;
    white-space: nowrap;
}
.source-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 10px;
    margin: 10px 0;
}
.source-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 14px;
    min-height: 108px;
}
.source-label { color: #6e6e73; font-size: 0.78rem; font-weight: 800; margin-bottom: 6px; }
.source-value { color: #1d1d1f; font-size: 1.15rem; font-weight: 850; margin-bottom: 5px; line-height: 1.15; }
.source-note { color: #515154; font-size: 0.88rem; line-height: 1.36; }
.detail-note {
    color: #6e6e73;
    font-size: 0.84rem;
    line-height: 1.4;
    margin: 4px 0 10px;
}
.detail-block {
    background: #ffffff;
    border: 1px solid #ececf0;
    border-radius: 8px;
    padding: 12px 14px;
    margin: 10px 0;
}
.detail-title { color: #1d1d1f; font-size: 0.96rem; font-weight: 850; margin-bottom: 4px; }
.detail-body { color: #515154; font-size: 0.88rem; line-height: 1.42; }
@media (max-width: 760px) {
    .tracker-header { grid-template-columns: 1fr; }
    .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .visual-grid { grid-template-columns: 1fr; }
    .room-header { grid-template-columns: 1fr; }
    .room-meta { width: fit-content; }
    .visual-card.wide { grid-column: span 1; }
    .decision-grid { grid-template-columns: 1fr; }
    .signal-row { grid-template-columns: 1fr; gap: 4px; }
    .layer-row { grid-template-columns: 1fr; gap: 6px; }
    .layer-state { text-align: left; }
    .bridge-grid { grid-template-columns: 1fr; }
    .hero-status { font-size: 2.1rem; }
}
</style>
""",
    unsafe_allow_html=True,
)


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _query_df(conn: duckdb.DuckDBPyConnection, sql: str, columns: list[str]) -> pd.DataFrame:
    try:
        return conn.execute(sql).df()
    except Exception:
        return _empty_df(columns)


ADEQUATE_PROXY_QUOTE_COUNT = 3


PUBLIC_PROXY_HISTORY_COLUMNS = [
    "date",
    "gpu_model",
    "median_price_per_gpu_hour",
    "min_price_per_gpu_hour",
    "quote_count",
    "coverage_quality",
    "source_url",
    "snapshot_path",
]


PUBLIC_PROXY_HISTORY_SQL = """
WITH proxy AS (
    SELECT
        date,
        gpu_model,
        source_url,
        snapshot_path,
        max(CASE WHEN metric = 'computeprices_row_median_price_per_gpu_hour_proxy' THEN value END)::DOUBLE
            AS median_price_per_gpu_hour,
        max(CASE WHEN metric = 'computeprices_row_min_price_per_gpu_hour_proxy' THEN value END)::DOUBLE
            AS min_price_per_gpu_hour,
        max(CASE WHEN metric = 'computeprices_row_count_proxy' THEN value END)::INTEGER
            AS quote_count
    FROM production_public_proxy_prices
    WHERE is_production_eligible = TRUE
      AND provider = 'ComputePrices'
      AND proxy_name = 'public_gpu_price_proxy'
      AND gpu_model IN ('H100', 'H200')
      AND metric IN (
          'computeprices_row_median_price_per_gpu_hour_proxy',
          'computeprices_row_min_price_per_gpu_hour_proxy',
          'computeprices_row_count_proxy'
      )
    GROUP BY date, gpu_model, source_url, snapshot_path
)
SELECT
    date,
    gpu_model,
    median_price_per_gpu_hour,
    min_price_per_gpu_hour,
    quote_count,
    CASE
        WHEN quote_count >= 3 THEN 'adequate'
        WHEN quote_count > 0 THEN 'thin'
        ELSE 'missing'
    END AS coverage_quality,
    source_url,
    snapshot_path
FROM proxy
WHERE median_price_per_gpu_hour IS NOT NULL
ORDER BY date, gpu_model
"""


MARKET_FACT_COLUMNS = [
    "date",
    "track",
    "entity",
    "sub_entity",
    "metric",
    "value",
    "unit",
    "dimension",
    "vendor",
    "source_name",
    "notes",
    "source_type",
    "source_url",
    "snapshot_path",
    "observed_at",
    "fetched_at",
    "confidence",
]


MARKET_FACT_SQL = """
SELECT date, track, entity, sub_entity, metric, value, unit, dimension, vendor,
       source_name, notes, source_type, source_url, snapshot_path, observed_at,
       fetched_at, confidence
FROM production_market_facts
WHERE is_production_eligible = TRUE
ORDER BY track, entity, sub_entity, metric, date DESC
"""


def _public_proxy_history(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _query_df(conn, PUBLIC_PROXY_HISTORY_SQL, PUBLIC_PROXY_HISTORY_COLUMNS)


def _market_facts(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _query_df(conn, MARKET_FACT_SQL, MARKET_FACT_COLUMNS)


def get_gpu_price_trend(db_path: str = DB_PATH) -> pd.DataFrame:
    """Backward-compatible API: returns decision-useful public proxy history, not raw quote rows."""
    return get_public_proxy_history(db_path)


def get_public_proxy_history(db_path: str = DB_PATH) -> pd.DataFrame:
    db = Database(db_path)
    conn = db.get_connection()
    try:
        return _public_proxy_history(conn)
    finally:
        conn.close()


def _legacy_counts(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for table_name in ["gpu_prices_daily", "capex_quarterly", "ocpi_daily", "capex_guidance", "capex_daily_implied", "capex_nowcast", "csi_history"]:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        except Exception:
            count = 0
        rows.append({"table_name": table_name, "rows": int(count)})
    return pd.DataFrame(rows)


def _source_coverage(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    specs = [
        ("GPU price", "gpu_prices", "date"),
        ("SEC CAPEX actual", "capex_actuals", "period_end"),
        ("Official guidance/RPO event", "official_events", "announcement_date"),
        ("Public GPU proxy", "public_proxy_prices", "date"),
        ("Four-track market facts", "market_facts", "date"),
        ("Quality/failure event", "quality_events", "observed_at"),
        ("Pipeline run", "pipeline_runs", "completed_at"),
    ]
    rows = []
    for layer, key, date_col in specs:
        df = tables.get(key, _empty_df([]))
        if df.empty:
            rows.append({"layer": layer, "source_type": "missing", "rows": 0, "source_urls": 0, "latest": ""})
            continue
        group_cols = ["source_type"] if "source_type" in df.columns else []
        grouped = df.groupby(group_cols, dropna=False) if group_cols else [(("",), df)]
        for group_key, group in grouped:
            source_type = group_key if isinstance(group_key, str) else group_key[0]
            rows.append(
                {
                    "layer": layer,
                    "source_type": str(source_type or "unknown"),
                    "rows": int(len(group)),
                    "source_urls": int(group["source_url"].nunique()) if "source_url" in group.columns else 0,
                    "latest": str(group[date_col].max()) if date_col in group.columns and not group.empty else "",
                }
            )
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def load_dashboard_data(db_path: str = DB_PATH) -> Dict[str, Any]:
    db = Database(db_path)
    quality_gate = evaluate_quality_gate(db)
    decision = None if quality_gate.status == FAIL else DecisionEngine(db).evaluate()
    conn = db.get_connection()
    try:
        gpu_prices = _query_df(
            conn,
            """
            SELECT date, provider, gpu_model, gpu_variant, billing_type, commitment,
                   gpu_count, region, price_per_gpu_hour, currency, source_type,
                   source_url, snapshot_path, observed_at, fetched_at
            FROM production_gpu_prices
            WHERE is_production_eligible = TRUE
            ORDER BY date DESC, source_type DESC, provider, gpu_model, gpu_variant, price_per_gpu_hour
            """,
            [
                "date",
                "provider",
                "gpu_model",
                "gpu_variant",
                "billing_type",
                "commitment",
                "gpu_count",
                "region",
                "price_per_gpu_hour",
                "currency",
                "source_type",
                "source_url",
                "snapshot_path",
                "observed_at",
                "fetched_at",
            ],
        )
        capex_actuals = _query_df(
            conn,
            """
            SELECT ticker, company, fiscal_period, fiscal_year, period_start, period_end,
                   capex_value, unit, xbrl_tag, accession_no, filed_at, form_type,
                   source_type, source_url, snapshot_path, observed_at, fetched_at
            FROM production_capex_actuals
            WHERE is_production_eligible = TRUE
              AND source_type = 'official'
            ORDER BY ticker, period_end DESC
            """,
            [
                "ticker",
                "company",
                "fiscal_period",
                "fiscal_year",
                "period_start",
                "period_end",
                "capex_value",
                "unit",
                "xbrl_tag",
                "accession_no",
                "filed_at",
                "form_type",
                "source_type",
                "source_url",
                "snapshot_path",
                "observed_at",
                "fetched_at",
            ],
        )
        official_events = _query_df(
            conn,
            """
            SELECT ticker, announcement_date, event_type, metric, value, unit,
                   description, fiscal_period, source_type, source_url, snapshot_path,
                   observed_at, fetched_at
            FROM production_official_events
            WHERE is_production_eligible = TRUE
              AND source_type = 'official'
            ORDER BY announcement_date DESC, ticker, event_type
            """,
            [
                "ticker",
                "announcement_date",
                "event_type",
                "metric",
                "value",
                "unit",
                "description",
                "fiscal_period",
                "source_type",
                "source_url",
                "snapshot_path",
                "observed_at",
                "fetched_at",
            ],
        )
        public_proxy_prices = _query_df(
            conn,
            """
            SELECT date, provider, proxy_name, metric, value, unit, gpu_model, region,
                   source_type, source_url, snapshot_path, observed_at, fetched_at
            FROM production_public_proxy_prices
            WHERE is_production_eligible = TRUE
            ORDER BY date DESC, gpu_model, metric
            """,
            [
                "date",
                "provider",
                "proxy_name",
                "metric",
                "value",
                "unit",
                "gpu_model",
                "region",
                "source_type",
                "source_url",
                "snapshot_path",
                "observed_at",
                "fetched_at",
            ],
        )
        quality_events = _query_df(
            conn,
            """
            SELECT event_id, table_name, severity, error_code, message, affected_key,
                   source_type, source_url, snapshot_path, observed_at, fetched_at
            FROM production_data_quality_events
            ORDER BY observed_at DESC, table_name, affected_key
            """,
            [
                "event_id",
                "table_name",
                "severity",
                "error_code",
                "message",
                "affected_key",
                "source_type",
                "source_url",
                "snapshot_path",
                "observed_at",
                "fetched_at",
            ],
        )
        pipeline_runs = _query_df(
            conn,
            """
            SELECT pipeline_name, status, started_at, completed_at, rows_loaded,
                   message, source_type, source_url, snapshot_path, observed_at
            FROM production_pipeline_runs
            ORDER BY completed_at DESC
            """,
            [
                "pipeline_name",
                "status",
                "started_at",
                "completed_at",
                "rows_loaded",
                "message",
                "source_type",
                "source_url",
                "snapshot_path",
                "observed_at",
            ],
        )
        public_proxy_history = _public_proxy_history(conn)
        market_facts = _market_facts(conn)
        legacy_counts = _legacy_counts(conn)
    finally:
        conn.close()

    tables = {
        "gpu_prices": gpu_prices,
        "capex_actuals": capex_actuals,
        "official_events": official_events,
        "public_proxy_prices": public_proxy_prices,
        "market_facts": market_facts,
        "quality_events": quality_events,
        "pipeline_runs": pipeline_runs,
    }
    return {
        "db_path": db_path,
        "quality_gate": quality_gate,
        "decision": decision,
        "tables": tables,
        "public_proxy_history": public_proxy_history,
        "gpu_price_trend": public_proxy_history,
        "source_coverage": _source_coverage(tables),
        "legacy_counts": legacy_counts,
    }


def get_first_view_summary(db_path: str = DB_PATH) -> Dict[str, Any]:
    data = load_dashboard_data(db_path)
    quality_gate = data["quality_gate"]
    decision = data["decision"]
    pipeline_runs = data["tables"]["pipeline_runs"]
    last_run = "" if pipeline_runs.empty else str(pipeline_runs["completed_at"].max())
    return {
        "db_path": data["db_path"],
        "quality_gate": quality_gate.status,
        "decision_state": "Blocked" if decision is None else decision.state,
        "confidence": None if decision is None else decision.confidence,
        "last_run": last_run,
        "public_proxy_history_rows": int(len(data["public_proxy_history"])),
        "public_proxy_history": data["public_proxy_history"],
        "gpu_price_trend_rows": int(len(data["public_proxy_history"])),
        "gpu_price_trend": data["public_proxy_history"],
        "production_counts": dict(quality_gate.table_counts),
        "source_coverage": data["source_coverage"],
        "missing_or_failed": pd.DataFrame([reason.__dict__ for reason in quality_gate.reasons]),
    }


def _metric_value(value: Any, fallback: str = "n/a") -> str:
    if value is None:
        return fallback
    text = str(value)
    return text if text else fallback


def _source_label(source_type: str) -> str:
    labels = {
        "aggregator": "ComputePrices public quote history",
        "public_pricing_page": "Provider pricing page snapshot",
        "official": "Official source",
        "licensed_unavailable": "Licensed source unavailable",
    }
    return labels.get(str(source_type), str(source_type))


def _proxy_history_summary(proxy_history: pd.DataFrame) -> Dict[str, Any]:
    if proxy_history.empty:
        return {
            "proxy_days": 0,
            "adequate_days": 0,
            "thin_days": 0,
            "latest_h100_median": None,
            "latest_h200_median": None,
            "latest_h100_quotes": None,
            "latest_h200_quotes": None,
        }
    proxy_history = proxy_history[proxy_history["gpu_model"].isin(["H100", "H200"])].copy()
    if proxy_history.empty:
        return {
            "proxy_days": 0,
            "adequate_days": 0,
            "thin_days": 0,
            "latest_h100_median": None,
            "latest_h200_median": None,
            "latest_h100_quotes": None,
            "latest_h200_quotes": None,
        }
    latest_by_gpu = {}
    latest_quotes_by_gpu = {}
    for gpu_model in ["H100", "H200"]:
        rows = proxy_history[proxy_history["gpu_model"] == gpu_model].sort_values("date")
        if rows.empty:
            latest_by_gpu[gpu_model] = None
            latest_quotes_by_gpu[gpu_model] = None
        else:
            latest_by_gpu[gpu_model] = float(rows.iloc[-1]["median_price_per_gpu_hour"])
            latest_quotes_by_gpu[gpu_model] = int(rows.iloc[-1]["quote_count"])
    adequate = proxy_history[proxy_history["quote_count"].fillna(0) >= ADEQUATE_PROXY_QUOTE_COUNT]
    thin = proxy_history[(proxy_history["quote_count"].fillna(0) > 0) & (proxy_history["quote_count"].fillna(0) < ADEQUATE_PROXY_QUOTE_COUNT)]
    return {
        "proxy_days": int(proxy_history["date"].nunique()),
        "adequate_days": int(adequate["date"].nunique()) if not adequate.empty else 0,
        "thin_days": int(thin["date"].nunique()) if not thin.empty else 0,
        "latest_h100_median": latest_by_gpu["H100"],
        "latest_h200_median": latest_by_gpu["H200"],
        "latest_h100_quotes": latest_quotes_by_gpu["H100"],
        "latest_h200_quotes": latest_quotes_by_gpu["H200"],
    }


def _pricing_snapshot_summary(gpu_prices: pd.DataFrame) -> Dict[str, Any]:
    if gpu_prices.empty:
        return {"days": 0, "providers": 0, "rows": 0}
    rows = gpu_prices[
        (gpu_prices["source_type"] == "public_pricing_page")
        & (gpu_prices["gpu_model"].isin(["H100", "H200"]))
    ].copy()
    if rows.empty:
        return {"days": 0, "providers": 0, "rows": 0}
    return {
        "days": int(rows["date"].nunique()),
        "providers": int(rows["provider"].nunique()),
        "rows": int(len(rows)),
    }


def _trend_return(df: pd.DataFrame, *, value_col: str = "value") -> float | None:
    if df.empty or value_col not in df.columns:
        return None
    rows = df.copy()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows[value_col] = pd.to_numeric(rows[value_col], errors="coerce")
    rows = rows.dropna(subset=["date", value_col]).sort_values("date")
    if len(rows) < 2:
        return None
    first = float(rows.iloc[0][value_col])
    last = float(rows.iloc[-1][value_col])
    if first == 0:
        return None
    return (last - first) / first


def _market_regime_summary(market_facts: pd.DataFrame) -> Dict[str, Any]:
    if market_facts.empty:
        return {
            "label": "数据不足",
            "headline": "等待价格趋势",
            "evidence": "缺少 GPUs.io movers 数据",
            "implication": "不能判断算力稀缺叙事是否松动。",
            "a100_90d": None,
            "h200_90d": None,
            "b200_90d": None,
        }

    facts = market_facts.copy()
    facts["value"] = pd.to_numeric(facts["value"], errors="coerce")
    trend = facts[
        (facts["track"] == "gpu_market_trend")
        & (facts["metric"] == "price_delta_90d_pct")
    ]

    def median_for(entity: str) -> float | None:
        values = pd.to_numeric(trend[trend["entity"] == entity]["value"], errors="coerce").dropna()
        return None if values.empty else float(values.median())

    a100_90d = median_for("NVIDIA A100 80GB")
    h200_90d = median_for("NVIDIA H200")
    b200_90d = median_for("NVIDIA B200")
    legacy_easing = a100_90d is not None and a100_90d <= -20
    frontier_tight = any(value is not None and value > 0 for value in [h200_90d, b200_90d])

    if legacy_easing and frontier_tight:
        label = "代际分化"
        headline = "旧卡松动，前沿卡仍紧"
        implication = "单一“算力持续紧缺”叙事变弱，但还不能推出硬件链全面转空。"
    elif legacy_easing:
        label = "旧卡松动"
        headline = "非前沿算力先商品化"
        implication = "更像存量 GPU 利用率和旧卡价格承压，不等同于 Blackwell/Hopper 订单见顶。"
    elif frontier_tight:
        label = "前沿仍紧"
        headline = "前沿卡价格仍有支撑"
        implication = "当前不支持算力稀缺溢价破裂判断。"
    else:
        label = "趋势未确认"
        headline = "90 日价格没有形成明确方向"
        implication = "需要继续等官方云 spot、GPU 租赁和 CAPEX 指引同向验证。"

    evidence = (
        f"A100 80GB 90d {_point_percent(a100_90d)}；"
        f"H200 90d {_point_percent(h200_90d)}；"
        f"B200 90d {_point_percent(b200_90d)}。"
    )
    return {
        "label": label,
        "headline": headline,
        "evidence": evidence,
        "implication": implication,
        "a100_90d": a100_90d,
        "h200_90d": h200_90d,
        "b200_90d": b200_90d,
    }


def _official_signal_summary(official_events: pd.DataFrame) -> Dict[str, Any]:
    if official_events.empty:
        return {
            "rows": 0,
            "coverage": "0/5 hyperscalers",
            "evidence": "官方 CAPEX/RPO/需求事件尚未接入。",
            "implication": "缺少官方确认层，价格信号不能升级。",
        }

    rows = official_events.copy()
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    tickers = set(rows["ticker"].astype(str).str.upper())

    def value_for(ticker: str, metric: str) -> float | None:
        values = rows[
            (rows["ticker"].astype(str).str.upper() == ticker)
            & (rows["metric"] == metric)
        ]["value"].dropna()
        return None if values.empty else float(values.iloc[0])

    meta_low = value_for("META", "fy2026_capex_guidance_low")
    meta_high = value_for("META", "fy2026_capex_guidance_high")
    meta_previous_low = value_for("META", "fy2026_capex_guidance_previous_low")
    meta_previous_high = value_for("META", "fy2026_capex_guidance_previous_high")
    googl_backlog = value_for("GOOGL", "cloud_backlog")
    orcl_rpo = value_for("ORCL", "remaining_performance_obligations")
    amzn_ai_capex = value_for("AMZN", "ttm_capex_increase_reflects_ai_investment")
    msft_demand = value_for("MSFT", "customer_demand_exceeds_supply")

    evidence_parts = []
    if meta_low is not None and meta_high is not None:
        previous = (
            f" vs prior {_plain_number(meta_previous_low, 'B')}-{_plain_number(meta_previous_high, 'B')}"
            if meta_previous_low is not None and meta_previous_high is not None
            else ""
        )
        evidence_parts.append(f"META capex {_plain_number(meta_low, 'B')}-{_plain_number(meta_high, 'B')}{previous}")
    if googl_backlog is not None:
        evidence_parts.append(f"GOOGL Cloud backlog >{_plain_number(googl_backlog, 'B')}")
    if orcl_rpo is not None:
        evidence_parts.append(f"ORCL RPO {_plain_number(orcl_rpo, 'B')}")
    if amzn_ai_capex is not None:
        evidence_parts.append(f"AMZN TTM PPE increase {_plain_number(amzn_ai_capex, 'B')} tied to AI")
    if msft_demand:
        evidence_parts.append("MSFT demand still exceeds supply")

    coverage_count = len(tickers & {"MSFT", "AMZN", "GOOGL", "META", "ORCL"})
    evidence = "；".join(evidence_parts) if evidence_parts else "官方事件行存在，但未形成可读 CAPEX/RPO 摘要。"
    return {
        "rows": int(len(rows)),
        "coverage": f"{coverage_count}/5 hyperscalers",
        "evidence": evidence,
        "implication": "官方 CAPEX/RPO/需求层仍偏扩张，不支持把旧卡降价直接解释成云厂商 CAPEX 下修。",
    }


def _model_value_summary(market_facts: pd.DataFrame) -> Dict[str, Any]:
    if market_facts.empty:
        return {
            "rows": 0,
            "models": 0,
            "top_value_model": "",
            "top_value_score": None,
            "top_value_quality": None,
            "top_value_output_price": None,
            "top_quality_model": "",
            "top_quality_score": None,
            "top_quality_value": None,
            "evidence": "缺少模型质量/价效比事实。",
        }
    rows = market_facts[market_facts["track"] == "model_value_score"].copy()
    if rows.empty:
        return {
            "rows": 0,
            "models": 0,
            "top_value_model": "",
            "top_value_score": None,
            "top_value_quality": None,
            "top_value_output_price": None,
            "top_quality_model": "",
            "top_quality_score": None,
            "top_quality_value": None,
            "evidence": "缺少模型质量/价效比事实。",
        }
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    pivot = (
        rows.pivot_table(index=["entity", "vendor", "sub_entity"], columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    required = {"quality_score", "value_score_per_output_dollar", "output_price_per_1m_tokens"}
    if pivot.empty or not required.issubset(pivot.columns):
        return {
            "rows": int(len(rows)),
            "models": int(rows["entity"].nunique()),
            "top_value_model": "",
            "top_value_score": None,
            "top_value_quality": None,
            "top_value_output_price": None,
            "top_quality_model": "",
            "top_quality_score": None,
            "top_quality_value": None,
            "evidence": "模型价效比事实不完整。",
        }
    high_quality = pivot[pd.to_numeric(pivot["quality_score"], errors="coerce") >= 80].copy()
    top_value = high_quality.sort_values("value_score_per_output_dollar", ascending=False).iloc[0] if not high_quality.empty else None
    top_quality = pivot.sort_values(["quality_score", "value_score_per_output_dollar"], ascending=[False, False]).iloc[0]
    if top_value is None:
        evidence = "CostGoat 有模型质量/价格事实，但没有 quality>=80 的高质量样本。"
    else:
        evidence = (
            f"CostGoat high-quality value leader: {top_value['entity']} "
            f"quality {_plain_number(top_value['quality_score'])}, output {_money(top_value['output_price_per_1m_tokens'], '/1M')}, "
            f"value {_plain_number(top_value['value_score_per_output_dollar'])}."
        )
    return {
        "rows": int(len(rows)),
        "models": int(pivot["entity"].nunique()),
        "top_value_model": "" if top_value is None else str(top_value["entity"]),
        "top_value_score": None if top_value is None else float(top_value["value_score_per_output_dollar"]),
        "top_value_quality": None if top_value is None else float(top_value["quality_score"]),
        "top_value_output_price": None if top_value is None else float(top_value["output_price_per_1m_tokens"]),
        "top_quality_model": str(top_quality["entity"]),
        "top_quality_score": float(top_quality["quality_score"]),
        "top_quality_value": float(top_quality["value_score_per_output_dollar"]),
        "evidence": evidence,
    }


def _market_track_summary(market_facts: pd.DataFrame) -> Dict[str, Any]:
    if market_facts.empty:
        return {
            "gpu_rows": 0,
            "gpu_entities": 0,
            "gpu_trend_rows": 0,
            "gpu_trend_days": 0,
            "gpu_market_trend_rows": 0,
            "gpu_available_offer_rows": 0,
            "gpu_available_offer_entities": 0,
            "h100_available_min": None,
            "h200_available_min": None,
            "b200_available_min": None,
            "h100_available_count": None,
            "cloud_rows": 0,
            "cloud_entities": 0,
            "cloud_vendors": 0,
            "token_rows": 0,
            "token_entities": 0,
            "model_value_rows": 0,
            "model_value_entities": 0,
            "top_value_model": "",
            "top_value_score": None,
            "arr_rows": 0,
            "arr_entities": 0,
            "adoption_rows": 0,
            "multimodal_rows": 0,
            "latest": "",
            "h100_spot_median": None,
            "h100_trend_7d": None,
            "h200_gpusio_30d": None,
            "b200_gpusio_30d": None,
            "azure_h100_spot_min": None,
            "aws_h100_spot_min": None,
            "h100_on_demand_median": None,
            "h200_on_demand_median": None,
            "openai_output_median": None,
            "anthropic_output_median": None,
            "top_arr_company": "",
            "top_arr_value": None,
            "anthropic_adoption": None,
            "openai_adoption": None,
            "seedance_1080p_usd_per_1m": None,
            "seedance_720p_5s_credits": None,
        }

    gpu = market_facts[(market_facts["track"] == "gpu_rental") & (market_facts["metric"] == "price_per_gpu_hour")]
    gpu_trend = market_facts[
        (market_facts["track"] == "gpu_rental_trend")
        & (market_facts["metric"] == "avg_price_per_gpu_hour")
    ].copy()
    cloud = market_facts[
        (market_facts["track"] == "cloud_instance_price")
        & (market_facts["metric"] == "instance_price_per_hour")
    ]
    gpu_market_trend = market_facts[market_facts["track"] == "gpu_market_trend"]
    available_offer_prices = market_facts[
        (market_facts["track"] == "gpu_available_offer")
        & (market_facts["metric"] == "available_price_per_gpu_hour")
    ]
    available_offer_counts = market_facts[
        (market_facts["track"] == "gpu_available_offer")
        & (market_facts["metric"] == "available_offer_count")
    ]
    token = market_facts[market_facts["track"] == "token_price"]
    model_value = market_facts[market_facts["track"] == "model_value_score"]
    arr = market_facts[(market_facts["track"] == "app_commercialization") & (market_facts["metric"] == "arr")]
    adoption = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"] == "business_adoption_share")
    ]
    multimodal = market_facts[market_facts["track"] == "multimodal_generation_cost"]

    def median_value(df: pd.DataFrame) -> float | None:
        if df.empty:
            return None
        return float(pd.to_numeric(df["value"], errors="coerce").dropna().median())

    def min_value(df: pd.DataFrame) -> float | None:
        if df.empty:
            return None
        values = pd.to_numeric(df["value"], errors="coerce").dropna()
        return None if values.empty else float(values.min())

    openai_output = token[
        (token["metric"] == "output_price_per_1m_tokens")
        & (token["vendor"].astype(str).str.contains("openai", case=False, na=False))
        & (pd.to_numeric(token["value"], errors="coerce") > 0)
    ]
    anthropic_output = token[
        (token["metric"] == "output_price_per_1m_tokens")
        & (token["vendor"].astype(str).str.contains("anthropic", case=False, na=False))
        & (pd.to_numeric(token["value"], errors="coerce") > 0)
    ]

    top_arr_company = ""
    top_arr_value = None
    if not arr.empty:
        arr_sorted = arr.sort_values("value", ascending=False)
        top_arr_company = str(arr_sorted.iloc[0]["entity"])
        top_arr_value = float(arr_sorted.iloc[0]["value"])
    anthropic_adoption = median_value(adoption[adoption["entity"] == "Anthropic"])
    openai_adoption = median_value(adoption[adoption["entity"] == "OpenAI"])
    seedance_1080p_usd_per_1m = median_value(
        multimodal[
            (multimodal["entity"] == "Dreamina Seedance 2.0")
            & (multimodal["sub_entity"] == "1080p")
            & (multimodal["metric"] == "video_generation_price_per_1m_tokens")
            & (multimodal["dimension"] == "input_without_video")
        ]
    )
    seedance_720p_5s_credits = median_value(
        multimodal[
            (multimodal["entity"] == "Seedance 2.0")
            & (multimodal["sub_entity"] == "720p")
            & (multimodal["metric"] == "video_generation_5s_example_credits")
            & (multimodal["dimension"] == "without_video_input")
        ]
    )
    value_summary = _model_value_summary(market_facts)

    return {
        "gpu_rows": int(len(gpu)),
        "gpu_entities": int(gpu["entity"].nunique()) if not gpu.empty else 0,
        "gpu_trend_rows": int(len(gpu_trend)),
        "gpu_trend_days": int(gpu_trend["date"].nunique()) if not gpu_trend.empty else 0,
        "gpu_market_trend_rows": int(len(gpu_market_trend)),
        "gpu_available_offer_rows": int(len(available_offer_prices)),
        "gpu_available_offer_entities": int(available_offer_prices["entity"].nunique()) if not available_offer_prices.empty else 0,
        "h100_available_min": min_value(available_offer_prices[available_offer_prices["entity"] == "H100"]),
        "h200_available_min": min_value(available_offer_prices[available_offer_prices["entity"] == "H200"]),
        "b200_available_min": min_value(available_offer_prices[available_offer_prices["entity"] == "B200"]),
        "h100_available_count": median_value(
            available_offer_counts[available_offer_counts["entity"] == "H100"]
        ),
        "cloud_rows": int(len(cloud)),
        "cloud_entities": int(cloud["sub_entity"].nunique()) if not cloud.empty else 0,
        "cloud_vendors": int(cloud["vendor"].nunique()) if not cloud.empty else 0,
        "token_rows": int(len(token)),
        "token_entities": int(token["entity"].nunique()) if not token.empty else 0,
        "model_value_rows": int(len(model_value)),
        "model_value_entities": int(model_value["entity"].nunique()) if not model_value.empty else 0,
        "top_value_model": value_summary["top_value_model"],
        "top_value_score": value_summary["top_value_score"],
        "arr_rows": int(len(arr)),
        "arr_entities": int(arr["entity"].nunique()) if not arr.empty else 0,
        "adoption_rows": int(len(adoption)),
        "multimodal_rows": int(len(multimodal)),
        "latest": str(market_facts["fetched_at"].max()) if "fetched_at" in market_facts.columns else "",
        "h100_spot_median": median_value(gpu[(gpu["entity"] == "H100") & (gpu["dimension"] == "spot")]),
        "h100_trend_7d": _trend_return(gpu_trend[gpu_trend["entity"] == "H100"], value_col="value"),
        "h200_gpusio_30d": median_value(
            gpu_market_trend[
                (gpu_market_trend["entity"] == "NVIDIA H200")
                & (gpu_market_trend["metric"] == "price_delta_30d_pct")
            ]
        ),
        "b200_gpusio_30d": median_value(
            gpu_market_trend[
                (gpu_market_trend["entity"] == "NVIDIA B200")
                & (gpu_market_trend["metric"] == "price_delta_30d_pct")
            ]
        ),
        "azure_h100_spot_min": (
            float(pd.to_numeric(cloud[(cloud["vendor"] == "Azure") & (cloud["entity"] == "H100") & (cloud["dimension"] == "spot")]["value"], errors="coerce").dropna().min())
            if not cloud[(cloud["vendor"] == "Azure") & (cloud["entity"] == "H100") & (cloud["dimension"] == "spot")].empty
            else None
        ),
        "aws_h100_spot_min": (
            float(pd.to_numeric(cloud[(cloud["vendor"] == "AWS") & (cloud["entity"] == "H100") & (cloud["dimension"] == "spot")]["value"], errors="coerce").dropna().min())
            if not cloud[(cloud["vendor"] == "AWS") & (cloud["entity"] == "H100") & (cloud["dimension"] == "spot")].empty
            else None
        ),
        "h100_on_demand_median": median_value(gpu[(gpu["entity"] == "H100") & (gpu["dimension"] == "on_demand")]),
        "h200_on_demand_median": median_value(gpu[(gpu["entity"] == "H200") & (gpu["dimension"] == "on_demand")]),
        "openai_output_median": median_value(openai_output),
        "anthropic_output_median": median_value(anthropic_output),
        "top_arr_company": top_arr_company,
        "top_arr_value": top_arr_value,
        "anthropic_adoption": anthropic_adoption,
        "openai_adoption": openai_adoption,
        "seedance_1080p_usd_per_1m": seedance_1080p_usd_per_1m,
        "seedance_720p_5s_credits": seedance_720p_5s_credits,
    }


def _money(value: Any, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"${float(value):,.2f}{suffix}"


def _percent(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.0f}%"


def _point_percent(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.1f}%"


def _plain_number(value: Any, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    text = f"{float(value):,.1f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _short_text(value: Any, limit: int = 150) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _signed_percent(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:+.1f}%"


def _vendor_norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text.lstrip("~") or "unknown"


def _render_four_track_summary(data: Dict[str, Any]) -> None:
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    summary = _market_track_summary(market_facts)
    st.subheader("四轨市场监控")
    _render_metric_grid(
        [
            ("GPU 租赁/spot", f"{summary['gpu_entities']} GPUs", f"H100 spot median {_money(summary['h100_spot_median'], '/hr')}"),
            ("可用GPU订单簿", f"{summary['gpu_available_offer_entities']} GPUs", f"H100 min {_money(summary['h100_available_min'], '/GPU hr')} / offers {_plain_number(summary['h100_available_count'])}"),
            ("GPU 7日趋势", f"{summary['gpu_trend_days']} days", f"H100 {_signed_percent(summary['h100_trend_7d'])}"),
            ("GPUs.io 30/90日", f"{summary['gpu_market_trend_rows']} facts", f"H200/B200 30d {_point_percent(summary['h200_gpusio_30d'])}/{_point_percent(summary['b200_gpusio_30d'])}"),
            ("官方云实例", f"{summary['cloud_vendors']} clouds / {summary['cloud_entities']} SKUs", f"Azure/AWS H100 spot min {_money(summary['azure_h100_spot_min'], '')}/{_money(summary['aws_h100_spot_min'], '/VM hr')}"),
            ("Token/API 价格", f"{summary['token_entities']} models", f"OpenAI output median {_money(summary['openai_output_median'], '/1M')}"),
            ("模型价效比", f"{summary['model_value_entities']} models", f"top value {summary['top_value_model'] or 'n/a'} {_plain_number(summary['top_value_score'])}"),
            ("AI 应用 ARR", f"{summary['arr_entities']} companies", f"top: {summary['top_arr_company'] or 'n/a'}"),
            ("企业采用率", f"{summary['adoption_rows']} signals", f"Anthropic/OpenAI {_point_percent(summary['anthropic_adoption'])}/{_point_percent(summary['openai_adoption'])}"),
            ("多模态生成成本", f"{summary['multimodal_rows']} facts", f"Seedance 1080p {_money(summary['seedance_1080p_usd_per_1m'], '/1M tok')}"),
        ]
    )

    if market_facts.empty:
        st.warning("market-facts 还没有生产数据；请先运行 `python3 tracker_v2.py update --production --only market-facts --db ai_compute_tracker_production.db`。")
        return

    st.markdown(
        """
<div class="decision-note">
当前可用判断：GPU 租赁、token/API 价格和多模态生成成本已经可以做横截面监控；ARR 只接入公开榜单，不能当完整私企收入历史。趋势拐点需要继续沉淀本地快照，尤其是官方云 spot、硬件现货和 ARR 历史。
注意：GPU 租赁横截面的体验不应与 gpus.io 正面对打；本产品的价值必须来自跨层判断。官方云实例价格单独展示为 VM-hour，不与 neocloud 的 per-GPU-hour 混算。
</div>
""",
        unsafe_allow_html=True,
    )


def _render_market_decision_cards(data: Dict[str, Any]) -> None:
    st.subheader("二级市场决策读数")
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    official_events = data["tables"].get("official_events", _empty_df([]))
    if market_facts.empty:
        st.warning("缺少 market-facts，无法生成决策读数。")
        return

    facts = market_facts.copy()
    facts["value"] = pd.to_numeric(facts["value"], errors="coerce")
    gpu = facts[(facts["track"] == "gpu_rental") & (facts["metric"] == "price_per_gpu_hour")]
    gpu_trend = facts[(facts["track"] == "gpu_rental_trend") & (facts["metric"] == "avg_price_per_gpu_hour")]
    gpu_market_trend = facts[facts["track"] == "gpu_market_trend"]
    available_offer_prices = facts[
        (facts["track"] == "gpu_available_offer")
        & (facts["metric"] == "available_price_per_gpu_hour")
    ]
    available_offer_counts = facts[
        (facts["track"] == "gpu_available_offer")
        & (facts["metric"] == "available_offer_count")
    ]
    cloud = facts[(facts["track"] == "cloud_instance_price") & (facts["metric"] == "instance_price_per_hour")]
    token = facts[(facts["track"] == "token_price") & (facts["metric"] == "output_price_per_1m_tokens") & (facts["value"] > 0)].copy()
    value_summary = _model_value_summary(facts)
    arr = facts[(facts["track"] == "app_commercialization") & (facts["metric"] == "arr")]
    adoption = facts[
        (facts["track"] == "app_commercialization")
        & (facts["metric"] == "business_adoption_share")
    ]
    multimodal = facts[facts["track"] == "multimodal_generation_cost"]
    proxy_summary = _proxy_history_summary(data.get("public_proxy_history", _empty_df(PUBLIC_PROXY_HISTORY_COLUMNS)))
    official_rows = int(data["quality_gate"].table_counts.get("production_official_events", 0))
    official_summary = _official_signal_summary(official_events)

    def median_value(df: pd.DataFrame) -> float | None:
        values = pd.to_numeric(df["value"], errors="coerce").dropna()
        return None if values.empty else float(values.median())

    def min_value(df: pd.DataFrame) -> float | None:
        values = pd.to_numeric(df["value"], errors="coerce").dropna()
        return None if values.empty else float(values.min())

    h100_spot = median_value(gpu[(gpu["entity"] == "H100") & (gpu["dimension"] == "spot")])
    h100_on_demand = median_value(gpu[(gpu["entity"] == "H100") & (gpu["dimension"] == "on_demand")])
    h100_discount = None
    if h100_spot is not None and h100_on_demand:
        h100_discount = max(0.0, min(1.0, (h100_on_demand - h100_spot) / h100_on_demand))
    h100_trend = _trend_return(gpu_trend[gpu_trend["entity"] == "H100"], value_col="value")
    h200_trend = _trend_return(gpu_trend[gpu_trend["entity"] == "H200"], value_col="value")
    b200_trend = _trend_return(gpu_trend[gpu_trend["entity"] == "B200"], value_col="value")
    trend_days = int(gpu_trend["date"].nunique()) if not gpu_trend.empty else 0
    h100_available_min = min_value(available_offer_prices[available_offer_prices["entity"] == "H100"])
    h200_available_min = min_value(available_offer_prices[available_offer_prices["entity"] == "H200"])
    b200_available_min = min_value(available_offer_prices[available_offer_prices["entity"] == "B200"])
    h100_available_count = median_value(available_offer_counts[available_offer_counts["entity"] == "H100"])
    h200_available_count = median_value(available_offer_counts[available_offer_counts["entity"] == "H200"])
    b200_available_count = median_value(available_offer_counts[available_offer_counts["entity"] == "B200"])
    gpusio_h200_30d = median_value(
        gpu_market_trend[
            (gpu_market_trend["entity"] == "NVIDIA H200")
            & (gpu_market_trend["metric"] == "price_delta_30d_pct")
        ]
    )
    gpusio_h200_90d = median_value(
        gpu_market_trend[
            (gpu_market_trend["entity"] == "NVIDIA H200")
            & (gpu_market_trend["metric"] == "price_delta_90d_pct")
        ]
    )
    gpusio_b200_30d = median_value(
        gpu_market_trend[
            (gpu_market_trend["entity"] == "NVIDIA B200")
            & (gpu_market_trend["metric"] == "price_delta_30d_pct")
        ]
    )
    gpusio_b200_90d = median_value(
        gpu_market_trend[
            (gpu_market_trend["entity"] == "NVIDIA B200")
            & (gpu_market_trend["metric"] == "price_delta_90d_pct")
        ]
    )
    gpusio_a100_90d = median_value(
        gpu_market_trend[
            (gpu_market_trend["entity"] == "NVIDIA A100 80GB")
            & (gpu_market_trend["metric"] == "price_delta_90d_pct")
        ]
    )
    h100_in_gpusio_movers = bool((gpu_market_trend["entity"] == "NVIDIA H100").any()) if not gpu_market_trend.empty else False

    azure_h100_spot = min_value(cloud[(cloud["vendor"] == "Azure") & (cloud["entity"] == "H100") & (cloud["dimension"] == "spot")])
    aws_h100_spot = min_value(cloud[(cloud["vendor"] == "AWS") & (cloud["entity"] == "H100") & (cloud["dimension"] == "spot")])

    token["vendor_norm"] = token["vendor"].map(_vendor_norm)
    openai_output = median_value(token[token["vendor_norm"] == "openai"])
    anthropic_output = median_value(token[token["vendor_norm"] == "anthropic"])
    deepseek_output = median_value(token[token["vendor_norm"] == "deepseek"])
    bytedance_output = median_value(token[token["vendor_norm"].str.contains("bytedance", na=False)])
    seedance_1080p_official = median_value(
        multimodal[
            (multimodal["entity"] == "Dreamina Seedance 2.0")
            & (multimodal["sub_entity"] == "1080p")
            & (multimodal["metric"] == "video_generation_price_per_1m_tokens")
            & (multimodal["dimension"] == "input_without_video")
        ]
    )
    seedance_720p_credits = median_value(
        multimodal[
            (multimodal["entity"] == "Seedance 2.0")
            & (multimodal["sub_entity"] == "720p")
            & (multimodal["metric"] == "video_generation_5s_example_credits")
            & (multimodal["dimension"] == "without_video_input")
        ]
    )

    top_arr = None
    if not arr.empty:
        top_arr = arr.sort_values("value", ascending=False).iloc[0]
    anthropic_adoption = median_value(adoption[adoption["entity"] == "Anthropic"])
    openai_adoption = median_value(adoption[adoption["entity"] == "OpenAI"])
    overall_adoption = median_value(adoption[adoption["entity"] == "Overall AI adoption"])

    if top_arr is None:
        commercialization_evidence = (
            f"Ramp AI Index May 2026: Anthropic {_point_percent(anthropic_adoption)}、"
            f"OpenAI {_point_percent(openai_adoption)}、overall {_point_percent(overall_adoption)} corporate payment adoption."
        )
    else:
        commercialization_evidence = (
            f"ARR.club public top signal: {top_arr['entity']} {_money(top_arr['value'], 'B public signal')}；"
            f"Ramp AI Index May 2026: Anthropic {_point_percent(anthropic_adoption)}、"
            f"OpenAI {_point_percent(openai_adoption)}、overall {_point_percent(overall_adoption)} corporate payment adoption."
        )

    rows = [
        {
            "资产层": "硬件 / 算力基础设施",
            "当前读数": "偏负观察，尚不足以交易",
            "证据": f"H100 租赁 spot median {_money(h100_spot, '/hr')}，on-demand median {_money(h100_on_demand, '/hr')}，折扣约 {_percent(h100_discount)}；GPUPerHour 当前可用 order book：H100 min {_money(h100_available_min, '/GPU hr')}（{_plain_number(h100_available_count)} offers）、H200 min {_money(h200_available_min, '/GPU hr')}（{_plain_number(h200_available_count)} offers）、B200 min {_money(b200_available_min, '/GPU hr')}（{_plain_number(b200_available_count)} offers）；ComputePrices public trend {trend_days} 天：H100 {_signed_percent(h100_trend)}、H200 {_signed_percent(h200_trend)}、B200 {_signed_percent(b200_trend)}；GPUs.io 90d movers：H200 {_point_percent(gpusio_h200_30d)} 30d/{_point_percent(gpusio_h200_90d)} 90d，B200 {_point_percent(gpusio_b200_30d)} 30d/{_point_percent(gpusio_b200_90d)} 90d，A100 80GB {_point_percent(gpusio_a100_90d)} 90d，H100 {'在 material movers 中' if h100_in_gpusio_movers else '未进入 material movers'}。",
            "二级市场含义": "短期价格没有给出单边下行确认；A100 等旧卡 90 日下跌说明非前沿算力商品化更明显，但 H200/B200 仍偏紧，不能直接推导 GPU/服务器订单下修。",
            "反证/升级条件": "需要 30/60/90 天趋势转弱，或云厂商 CAPEX / RPO / 管理层指引同步转弱。",
        },
        {
            "资产层": "Hyperscaler 云厂商",
            "当前读数": "CAPEX/RPO 仍偏扩张",
            "证据": f"Azure/AWS 已有官方 spot/current spot 横截面；H100 min 为 {_money(azure_h100_spot, '')}/{_money(aws_h100_spot, '/VM hr')}，口径是 VM-hour。官方事件：{official_summary['evidence']}。",
            "二级市场含义": f"闲置算力变现可能利好云厂商利用率，但 VM-hour 不能直接与 neocloud per-GPU-hour 混算。{official_summary['implication']}",
            "反证/升级条件": "需要看到官方 cloud spot 历史持续走低，同时 CAPEX 指引没有继续上修。",
        },
        {
            "资产层": "AI 应用 / 模型 API",
            "当前读数": "成本端改善线索",
            "证据": f"OpenAI output median {_money(openai_output, '/1M')}，Anthropic {_money(anthropic_output, '/1M')}，DeepSeek {_money(deepseek_output, '/1M')}，ByteDance {_money(bytedance_output, '/1M')}；{value_summary['evidence']} BytePlus Seedance 1080p 官方视频生成价 {_money(seedance_1080p_official, '/1M tokens')}，seedance2.ai 720p 5s wrapper example {_plain_number(seedance_720p_credits, ' credits')}。",
            "二级市场含义": "更支持应用层和 API routing 的毛利改善，而不是单纯硬件链受益；高质量模型之间价效比分化大，应用公司可通过路由把常规任务迁移到更高 value/price 的模型。",
            "反证/升级条件": "需要 Artificial Analysis API key 或等价授权源确认 benchmark；Seedance 官方 token 价和第三方 credits 价不能混算。",
        },
        {
            "资产层": "AI 应用商业化",
            "当前读数": "有需求信号，但仍需验证收入质量",
            "证据": commercialization_evidence,
            "二级市场含义": "说明应用层收入叙事值得跟踪，但不能当作审计 ARR 或完整私企财务。",
            "反证/升级条件": "需要 ARR.club Pro/source links、Sacra 或公司一手披露来确认历史、口径和续费质量。",
        },
        {
            "资产层": "总判断",
            "当前读数": "No Signal / WARN",
            "证据": f"生产事实 {len(market_facts):,} 行，official event rows={official_rows}（{official_summary['coverage']}），ORNN/GCP/AWS history/ARR deep source 仍有缺口。",
            "二级市场含义": "价格层显示代际分化，适合降低对单一稀缺叙事的确定性；但官方 CAPEX/RPO 层仍偏扩张，不适合输出方向性 cracking call。",
            "反证/升级条件": "当价格趋势、官方云 spot、CAPEX 指引和应用 ARR 至少两层同向时，才升级为可行动信号。",
        },
    ]
    for row in rows:
        st.markdown(
            f"""
<div class="readout-card">
  <div class="readout-title">{row['资产层']}：{row['当前读数']}</div>
  <div class="readout-line"><span class="readout-label">证据：</span>{row['证据']}</div>
  <div class="readout-line"><span class="readout-label">二级市场含义：</span>{row['二级市场含义']}</div>
  <div class="readout-line"><span class="readout-label">反证/升级条件：</span>{row['反证/升级条件']}</div>
</div>
""",
            unsafe_allow_html=True,
        )


def _core_evidence_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    official_events = data["tables"].get("official_events", _empty_df([]))
    quality_gate = data["quality_gate"]
    decision = data["decision"]
    regime = _market_regime_summary(market_facts)
    official_summary = _official_signal_summary(official_events)
    summary = _market_track_summary(market_facts)
    value_summary = _model_value_summary(market_facts)

    facts = market_facts.copy()
    if not facts.empty:
        facts["value"] = pd.to_numeric(facts["value"], errors="coerce")

    def median_value(df: pd.DataFrame) -> float | None:
        if df.empty or "value" not in df.columns:
            return None
        values = pd.to_numeric(df["value"], errors="coerce").dropna()
        return None if values.empty else float(values.median())

    def min_value(df: pd.DataFrame) -> float | None:
        if df.empty or "value" not in df.columns:
            return None
        values = pd.to_numeric(df["value"], errors="coerce").dropna()
        return None if values.empty else float(values.min())

    gpusio = facts[facts["track"] == "gpu_market_trend"] if not facts.empty else facts
    offers = facts[
        (facts["track"] == "gpu_available_offer")
        & (facts["metric"] == "available_price_per_gpu_hour")
    ] if not facts.empty else facts
    counts = facts[
        (facts["track"] == "gpu_available_offer")
        & (facts["metric"] == "available_offer_count")
    ] if not facts.empty else facts
    rental_trend = facts[
        (facts["track"] == "gpu_rental_trend")
        & (facts["metric"] == "avg_price_per_gpu_hour")
    ] if not facts.empty else facts

    gpu_rows = []
    gpu_map = [
        ("A100 80GB", "NVIDIA A100 80GB", "A100"),
        ("H100", "NVIDIA H100", "H100"),
        ("H200", "NVIDIA H200", "H200"),
        ("B200", "NVIDIA B200", "B200"),
    ]
    for label, gpusio_entity, offer_entity in gpu_map:
        delta90 = median_value(
            gpusio[
                (gpusio["entity"] == gpusio_entity)
                & (gpusio["metric"] == "price_delta_90d_pct")
            ]
        ) if not gpusio.empty else None
        min_offer = min_value(offers[offers["entity"] == offer_entity]) if not offers.empty else None
        offer_count = median_value(counts[counts["entity"] == offer_entity]) if not counts.empty else None
        seven_day = _trend_return(rental_trend[rental_trend["entity"] == offer_entity], value_col="value") if not rental_trend.empty else None
        gpu_rows.append(
            {
                "GPU": label,
                "90日变化": _point_percent(delta90),
                "7日租赁": _signed_percent(seven_day),
                "当前可用最低价": _money(min_offer, "/GPU hr"),
                "可用offer": _plain_number(offer_count),
                "delta90_numeric": delta90,
                "min_offer_numeric": min_offer,
                "offer_count_numeric": offer_count,
            }
        )

    decision_state = "Blocked" if decision is None else decision.state
    gpu_table = pd.DataFrame(gpu_rows)
    evidence_rows = [
        {
            "证据层": "价格层",
            "读数": regime["label"],
            "最关键证据": regime["evidence"],
            "现在说明什么": regime["implication"],
        },
        {
            "证据层": "官方层",
            "读数": official_summary["coverage"],
            "最关键证据": official_summary["evidence"],
            "现在说明什么": official_summary["implication"],
        },
        {
            "证据层": "应用/API层",
            "读数": f"{summary['model_value_entities']} models / {summary['arr_entities']} ARR names",
            "最关键证据": value_summary["evidence"],
            "现在说明什么": "价效比改善更像应用层毛利和 routing 机会，不足以单独证明硬件链转弱。",
        },
    ]
    if quality_gate.status != "PASS":
        evidence_rows.append(
            {
                "证据层": "质量门",
                "读数": quality_gate.status,
                "最关键证据": "ORNN/OCPI、GCP spot、AWS 90天 history、ARR 深源等仍有缺口。",
                "现在说明什么": "可以做观察和反证框架，不能把 No Signal 包装成交易信号。",
            }
        )

    return {
        "decision_state": decision_state,
        "quality_status": quality_gate.status,
        "regime": regime,
        "official_summary": official_summary,
        "model_value_summary": value_summary,
        "summary": summary,
        "gpu_table": gpu_table,
        "evidence_table": pd.DataFrame(evidence_rows),
    }


def _render_core_evidence(data: Dict[str, Any]) -> None:
    snapshot = _core_evidence_snapshot(data)
    regime = snapshot["regime"]
    official = snapshot["official_summary"]
    model_value = snapshot["model_value_summary"]
    summary = snapshot["summary"]

    st.subheader("核心证据链")
    st.markdown(
        f"""
<div class="evidence-grid">
  <div class="evidence-card">
    <div class="evidence-layer">价格层</div>
    <div class="evidence-verdict">{regime['label']}</div>
    <div class="evidence-body">A100 90日 {_point_percent(regime['a100_90d'])}；H200 {_point_percent(regime['h200_90d'])}；B200 {_point_percent(regime['b200_90d'])}。</div>
  </div>
  <div class="evidence-card">
    <div class="evidence-layer">官方层</div>
    <div class="evidence-verdict">{official['coverage']}</div>
    <div class="evidence-body">CAPEX、RPO、需求表述仍偏扩张，暂不支持 CAPEX 下修判断。</div>
  </div>
  <div class="evidence-card">
    <div class="evidence-layer">应用/API层</div>
    <div class="evidence-verdict">{summary['model_value_entities']} models / {summary['arr_entities']} ARR names</div>
    <div class="evidence-body">价效比改善更支持应用层毛利和 routing 机会。</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.05, 1])
    gpu_table = snapshot["gpu_table"].copy()
    with left:
        numeric = gpu_table.dropna(subset=["delta90_numeric"]).copy()
        if not numeric.empty:
            fig = px.bar(
                numeric,
                x="GPU",
                y="delta90_numeric",
                color="GPU",
                hover_data=["当前可用最低价", "可用offer", "7日租赁"],
                labels={"delta90_numeric": "90日价格变化，%", "GPU": "GPU"},
                title="价格层：旧卡松动，前沿卡仍未同步转弱",
            )
            fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#6b7280")
            fig.update_layout(height=330, margin=dict(l=10, r=10, t=45, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key="core_gpu_90d_bar")
        st.dataframe(
            gpu_table.drop(columns=["delta90_numeric", "min_offer_numeric", "offer_count_numeric"], errors="ignore"),
            width="stretch",
            hide_index=True,
        )
    with right:
        st.metric("当前判断", snapshot["decision_state"], snapshot["quality_status"])
        st.metric("H100 当前可用最低价", _money(summary["h100_available_min"], "/GPU hr"), f"{_plain_number(summary['h100_available_count'])} offers")
        st.metric("高质量价效比 leader", model_value["top_value_model"] or "n/a", _plain_number(model_value["top_value_score"]))
        with st.expander("展开完整依据", expanded=False):
            st.dataframe(snapshot["evidence_table"], width="stretch", hide_index=True)
            st.markdown(f"**官方层原文摘要**：{official['evidence']}")
            st.markdown(f"**应用/API层摘要**：{model_value['evidence']}")
            st.markdown("**读法**：价格层削弱单一稀缺叙事，但官方层仍偏扩张；所以当前是观察框架，不是方向性交易信号。")


def _decision_headline(data: Dict[str, Any]) -> str:
    quality_gate = data["quality_gate"]
    decision = data["decision"]
    regime = _market_regime_summary(data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS)))
    official_summary = _official_signal_summary(data["tables"].get("official_events", _empty_df([])))
    if quality_gate.status == FAIL:
        return "当前：数据不足。不能输出投资判断。"
    if decision and decision.state == "Scarcity Premium Cracking":
        return "当前：稀缺溢价破裂信号出现。需要逐项核对反证。"
    return f"当前：{regime['label']} / No Signal。价格层有松动，官方层仍未转弱（{official_summary['coverage']}）。"


def _decision_explanation(data: Dict[str, Any]) -> str:
    quality_gate = data["quality_gate"]
    decision = data["decision"]
    proxy_summary = _proxy_history_summary(data.get("public_proxy_history", _empty_df(PUBLIC_PROXY_HISTORY_COLUMNS)))
    snapshot_summary = _pricing_snapshot_summary(data["tables"].get("gpu_prices", _empty_df([])))
    regime = _market_regime_summary(data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS)))
    official_summary = _official_signal_summary(data["tables"].get("official_events", _empty_df([])))
    if quality_gate.status == FAIL:
        return "当前生产证据不足，不能输出投资判断；页面不会用 seed、mock 或旧 CSI 补图。"
    if decision and decision.state == "Scarcity Premium Cracking":
        return "价格层和官方确认层同时指向稀缺溢价破裂，但仍需逐项核对来源和反证。"
    return (
        f"当前最小可用判断是 {regime['label']} / No Signal：{regime['evidence']}"
        f"{regime['implication']}"
        f"ComputePrices proxy 有 {proxy_summary['proxy_days']} 个 quote-date，其中 "
        f"{proxy_summary['adequate_days']} 个日期达到 {ADEQUATE_PROXY_QUOTE_COUNT}+ 报价样本；"
        f"RunPod/Lambda 官方价格页只有 {snapshot_summary['days']} 个快照日。"
        f"官方事件层覆盖 {official_summary['coverage']}：{official_summary['evidence']}。"
        "同时 token/API 与 ARR 已进入四轨监控，但历史仍需本地快照继续沉淀。"
    )


def _render_compact_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
<div class="compact-card">
  <div class="card-label">{label}</div>
  <div class="card-value">{value}</div>
  <div class="card-note">{note}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_metric_grid(items: list[tuple[str, str, str]]) -> None:
    cards = []
    for label, value, note in items:
        cards.append(
            f"""
  <div class="metric-card">
    <div class="metric-label">{label}</div>
    <div class="metric-value">{value}</div>
    <div class="metric-note">{note}</div>
  </div>
"""
        )
    st.markdown(f'<div class="metric-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _render_public_proxy_history(proxy_history: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("公开报价 proxy 历史")
    st.caption(
        f"只读 `production_public_proxy_prices`。只有 quote_count >= {ADEQUATE_PROXY_QUOTE_COUNT} 的日期进入趋势线；"
        "低样本日期只在明细中暴露，不连成趋势。"
    )
    if proxy_history.empty:
        st.warning("No public proxy history is available.")
        return

    plot_df = proxy_history[proxy_history["gpu_model"].isin(["H100", "H200"])].copy()
    if plot_df.empty:
        st.warning("No H100/H200 public proxy rows.")
        return
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df["quote_count"] = pd.to_numeric(plot_df["quote_count"], errors="coerce").fillna(0).astype(int)
    adequate = plot_df[plot_df["quote_count"] >= ADEQUATE_PROXY_QUOTE_COUNT].copy()
    thin = plot_df[(plot_df["quote_count"] > 0) & (plot_df["quote_count"] < ADEQUATE_PROXY_QUOTE_COUNT)].copy()

    summary = _proxy_history_summary(proxy_history)
    cols = st.columns(3)
    cols[0].metric("Proxy 日期", f"{summary['proxy_days']}d", f"{summary['adequate_days']}d usable")
    cols[1].metric(
        "H100 最新 proxy",
        "n/a" if summary["latest_h100_median"] is None else f"${summary['latest_h100_median']:.2f}/hr",
        "n/a" if summary["latest_h100_quotes"] is None else f"{summary['latest_h100_quotes']} quotes",
    )
    cols[2].metric(
        "H200 最新 proxy",
        "n/a" if summary["latest_h200_median"] is None else f"${summary['latest_h200_median']:.2f}/hr",
        "n/a" if summary["latest_h200_quotes"] is None else f"{summary['latest_h200_quotes']} quotes",
    )

    if adequate.empty:
        st.warning("Proxy rows exist, but no date has enough quotes to draw a decision-useful trend line.")
    else:
        fig = go.Figure()
        colors = {"H100": "#2563eb", "H200": "#dc2626"}
        for gpu_model, group in adequate.groupby("gpu_model", dropna=False):
            group = group.sort_values("date")
            fig.add_trace(
                go.Scatter(
                    x=group["date"],
                    y=group["median_price_per_gpu_hour"],
                    mode="lines+markers",
                    name=f"{gpu_model} median proxy",
                    line=dict(color=colors.get(str(gpu_model), "#475467"), width=2.7),
                    marker=dict(size=8),
                    customdata=group[["quote_count", "min_price_per_gpu_hour", "source_url", "snapshot_path"]],
                    hovertemplate=(
                        "%{x|%Y-%m-%d}<br>"
                        f"{gpu_model} ComputePrices proxy<br>"
                        "median=%{y:.2f} USD/hr<br>"
                        "min=%{customdata[1]:.2f} USD/hr<br>"
                        "quotes=%{customdata[0]}<extra></extra>"
                    ),
                )
            )
        fig.update_layout(
            height=360,
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis_title="Quote date",
            yaxis_title="Median USD per GPU hour",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=-0.24, x=0),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_public_proxy_history")

    if not thin.empty:
        with st.expander(f"低样本 proxy 日期（{len(thin)} 行，不进入趋势线）", expanded=False):
            st.dataframe(
                thin[
                    [
                        "date",
                        "gpu_model",
                        "median_price_per_gpu_hour",
                        "min_price_per_gpu_hour",
                        "quote_count",
                        "source_url",
                        "snapshot_path",
                    ]
                ].sort_values(["gpu_model", "date"]),
                width="stretch",
                hide_index=True,
            )


def _render_gpu_rental_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("GPU 租赁 / Spot 价格横截面")
    gpu = market_facts[
        (market_facts["track"] == "gpu_rental")
        & (market_facts["metric"] == "price_per_gpu_hour")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if gpu.empty:
        st.warning("No GPU rental market facts.")
        return
    gpu["value"] = pd.to_numeric(gpu["value"], errors="coerce")
    default_models = [model for model in ["H100", "H200", "B200", "B300", "A100", "MI300X"] if model in set(gpu["entity"])]
    models = st.multiselect("GPU 型号", sorted(gpu["entity"].dropna().unique()), default=default_models[:6], key=f"{key_prefix}_gpu_market_models")
    markets = st.multiselect(
        "计费类型",
        sorted(gpu["dimension"].dropna().unique()),
        default=[item for item in ["on_demand", "spot", "reserved"] if item in set(gpu["dimension"])],
        key=f"{key_prefix}_gpu_market_dimensions",
    )
    shown = gpu[gpu["entity"].isin(models) & gpu["dimension"].isin(markets)].copy()
    if shown.empty:
        st.warning("当前筛选没有 GPU 价格样本。")
        return
    fig = px.box(
        shown,
        x="entity",
        y="value",
        color="dimension",
        points="all",
        hover_data=["sub_entity", "source_name", "source_url", "notes"],
        labels={"entity": "GPU", "value": "USD per GPU hour", "dimension": "market"},
    )
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), yaxis_type="log")
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_gpu_rental_box")
    summary = (
        shown.groupby(["entity", "dimension"], dropna=False)["value"]
        .agg(sample_count="count", min_price="min", median_price="median", max_price="max")
        .reset_index()
        .sort_values(["entity", "dimension"])
    )
    st.caption("纵轴使用 log scale，避免超高价云实例压扁低价 spot/marketplace 样本。")
    st.dataframe(summary, width="stretch", hide_index=True)


def _render_gpu_available_offers(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("GPUPerHour 当前可用订单簿")
    offers = market_facts[
        (market_facts["track"] == "gpu_available_offer")
        & (market_facts["metric"] == "available_price_per_gpu_hour")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    counts = market_facts[
        (market_facts["track"] == "gpu_available_offer")
        & (market_facts["metric"] == "available_offer_count")
    ].copy()
    if offers.empty:
        st.warning("No GPUPerHour available offer rows.")
        return
    offers["value"] = pd.to_numeric(offers["value"], errors="coerce")
    default_models = [model for model in ["H100", "H200", "B200", "B300", "A100", "MI300X", "L40S"] if model in set(offers["entity"])]
    models = st.multiselect(
        "可用报价 GPU",
        sorted(offers["entity"].dropna().unique()),
        default=default_models[:7],
        key=f"{key_prefix}_available_offer_models",
    )
    pricing_types = st.multiselect(
        "可用报价计费类型",
        sorted(offers["dimension"].dropna().unique()),
        default=[item for item in ["spot", "on_demand"] if item in set(offers["dimension"])],
        key=f"{key_prefix}_available_offer_pricing",
    )
    shown = offers[offers["entity"].isin(models) & offers["dimension"].isin(pricing_types)].copy()
    if shown.empty:
        st.warning("当前筛选没有 GPUPerHour 可用报价。")
        return
    fig = px.strip(
        shown,
        x="entity",
        y="value",
        color="dimension",
        hover_data=["vendor", "sub_entity", "notes", "source_url"],
        labels={"entity": "GPU", "value": "available USD per GPU hour", "dimension": "pricing"},
    )
    fig.update_traces(jitter=0.22, marker=dict(size=8, opacity=0.75))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), yaxis_type="log")
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_available_offer_strip")

    summary = (
        shown.groupby(["entity", "dimension"], dropna=False)["value"]
        .agg(shown_offer_rows="count", min_available_price="min", median_top50_price="median", max_top50_price="max")
        .reset_index()
        .sort_values(["entity", "dimension"])
    )
    if not counts.empty:
        counts["value"] = pd.to_numeric(counts["value"], errors="coerce")
        count_table = counts[["entity", "value"]].rename(columns={"value": "api_available_offer_total"})
        summary = summary.merge(count_table, on="entity", how="left")
    st.dataframe(summary, width="stretch", hide_index=True)

    lowest = shown.sort_values("value").head(20)[["entity", "vendor", "sub_entity", "dimension", "value", "notes", "source_url"]]
    with st.expander("最低可用报价明细", expanded=False):
        st.dataframe(lowest, width="stretch", hide_index=True)
    st.caption("GPUPerHour API 只展示当前 available=true offer；这里不混入不可用历史报价，也不和 ComputePrices/gpus.io 合并计算中位数。")


def _render_gpu_trend_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("GPU 租赁公开趋势")
    trend = market_facts[
        (market_facts["track"] == "gpu_rental_trend")
        & (market_facts["metric"] == "avg_price_per_gpu_hour")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if trend.empty:
        st.warning("No ComputePrices public trend facts.")
        return
    trend["date"] = pd.to_datetime(trend["date"], errors="coerce")
    trend["value"] = pd.to_numeric(trend["value"], errors="coerce")
    trend = trend.dropna(subset=["date", "value"])
    if trend.empty:
        st.warning("ComputePrices public trend rows are not parseable.")
        return
    default_models = [model for model in ["H100", "H200", "B200"] if model in set(trend["entity"])]
    models = st.multiselect(
        "趋势型号",
        sorted(trend["entity"].dropna().unique()),
        default=default_models,
        key=f"{key_prefix}_gpu_trend_models",
    )
    shown = trend[trend["entity"].isin(models)].copy()
    if shown.empty:
        st.warning("当前筛选没有趋势样本。")
        return
    fig = px.line(
        shown.sort_values("date"),
        x="date",
        y="value",
        color="entity",
        markers=True,
        hover_data=["notes", "source_url", "confidence"],
        labels={"date": "date", "value": "avg USD per GPU hour", "entity": "GPU"},
    )
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_gpu_trend_line")
    returns = []
    for entity, group in shown.groupby("entity", dropna=False):
        returns.append(
            {
                "GPU": entity,
                "days": int(group["date"].nunique()),
                "first_date": group["date"].min().date().isoformat(),
                "last_date": group["date"].max().date().isoformat(),
                "first_price": float(group.sort_values("date").iloc[0]["value"]),
                "last_price": float(group.sort_values("date").iloc[-1]["value"]),
                "period_return": _trend_return(group, value_col="value"),
            }
        )
    ret_df = pd.DataFrame(returns)
    if not ret_df.empty:
        ret_df["period_return"] = ret_df["period_return"].map(_signed_percent)
        st.dataframe(ret_df, width="stretch", hide_index=True)
    st.caption("ComputePrices public tier currently returns 7 days; this is useful for short-term direction, not enough for 30/60/90 day regime calls.")


def _render_gpusio_market_trends(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("GPUs.io 30/90 日 movers")
    trend = market_facts[market_facts["track"] == "gpu_market_trend"].copy()
    if trend.empty:
        st.warning("No GPUs.io market trend facts.")
        return
    trend["value"] = pd.to_numeric(trend["value"], errors="coerce")
    delta = trend[trend["metric"].isin(["price_delta_30d_pct", "price_delta_90d_pct"])].copy()
    if delta.empty:
        st.warning("No GPUs.io delta rows.")
        return
    focus = [
        "NVIDIA H200",
        "NVIDIA B200",
        "NVIDIA A100 80GB",
        "NVIDIA RTX 5090",
        "NVIDIA RTX 4090",
        "NVIDIA L40S",
        "NVIDIA Tesla V100",
    ]
    ordered = [item for item in focus if item in set(delta["entity"])]
    shown = delta[delta["entity"].isin(ordered)].copy() if ordered else delta.copy()
    shown["metric_label"] = shown["metric"].map(
        {"price_delta_30d_pct": "30d delta", "price_delta_90d_pct": "90d delta"}
    )
    fig = px.bar(
        shown,
        x="entity",
        y="value",
        color="metric_label",
        barmode="group",
        hover_data=["notes", "source_url", "confidence"],
        labels={"entity": "GPU", "value": "price change, %", "metric_label": "Window"},
    )
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#6b7280")
    fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_gpusio_delta_bar")

    price = trend[trend["metric"].isin(["median_price_per_gpu_hour", "price_range_low_per_gpu_hour", "price_range_high_per_gpu_hour"])].copy()
    if not price.empty:
        pivot = (
            price.pivot_table(index=["entity", "sub_entity"], columns="metric", values="value", aggfunc="median")
            .reset_index()
            .rename_axis(None, axis=1)
        )
        pivot = pivot[pivot["entity"].isin(ordered)].copy() if ordered else pivot
        required = {"price_range_low_per_gpu_hour", "price_range_high_per_gpu_hour", "median_price_per_gpu_hour"}
        if not pivot.empty and required.issubset(pivot.columns):
            fig_price = go.Figure()
            fig_price.add_trace(
                go.Bar(
                    x=pivot["entity"],
                    y=pivot["median_price_per_gpu_hour"],
                    name="Median $/GPU/hr",
                    marker_color="#2563eb",
                    customdata=pivot[["price_range_low_per_gpu_hour", "price_range_high_per_gpu_hour", "sub_entity"]],
                    hovertemplate=(
                        "%{x}<br>median=%{y:$,.2f}/GPU/hr<br>"
                        "90d range=%{customdata[0]:$,.2f}-%{customdata[1]:$,.2f}<br>"
                        "category=%{customdata[2]}<extra></extra>"
                    ),
                )
            )
            fig_price.update_layout(
                height=330,
                margin=dict(l=10, r=10, t=20, b=10),
                yaxis_title="Median USD / GPU hr",
                showlegend=False,
            )
            st.plotly_chart(fig_price, use_container_width=True, key=f"{key_prefix}_gpusio_price_bar")
    st.caption("GPUs.io 口径是 90-day rolling window 的 median on-demand prices；这里展示 material movers，不代表所有 GPU 都有显著趋势。")


def _render_cloud_instance_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("官方云 GPU 实例价格")
    cloud = market_facts[
        (market_facts["track"] == "cloud_instance_price")
        & (market_facts["metric"] == "instance_price_per_hour")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if cloud.empty:
        st.warning("No official cloud instance price facts.")
        return
    cloud["value"] = pd.to_numeric(cloud["value"], errors="coerce")
    providers = st.multiselect(
        "云厂商",
        sorted(cloud["vendor"].dropna().unique()),
        default=[item for item in ["Azure", "AWS"] if item in set(cloud["vendor"])] or sorted(cloud["vendor"].dropna().unique())[:3],
        key=f"{key_prefix}_cloud_vendors",
    )
    gpu_default = [item for item in ["H100", "H200", "A100", "MI300X", "T4", "RTX PRO 6000"] if item in set(cloud["entity"])]
    gpu_families = st.multiselect(
        "GPU/实例家族",
        sorted(cloud["entity"].dropna().unique()),
        default=gpu_default[:6],
        key=f"{key_prefix}_cloud_gpu_families",
    )
    billing_types = st.multiselect(
        "计费类型",
        sorted(cloud["dimension"].dropna().unique()),
        default=[item for item in ["spot", "low_priority", "on_demand"] if item in set(cloud["dimension"])],
        key=f"{key_prefix}_cloud_billing",
    )
    shown = cloud[
        cloud["vendor"].isin(providers)
        & cloud["entity"].isin(gpu_families)
        & cloud["dimension"].isin(billing_types)
    ].copy()
    if shown.empty:
        st.warning("当前筛选没有官方云实例价格样本。")
        return
    fig = px.box(
        shown,
        x="entity",
        y="value",
        color="dimension",
        points="all",
        hover_data=["vendor", "sub_entity", "notes", "source_url"],
        labels={"entity": "GPU / VM family", "value": "USD per VM hour", "dimension": "billing"},
    )
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), yaxis_type="log")
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_cloud_instance_box")
    st.caption("这里展示的是官方云 VM-hour 价格，不按 GPU 数量拆成 per-GPU-hour；因此不能和 neocloud 租赁价直接混算。")
    summary = (
        shown.groupby(["vendor", "entity", "dimension"], dropna=False)["value"]
        .agg(sample_count="count", min_price="min", median_price="median", max_price="max")
        .reset_index()
        .sort_values(["vendor", "entity", "dimension"])
    )
    st.dataframe(summary, width="stretch", hide_index=True)


def _render_token_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("模型 API / Token 价格")
    token = market_facts[
        (market_facts["track"] == "token_price")
        & (market_facts["metric"].isin(["input_price_per_1m_tokens", "output_price_per_1m_tokens", "cached_input_price_per_1m_tokens"]))
    ].copy()
    if token.empty:
        st.warning("No token price facts.")
        return
    token["value"] = pd.to_numeric(token["value"], errors="coerce")
    token = token[token["value"].notna()]
    vendor_options = sorted([item for item in token["vendor"].dropna().unique() if str(item).strip()])
    preferred = [v for v in vendor_options if str(v).lower() in {"openai", "anthropic", "google", "deepseek", "bytedance", "xai"}]
    selected_vendors = st.multiselect("模型厂商/creator", vendor_options, default=preferred[:6] or vendor_options[:6], key=f"{key_prefix}_token_vendors")
    selected_metric = st.selectbox(
        "价格口径",
        ["output_price_per_1m_tokens", "input_price_per_1m_tokens", "cached_input_price_per_1m_tokens"],
        index=0,
        key=f"{key_prefix}_token_metric",
    )
    shown = token[(token["vendor"].isin(selected_vendors)) & (token["metric"] == selected_metric) & (token["value"] > 0)].copy()
    if shown.empty:
        st.warning("当前筛选没有 token 价格样本。")
        return
    summary = (
        shown.assign(vendor_norm=shown["vendor"].map(_vendor_norm))
        .groupby("vendor_norm", dropna=False)["value"]
        .agg(model_count="count", min_price="min", median_price="median", max_price="max")
        .reset_index()
        .sort_values("median_price")
    )
    fig = px.bar(
        summary,
        x="vendor_norm",
        y="median_price",
        color="vendor_norm",
        hover_data=["model_count", "min_price", "max_price"],
        labels={"vendor_norm": "creator/provider normalized", "median_price": "median USD / 1M tokens"},
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_token_bar")
    with st.expander("Token 价格明细（当前筛选）", expanded=False):
        st.dataframe(
            shown[
                [
                    "vendor",
                    "entity",
                    "sub_entity",
                    "metric",
                    "value",
                    "unit",
                    "source_name",
                    "source_url",
                    "confidence",
                ]
            ].sort_values(["vendor", "value"]),
            width="stretch",
            hide_index=True,
        )


def _render_model_value_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("模型质量 / 价格 / 价效比")
    rows = market_facts[market_facts["track"] == "model_value_score"].copy()
    if rows.empty:
        st.warning("No model quality/value facts.")
        return
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    pivot = (
        rows.pivot_table(index=["entity", "vendor", "sub_entity", "source_url"], columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    required = {"quality_score", "value_score_per_output_dollar", "output_price_per_1m_tokens", "input_price_per_1m_tokens"}
    if pivot.empty or not required.issubset(pivot.columns):
        st.warning("Model quality/value rows are incomplete.")
        return

    provider_options = sorted([item for item in pivot["vendor"].dropna().unique() if str(item).strip()])
    preferred = [item for item in provider_options if str(item).lower() in {"openai", "anthropic", "google", "deepseek", "xiaomi", "minimax", "moonshot", "qwen", "x-ai"}]
    selected = st.multiselect(
        "价效比厂商",
        provider_options,
        default=preferred[:9] or provider_options[:9],
        key=f"{key_prefix}_model_value_vendors",
    )
    min_quality = st.slider("最低质量分", min_value=0, max_value=100, value=75, step=5, key=f"{key_prefix}_model_value_min_quality")
    shown = pivot[
        pivot["vendor"].isin(selected)
        & (pd.to_numeric(pivot["quality_score"], errors="coerce") >= min_quality)
        & (pd.to_numeric(pivot["output_price_per_1m_tokens"], errors="coerce") > 0)
    ].copy()
    if shown.empty:
        st.warning("当前筛选没有模型价效比样本。")
        return

    fig = px.scatter(
        shown,
        x="output_price_per_1m_tokens",
        y="quality_score",
        size="value_score_per_output_dollar",
        color="vendor",
        hover_data=["entity", "sub_entity", "input_price_per_1m_tokens", "value_score_per_output_dollar", "source_url"],
        labels={
            "output_price_per_1m_tokens": "Output USD / 1M tokens",
            "quality_score": "Quality score, 0-100",
            "value_score_per_output_dollar": "Quality per $ output",
        },
        log_x=True,
    )
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_model_value_scatter")

    top_value = shown.sort_values("value_score_per_output_dollar", ascending=False).head(12)
    fig_top = px.bar(
        top_value.sort_values("value_score_per_output_dollar"),
        x="value_score_per_output_dollar",
        y="entity",
        color="vendor",
        orientation="h",
        hover_data=["quality_score", "output_price_per_1m_tokens", "input_price_per_1m_tokens"],
        labels={"value_score_per_output_dollar": "Quality per $ output", "entity": "Model"},
    )
    fig_top.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_top, use_container_width=True, key=f"{key_prefix}_model_value_top_bar")
    st.caption("CostGoat 口径：quality score 来自其公开页标注的独立 Theozard benchmark；value score = quality / output USD per 1M tokens。Artificial Analysis API 仍需 key，未用 CostGoat 冒充。")


def _render_arr_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("AI 应用商业化 / ARR 公开信号")
    arr = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"] == "arr")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    adoption = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"] == "business_adoption_share")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if arr.empty and adoption.empty:
        st.warning("No public commercialization facts.")
        return
    if not arr.empty:
        arr["value"] = pd.to_numeric(arr["value"], errors="coerce")
        arr = arr.sort_values("value", ascending=False)
        fig = px.bar(
            arr.head(12),
            x="entity",
            y="value",
            color="entity",
            hover_data=["notes", "source_url", "confidence"],
            labels={"entity": "Company", "value": "public ARR signal, USD billions"},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_arr_bar")
        st.caption("ARR.club 免费公开页不是完整私企收入数据库；完整历史、source links 与 Sacra 深度财务需要授权。")
        with st.expander("ARR 公开事实明细", expanded=False):
            st.dataframe(
                arr[["entity", "value", "unit", "notes", "source_url", "confidence"]],
                width="stretch",
                hide_index=True,
            )
    else:
        st.warning("No public ARR facts.")

    if not adoption.empty:
        adoption["value"] = pd.to_numeric(adoption["value"], errors="coerce")
        adoption = adoption.sort_values("value", ascending=True)
        adoption_fig = px.bar(
            adoption,
            x="value",
            y="entity",
            orientation="h",
            color="entity",
            hover_data=["notes", "source_url", "confidence"],
            labels={"entity": "Signal", "value": "business adoption share, %"},
        )
        adoption_fig.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
        st.plotly_chart(adoption_fig, use_container_width=True, key=f"{key_prefix}_adoption_bar")
        st.caption("Ramp AI Index 口径是企业卡和 invoice 支付采用率，不等于收入、ARR 或用户份额；它用于观察企业实际付费采用方向。")
        with st.expander("企业付费采用率事实明细", expanded=False):
            st.dataframe(
                adoption[["entity", "value", "unit", "notes", "source_url", "confidence"]],
                width="stretch",
                hide_index=True,
            )


def _render_multimodal_market(market_facts: pd.DataFrame, *, key_prefix: str = "main") -> None:
    st.subheader("多模态生成成本 / Seedance")
    multimodal = market_facts[
        (market_facts["track"] == "multimodal_generation_cost")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if multimodal.empty:
        st.warning("No multimodal generation cost facts.")
        return
    multimodal["value"] = pd.to_numeric(multimodal["value"], errors="coerce")

    official = multimodal[multimodal["metric"] == "video_generation_price_per_1m_tokens"].copy()
    if not official.empty:
        official["label"] = official["sub_entity"].astype(str) + " / " + official["dimension"].astype(str)
        fig = px.bar(
            official.sort_values(["sub_entity", "dimension"]),
            x="label",
            y="value",
            color="dimension",
            hover_data=["source_url", "notes", "confidence"],
            labels={"label": "Resolution / input mode", "value": "USD / 1M tokens"},
        )
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_seedance_official_token_bar")
        st.caption("BytePlus ModelArk 官方口径是 USD / 1M tokens；最终单次视频成本还取决于实际 completion tokens，不能直接当作每条视频美元价格。")

    credits = multimodal[multimodal["metric"] == "video_generation_5s_example_credits"].copy()
    if not credits.empty:
        credits["label"] = credits["entity"].astype(str) + " / " + credits["sub_entity"].astype(str)
        fig = px.bar(
            credits.sort_values(["entity", "sub_entity", "dimension"]),
            x="label",
            y="value",
            color="dimension",
            barmode="group",
            hover_data=["source_url", "notes", "confidence"],
            labels={"label": "Model / resolution", "value": "credits / 5s example"},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_seedance_credit_bar")
        st.caption("seedance2.ai 是第三方包装 credits 表；它适合跟踪应用端可见扣费，不与官方 USD/token 价格相加。")

    with st.expander("多模态生成成本事实明细", expanded=False):
        st.dataframe(
            multimodal[
                [
                    "date",
                    "entity",
                    "sub_entity",
                    "metric",
                    "value",
                    "unit",
                    "dimension",
                    "vendor",
                    "source_url",
                    "confidence",
                ]
            ].sort_values(["metric", "entity", "sub_entity", "dimension"]),
            width="stretch",
            hide_index=True,
        )


def _render_market_gaps(quality_events: pd.DataFrame) -> None:
    st.subheader("需要授权或尚未接入的数据")
    if quality_events.empty:
        st.success("No market-facts quality events.")
        return
    gaps = quality_events[quality_events["table_name"] == "production_market_facts"].copy()
    if gaps.empty:
        st.success("No market-facts quality events.")
        return
    st.dataframe(
        gaps[["error_code", "affected_key", "message", "source_url", "observed_at"]],
        width="stretch",
        hide_index=True,
    )


def _render_missing_summary(data: Dict[str, Any]) -> None:
    reasons = pd.DataFrame([reason.__dict__ for reason in data["quality_gate"].reasons])
    st.subheader("影响判断的缺口")
    if reasons.empty:
        st.success("当前质量门没有记录阻塞项。")
        return

    preferred = ["OFFICIAL_EVENT_MISSING", "SOURCE_UNAVAILABLE", "DATA_SOURCE_UNAVAILABLE", "GPU_OFFICIAL_TREND_INSUFFICIENT"]
    shown = reasons[reasons["reason_code"].isin(preferred)].copy()
    if shown.empty:
        shown = reasons.copy()
    shown = shown.head(6)
    for _, row in shown.iterrows():
        affected = str(row.get("affected_key") or "").strip()
        prefix = f"{row['reason_code']}"
        if affected:
            prefix += f" · {affected}"
        st.markdown(f"- **{prefix}**：{row['message']}")


def _render_provider_snapshot_cards(gpu_prices: pd.DataFrame) -> None:
    st.subheader("官方价格页当前快照")
    if gpu_prices.empty:
        st.warning("No provider pricing-page snapshot rows.")
        return
    rows = gpu_prices[
        (gpu_prices["source_type"] == "public_pricing_page")
        & (gpu_prices["gpu_model"].isin(["H100", "H200"]))
        & (gpu_prices["price_per_gpu_hour"].notna())
    ].copy()
    if rows.empty:
        st.warning("No H100/H200 provider pricing-page snapshot rows.")
        return

    grouped = (
        rows.groupby(["provider", "gpu_model", "date"], dropna=False)
        .agg(
            min_price=("price_per_gpu_hour", "min"),
            max_price=("price_per_gpu_hour", "max"),
            row_count=("price_per_gpu_hour", "count"),
            source_url=("source_url", "first"),
            snapshot_path=("snapshot_path", "first"),
        )
        .reset_index()
        .sort_values(["gpu_model", "provider", "min_price"])
    )

    cols = st.columns(min(4, max(1, len(grouped))))
    for idx, (_, row) in enumerate(grouped.head(4).iterrows()):
        min_price = float(row["min_price"])
        max_price = float(row["max_price"])
        value = f"${min_price:.2f}/hr" if min_price == max_price else f"${min_price:.2f}-${max_price:.2f}/hr"
        with cols[idx % len(cols)]:
            _render_compact_card(
                f"{row['provider']} {row['gpu_model']}",
                value,
                f"{row['date']} · {int(row['row_count'])} rows",
            )

    with st.expander("价格页快照明细", expanded=False):
        st.dataframe(
            rows[
                [
                    "date",
                    "provider",
                    "gpu_model",
                    "gpu_variant",
                    "billing_type",
                    "price_per_gpu_hour",
                    "source_url",
                    "snapshot_path",
                ]
            ].sort_values(["gpu_model", "provider", "price_per_gpu_hour"]),
            width="stretch",
            hide_index=True,
        )


def _render_decision_requirements(data: Dict[str, Any]) -> None:
    proxy_summary = _proxy_history_summary(data.get("public_proxy_history", _empty_df(PUBLIC_PROXY_HISTORY_COLUMNS)))
    snapshot_summary = _pricing_snapshot_summary(data["tables"].get("gpu_prices", _empty_df([])))
    official_rows = int(data["quality_gate"].table_counts.get("production_official_events", 0))
    regime = _market_regime_summary(data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS)))
    st.subheader("现在这套数据能告诉你什么")
    cols = st.columns(3)
    with cols[0]:
        _render_compact_card(
            "能判断",
            regime["label"],
            regime["evidence"],
        )
    with cols[1]:
        _render_compact_card(
            "不能判断",
            "Cracking",
            f"官方价格页仅 {snapshot_summary['days']} 天，多家公司 guidance/RPO 未闭环",
        )
    with cols[2]:
        _render_compact_card(
            "升级条件",
            "2+ signals",
            f"连续快照 + 官方事件，目前 official rows={official_rows}",
        )


def _render_source_health(data: Dict[str, Any]) -> None:
    proxy_summary = _proxy_history_summary(data.get("public_proxy_history", _empty_df(PUBLIC_PROXY_HISTORY_COLUMNS)))
    snapshot_summary = _pricing_snapshot_summary(data["tables"].get("gpu_prices", _empty_df([])))
    capex_rows = int(data["quality_gate"].table_counts.get("production_capex_actuals", 0))
    official_rows = int(data["quality_gate"].table_counts.get("production_official_events", 0))
    proxy_rows = int(data["quality_gate"].table_counts.get("production_public_proxy_prices", 0))
    cols = st.columns(4)
    with cols[0]:
        _render_compact_card("Proxy 历史", f"{proxy_summary['proxy_days']} days", f"{proxy_summary['adequate_days']} usable")
    with cols[1]:
        _render_compact_card("价格页快照", f"{snapshot_summary['days']} days", f"{snapshot_summary['providers']} providers")
    with cols[2]:
        _render_compact_card("SEC CAPEX", f"{capex_rows} rows", "MSFT/AMZN/GOOGL/META/ORCL")
    with cols[3]:
        _render_compact_card("官方事件", f"{official_rows} rows", f"proxy raw rows={proxy_rows}")


def _render_first_view(data: Dict[str, Any]) -> None:
    quality_gate = data["quality_gate"]
    decision = data["decision"]
    pipeline_runs = data["tables"]["pipeline_runs"]
    last_run = "" if pipeline_runs.empty else str(pipeline_runs["completed_at"].max())
    total_production_rows = sum(int(v) for v in quality_gate.table_counts.values())
    proxy_summary = _proxy_history_summary(data.get("public_proxy_history", _empty_df(PUBLIC_PROXY_HISTORY_COLUMNS)))
    snapshot_summary = _pricing_snapshot_summary(data["tables"].get("gpu_prices", _empty_df([])))
    regime = _market_regime_summary(data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS)))
    official_summary = _official_signal_summary(data["tables"].get("official_events", _empty_df([])))

    st.title("AI 算力与商业化 Tracker")
    with st.expander("数据路径", expanded=False):
        st.caption(f"Production database: `{data['db_path']}`")

    _render_metric_grid(
        [
            ("市场状态", regime["label"], regime["headline"]),
            ("当前判断", "Blocked" if decision is None else decision.state, "不要输出 cracking call"),
            ("官方 CAPEX/RPO", official_summary["coverage"], "not capex cut"),
            ("数据质量门", quality_gate.status, "source-backed production only"),
            ("判断置信度", "n/a" if decision is None else f"{decision.confidence}%", "不足以交易"),
        ]
    )

    with st.expander("刷新状态", expanded=False):
        if last_run:
            st.caption(f"Last production run: {last_run}")
        else:
            st.caption("Last production run: none")
        st.caption(
            f"Proxy usable history: {proxy_summary['adequate_days']}d / {proxy_summary['proxy_days']}d observed. "
            f"Production rows: {total_production_rows:,}."
        )

    st.markdown(f'<div class="decision-note">{_decision_headline(data)}</div>', unsafe_allow_html=True)
    with st.expander("展开判断依据", expanded=False):
        st.write(_decision_explanation(data))
    _render_core_evidence(data)

    with st.expander("完整二级市场读数", expanded=False):
        _render_four_track_summary(data)
        _render_market_decision_cards(data)

    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    if not market_facts.empty:
        with st.expander("详细市场图表", expanded=False):
            _render_gpusio_market_trends(market_facts, key_prefix="home")
            _render_gpu_available_offers(market_facts, key_prefix="home")
            _render_gpu_trend_market(market_facts, key_prefix="home")
            _render_gpu_rental_market(market_facts, key_prefix="home")
            _render_cloud_instance_market(market_facts, key_prefix="home")
            _render_token_market(market_facts, key_prefix="home")
            _render_model_value_market(market_facts, key_prefix="home")
            _render_arr_market(market_facts, key_prefix="home")
            _render_multimodal_market(market_facts, key_prefix="home")

    _render_decision_requirements(data)

    with st.expander("Proxy 历史和价格页快照审计", expanded=False):
        _render_public_proxy_history(data["public_proxy_history"], key_prefix="home_proxy")
        _render_provider_snapshot_cards(data["tables"]["gpu_prices"])

    with st.expander("影响判断的缺口", expanded=False):
        _render_missing_summary(data)

    with st.expander("来源健康", expanded=False):
        _render_source_health(data)

    with st.expander("完整数据覆盖与失败源明细", expanded=False):
        st.markdown("#### 数据覆盖")
        st.dataframe(data["source_coverage"], width="stretch", hide_index=True)
        reasons = pd.DataFrame([reason.__dict__ for reason in quality_gate.reasons])
        st.markdown("#### 失败源明细")
        if reasons.empty:
            st.success("当前质量门没有记录阻塞项。")
        else:
            detail_cols = ["severity", "table_name", "reason_code", "affected_key", "message", "source_url", "snapshot_path"]
            st.dataframe(reasons[[c for c in detail_cols if c in reasons.columns]], width="stretch", hide_index=True)


def _render_gpu_tab(gpu_prices: pd.DataFrame, public_proxy_history: pd.DataFrame) -> None:
    if gpu_prices.empty:
        st.warning("No production GPU price rows.")
        return

    h100_h200 = gpu_prices[gpu_prices["gpu_model"].isin(["H100", "H200"])].copy()
    pricing_page = h100_h200[h100_h200["source_type"] == "public_pricing_page"].copy()
    aggregator = h100_h200[h100_h200["source_type"] == "aggregator"].copy()
    dedupe_cols = [
        "date",
        "source_type",
        "provider",
        "gpu_model",
        "gpu_variant",
        "billing_type",
        "price_per_gpu_hour",
        "source_url",
    ]
    pricing_page_unique = pricing_page.drop_duplicates([c for c in dedupe_cols if c in pricing_page.columns])
    aggregator_unique = aggregator.drop_duplicates([c for c in dedupe_cols if c in aggregator.columns])
    duplicates_removed = (len(pricing_page) - len(pricing_page_unique)) + (len(aggregator) - len(aggregator_unique))

    _render_public_proxy_history(public_proxy_history, key_prefix="gpu_tab")
    _render_provider_snapshot_cards(gpu_prices)

    st.subheader("原始 GPU 报价证据")
    st.caption("下方图表折叠重复报价行；原始 raw rows 只作为来源审计，不进入首屏趋势判断。")
    if duplicates_removed:
        st.warning(f"展示层已折叠 {duplicates_removed} 条重复报价样本，避免重复 provider 行放大分布。")

    if not pricing_page_unique.empty:
        fig = px.bar(
            pricing_page_unique,
            x="provider",
            y="price_per_gpu_hour",
            color="gpu_model",
            facet_col="billing_type",
            hover_data=["gpu_variant", "source_url", "snapshot_path"],
            title="Public provider pricing-page rows: RunPod / Lambda",
            labels={"price_per_gpu_hour": "USD per GPU hour", "provider": "Provider"},
        )
        st.plotly_chart(fig, use_container_width=True, key="gpu_tab_pricing_page_bar")
    else:
        st.warning("No public provider pricing-page rows.")

    if not aggregator_unique.empty:
        fig = px.box(
            aggregator_unique,
            x="gpu_model",
            y="price_per_gpu_hour",
            color="gpu_model",
            points="all",
            hover_data=["provider", "date", "source_url", "snapshot_path"],
            title="Aggregator rows: ComputePrices public quote distribution",
            labels={"price_per_gpu_hour": "USD per GPU hour", "gpu_model": "GPU"},
        )
        st.plotly_chart(fig, use_container_width=True, key="gpu_tab_aggregator_box")
    else:
        st.warning("No aggregator rows.")

    with st.expander("原始报价明细（审计用，未折叠）", expanded=False):
        st.dataframe(
            h100_h200[
                [
                    "date",
                    "provider",
                    "gpu_model",
                    "gpu_variant",
                    "billing_type",
                    "price_per_gpu_hour",
                    "source_type",
                    "source_url",
                    "snapshot_path",
                ]
            ],
            width="stretch",
            hide_index=True,
        )


def _render_capex_tab(capex_actuals: pd.DataFrame) -> None:
    if capex_actuals.empty:
        st.warning("No official SEC CAPEX actual rows.")
        return
    fig = px.bar(
        capex_actuals,
        x="ticker",
        y="capex_value",
        color="ticker",
        hover_data=["fiscal_period", "period_end", "xbrl_tag", "accession_no", "source_url", "snapshot_path"],
        title="Official SEC CAPEX actuals",
        labels={"capex_value": "CAPEX, USD_B", "ticker": "Company"},
    )
    st.plotly_chart(fig, key="capex_actuals_bar")
    st.dataframe(
        capex_actuals[
            [
                "ticker",
                "company",
                "fiscal_period",
                "period_end",
                "capex_value",
                "unit",
                "xbrl_tag",
                "accession_no",
                "source_url",
                "snapshot_path",
            ]
        ],
        width="stretch",
        hide_index=True,
    )


def _render_events_tab(official_events: pd.DataFrame, quality_events: pd.DataFrame) -> None:
    if official_events.empty:
        st.warning("No source-backed official guidance/RPO events.")
    else:
        st.dataframe(
            official_events[
                [
                    "ticker",
                    "announcement_date",
                    "event_type",
                    "metric",
                    "value",
                    "unit",
                    "fiscal_period",
                    "source_url",
                    "snapshot_path",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    failed = quality_events[quality_events["error_code"].notna()].copy() if not quality_events.empty else quality_events
    st.subheader("Failed official/licensed sources")
    if failed.empty:
        st.success("No failed source events recorded.")
    else:
        st.dataframe(
            failed[
                [
                    "table_name",
                    "severity",
                    "error_code",
                    "affected_key",
                    "message",
                    "source_url",
                    "snapshot_path",
                ]
            ],
            width="stretch",
            hide_index=True,
        )


def _render_proxy_tab(public_proxy_prices: pd.DataFrame, public_proxy_history: pd.DataFrame) -> None:
    st.info("ORNN/OCPI licensed feed is not configured. The rows below are public GPU price proxy rows, not OCPI.")
    _render_public_proxy_history(public_proxy_history, key_prefix="proxy_tab")
    if public_proxy_prices.empty:
        st.warning("No public proxy rows.")
        return

    metrics = public_proxy_prices[public_proxy_prices["metric"].str.contains("median|min|count", na=False)].copy()
    if not metrics.empty:
        fig = px.bar(
            metrics,
            x="gpu_model",
            y="value",
            color="metric",
            barmode="group",
            hover_data=["date", "source_url", "snapshot_path"],
            title="ComputePrices-derived public GPU proxy metrics",
        )
        st.plotly_chart(fig, key="proxy_metrics_bar")
    st.dataframe(public_proxy_prices, width="stretch", hide_index=True)


def _render_market_tab(market_facts: pd.DataFrame, quality_events: pd.DataFrame) -> None:
    if market_facts.empty:
        st.warning("No four-track market facts.")
        return
    _render_four_track_summary({"tables": {"market_facts": market_facts}})

    with st.expander("展开市场图表", expanded=False):
        _render_gpusio_market_trends(market_facts, key_prefix="tab")
        _render_gpu_available_offers(market_facts, key_prefix="tab")
        _render_gpu_trend_market(market_facts, key_prefix="tab")
        _render_gpu_rental_market(market_facts, key_prefix="tab")
        _render_cloud_instance_market(market_facts, key_prefix="tab")
        _render_token_market(market_facts, key_prefix="tab")
        _render_model_value_market(market_facts, key_prefix="tab")
        _render_arr_market(market_facts, key_prefix="tab")
        _render_multimodal_market(market_facts, key_prefix="tab")

    with st.expander("展开授权缺口", expanded=False):
        _render_market_gaps(quality_events)

    with st.expander("production_market_facts 明细", expanded=False):
        st.dataframe(
            market_facts[
                [
                    "date",
                    "track",
                    "entity",
                    "sub_entity",
                    "metric",
                    "value",
                    "unit",
                    "dimension",
                    "vendor",
                    "source_name",
                    "source_url",
                    "confidence",
                ]
            ],
            width="stretch",
            hide_index=True,
        )


def _chart_title(title: str, subtitle: str = "") -> str:
    return f"<b>{escape(title)}</b>"


def _quiet_figure(
    fig: go.Figure,
    *,
    height: int = 360,
    title: str | None = None,
    subtitle: str = "",
    legend_title: str = "",
) -> go.Figure:
    top_margin = 58 if title else 42
    fig.update_layout(
        template="simple_white",
        height=height,
        margin=dict(l=68, r=18, t=top_margin, b=58),
        font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", size=12, color="#1d1d1f"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=["#002FA7", "#5B8DEF", "#111827", "#737373", "#A3A3A3", "#0F766E", "#D97706", "#7C3AED"],
        legend=dict(
            title=dict(text=legend_title, font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="right",
            x=1,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
        title=dict(
            text=_chart_title(title, subtitle) if title else None,
            x=0,
            xanchor="left",
            y=0.98,
            yanchor="top",
            font=dict(size=14, color="#0a0a0a"),
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="#eeeeef",
        zerolinecolor="#d4d4d2",
        linecolor="#737373",
        title_font=dict(size=12, color="#515154"),
        tickfont=dict(size=11, color="#515154"),
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#eeeeef",
        zerolinecolor="#d4d4d2",
        linecolor="#737373",
        title_font=dict(size=12, color="#515154"),
        tickfont=dict(size=11, color="#515154"),
        automargin=True,
    )
    return fig


def _date_xaxis(fig: go.Figure, *, tickformat: str = "%b %-d") -> go.Figure:
    fig.update_xaxes(tickformat=tickformat, hoverformat="%Y-%m-%d")
    return fig


def _add_endpoint_labels(
    fig: go.Figure,
    frame: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    series_col: str,
    label_limit: int = 18,
) -> go.Figure:
    if frame.empty:
        return fig
    endpoints = frame.dropna(subset=[x_col, y_col, series_col]).sort_values([series_col, x_col]).groupby(series_col, dropna=False).tail(1)
    endpoints = endpoints.sort_values(y_col, ascending=True).reset_index(drop=True)
    for idx, row in endpoints.iterrows():
        fig.add_annotation(
            x=row[x_col],
            y=row[y_col],
            text=_short_chart_label(row[series_col], label_limit),
            showarrow=False,
            xshift=8,
            yshift=((idx % 3) - 1) * 9,
            xanchor="left",
            yanchor="middle",
            font=dict(size=10, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
            bordercolor="rgba(212,212,210,0.72)",
            borderwidth=1,
            borderpad=2,
        )
    dates = pd.to_datetime(frame[x_col], errors="coerce").dropna()
    if not dates.empty and dates.nunique() > 1:
        span = dates.max() - dates.min()
        fig.update_xaxes(range=[dates.min(), dates.max() + span * 0.16])
    fig.update_layout(showlegend=False)
    return fig


def _short_chart_label(value: Any, limit: int = 30) -> str:
    text = str(value or "").strip()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    text = text.replace("Dreamina Seedance 2.0", "Seedance 2.0")
    text = text.replace("NVIDIA ", "")
    return _short_text(text, limit)


def _market_fact_numeric_rows(market_facts: pd.DataFrame, track: str, metrics: list[str] | None = None) -> pd.DataFrame:
    if market_facts.empty:
        return _empty_df(MARKET_FACT_COLUMNS)
    rows = market_facts[market_facts["track"] == track].copy()
    if metrics is not None:
        rows = rows[rows["metric"].isin(metrics)].copy()
    if rows.empty:
        return rows
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    if "fetched_at" in rows.columns:
        rows["fetched_at"] = pd.to_datetime(rows["fetched_at"], errors="coerce")
    return rows.dropna(subset=["value", "date"])


def _market_facts_with_dashboard_date(market_facts: pd.DataFrame) -> pd.DataFrame:
    if market_facts.empty:
        return _empty_df(MARKET_FACT_COLUMNS + ["dashboard_date"])
    rows = market_facts.copy()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["fetched_at"] = pd.to_datetime(rows.get("fetched_at"), errors="coerce")
    rows["dashboard_date"] = rows["date"]
    snapshot_tracks = {
        "cloud_instance_price",
        "model_value_score",
        "multimodal_generation_cost",
        "openrouter_usage",
        "openrouter_app_usage",
    }
    snapshot_mask = rows["track"].isin(snapshot_tracks) & rows["fetched_at"].notna()
    rows.loc[snapshot_mask, "dashboard_date"] = rows.loc[snapshot_mask, "fetched_at"].dt.normalize()
    return rows


def _dashboard_date_bounds(market_facts: pd.DataFrame) -> tuple[Any, Any]:
    rows = _market_facts_with_dashboard_date(market_facts)
    if rows.empty or "dashboard_date" not in rows.columns:
        return None, None
    dates = pd.to_datetime(rows["dashboard_date"], errors="coerce").dropna()
    if dates.empty:
        return None, None
    return dates.min().date(), dates.max().date()


def _filter_market_facts_by_dashboard_date(market_facts: pd.DataFrame, date_window: tuple[Any, Any] | None) -> pd.DataFrame:
    rows = _market_facts_with_dashboard_date(market_facts)
    if rows.empty or not date_window:
        return rows
    start, end = date_window
    if start is None or end is None:
        return rows
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    filtered = rows[(rows["dashboard_date"] >= start_ts) & (rows["dashboard_date"] <= end_ts)].copy()
    return filtered.drop(columns=["dashboard_date"], errors="ignore")


def _render_trend_date_filter(market_facts: pd.DataFrame) -> tuple[tuple[Any, Any] | None, str]:
    min_date, max_date = _dashboard_date_bounds(market_facts)
    if min_date is None or max_date is None:
        return None, "all_dates"
    selected = st.date_input(
        "日期范围",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="trend_board_date_range",
    )
    if isinstance(selected, tuple) and len(selected) == 2:
        start, end = selected
    else:
        start, end = min_date, max_date
    if start is None or end is None:
        start, end = min_date, max_date
    if start > end:
        start, end = end, start
    suffix = f"{start.isoformat()}_{end.isoformat()}"
    return (start, end), suffix


def _market_fact_state_suffix(market_facts: pd.DataFrame, date_suffix: str) -> str:
    if market_facts.empty:
        return f"{date_suffix}_empty"
    fetched = pd.to_datetime(market_facts.get("fetched_at"), errors="coerce")
    latest = fetched.dropna().max()
    latest_text = latest.strftime("%Y%m%d%H%M%S") if pd.notna(latest) else "no_fetch"
    return f"{date_suffix}_{len(market_facts)}_{latest_text}"


def _trend_label_from_row(row: pd.Series, parts: list[str]) -> str:
    labels = []
    for part in parts:
        value = str(row.get(part) or "").strip()
        if value and value.lower() != "nan":
            labels.append(value)
    return " · ".join(labels) if labels else "unknown"


def _trend_date_range(market_facts: pd.DataFrame, tracks: list[str]) -> str:
    if market_facts.empty:
        return "no production facts"
    rows = market_facts[market_facts["track"].isin(tracks)].copy()
    if rows.empty:
        return "no production facts"
    dates = pd.to_datetime(rows["date"], errors="coerce").dropna()
    if dates.empty:
        return "date unknown"
    first = dates.min().date().isoformat()
    last = dates.max().date().isoformat()
    return last if first == last else f"{first} - {last}"


def _source_caption_from_rows(rows: pd.DataFrame, fallback: str) -> str:
    if rows.empty:
        return fallback
    source_col = "source_name" if "source_name" in rows.columns else "source_type"
    sources = [str(item) for item in rows[source_col].dropna().unique() if str(item).strip()]
    dates = pd.to_datetime(rows["date"], errors="coerce").dropna() if "date" in rows.columns else pd.Series(dtype="datetime64[ns]")
    if dates.empty:
        date_text = "date unknown"
    else:
        first = dates.min().date().isoformat()
        last = dates.max().date().isoformat()
        date_text = last if first == last else f"{first} - {last}"
    source_text = " / ".join(sources[:2]) if sources else fallback
    return f"{source_text} · {date_text}"


def _gpu_rental_trend_frame(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = _market_fact_numeric_rows(market_facts, "gpu_rental", ["price_per_gpu_hour"])
    if rows.empty:
        return pd.DataFrame(columns=["date", "gpu", "price"])
    rows = rows[rows["value"] > 0].copy()
    focus = ["A100 80GB", "A100", "H100", "H200", "B200", "B300", "L40S", "RTX 4090", "RTX 5090"]
    rows["gpu"] = rows["entity"].astype(str).str.replace("NVIDIA ", "", regex=False)
    rows = rows[rows["gpu"].isin(focus)].copy()
    if rows.empty:
        return pd.DataFrame(columns=["date", "gpu", "price"])
    return (
        rows.groupby(["date", "gpu"], dropna=False)["value"]
        .median()
        .reset_index(name="price")
        .sort_values(["gpu", "date"])
    )


def _gpu_rental_trend_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    frame = _gpu_rental_trend_frame(market_facts)
    if frame.empty or frame["date"].nunique() < 2:
        return None, "gpu_rental · insufficient multi-day production facts"
    fig = px.line(
        frame,
        x="date",
        y="price",
        color="gpu",
        markers=True,
        labels={"date": "日期", "price": "USD / GPU hour", "gpu": "GPU"},
    )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title_text="日期")
    fig.update_yaxes(title_text="租赁价格，USD / GPU hour")
    _add_endpoint_labels(fig, frame, x_col="date", y_col="price", series_col="gpu", label_limit=12)
    _date_xaxis(fig)
    return _quiet_figure(
        fig,
        height=390,
        title="GPU 租赁现货价格趋势",
        subtitle="同一 GPU 按日取公开租赁价格中位数，观察供需价格方向。",
        legend_title="",
    ), f"gpu_rental · {_trend_date_range(market_facts, ['gpu_rental'])}"


def _gpu_window_delta_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    rows = _market_fact_numeric_rows(market_facts, "gpu_market_trend", ["price_delta_30d_pct", "price_delta_90d_pct"])
    if rows.empty:
        return None, "gpu_market_trend · no production facts"
    focus = ["NVIDIA A100 80GB", "NVIDIA H100", "NVIDIA H200", "NVIDIA B200", "NVIDIA RTX 5090", "NVIDIA L40S"]
    shown = rows[rows["entity"].isin(focus)].copy()
    if shown.empty:
        shown = rows.copy()
    shown["gpu"] = shown["entity"].astype(str).str.replace("NVIDIA ", "", regex=False)
    shown["window"] = shown["metric"].map({"price_delta_30d_pct": "30d", "price_delta_90d_pct": "90d"}).fillna(shown["metric"])
    fig = px.bar(
        shown.sort_values(["gpu", "window"]),
        x="gpu",
        y="value",
        color="window",
        barmode="group",
        labels={"gpu": "GPU", "value": "价格变化，%", "window": "窗口"},
    )
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#a1a1aa")
    fig.update_xaxes(title_text="GPU")
    fig.update_yaxes(title_text="30/90 日价格变化，%")
    return _quiet_figure(
        fig,
        height=390,
        title="GPU 价格动量：30 日 vs 90 日",
        subtitle="正值代表报价上涨，负值代表报价下行；零线用于识别方向切换。",
        legend_title="窗口",
    ), f"GPUs.io movers · {_trend_date_range(market_facts, ['gpu_market_trend'])}"


def _gpu_rental_index_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    rows = _market_fact_numeric_rows(
        market_facts,
        "gpu_rental_index",
        [
            "median_price_per_gpu_hour",
            "range_low_price_per_gpu_hour",
            "range_high_price_per_gpu_hour",
            "aggregate_low_price_per_gpu_hour",
            "aggregate_high_price_per_gpu_hour",
        ],
    )
    if rows.empty:
        return None, "gpu_rental_index · no production index facts"
    focus = ["H100", "H200", "B200", "B300", "A100", "A100 80GB", "L40S", "RTX 4090", "RTX 5090", "MI300X"]
    rows["gpu"] = rows["entity"].astype(str).str.replace("NVIDIA ", "", regex=False)
    rows = rows[rows["gpu"].isin(focus)].copy()
    if rows.empty:
        return None, "gpu_rental_index · no focused GPU index facts"
    rows["bucket"] = rows["metric"].map(
        {
            "median_price_per_gpu_hour": "median",
            "range_low_price_per_gpu_hour": "low",
            "range_high_price_per_gpu_hour": "high",
            "aggregate_low_price_per_gpu_hour": "low",
            "aggregate_high_price_per_gpu_hour": "high",
        }
    )
    rows = rows.dropna(subset=["bucket"])
    if rows.empty:
        return None, "gpu_rental_index · incomplete index facts"
    envelope = pd.concat(
        [
            rows[rows["bucket"] == "low"].groupby("gpu")["value"].min().rename("low"),
            rows[rows["bucket"] == "median"].groupby("gpu")["value"].median().rename("median"),
            rows[rows["bucket"] == "high"].groupby("gpu")["value"].max().rename("high"),
        ],
        axis=1,
    ).reset_index()
    envelope = envelope.dropna(subset=["low", "high"], how="all")
    if envelope.empty:
        return None, "gpu_rental_index · incomplete index facts"
    focus_order = {gpu: idx for idx, gpu in enumerate(focus)}
    envelope["rank"] = envelope["gpu"].map(focus_order).fillna(999)
    envelope = envelope.sort_values(["rank", "gpu"]).head(9)

    fig = go.Figure()
    for _, row in envelope.iterrows():
        gpu = str(row["gpu"])
        low = row.get("low")
        high = row.get("high")
        median = row.get("median")
        if pd.notna(low) and pd.notna(high):
            fig.add_trace(
                go.Scatter(
                    x=[float(low), float(high)],
                    y=[gpu, gpu],
                    mode="lines",
                    line=dict(color="#002FA7", width=5),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        for value, name, symbol, color in [
            (low, "low", "line-ns-open", "#737373"),
            (median, "median", "diamond", "#002FA7"),
            (high, "high", "line-ns-open", "#737373"),
        ]:
            if pd.notna(value):
                fig.add_trace(
                    go.Scatter(
                        x=[float(value)],
                        y=[gpu],
                        mode="markers",
                        marker=dict(symbol=symbol, size=10 if name == "median" else 8, color=color, line=dict(width=1, color="#ffffff")),
                        name=name,
                        legendgroup=name,
                        showlegend=not any(trace.name == name for trace in fig.data),
                        hovertemplate=f"{gpu}<br>{name}: $%{{x:.2f}}/GPU hr<extra></extra>",
                    )
                )
    fig.update_layout(
        xaxis_title="价格区间，USD / GPU hour",
        yaxis_title="GPU",
        showlegend=False,
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=1,
        y=1.08,
        xanchor="right",
        yanchor="bottom",
        text="横线 = 低-高区间 · 蓝钻 = 中位数",
        showarrow=False,
        font=dict(size=11, color="#515154"),
        bgcolor="#fafaf8",
        bordercolor="#d4d4d2",
        borderwidth=1,
        borderpad=4,
    )
    return _quiet_figure(
        fig,
        height=390,
        title="聚合租赁价格区间",
        subtitle="横线为低高区间，蓝色菱形为中位数；用于判断价格分散度。",
        legend_title="",
    ), f"AIMultiple / GetDeploying index envelope · {_trend_date_range(market_facts, ['gpu_rental_index'])}"


def _orderbook_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    rows = _market_fact_numeric_rows(
        market_facts,
        "gpu_available_offer",
        ["available_price_per_gpu_hour", "available_offer_count"],
    )
    if rows.empty:
        return None, "gpu_available_offer · no production facts"
    pivot = (
        rows.pivot_table(index=["date", "entity"], columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    required = {"available_price_per_gpu_hour", "available_offer_count"}
    if pivot.empty or not required.issubset(pivot.columns):
        return None, "gpu_available_offer · incomplete orderbook facts"
    pivot = pivot.dropna(subset=["available_price_per_gpu_hour", "available_offer_count"])
    if pivot.empty:
        return None, "gpu_available_offer · incomplete orderbook facts"
    pivot["gpu"] = pivot["entity"].astype(str)
    pivot = pivot.sort_values("available_offer_count", ascending=False).head(10)
    fig = px.scatter(
        pivot,
        x="available_price_per_gpu_hour",
        y="gpu",
        size="available_offer_count",
        color="gpu",
        hover_data=["available_offer_count"],
        labels={"available_price_per_gpu_hour": "最低可用价，USD / GPU hour", "gpu": "GPU", "available_offer_count": "可用 offer 数"},
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="最低可用价，USD / GPU hour")
    fig.update_yaxes(title_text="GPU")
    fig.update_traces(marker=dict(opacity=0.78, line=dict(width=1, color="#ffffff")))
    return _quiet_figure(
        fig,
        height=390,
        title="可用订单簿：价格 vs 可售深度",
        subtitle="横轴是最低可用价，气泡大小是可用 offer 数；用于看低价是否有真实深度。",
        legend_title="",
    ), f"GPUPerHour available=true · {_trend_date_range(market_facts, ['gpu_available_offer'])}"


def _cloud_instance_trend_frame(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = _market_fact_numeric_rows(market_facts, "cloud_instance_price", ["instance_price_per_hour"])
    if rows.empty:
        return pd.DataFrame(columns=["date", "series", "price"])
    rows = rows[rows["value"] > 0].copy()
    rows["chart_date"] = pd.to_datetime(rows.get("fetched_at"), errors="coerce").dt.normalize()
    rows["chart_date"] = rows["chart_date"].fillna(rows["date"])
    preferred_entities = ["H100", "H200", "A100", "MI300X"]
    preferred_dimensions = ["spot", "low_priority", "on_demand"]
    rows = rows[rows["entity"].isin(preferred_entities) & rows["dimension"].isin(preferred_dimensions)].copy()
    if rows.empty:
        return pd.DataFrame(columns=["date", "series", "price"])
    rows["series"] = rows.apply(lambda r: _trend_label_from_row(r, ["vendor", "entity", "dimension"]), axis=1)
    rows["series"] = (
        rows["series"]
        .str.replace(" · ", " ", regex=False)
        .str.replace("low_priority", "LP", regex=False)
        .str.replace("on_demand", "OD", regex=False)
    )
    grouped = (
        rows.groupby(["chart_date", "series"], dropna=False)["value"]
        .min()
        .reset_index(name="price")
        .rename(columns={"chart_date": "date"})
        .sort_values(["series", "date"])
    )
    series_rank = (
        grouped.groupby("series")
        .agg(days=("date", "nunique"), latest=("date", "max"), median_price=("price", "median"))
        .sort_values(["days", "latest", "median_price"], ascending=[False, False, True])
        .head(8)
        .index
    )
    return grouped[grouped["series"].isin(series_rank)].copy()


def _cloud_instance_trend_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    frame = _cloud_instance_trend_frame(market_facts)
    if frame.empty or frame["date"].nunique() < 2:
        return None, "cloud_instance_price · insufficient multi-day production facts"
    fig = px.line(
        frame,
        x="date",
        y="price",
        color="series",
        markers=True,
        labels={"date": "日期", "price": "USD / VM hour", "series": "云厂商 · GPU · 计费口径"},
    )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title_text="抓取日期")
    fig.update_yaxes(title_text="实例价格，USD / VM hour")
    _date_xaxis(fig)
    finished = _quiet_figure(
        fig,
        height=480,
        title="官方云 GPU 实例价格快照趋势",
        subtitle="按抓取日重采样公开 VM 小时价，频率与租赁价格趋势对齐。",
        legend_title="实例系列",
    )
    finished.update_layout(
        margin=dict(l=68, r=18, t=58, b=112),
        legend=dict(
            title=dict(text="实例系列", font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="top",
            y=-0.20,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
    )
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna()
    if dates.empty:
        date_text = "date unknown"
    else:
        first = dates.min().date().isoformat()
        last = dates.max().date().isoformat()
        date_text = last if first == last else f"{first} - {last}"
    return finished, f"official VM-hour daily snapshots · {date_text}"


def _openrouter_usage_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    usage = _market_fact_numeric_rows(
        market_facts,
        "openrouter_usage",
        ["model_total_tokens", "tool_call_count", "image_processing_count"],
    )
    app_usage = _market_fact_numeric_rows(
        market_facts,
        "openrouter_app_usage",
        ["app_total_requests", "app_total_tokens"],
    )
    if usage.empty and app_usage.empty:
        return None, "openrouter_usage · no production facts"

    token_daily = pd.DataFrame(columns=["date", "value"])
    call_proxy = pd.DataFrame(columns=["date", "metric_label", "value"])
    app_requests = pd.DataFrame(columns=["date", "value"])
    if not usage.empty:
        token_daily = (
            usage[usage["metric"] == "model_total_tokens"]
            .groupby("date", dropna=False)["value"]
            .sum()
            .reset_index()
            .sort_values("date")
        )
        proxy_rows = usage[usage["metric"].isin(["tool_call_count", "image_processing_count"])].copy()
        if not proxy_rows.empty:
            proxy_rows["metric_label"] = proxy_rows["metric"].map(
                {
                    "tool_call_count": "Tool calls",
                    "image_processing_count": "Image processing",
                }
            )
            call_proxy = (
                proxy_rows.groupby(["date", "metric_label"], dropna=False)["value"]
                .sum()
                .reset_index()
                .sort_values(["metric_label", "date"])
            )
    if not app_usage.empty:
        app_requests = (
            app_usage[app_usage["metric"] == "app_total_requests"]
            .groupby("date", dropna=False)["value"]
            .sum()
            .reset_index()
            .sort_values("date")
        )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.22,
        subplot_titles=("Daily model tokens, top 50 + other", "Public activity / request proxies"),
    )
    if not token_daily.empty:
        fig.add_trace(
            go.Scatter(
                x=token_daily["date"],
                y=token_daily["value"],
                mode="lines+markers",
                name="Model tokens",
                line=dict(color="#002FA7", width=2),
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.0f} tokens<extra></extra>",
            ),
            row=1,
            col=1,
        )
    else:
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.78,
            text="OpenRouter daily token dataset requires OPENROUTER_API_KEY",
            showarrow=False,
            font=dict(size=12, color="#737373"),
            bgcolor="#fafaf8",
            bordercolor="#d4d4d2",
            borderwidth=1,
            borderpad=5,
        )
    for metric_label, group in call_proxy.groupby("metric_label", dropna=False):
        fig.add_trace(
            go.Scatter(
                x=group["date"],
                y=group["value"],
                mode="lines+markers",
                name=str(metric_label),
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.0f}<extra></extra>",
            ),
            row=2,
            col=1,
        )
    if not app_requests.empty:
        fig.add_trace(
            go.Scatter(
                x=app_requests["date"],
                y=app_requests["value"],
                mode="lines+markers",
                name="App requests",
                line=dict(color="#0F766E", width=2),
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.0f} requests<extra></extra>",
            ),
            row=2,
            col=1,
        )
    fig.update_xaxes(title_text="日期", row=1, col=1)
    fig.update_xaxes(title_text="日期", row=2, col=1)
    fig.update_yaxes(title_text="tokens", row=1, col=1)
    fig.update_yaxes(title_text="counts / requests", row=2, col=1)
    fig.update_layout(hovermode="x unified")
    fig.update_annotations(font=dict(size=12, color="#515154"))
    _date_xaxis(fig)
    finished = _quiet_figure(
        fig,
        height=520,
        title="OpenRouter 公开用量趋势",
        subtitle="Token 总量、应用请求与公开 activity proxy 分层展示。",
        legend_title="指标",
    )
    finished.update_layout(
        margin=dict(l=68, r=18, t=58, b=112),
        legend=dict(
            title=dict(text="指标", font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
    )
    source_tracks = ["openrouter_usage"]
    if not app_usage.empty:
        source_tracks.append("openrouter_app_usage")
    return finished, f"OpenRouter rankings APIs · {_trend_date_range(market_facts, source_tracks)}"


def _token_output_trend_frame(market_facts: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    rows = _market_fact_numeric_rows(market_facts, "token_price", ["output_price_per_1m_tokens"])
    if rows.empty:
        return pd.DataFrame(columns=["date", "model", "price"])
    rows = rows[rows["value"] > 0].copy()
    daily = (
        rows.groupby(["date", "entity", "vendor"], dropna=False)["value"]
        .median()
        .reset_index(name="price")
        .sort_values(["entity", "date"])
    )
    eligible = (
        daily.groupby(["entity", "vendor"], dropna=False)
        .agg(days=("date", "nunique"), first=("price", "first"), latest=("price", "last"))
        .reset_index()
    )
    eligible = eligible[eligible["days"] >= 2].copy()
    if eligible.empty:
        return pd.DataFrame(columns=["date", "model", "price"])
    watchlist = [
        "GPT-5",
        "Claude 3.5 Sonnet",
        "Claude 3.5 Haiku",
        "Gemini 3 Flash",
        "Gemini 2.5 Flash",
        "DeepSeek V4 Pro",
        "Kimi K2",
        "GPT-OSS-120B",
    ]
    rank = {name: idx for idx, name in enumerate(watchlist)}
    eligible["rank"] = eligible["entity"].map(rank).fillna(999).astype(int)
    eligible["move"] = (eligible["latest"] - eligible["first"]).abs()
    chosen = eligible.sort_values(["rank", "days", "move"], ascending=[True, False, False]).head(limit)
    out = daily.merge(chosen[["entity", "vendor"]], on=["entity", "vendor"], how="inner")
    out["model"] = out["entity"].astype(str)
    return out[["date", "model", "price"]].sort_values(["model", "date"])


def _token_output_trend_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    frame = _token_output_trend_frame(market_facts)
    if frame.empty or frame["date"].nunique() < 2:
        return None, "token_price · insufficient multi-day production facts"
    fig = px.line(
        frame,
        x="date",
        y="price",
        color="model",
        markers=True,
        labels={"date": "日期", "price": "输出价，USD / 1M tokens", "model": "模型"},
    )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title_text="发布日期 / 生效日期")
    fig.update_yaxes(title_text="输出价，USD / 1M tokens")
    _date_xaxis(fig)
    finished = _quiet_figure(
        fig,
        height=480,
        title="API 输出 Token 价格趋势",
        subtitle="公开模型目录中的输出 token 单价；观察模型能力价格是否继续下行。",
        legend_title="模型",
    )
    finished.update_layout(
        margin=dict(l=68, r=18, t=58, b=112),
        legend=dict(
            title=dict(text="模型", font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="top",
            y=-0.20,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
    )
    return finished, f"public token catalogs · {_trend_date_range(market_facts, ['token_price'])}"


def _model_output_price_trend_frame(market_facts: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    rows = _market_fact_numeric_rows(
        market_facts,
        "model_value_score",
        ["quality_score", "output_price_per_1m_tokens"],
    )
    if rows.empty:
        return pd.DataFrame(columns=["date", "model", "price", "quality_score"])
    pivot = (
        rows.pivot_table(index=["date", "entity", "vendor"], columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    if pivot.empty or "quality_score" not in pivot.columns or "output_price_per_1m_tokens" not in pivot.columns:
        return pd.DataFrame(columns=["date", "model", "price", "quality_score"])
    pivot["quality_score"] = pd.to_numeric(pivot["quality_score"], errors="coerce")
    pivot["output_price_per_1m_tokens"] = pd.to_numeric(pivot["output_price_per_1m_tokens"], errors="coerce")
    pivot = pivot[(pivot["quality_score"] >= 80) & (pivot["output_price_per_1m_tokens"] > 0)].copy()
    if pivot.empty:
        return pd.DataFrame(columns=["date", "model", "price", "quality_score"])
    latest_date = pivot["date"].max()
    latest = pivot[pivot["date"] == latest_date].copy()
    latest["rank_price"] = latest["output_price_per_1m_tokens"].rank(method="first", ascending=True)
    chosen = latest.sort_values(["rank_price", "quality_score"], ascending=[True, False]).head(limit)[["entity", "vendor"]]
    out = pivot.merge(chosen, on=["entity", "vendor"], how="inner")
    out["model"] = out["entity"].map(lambda value: _short_chart_label(value, 28))
    return (
        out.rename(columns={"output_price_per_1m_tokens": "price"})[["date", "model", "price", "quality_score"]]
        .sort_values(["model", "date"])
    )


def _model_output_price_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    frame = _model_output_price_trend_frame(market_facts)
    if frame.empty or frame["date"].nunique() < 2:
        return None, "model_value_score · insufficient high-quality price snapshots"
    fig = px.line(
        frame,
        x="date",
        y="price",
        color="model",
        markers=True,
        hover_data={"quality_score": ":.1f"},
        labels={"date": "日期", "price": "输出价，USD / 1M tokens", "model": "模型", "quality_score": "质量分"},
    )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title_text="快照日期")
    fig.update_yaxes(title_text="高质量模型输出价，USD / 1M tokens")
    _date_xaxis(fig)
    finished = _quiet_figure(
        fig,
        height=430,
        title="高质量模型输出价格趋势",
        subtitle="质量分 ≥80 的模型按快照日走线，用于观察高质量输出成本是否压缩。",
        legend_title="模型",
    )
    finished.update_layout(
        margin=dict(l=68, r=18, t=58, b=112),
        legend=dict(
            title=dict(text="模型", font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="top",
            y=-0.20,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
    )
    return finished, f"CostGoat public proxy snapshots · {_trend_date_range(market_facts, ['model_value_score'])}"


def _commercialization_signal_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    rows = _market_fact_numeric_rows(market_facts, "app_commercialization", ["arr", "business_adoption_share"])
    if rows.empty:
        return None, "app_commercialization · no production facts"
    arr = rows[rows["metric"] == "arr"].copy()
    adoption = rows[rows["metric"] == "business_adoption_share"].copy()
    if not arr.empty:
        latest_arr = arr.sort_values("date").groupby("entity", dropna=False).tail(1).sort_values("value", ascending=False).head(6)
        arr = arr[arr["entity"].isin(latest_arr["entity"])].copy()
    if not adoption.empty:
        latest_adoption = adoption.sort_values("date").groupby("entity", dropna=False).tail(1).sort_values("value", ascending=False).head(5)
        adoption = adoption[adoption["entity"].isin(latest_adoption["entity"])].copy()
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.20,
        subplot_titles=("ARR public signal, USD B", "Business adoption snapshots, %"),
    )
    if not arr.empty:
        for entity, group in arr.sort_values(["entity", "date"]).groupby("entity", dropna=False):
            fig.add_trace(
                go.Scatter(
                    x=group["date"],
                    y=group["value"],
                    mode="lines+markers",
                    name=_short_chart_label(entity, 24),
                    hovertemplate="%{x|%Y-%m-%d}<br>ARR: $%{y:.1f}B<extra></extra>",
                    legendgroup=str(entity),
                    showlegend=True,
                ),
                row=1,
                col=1,
            )
    if not adoption.empty:
        for entity, group in adoption.sort_values(["entity", "date"]).groupby("entity", dropna=False):
            fig.add_trace(
                go.Scatter(
                    x=group["date"],
                    y=group["value"],
                    mode="lines+markers",
                    name=_short_chart_label(entity, 24),
                    hovertemplate="%{x|%Y-%m-%d}<br>adoption: %{y:.1f}%<extra></extra>",
                    legendgroup=f"adoption-{entity}",
                    showlegend=False,
                    line=dict(color="#737373", dash="dot"),
                    marker=dict(color="#737373"),
                ),
                row=2,
                col=1,
            )
    fig.update_xaxes(title_text="日期", row=1, col=1)
    fig.update_xaxes(title_text="日期", row=2, col=1)
    fig.update_yaxes(title_text="ARR，USD B", row=1, col=1)
    fig.update_yaxes(title_text="企业采用率，%", row=2, col=1)
    fig.update_layout(hovermode="x unified")
    fig.update_annotations(font=dict(size=12, color="#515154"))
    _date_xaxis(fig)
    finished = _quiet_figure(
        fig,
        height=500,
        title="应用商业化信号趋势",
        subtitle="ARR 与企业采用率分轴展示，只看时间变化，不混单位。",
        legend_title="ARR",
    )
    finished.update_layout(
        margin=dict(l=68, r=18, t=58, b=104),
        legend=dict(
            title=dict(text="ARR", font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
    )
    return finished, f"ARR.club / Ramp snapshots · {_trend_date_range(market_facts, ['app_commercialization'])}"


def _multimodal_cost_figure(market_facts: pd.DataFrame) -> tuple[go.Figure | None, str]:
    rows = _market_fact_numeric_rows(
        market_facts,
        "multimodal_generation_cost",
        ["video_generation_price_per_1m_tokens", "video_generation_5s_example_credits"],
    )
    if rows.empty:
        return None, "multimodal_generation_cost · no production facts"
    rows["label"] = rows.apply(lambda r: _short_chart_label(_trend_label_from_row(r, ["entity", "sub_entity", "dimension"]), 34), axis=1)
    usd = rows[rows["metric"] == "video_generation_price_per_1m_tokens"].copy()
    credits = rows[rows["metric"] == "video_generation_5s_example_credits"].copy()
    if not usd.empty:
        latest_usd = usd.sort_values("date").groupby("label", dropna=False).tail(1).sort_values("value").head(6)
        usd = usd[usd["label"].isin(latest_usd["label"])].copy()
    if not credits.empty:
        latest_credits = credits.sort_values("date").groupby("label", dropna=False).tail(1).sort_values("value").head(6)
        credits = credits[credits["label"].isin(latest_credits["label"])].copy()
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.20,
        subplot_titles=("Official token pricing, USD / 1M tokens", "Wrapper credit schedule, credits / 5s"),
    )
    for label, group in usd.sort_values(["label", "date"]).groupby("label", dropna=False):
        fig.add_trace(
            go.Scatter(
                x=group["date"],
                y=group["value"],
                mode="lines+markers",
                name=label,
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f} USD / 1M tokens<extra></extra>",
                legendgroup=label,
                showlegend=True,
            ),
            row=1,
            col=1,
        )
    for label, group in credits.sort_values(["label", "date"]).groupby("label", dropna=False):
        fig.add_trace(
            go.Scatter(
                x=group["date"],
                y=group["value"],
                mode="lines+markers",
                name=label,
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.0f} credits / 5s<extra></extra>",
                legendgroup=f"credits-{label}",
                showlegend=False,
                line=dict(color="#737373", dash="dot"),
                marker=dict(color="#737373"),
            ),
            row=2,
            col=1,
        )
    fig.update_xaxes(title_text="日期", row=1, col=1)
    fig.update_xaxes(title_text="日期", row=2, col=1)
    fig.update_yaxes(title_text="USD / 1M tokens", row=1, col=1)
    fig.update_yaxes(title_text="credits / 5s", row=2, col=1)
    fig.update_layout(hovermode="x unified")
    fig.update_annotations(font=dict(size=12, color="#515154"))
    _date_xaxis(fig)
    finished = _quiet_figure(
        fig,
        height=500,
        title="多模态生成成本趋势",
        subtitle="官方 token 价格与第三方 credit 口径分轴展示。",
        legend_title="USD token 价",
    )
    finished.update_layout(
        margin=dict(l=68, r=18, t=58, b=108),
        legend=dict(
            title=dict(text="USD token 价", font=dict(size=12, color="#515154")),
            orientation="h",
            yanchor="top",
            y=-0.17,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#0a0a0a"),
            bgcolor="rgba(250,250,248,0.88)",
        ),
    )
    return finished, f"BytePlus / seedance2.ai snapshots · {_trend_date_range(market_facts, ['multimodal_generation_cost'])}"


def _latest_china_capex_rows(market_facts: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    vendor_order = [
        ("Alibaba Cloud", "BABA / 9988.HK"),
        ("Tencent Cloud", "0700.HK / TCEHY"),
        ("Baidu AI Cloud", "BIDU / 9888.HK"),
        ("Huawei Cloud", "private"),
        ("ByteDance Volcano Engine", "private"),
    ]
    facts = _market_fact_numeric_rows(market_facts, "china_cloud_capex") if not market_facts.empty else _empty_df(MARKET_FACT_COLUMNS)
    rows = []
    for company, ticker in vendor_order:
        company_rows = facts[facts["entity"] == company].copy() if not facts.empty else facts
        capex_rows = company_rows[company_rows["metric"].str.contains("capex", case=False, na=False)].copy() if not company_rows.empty else company_rows
        if not capex_rows.empty:
            latest = capex_rows.sort_values("date").iloc[-1]
            value = pd.to_numeric(latest.get("value"), errors="coerce")
            latest_capex = f"RMB {value:.1f}B" if pd.notna(value) else "数值异常"
            period = latest["date"].date().isoformat() if pd.notna(latest["date"]) else ""
            note = _short_text(str(latest.get("notes") or ""), 120)
        elif not company_rows.empty:
            context = company_rows.sort_values("date").iloc[-1]
            latest_capex = "未单列云 CAPEX"
            period = context["date"].date().isoformat() if pd.notna(context["date"]) else ""
            note = _short_text(str(context.get("notes") or ""), 120)
        else:
            latest_capex = "未披露官方 CAPEX"
            period = ""
            note = "私有/未单列披露，媒体估算不并入官方 CAPEX 确认层。"
        rows.append(
            {
                "区域": "中国",
                "公司": company,
                "Ticker": ticker,
                "最新 CAPEX": latest_capex,
                "期间": period,
                "官方说明": note,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _latest_capex_actual_table(capex_actuals: pd.DataFrame, official_events: pd.DataFrame, market_facts: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = ["区域", "公司", "Ticker", "最新 CAPEX", "期间", "官方说明"]
    us_order = ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]
    if capex_actuals.empty:
        us_rows = pd.DataFrame(columns=columns)
    else:
        rows = capex_actuals.copy()
        rows["period_end"] = pd.to_datetime(rows["period_end"], errors="coerce")
        rows = rows.sort_values(["ticker", "period_end"], ascending=[True, False]).drop_duplicates("ticker")
        events = official_events.copy()
        event_text = {}
        if not events.empty:
            events = events.sort_values("announcement_date", ascending=False)
            for ticker, group in events.groupby("ticker", dropna=False):
                descriptions = [str(item) for item in group["description"].dropna().head(2)]
                event_text[str(ticker)] = " / ".join(descriptions)
        out = []
        for ticker in us_order:
            match = rows[rows["ticker"] == ticker]
            if match.empty:
                out.append({"区域": "美国", "公司": "", "Ticker": ticker, "最新 CAPEX": "暂无生产事实", "期间": "", "官方说明": ""})
                continue
            row = match.iloc[0]
            out.append(
                {
                    "区域": "美国",
                    "公司": str(row.get("company") or ticker),
                    "Ticker": ticker,
                    "最新 CAPEX": _money(row.get("capex_value"), "B"),
                    "期间": str(row.get("fiscal_period") or row.get("period_end") or ""),
                    "官方说明": _short_text(event_text.get(ticker, ""), 120),
                }
            )
        us_rows = pd.DataFrame(out, columns=columns)
    china = _latest_china_capex_rows(market_facts if market_facts is not None else _empty_df(MARKET_FACT_COLUMNS), columns)
    return pd.concat([us_rows, china], ignore_index=True)


def _render_trend_card(title: str, subtitle: str, fig: go.Figure | None, caption: str, key: str, state_suffix: str = "") -> None:
    with st.container(border=True):
        st.markdown(f'<div class="trend-card-title">{escape(title)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="trend-card-subtitle">{escape(subtitle)}</div>', unsafe_allow_html=True)
        if fig is None:
            st.markdown(f'<div class="missing-tile">{escape(caption)}</div>', unsafe_allow_html=True)
        else:
            chart_key = f"{key}_{state_suffix}" if state_suffix else key
            st.plotly_chart(fig, use_container_width=True, key=chart_key)
            st.markdown(f'<div class="trend-caption">{escape(caption)}</div>', unsafe_allow_html=True)


def _render_trend_section(kicker: str, title: str, note: str) -> None:
    st.markdown(
        f"""
<div class="trend-section">
  <div>
    <div class="trend-section-kicker">{escape(kicker)}</div>
    <div class="trend-section-title">{escape(title)}</div>
  </div>
  <div class="trend-section-note">{escape(note)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_single_page_trend_board(data: Dict[str, Any]) -> None:
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    capex_actuals = data["tables"].get("capex_actuals", _empty_df([]))
    official_events = data["tables"].get("official_events", _empty_df([]))
    quality_gate = data["quality_gate"]
    production_rows = int(market_facts.shape[0])
    date_range = _trend_date_range(
        market_facts,
        [
            "gpu_rental",
            "gpu_rental_index",
            "gpu_market_trend",
            "gpu_available_offer",
            "cloud_instance_price",
            "openrouter_usage",
            "openrouter_app_usage",
            "token_price",
            "app_commercialization",
            "multimodal_generation_cost",
            "china_cloud_capex",
        ],
    )

    st.markdown(
        f"""
<div class="trend-hero">
  <div class="trend-title">AI Compute Price & Cost Trends</div>
  <div class="trend-meta">{escape(date_range)} · {production_rows:,} production market facts · quality {escape(str(quality_gate.status))}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    date_window, date_suffix = _render_trend_date_filter(market_facts)
    filtered_market_facts = _filter_market_facts_by_dashboard_date(market_facts, date_window)
    state_suffix = _market_fact_state_suffix(filtered_market_facts, date_suffix)

    _render_trend_section(
        "L1 · SUPPLY PRICE",
        "GPU 现货与租赁价格",
        "先看算力本身是否仍稀缺：租赁价格、云实例锚点、动量和价格带。",
    )
    fig, caption = _gpu_rental_trend_figure(filtered_market_facts)
    _render_trend_card("Exhibit 1 · 租赁价格趋势", "按 GPU 代际跟踪公开租赁价曲线。", fig, caption, "trend_gpu_rental", state_suffix)
    fig, caption = _cloud_instance_trend_figure(filtered_market_facts)
    _render_trend_card("Exhibit 2 · 云实例价格快照", "按抓取日展示官方 VM 小时价，频率与租赁价格对齐。", fig, caption, "trend_cloud_instance", state_suffix)
    left, right = st.columns(2)
    with left:
        fig, caption = _gpu_window_delta_figure(filtered_market_facts)
        _render_trend_card("Exhibit 3 · 价格动量", "比较短期和中期报价方向。", fig, caption, "trend_gpu_window_delta", state_suffix)
    with right:
        fig, caption = _gpu_rental_index_figure(filtered_market_facts)
        _render_trend_card("Exhibit 4 · 聚合价格区间", "低位、中位、高位形成价格带。", fig, caption, "trend_gpu_rental_index", state_suffix)

    _render_trend_section(
        "L2 · APPLICATION ECONOMICS",
        "API、模型与应用端单位经济",
        "再看需求端能否吸收算力供给：OpenRouter 用量、token 价格、模型成本和商业化信号。",
    )
    fig, caption = _openrouter_usage_figure(filtered_market_facts)
    _render_trend_card("Exhibit 5 · OpenRouter 用量趋势", "Token、请求与公开 activity proxy 分层展示。", fig, caption, "trend_openrouter_usage", state_suffix)
    fig, caption = _token_output_trend_figure(filtered_market_facts)
    _render_trend_card("Exhibit 6 · Token 输出价趋势", "跟踪主流模型输出价格是否继续压缩。", fig, caption, "trend_token_output", state_suffix)
    fig, caption = _model_output_price_figure(filtered_market_facts)
    _render_trend_card("Exhibit 7 · 高质量模型价格趋势", "质量分 ≥80 的模型单位输出成本。", fig, caption, "trend_model_output_price", state_suffix)
    fig, caption = _multimodal_cost_figure(filtered_market_facts)
    _render_trend_card("Exhibit 8 · 多模态生成成本趋势", "不同单位分轴，不混读 token 与 credit。", fig, caption, "trend_multimodal_cost", state_suffix)
    fig, caption = _commercialization_signal_figure(filtered_market_facts)
    _render_trend_card("Exhibit 9 · 商业化信号趋势", "ARR 与采用率分轴展示。", fig, caption, "trend_commercialization", state_suffix)

    _render_trend_section(
        "L3 · CAPEX CONFIRMATION",
        "云厂商 CAPEX 官方说明",
        "CAPEX 不和高频价格图混成指数，只作为底部确认层：看管理层披露是否仍支持算力紧缺叙事。",
    )
    st.markdown(
        '<div class="trend-capex-note">下表只展示官方或明确 source-backed 生产事实；无法披露云 CAPEX 的公司直接暴露口径限制。</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(_latest_capex_actual_table(capex_actuals, official_events, market_facts), width="stretch", hide_index=True)


def _gpu_delta_chart(snapshot: Dict[str, Any], *, key: str) -> None:
    gpu_table = snapshot["gpu_table"].copy()
    numeric = gpu_table.dropna(subset=["delta90_numeric"]).copy()
    if numeric.empty:
        st.info("暂无可展示的 90 日 GPU 价格变化。")
        return
    fig = px.bar(
        numeric,
        x="GPU",
        y="delta90_numeric",
        color="GPU",
        hover_data=["当前可用最低价", "可用offer", "7日租赁"],
        labels={"delta90_numeric": "90日变化，%", "GPU": ""},
        title="90日价格变化",
    )
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#86868b")
    fig.update_layout(showlegend=False)
    st.plotly_chart(_quiet_figure(fig), use_container_width=True, key=key)


def _gpu_orderbook_chart(snapshot: Dict[str, Any], *, key: str) -> None:
    gpu_table = snapshot["gpu_table"].copy()
    numeric = gpu_table.dropna(subset=["min_offer_numeric"]).copy()
    if numeric.empty:
        st.info("暂无可展示的当前可用订单簿。")
        return
    numeric["offer_count_numeric"] = pd.to_numeric(numeric["offer_count_numeric"], errors="coerce").fillna(1)
    fig = px.scatter(
        numeric,
        x="min_offer_numeric",
        y="GPU",
        size="offer_count_numeric",
        hover_data=["当前可用最低价", "可用offer", "90日变化"],
        labels={"min_offer_numeric": "最低可用价，$/GPU hr", "GPU": ""},
        title="当前可用订单簿",
    )
    fig.update_traces(marker=dict(color="#2563eb", opacity=0.72, line=dict(width=1, color="#1d4ed8")))
    fig.update_layout(showlegend=False)
    st.plotly_chart(_quiet_figure(fig), use_container_width=True, key=key)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _render_home_price_visual(snapshot: Dict[str, Any]) -> str:
    rows = []
    table = snapshot["gpu_table"].dropna(subset=["delta90_numeric"]).copy()
    for _, row in table.iterrows():
        value = float(row["delta90_numeric"])
        neg_width = _clamp(abs(value) / 45 * 50, 0, 50) if value < 0 else 0
        pos_width = _clamp(value / 15 * 50, 0, 50) if value > 0 else 0
        rows.append(
            f"""
<div class="bar-row">
  <div class="bar-label">{escape(str(row['GPU']))}</div>
  <div class="bar-track">
    <div class="bar-zero"></div>
    <div class="bar-neg" style="width:{neg_width:.1f}%;"></div>
    <div class="bar-pos" style="width:{pos_width:.1f}%;"></div>
  </div>
  <div class="bar-value">{_point_percent(value)}</div>
</div>
"""
        )
    return "".join(rows) or '<div class="visual-footnote">暂无 90 日价格变化。</div>'


def _render_home_orderbook_visual(snapshot: Dict[str, Any]) -> str:
    rows = []
    table = snapshot["gpu_table"].dropna(subset=["min_offer_numeric"]).copy()
    if not table.empty:
        max_price = max(5.0, float(pd.to_numeric(table["min_offer_numeric"], errors="coerce").max()))
    else:
        max_price = 5.0
    for _, row in table.iterrows():
        price = float(row["min_offer_numeric"])
        offers = row.get("offer_count_numeric")
        offers = 1 if offers is None or pd.isna(offers) else float(offers)
        left = _clamp(price / max_price * 100, 0, 100)
        dot_size = _clamp(8 + offers / 48 * 18, 9, 26)
        rows.append(
            f"""
<div class="dot-row">
  <div class="dot-label">{escape(str(row['GPU']))}</div>
  <div class="dot-track">
    <div class="dot" style="left:{left:.1f}%; --dot-size:{dot_size:.1f}px;"></div>
  </div>
  <div class="dot-value">{_money(price, '')}</div>
</div>
"""
        )
    body = "".join(rows) or '<div class="visual-footnote">暂无当前可用订单簿。</div>'
    summary = snapshot.get("summary", {})
    azure_h100 = summary.get("azure_h100_spot_min")
    aws_h100 = summary.get("aws_h100_spot_min")
    chips = []
    if azure_h100 is not None and not pd.isna(azure_h100):
        chips.append(
            f"""
<div class="cloud-chip">
  <div class="cloud-chip-label">Azure H100 spot</div>
  <div class="cloud-chip-value">{_money(azure_h100, '/VM hr')}</div>
</div>
"""
        )
    if aws_h100 is not None and not pd.isna(aws_h100):
        chips.append(
            f"""
<div class="cloud-chip">
  <div class="cloud-chip-label">AWS H100 spot</div>
  <div class="cloud-chip-value">{_money(aws_h100, '/VM hr')}</div>
</div>
"""
        )
    if chips:
        body += f'<div class="commercial-note">{"".join(chips)}</div>'
    return body


def _render_home_model_value_visual(market_facts: pd.DataFrame) -> str:
    table = _model_value_table(market_facts)
    if table.empty:
        return '<div class="visual-footnote">暂无模型价效比样本。</div>'
    shown = table.head(6).copy()
    shown["score_numeric"] = pd.to_numeric(shown["价效比"], errors="coerce")
    max_score = max(1.0, float(shown["score_numeric"].max()))
    rows = []
    for _, row in shown.iterrows():
        score = float(row["score_numeric"])
        width = _clamp(score / max_score * 100, 4, 100)
        model_name = str(row["模型"])
        rows.append(
            f"""
<div class="value-row">
  <div class="value-label" title="{escape(model_name)}">{escape(model_name)}</div>
  <div class="value-track"><div class="value-bar" style="width:{width:.1f}%;"></div></div>
  <div class="value-score">{_plain_number(score)}</div>
</div>
"""
        )
    return "".join(rows)


def _render_home_commercialization_visual(market_facts: pd.DataFrame) -> str:
    rows = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"] == "business_adoption_share")
    ].copy()
    chips = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"] == "arr")
    ].copy()
    if rows.empty and chips.empty:
        return '<div class="visual-footnote">暂无应用商业化样本。</div>'

    html_rows = []
    if not rows.empty:
        rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
        rows = rows.dropna(subset=["value"]).sort_values("value", ascending=False).head(4)
        max_value = max(50.0, float(rows["value"].max())) if not rows.empty else 50.0
        for _, row in rows.iterrows():
            value = float(row["value"])
            width = _clamp(value / max_value * 100, 4, 100)
            entity = str(row["entity"])
            html_rows.append(
                f"""
<div class="commercial-row">
  <div class="commercial-label" title="{escape(entity)}">{escape(entity)}</div>
  <div class="commercial-track"><div class="commercial-bar" style="width:{width:.1f}%;"></div></div>
  <div class="commercial-score">{_point_percent(value)}</div>
</div>
"""
            )

    chip_rows = []
    if not chips.empty:
        chips["value"] = pd.to_numeric(chips["value"], errors="coerce")
        chips = chips.dropna(subset=["value"]).sort_values("value", ascending=False).head(2)
        for _, row in chips.iterrows():
            entity = str(row["entity"])
            chip_rows.append(
                f"""
<div class="commercial-chip">
  <div class="commercial-chip-label">ARR public</div>
  <div class="commercial-chip-value" title="{escape(entity)}">{escape(entity)} {_money(float(row['value']), 'B')}</div>
</div>
"""
            )

    chip_html = f'<div class="commercial-note">{"".join(chip_rows)}</div>' if chip_rows else ""
    return "".join(html_rows) + chip_html


def _market_source_caption(
    market_facts: pd.DataFrame,
    tracks: list[str],
    *,
    note: str = "",
    max_sources: int = 2,
) -> str:
    if market_facts.empty:
        return "来源：暂无生产事实"
    rows = market_facts[market_facts["track"].isin(tracks)].copy()
    if rows.empty:
        return "来源：暂无生产事实"
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    dates = rows["date"].dropna()
    date_text = "日期未知"
    if not dates.empty:
        min_date = dates.min().date().isoformat()
        max_date = dates.max().date().isoformat()
        date_text = f"截至 {max_date}" if min_date == max_date else f"{min_date} 至 {max_date}"
    source_col = "source_name" if "source_name" in rows.columns else "source_type"
    sources = [str(x) for x in rows[source_col].dropna().unique() if str(x)]
    sources = sources[:max_sources]
    source_text = " / ".join(sources) if sources else "source-backed production facts"
    note_text = f" · {note}" if note else ""
    return f"来源：{source_text} · {date_text}{note_text}"


def _caption_div(text: str) -> str:
    return f'\n<div class="source-caption">{escape(text)}</div>'


def _official_source_caption(official_events: pd.DataFrame) -> str:
    if official_events.empty:
        return "来源：暂无官方事件"
    rows = official_events.copy()
    rows["announcement_date"] = pd.to_datetime(rows["announcement_date"], errors="coerce")
    dates = rows["announcement_date"].dropna()
    date_text = "日期未知"
    if not dates.empty:
        min_date = dates.min().date().isoformat()
        max_date = dates.max().date().isoformat()
        date_text = f"截至 {max_date}" if min_date == max_date else f"{min_date} 至 {max_date}"
    tickers = ", ".join(sorted(rows["ticker"].dropna().astype(str).str.upper().unique())[:5])
    return f"来源：SEC/官方事件 · {date_text} · 覆盖 {tickers}"


def _render_home_visuals(snapshot: Dict[str, Any], market_facts: pd.DataFrame) -> None:
    st.markdown(
        f"""
<div class="visual-grid">
  <div class="visual-card">
    <div class="visual-title">90日价格变化</div>
    {_render_home_price_visual(snapshot)}
    {_caption_div(_market_source_caption(market_facts, ["gpu_market_trend"], note="GPUs.io material movers，90日变化"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">当前可用订单簿</div>
    {_render_home_orderbook_visual(snapshot)}
    {_caption_div(_market_source_caption(market_facts, ["gpu_available_offer", "cloud_instance_price"], note="GPUPerHour 为 per-GPU-hour；AWS/Azure 为 VM-hour"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">高质量模型价效比</div>
    {_render_home_model_value_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["model_value_score"], note="CostGoat public proxy，质量阈值按当前页面逻辑筛选"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">应用商业化信号</div>
    {_render_home_commercialization_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["app_commercialization"], note="Ramp 为支付采用率；ARR.club 为公开 ARR 信号"))}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_room_header(title: str, subtitle: str, meta: str = "") -> None:
    meta_html = f'<div class="room-meta">{escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
<div class="room-header">
  <div>
    <div class="room-title">{escape(title)}</div>
    <div class="room-subtitle">{escape(subtitle)}</div>
  </div>
  {meta_html}
</div>
""",
        unsafe_allow_html=True,
    )


def _render_detail_intro(title: str, body: str) -> None:
    st.markdown(
        f"""
<div class="detail-block">
  <div class="detail-title">{escape(title)}</div>
  <div class="detail-body">{escape(body)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_price_generation_visual(snapshot: Dict[str, Any]) -> str:
    table = snapshot["gpu_table"].dropna(subset=["delta90_numeric"]).copy()
    if table.empty:
        return '<div class="visual-footnote">暂无代际压力读数。</div>'
    groups = [
        ("旧卡/上一代", ["A100 80GB", "H100"]),
        ("前沿卡", ["H200", "B200"]),
    ]
    rows = []
    for label, names in groups:
        values = pd.to_numeric(table[table["GPU"].isin(names)]["delta90_numeric"], errors="coerce").dropna()
        if values.empty:
            continue
        value = float(values.mean())
        neg_width = _clamp(abs(value) / 45 * 50, 0, 50) if value < 0 else 0
        pos_width = _clamp(value / 15 * 50, 0, 50) if value > 0 else 0
        rows.append(
            f"""
<div class="bar-row">
  <div class="bar-label">{escape(label)}</div>
  <div class="bar-track">
    <div class="bar-zero"></div>
    <div class="bar-neg" style="width:{neg_width:.1f}%;"></div>
    <div class="bar-pos" style="width:{pos_width:.1f}%;"></div>
  </div>
  <div class="bar-value">{_point_percent(value)}</div>
</div>
"""
        )
    return "".join(rows) + '<div class="visual-footnote">按已接 GPUs.io 90日变化粗分，不把 A100 下跌直接外推到前沿卡。</div>'


def _render_orderbook_depth_visual(snapshot: Dict[str, Any]) -> str:
    table = snapshot["gpu_table"].dropna(subset=["offer_count_numeric"]).copy()
    if table.empty:
        return '<div class="visual-footnote">暂无订单簿深度读数。</div>'
    table["offer_count_numeric"] = pd.to_numeric(table["offer_count_numeric"], errors="coerce")
    table = table.dropna(subset=["offer_count_numeric"])
    max_count = max(1.0, float(table["offer_count_numeric"].max()))
    rows = []
    for _, row in table.iterrows():
        gpu = str(row["GPU"])
        count = float(row["offer_count_numeric"])
        price = row.get("min_offer_numeric")
        width = _clamp(count / max_count * 100, 4, 100)
        rows.append(
            f"""
<div class="value-row">
  <div class="value-label" title="{escape(gpu)}">{escape(gpu)}</div>
  <div class="value-track"><div class="value-bar" style="width:{width:.1f}%;"></div></div>
  <div class="value-score">{_plain_number(count)}</div>
</div>
"""
        )
    return "".join(rows) + '<div class="visual-footnote">条形表示 available=true offer 数，价格明细在展开区。</div>'


def _render_cloud_price_visual(market_facts: pd.DataFrame) -> str:
    cloud = market_facts[
        (market_facts["track"] == "cloud_instance_price")
        & (market_facts["metric"] == "instance_price_per_hour")
        & (market_facts["entity"] == "H100")
    ].copy()
    if cloud.empty:
        return '<div class="visual-footnote">暂无云厂商 H100 实例价格。</div>'
    cloud["value"] = pd.to_numeric(cloud["value"], errors="coerce")
    cloud = cloud.dropna(subset=["value"])
    if cloud.empty:
        return '<div class="visual-footnote">暂无可用云厂商价格数值。</div>'
    grouped = (
        cloud.groupby(["vendor", "dimension"], dropna=False)["value"]
        .min()
        .reset_index()
        .sort_values(["dimension", "value"])
        .head(8)
    )
    max_value = max(1.0, float(grouped["value"].max()))
    rows = []
    for _, row in grouped.iterrows():
        label = f"{row['vendor']} {str(row['dimension']).replace('_', ' ')}"
        width = _clamp(float(row["value"]) / max_value * 100, 4, 100)
        rows.append(
            f"""
<div class="value-row">
  <div class="value-label" title="{escape(label)}">{escape(label)}</div>
  <div class="value-track"><div class="value-bar" style="width:{width:.1f}%;"></div></div>
  <div class="value-score">{_money(row['value'], '')}</div>
</div>
"""
        )
    return "".join(rows) + '<div class="visual-footnote">单位是 VM-hour，不与 GPUPerHour 的 per-GPU-hour 混算。</div>'


def _render_official_cloud_visual(official_events: pd.DataFrame) -> str:
    table = _official_layer_table(official_events)
    if table.empty:
        return '<div class="visual-footnote">暂无官方 CAPEX/RPO 事件。</div>'
    rows = []
    for _, row in table.head(5).iterrows():
        rows.append(
            f"""
<div class="source-card">
  <div class="source-label">{escape(str(row['公司']))}</div>
  <div class="source-value">仍偏扩张</div>
  <div class="source-note">{escape(_short_text(str(row['当前信号']), 96))}</div>
</div>
"""
        )
    return f'<div class="source-grid">{"".join(rows)}</div>'


def _model_value_pivot(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = market_facts[market_facts["track"] == "model_value_score"].copy()
    if rows.empty:
        return pd.DataFrame()
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    return (
        rows.pivot_table(index=["entity", "vendor"], columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )


def _token_change_table(market_facts: pd.DataFrame, limit: int = 6) -> pd.DataFrame:
    columns = ["模型", "厂商", "首日", "最新日", "首日输出价", "最新输出价", "变化", "快照数", "source_name"]
    rows = market_facts[
        (market_facts["track"] == "token_price")
        & (market_facts["metric"] == "output_price_per_1m_tokens")
    ].copy()
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows = rows.dropna(subset=["value", "date"])
    rows = rows[rows["value"] > 0]
    if rows.empty:
        return pd.DataFrame(columns=columns)

    source_col = "source_name" if "source_name" in rows.columns else "source_type"
    rows[source_col] = rows[source_col].fillna("")
    daily = (
        rows.groupby(["entity", "vendor", "date"], dropna=False)
        .agg(value=("value", "median"), source_name=(source_col, "first"))
        .reset_index()
    )
    records = []
    for (entity, vendor), group in daily.groupby(["entity", "vendor"], dropna=False):
        group = group.sort_values("date")
        if group["date"].nunique() < 2:
            continue
        first = group.iloc[0]
        latest = group.iloc[-1]
        first_value = float(first["value"])
        latest_value = float(latest["value"])
        if first_value <= 0:
            continue
        pct_change = (latest_value - first_value) / first_value * 100
        records.append(
            {
                "模型": str(entity),
                "厂商": str(vendor),
                "首日": first["date"].date().isoformat(),
                "最新日": latest["date"].date().isoformat(),
                "首日输出价": first_value,
                "最新输出价": latest_value,
                "变化": pct_change,
                "快照数": int(group["date"].nunique()),
                "source_name": str(latest["source_name"] or first["source_name"]),
            }
        )
    if not records:
        return pd.DataFrame(columns=columns)

    out = pd.DataFrame(records)
    watchlist = [
        "GPT-5",
        "Claude 3.5 Sonnet",
        "Claude 3.5 Haiku",
        "Gemini 3 Flash",
        "Gemini 2.5 Flash",
        "DeepSeek V4 Pro",
        "Kimi K2",
        "GPT-OSS-120B",
    ]
    watch_rank = {name: i for i, name in enumerate(watchlist)}
    out["watch_rank"] = out["模型"].map(watch_rank).fillna(999).astype(int)
    out["abs_change"] = pd.to_numeric(out["变化"], errors="coerce").abs()
    out = out.sort_values(["watch_rank", "快照数", "abs_change"], ascending=[True, False, False])
    return out.drop(columns=["watch_rank", "abs_change"], errors="ignore").head(limit).reset_index(drop=True)


def _has_token_change_history(market_facts: pd.DataFrame) -> bool:
    return not _token_change_table(market_facts, limit=1).empty


def _render_token_change_visual(market_facts: pd.DataFrame) -> str:
    table = _token_change_table(market_facts)
    if table.empty:
        return '<div class="visual-footnote">暂无足够多日 token 输出价快照；不能画趋势。</div>'
    max_abs = max(25.0, float(pd.to_numeric(table["变化"], errors="coerce").abs().max()))
    rows = []
    for _, row in table.iterrows():
        change = float(row["变化"])
        down_width = _clamp(abs(change) / max_abs * 50, 0, 50) if change < 0 else 0
        up_width = _clamp(change / max_abs * 50, 0, 50) if change > 0 else 0
        flat = abs(change) < 0.1
        note = f"{row['首日']} {_money(row['首日输出价'], '/1M')} -> {row['最新日']} {_money(row['最新输出价'], '/1M')} · {row['快照数']} snaps"
        rows.append(
            f"""
<div class="token-row">
  <div class="token-label" title="{escape(str(row['模型']))}">{escape(str(row['模型']))}</div>
  <div class="token-track">
    <div class="token-zero"></div>
    <div class="token-down" style="width:{down_width:.1f}%;"></div>
    <div class="token-up" style="width:{up_width:.1f}%;"></div>
    {'<div class="token-flat"></div>' if flat else ''}
  </div>
  <div class="token-score">{_point_percent(change)}</div>
</div>
<div class="token-note">{escape(note)}</div>
"""
        )
    return "".join(rows) + '<div class="visual-footnote">负值代表 output token 价下降；这是公开源离散快照，不是连续价格曲线。</div>'


def _render_model_price_quality_visual(market_facts: pd.DataFrame) -> str:
    pivot = _model_value_pivot(market_facts)
    required = {"quality_score", "output_price_per_1m_tokens"}
    if pivot.empty or not required.issubset(pivot.columns):
        return '<div class="visual-footnote">暂无质量/输出价样本。</div>'
    shown = pivot[pd.to_numeric(pivot["quality_score"], errors="coerce") >= 80].copy()
    shown = shown[pd.to_numeric(shown["output_price_per_1m_tokens"], errors="coerce") > 0]
    if shown.empty:
        return '<div class="visual-footnote">暂无高质量输出价样本。</div>'
    shown = shown.sort_values("output_price_per_1m_tokens", ascending=True).head(6)
    max_price = max(1.0, float(shown["output_price_per_1m_tokens"].max()))
    rows = []
    for _, row in shown.iterrows():
        model = str(row["entity"])
        price = float(row["output_price_per_1m_tokens"])
        quality = float(row["quality_score"])
        width = _clamp(price / max_price * 100, 4, 100)
        rows.append(
            f"""
<div class="value-row">
  <div class="value-label" title="{escape(model)}">{escape(model)}</div>
  <div class="value-track"><div class="value-bar" style="width:{width:.1f}%;"></div></div>
  <div class="value-score">{_money(price, '/1M')}</div>
</div>
<div class="visual-footnote" style="margin-top:-7px;margin-bottom:7px;">quality {_plain_number(quality)}</div>
"""
        )
    return "".join(rows)


def _render_app_spread_visual(market_facts: pd.DataFrame) -> str:
    rows = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"].isin(["arr", "business_adoption_share"]))
    ].copy()
    if rows.empty:
        return '<div class="visual-footnote">暂无商业化差值样本。</div>'
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")

    def metric_value(entity: str, metric: str) -> float | None:
        values = rows[(rows["entity"] == entity) & (rows["metric"] == metric)]["value"].dropna()
        return None if values.empty else float(values.median())

    anth_adoption = metric_value("Anthropic", "business_adoption_share")
    openai_adoption = metric_value("OpenAI", "business_adoption_share")
    anth_arr = metric_value("Anthropic", "arr")
    openai_arr = metric_value("OpenAI", "arr")
    chips = [
        ("采用率差", _point_percent((anth_adoption or 0) - (openai_adoption or 0)) if anth_adoption is not None and openai_adoption is not None else "n/a", "Anthropic - OpenAI"),
        ("ARR 差", _money((anth_arr or 0) - (openai_arr or 0), "B") if anth_arr is not None and openai_arr is not None else "n/a", "ARR.club public"),
        ("Anthropic", f"{_point_percent(anth_adoption)} / {_money(anth_arr, 'B')}", "adoption / ARR"),
        ("OpenAI", f"{_point_percent(openai_adoption)} / {_money(openai_arr, 'B')}", "adoption / ARR"),
    ]
    html = "".join(
        f"""
<div class="source-card">
  <div class="source-label">{escape(label)}</div>
  <div class="source-value">{escape(value)}</div>
  <div class="source-note">{escape(note)}</div>
</div>
"""
        for label, value, note in chips
    )
    return f'<div class="source-grid">{html}</div>'


def _render_multimodal_cost_visual(market_facts: pd.DataFrame) -> str:
    multimodal = market_facts[
        (market_facts["track"] == "multimodal_generation_cost")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if multimodal.empty:
        return '<div class="visual-footnote">暂无多模态成本样本。</div>'
    multimodal["value"] = pd.to_numeric(multimodal["value"], errors="coerce")
    shown = multimodal[
        multimodal["metric"].isin(["video_generation_price_per_1m_tokens", "video_generation_5s_example_credits"])
    ].copy()
    if shown.empty:
        return '<div class="visual-footnote">暂无可展示的 Seedance 成本样本。</div>'
    shown["label"] = shown["entity"].astype(str) + " " + shown["sub_entity"].astype(str)
    shown = shown.sort_values(["metric", "value"], ascending=[True, True]).head(6)
    max_value = max(1.0, float(shown["value"].max()))
    rows = []
    for _, row in shown.iterrows():
        label = str(row["label"])
        suffix = "/1M" if row["metric"] == "video_generation_price_per_1m_tokens" else " cr"
        value_text = _money(row["value"], suffix) if suffix == "/1M" else _plain_number(row["value"], suffix)
        width = _clamp(float(row["value"]) / max_value * 100, 4, 100)
        rows.append(
            f"""
<div class="commercial-row">
  <div class="commercial-label" title="{escape(label)}">{escape(label)}</div>
  <div class="commercial-track"><div class="commercial-bar" style="width:{width:.1f}%;"></div></div>
  <div class="commercial-score">{value_text}</div>
</div>
"""
        )
    return "".join(rows) + '<div class="visual-footnote">token 美元价与第三方 credits 扣费分开读，不相加。</div>'


def _render_evidence_status_visual(data: Dict[str, Any]) -> None:
    coverage = data.get("source_coverage", _empty_df([]))
    gaps = _quality_gap_table(data, limit=3)
    market_rows = data["tables"].get("market_facts", _empty_df([])).shape[0]
    official_rows = data["tables"].get("official_events", _empty_df([])).shape[0]
    quality = data["quality_gate"].status
    source_layers = 0 if coverage.empty else int(coverage["layer"].nunique())
    gap_note = "无主要缺口" if gaps.empty else " / ".join(
        f"{row['缺口']}:{row['原因']}" for _, row in gaps.head(2).iterrows()
    )
    st.markdown(
        f"""
<div class="source-grid">
  <div class="source-card">
    <div class="source-label">质量门</div>
    <div class="source-value">{escape(str(quality))}</div>
    <div class="source-note">WARN 代表可以观察，但不能升级为强交易信号。</div>
  </div>
  <div class="source-card">
    <div class="source-label">真实事实</div>
    <div class="source-value">{_plain_number(market_rows)} market</div>
    <div class="source-note">{_plain_number(official_rows)} official events；生产表优先。</div>
  </div>
  <div class="source-card">
    <div class="source-label">覆盖层</div>
    <div class="source-value">{_plain_number(source_layers)}</div>
    <div class="source-note">GPU、云、应用、官方事件、失败源均可追溯。</div>
  </div>
  <div class="source-card">
    <div class="source-label">最大阻碍</div>
    <div class="source-value">仍未完全闭环</div>
    <div class="source-note">{escape(_short_text(gap_note, 108))}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _available_offer_summary_table(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = market_facts[market_facts["track"] == "gpu_available_offer"].copy()
    if rows.empty:
        return pd.DataFrame(columns=["GPU", "可用offer", "最低价", "单位"])
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    prices = rows[rows["metric"] == "available_price_per_gpu_hour"].groupby("entity")["value"].min()
    counts = rows[rows["metric"] == "available_offer_count"].groupby("entity")["value"].median()
    out = []
    for gpu in sorted(set(prices.index).union(set(counts.index))):
        out.append(
            {
                "GPU": gpu,
                "可用offer": _plain_number(counts.get(gpu)),
                "最低价": _money(prices.get(gpu), "/GPU hr"),
                "单位": "GPUPerHour available=true",
            }
        )
    return pd.DataFrame(out)


def _gpu_market_trend_summary_table(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = market_facts[market_facts["track"] == "gpu_market_trend"].copy()
    if rows.empty:
        return pd.DataFrame(columns=["GPU", "30日", "90日", "来源"])
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    pivot = (
        rows.pivot_table(index="entity", columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    out = []
    for _, row in pivot.iterrows():
        out.append(
            {
                "GPU": str(row["entity"]).replace("NVIDIA ", ""),
                "30日": _point_percent(row.get("price_delta_30d_pct")),
                "90日": _point_percent(row.get("price_delta_90d_pct")),
                "来源": "GPUs.io movers",
            }
        )
    return pd.DataFrame(out).head(12)


def _cloud_instance_summary_table(market_facts: pd.DataFrame) -> pd.DataFrame:
    cloud = market_facts[
        (market_facts["track"] == "cloud_instance_price")
        & (market_facts["metric"] == "instance_price_per_hour")
    ].copy()
    if cloud.empty:
        return pd.DataFrame(columns=["云厂商", "GPU", "计费", "最低价", "单位"])
    cloud["value"] = pd.to_numeric(cloud["value"], errors="coerce")
    grouped = (
        cloud.dropna(subset=["value"])
        .groupby(["vendor", "entity", "dimension"], dropna=False)["value"]
        .min()
        .reset_index()
        .sort_values(["vendor", "entity", "dimension"])
    )
    return pd.DataFrame(
        {
            "云厂商": grouped["vendor"],
            "GPU": grouped["entity"],
            "计费": grouped["dimension"],
            "最低价": grouped["value"].map(lambda v: _money(v, "/VM hr")),
            "单位": "official VM-hour",
        }
    ).head(16)


def _multimodal_summary_table(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = market_facts[
        (market_facts["track"] == "multimodal_generation_cost")
        & (pd.to_numeric(market_facts["value"], errors="coerce").notna())
    ].copy()
    if rows.empty:
        return pd.DataFrame(columns=["项目", "口径", "数值", "来源"])
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    out = []
    for _, row in rows.sort_values(["metric", "entity", "sub_entity"]).head(14).iterrows():
        metric = str(row["metric"])
        is_token = metric == "video_generation_price_per_1m_tokens"
        out.append(
            {
                "项目": f"{row['entity']} {row['sub_entity']}",
                "口径": str(row["dimension"]),
                "数值": _money(row["value"], "/1M tokens") if is_token else _plain_number(row["value"], " credits"),
                "来源": str(row["source_type"]),
            }
        )
    return pd.DataFrame(out)


def _official_layer_table(official_events: pd.DataFrame) -> pd.DataFrame:
    summary = _official_signal_summary(official_events)
    parts = [part.strip() for part in summary["evidence"].split("；") if part.strip()]
    rows = []
    for part in parts:
        company = part.split(" ", 1)[0] if " " in part else part
        rows.append({"公司": company, "当前信号": part, "读法": "扩张或需求仍强"})
    return pd.DataFrame(rows)


def _model_value_table(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = market_facts[market_facts["track"] == "model_value_score"].copy()
    if rows.empty:
        return pd.DataFrame(columns=["模型", "厂商", "质量", "输出价", "价效比"])
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    pivot = (
        rows.pivot_table(index=["entity", "vendor"], columns="metric", values="value", aggfunc="median")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    required = {"quality_score", "output_price_per_1m_tokens", "value_score_per_output_dollar"}
    if pivot.empty or not required.issubset(pivot.columns):
        return pd.DataFrame(columns=["模型", "厂商", "质量", "输出价", "价效比"])
    shown = pivot[pd.to_numeric(pivot["quality_score"], errors="coerce") >= 80].copy()
    shown = shown.sort_values("value_score_per_output_dollar", ascending=False).head(8)
    return pd.DataFrame(
        {
            "模型": shown["entity"],
            "厂商": shown["vendor"],
            "质量": shown["quality_score"].map(_plain_number),
            "输出价": shown["output_price_per_1m_tokens"].map(lambda v: _money(v, "/1M")),
            "价效比": shown["value_score_per_output_dollar"].map(_plain_number),
        }
    )


def _adoption_table(market_facts: pd.DataFrame) -> pd.DataFrame:
    rows = market_facts[
        (market_facts["track"] == "app_commercialization")
        & (market_facts["metric"].isin(["arr", "business_adoption_share"]))
    ].copy()
    if rows.empty:
        return pd.DataFrame(columns=["信号", "数值", "口径"])
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    out = []
    for _, row in rows.sort_values(["metric", "value"], ascending=[True, False]).head(10).iterrows():
        if row["metric"] == "arr":
            value = _money(row["value"], "B")
            unit = "ARR.club public signal"
        else:
            value = _point_percent(row["value"])
            unit = "Ramp payment adoption"
        out.append({"信号": row["entity"], "数值": value, "口径": unit})
    return pd.DataFrame(out)


def _signal_readiness_table(data: Dict[str, Any]) -> pd.DataFrame:
    snapshot = _core_evidence_snapshot(data)
    summary = snapshot["summary"]
    regime = snapshot["regime"]
    official = snapshot["official_summary"]
    value = snapshot["model_value_summary"]
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    quality_events = data["tables"].get("quality_events", _empty_df([]))

    def has_track(track: str) -> bool:
        return not market_facts.empty and bool((market_facts["track"] == track).any())

    def has_gap(keywords: list[str]) -> bool:
        if quality_events.empty or "affected_key" not in quality_events.columns:
            return False
        keys = quality_events["affected_key"].fillna("").str.lower()
        return any(keys.str.contains(keyword, regex=False).any() for keyword in keywords)

    rows = [
        {
            "信号": "GPU租赁价格",
            "状态": "可观察",
            "已接证据": f"{regime['evidence']}；H100 order book {_money(summary['h100_available_min'], '/GPU hr')} / {_plain_number(summary['h100_available_count'])} offers。",
            "仍缺什么": "硬件二手成交价、长历史、折扣与合同期。",
            "决策读法": "只支持观察代际分化，不能推出全市场算力过剩。",
        },
        {
            "信号": "云厂商CAPEX/RPO",
            "状态": "反证层已接入",
            "已接证据": official["evidence"],
            "仍缺什么": "完整 CAPEX 指引历史、GCP spot、AWS 90天 spot history。",
            "决策读法": "官方层仍偏扩张，是价格层转弱的反证。",
        },
        {
            "信号": "模型/API成本",
            "状态": "离散趋势可观察" if _has_token_change_history(market_facts) else ("横截面可观察" if has_track("model_value_score") or has_track("token_price") else "缺口"),
            "已接证据": value["evidence"],
            "仍缺什么": "Artificial Analysis 授权 API、任务质量归因、连续历史；当前 token 价格是离散快照。",
            "决策读法": "更像应用层毛利改善线索，不直接等于 GPU 需求下滑。",
        },
        {
            "信号": "应用商业化",
            "状态": "弱信号" if has_track("app_commercialization") else "缺口",
            "已接证据": "ARR.club public + Ramp adoption 已入库。",
            "仍缺什么": "Sacra/ARR 深源、私企收入历史、source links。",
            "决策读法": "可看需求方向，不能单独支撑估值切换。",
        },
        {
            "信号": "多模态成本",
            "状态": "横截面可观察" if has_track("multimodal_generation_cost") else "缺口",
            "已接证据": "BytePlus Seedance token pricing + seedance2.ai credits。",
            "仍缺什么": "credits 到 USD 的稳定换算、视频成本历史。",
            "决策读法": "可观察应用成本曲线，不能和 token 单价混算。",
        },
        {
            "信号": "授权指数/硬件成交",
            "状态": "缺口",
            "已接证据": "暂无可用授权 feed。",
            "仍缺什么": "ORNN/OCPI、SemiAnalysis index、GPU hardware sold price。",
            "决策读法": "这是升级为强交易信号前必须补的证据层。",
        },
    ]

    table = pd.DataFrame(rows)
    if has_gap(["gpu_contract_index", "hardware", "ocpi", "ornn"]):
        table.loc[table["信号"] == "授权指数/硬件成交", "状态"] = "缺口"
    return table


def _quality_gap_table(data: Dict[str, Any], limit: int = 8) -> pd.DataFrame:
    quality_events = data["tables"].get("quality_events", _empty_df([]))
    if quality_events.empty:
        return pd.DataFrame(columns=["缺口", "原因", "次数"])
    grouped = (
        quality_events.assign(
            affected_key=quality_events["affected_key"].fillna("unknown"),
            error_code=quality_events["error_code"].fillna("UNKNOWN"),
        )
        .groupby(["affected_key", "error_code"], dropna=False)
        .size()
        .reset_index(name="次数")
        .sort_values(["次数", "affected_key"], ascending=[False, True])
        .head(limit)
    )
    return grouped.rename(columns={"affected_key": "缺口", "error_code": "原因"})


def _inflection_watchlist_table(data: Dict[str, Any]) -> pd.DataFrame:
    snapshot = _core_evidence_snapshot(data)
    regime = snapshot["regime"]
    summary = snapshot["summary"]
    value = snapshot["model_value_summary"]

    h200_90d = regime.get("h200_90d")
    b200_90d = regime.get("b200_90d")
    h100_min = summary.get("h100_available_min")
    h100_count = summary.get("h100_available_count")
    h200_weak = h200_90d is not None and h200_90d < 0
    b200_weak = b200_90d is not None and b200_90d < 0
    h100_liquid_low = h100_min is not None and h100_min <= 1.5 and (h100_count or 0) >= 40
    hardware_triggered = h200_weak and b200_weak and h100_liquid_low

    official_text = snapshot["official_summary"]["evidence"]
    official_still_strong = snapshot["official_summary"]["coverage"] == "5/5 hyperscalers"
    capex_triggered = False

    model_value_ok = (value.get("top_value_score") or 0) >= 100
    adoption_edge = None
    if summary.get("anthropic_adoption") is not None and summary.get("openai_adoption") is not None:
        adoption_edge = summary["anthropic_adoption"] - summary["openai_adoption"]
    app_triggered = model_value_ok and adoption_edge is not None and adoption_edge > 0

    rows = [
        {
            "拐点": "硬件链转负",
            "当前状态": "未触发" if not hardware_triggered else "触发",
            "视觉读数": f"H200 {_point_percent(h200_90d)} / B200 {_point_percent(b200_90d)}",
            "当前读数": f"H200 90d {_point_percent(h200_90d)}；B200 90d {_point_percent(b200_90d)}；H100 order book {_money(h100_min, '/GPU hr')} / {_plain_number(h100_count)} offers。",
            "触发条件": "H200/B200 90日价格同步转负，且 H100 低价可用订单簿有足够深度。",
            "二级市场动作": "触发后才考虑提高硬件/算力基础设施链的负面权重。",
        },
        {
            "拐点": "云厂商由压制转受益",
            "当前状态": "反向约束" if official_still_strong and not capex_triggered else "观察",
            "视觉读数": f"{snapshot['official_summary']['coverage']} 未转弱",
            "当前读数": _short_text(official_text),
            "触发条件": "闲置算力变现扩大，同时 CAPEX/RPO 指引不再继续上修或出现利用率改善证据。",
            "二级市场动作": "触发后才把算力变现从硬件链利空，转化为云厂商经营杠杆利好。",
        },
        {
            "拐点": "应用层价值接棒",
            "当前状态": "观察中" if app_triggered else "弱信号",
            "视觉读数": f"Value {_plain_number(value.get('top_value_score'))} / +{_point_percent(adoption_edge)}",
            "当前读数": f"CostGoat leader {value.get('top_value_model') or 'n/a'} value {_plain_number(value.get('top_value_score'))}；Anthropic/OpenAI adoption spread {_point_percent(adoption_edge)}。",
            "触发条件": "模型/API 价效比继续改善，同时 ARR、采用率或用量出现连续改善。",
            "二级市场动作": "触发后优先寻找应用/API routing 与垂直工作流公司，而不是单押硬件链。",
        },
    ]
    return pd.DataFrame(rows)


def _render_inflection_watchlist(data: Dict[str, Any], *, compact: bool = True) -> None:
    table = _inflection_watchlist_table(data)
    rows = table.to_dict("records")
    html = "".join(
        f"""
<div class="watch-card">
  <div class="watch-label">{row['拐点']}</div>
  <div class="watch-status">{row['当前状态']}</div>
  <div class="watch-body">{row['视觉读数']}</div>
</div>
"""
        for row in rows
    )
    st.markdown(
        f"""
<div class="decision-panel">
  <div class="panel-label">拐点监控</div>
  <div class="panel-title">下一次改变判断，看这三件事</div>
  <div class="watch-grid">{html}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    if not compact:
        with st.expander("展开拐点监控表", expanded=False):
            _render_detail_intro("拐点监控明细", "这里是总览拐点卡的可审计表格，含当前读数、触发条件和二级市场动作。")
            st.dataframe(table, width="stretch", hide_index=True)


def _render_investment_bridge(data: Dict[str, Any]) -> None:
    snapshot = _core_evidence_snapshot(data)
    regime = snapshot["regime"]
    summary = snapshot["summary"]
    official = snapshot["official_summary"]
    value = snapshot["model_value_summary"]
    decision = data["decision"]
    confidence = "n/a" if decision is None else f"{decision.confidence}%"
    gpu_table = snapshot["gpu_table"].copy()
    old_values = pd.to_numeric(
        gpu_table[gpu_table["GPU"].isin(["A100 80GB", "H100"])]["delta90_numeric"],
        errors="coerce",
    ).dropna()
    frontier_values = pd.to_numeric(
        gpu_table[gpu_table["GPU"].isin(["H200", "B200"])]["delta90_numeric"],
        errors="coerce",
    ).dropna()
    old_avg = None if old_values.empty else float(old_values.mean())
    frontier_avg = None if frontier_values.empty else float(frontier_values.mean())
    adoption_edge = None
    if summary.get("anthropic_adoption") is not None and summary.get("openai_adoption") is not None:
        adoption_edge = summary["anthropic_adoption"] - summary["openai_adoption"]

    rows = [
        {
            "layer": "价格层",
            "state": "支持叙事松动",
            "style": "support",
            "readout": f"旧卡均值 {_point_percent(old_avg)}，前沿卡均值 {_point_percent(frontier_avg)}；H100 订单簿 {_money(summary.get('h100_available_min'), '/GPU hr')} / {_plain_number(summary.get('h100_available_count'))} offers。",
            "action": "只能降低“持续紧缺”的确定性。",
        },
        {
            "layer": "官方层",
            "state": "反证未解除",
            "style": "contra",
            "readout": f"{official['coverage']}；{_short_text(official['evidence'], 96)}",
            "action": "不支持现在把硬件链直接转空。",
        },
        {
            "layer": "应用层",
            "state": "观察接棒",
            "style": "watch",
            "readout": f"模型价效比 leader {value.get('top_value_model') or 'n/a'}，value {_plain_number(value.get('top_value_score'))}；Anthropic/OpenAI 采用率差 {_point_percent(adoption_edge)}。",
            "action": "若连续改善，优先看应用/API routing。",
        },
        {
            "layer": "质量门",
            "state": f"{snapshot['quality_status']} / {confidence}",
            "style": "block",
            "readout": "ORNN/OCPI、硬件成交价、AWS/GCP spot 历史和 ARR 深源仍未闭环。",
            "action": "阻止升级为强交易信号。",
        },
    ]
    html = "".join(
        f"""
<div class="bridge-card {row['style']}">
  <div class="bridge-label">{escape(row['layer'])}</div>
  <div class="bridge-call">{escape(row['state'])}</div>
  <div class="bridge-readout">{escape(row['readout'])}</div>
  <div class="bridge-action">{escape(row['action'])}</div>
</div>
"""
        for row in rows
    )
    st.markdown(
        f"""
<div class="decision-panel">
  <div class="panel-label">投资判断桥</div>
  <div class="panel-title">现在只够做一件事：降低单一稀缺叙事权重</div>
  <div class="bridge-grid">{html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _readiness_visual_html(data: Dict[str, Any]) -> str:
    table = _signal_readiness_table(data)
    if table.empty:
        body = '<div class="visual-footnote">暂无信号就绪度。</div>'
        return f"""
<div class="visual-card">
  <div class="visual-title">信号就绪结构</div>
  {body}
</div>
"""
    status = table["状态"].fillna("")
    ready = int(status.str.contains("可观察|已接入", regex=True).sum())
    weak = int(status.str.contains("弱信号", regex=False).sum())
    missing = int(status.str.contains("缺口", regex=False).sum())
    total = max(1, int(len(table)))
    rows = [
        ("可用/反证层", ready, "ready"),
        ("弱信号", weak, "weak"),
        ("硬缺口", missing, "missing"),
    ]
    html = ""
    for label, count, style in rows:
        width = _clamp(count / total * 100, 3, 100)
        class_name = "readiness-bar" if style == "ready" else f"readiness-bar {style}"
        html += f"""
<div class="readiness-row">
  <div class="readiness-label">{escape(label)}</div>
  <div class="readiness-track"><div class="{class_name}" style="width:{width:.1f}%;"></div></div>
  <div class="readiness-score">{count}/{total}</div>
</div>
"""
    return f"""
<div class="visual-card">
  <div class="visual-title">信号就绪结构</div>
  {html}
  <div class="visual-footnote">可用层能观察方向；弱信号只做辅助；硬缺口会阻止信号升级。</div>
</div>
"""


def _gap_blocker_visual_html(data: Dict[str, Any]) -> str:
    gaps = _quality_gap_table(data, limit=6)
    if gaps.empty:
        body = '<div class="visual-footnote">暂无主要质量缺口。</div>'
    else:
        max_count = max(1.0, float(pd.to_numeric(gaps["次数"], errors="coerce").max()))
        rows = []
        for _, row in gaps.iterrows():
            count = float(row["次数"])
            label = _short_text(f"{row['缺口']} / {row['原因']}", 42)
            width = _clamp(count / max_count * 100, 4, 100)
            rows.append(
                f"""
<div class="value-row">
  <div class="value-label" title="{escape(str(row['缺口']))}">{escape(label)}</div>
  <div class="value-track"><div class="value-bar gap-bar" style="width:{width:.1f}%;"></div></div>
  <div class="value-score">{_plain_number(count)}</div>
</div>
"""
            )
        body = "".join(rows)
    return f"""
<div class="visual-card">
  <div class="visual-title">信号升级阻碍</div>
  {body}
  <div class="visual-footnote">条形越长，越应该先解决；这不是坏消息包装，而是防止误判。</div>
</div>
"""


def _render_signal_readiness(data: Dict[str, Any], *, compact: bool = True) -> None:
    table = _signal_readiness_table(data)
    rows = table.head(4 if compact else len(table)).to_dict("records")
    html = "".join(
        f"""
<div class="signal-row">
  <div class="signal-name">{row['信号']}</div>
  <div class="signal-state">{row['状态']}</div>
  <div class="signal-detail">{row['决策读法']}<br><span style="color:#86868b;">仍缺：{row['仍缺什么']}</span></div>
</div>
"""
        for row in rows
    )
    st.markdown(
        f"""
<div class="decision-panel">
  <div class="panel-label">信号就绪度</div>
  {html}
</div>
""",
        unsafe_allow_html=True,
    )
    if not compact:
        with st.expander("展开信号就绪度表", expanded=False):
            _render_detail_intro("信号就绪度明细", "这里按证据层列出已接数据、仍缺数据和当前可用于判断的方式。")
            st.dataframe(table, width="stretch", hide_index=True)


def _render_decision_rules(data: Dict[str, Any]) -> None:
    snapshot = _core_evidence_snapshot(data)
    regime = snapshot["regime"]
    official = snapshot["official_summary"]
    st.markdown(
        f"""
<div class="decision-panel">
  <div class="panel-label">怎么用它</div>
  <div class="panel-title">只在两层证据同向时改变判断</div>
  <div class="panel-body">当前价格层是 <b>{regime['label']}</b>，官方层是 <b>{official['coverage']}</b> 且未转弱，所以动作仍是观察。</div>
  <div class="rule-list">
    <div class="rule-item"><b>硬件链转负：</b>前沿卡价格和可用订单簿一起转弱，同时官方 CAPEX/RPO 下修。</div>
    <div class="rule-item"><b>云厂商转正：</b>闲置算力变现扩大，但 CAPEX 不继续加速，毛利或 FCF 口径出现改善。</div>
    <div class="rule-item"><b>应用层转正：</b>模型/API 成本继续下降，同时 ARR、采用率或用量出现连续改善。</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_decision_shell(data: Dict[str, Any]) -> None:
    snapshot = _core_evidence_snapshot(data)
    regime = snapshot["regime"]
    summary = snapshot["summary"]
    official = snapshot["official_summary"]
    value = snapshot["model_value_summary"]
    decision = data["decision"]
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    confidence = "n/a" if decision is None else f"{decision.confidence}%"

    st.markdown(
        f"""
<div class="tracker-header">
  <div>
    <div class="tracker-title">AI 算力 Tracker</div>
    <div class="tracker-action">继续观察</div>
    <div class="tracker-reason">价格层松动，但官方 CAPEX/RPO 还没有转弱。</div>
  </div>
  <div class="status-grid">
    <div class="status-tile">
      <div class="status-label">GPU</div>
      <div class="status-value">{escape(str(regime['label']))}</div>
      <div class="status-note">A100 {_point_percent(regime['a100_90d'])}</div>
    </div>
    <div class="status-tile">
      <div class="status-label">Order book</div>
      <div class="status-value">{_money(summary['h100_available_min'], '')}</div>
      <div class="status-note">H100 / {_plain_number(summary['h100_available_count'])} offers</div>
    </div>
    <div class="status-tile">
      <div class="status-label">Model value</div>
      <div class="status-value">{_plain_number(value['top_value_score'])}</div>
      <div class="status-note">{escape(str(value['top_value_model'] or 'n/a'))}</div>
    </div>
    <div class="status-tile">
      <div class="status-label">Gate</div>
      <div class="status-value">{escape(str(snapshot['quality_status']))}</div>
      <div class="status-note">{escape(str(snapshot['decision_state']))} / {confidence}</div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    _render_home_visuals(snapshot, market_facts)

    _render_investment_bridge(data)


def _render_price_room(data: Dict[str, Any]) -> None:
    snapshot = _core_evidence_snapshot(data)
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    regime = snapshot["regime"]
    _render_room_header(
        "价格",
        "先看代际分化，再看当前订单簿。前沿卡没有同步转弱时，不把旧卡下跌解读成全市场过剩。",
        f"{escape(str(regime['label']))}",
    )
    st.markdown(
        f"""
<div class="visual-grid">
  <div class="visual-card">
    <div class="visual-title">代际价格压力</div>
    {_render_price_generation_visual(snapshot)}
    {_caption_div(_market_source_caption(market_facts, ["gpu_market_trend"], note="只用 GPUs.io 90日 mover，不外推为完整成交价"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">订单簿深度</div>
    {_render_orderbook_depth_visual(snapshot)}
    {_caption_div(_market_source_caption(market_facts, ["gpu_available_offer"], note="available=true 当前可租 offer，不是硬件二手成交价"))}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("展开价格明细", expanded=False):
        _render_detail_intro("价格明细", "这里保留精确数值、GPUPerHour 当前可用订单簿、ComputePrices 7日公开趋势和 GPUs.io movers；不与总览图重复。")
        st.dataframe(
            snapshot["gpu_table"].drop(columns=["delta90_numeric", "min_offer_numeric", "offer_count_numeric"], errors="ignore"),
            width="stretch",
            hide_index=True,
        )
        st.dataframe(_available_offer_summary_table(market_facts), width="stretch", hide_index=True)
        st.dataframe(_gpu_market_trend_summary_table(market_facts), width="stretch", hide_index=True)


def _render_cloud_room(data: Dict[str, Any]) -> None:
    official_events = data["tables"].get("official_events", _empty_df([]))
    snapshot = _core_evidence_snapshot(data)
    official = snapshot["official_summary"]
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    _render_room_header(
        "云厂商",
        "云 spot 价格可以观察供需，但真正改变判断的是 CAPEX/RPO 是否转弱。现在官方层仍是反证。",
        f"{escape(str(official['coverage']))}",
    )
    st.markdown(
        f"""
<div class="visual-grid">
  <div class="visual-card">
    <div class="visual-title">H100 云实例价格</div>
    {_render_cloud_price_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["cloud_instance_price"], note="官方云 VM-hour 价格，不与 neocloud per-GPU-hour 混算"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">官方 CAPEX / RPO</div>
    {_render_official_cloud_visual(official_events)}
    {_caption_div(_official_source_caption(official_events))}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("展开官方云实例价格", expanded=False):
        _render_detail_intro("云实例与官方事件明细", "这里保留官方云 VM-hour 样本和 hyperscaler 官方 CAPEX/RPO 事件；单位不归一到 per-GPU-hour。")
        table = _official_layer_table(official_events)
        if not table.empty:
            st.dataframe(table, width="stretch", hide_index=True)
        st.dataframe(_cloud_instance_summary_table(market_facts), width="stretch", hide_index=True)


def _render_apps_room(data: Dict[str, Any]) -> None:
    market_facts = data["tables"].get("market_facts", _empty_df(MARKET_FACT_COLUMNS))
    snapshot = _core_evidence_snapshot(data)
    value = snapshot["model_value_summary"]
    _render_room_header(
        "应用",
        "这里看成本下降有没有被应用商业化接住。模型价效比、企业采用率、Seedance 成本分开读。",
        f"value {_plain_number(value['top_value_score'])}",
    )
    st.markdown(
        f"""
<div class="visual-grid">
  <div class="visual-card">
    <div class="visual-title">Token 价格变化</div>
    {_render_token_change_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["token_price"], note="output $/1M tokens，离散快照，不画连续趋势"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">高质量模型输出价</div>
    {_render_model_price_quality_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["model_value_score"], note="CostGoat public proxy，不替代 Artificial Analysis"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">商业化差值</div>
    {_render_app_spread_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["app_commercialization"], note="采用率和 ARR public signal 分开读"))}
  </div>
  <div class="visual-card">
    <div class="visual-title">多模态生成成本</div>
    {_render_multimodal_cost_visual(market_facts)}
    {_caption_div(_market_source_caption(market_facts, ["multimodal_generation_cost"], note="官方 token 价与第三方 credits 不相加"))}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("展开应用/API 明细", expanded=False):
        _render_detail_intro("应用/API 明细", "这里保留 CostGoat、token/API、ARR.club、Ramp 和 Seedance 的明细；顶部图只展示最关键的价格变化、价效比、商业化差值和成本结构。")
        st.dataframe(_token_change_table(market_facts), width="stretch", hide_index=True)
        st.dataframe(_model_value_table(market_facts), width="stretch", hide_index=True)
        st.dataframe(_adoption_table(market_facts), width="stretch", hide_index=True)
        st.dataframe(_multimodal_summary_table(market_facts), width="stretch", hide_index=True)


def _render_evidence_room(data: Dict[str, Any]) -> None:
    _render_room_header(
        "证据库",
        "这里只回答两件事：哪些证据能支撑判断，哪些缺口会阻止升级信号。",
        str(data["quality_gate"].status),
    )
    _render_evidence_status_visual(data)
    st.markdown(
        f"""
<div class="visual-grid">
  {_readiness_visual_html(data)}
  {_gap_blocker_visual_html(data)}
</div>
""",
        unsafe_allow_html=True,
    )
    _render_signal_readiness(data, compact=False)
    _render_decision_rules(data)
    gaps = _quality_gap_table(data)
    if not gaps.empty:
        st.markdown("#### 当前最影响判断的缺口")
        st.dataframe(gaps, width="stretch", hide_index=True)
    with st.expander("影响判断的缺口明细", expanded=False):
        _render_detail_intro("缺口明细", "这里列出阻止信号升级的数据源问题、授权缺口和失败原因。")
        _render_missing_summary(data)
    with st.expander("来源健康", expanded=False):
        _render_detail_intro("来源健康", "这里用于检查各生产源是否正常刷新，以及是否出现限流、授权或解析问题。")
        _render_source_health(data)
    with st.expander("Proxy 历史和价格页快照", expanded=False):
        _render_detail_intro("Proxy 审计", "这里只做来源审计，不把低样本 proxy 或单日价格页包装成趋势结论。")
        _render_public_proxy_history(data["public_proxy_history"], key_prefix="evidence_room_proxy")
        _render_provider_snapshot_cards(data["tables"]["gpu_prices"])
    with st.expander("完整二级市场读数", expanded=False):
        _render_detail_intro("二级市场读数", "这里保留较长文字版判断，供回看每一层证据如何影响硬件链、云厂商和应用层。")
        _render_market_decision_cards(data)
    with st.expander("完整数据覆盖与失败源明细", expanded=False):
        _render_detail_intro("数据覆盖与失败源", "这里是生产表覆盖和质量门 reason table，主要用于排查，不作为首屏展示。")
        st.dataframe(data["source_coverage"], width="stretch", hide_index=True)
        reasons = pd.DataFrame([reason.__dict__ for reason in data["quality_gate"].reasons])
        if reasons.empty:
            st.success("当前质量门没有记录阻塞项。")
        else:
            st.dataframe(reasons, width="stretch", hide_index=True)


def _render_legacy_note(legacy_counts: pd.DataFrame) -> None:
    st.warning("Legacy/demo 表不参与生产判断，也不进入首屏指标。")
    st.dataframe(legacy_counts, width="stretch", hide_index=True)


def main() -> None:
    data = load_dashboard_data(DB_PATH)
    _render_single_page_trend_board(data)


if __name__ == "__main__":
    main()
