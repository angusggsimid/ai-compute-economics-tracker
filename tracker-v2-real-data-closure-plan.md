# Plan: tracker_v2 Real-Data Decision Product Closure

**Generated**: 2026-07-05  
**Project**: `/Users/agg/Documents/New project 2/tracker_v2`  
**Recommended executor**: `$parallel-task`  
**Do not use by default**: `super-swarm`, because this product has shared database/schema dependencies and real-data quality gates.

## Overview

目标不是继续做 dashboard 外壳，而是一次性把 `tracker_v2` 做成可用的数据决策产品：

1. L1 只接真实、可追溯数据；seed/mock/reference price 只能在 demo/test 模式出现。
2. GPU 价格、CAPEX actual、CAPEX guidance/RPO、OCPI/替代指数各自保留频率与口径，不再混成一个伪精确加权分数。
3. 产品输出的第一屏先回答：当前证据支持“算力稀缺溢价消退”吗？证据强度如何？缺口在哪里？
4. 每条生产数据必须能追到 `source_url`、`observed_at`、`fetched_at`、`source_type`、`collection_method`、`confidence`。
5. 失败时必须暴露失败，不允许用 fallback/mock/硬编码值伪装成功。

## Current Reality

当前数据库状态确认：

| Table | Current issue |
|---|---|
| `gpu_prices_daily` | 300 条 `seed_data` + 11 条 `direct_pricing`，其中 `direct_pricing` 实际来自代码硬编码 `reference_prices` |
| `capex_quarterly` | 28 条全部为 `seed_data` |
| `ocpi_daily` | 300 条 `seed_data` + 1 条 `composite_public`，其中 `composite_public` 是硬编码 |
| `capex_guidance` | 10 条全部为 `seed_guidance` |
| `capex_daily_implied` / `capex_nowcast` | 从 seed/guidance 派生，不能作为生产判断 |

因此本计划的完成标准是：生产命令和报告默认不再消费上述 seed/hardcoded 数据。

## Verified Real Data Samples

以下样本只用于定义验收，不代表代码可继续硬编码这些值。实现必须实时抓取或从 source-backed snapshot 生成。

| Layer | Source | Real sample verified on 2026-07-05 | URL |
|---|---|---|---|
| GPU price | RunPod official pricing | H100 PCIe `$2.89/hr`; H100 SXM `$3.29/hr`; H100 NVL `$3.19/hr`; H200 `$4.39/hr`; B200 `$5.89/hr`; B300 `$7.39/hr` | https://www.runpod.io/pricing |
| GPU price | Lambda official pricing | H100 1-click cluster: 16 GPUs `$6.16/hr`, 64 GPUs `$5.85/hr`, 256 GPUs `$5.54/hr`; H100 SXM instance `$3.99/hr`; H100 PCIe 1x `$3.29/hr`; B200 SXM6 8x `$6.69/hr` | https://lambda.ai/pricing |
| GPU price index | ComputePrices H100 | H100 SXM page: "from `$0.067/hr`", across 38 providers; examples include Verda `$0.067/hr` on 2026-06-30, Microsoft Azure `$1.14/hr` on 2026-07-05, Hyperbolic `$1.40/hr` on 2026-07-04 | https://computeprices.com/gpus/h100 |
| GPU price index | ComputePrices H200 | H200 page: "from `$0.076/hr`", across 28 providers; examples include Verda `$0.076/hr` on 2026-06-30, fal.ai `$1.40/hr` on 2026-07-05 | https://computeprices.com/gpus/h200 |
| CAPEX actual | SEC companyfacts, MSFT CIK 0000789019 | `PaymentsToAcquirePropertyPlantAndEquipment`, FY2026 Q3, 2026-01-01 to 2026-03-31, value `$30.876B`, filed 2026-04-29 | https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json |
| CAPEX actual | SEC companyfacts, AMZN CIK 0001018724 | `PaymentsToAcquireProductiveAssets`, FY2026 Q1, 2026-01-01 to 2026-03-31, value `$44.203B`, filed 2026-04-30 | https://data.sec.gov/api/xbrl/companyfacts/CIK0001018724.json |
| CAPEX actual | SEC companyfacts, GOOGL CIK 0001652044 | `PaymentsToAcquirePropertyPlantAndEquipment`, FY2026 Q1, 2026-01-01 to 2026-03-31, value `$35.674B`, filed 2026-04-30 | https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json |
| CAPEX actual | SEC companyfacts, META CIK 0001326801 | `PaymentsToAcquirePropertyPlantAndEquipment`, FY2026 Q1, 2026-01-01 to 2026-03-31, value `$18.997B`, filed 2026-04-30 | https://data.sec.gov/api/xbrl/companyfacts/CIK0001326801.json |
| CAPEX actual | SEC companyfacts, ORCL CIK 0001341439 | `PaymentsToAcquirePropertyPlantAndEquipment`, FY2026 FY, 2025-06-01 to 2026-05-31, value `$55.663B`, filed 2026-06-22 | https://data.sec.gov/api/xbrl/companyfacts/CIK0001341439.json |

## Prerequisites

- Network access for public pages and SEC API.
- Existing dependencies: `duckdb`, `pandas`, `numpy`, `requests`, `beautifulsoup4` if added, `streamlit`, `plotly`, `pytest`.
- SEC requests must use a compliant `User-Agent`.
- Any source that requires paid access, login, Bloomberg, ORNN, or Terms-restricted scraping must be marked unavailable or manual-verified; it must not be silently synthesized.

## Dependency Graph

```text
T1 ── T1.5 ── T2 ──┬── T3 ──┬── T6 ── T7 ── T8 ── T9 ── T11 ── T12 ── T10 ── T13
                   │        │
                   ├── T4 ──┤
                   │        │
                   └── T5 ──┘

T14 ───────────────┬── T3
                   ├── T4
                   ├── T5
                   └── T6
```

## Tasks

### T1: Define Production Data Contract And Provenance Schema

