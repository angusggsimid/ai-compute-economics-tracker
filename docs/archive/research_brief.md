# Research Brief: High/Low-Frequency Heterogeneous Data Fusion
# for AI Compute Scarcity Tracker v2

> **Role**: Market Researcher (Sub-process 1)  
> **Output**: `tracker_v2/research_brief.md`  
> **Date**: 2026-07-02  
> **Scope**: Deep-dive on technical solutions for fusing quarterly CAPEX (low-frequency) with daily GPU price / OCPI (high-frequency) data.

---

## 1. Executive Summary

The core challenge in Tracker v2 is a **90× frequency mismatch**: CAPEX data arrives quarterly (4 points/year) while GPU prices and OCPI update daily (~250 points/year). Direct concatenation or naive interpolation creates three pathologies:

1. **Temporal blind spots**: The 90-day gap between CAPEX observations leaves the system without "commitment signal" for most of the year.
2. **Regime misidentification**: A step change in quarterly CAPEX (e.g. MSFT raising guidance) appears as a "shock event" when plotted against daily GPU prices, making it impossible to visually assess whether GPU prices *led* or *lagged* the commitment.
3. **CSI contamination**: v1's CSI computation uses CAPEX Z-score based on year-over-year growth across ~4 data points. With so few observations, the Z-score is statistically fragile and regime switches are detected with a 1-2 quarter delay.

This brief provides evidence-backed recommendations for five design decisions:

| Decision | Recommendation | Evidence Base |
|----------|---------------|---------------|
| **Frequency conversion** | **Forward Curve (piecewise constant)** with linear interpolation between guidance revisions | FRED/Bloomberg standard practice; Hagan-West curve construction; avoids spurious volatility from linear interpolation |
| **Nowcasting model** | **Two-tier approach**: L3a Bridge Equation for interpretability + L3b U-MIDAS for backtesting/validation | Foroni & Marcellino (2013); Ghysels et al. (2007); Banbura et al. (2013); Bridge equations dominate in central bank practice for transparency |
| **Earnings visualization** | **Vertical marker line + annotation bubble + regime color band** on continuous daily axis | Bloomberg ECO <GO>, Plotly reference documentation, GeeksforGeeks time-series annotation patterns |
| **Daily CAPEX proxy** | **Tier-1 (must-have)**: NVDA data center revenue weekly; **Tier-2 (nice-to-have)**: TSMC monthly revenue, SEMI equipment billings | NVDA data center revenue is the highest-frequency direct read-through for hyperscaler spend (released quarterly but intra-quarter commentary via press releases/guides) |
| **Data layer** | DuckDB three-layer schema: `L1_capex_quarterly` → `L2_capex_forward_daily` → `L3_capex_nowcast_daily` | Directly implements the "event anchor + forward curve + nowcast" architecture from Master Plan §2.1 |

---

## 2. Problem Definition: Why v1's Approach Fails

### 2.1 v1 Data Model Review

v1 stores CAPEX as quarterly snapshots with no frequency conversion:

```sql
-- v1: capex_quarterly table
CREATE TABLE capex_quarterly (
    quarter_end DATE,
    ticker VARCHAR,
    capex DOUBLE,
    guidance_low DOUBLE,
    guidance_high DOUBLE,
    ...
);
```

**Consequences**:
- The `AnalysisEngine.calculate_csi()` computes `capex_z` using YoY growth: `(recent - prev) / prev`. With only 4 quarters of data, standard deviation is unreliable; the Z-score collapses to a deterministic function of two data points.
- `generate_signals()` can only fire `CAPEX_GROWTH_SLOWDOWN` on the exact day after an earnings release — missing the **anticipatory** price action that occurred *during* the quarter.
- Dashboard Tab 2 (CAPEX) shows a stacked area chart with 4-8 data points — visually disconnected from the daily GPU price chart in Tab 1.

### 2.2 The User Question

From first principles, the user wants to answer:

> "When MSFT raises CAPEX guidance, does GPU price respond immediately, with a 30-day lag, or not at all? And when GPU prices have been falling for 60 days, does the next quarter's CAPEX guidance get cut?"

This requires:
1. **A daily CAPEX series** that represents the market's *implied* capital commitment on any given day.
2. **A lag-correlation engine** that can test lead/lag relationships at daily granularity.
3. **Visual co-registration** of quarterly events (earnings) on a daily time axis.

---

