# SEC CAPEX Actuals Mapping

本文档记录 T4 的官方 CAPEX actual 采集口径。生产主源是 SEC companyfacts API，不使用 yfinance 作为官方 CAPEX 主源。

## Source

| Item | Policy |
|---|---|
| API | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| Source type | `official` |
| Collection method | `sec_companyfacts_api` |
| User-Agent | 必须带清楚的应用名和联系邮箱；默认值为 `AI-Compute-Scarcity-Tracker/2.0 contact: agg@example.com`，可用 `SEC_USER_AGENT` 覆盖 |
| Snapshot | 每次采集保存到 `tracker_snapshots/sec_capex/`，保留原始 SEC JSON、选中的 raw fact、raw value、raw unit 和 hash |
| Storage boundary | `production_capex_actuals.capex_value` 存十亿美元，`unit='USD_B'`；原始 SEC value/unit 只保存在 snapshot |

## Company Tag Mapping

映射来自 `company_config.py`，collector 不硬编码公司宇宙。

| Ticker | CIK | XBRL tag |
|---|---:|---|
| MSFT | `0000789019` | `PaymentsToAcquirePropertyPlantAndEquipment` |
| AMZN | `0001018724` | `PaymentsToAcquireProductiveAssets` |
| GOOGL | `0001652044` | `PaymentsToAcquirePropertyPlantAndEquipment` |
| META | `0001326801` | `PaymentsToAcquirePropertyPlantAndEquipment` |
| ORCL | `0001341439` | `PaymentsToAcquirePropertyPlantAndEquipment` |

## Stored Fields

`CapexActualObservation` 写入以下关键字段：

| Field | Meaning |
|---|---|
| `ticker`, `company` | 公司标识 |
| `period_start`, `period_end` | SEC fact 的统计期 |
| `fiscal_period`, `fiscal_year` | 由 SEC `fy` / `fp` 生成，例如 `FY2026 Q3` 或 `FY2026` |
| `filed_at`, `accession_no`, `form_type` | SEC filing 元数据 |
| `xbrl_tag` | 来自 company config 的 CAPEX tag |
| `capex_value`, `unit` | 十亿美元口径，`unit='USD_B'` |
| `source_id`, `source_url`, `snapshot_path`, `raw_payload_hash` | CIK/tag/source/snapshot/hash provenance |

## Selection Rule

1. 只读取公司配置中的 CAPEX XBRL tag。
2. 对同一公司展开 tag 下所有 units 和 facts。
3. 必须有 `start/end/val/accn/fy/fp/form/filed` 才可进入候选。
4. 选择最新 `period_end`；若同一 `period_end` 同时有季度和 YTD，优先季度 duration。
5. ORCL 这类最新可用为 FY fact 的公司，可写入 FY actual，但不会伪装成季度趋势。

## Failure Codes

| Code | Trigger | Behavior |
|---|---|---|
| `SEC_TAG_NOT_FOUND` | companyfacts 中找不到配置 tag | 不写 actual，写 `production_data_quality_events` |
| `SEC_SOURCE_UNAVAILABLE` | SEC HTTP 403/429/请求失败/无效 JSON | 不写 fabricated record，写 quality event 和 error snapshot |
| `SEC_PERIOD_AMBIGUOUS` | 找到 tag 但缺 period/value/filing 字段 | 不写 actual，写 quality event |

## Trend Boundary

T4 只暴露 `sequential_quarter_count` 和 `can_evaluate_trend`。至少 4 个连续季度才允许后续模块判断 acceleration/deceleration；本 collector 不输出趋势方向，不写投资判断。