- **depends_on**: []
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/data_contract.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_data_contract.py`
- **description**:
  - Add a production data contract before adding collectors.
  - Use one explicit schema strategy, not optional alternatives:
    - Keep legacy raw tables for compatibility.
    - Add canonical production tables/views and provenance tables: `production_gpu_prices`, `production_capex_actuals`, `production_official_events`, `production_public_proxy_prices`, `production_data_quality_events`, `production_pipeline_runs`.
    - Existing dashboard queries may read compatibility views, but production decisions may only read `production_*`.
  - All production rows must include:
    - `run_id`
    - `source_id`
    - `source_url`
    - `snapshot_path`
    - `source_type` in `official`, `public_pricing_page`, `aggregator`, `manual_verified`, `licensed_unavailable`
    - `collection_method` in `sec_companyfacts_api`, `html_parse`, `embedded_json_parse`, `manual_sourcebacked_yaml`, `unavailable_marker`
    - `observed_at`
    - `fetched_at`
    - `raw_payload_hash`
    - `is_production_eligible`
    - `confidence`
    - `error_code`
  - Define one central function that rejects production inserts with `source_type in ('seed', 'mock')`.
  - Define deterministic upsert keys before any collector writes:
    - GPU: `(date, provider, gpu_model, gpu_variant, billing_type, commitment, gpu_count, region, source_url)`
    - CAPEX actual: `(ticker, period_start, period_end, fiscal_period, xbrl_tag, accession_no)`
    - official event: `(ticker, announcement_date, event_type, metric, source_url)`
- **data sources**:
  - No external data pull in this task.
  - Uses existing table reality: `seed_data`, `seed_guidance`, `direct_pricing`, `composite_public`.
- **real data sample**:
  - Current local DB: `gpu_prices_daily` has `seed_data=300`, `direct_pricing=11`; `capex_quarterly` has `seed_data=28`.
- **validation**:
  - `python3 -m pytest test_suite/test_data_contract.py -q` passes.
  - A production insert with `source_type='seed'` fails with a clear error.
  - `python3 tracker_v2.py status` shows data quality counts by `source_type`.
  - Test proves same-day RunPod, Lambda, and ComputePrices H100 rows all remain after upsert.
  - Test proves production queries read `production_*` only and ignore seed-only legacy rows.
- **failure exposure**:
  - If schema migration fails, CLI prints `SCHEMA_MIGRATION_FAILED` and exits non-zero.
  - If old rows lack provenance, status prints `legacy_unclassified` and production report refuses to use them.
- **status**: Completed
- **log**:
  - 2026-07-05: T1 RED added `test_suite/test_data_contract.py`; first run failed on missing production contract imports (`ProductionDataContractError`, `PRODUCTION_TABLES`, provenance fields), confirming current gap.
  - 2026-07-05: Implemented production schema in `tracker_v2.py`: six `production_*` tables, `production_gpu_prices_current` view, shared provenance guard rejecting `seed/mock`, deterministic upsert keys, production GPU query, status source_type counts, and `SCHEMA_MIGRATION_FAILED` exposure.
  - 2026-07-05: T1 GREEN passed `python3 -m pytest test_suite/test_data_contract.py -q` with 6 passed; compatibility check passed `python3 -m pytest test_suite/test_unit.py test_suite/test_integration.py -q` with 41 passed; `python3 tracker_v2.py status` shows source_type data quality counts.
  - 2026-07-05: reason_not_committed: target files are all untracked in the parent Git repo, including pre-existing copied files such as `tracker_v2.py`; committing would add whole baseline files rather than an isolated T1 diff, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/data_contract.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_data_contract.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T1.5: Create Integration Surface For Parallel Workers

- **depends_on**: [T1]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/__init__.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/company_config.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/production_store.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_integration_surface.py`
- **description**:
  - Add the shared interface that all later workers must use, so T2/T3/T4/T5 do not independently edit the same CLI and insert logic.
  - Define dataclasses or typed dictionaries for:
    - `GpuPriceObservation`
    - `CapexActualObservation`
    - `OfficialEventObservation`
    - `DataQualityEvent`
    - `PipelineRun`
  - Add production insert APIs:
    - `ProductionStore.insert_gpu_prices()`
    - `ProductionStore.insert_capex_actuals()`
    - `ProductionStore.insert_official_events()`
    - `ProductionStore.insert_quality_events()`
  - Add company config for MSFT, AMZN, GOOGL, META, ORCL:
    - ticker,
    - company name,
    - CIK,
    - fiscal year end convention,
    - CAPEX XBRL tag,
    - whether included in decision universe.
  - Add CLI skeleton commands without collector internals:
    - `update --production --only ...`
    - `validate-data --production`
    - `report --production`
    - `status --quality`
- **data sources**:
  - No external data pull in this task.
- **real data sample**:
  - Company config must include ORCL with CIK `0001341439` and tag `PaymentsToAcquirePropertyPlantAndEquipment`.
- **validation**:
  - `python3 -m pytest test_suite/test_integration_surface.py -q` passes.
  - Later collectors can be added without modifying core insert/upsert methods.
  - `python3 tracker_v2.py update --production --only gpu-prices` returns a clear `NOT_IMPLEMENTED_COLLECTOR` until T3 fills it.
- **failure exposure**:
  - Missing company config emits `COMPANY_CONFIG_MISSING`.
  - Unknown `--only` value emits allowed values and exits non-zero.
- **status**: Completed
- **log**:
  - 2026-07-05: T1.5 RED added `test_suite/test_integration_surface.py`; first run failed with 7 failures covering missing `production_store`, missing `company_config`, and missing production CLI skeleton.
  - 2026-07-05: Implemented shared integration surface without external collection: production observation dataclasses, `ProductionStore` wrapper over T1 `Database.insert_production_*`, MSFT/AMZN/GOOGL/META/ORCL company config, production update/validate/report/status CLI skeleton, and allowed production update target registry.
  - 2026-07-05: T1.5 GREEN passed `python3 -m pytest test_suite/test_integration_surface.py -q` with 7 passed; T1 compatibility passed `python3 -m pytest test_suite/test_data_contract.py -q` with 6 passed.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` baseline and prior T1/T14 files as untracked; committing now would capture unrelated copied baseline and parallel worker changes, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/__init__.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/company_config.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/production_store.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_integration_surface.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T2: Separate Demo Seed Mode From Production Mode

- **depends_on**: [T1.5]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_seed_isolation.py`
- **description**:
  - Change `cmd_init()` so default `init` creates schema only and does not load seed data.
  - Move current seed loader behind an explicit command or flag: `python3 tracker_v2.py init --demo-seed`.
  - Add `python3 tracker_v2.py reset-production-db --confirm-real-data-reset` or a safer equivalent that clears production tables only after explicit confirmation.
  - Ensure `cmd_update()` never calls hardcoded pricing/OCPI methods.
- **data sources**:
  - Local current seed rows are the negative control.
- **real data sample**:
  - Existing bad sample to isolate: `CAPEXRecord(... capex=37.5, source='seed_data')` for MSFT 2026-03-31.
- **validation**:
  - Fresh `python3 tracker_v2.py init` creates empty production tables and no `seed_data`.
  - `python3 tracker_v2.py init --demo-seed` still supports tests/demo, clearly labeled.
  - `python3 tracker_v2.py report` refuses to produce investment conclusion when only seed/demo rows exist.
- **failure exposure**:
  - If no real data exists, CLI prints `NO_PRODUCTION_DATA` with next command suggestions.
  - Dashboard top banner shows `Production data unavailable`, not neutral/green.
- **status**: Completed
- **log**:
  - 2026-07-05: T2 RED added `test_suite/test_seed_isolation.py`; first run failed with 5 failures covering default `init` loading seed rows, missing `init --demo-seed`, missing `reset-production-db`, default `cmd_update()` calling hardcoded demo collectors, and production report not failing seed-only databases.
  - 2026-07-05: Implemented seed isolation in `tracker_v2.py`: default `init` is schema-only, legacy seed loader moved behind explicit `init --demo-seed`, default `update` refuses legacy hardcoded collectors unless `--demo` is passed, production report returns `NO_PRODUCTION_DATA` for empty production DB and `FAIL_SEED_ONLY` for legacy/demo-only DBs, and `reset-production-db --confirm-real-data-reset` clears only `production_*` tables.
  - 2026-07-05: Updated `README_v2.md` to separate production commands from DEMO ONLY seed/update/dashboard usage.
  - 2026-07-05: T2 GREEN passed `python3 -m pytest test_suite/test_seed_isolation.py -q` with 5 passed; compatibility passed `python3 -m pytest test_suite/test_integration_surface.py test_suite/test_data_contract.py -q` with 13 passed.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` and surrounding project files as untracked, with prior T1/T1.5/T14 worker changes already in the worktree; committing now would capture baseline/unrelated worker changes rather than an isolated T2 diff, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_seed_isolation.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T3: Build GPU Pricing Source Adapters

- **depends_on**: [T2, T14]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/gpu_pricing.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_gpu_pricing_sources.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/gpu_prices/`
- **description**:
  - Replace `fetch_gpu_price_from_providers()` hardcoded `reference_prices`.
  - Implement adapters:
    - RunPod official HTML parser.
    - Lambda official HTML parser.
    - ComputePrices parser for H100/H200/B200 pages. Prefer embedded structured data if available; otherwise parse stable text rows and store raw snapshot.
  - Normalize output fields:
    - `provider`
    - `gpu_model`
    - `gpu_variant`
    - `billing_type`
    - `commitment`
    - `gpu_count`
    - `price_per_gpu_hour`
    - `region`
    - `availability_observed`
    - provenance fields from T1.
  - Do not collapse official provider quotes and aggregator quotes into one average. Store both; decision layer chooses aggregation.
  - ComputePrices rows are aggregator evidence, not market truth. Each row must retain provider, quote date, quote age, GPU variant, availability if present, and whether it is allowed into the decision layer. The page-level "from price" cannot become the market median.
- **data sources**:
  - https://www.runpod.io/pricing
  - https://lambda.ai/pricing
  - https://computeprices.com/gpus/h100
  - https://computeprices.com/gpus/h200
