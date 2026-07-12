# Source Terms Checklist

本清单用于实现前检查。每个生产来源都必须有 source URL、access method、allowed-use assumption、parser risk、fallback behavior。若任一项不能确认，来源状态必须降级为 `manual_verified` 或 `unavailable`。

## Checklist

| Source | Source URL | Access method | Allowed-use assumption | Parser risk | Fallback behavior |
|---|---|---|---|---|---|
| SEC companyfacts API | https://www.sec.gov/search-filings/edgar-application-programming-interfaces; endpoint `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | HTTPS JSON API with compliant `User-Agent`; `collection_method=sec_companyfacts_api` | 官方公开 API 可用于公司事实数据采集；必须遵守 SEC fair access、限速和 User-Agent 要求 | CIK 需补零；CAPEX tag 公司差异大；QTD/YTD/FY period 容易误选；403/429 不代表数据不存在 | 403/429/timeout 记录 `SEC_SOURCE_UNAVAILABLE`; tag 缺失记录 `SEC_TAG_NOT_FOUND`; 不写 fabricated CAPEX |
| SEC fair access and User-Agent | https://www.sec.gov/os/webmaster-faq; https://data.sec.gov/ | Request policy check before collector runs | User-Agent 必须清楚标识应用和联系方式；请求要限速 | 默认 UA、空 UA、过高并发会被限制 | 停止本轮 SEC 采集，写 quality event；等待重试，不绕过 |
| RunPod official pricing | https://www.runpod.io/pricing | Public page fetch; prefer embedded structured data; otherwise stable visible text/table parse; save raw HTML snapshot | 公共定价页可作为官方供应商价格 evidence；不代表成交价、库存或所有地区 | 页面前端渲染、class 改名、GPU variant/commitment/region 混淆 | 记录 `PRICING_SOURCE_UNAVAILABLE` 或 `PARSER_SCHEMA_CHANGED`; 不用 reference price 补齐 |
| Lambda official pricing | https://lambda.ai/pricing | Public page fetch; prefer embedded structured data; otherwise stable visible text/table parse; save raw HTML snapshot | 公共定价页可作为官方供应商价格 evidence；cluster、instance、reserved/on-demand 要分开 | 1-click cluster、instance、GPU count、commitment、region 容易混用；页面结构会变 | 部分字段缺失则 `is_production_eligible=false`; 关键字段缺失写 quality event |
| ComputePrices H100 | https://computeprices.com/gpus/h100 | Public aggregator page fetch; parse provider rows and quote metadata; save raw HTML snapshot | 只能作为 aggregator/public proxy，不是官方市场真实价格 | `from price` 是页面低价入口或最低价线索，不是 market median；provider row 可能缺 date、region、availability | 记录 `AGGREGATOR_SOURCE_UNAVAILABLE` 或 `AGGREGATOR_SCHEMA_CHANGED`; 不替代 RunPod/Lambda 官方报价 |
| ComputePrices H200 | https://computeprices.com/gpus/h200 | Public aggregator page fetch; parse provider rows and quote metadata; save raw HTML snapshot | 只能作为 aggregator/public proxy，不是官方市场真实价格 | 样本 provider 可能非等价 GPU variant；quote age 过旧会污染趋势 | 不足 quote count 或 quote age 超阈值时，只保留 raw evidence，不进入 decision layer |
| ComputePrices B200 | https://computeprices.com/gpus/b200 | Public aggregator page fetch; parse provider rows and quote metadata; save raw HTML snapshot | 只能作为 aggregator/public proxy，用于 breadth check 或辅助 proxy | B200 供应商覆盖可能少，价格可能受促销、区域和容量约束影响 | 页面不可用则标记 unavailable；不能用 H100/H200 外推 B200 |
| ORNN / OCPI | https://www.ornn.ai/; distribution reference https://www.ice.com/insights/conversations/inside-the-ice-house/ornn-ais-nicholas-chapados-on-the-gpu-market-and-compute-financing | No production access without licensed feed; authorized feed only if configured | 没有授权 feed 时不可采集；OCPI 不是公共网页可自由复刻的数据 | 截图、新闻文字或历史报告无法提供可审计 daily series | `source_type=licensed_unavailable`, `collection_method=unavailable_marker`; 报告显示 `OCPI unavailable` |
| Public GPU price proxy from ComputePrices | https://computeprices.com/gpus/h100; https://computeprices.com/gpus/h200; https://computeprices.com/gpus/b200 | Aggregator row parse after snapshot | 可作为 `public_gpu_price_proxy`，不能命名为 OCPI | proxy 与 OCPI 口径不同；聚合样本不等于市场全体 | 与 OCPI 分开展示；proxy 缺失时显示 proxy unavailable |
| yfinance | https://github.com/ranaroussi/yfinance | Python package for secondary comparison only | 最多作为 Yahoo Finance public-facing data 的 secondary comparison 或 sanity check | 非官方 CAPEX feed；字段口径、回溯、segment 粒度和可用性不稳定 | 不写 `source_type=official`; 与 SEC 冲突时以 SEC/company filing 为准 |
| DuckDB docs | https://duckdb.org/docs/ | Local database/query behavior reference | 技术文档可用于确认存储、事务和查询行为 | 不是市场数据来源；不能提高来源可信度 | 数据缺 provenance 时拒绝 production eligibility |
| Streamlit docs | https://docs.streamlit.io/ | UI behavior reference for warnings/errors/status display | 技术文档可用于确认页面如何暴露错误 | 不是市场数据来源；UI 可能把空状态误显示为正常 | 数据缺失、来源失败、OCPI 未授权时显示 warning/error，不显示 false green |