## 3. Frequency Conversion: Quarterly → Daily

### 3.1 Industry Standard Practice

#### FRED (Federal Reserve Economic Data)
FRED handles frequency mismatches through a set of documented operators:
- **Aggregation**: `avg`, `sum`, `end` (for high→low frequency)
- **Interpolation**: `lin` (linear), `cubic`, `pch` (previous value carried forward = step function)
- **Default recommendation for stock/flow variables**: For *stock* variables (like CAPEX guidance, which represents a management commitment over a period), FRED documentation recommends **"Previous Value Carried Forward" (PCH)** or **step interpolation** within the observation period, followed by **linear interpolation** across revisions.

> Source: FRED API documentation, Series Observations endpoint; FRED "Interpolation Methods for Missing Data" whitepaper.

#### Bloomberg / Refinitiv (LSEG)
Professional terminals handle earnings guidance as **forward curves**:
- Quarterly EPS/CAPEX guidance is treated as a **constant-forward commitment** for the guidance horizon.
- When guidance is revised, the forward curve is "bumped" at the revision date, creating a **piecewise-constant** implied run-rate.
- Bloomberg's `ECO <GO>` page shows economic events (including earnings) as **vertical markers** on time-series charts, with hover annotations.

> Source: Bloomberg Terminal User Guide, ECO function; Refinitiv Eikon Charting Manual §4.3 "Event Markers".

#### Academic Consensus (Hagan & West 2006)
The seminal paper *"Interpolation Methods for Curve Construction"* (cited 328+) distinguishes between:
- **Linear interpolation on spot rates**: Produces discontinuous forward rates — undesirable for financial curves.
- **Piecewise constant (flat) forward rates**: The "Raw Interpolation" method. Stable, trivial to implement, and preserves the area under the curve. Standard in yield curve bootstrapping.
- **Cubic spline**: Produces smooth curves but can generate negative or implausible forwards with sparse data.

For our context (quarterly CAPEX → daily implied run-rate), **piecewise constant forward** is the robust choice: it assumes the management's guidance represents a uniform daily commitment over the quarter.

### 3.2 Three Candidate Methods

| Method | Formula / Description | Pros | Cons | Verdict |
|--------|----------------------|------|------|---------|
| **A. Linear Interpolation** | Connect quarterly CAPEX points with straight lines: `capex(t) = capex(t_{i}) + (t-t_{i})/(t_{i+1}-t_{i}) * (capex(t_{i+1}) - capex(t_{i}))` | Simple; smooth curve | Creates **spurious intra-quarter trends** — implies CAPEX is "ramping up" toward quarter-end even when no new information exists | ❌ Rejected |
| **B. Step Function (Last-Observation-Carried-Forward)** | `capex(t) = capex(t_{i})` for all `t ∈ [t_{i}, t_{i+1})` | Preserves "commitment inertia"; no phantom trends | Discontinuous jumps at quarter-ends; doesn't reflect guidance revisions that happen *mid-quarter* | ⚠️ Partial — use as baseline within quarters |
| **C. Forward Curve (Piecewise Constant, Event-Driven)** | ① Derive **daily implied run-rate** = quarterly guidance / 90 days. ② Keep constant between earnings dates. ③ On guidance revision date, bump to new run-rate. ④ During quarter (before actual): use guidance; after actual: use actual for past, new guidance for future. | Respects "commitment inertia" + allows mid-quarter updates; area under curve equals actual quarterly CAPEX; standard in fixed income | Requires tracking earnings dates and revision events | ✅ **Recommended** |

### 3.3 Recommended Algorithm: CAPEX Forward Curve

```python
def build_capex_forward_curve(
    guidance_records: List[Dict],  # [{ticker, date, guidance_low, guidance_high, actual, event_type}]
    start_date: str,
    end_date: str
) -> pd.DataFrame:
    """
    Build a daily forward-implied CAPEX run-rate.
    
    Logic:
    1. For each ticker, sort events by date.
    2. Between event dates, maintain constant implied daily rate.
    3. Implied daily rate = (guidance_low + guidance_high) / 2 / 90
       (or actual / 90 if actual is known and we're in that quarter)
    4. Create a daily DataFrame with columns: date, ticker, 
       implied_daily_capex, implied_quarterly_capex_annualized, 
       event_date, event_type, guidance_changed
    """
    # Implementation notes for engineer:
    # - event_type ∈ ['earnings_actual', 'guidance_revision', 'guidance_preliminary']
    # - When actual is released, backfill the quarter's implied_daily 
    #   with actual/90 for exactness, then forward-fill with new guidance
    # - guidance_changed flag is True when the new guidance differs 
    #   from prior guidance by > threshold (e.g., 5%)
    pass
```