- **real data sample**:
  - RunPod official: H100 PCIe `$2.89/hr`, H100 SXM `$3.29/hr`, H100 NVL `$3.19/hr`, H200 `$4.39/hr`, B200 `$5.89/hr`, B300 `$7.39/hr`.
  - Lambda official: H100 cluster 16 GPUs `$6.16/hr`, 64 GPUs `$5.85/hr`, 256 GPUs `$5.54/hr`; H100 SXM instance `$3.99/hr`; H100 PCIe 1x `$3.29/hr`.
  - ComputePrices H100: from `$0.067/hr`, 38 providers.
  - ComputePrices H200: from `$0.076/hr`, 28 providers.
- **validation**:
  - `python3 -m pytest test_suite/test_gpu_pricing_sources.py -q` passes with saved HTML fixtures.
  - Live `python3 tracker_v2.py update --only gpu-prices` inserts at least:
    - 3 RunPod rows,
    - 3 Lambda rows,
    - 5 ComputePrices H100 rows,
    - 3 ComputePrices H200 rows,
    - unless source is unavailable, in which case a data quality event is inserted.
  - Inserted rows have non-empty `source_url`, `observed_at`, `fetched_at`, `raw_payload_hash`.
  - Test fixture requires each real sample to produce `source_url`, `snapshot_path`, `raw_payload_hash`, and `fetched_at`.
- **failure exposure**:
  - If a page layout changes, parser emits `GPU_SOURCE_PARSE_FAILED` with source URL and snapshot path.
  - If a source times out, row is not synthesized; `data_quality_events` records `SOURCE_TIMEOUT`.
- **status**: Completed
- **log**:
  - 2026-07-05: T3 RED added `test_suite/test_gpu_pricing_sources.py` plus saved parser fixtures; first run failed with `ModuleNotFoundError: No module named 'data_sources.gpu_pricing'`, confirming the missing GPU pricing source adapter.
  - 2026-07-05: Implemented `data_sources/gpu_pricing.py`: RunPod official HTML parser, Lambda official HTML parser, ComputePrices H100/H200 aggregator parser, raw HTML/error snapshot saving, `sha256` raw payload hashes, `SOURCE_TIMEOUT` and `GPU_SOURCE_PARSE_FAILED` quality events, and `ProductionStore` insertion helper.
  - 2026-07-05: Added minimal production CLI wiring for `python3 tracker_v2.py update --production --only gpu-prices` without changing T4/T5 handlers. Existing skeleton test now checks remaining unimplemented `public-proxy-prices` instead of the newly implemented GPU target.
  - 2026-07-05: Live update succeeded: `python3 tracker_v2.py update --production --only gpu-prices` processed 145 parsed observations and wrote snapshots under `tracker_snapshots/gpu_prices/`; production table currently has RunPod 6 rows, Lambda 22 rows, ComputePrices H100 63 rows, ComputePrices H200 37 rows, and 0 GPU pricing quality events.
  - 2026-07-05: T3 GREEN passed `python3 -m pytest test_suite/test_gpu_pricing_sources.py -q` with 8 passed; regression passed `python3 -m pytest test_suite/test_seed_isolation.py test_suite/test_integration_surface.py test_suite/test_data_contract.py -q` with 18 passed.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` baseline and parallel worker outputs as untracked; T4/T5 also modified shared CLI/test surfaces during this run, so committing now would capture unrelated baseline/worker changes rather than an isolated T3 diff.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/gpu_pricing.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_gpu_pricing_sources.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/gpu_pricing/runpod_pricing.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/gpu_pricing/lambda_pricing.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/gpu_pricing/computeprices_h100.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/gpu_pricing/computeprices_h200.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_integration_surface.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/gpu_prices/2026-07-05t073615z-runpod-pricing.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/gpu_prices/2026-07-05t073615z-lambda-pricing.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/gpu_prices/2026-07-05t073615z-computeprices-h100.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/gpu_prices/2026-07-05t073615z-computeprices-h200.html`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T4: Build Official SEC CAPEX Actuals Collector

- **depends_on**: [T2, T14]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/sec_capex.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_sec_capex.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/sec_capex_mapping.md`
- **description**:
  - Replace production dependence on `yfinance` for CAPEX actuals.
  - Use SEC companyfacts as primary official source for US-listed hyperscalers.
  - Maintain company-specific XBRL tag mapping:
    - MSFT: `PaymentsToAcquirePropertyPlantAndEquipment`
    - AMZN: `PaymentsToAcquireProductiveAssets`
    - GOOGL: `PaymentsToAcquirePropertyPlantAndEquipment`
    - META: `PaymentsToAcquirePropertyPlantAndEquipment`
    - ORCL: `PaymentsToAcquirePropertyPlantAndEquipment`
  - Use company config from T1.5; do not hardcode a four-company hyperscaler universe.
  - Preserve fiscal period, start/end dates, filing date, accession number, and unit.
  - Convert to `$B` only at storage boundary with original raw value retained in provenance/raw snapshot.
- **data sources**:
  - SEC companyfacts API for CIKs:
    - MSFT `0000789019`
    - AMZN `0001018724`
    - GOOGL `0001652044`
    - META `0001326801`
    - ORCL `0001341439`
- **real data sample**:
  - MSFT FY2026 Q3 quarter cash capex: `$30.876B`.
  - AMZN FY2026 Q1 quarter productive assets: `$44.203B`.
  - GOOGL FY2026 Q1 cash capex: `$35.674B`.
  - META FY2026 Q1 cash capex: `$18.997B`.
  - ORCL FY2026 full-year cash capex: `$55.663B`.
- **validation**:
  - `python3 -m pytest test_suite/test_sec_capex.py -q` passes.
  - Live update inserts at least one latest official actual for each of MSFT, AMZN, GOOGL, META, ORCL.
  - Each inserted record includes SEC URL, CIK, tag, accession number, filed date.
  - AMZN uses `PaymentsToAcquireProductiveAssets`, not the wrong PP&E tag.
  - Trend calculations require at least four quarters per company. With fewer than four quarters, product may display actuals but must not call acceleration/deceleration.
- **failure exposure**:
  - Missing company tag emits `SEC_TAG_NOT_FOUND`.
  - SEC HTTP 403/429 emits `SEC_SOURCE_UNAVAILABLE`, stores no fabricated record, and suggests retry interval.
- **status**: Completed
- **log**:
  - 2026-07-05: T4 RED added `test_suite/test_sec_capex.py` plus saved SEC companyfacts JSON fixtures; first run failed with `ModuleNotFoundError: No module named 'data_sources.sec_capex'`, confirming missing collector.
  - 2026-07-05: Implemented `data_sources/sec_capex.py`: SEC companyfacts client with compliant User-Agent, company-config-driven CIK/tag mapping, snapshot/hash writing under `tracker_snapshots/sec_capex/`, latest official actual parsing, `$B` storage boundary, raw SEC JSON/value preservation, `SEC_TAG_NOT_FOUND` and `SEC_SOURCE_UNAVAILABLE` quality events, and quarter-count trend availability without acceleration/deceleration labels.
  - 2026-07-05: Added minimal CLI wiring for `python3 tracker_v2.py update --production --only capex-actuals`; other production targets remain `NOT_IMPLEMENTED_COLLECTOR` for T3/T5/T6 workers.
  - 2026-07-05: T4 GREEN passed `python3 -m pytest test_suite/test_sec_capex.py -q` with 7 passed; compatibility passed `python3 -m pytest test_suite/test_seed_isolation.py test_suite/test_integration_surface.py test_suite/test_data_contract.py -q` with 18 passed.
  - 2026-07-05: Live SEC update passed: `python3 tracker_v2.py update --production --only capex-actuals` inserted 5 official CAPEX actuals and 0 quality events for MSFT/AMZN/GOOGL/META/ORCL; snapshots were saved in `tracker_snapshots/sec_capex/`.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` and broader project files as untracked, with prior parallel worker changes already in the worktree; committing now would capture baseline/unrelated worker changes rather than an isolated T4 diff, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/sec_capex.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_sec_capex.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/sec_companyfacts/MSFT.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/sec_companyfacts/AMZN.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/sec_companyfacts/GOOGL.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/sec_companyfacts/META.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/fixtures/sec_companyfacts/ORCL.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/sec_capex_mapping.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/sec_capex/AMZN_0001018724_2026-07-05T07-35-44Z_ab593c88c663.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/sec_capex/GOOGL_0001652044_2026-07-05T07-35-44Z_c883f5d0fdc9.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/sec_capex/META_0001326801_2026-07-05T07-35-44Z_8d5e8e7185b8.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/sec_capex/MSFT_0000789019_2026-07-05T07-35-44Z_7d8f8f997f2e.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/sec_capex/ORCL_0001341439_2026-07-05T07-35-44Z_cf7cb9e13f6d.json`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`
  - `/Users/agg/Documents/New project 2/CONTEXT.md`

