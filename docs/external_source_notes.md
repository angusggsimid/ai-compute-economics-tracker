# External Source Notes And Parser Policy

本文档是 T14 的来源政策说明。它只定义外部来源的使用边界、解析风险和失败暴露方式；不得把本文档中的样本值写成生产硬编码数据。

## 总原则

1. 生产数据必须来自实时抓取，或来自带 `source_url`、`snapshot_path`、`raw_payload_hash`、`observed_at`、`fetched_at` 的 source-backed snapshot。
2. `seed`、`mock`、`reference price` 只能用于 demo、测试或回归，不允许进入生产判断。
3. 任何来源如果阻止抓取、条款不清、登录不可达、付费不可达、授权不可达，必须标记为 `manual_verified` 或 `unavailable`。不得绕过验证码、登录墙、付费墙、rate limit 或隐藏控制。
4. HTML 解析必须保存原始快照。页面结构变化、关键字段缺失、HTTP 403/429/5xx、JavaScript 渲染失败，都必须写入数据质量事件，不允许静默 fallback 到旧值或硬编码值。
5. 价格、CAPEX actual、guidance/RPO、OCPI 或 public proxy 必须保留各自频率和来源质量，不得混成一个伪精确指标。
6. 本文档中的 verified sample table 只用于验收和回归提示。生产路径必须重新抓取或读取 source-backed snapshot 后再入库。

## SEC Companyfacts API

- Source URL:
  - API docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
  - Data host: https://data.sec.gov/
  - Companyfacts endpoint pattern: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
  - Fair access / User-Agent policy: https://www.sec.gov/os/webmaster-faq
- Access method: HTTPS JSON API, `collection_method=sec_companyfacts_api`。
- User-Agent requirement: 请求必须带清楚的 `User-Agent`，至少包含项目或应用名、负责人或联系邮箱。不要使用空 UA、默认爬虫 UA 或伪装浏览器的 UA。
- Rate discipline: 按 SEC fair access 要求限速，生产采集应串行或低并发，遇到 403/429 立即停止本轮来源采集并记录失败。
- Parsing notes:
  - CIK 必须补足 10 位，例如 MSFT 为 `CIK0000789019`。
  - CAPEX XBRL tag 不同公司可能不同。AMZN 常见为 `PaymentsToAcquireProductiveAssets`，其他 hyperscaler 常见为 `PaymentsToAcquirePropertyPlantAndEquipment`。不能用单一 tag 强行套所有公司。
  - 生产行必须记录 ticker、CIK、xbrl_tag、period_start、period_end、fiscal_period、accession_no、filed_date、source_url。
- Parser risk:
  - 公司 tag 差异导致漏数。
  - 同一 tag 可能有 FY、QTD、YTD 或修订值，必须用 period_start/period_end/duration 判定，不只按最新 filed date。
  - SEC 403/429 代表来源暂不可用，不代表数据不存在。
- Failure exposure:
  - HTTP 403/429/timeout: 记录 `SEC_SOURCE_UNAVAILABLE`，不写 fabricated record。
  - 找不到公司 tag: 记录 `SEC_TAG_NOT_FOUND`，附 CIK 和候选 tags。
  - period 无法判定: 记录 `SEC_PERIOD_AMBIGUOUS`，不进入生产 eligible。

## Provider Pricing Pages

### RunPod

- Source URL: https://www.runpod.io/pricing
- Source type: `public_pricing_page`
- Access method: public page fetch, prefer embedded structured data if available; otherwise parse stable visible text/table after saving raw HTML snapshot。
- Allowed-use assumption: 公共定价页可用于研究监控和来源链接展示；不得绕过防护，不得高频抓取，不得假设页面价格包含所有折扣、库存、区域和可用性。
- Parser risk:
  - 页面可能由前端渲染，字段 class、排序、命名会变。
  - 同一 GPU 可能区分 PCIe、SXM、NVL、secure cloud、community cloud、不同 GPU count 或 commitment。
  - 页面价格不等于成交价，也不一定包含地区、库存、税费或长期折扣。
- Failure exposure:
  - 页面无法访问或字段缺失，记录 `PRICING_SOURCE_UNAVAILABLE` 或 `PARSER_SCHEMA_CHANGED`。
  - 不允许 fallback 到旧代码中的 `reference_prices`。