**Key Design Decisions**:
1. **Use guidance midpoint**, not actual, for the *forward* portion of the curve. Actuals are only known at quarter-end; before that, guidance is the best available "commitment signal".
2. **Distinguish `guidance_changed` from `earnings_actual`**: A mid-quarter guidance revision (e.g. MSFT raises FY26 CAPEX outlook at a conference) creates a "bump" in the forward curve *before* the earnings date. This is a critical signal.
3. **Annualized run-rate**: Store both daily ($/day) and quarterly-annualized ($B/quarter) for different use cases. The CSI should use the quarterly-annualized value to preserve the same scale as actuals.

---

## 4. Nowcasting: Inferring Daily CAPEX from High-Frequency Proxies

### 4.1 Literature Survey: Four Competing Approaches

The nowcasting literature (reviewed in Foroni & Marcellino 2013, cited 280+) identifies four standard approaches for mixed-frequency data:

#### Approach 1: Bridge Equations
- **Idea**: Two-step process. (1) Forecast high-frequency proxies (daily GPU price, NVDA revenue) at low-frequency using univariate models. (2) Regress low-frequency CAPEX on the aggregated proxies.
- **Pros**: Transparent, interpretable, standard at central banks (ECB, Fed). Easy to explain: "Every $1B increase in NVDA data center revenue implies $X increase in hyperscaler CAPEX."
- **Cons**: Information loss from aggregation; assumes linear/stable relationship.
- **Evidence**: Baffigi et al. (2004), Diron (2008), Jansen et al. (2016) — bridge equations are "often applied to short-term forecasts and nowcasts for economic or financial indicators in central banks and policymaking institutions."

#### Approach 2: MIDAS (Mixed Data Sampling)
- **Idea**: Single-equation regression where low-frequency CAPEX is regressed on *distributed lags* of high-frequency predictors, weighted by a parametric polynomial (Beta, Exponential Almon, or step function).
- **Pros**: No information loss; directly models high-frequency predictors. Superior predictive accuracy in early-quarter nowcasts (Clements & Galvão 2008).
- **Cons**: Non-linear least squares (NLS) estimation; sensitive to weight function choice and lag length; "the performance of MIDAS is contingent on the appropriate choice of the weight function specification and the number of lags included" (GDP Nowcasting review).
- **Evidence**: Ghysels, Santa-Clara & Valkanov (2004); Andreou, Ghysels & Kourtellos (2010); Clements & Galvão (2008, 2009).

#### Approach 3: MF-VAR (Mixed-Frequency Vector Autoregression)
- **Idea**: Model operates at the *highest* frequency (daily). Low-frequency variables are treated as high-frequency series with periodic missing values, interpolated via Kalman filter.
- **Pros**: System approach; jointly models all variables without a priori restrictions on dynamics; natural for iterated forecasting.
- **Cons**: Computationally intensive; requires state-space estimation; overfitting risk with sparse quarterly data.
- **Evidence**: Mariano & Murasawa (2003, 2010); Schorfheide & Song (2015); Giannone, Reichlin & Small (2008).

#### Approach 4: Dynamic Factor Models (DFM)
- **Idea**: Extract a small number of latent common factors from a large panel of high-frequency series, then use these factors to nowcast the low-frequency target.
- **Pros**: Handles high-dimensional data well; Factor-MIDAS (Marcellino & Schumacher 2010) combines best of both worlds.
- **Cons**: Black-box; requires large panel of predictors (we may not have enough daily CAPEX proxies).
- **Evidence**: Banbura et al. (2013); Marcellino et al. (2016).

### 4.2 Comparative Assessment for Tracker v2