### T5: Build Official Guidance And RPO Event Layer

- **depends_on**: [T2, T14]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/official_events.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data/manual_official_events.yml`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/official_events_policy.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_official_events.py`
- **description**:
  - Create an event ingestion layer for CAPEX guidance, RPO/backlog, and management comments.
  - Use source-backed YAML/JSON as acceptable production input only when every value has:
    - official URL,
    - announcement date,
    - company,
    - metric,
    - value/range,
    - unit,
    - short source excerpt under copyright limits,
    - collector name `manual_sourcebacked_yaml`.
  - Later HTML/PDF parsers can automate these official pages, but this task must make the product useful immediately without fabricating guidance.
  - Store event types separately:
    - `capex_guidance_range`
    - `capex_guidance_revision`
    - `rpo`
    - `capacity_comment`
    - `supply_constraint_comment`
- **data sources**:
  - Official investor relations pages, SEC filings, earnings releases, and transcripts if public.
  - Examples to seed manually only if source-backed:
    - Microsoft investor earnings pages.
    - Meta investor earnings releases.
    - Alphabet investor earnings releases.
    - Oracle investor releases/10-K.
- **real data sample**:
  - Meta official investor release: 2026 capex guidance range `$125B-$145B`, increased from `$115B-$135B`; event type `capex_guidance_revision`; source candidate `https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-First-Quarter-2026-Results/default.aspx`.
  - Alphabet official Q1 2026 earnings call page: FY2026 capex guidance updated to `$180B-$190B`, up from `$175B-$185B`; event type `capex_guidance_revision`; source candidate `https://abc.xyz/investor/events/event-details/2026/2026-Q1-Earnings-Call-2026-nW8kCrBAKS/default.aspx`.
  - Oracle official Q4 FY2026 results: RPO `$638B`, up 363% year-over-year and up `$85B` sequentially; event type `rpo`; source candidate `https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Record-Q4-and-FY-2026-Results-Driven-by-Cloud-Infrastructure--Cloud-Applications/default.aspx`.
  - Microsoft official Q2 FY2026 earnings page: capex `$37.5B`, roughly two-thirds short-lived assets primarily GPUs and CPUs, customer demand exceeds supply; event type `management_capacity_comment`; source candidate `https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q2`.
  - Implementation must re-fetch and snapshot these official pages before accepting them. Unverified memory values are not allowed.
- **validation**:
  - `python3 -m pytest test_suite/test_official_events.py -q` passes.
  - Loader rejects any event without `source_url`, `announcement_date`, `metric`, `unit`, and `value`.
  - `python3 tracker_v2.py update --only official-events` loads only source-backed events.
  - At least three event types are represented if sources are reachable: `capex_guidance_revision`, `rpo`, and `management_capacity_comment`.
- **failure exposure**:
  - If an event lacks proof, it is moved to `rejected_events` with reason `MISSING_SOURCE_PROOF`.
  - Dashboard displays "official guidance missing" rather than inventing range.
- **status**: Completed
- **log**:
  - 2026-07-05: T5 RED added `test_suite/test_official_events.py` and source-backed `data/manual_official_events.yml`; first run failed with missing `data_sources.official_events` and `official-events` CLI still returning `NOT_IMPLEMENTED_COLLECTOR`.
  - 2026-07-05: Implemented official event loader in `data_sources/official_events.py`: validates required source proof fields, supports `capex_guidance_range`, `capex_guidance_revision`, `rpo`, `capacity_comment`, `supply_constraint_comment`, and `management_capacity_comment`, expands numeric ranges into production observations, re-fetches official pages, writes snapshots/hashes, and moves missing/unreachable/unverified rows to rejected events plus production data quality events.
  - 2026-07-05: Added `docs/official_events_policy.md` documenting required fields, snapshot/proof policy, failure reasons, and blocked-source behavior.
  - 2026-07-05: Added minimal CLI wiring for `python3 tracker_v2.py update --production --only official-events`; T3/T4 CLI branches were already present, so this only added the official-events branch and left other collectors unchanged.
  - 2026-07-05: T5 GREEN passed `python3 -m pytest test_suite/test_official_events.py -q` with 5 passed. Regression passed `python3 -m pytest test_suite/test_seed_isolation.py test_suite/test_integration_surface.py test_suite/test_data_contract.py -q` with 18 passed.
  - 2026-07-05: Live CLI verification passed `python3 tracker_v2.py update --production --only official-events`: Microsoft official page produced 2 source-backed production events (`capacity_comment`, `management_capacity_comment`); Meta, Alphabet, and Oracle candidate pages returned unavailable/blocked responses and were written as `SOURCE_UNAVAILABLE` quality events with saved snapshots. No blocked page value was inserted as production data.
  - 2026-07-05: Added a narrow parent `.gitignore` exception so `tracker_v2/data/manual_official_events.yml` is not hidden by the global `data/` ignore rule.
  - 2026-07-05: Updated parent `CONTEXT.md` with T5 completion status, live verification result, and validation summary.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` and surrounding project baseline as untracked, and T3/T4 changes are already present in the shared worktree; committing now would capture baseline/unrelated parallel worker files rather than an isolated T5 diff, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/official_events.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data/manual_official_events.yml`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/official_events_policy.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_official_events.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_integration_surface.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/official_events/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`
  - `/Users/agg/Documents/New project 2/.gitignore`
  - `/Users/agg/Documents/New project 2/CONTEXT.md`

### T6: Replace OCPI Hardcode With Licensed-Unavailable And Public Proxy Policy

- **depends_on**: [T3, T14]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/ocpi_policy.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_ocpi_policy.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/ocpi_policy.md`
- **description**:
  - Remove hardcoded `fetch_ocpi_public()`.
  - Treat ORNN/OCPI as a licensed or externally unavailable source unless a real authorized feed is configured.
  - Create separate public proxy series from ComputePrices, named clearly as `public_gpu_price_proxy`, not OCPI.
  - Do not show OCPI in production report unless source is authorized and live.
- **data sources**:
  - ORNN/OCPI: unavailable unless configured.
  - ComputePrices H100/H200 as public proxy only.
- **real data sample**:
  - ComputePrices H100 from `$0.067/hr`, 38 providers.
  - ComputePrices H200 from `$0.076/hr`, 28 providers.
- **validation**:
  - `python3 -m pytest test_suite/test_ocpi_policy.py -q` passes.
  - No row with `source='composite_public'` is created in production.
  - Report includes `OCPI unavailable` and `public_gpu_price_proxy available` as separate lines.
- **failure exposure**:
  - If OCPI env/config missing, create `DATA_SOURCE_UNAVAILABLE` quality event.
  - No fallback value is inserted.