### Lambda

- Source URL: https://lambda.ai/pricing
- Source type: `public_pricing_page`
- Access method: public page fetch, prefer embedded structured data if available; otherwise parse stable visible text/table after saving raw HTML snapshot。
- Allowed-use assumption: 公共定价页可用于研究监控和来源链接展示；不得绕过登录、付费、反爬或不可见 API。
- Parser risk:
  - Lambda 页面同时展示 instance、1-click cluster、不同 GPU count、不同 commitment 或 reserved pricing。
  - 同一个 H100/B200 价格不能在不同计费形态之间直接混为一个 market price。
  - 页面可能隐藏地区、库存、最小租期和容量约束。
- Failure exposure:
  - 如果只能看到营销页但无法稳定定位价格，标记 `manual_verified` 或 `unavailable`。
  - 如果部分字段缺失，行可以进入 raw evidence，但 `is_production_eligible=false`，并写明缺失字段。

### ComputePrices

- Source URLs:
  - H100: https://computeprices.com/gpus/h100
  - H200: https://computeprices.com/gpus/h200
  - B200: https://computeprices.com/gpus/b200
- Source type: `aggregator`
- Access method: public page fetch, prefer embedded structured data; otherwise parse visible provider rows and save raw HTML snapshot。
- Allowed-use assumption: 聚合页面可作为 public proxy 和交叉比较线索，不是官方市场真实价格源。
- Required interpretation:
  - ComputePrices 是 aggregator，不是 RunPod、Lambda、Azure、Hyperbolic 等供应商的官方报价。
  - 页面级 `from price` 只能表示该页面展示的低价入口或聚合最低价线索，不能当作市场 median、official price 或成交价。
  - 每条 row 必须保留 provider、quote date、quote age、GPU variant、billing type、region、availability if present、source_url、snapshot_path。
  - ComputePrices 可命名为 `public_gpu_price_proxy`，不能命名为 OCPI，也不能替代官方供应商报价。
- Parser risk:
  - provider 行可能缺 quote date、availability、region 或 commitment。
  - 低价供应商可能是促销、限量、非等价 GPU variant、非主流地区或不可立即购买。
  - 页面供应商数量、排序和字段随时变化。
- Failure exposure:
  - 页面不可访问或字段缺失，记录 `AGGREGATOR_SOURCE_UNAVAILABLE` 或 `AGGREGATOR_SCHEMA_CHANGED`。
  - 不能用 ComputePrices 聚合值填补 RunPod/Lambda 官方报价。
  - 不能把 `from price` 转换为 median；只有足够 provider rows、quote age 和过滤规则时，才可单独计算 proxy median。

## ORNN / OCPI Policy

- Source reference:
  - ORNN AI: https://www.ornn.ai/
  - ICE/Bloomberg distribution reference: https://www.ice.com/insights/conversations/inside-the-ice-house/ornn-ais-nicholas-chapados-on-the-gpu-market-and-compute-financing
- Access method without license: none。
- Production policy:
  - 没有 ORNN 授权 feed、Bloomberg 可访问 feed 或其他明确授权接口时，OCPI 必须标记为 `source_type=licensed_unavailable`、`collection_method=unavailable_marker`。
  - 生产报告必须显示 `OCPI unavailable`，而不是展示硬编码指数。
  - 公开 proxy 可以来自 ComputePrices，但必须命名为 `public_gpu_price_proxy`，不能伪装为 ORNN/OCPI。
- Failure exposure:
  - 未配置授权 feed: 记录 `DATA_SOURCE_UNAVAILABLE`。
  - 有截图、新闻描述或历史报告但无可追溯授权数据: 只能作为 `manual_verified` 研究备注，不能进入 production series。

## GPU Rental Index Sources

### AIMultiple GPU Index

- Source URL: https://aimultiple.com/gpu-index
- Source type: `aggregator`
- Access method: public HTML fetch, parse visible article text after saving raw HTML snapshot。
- Production policy:
  - 只写入 `production_market_facts.track='gpu_rental_index'`。
  - 可以记录 median、range low/high、provider count。
  - 不允许混入 `gpu_rental` 可报价/可租赁曲线，不允许当作成交价、spot instance price 或硬件现货价。