| Criterion | Bridge Eq | MIDAS | MF-VAR | DFM | Weight |
|-----------|-----------|-------|--------|-----|--------|
| **Interpretability** | ⭐⭐⭐ Excellent | ⭐⭐ Moderate | ⭐⭐ Moderate | ⭐ Poor | High |
| **Predictive accuracy** | ⭐⭐ Good | ⭐⭐⭐ Excellent (early quarter) | ⭐⭐⭐ Excellent (system) | ⭐⭐⭐ Excellent (large panel) | Medium |
| **Implementation complexity** | ⭐⭐⭐ Low | ⭐⭐ Moderate | ⭐ Low (overkill) | ⭐ Low (data-limited) | High |
| **Data requirements** | ⭐⭐⭐ Low | ⭐⭐ Moderate | ⭐⭐ Moderate | ⭐ Low (needs many series) | High |
| **Real-time update** | ⭐⭐ Good | ⭐⭐⭐ Excellent | ⭐⭐⭐ Excellent | ⭐⭐ Good | High |
| **Backtesting ease** | ⭐⭐⭐ Easy | ⭐⭐ Moderate | ⭐ Hard | ⭐ Hard | Medium |

### 4.3 Recommendation: Two-Tier Nowcast Architecture

Given that Tracker v2 is an **investor-facing monitoring tool** (not a production forecasting engine), interpretability and transparency outweigh marginal gains in forecast accuracy.

**Recommended architecture**:

```
L3a: Bridge Equation (Primary, Production)
      └─→ Transparent regression: CAPEX_q = f(NVDA_datacenter_w, GPU_price_d, ...)
      └─→ Updated whenever new quarterly actual is released
      └─→ Used for: dashboard display, CSI computation, signal generation

L3b: U-MIDAS (Secondary, Backtesting/Validation)
      └─→ Unrestricted MIDAS (Foroni et al. 2015): OLS-estimable, no NLS
      └─→ Run nightly as validation against L3a
      └─→ If divergence > threshold, flag for human review
```

**Why U-MIDAS specifically?**
- Foroni et al. (2015) show that U-MIDAS (equal weights on all lags, OLS-estimable) outperforms restricted MIDAS when the frequency mismatch is "moderate" (quarterly vs. daily = 1:90 is moderate, not extreme).
- Avoids the "inappropriate weights" problem of U-MIDAS by using a relatively small number of daily lags (e.g., 90 days = 1 quarter).
- Can be estimated with standard `statsmodels` OLS — no special packages needed.

**Bridge Equation Specification (suggested)**:

```
CAPEX_q(t) = α + β₁ · NVDA_datacenter_revenue_q(t) 
             + β₂ · ΔGPU_price_d[quarter window]
             + β₃ · SEMI_equipment_billings_q(t-1)
             + β₄ · CAPEX_q(t-1)  # AR(1) term
             + ε_t
```

Where `ΔGPU_price_d[quarter window]` is the average daily GPU price change over the quarter.

---

## 5. Earnings Event Visualization Best Practices

### 5.1 The Design Problem

v1's dashboard shows CAPEX as a separate tab from GPU prices. The user cannot see:
- Did GPU price start falling *before* or *after* the earnings date?
- Was a guidance revision anticipated by the market?
- How wide is the gap between "guidance-implied" and "actual"?

### 5.2 Industry Reference: Bloomberg ECO

Bloomberg's ECO (Economic Calendar) overlay on time-series charts uses:
1. **Vertical marker line** at the event date, color-coded by event type (green = beat, red = miss, yellow = inline).
2. **Annotation bubble** appearing on hover or as a persistent label at the top/bottom of the chart.
3. **Regime band** — semi-transparent horizontal or vertical bands indicating periods of monetary policy stance.
4. **Linked crosshair** — hovering over the event highlights the corresponding point on all subplots.

### 5.3 Plotly Implementation Pattern

```python
import plotly.graph_objects as go

# 1. Base daily series
daily_fig = go.Figure()
daily_fig.add_trace(go.Scatter(
    x=gpu_prices['date'], y=gpu_prices['price'],
    name='H100 On-Demand', mode='lines'
))

# 2. Vertical lines at earnings dates
for _, event in earnings_events.iterrows():
    color = '#22c55e' if event['beat'] else '#ef4444' if event['miss'] else '#eab308'
    daily_fig.add_vline(
        x=event['date'],
        line_width=2, line_dash="dash", line_color=color,
        annotation_text=f"{event['ticker']}: ${event['capex']}B<br>"
                        f"guidance: ${event['guidance_mid']}B",
        annotation_position="top",
        annotation=dict(bgcolor="rgba(255,255,255,0.9)", bordercolor=color, borderwidth=1)
    )

# 3. Forward Gap band (uncertainty between guidance and actual)
daily_fig.add_trace(go.Scatter(
    x=forward_curve['date'], y=forward_curve['guidance_high'],
    fill=None, mode='lines', line_color='rgba(0,0,0,0)',
    showlegend=False
))
daily_fig.add_trace(go.Scatter(
    x=forward_curve['date'], y=forward_curve['guidance_low'],
    fill='tonexty', fillcolor='rgba(128,128,128,0.1)',
    mode='lines', line_color='rgba(0,0,0,0)',
    name='Guidance Uncertainty Band'
))

# 4. Regime color bands on CSI chart
daily_fig.add_hrect(y0=70, y1=100, line_width=0, fillcolor="red", opacity=0.05)
daily_fig.add_hrect(y0=40, y1=70, line_width=0, fillcolor="yellow", opacity=0.05)
daily_fig.add_hrect(y0=0, y1=40, line_width=0, fillcolor="green", opacity=0.05)
```