- **status**: Completed
- **log**:
  - 2026-07-05: T6 RED added `test_suite/test_ocpi_policy.py`; first run failed with `ModuleNotFoundError: No module named 'data_sources.ocpi_policy'`, confirming the missing OCPI/public proxy policy layer.
  - 2026-07-05: Implemented `data_sources/ocpi_policy.py`: OCPI licensed-unavailable quality marker, ComputePrices-derived `public_gpu_price_proxy` rows from existing `production_gpu_prices` aggregator rows, transparent row_count/min/median proxy metrics, and no fallback OCPI value insertion.
  - 2026-07-05: Added `PublicProxyPriceObservation` and `ProductionStore.insert_public_proxy_prices()` as a thin wrapper over T1 schema; did not change production table schema.
  - 2026-07-05: Wired `python3 tracker_v2.py update --production --only public-proxy-prices`; CLI/status/report now show `OCPI unavailable` separately from `public_gpu_price_proxy available/unavailable`. The legacy `fetch_ocpi_public()` function is explicitly marked demo/legacy only.
  - 2026-07-05: Added `docs/ocpi_policy.md` documenting that ComputePrices proxy is not OCPI, not market median, and must retain source URL, snapshot, hash, and aggregator provenance.
  - 2026-07-05: T6 GREEN passed `python3 -m pytest test_suite/test_ocpi_policy.py -q` with 4 passed; regression passed `python3 -m pytest test_suite/test_gpu_pricing_sources.py test_suite/test_seed_isolation.py test_suite/test_integration_surface.py test_suite/test_data_contract.py -q` with 26 passed.
  - 2026-07-05: Live update passed: `python3 tracker_v2.py update --production --only public-proxy-prices` inserted 84 `public_gpu_price_proxy` rows from T3 ComputePrices H100/H200 aggregator rows and 1 `DATA_SOURCE_UNAVAILABLE` OCPI quality event; no production `composite_public` row was inserted.
  - 2026-07-05: Status verification passed: `python3 tracker_v2.py status --quality` shows `production_public_proxy_prices | aggregator | rows=84 | eligible=84`, `production_data_quality_events | licensed_unavailable | rows=1 | eligible=0`, plus separate `OCPI unavailable` and `public_gpu_price_proxy available` lines.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` baseline and parallel worker outputs as untracked, and T3/T4/T5/T14 changes are already present in the shared worktree; committing now would capture baseline/unrelated parallel worker files rather than an isolated T6 diff, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/data_sources/ocpi_policy.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_ocpi_policy.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/ocpi_policy.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/production_store.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_integration_surface.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T7: Add Pipeline Run, Snapshot, And Quality Gate System

- **depends_on**: [T3, T4, T5, T6]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/data_quality.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_data_quality.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/`
- **description**:
  - Add run-level tracking:
    - `pipeline_runs`
    - `data_quality_events`
    - raw HTML/JSON snapshots by source/date.
  - Add freshness and coverage checks before report/dashboard:
    - GPU price freshness: at least one source updated within 3 days.
    - CAPEX actual freshness: latest filing period exists for each covered company, or explicit missing status.
    - Guidance/RPO freshness: latest official event per company if available; otherwise missing status.
    - Seed ratio: production used rows must have `seed/mock = 0`.
  - Quality gate returns `PASS`, `WARN`, or `FAIL`.
- **data sources**:
  - All source outputs from T3/T4/T5.
- **real data sample**:
  - A passing GPU gate should include RunPod or Lambda rows with 2026-07-05 fetch time.
  - A passing CAPEX gate should include SEC samples from T4.
- **validation**:
  - `python3 -m pytest test_suite/test_data_quality.py -q` passes.
  - `python3 tracker_v2.py validate-data --production` returns non-zero on current copied DB because seed rows dominate.
  - After real update, validation returns PASS or WARN with explicit missing sources.
- **failure exposure**:
  - Validation output prints table-level reason codes, e.g. `SEED_ROWS_PRESENT`, `SOURCE_STALE`, `CAPEX_COMPANY_MISSING`, `GPU_PROVIDER_PARSE_FAILED`.
- **status**: Completed
- **log**:
  - 2026-07-05: Implemented `data_quality.py` quality gate with `PASS`/`WARN`/`FAIL`, run-level `production_pipeline_runs` snapshot helpers, quality-event helpers, production freshness/coverage checks, source failure reason table, and legacy seed warning isolation.
  - 2026-07-05: `python3 tracker_v2.py validate-data --production` now evaluates real production rows instead of printing collector skeleton status. Current real-data DB returns `quality_gate=WARN`, exit code 0, with explicit reasons for legacy rows ignored by production, missing official events for AMZN/GOOGL/META/ORCL, ORNN/OCPI unavailable, and blocked official-event sources.
  - 2026-07-05: GREEN passed `python3 -m pytest test_suite/test_data_quality.py -q` with 9 passed; source-regression suite passed `python3 -m pytest test_suite/test_ocpi_policy.py test_suite/test_gpu_pricing_sources.py test_suite/test_sec_capex.py test_suite/test_official_events.py -q` with 24 passed.
  - 2026-07-05: reason_not_committed: the worker stream disconnected before final response, but local validation passed; parent Git still treats `tracker_v2` baseline and parallel worker outputs as untracked, so committing now would capture baseline/unrelated files rather than an isolated T7 diff.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/data_quality.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_data_quality.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/pipeline_runs/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T8: Rebuild L1/L2/L3 Decision Logic Without Mixed-Frequency Weighted CSI

- **depends_on**: [T7]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/decision_engine.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_decision_engine.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/decision_framework.md`
- **description**:
  - Keep raw frequencies separate:
    - L1 actual/event layer: SEC CAPEX actuals, official guidance/RPO events.
    - L2 commitment layer: event-driven forward curve from guidance/actuals.
    - L3 market proxy layer: daily GPU price trend and public proxy breadth.
  - Demote existing `calculate_csi()` to legacy/demo only or mark as deprecated.
  - Replace final decision with gate-based state:
    - `No Signal`: data insufficient.
    - `Watch`: GPU price easing but CAPEX/guidance not confirming.
    - `Pressure Building`: price easing + proxy breadth weakening + no CAPEX acceleration.
    - `Scarcity Premium Cracking`: sustained price easing + official CAPEX/guidance/RPO deceleration or negative revisions.
    - `Scarcity Still Tight`: price firming or supply-constrained comments with rising CAPEX.
  - Add confidence based on data quality, source count, freshness, and cross-layer agreement.
  - Implement numeric trigger matrix:
    - GPU official price easing: median comparable H100 official quote down at least 10% over 30 days or at least 20% over 90 days.
    - Aggregator breadth weakening: ComputePrices comparable H100/H200 median down at least 15% over 30 days, with at least 8 current quotes and quote age under 14 days.
    - CAPEX acceleration/deceleration: QoQ and YoY only allowed when company has at least 4 sequential quarters; otherwise actuals are display-only.
    - Guidance revision: direction and percentage from official event layer; negative revisions are confirmation, positive revisions are counter-evidence.
    - RPO/backlog: deceleration requires comparable sequential or YoY data from official source; one standalone RPO value is display-only.
    - Official layer missing cap: without CAPEX actuals or official events, maximum decision state is `Watch`.
    - Price-only signal cap: if only GPU pricing layer passes, conclusion must be `Watch`, confidence no higher than 40%.
    - `Scarcity Premium Cracking` requires both market-price evidence and official CAPEX/guidance/RPO confirmation.
- **data sources**:
  - L1: SEC and official-events.
  - L3: RunPod, Lambda, ComputePrices.
  - OCPI only if authorized.
- **real data sample**:
  - GPU easing proxy sample: ComputePrices H100 "from `$0.067/hr`" and official H100 rows from RunPod/Lambda.
  - CAPEX actual sample: MSFT `$30.876B`, AMZN `$44.203B`, GOOGL `$35.674B`, META `$18.997B`.
- **validation**:
  - `python3 -m pytest test_suite/test_decision_engine.py -q` passes.
  - Decision engine refuses to emit `Scarcity Premium Cracking` if official CAPEX/guidance layer is missing.
  - Decision engine can emit `Watch` using GPU-only evidence with confidence capped.
  - No production report uses the old weighted CSI as primary conclusion.
  - Production mode does not write `csi_history`.
  - Dashboard and report do not display CSI as a primary metric in production; legacy CSI may appear only under `legacy_metrics/demo` with label `not used for production decision`.
- **failure exposure**:
  - Missing official layer appears as `CAPEX_CONFIRMATION_MISSING`.
  - Mixed-frequency weighted index appears only under `legacy_metrics`, never in `decision`.
- **status**: Completed
- **log**:
  - 2026-07-05: T8 RED added `test_suite/test_decision_engine.py`; first run failed with `ModuleNotFoundError: No module named 'decision_engine'`, confirming the missing production decision engine.
  - 2026-07-05: Implemented `decision_engine.py` with frequency-preserving L1/L2/L3 gates, numeric trigger matrix, price-only confidence cap, official missing cap, source references, quality gate attachment, and `legacy_metrics.csi.used_for_production_decision=False`.
  - 2026-07-05: Wired `python3 tracker_v2.py report --production` to print `source-backed decision` with `decision_state`, evidence, counter-evidence, missing data, source references, and legacy CSI label; production report does not call `calculate_csi()` or write `csi_history`.
  - 2026-07-05: Current real production DB reports `decision_state=No Signal`, `quality_gate=WARN`, and does not emit `Scarcity Premium Cracking` because official confirmation is insufficient and GPU/aggregator trends lack comparable history.
  - 2026-07-05: GREEN passed `python3 -m pytest test_suite/test_decision_engine.py -q` with 7 passed; source-regression suite passed `python3 -m pytest test_suite/test_data_quality.py test_suite/test_ocpi_policy.py test_suite/test_gpu_pricing_sources.py test_suite/test_sec_capex.py test_suite/test_official_events.py -q` with 33 passed; `python3 tracker_v2.py report --production` returned exit code 0 with source-backed decision state and no primary CSI.
  - 2026-07-05: reason_not_committed: parent Git still treats the whole project and `tracker_v2` baseline as untracked, with prior parallel worker changes already present; committing now would capture baseline/unrelated files rather than an isolated T8 diff.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/decision_engine.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_decision_engine.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/decision_framework.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T9: Update Report Generator Into Source-Backed Decision Brief

- **depends_on**: [T8]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/reports.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_report_quality.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/`
- **description**:
  - Rewrite report structure:
    1. Data quality verdict.
    2. Current decision state.
    3. GPU price evidence table.
    4. CAPEX actual/guidance/RPO evidence table.
    5. Missing data and failed sources.
    6. Investment implication by layer, not one blended number.
  - Every number in report must cite source URL or local snapshot path.
  - Report must not say tracker complete if data quality gate fails.