- Parser risk:
  - 文章正文结构和措辞可能变化。
  - range 是页面级统计，不代表任意 provider 上可立即成交。
  - provider count 与价格点不是订单簿深度。
- Failure exposure:
  - 页面不可访问或字段缺失时记录 source unavailable/schema changed，不用旧值补齐。

### GetDeploying GPU Pages

- Source URL pattern: `https://getdeploying.com/gpus/<gpu-slug>`
- Source type: `aggregator`
- Access method: public HTML fetch, parse schema.org JSON-LD AggregateOffer after saving raw HTML snapshot。
- Production policy:
  - 只写入 `production_market_facts.track='gpu_rental_index'`。
  - 可以记录 AggregateOffer low/high price 和 offerCount。
  - 不允许混入 `gpu_available_offer` 或 `gpu_rental`，因为页面级 AggregateOffer 不是逐条可用订单。
- Parser risk:
  - JSON-LD 可能缺失、单位变化、价格区间跨不同 provider 或不同配置。
  - offerCount 是页面聚合，不等于可用库存。
- Failure exposure:
  - 单个 GPU 页面 404/timeout/JSON-LD 缺失时，记录质量事件，不影响其他页面。

## Token Price Catalog Sources

### LiteLLM model_prices JSON

- Source URL: https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
- Source type: `aggregator`
- Access method: GitHub raw JSON fetch, `collection_method=json_api`。
- Production policy:
  - 写入 `production_market_facts.track='token_price'`。
  - 单位统一为 `USD/1M tokens`，输入、输出、cached input 分 metric 保留。
  - 保留 model id、provider/source、source_url，不把社区 catalog 包装成模型公司官方价格。
- Parser risk:
  - 社区 JSON 可能有单位差异、字段缺失或 provider 命名变化。
  - 同一模型在不同 provider 有不同价格，不能无来源地合并成唯一官方价。
- Failure exposure:
  - JSON 不可访问或字段缺失时写质量事件，不沿用旧 catalog。

### models.dev API

- Source URL: https://models.dev/api.json
- Source type: `aggregator`
- Access method: public JSON API fetch, `collection_method=json_api`。
- Production policy:
  - 写入 `production_market_facts.track='token_price'`。
  - 只保留 focused AI application / model universe 中相关 provider 或模型。
  - 不替代 OpenAI、Anthropic、Google 等官方 pricing pages，只作为公开 catalog 交叉源。
- Parser risk:
  - API schema 可能调整。
  - 同一模型不同 endpoint/provider 价格不同。
  - release_date、cost、modalities 等元数据可能来自 catalog 维护者，不等于公司公告。
- Failure exposure:
  - API 失败、字段缺失、单位不可判定时写质量事件，不插入估算。

## yfinance Policy

- Source URL: https://github.com/ranaroussi/yfinance
- Access method: Python package against Yahoo Finance public-facing data。
- Production policy:
  - yfinance 最多作为 secondary comparison 或 sanity check。
  - yfinance 不允许作为官方 CAPEX 主源，不允许写入 `source_type=official` 的 CAPEX actual。
  - CAPEX official actuals 以 SEC companyfacts 或公司官方披露为主。
- Parser risk:
  - Yahoo Finance 字段口径、回溯修订、segment 粒度和可用性不稳定。
  - yfinance 项目本身不是 Yahoo Finance 官方授权数据 feed。
- Failure exposure:
  - yfinance 失败不应阻断官方 SEC 采集。
  - 如果 yfinance 与 SEC 不一致，以 SEC/company filing 为准，并记录 comparison discrepancy。

## DuckDB And Streamlit Technical Behavior

- DuckDB docs: https://duckdb.org/docs/
- Streamlit docs: https://docs.streamlit.io/
- Policy:
  - DuckDB 只负责本地存储和查询，不改变来源质量。生产表必须保留 provenance 字段。
  - Streamlit 只负责展示，不允许把缺失数据渲染成正常状态。
  - 页面遇到生产数据为空、来源失败、OCPI 未授权时，应显示 warning/error/status banner，并暴露 failure code。

## Verified Sample Table From Plan

以下样本来自 `tracker-v2-real-data-closure-plan.md` 的验收表。它们只证明目标来源和字段形态，不代表生产代码可以硬编码这些值。实现时必须重新抓取，或从带快照和哈希的 source-backed snapshot 生成。

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