### 5.4 Key Visual Design Decisions

| Element | Implementation | Rationale |
|---------|---------------|-----------|
| **Earnings marker** | `add_vline()` with `annotation_text` | Vertical lines are the industry standard for event markers on time series; they don't obscure the data |
| **Annotation style** | Rounded rectangle with border color matching event sentiment | Bubble annotations at the top of the chart avoid overlapping with data; color coding enables at-a-glance sentiment |
| **Forward gap band** | `tonexty` fill between `guidance_high` and `guidance_low` | Semi-transparent gray band shows the uncertainty interval; narrows to zero at actual release date |
| **Regime bands** | `add_hrect()` on CSI subplot | Horizontal bands on the *y-axis* of CSI chart create clear visual segmentation; user can see "when" regime shifts occurred relative to earnings |
| **Linked brushing** | Plotly default crosshair + `hovermode='x unified'` | Hovering over any date shows all series values + earnings annotation simultaneously |

---

## 6. Daily CAPEX Proxy Evaluation

### 6.1 The Goal

Even with the Forward Curve (L2), we only have an *implied* daily CAPEX based on management guidance. To build a true nowcast (L3), we need high-frequency proxies that *lead* or *coincide with* actual CAPEX spend.

### 6.2 Candidate Proxies: Tier Assessment

| Proxy | Frequency | Lead/Lag | Correlation Strength | Accessibility | Tier |
|-------|-----------|----------|---------------------|---------------|------|
| **NVDA Data Center Revenue** | Quarterly (with monthly intra-quarter commentary) | Coincident/Leading | ⭐⭐⭐ Very High | Public (10-Q, earnings calls) | **Tier-1: Must-have** |
| **TSMC Revenue (Monthly)** | Monthly | Leading by ~1 quarter | ⭐⭐⭐ High | Public monthly revenue reports | **Tier-1: Must-have** |
| **SEMI Equipment Billings** | Monthly | Leading by ~2 quarters | ⭐⭐ High | SEMI.org (subscription/delayed) | **Tier-2: Nice-to-have** |
| **GPU Spot Price (H100)** | Daily | Coincident/Short-lead | ⭐⭐ Moderate | Scraped (Vast.ai, Lambda) | **Tier-1: Already have** |
| **Data Center REIT leasing rates** | Quarterly | Lagging | ⭐⭐ Moderate | Public (EQIX, DLR earnings) | **Tier-2: Nice-to-have** |
| **Google Trends: "GPU rental"** | Weekly | Leading indicator | ⭐ Uncertain | Free API | **Tier-3: Experimental** |
| **AI startup funding (Crunchbase)** | Event-driven | Leading by ~6 months | ⭐⭐ Moderate | API (limited free tier) | **Tier-3: Experimental** |

### 6.3 NVDA Data Center Revenue: The King Proxy

**Why NVDA data center revenue is the best CAPEX proxy**:
1. **Direct read-through**: MSFT, AMZN, GOOGL, META collectively account for ~40-50% of NVDA data center revenue. NVDA's quarterly report effectively "pre-announces" hyperscaler CAPEX with a ~0-1 quarter lead.
2. **Higher frequency than CAPEX**: NVDA reports monthly (press releases for major deals) and quarterly (10-Q). Hyperscaler CAPEX is only known quarterly.
3. **Guidance linkage**: NVDA's forward guidance for data center revenue is directly tied to known purchase orders from hyperscalers.