- **data sources**:
  - Outputs from T3/T4/T5/T6.
- **real data sample**:
  - Report should be able to display RunPod H100 PCIe `$2.89/hr` with source URL.
  - Report should be able to display SEC MSFT Q3 FY2026 capex `$30.876B` with CIK/tag/accession.
- **validation**:
  - `python3 -m pytest test_suite/test_report_quality.py -q` passes.
  - `python3 tracker_v2.py report --production` contains `source_url` or snapshot reference for every evidence row.
  - Current seed-only DB causes report to show FAIL, not a regime call.
- **failure exposure**:
  - If source citations are missing, report generation fails with `REPORT_UNCITED_VALUE`.
- **status**: Completed
- **log**:
  - 2026-07-05: T9 RED added `test_suite/test_report_quality.py`; first run failed with `ModuleNotFoundError: No module named 'reports'`, confirming the missing source-backed production report generator.
  - 2026-07-05: Added `reports.py` source-backed decision brief generator with required sections, source-citation validation, `REPORT_UNCITED_VALUE` failure, quality-gate FAIL blocking, seed-only FAIL/NO_PRODUCTION_DATA exposure, layer-by-layer implication, and legacy/demo-only CSI note.
  - 2026-07-05: Rewired `python3 tracker_v2.py report --production` to generate and print the source-backed brief, write it to `tracker_data/`, and exit non-zero when quality gate FAILs or uncited evidence is found.
  - 2026-07-05: Current real production DB report generated at `tracker_data/20260705T142101Z-production-source-backed-decision-brief.md`; it shows `quality_gate=WARN`, `decision_state=No Signal`, RunPod H100 PCIe `2.89/hr`, MSFT FY2026 Q3 CAPEX `30.876B`, source URLs, snapshots, missing official events, and failed source rows.
  - 2026-07-05: GREEN passed `python3 -m pytest test_suite/test_report_quality.py -q` with 4 passed; regression passed `python3 -m pytest test_suite/test_decision_engine.py test_suite/test_data_quality.py -q` with 16 passed; `python3 tracker_v2.py report --production` returned exit code 0 and wrote a production source-backed report file.
  - 2026-07-05: reason_not_committed: parent Git still treats the whole project and `tracker_v2` baseline as untracked, with prior parallel worker changes already present; committing now would capture baseline/unrelated files rather than an isolated T9 diff.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/reports.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_report_quality.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/20260705T142101Z-production-source-backed-decision-brief.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T10: Update Dashboard To Show Data Truth Before Charts

- **depends_on**: [T12]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/dashboard_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_dashboard_queries.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/dashboard_checklist.md`
- **description**:
  - First viewport must show:
    - data quality state,
    - decision state,
    - last successful run,
    - source coverage,
    - missing/failed sources.
  - Existing charts stay, but labels must distinguish:
    - official provider price,
    - aggregator price,
    - public proxy,
    - official CAPEX actual,
    - source-backed guidance.
  - Remove or demote top-line CSI metric from primary header.
- **data sources**:
  - Query production rows only by default.
- **real data sample**:
  - Header should show RunPod/Lambda/ComputePrices coverage if those adapters succeed.
  - CAPEX panel should show SEC actuals from T4.
- **validation**:
  - `python3 -m pytest test_suite/test_dashboard_queries.py -q` passes.
  - Streamlit loads against empty production DB and seed-only DB without showing false green.
  - Visual checklist confirms no primary metric is seed-derived.
- **failure exposure**:
  - Dashboard renders `No production data` state rather than charting seed rows.
- **status**: Completed
- **log**:
  - 2026-07-05: Added explicit database path support for production commands: every CLI subcommand now accepts `--db`, `AI_COMPUTE_TRACKER_DB` is honored, `Database()` resolves the active path at runtime, and `ProductionStore` no longer captures the legacy DB path at import time.
  - 2026-07-05: First T12 live attempt exposed a real path propagation bug: running `tracker_v2.py` as `__main__` let collector modules import a second `tracker_v2` module and write to the legacy default DB while validation read the new production DB. This was fixed by aliasing the running CLI module and propagating `--db` into `AI_COMPUTE_TRACKER_DB`.
  - 2026-07-05: Added regression coverage in `test_suite/test_production_database_path.py` proving explicit `--db` init does not create/touch the legacy DB, env-routed production store writes use the production DB, and late imports see the CLI DB override.
  - 2026-07-05: Built the independent production database `/Users/agg/Documents/New project 2/tracker_v2/ai_compute_tracker_production.db` and ran `python3 tracker_v2.py update --production --db ai_compute_tracker_production.db` successfully.
  - 2026-07-05: Final production DB row counts: `production_gpu_prices=128` (`public_pricing_page=28`, `aggregator=100`), `production_capex_actuals=5`, `production_official_events=2`, `production_public_proxy_prices=84`, `production_data_quality_events=4`, `production_pipeline_runs=4`; legacy/demo tables in the production DB remain empty (`gpu_prices_daily=0`, `capex_quarterly=0`, `ocpi_daily=0`, `csi_history=0`).
  - 2026-07-05: `python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` returned exit code 0 with `quality_gate=WARN`; explicit gaps are AMZN/GOOGL/META/ORCL official event coverage, ORNN/OCPI licensed feed unavailable, and source page 403s for META/GOOGL/ORCL.
  - 2026-07-05: `python3 tracker_v2.py report --production --db ai_compute_tracker_production.db` generated `tracker_data/20260705T143710Z-production-source-backed-decision-brief.md` with `decision_state=No Signal`, `cli_exit_semantics=WARN_CAPEX_CONFIRMATION_MISSING`, and no `Scarcity Premium Cracking` regime call.
  - 2026-07-05: Legacy `ai_compute_tracker.db` was not overwritten or reset. However, the first failed T12 attempt did touch its production tables before the path propagation bug was fixed; from this point production source of truth is the independent `ai_compute_tracker_production.db`, and README commands now require `--db ai_compute_tracker_production.db` or `AI_COMPUTE_TRACKER_DB`.
  - 2026-07-05: GREEN passed `python3 -m pytest test_suite/test_production_database_path.py -q` with 3 passed; `python3 -m pytest test_suite/test_cli_real_data.py test_suite/test_seed_isolation.py test_suite/test_integration_surface.py -q` with 18 passed; `python3 -m pytest test_suite/test_report_quality.py test_suite/test_decision_engine.py test_suite/test_data_quality.py -q` with 20 passed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/production_store.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_production_database_path.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_integration_surface.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/ai_compute_tracker_production.db`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/20260705T143710Z-production-source-backed-decision-brief.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T11: Update CLI Commands For One-Command Production Closure

