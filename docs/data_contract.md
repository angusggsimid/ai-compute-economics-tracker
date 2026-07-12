# tracker_v2 Production Data Contract

本文件定义 T1 生产数据合同。旧 raw 表继续保留给 demo、回归测试和兼容查询使用；生产判断、生产报告和后续 dashboard 默认只能读取 `production_*` 表或基于它们的 view。

## 表策略

保留 legacy raw tables：

| 表 | 用途 |
|---|---|
| `gpu_prices_daily` | 旧 GPU 价格与 seed/demo 数据 |
| `capex_quarterly` | 旧 CAPEX 季度数据 |
| `ocpi_daily` | 旧 OCPI/demo 数据 |
| `capex_guidance` | 旧 CAPEX guidance/demo 数据 |
| `capex_daily_implied` | 旧派生 L2 forward curve |
| `capex_nowcast` | 旧派生 L3 nowcast |

新增 canonical production tables：

| 表 | 用途 |
|---|---|
| `production_gpu_prices` | 真实 GPU 报价观测 |
| `production_capex_actuals` | SEC 或官方 CAPEX actual |
| `production_official_events` | 官方公告、RPO、guidance 等事件 |
| `production_public_proxy_prices` | 允许来源下的公开代理价格或指数 |
| `production_data_quality_events` | 数据质量、阻塞和异常事件 |
| `production_pipeline_runs` | 每次生产采集或验证运行记录 |

## 统一 provenance 字段

所有 `production_*` 表必须包含以下字段：

| 字段 | 要求 |
|---|---|
| `run_id` | 本次采集、导入或验证运行 ID |
| `source_id` | 规范化来源 ID |
| `source_url` | 可追溯 URL；不可用来源也要写明政策或来源页 |
| `snapshot_path` | 本地快照路径或手工 source-backed 文件路径 |
| `source_type` | 只允许 `official`、`public_pricing_page`、`aggregator`、`manual_verified`、`licensed_unavailable` |
| `collection_method` | 只允许 `sec_companyfacts_api`、`html_parse`、`embedded_json_parse`、`manual_sourcebacked_yaml`、`unavailable_marker` |
| `observed_at` | 数据对应的观察时间 |
| `fetched_at` | 本地抓取或导入时间 |
| `raw_payload_hash` | 原始 payload 或快照的确定性 hash |
| `is_production_eligible` | 是否允许进入生产判断 |
| `confidence` | 0 到 1 之间的置信度 |
| `error_code` | 质量异常码；正常可为空 |

生产写入统一经过 `validate_production_provenance()`。`source_type='seed'` 或 `source_type='mock'` 会被拒绝，并抛出 `PRODUCTION_SOURCE_TYPE_REJECTED`。

## 确定性 upsert key

| 表 | upsert key |
|---|---|
| `production_gpu_prices` | `(date, provider, gpu_model, gpu_variant, billing_type, commitment, gpu_count, region, source_url)` |
| `production_capex_actuals` | `(ticker, period_start, period_end, fiscal_period, xbrl_tag, accession_no)` |
| `production_official_events` | `(ticker, announcement_date, event_type, metric, source_url)` |
| `production_public_proxy_prices` | `(date, provider, proxy_name, metric, source_url)` |
| `production_data_quality_events` | `(event_id)` |
| `production_pipeline_runs` | `(run_id)` |

GPU key 必须保留 `provider`、`gpu_variant`、`gpu_count` 和 `source_url`，避免同一天 RunPod、Lambda、ComputePrices 的 H100 行互相覆盖。

## 查询规则

生产查询入口必须只读 `production_*`，不能在没有生产数据时回退到 legacy seed/demo 行。当前 T1 提供的 `Database.get_production_gpu_prices()` 只读取 `production_gpu_prices`。

`python3 tracker_v2.py status` 会输出：

1. legacy 与 production 表的行数和最新日期。
2. `source_type data quality counts`，其中 legacy 表按 `source` 字段归类，空来源显示为 `legacy_unclassified`。

如果 schema 初始化失败，CLI 必须暴露 `SCHEMA_MIGRATION_FAILED` 并非零退出。
