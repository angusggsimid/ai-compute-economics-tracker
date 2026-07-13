# Dashboard Usability Closure Plan

Goal: make the tracker dashboard useful to a real user, not just technically correct. The first screen must still show data quality and current judgment, but it must also surface historical GPU price movement using real production data.

## Tasks

### U1: Simulate User Use And Product Critique

- **depends_on**: []
- **location**:
  - `/Users/agg/Documents/AI Compute Economics/dashboard_v2.py`
  - `/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_production_smoke.png`
- **description**:
  - Use the running dashboard as a skeptical user.
  - Identify why it is not yet decision-useful or visually acceptable.
  - Focus on first-screen usefulness, historical price trend visibility, visual hierarchy, source clarity, and failure exposure.
- **validation**:
  - Produce concrete acceptance criteria for UI/product changes.
- **status**: Completed
- **log**:
  - 2026-07-06: User-simulation subagent reviewed the running dashboard and concluded it was still a data validation page rather than a usable tracker. The highest-impact issue was that first screen did not show historical GPU price movement even though production data had quote-date history.
  - 2026-07-06: Acceptance criteria from critique: first screen must show H100/H200 historical price trend, separate `public_pricing_page` from `aggregator`, compress missing-source summary, move full coverage table below/inside expander, and keep seed/legacy out of trend.
- **files edited/created**:
  - No file edits; read-only user simulation.

### U2: Add Real Historical GPU Price Trend Contract

- **depends_on**: []
- **location**:
  - `/Users/agg/Documents/AI Compute Economics/dashboard_v2.py`
  - `/Users/agg/Documents/AI Compute Economics/test_suite/test_dashboard_queries.py`
- **description**:
  - Add dashboard query helpers that build a real GPU price trend from `production_gpu_prices`.
  - Trend must group by `date`, `gpu_model`, `source_type`, and expose median/min/max/quote count.
  - It must not read `gpu_prices_daily`, seed rows, demo rows, or legacy CSI.
  - It must preserve source type separation: `public_pricing_page` and `aggregator` are not blended into one official metric.
- **validation**:
  - `python3 -m pytest test_suite/test_dashboard_queries.py -q`
  - Empty and seed-only DB return blocked first view and no fake trend.
- **status**: Completed
- **log**:
  - 2026-07-06: Added a dashboard GPU price trend contract sourced only from `production_gpu_prices`; it groups by `date`, `gpu_model`, and `source_type`, exposing median/min/max/quote count.
  - 2026-07-06: Added tests proving empty and seed-only DBs produce no fake trend, and `public_pricing_page` rows remain separate from `aggregator` rows.
- **files edited/created**:
  - `/Users/agg/Documents/AI Compute Economics/dashboard_v2.py`
  - `/Users/agg/Documents/AI Compute Economics/test_suite/test_dashboard_queries.py`
  - `/Users/agg/Documents/AI Compute Economics/dashboard-usable-product-plan.md`

### U3: Redesign Dashboard First Screen And Evidence Tabs

- **depends_on**: [U2]
- **location**:
  - `/Users/agg/Documents/AI Compute Economics/dashboard_v2.py`
  - `/Users/agg/Documents/AI Compute Economics/test_suite/dashboard_checklist.md`
- **description**:
  - Improve visual hierarchy and product usability.
  - First screen should show:
    - current judgment,
    - quality gate,
    - confidence,
    - latest run,
    - historical GPU price trend chart,
    - compact missing-source summary.
  - Data coverage table should move below the trend instead of dominating the first screen.
  - GPU tab should include the historical chart and quote table.
  - The chart title and copy must make clear whether a line is public aggregator quote history or official provider snapshot.
- **validation**:
  - `python3 -m py_compile dashboard_v2.py`
  - Browser smoke verifies first-screen text, historical chart title, and no old CSI primary metric.
- **status**: Completed
- **log**:
  - 2026-07-06: Redesigned first screen around a decision strip, H100/H200 historical GPU price trend, compact missing-source summary, and source health cards.
  - 2026-07-06: Added trend rendering with median line, min/max band, quote-count hover details, and source labels that distinguish `ComputePrices public quote history` from `Provider pricing page snapshot`.
  - 2026-07-06: Moved full data coverage and detailed failure table into a collapsed expander so they remain inspectable without dominating the first viewport.
  - 2026-07-06: GPU evidence tab now starts with the same historical trend chart before quote distribution and row-level evidence.
  - 2026-07-06: Updated `test_suite/dashboard_checklist.md` to reflect the usable-dashboard criteria and current pass state.
  - 2026-07-06: Validation passed: `python3 -m py_compile dashboard_v2.py`; `python3 -m pytest test_suite/test_dashboard_queries.py -q` with 4 passed.
- **files edited/created**:
  - `/Users/agg/Documents/AI Compute Economics/dashboard_v2.py`
  - `/Users/agg/Documents/AI Compute Economics/test_suite/dashboard_checklist.md`
  - `/Users/agg/Documents/AI Compute Economics/dashboard-usable-product-plan.md`

### U4: End-To-End Browser Smoke And Documentation

- **depends_on**: [U3]
- **location**:
  - `/Users/agg/Documents/AI Compute Economics/tracker_data/`
  - `/Users/agg/Documents/AI Compute Economics/README_v2.md`
  - `/Users/agg/Documents/AI Compute Economics/CONTEXT.md`
  - `/Users/agg/Documents/AI Compute Economics/dashboard-usable-product-plan.md`
- **description**:
  - Run tests, restart/reuse dashboard, simulate user use in browser, save screenshot.
  - Update docs with the usable-dashboard result and remaining data limitations.
- **validation**:
  - `python3 -m pytest test_suite/test_dashboard_queries.py -q`
  - `curl http://127.0.0.1:8503` returns 200.
  - Browser smoke screenshot saved.
- **status**: Completed
- **log**:
  - 2026-07-06: Reused running dashboard at `http://127.0.0.1:8503`; `curl` returned HTTP 200.
  - 2026-07-06: Browser smoke with local Google Chrome verified first-screen title, `H100/H200 历史 GPU 价格趋势`, `影响判断的缺口`, and `来源健康`; also verified no `Composite Scarcity Index` primary metric in body text.
  - 2026-07-06: Browser screenshot saved to `tracker_data/dashboard_v2_usable_trend_smoke.png`.
  - 2026-07-06: Current real-data first screen shows `No Signal`, `WARN`, `15%`, H100/H200 price history, and source-backed missing data rather than a data-coverage table as the main content.
- **files edited/created**:
  - `/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_usable_trend_smoke.png`
  - `/Users/agg/Documents/AI Compute Economics/dashboard-usable-product-plan.md`