- **depends_on**: [T9]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_cli_real_data.py`
- **description**:
  - Add or refine CLI:
    - `init` schema only.
    - `init --demo-seed` demo only.
    - `update --production` fetches GPU, SEC CAPEX, official events, OCPI/proxy policy, rebuilds L2/L3, validates data, writes report.
    - `validate-data --production`.
    - `report --production`.
    - `status --quality`.
  - Default user path should be:
    - `python3 tracker_v2.py init`
    - `python3 tracker_v2.py update --production`
    - `python3 tracker_v2.py validate-data --production`
    - `python3 tracker_v2.py report --production`
  - Define exit semantics:
    - `PASS`: exit 0 and may emit directional decision.
    - `WARN_CAPEX_CONFIRMATION_MISSING`: exit 0 for report generation, but report must say decision is blocked or max `Watch`; no regime call.
    - `WARN_GPU_ONLY`: exit 0 for data collection, but report confidence cap is 40% and no `Scarcity Premium Cracking`.
    - `FAIL`: exit non-zero and no investment conclusion.
    - `FAIL_SEED_ONLY`: exit non-zero and report only explains missing production data.
- **data sources**:
  - All production collectors.
- **real data sample**:
  - Production update should collect at least one GPU row and one SEC actual row if network is available.
- **validation**:
  - `python3 -m pytest test_suite/test_cli_real_data.py -q` passes.
  - Full command sequence exits 0 only under the defined PASS/WARN semantics, never when all data is seed/missing.
  - `WARN_CAPEX_CONFIRMATION_MISSING` can create an evidence report but cannot print a regime call.
- **failure exposure**:
  - CLI emits source-specific failure codes and exits non-zero on FAIL.
- **status**: Completed
- **log**:
  - 2026-07-05: T11 RED added `test_suite/test_cli_real_data.py`; first run failed with 3 failing tests because full `update --production` did not run validation/report and stopped after the first source failure instead of collecting all source-level failure codes.
  - 2026-07-05: Reworked `update --production` into one-command production closure: it now runs GPU pricing, SEC CAPEX actuals, official events, and OCPI/public proxy policy, prints a target summary, runs the production quality gate, generates a source-backed report, and exits from the final PASS/WARN/FAIL semantics.
  - 2026-07-05: Preserved `update --production --only ...` as single-target refresh/debug mode without full closure; invalid targets still print allowed values and exit non-zero.
  - 2026-07-05: Added CLI exit labels `PASS`, `WARN_CAPEX_CONFIRMATION_MISSING`, `WARN_GPU_ONLY`, `WARN`, `FAIL`, and `FAIL_SEED_ONLY`; WARN report output is capped so it does not emit `Scarcity Premium Cracking` as a CLI/report regime call.
  - 2026-07-05: Updated `README_v2.md` to separate real-data production path from demo seed path and document init/update/validate/report/status/reset commands plus exit semantics.
  - 2026-07-05: GREEN passed `python3 -m pytest test_suite/test_cli_real_data.py -q` with 6 passed; regression passed `python3 -m pytest test_suite/test_report_quality.py test_suite/test_decision_engine.py test_suite/test_data_quality.py -q` with 20 passed.
  - 2026-07-05: Live `python3 tracker_v2.py update --production` returned exit code 0 under WARN semantics, refreshed GPU rows (145 parsed observations / 132 production rows after upsert), SEC CAPEX actuals (5 rows), official events (2 MSFT rows plus 3 `SOURCE_UNAVAILABLE` quality events), public proxy rows (84 rows), ran quality gate, and generated `tracker_data/20260705T142741Z-production-source-backed-decision-brief.md`.
  - 2026-07-05: Live `python3 tracker_v2.py validate-data --production` returned exit code 0 with `quality_gate=WARN`; `python3 tracker_v2.py report --production` returned exit code 0 and generated a source-backed report; `python3 tracker_v2.py status --quality` returned exit code 0 and showed production/legacy source counts separately.
  - 2026-07-05: Live `python3 tracker_v2.py update --production --only gpu-prices` returned exit code 0, refreshed GPU rows, and did not trigger full validate/report closure.
  - 2026-07-05: reason_not_committed: parent Git still treats the whole `tracker_v2` baseline and prior parallel worker files as untracked, and this task also produced live DB/snapshot/report changes; committing now would capture unrelated baseline/generated files rather than an isolated T11 diff.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_cli_real_data.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/20260705T142741Z-production-source-backed-decision-brief.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/20260705T142748Z-production-source-backed-decision-brief.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/gpu_prices/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/sec_capex/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/official_events/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/pipeline_runs/`

### T12: Production Backfill And Database Rebuild

- **depends_on**: [T11]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/ai_compute_tracker_production.db`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_snapshots/`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/`
- **description**:
  - Rebuild the local production database from real sources.
  - Do not overwrite `ai_compute_tracker.db`.
  - Create new `ai_compute_tracker_production.db`.
  - If any future task needs to clear or replace an existing DB, it must first create timestamp backup and require explicit user confirmation.
  - Keep old seeded DB as demo/test artifact only; production commands must default to the production DB path or explicit `--db`.
  - Run production update and store source snapshots.
  - Generate one final production report.
- **data sources**:
  - T3/T4/T5/T6 outputs.
- **real data sample**:
  - Final DB should include:
    - RunPod H100 row,
    - Lambda H100 row,
    - ComputePrices H100 or H200 rows,
    - SEC CAPEX rows for MSFT/AMZN/GOOGL/META/ORCL or explicit failure events.
- **validation**:
  - `python3 tracker_v2.py status --quality` shows seed/mock rows excluded from production.
  - `python3 tracker_v2.py validate-data --production` passes or warns with explicit missing sources.
  - `python3 tracker_v2.py report --production` creates a source-backed report.
  - `ai_compute_tracker.db` remains unchanged unless user explicitly confirms a destructive reset.
- **failure exposure**:
  - If any source fails, quality event and report missing-data table show it.
- **status**: Completed
- **log**:
  - 2026-07-05: Rebuilt `dashboard_v2.py` as a production-first Streamlit dashboard. Default DB path is now `AI_COMPUTE_TRACKER_DB` or `ai_compute_tracker_production.db`; first viewport reads production data only and shows current decision, quality gate, confidence, production row count, source coverage, and missing/failed sources.
  - 2026-07-05: Removed the old first-screen CSI/regime positioning flow from the production dashboard. Legacy/demo table counts are now shown only in a separate `Legacy/demo not used` tab and are explicitly excluded from production decisions.
  - 2026-07-05: Added production charts/tables for GPU price evidence, SEC CAPEX actuals, official events and gaps, public GPU proxy/OCPI policy, and source-backed row-level provenance.
  - 2026-07-05: Added `test_suite/test_dashboard_queries.py`, covering empty production DB, seed-only DB, and source-backed production DB behavior. Seed-only and empty DBs show `quality_gate=FAIL` and `decision_state=Blocked`.
  - 2026-07-05: Replaced the old mock/CSI dashboard checklist with a production-first checklist in `test_suite/dashboard_checklist.md`.
  - 2026-07-05: GREEN passed `python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_production_database_path.py -q` with 6 passed; dashboard compile passed `python3 -m py_compile dashboard_v2.py`.
  - 2026-07-05: Live dashboard smoke passed: `AI_COMPUTE_TRACKER_DB=ai_compute_tracker_production.db python3 -m streamlit run dashboard_v2.py --server.port 8503 --server.address 127.0.0.1 --server.headless true` returned HTTP 200. Browser smoke with local Chrome verified first-screen text and saved screenshot `tracker_data/dashboard_v2_production_smoke.png`.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/dashboard_v2.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/test_dashboard_queries.py`
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/dashboard_checklist.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/dashboard_v2_production_smoke.png`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T13: End-To-End Test And Product Acceptance

- **depends_on**: [T10]
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/test_suite/`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/CONTEXT.md`
- **description**:
  - Run complete verification:
    - unit tests,
    - integration tests,
    - production data validation,
    - production report generation,
    - dashboard launch smoke test.
  - Update docs to describe real-data path and demo path separately.
  - Update project `CONTEXT.md` with result and remaining data gaps.
- **data sources**:
  - Final production DB and snapshots.
- **real data sample**:
  - Acceptance summary must include exact row counts by source and at least:
    - 3 GPU evidence rows with source URL/snapshot,
    - 5 CAPEX actual rows or explicit company-level missing reasons,
    - 1 official event row or explicit blocker,
    - current judgment,
    - confidence,
    - next monitoring variables.
- **validation**:
  - `python3 -m pytest test_suite/test_unit.py -q`
  - `python3 -m pytest test_suite/test_integration.py -q`
  - New tests from this plan pass.
  - Dashboard can start with `streamlit run dashboard_v2.py`.
- **failure exposure**:
  - Any failed test or missing source becomes an explicit final blocker, not buried in "next steps".
- **status**: Completed
- **log**:
  - 2026-07-05: End-to-end acceptance completed against `/Users/agg/Documents/New project 2/tracker_v2/ai_compute_tracker_production.db`.
  - 2026-07-05: Old baseline tests passed: `python3 -m pytest test_suite/test_unit.py -q` with 28 passed; `python3 -m pytest test_suite/test_integration.py -q` with 13 passed.
  - 2026-07-05: Real-data closure tests passed: `python3 -m pytest test_suite/test_data_contract.py test_suite/test_integration_surface.py test_suite/test_seed_isolation.py test_suite/test_gpu_pricing_sources.py test_suite/test_sec_capex.py test_suite/test_official_events.py test_suite/test_ocpi_policy.py test_suite/test_data_quality.py test_suite/test_decision_engine.py test_suite/test_report_quality.py test_suite/test_cli_real_data.py test_suite/test_production_database_path.py test_suite/test_dashboard_queries.py -q` with 74 passed.
  - 2026-07-05: Production validation passed under WARN semantics: `python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` exited 0 with `quality_gate=WARN`.
  - 2026-07-05: Production report generation passed: `python3 tracker_v2.py report --production --db ai_compute_tracker_production.db` exited 0 and generated `tracker_data/20260705T143710Z-production-source-backed-decision-brief.md`.
  - 2026-07-05: Dashboard smoke passed: Streamlit ran at `http://127.0.0.1:8503`, HTTP returned 200, browser smoke verified first-screen production text, and screenshot was saved to `tracker_data/dashboard_v2_production_smoke.png`.
  - 2026-07-05: Acceptance summary written to `tracker_data/20260705T144531Z-production-acceptance-summary.md` with row counts, 3 GPU samples, 5 CAPEX actuals, official events, current judgment, confidence, missing data, and next monitoring variables.
  - 2026-07-05: Current product result is useful but deliberately conservative: `decision_state=No Signal`, `confidence=15%`; the product does not claim `Scarcity Premium Cracking` because official trend history and multi-company guidance/RPO confirmation are missing.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker_data/20260705T144531Z-production-acceptance-summary.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/README_v2.md`
  - `/Users/agg/Documents/New project 2/CONTEXT.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

