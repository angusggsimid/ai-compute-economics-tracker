# Phase 6 Investor Scenario Acceptance | 2026-07-11

## Final Assessment

| Item | Result |
|---|---|
| Product acceptance | **PASS** |
| Investment inflection readiness | **Observing / partial evidence** |
| Shareability | **Ready to share with explicit data-history caveats** |
| Formal product | `html_dashboard/ai_compute_economics_monitor.html` |
| As of | 2026-07-11 |

The product passes because it lets an investor distinguish observable facts from unavailable trend conclusions. It does not pass an AI compute inflection call because the fixed GPU panels still have only 3 valid days versus the 10-day chart threshold and 20-day inflection threshold.

## 60-Second Six-Question Test

| Core question | Visible answer | Evidence |
|---|---|---|
| 1. H100/H200/B200 matched-panel 7D/30D change? | **Not yet observable.** No price line is shown. | Each family has 3 valid daily observations; fixed chart threshold is 10; chart-ready panels are 0. |
| 2. Are lower prices accompanied by more offers and wider capacity? | **Cannot test simultaneous change yet.** The latest depth snapshot is observable. | H100: 56 offers, median `$2.90/GPU-h`, P25-P75 `$2.48-$3.12`; H200: 30 offers, median `$3.79`; B200: 13 offers, median `$5.89`. |
| 3. Are RunPod/Vast/GPUPerHour/cloud spreads converging? | **Not yet observable as a trend.** | Exact-config history is below threshold; official cloud remains VM-hour and is not mixed with GPU-hour. |
| 4. Did model output prices change, and did usage rise afterward? | **Price changes and usage direction are observable; causality is not confirmed.** | 16 material catalog change events are shown. OpenRouter complete-week 4W MA ends at 190.79 for tool calls and 123.83 for image processing, each rebased to 100. |
| 5. Are application commercialization signals repeatedly revised upward? | **No sustained revision is established.** | 26 distinct public ARR/adoption series; 0 positive revisions and 0 negative revisions. Repeated snapshots are excluded from revision counts. |
| 6. Are US/China cloud CAPEX, guidance or RPO broadly revised down? | **No broad negative revision is visible.** | Four comparable calendar-Q1 US CAPEX actuals are separated from Oracle FY2026 annual data. Meta guidance is `$125-$145B` versus prior `$115-$135B`; China rows preserve native CNY and context labels. |

## Traceability Test

### H100 Market Depth

| Layer | Trace |
|---|---|
| Dashboard row | `H100 · 56 offers · median $2.90 · P25-P75 $2.48-$3.12` |
| Canonical observation | `obs_a142b8b957eea61548fa1212` |
| Stable series | `ser_ce355c2884718786e80b` |
| Source | `gpuperhour-offers-h100` |
| Raw snapshot | `tracker_snapshots/market_facts/2026-07-11t092719z-gpuperhour-offers-h100.json` |
| Raw hash | `sha256:c42a8c2c9efdbea9d72b55c9ddd26090459bf72bf8a75deecf9a2d0fcd5d530e` |

### OpenRouter Demand

| Layer | Trace |
|---|---|
| Dashboard series | `Tool calls · 4W MA` through 2026-06-29 |
| Sample canonical observation | `obs_e7cc100b32c75ec688db6c04` |
| Stable series | `ser_ef70a36aa9728b713563` |
| Source | `openrouter-frontend-rankings-tool-call-count` |
| Raw snapshot | `tracker_snapshots/market_facts/2026-07-11t092719z-openrouter-frontend-rankings-tool-call-count.json` |
| Raw hash | `sha256:8a04dc4872a78e2194d7d10eac5cd277922eb4a3e568ea800fc47882032a829d` |

Every card, chart and table also exposes its exact DuckDB query, source tables, filters and metric definitions through the source action.

## Interaction And Visual Acceptance

| Check | Result |
|---|---|
| Portable artifact validation | Passed |
| Self-contained HTML packaging | Passed |
| 1440px desktop | Passed |
| 390px mobile | Passed; document width `390/390` |
| Source keyboard menu and modal | Passed |
| Demand legend recomputation | Passed: visible line paths changed `2 -> 1`; `aria-pressed` changed `true -> false` |
| Chart titles, axes and units | Passed for all 6 charts |
| Commercialization evidence cards | Passed; shown only inside Commitment, not duplicated at the top |
| Horizontal overflow | 0 |

## Adversarial Data Acceptance

The formal Phase 1-6 test set passed **68 tests, 0 failures**. It includes:

- zero and unavailable GPU prices;
- MIG versus full-GPU contamination;
- incomplete OpenRouter weeks;
- duplicate snapshots versus real value changes;
- insufficient exact-config history;
- changing-composition GPU aggregates;
- price decline without expanding depth;
- insufficient market breadth;
- public proxy history that cannot confirm an inflection;
- one-quarter CAPEX that cannot become a sequential trend;
- production database and seed isolation;
- dashboard scope, provenance and mixed-frequency restrictions.

## Required Investor Caveats

1. No H100/H200/B200 matched-panel price trend is currently qualified. The visible 3/10 bars are collection progress, not a market-price signal.
2. Available offer count is observable listing depth, not installed capacity or utilization.
3. AWS/Azure prices are VM-hour snapshots and are not normalized into neocloud GPU-hour prices.
4. OpenRouter is a public activity proxy, not official total token volume.
5. Catalog price changes are venue-level observations, not automatically vendor-wide official announcements.
6. Application commercialization has public initial observations but no qualified revision history.
7. CAPEX includes non-AI spending; company periods and units remain explicit.

## Scope Confirmation

The monitor ends at AI compute economics evidence. It does not ingest security prices, stock daily data, portfolio positions or trading returns, and it does not output buy/sell recommendations.
