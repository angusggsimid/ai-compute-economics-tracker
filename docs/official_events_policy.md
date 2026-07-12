# Official Events Policy

本文件定义 T5 官方 guidance / RPO / capacity comment 事件层的生产规则。

## 允许进入生产的事件

生产事件只接受 `data/manual_official_events.yml` 中的 source-backed YAML，并且每条事件必须同时具备：

| 字段 | 要求 |
|---|---|
| `source_url` | 官方 IR 页面、SEC filing、官方 earnings release 或公开 transcript 页面 |
| `announcement_date` | 官方披露日期 |
| `ticker` / `company` | 必须匹配 `company_config.py` |
| `event_type` | 只能是 `capex_guidance_range`、`capex_guidance_revision`、`rpo`、`capacity_comment`、`supply_constraint_comment`、`management_capacity_comment` |
| `metric` / `value` / `unit` | 数值事件必须有可入库数值；range 会拆成 low/high 等单值 observation |
| `source_excerpt` | 页面中能找到的短摘录，只用于证明该 YAML 行不是记忆值 |
| `collector_name` | 必须是 `manual_sourcebacked_yaml` |

## 快照与证明

Loader 每次运行都会重新抓取 `source_url`，保存原始页面到 `tracker_snapshots/official_events/`，并记录 `raw_payload_hash`。只有页面 HTTP 2xx 且页面文本能命中 `source_excerpt` 时，事件才会写入 `production_official_events`。

如果页面不可达、403/429、超时、或摘录未命中，YAML 不会被信任。该事件会进入 `rejected_events`，同时写入 `production_data_quality_events`。

## 失败原因

| reason / error_code | 含义 |
|---|---|
| `MISSING_SOURCE_PROOF` | 缺 `source_url`、`announcement_date`、`metric`、`unit`、`value`、`source_excerpt` 或 collector 不正确 |
| `SOURCE_UNAVAILABLE` | 官方页面重抓失败、403/429/5xx 或请求异常 |
| `SOURCE_PROOF_NOT_FOUND` | 页面可达，但短摘录没有出现在页面中 |
| `INVALID_EVENT_TYPE` | 事件类型不在白名单内 |
| `INVALID_EVENT_VALUE` | 数值或 range 不能转为数字 |
| `COMPANY_CONFIG_MISSING` / `COMPANY_TICKER_MISMATCH` | 公司配置缺失或 ticker/company 不匹配 |

## 当前官方候选

当前 YAML 覆盖 Meta、Alphabet、Oracle、Microsoft 四家公司。Meta、Alphabet、Oracle 的 IR 页面可能返回 Cloudflare/403/429；这类情况必须暴露为质量事件，不允许绕过，也不允许用计划里的样本值直接入库。Microsoft 页面当前可用时，可验证管理层 capacity / supply comment。