### T14: External Documentation And Parser Policy Check

- **depends_on**: []
- **location**:
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/external_source_notes.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/source_terms_checklist.md`
- **description**:
  - Document external-source assumptions before implementation finishes:
    - SEC companyfacts API usage and User-Agent.
    - Provider pricing pages and parser fragility.
    - ComputePrices as aggregator, not official price.
    - ORNN/OCPI unavailable unless licensed.
    - yfinance acceptable only as secondary comparison, not official CAPEX source.
  - If a source blocks scraping or terms are unclear, classify as `manual_verified` or `unavailable`, not silently scrape around controls.
- **data sources**:
  - SEC companyfacts docs.
  - RunPod/Lambda/ComputePrices public pages.
  - DuckDB/Streamlit docs for technical behavior.
- **real data sample**:
  - Include the verified sample table from this plan in the notes.
- **validation**:
  - Docs include source URL, access method, allowed use assumption, parser risk, fallback behavior.
- **failure exposure**:
  - Missing source policy blocks final acceptance.
- **status**: Completed
- **log**:
  - 2026-07-05: Created external source policy docs covering SEC companyfacts/User-Agent, RunPod/Lambda/ComputePrices parser policy, ComputePrices aggregator limits, ORNN/OCPI licensed-unavailable handling, yfinance secondary-only CAPEX policy, blocked-source fallback rules, and verified sample table caveat.
  - 2026-07-05: Static check passed: both docs exist and contain required source URLs, access methods, allowed-use assumptions, parser risks, fallback behavior, unavailable/manual_verified policy, and sample-table non-hardcode warning.
  - 2026-07-05: reason_not_committed: parent Git repo still treats `tracker_v2` files as untracked and this plan file contains parallel worker T1 updates; committing now would capture baseline/unrelated worker changes rather than an isolated T14 diff, so no stage/commit was performed.
- **files edited/created**:
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/external_source_notes.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/docs/source_terms_checklist.md`
  - `/Users/agg/Documents/New project 2/tracker_v2/tracker-v2-real-data-closure-plan.md`

## Parallel Execution Groups

| Wave | Tasks | Can Start When |
|---|---|---|
| 1 | T1, T14 | Immediately |
| 2 | T1.5 | T1 complete |
| 3 | T2 | T1.5 complete |
| 4 | T3, T4, T5 | T2 complete; all also require T14 |
| 5 | T6 | T3 and T14 complete |
| 6 | T7 | T3/T4/T5/T6 complete |
| 7 | T8 | T7 complete |
| 8 | T9 | T8 complete |
| 9 | T11 | T9 complete |
| 10 | T12 | T11 complete |
| 11 | T10 | T12 complete |
| 12 | T13 | T10 complete |

## Testing Strategy

Required commands before final acceptance:

```bash
cd /Users/agg/Documents/New\ project\ 2/tracker_v2
python3 -m pytest test_suite/test_unit.py -q
python3 -m pytest test_suite/test_integration.py -q
python3 -m pytest test_suite/test_data_contract.py -q
python3 -m pytest test_suite/test_seed_isolation.py -q
python3 -m pytest test_suite/test_gpu_pricing_sources.py -q
python3 -m pytest test_suite/test_sec_capex.py -q
python3 -m pytest test_suite/test_official_events.py -q
python3 -m pytest test_suite/test_ocpi_policy.py -q
python3 -m pytest test_suite/test_data_quality.py -q
python3 -m pytest test_suite/test_decision_engine.py -q
python3 -m pytest test_suite/test_report_quality.py -q
python3 -m pytest test_suite/test_dashboard_queries.py -q
python3 -m pytest test_suite/test_cli_real_data.py -q
python3 tracker_v2.py validate-data --production
python3 tracker_v2.py report --production
```

Dashboard smoke test:

```bash
streamlit run dashboard_v2.py
```

The final answer must report pass/fail counts only, plus explicit data gaps.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Provider pricing page layout changes | Save raw snapshots, add parser tests with fixtures, emit parse failure events |
| SEC tags differ by company | Maintain company-specific mapping and test AMZN separately |
| ORNN/OCPI not publicly accessible | Mark unavailable; use ComputePrices only as public proxy, not OCPI |
| Official guidance parsing is hard | Use source-backed manual YAML first, with strict proof requirements |
| Mixed-frequency index creates false confidence | Replace primary CSI with gate-based decision state |
| Seed data leaks into production | Production insert guard + report quality gate + validation test |
| Dashboard hides data failures | First viewport must show data quality and missing sources |

## Completion Bar

This plan is complete only when:

1. Production report can be generated from real source-backed rows.
2. Seed/mock/reference rows are not consumed by production decision/report/dashboard.
3. Every displayed number has a source URL or snapshot path.
4. GPU price, CAPEX actual, guidance/RPO, and OCPI/proxy are clearly separated by frequency and source quality.
5. The product gives a minimum useful judgment, or explicitly says why judgment is blocked.
6. Tests and validation commands pass, or failures are reported as blockers with exact reason codes.