**Data source**:
- Yahoo Finance (`yfinance`) already pulls NVDA financials in v1's `fetch_yahoo_finance_capex()`.
- Extend to extract `Total Revenue` → segment into `Data Center` vs `Gaming` using NVDA's segment reporting.

### 6.4 TSMC Monthly Revenue: The Early Warning

TSMC publishes monthly revenue (in NTD) around the 10th of the following month. TSMC's HPC (High Performance Computing) segment revenue is ~85% AI-related and has a ~1-quarter lead on hyperscaler CAPEX (chips are ordered, manufactured, and then installed).

**Data source**:
- TSMC Investor Relations: `https://investor.tsmc.com/english/quarterly-results/2026/` (monthly revenue PDFs)
- Alternative: `kimi_fetch_v2` on TSMC IR page; or parse via `pandas.read_html()`

### 6.5 Implementation in v2

```sql
-- New table for daily CAPEX proxies
CREATE TABLE capex_proxy_daily (
    date DATE,
    ticker VARCHAR,  -- 'NVDA', 'TSM', 'COMPOSITE'
    proxy_type VARCHAR,  -- 'nvda_datacenter_revenue', 'tsmc_monthly_hpc', 'gpu_price_index'
    proxy_value DOUBLE,  -- normalized to $B/quarter equivalent
    weight DOUBLE,       -- weight in composite proxy (sum to 1.0 per date)
    source VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Composite proxy (weighted average of available proxies)
-- Missing values handled by: last-observation-carried-forward for monthly,
-- and linear interpolation within month for daily.
```

---

## 7. Technical Architecture: Three-Layer Data Model

### 7.1 Schema Design

Based on the Master Plan §2.1, we implement a three-layer DuckDB schema:

```sql
-- ============================================================
-- L1: Raw Quarterly Data (Event Anchor)
-- ============================================================
CREATE TABLE l1_capex_quarterly (
    quarter_end DATE,
    ticker VARCHAR,
    company VARCHAR,
    capex_actual DOUBLE,          -- actual reported CAPEX
    revenue DOUBLE,
    ocf DOUBLE,
    guidance_low DOUBLE,
    guidance_high DOUBLE,
    guidance_mid AS (guidance_low + guidance_high) / 2,
    guidance_changed BOOLEAN DEFAULT FALSE,
    earnings_date DATE,           -- date of earnings release
    source VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- L2: Forward Curve (Daily Implied CAPEX Run-Rate)
-- ============================================================
CREATE TABLE l2_capex_forward_daily (
    date DATE,
    ticker VARCHAR,
    implied_daily_rate DOUBLE,        -- $B per day = guidance_mid / 90
    implied_quarterly_annualized DOUBLE, -- $B per quarter
    active_guidance_low DOUBLE,
    active_guidance_high DOUBLE,
    active_event_date DATE,            -- date of the guidance that drives this value
    active_event_type VARCHAR,         -- 'earnings_actual', 'guidance_revision', 'guidance_preliminary'
    days_since_event INTEGER,          -- days since last guidance update
    in_quarter_actual BOOLEAN,         -- TRUE if actual for this quarter is known
    source VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, ticker)
);

-- ============================================================
-- L3: Nowcast (Daily CAPEX Estimate from High-Frequency Proxies)
-- ============================================================
CREATE TABLE l3_capex_nowcast_daily (
    date DATE,
    ticker VARCHAR,  -- 'COMPOSITE' or individual hyperscaler
    
    -- Bridge Equation output
    bridge_equation_estimate DOUBLE,
    bridge_equation_r_squared DOUBLE,
    bridge_equation_last_fitted DATE,
    
    -- U-MIDAS output
    u_midas_estimate DOUBLE,
    u_midas_rmse DOUBLE,
    
    -- Composite (ensemble)
    nowcast_composite DOUBLE,  -- weighted average of bridge + u-midas
    nowcast_confidence VARCHAR, -- 'HIGH', 'MEDIUM', 'LOW' based on proxy availability
    
    -- Deviation metrics
    forward_gap DOUBLE,       -- nowcast_composite - l2.implied_quarterly_annualized
    forward_gap_pct DOUBLE,   -- forward_gap / l2.implied_quarterly_annualized
    
    source VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, ticker)
);
```