## Hard Blocks

1. ComputePrices 是 aggregator，不是官方市场真实价格。页面级 `from price` 不能当市场 median。
2. ORNN/OCPI 没有授权 feed 时只能是 `licensed_unavailable` / `unavailable_marker`，禁止硬编码或用公开 proxy 冒充。
3. yfinance 不能作为官方 CAPEX 主源，只能做 secondary comparison。
4. 来源阻止抓取、条款不清、登录/付费/授权不可达时，必须标记 `manual_verified` 或 `unavailable`，不得绕过。
5. RunPod、Lambda、ComputePrices 的 parser 失败必须暴露为质量事件，不允许静默使用旧值、seed、mock 或 reference price。

## Minimum Row Fields Before Production Eligibility

| Source family | Required fields |
|---|---|
| SEC CAPEX actual | ticker, CIK, xbrl_tag, period_start, period_end, fiscal_period, accession_no, filed_date, value, unit, source_url, snapshot_path, raw_payload_hash, fetched_at |
| Official pricing page | provider, gpu_model, gpu_variant, billing_type, commitment, gpu_count, region if available, price_per_hour, currency, observed_at, source_url, snapshot_path, raw_payload_hash, fetched_at |
| Aggregator proxy | aggregator, provider, gpu_model, gpu_variant, quote_date, quote_age, price_per_hour, currency, region if available, availability if present, source_url, snapshot_path, raw_payload_hash, fetched_at |
| Licensed unavailable marker | source_name, source_type, collection_method, observed_at, fetched_at, unavailable_reason, source_url |

## Static Acceptance Checklist

- [x] SEC companyfacts API and User-Agent requirement documented.
- [x] RunPod, Lambda, and ComputePrices access method, parser fragility, and failure exposure documented.
- [x] ComputePrices aggregator limitation documented; page-level `from price` cannot be market median.
- [x] ORNN/OCPI licensed-unavailable policy documented.
- [x] yfinance secondary-only CAPEX policy documented.
- [x] blocked/unclear/login/pay/licensed sources must become `manual_verified` or `unavailable`.
- [x] every source row lists source URL, access method, allowed-use assumption, parser risk, fallback behavior.
- [x] verified sample table is in `external_source_notes.md` and marked as not hardcodable production data.