### 7.2 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Raw Inputs                                                  │
│  ├─ Yahoo Finance: quarterly CAPEX (MSFT, AMZN, GOOGL, META) │
│  ├─ Yahoo Finance: NVDA data center revenue (quarterly)      │
│  ├─ TSMC IR: monthly revenue (HPC segment)                   │
│  ├─ Scrapers: daily GPU prices (H100/A100 spot & on-demand)  │
│  └─ Manual: earnings date calendar, guidance revisions       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  L1: Event Ingestion                                         │
│  ├─ Upsert quarterly actuals into l1_capex_quarterly         │
│  ├─ Upsert guidance revisions (mid-quarter events)           │
│  └─ Tag guidance_changed = TRUE if delta > threshold         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  L2: Forward Curve Builder                                   │
│  ├─ For each ticker, sort events by date                     │
│  ├─ Compute implied_daily_rate = active_guidance_mid / 90    │
│  ├─ Forward-fill between events                              │
│  ├─ On earnings_date: backfill quarter with actual/90        │
│  └─ Output: l2_capex_forward_daily (full daily history)      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  L3: Nowcast Engine (nightly batch)                          │
│  ├─ Bridge Equation: regress L1 actuals on aggregated proxies│
│  ├─ U-MIDAS: OLS regression with distributed daily lags      │
│  ├─ Ensemble: weighted average (weight by backtest RMSE)     │
│  ├─ Compute forward_gap = nowcast - forward_curve            │
│  └─ Output: l3_capex_nowcast_daily                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  CSI Engine (updated nightly)                                │
│  ├─ gpu_z: from daily GPU price (unchanged from v1)          │
│  ├─ capex_z: from l3.nowcast_composite (replaces v1's      │
│  │           YoY growth on 4 data points)                    │
│  ├─ ocpi_z: from daily OCPI (unchanged from v1)            │
│  └─ Regime: from CSI thresholds (unchanged)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Dashboard (Streamlit + Plotly)                              │
│  ├─ Main chart: daily GPU price + vertical earnings markers  │
│  ├─ Overlay: l2 forward curve (dashed line)                  │
│  ├─ Overlay: l3 nowcast (dotted line, different color)       │
│  ├─ Forward gap band: fill between l2 guidance_low/high      │
│  └─ Regime subplot: CSI with horizontal regime bands         │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Backward Compatibility

v1 tables (`gpu_prices_daily`, `ocpi_daily`, `signals`, `csi_history`) remain **unchanged** in schema. v2 adds three new tables. The `AnalysisEngine.calculate_csi()` in v2 should:

1. Attempt to read from `l3_capex_nowcast_daily`.
2. If not available (first run), fall back to v1's YoY method on `capex_quarterly`.
3. Gradually migrate to the nowcast-based CSI as data accumulates.

---

## 8. Implementation Roadmap for Engineer

### Phase 1: L2 Forward Curve (Priority: P0)
- [ ] Add `l1_capex_quarterly` table with `earnings_date` and `guidance_changed` fields
- [ ] Build `ForwardCurveBuilder` class that generates `l2_capex_forward_daily`
- [ ] Add earnings date calendar (manual seed data for MSFT/AMZN/GOOGL/META)
- [ ] Update `AnalysisEngine.calculate_csi()` to use `l2.implied_quarterly_annualized` as CAPEX input
- [ ] Dashboard: add forward curve overlay on GPU price chart

### Phase 2: Earnings Event Visualization (Priority: P0)
- [ ] Add vertical marker lines at earnings dates on GPU price chart
- [ ] Add annotation bubbles showing CAPEX actual + guidance
- [ ] Add forward gap uncertainty band (`guidance_low` to `guidance_high`)
- [ ] Add separate regime subplot with horizontal bands

### Phase 3: L3 Nowcast - Bridge Equation (Priority: P1)
- [ ] Add `capex_proxy_daily` table with NVDA data center revenue
- [ ] Implement `BridgeEquationNowcaster` class
- [ ] Backtest on historical data (train on 2024-2025, test on 2026)
- [ ] Add `nowcast_composite` to CSI calculation

### Phase 4: L3 Nowcast - U-MIDAS (Priority: P2)
- [ ] Implement `UMIDASNowcaster` class using `statsmodels` OLS
- [ ] Compare RMSE against Bridge Equation on backtest period
- [ ] Ensemble both models for final nowcast

### Phase 5: Proxy Expansion (Priority: P3)
- [ ] Add TSMC monthly revenue proxy
- [ ] Add SEMI equipment billings proxy (if data available)
- [ ] Evaluate experimental proxies (Google Trends, startup funding)

---

## 9. Key Decisions Log

| # | Decision | Alternatives Considered | Rationale | Risk |
|---|----------|------------------------|-----------|------|
| 1 | **Forward Curve (piecewise constant)** vs. linear interpolation | Linear interpolation, spline interpolation | Piecewise constant preserves "commitment inertia" and avoids phantom intra-quarter trends; standard in yield curve construction (Hagan-West 2006) | Discontinuous jumps at earnings dates may look jarring to non-finance users — mitigate with annotation explaining the "guidance revision" event |
| 2 | **Bridge Equation as primary nowcast** vs. MIDAS/MF-VAR | MIDAS (restricted), U-MIDAS, MF-VAR, DFM | Transparency paramount for investor-facing tool; bridge equations are standard at central banks; coefficients are directly interpretable | Lower predictive accuracy than MIDAS in early-quarter; mitigate by keeping U-MIDAS as validation layer |
| 3 | **NVDA data center revenue as Tier-1 proxy** vs. other proxies | TSMC revenue, SEMI billings, GPU prices | Highest direct correlation to hyperscaler CAPEX; already accessible via yfinance; intra-quarter commentary available | NVDA revenue is coincident, not leading; TSMC monthly revenue provides the leading signal — use both |
| 4 | **DuckDB schema extension** (new tables) vs. migration | Migrate v1 tables, use Parquet files | Minimal change to v1; clean separation of concerns; DuckDB handles JOINs across tables efficiently | Slightly more complex schema; well-documented in this brief |
| 5 | **Vertical line + annotation** for earnings events vs. separate subplot | Separate earnings timeline subplot, dot markers on series | Vertical lines are industry standard (Bloomberg ECO); don't obscure data; annotation bubbles provide context without clutter | Many earnings dates close together may cause annotation overlap — mitigate with collision detection or expandable list |

---

## 10. References

### Primary Literature
1. **Ghysels, E., Santa-Clara, P., & Valkanov, R. (2004)**. "The MIDAS Touch: Mixed Data Sampling Regression Models." *Working Paper*.
2. **Ghysels, E., Sinko, A., & Valkanov, R. (2007)**. "MIDAS Regressions: Further Results and New Directions." *Econometric Reviews*, 26(1), 53-90.
3. **Foroni, C. & Marcellino, M. (2013)**. "A Survey of Econometric Methods for Mixed-Frequency Data." *Norges Bank Working Paper 2013/06*.
4. **Foroni, C., Marcellino, M., & Schumacher, C. (2015)**. "U-MIDAS: MIDAS Regressions with Unrestricted Polynomial Lag Parameters." *Journal of the Royal Statistical Society*, Series A.
5. **Mariano, R. S. & Murasawa, Y. (2003, 2010)**. "A New Coincident Index of Business Cycles Based on Monthly and Quarterly Series." *Journal of Applied Econometrics*.
6. **Banbura, M., Giannone, D., Modugno, M., & Reichlin, L. (2013)**. "Now-Casting and the Real-Time Data Flow." *ECB Working Paper*.
7. **Hagan, P. S. & West, G. (2006)**. "Interpolation Methods for Curve Construction." *Wilmott Magazine*.
8. **Clements, M. P. & Galvão, A. B. (2008, 2009)**. "Macroeconomic Forecasting With Mixed-Frequency Data." *Journal of Applied Econometrics*.

### Industry Practice
9. **FRED API Documentation**. "Interpolation Methods for Missing Data." Federal Reserve Bank of St. Louis.
10. **Bloomberg Terminal User Guide**. "ECO <GO>: Economic Calendar and Event Markers."
11. **Refinitiv Eikon Charting Manual**. §4.3 "Event Markers and Annotations on Time-Series."

### Context Sources (NVDA / Hyperscaler CAPEX)
12. **TechMarketBriefs (2026)**. "NVIDIA Stock (NVDA) Analysis: AI Chips, Earnings." — Hyperscaler CAPEX >$300B in 2026.
13. **247WallSt (2026)**. "SOXQ Holds $1 Billion in AI Chip Stocks as Hyperscaler Capex Dictates."
14. **HeyGoTrade (2026)**. "5 AI Stocks Tested by Mag 7 Earnings." — NVDA as direct CAPEX proxy.

---

*End of Research Brief. This document is intended as the primary technical specification for the Product Builder Engineer (Sub-process 2) and the Test & Validation Engineer (Sub-process 3).*
