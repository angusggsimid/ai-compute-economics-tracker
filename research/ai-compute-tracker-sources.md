# AI Compute Tracker 免费/公开数据源清单

更新日期：2026-07-08

## 目标口径

这个 tracker 不只看 GPU 租赁价格，而是同时覆盖三类数据：

1. GPU 现货、租赁、预留、远期/期货价格
2. 模型 token 价格、推算 token 成本、价格/性能
3. 主要 AI 应用和模型公司的 ARR、收入 run-rate、企业采用率和应用热度

结论先说：GPU 和 token 可以做成较高频的免费 tracker；ARR/商业化只能做低频研究库，必须给来源和置信度，不能伪装成精确实时数据。

## 一、GPU 租赁、现货、预留、期货价格

| 源 | 链接 | 可获取内容 | 适合用途 | 局限 |
|---|---|---|---|---|
| AIMultiple GPU Index | https://aimultiple.com/gpu-index | 公开挂牌的 GPU 小时价，覆盖 on-demand、spot、1-year reserved | 做免费版 GPU price index 的底表 | 不覆盖多年合约、大客户私下价格、TCO |
| GetDeploying GPU Prices | https://getdeploying.com/gpus | 多供应商、多 GPU 型号的云 GPU 报价 | 横向比价、发现低价供应商、补 provider universe | 需要自己清洗库存、地区、服务质量 |
| GetDeploying H100 Page | https://getdeploying.com/gpus/nvidia-h100 | H100 专页，包含多 provider 的 H100 价格 | 追踪 H100 单卡小时价区间 | 不是交易成交价 |
| Vast.ai Pricing | https://vast.ai/pricing | Vast marketplace 实时 GPU 价格，含 on-demand、interruptible、reserved | 观察真实 marketplace 供需和低价尾部 | 主机质量、网络、可靠性差异很大 |
| Vast.ai API / Docs | https://docs.vast.ai/ | 可程序化搜索 GPU、价格、库存、规格 | 自动抓取 marketplace 现货样本 | 需要 API key，字段要自己标准化 |
| RunPod Pricing | https://www.runpod.io/pricing | Community Cloud、Secure Cloud、serverless、per-second/per-hour 价格 | 观察开发者常用 neocloud 价格 | Community 和 Secure 的 SLA/安全性不可混比 |
| AWS EC2 Spot Pricing | https://aws.amazon.com/ec2/spot/pricing/ | AWS Spot 折扣和当前价格入口 | hyperscaler spot 价格基准 | GPU SKU 映射复杂，区域差异大 |
| AWS DescribeSpotPriceHistory | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSpotPriceHistory.html | EC2 spot price history API | 拉历史 spot 序列 | 需要 AWS API 权限；不是 on-demand |
| AWS Price List Bulk API | https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html | AWS 官方价格文件，JSON/CSV | 拉 EC2 on-demand list price | 不含 Savings Plan 私价；Spot 另走 spot API |
| Google Cloud Billing APIs | https://docs.cloud.google.com/billing/docs/apis | GCP publicly available pricing、Cloud Billing Catalog API | 拉 GCP list price | SKU 很细，GPU/VM/region 要自己映射 |
| Google Cloud Billing API Pricing | https://cloud.google.com/billing/v1/pricing | Cloud Billing APIs 免费使用说明 | 确认采集成本 | 只说明 API 费用，不解决清洗难度 |
| Azure Retail Prices API | https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices | Azure retail rates，免认证 API | 拉 Azure VM/GPU list price | Preview/字段可能缺 SKU，需要分页和过滤 |
| Ornn OCPI | https://ornn.com/ | GPU compute spot reference index，覆盖 H100、H200、B200 等 | 观察 compute 金融化和 reference index | 完整数据/交易细节可能不是免费 |
| ICE + Ornn GPU Compute Futures | https://ir.theice.com/press/news-details/2026/ICE-and-Ornn-to-Launch-GPU-Compute-Futures-Contracts/default.aspx | 基于 Ornn Compute Price Index 的 GPU compute futures 计划 | 追踪期货/远期市场是否成熟 | 不是免费历史交易数据库 |
| Silicon Data Silicon Index | https://www.silicondata.com/products/silicon-index | H100 rental index、GPU pricing benchmark | 对照专业指数方法论 | 商业化数据产品，完整数据需联系销售 |
| IEEE Spectrum on Silicon Data Index | https://spectrum.ieee.org/gpu-prices | Silicon Data 指数背景、H100 spot index 解释 | 理解 GPU price index 方法论 | 新闻/解释性文章，不是可持续数据 API |

### GPU 表建议字段

| 字段 | 说明 |
|---|---|
| date | 采集日期 |
| provider | 供应商 |
| source | 数据源 |
| gpu_model | H100、H200、B200、A100、L40S、RTX 4090 等 |
| region | 地区 |
| price_type | on_demand / spot / interruptible / reserved / futures / index |
| term | hourly / 1y / 3y / forward_month 等 |
| usd_per_gpu_hour | 标准化后的每 GPU 小时美元价格 |
| availability | 有货、低库存、未知、数量 |
| quality_tier | hyperscaler / neocloud / marketplace / community / secure |
| notes | 是否含 CPU、存储、网络、SLA、最小时长等 |

## 二、Token 价格、模型价格、推算 token 成本

| 源 | 链接 | 可获取内容 | 适合用途 | 局限 |
|---|---|---|---|---|
| OpenRouter Models Docs | https://openrouter.ai/docs/guides/overview/models | 模型 pricing object，input/output/cache/request/unit 价格 | 程序化获取多模型价格结构 | 通过 OpenRouter 的价格不一定等同所有直连价 |
| OpenRouter Pricing | https://openrouter.ai/pricing | 计费规则、free tier、BYOK、routing/fallback 规则 | 理解 OpenRouter 价格口径 | 价格会随模型目录变化 |
| OpenRouter Models API | https://openrouter.ai/api/v1/models | 模型列表、价格、context、能力字段 | 直接落库 | 需要处理 provider/model 命名变化 |
| LiteLLM Pricing Docs | https://docs.litellm.ai/docs/provider_registration/add_model_pricing | LiteLLM 模型价格和 context window 文件说明 | 建统一模型价格表 | 社区维护，可能滞后 |
| LiteLLM model_prices JSON | https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json | input/output/cached pricing、context window、model metadata | 成本计算底表 | 需要和官方 pricing 交叉校验 |
| models.dev | https://models.dev/ | 模型、provider、pricing、capability 元数据 | 模型规格库、能力对照 | 新项目，覆盖和字段需验证 |
| models.dev GitHub | https://github.com/anomalyco/models.dev | 开源数据库源码 | 可 fork 成自己的 model catalog | 社区维护，需版本控制 |
| Artificial Analysis | https://artificialanalysis.ai/ | 模型质量、速度、价格、provider performance | 计算 price/performance、tokens/sec | API 付费；免费网页适合人工/轻量抓取 |
| Artificial Analysis Methodology | https://artificialanalysis.ai/methodology | benchmark、speed、price 方法论 | 确认性能指标口径 | 指数权重和具体任务不完全公开到可复现 |
| Price Per Token | https://pricepertoken.com/ | 多模型 API 价格比较 | 快速 sanity check | 第三方站点，需官方校验 |
| CostGoat LLM API Compare | https://costgoat.com/compare/llm-api | 多模型价格、质量/value 排名、成本计算 | 快速横向对比 | 第三方评分和价格要复核 |
| BenchLM LLM Pricing | https://benchlm.ai/llm-pricing | 多模型价格、benchmark/value 对照 | 价格/质量补充源 | 第三方聚合，不作唯一来源 |
| OpenAI API Pricing | https://developers.openai.com/api/docs/pricing | OpenAI 官方模型价格 | 官方校验 | 只覆盖 OpenAI |
| Claude API Pricing | https://platform.claude.com/docs/en/about-claude/pricing | Anthropic 官方 API 价格 | 官方校验 | 只覆盖 Anthropic |
| Gemini API Pricing | https://ai.google.dev/gemini-api/docs/pricing | Gemini 官方 API 价格 | 官方校验 | 只覆盖 Google Gemini |
| Gemini API Billing | https://ai.google.dev/gemini-api/docs/billing | Gemini billing 规则 | 理解计费、免费层和账单 | 不等于完整模型价格表 |
| Mistral Pricing | https://mistral.ai/pricing/ | Mistral 官方计划和 API pricing 入口 | 官方校验 | 页面结构可能变化 |
| xAI Pricing Docs | https://docs.x.ai/developers/pricing | xAI/Grok 官方 API 价格 | 官方校验 | 只覆盖 xAI |

### Token 表建议字段

| 字段 | 说明 |
|---|---|
| date | 采集日期 |
| model | 模型名 |
| provider | OpenAI、Anthropic、Google、Mistral、xAI、OpenRouter、Together 等 |
| route | direct / aggregator / byok |
| input_usd_per_1m | 每 100 万 input tokens 价格 |
| output_usd_per_1m | 每 100 万 output tokens 价格 |
| cached_input_usd_per_1m | cache hit input 价格 |
| batch_discount | batch 折扣 |
| context_window | 上下文长度 |
| output_limit | 最大输出 |
| speed_tokens_sec | 输出速度 |
| quality_score | benchmark 或内部评分 |
| source_url | 来源 |

### Token 成本推算公式

API 价格不是模型真实成本。若要估算自部署或供应商毛利，需要把 GPU 小时价和吞吐接起来：

```text
每 100 万 output token 推算成本
= GPU 每小时价格 / (tokens_per_second * 3600 / 1,000,000 * 利用率 * batch效率)
```

最低可用字段：

| 字段 | 来源 |
|---|---|
| GPU 每小时价格 | AIMultiple / Vast / RunPod / AWS / GCP / Azure |
| tokens_per_second | Artificial Analysis 或自测 benchmark |
| 利用率 | 自设情景：30%、50%、70% |
| batch效率 | 自设情景：1.0、1.5、2.0 |
| API price | OpenRouter / LiteLLM / 官方 pricing |

## 三、AI 应用 ARR、收入 run-rate、采用率

| 源 | 链接 | 可获取内容 | 适合用途 | 局限 |
|---|---|---|---|---|
| Sacra AI Research | https://sacra.com/t/ai/ | OpenAI、Anthropic、Perplexity、Cursor、Windsurf、Manus、Genspark 等 ARR/annualized revenue 估算 | 私营 AI 公司商业化线索 | 估算和研究口径，不是公司公告 |
| Sacra Perplexity Example | https://sacra.com/research/perplexity-at-148m-year/ | Perplexity annualized revenue、OpenAI/Anthropic/Glean 对照 | 建立应用 ARR 样本 | 单篇研究，时间点会过期 |
| Sacra Windsurf/Cursor Example | https://sacra.com/research/why-openai-wants-windsurf/ | Windsurf、Cursor ARR 和 AI IDE 市场线索 | coding app 商业化样本 | 估算，需持续更新 |
| Sacra Manus Example | https://sacra.com/research/manus-at-90m-year/ | Manus、Genspark、Cognition、Cursor annualized revenue | agent app 商业化样本 | 估算，时间敏感 |
| Ramp AI Index | https://ramp.com/data/ai-index | 美国企业 AI 采用率和支出趋势 | 企业付费 adoption proxy | 不是 ARR；样本是 Ramp 客户 |
| Ramp Econ Lab | https://econlab.substack.com/p/anthropic-beats-openai | Ramp AI Index 月度解读，模型公司采用率变化 | 追踪 Anthropic/OpenAI 企业采用率 | 样本口径有限，不等于全市场收入 |
| Menlo State of Generative AI in the Enterprise | https://menlovc.com/perspective/2025-the-state-of-generative-ai-in-the-enterprise/ | 企业 GenAI 支出、应用层/模型层/行业层拆分 | 行业级 TAM 和 spend allocation | 不是单公司 ARR |
| a16z Top 100 Gen AI Apps | https://a16z.com/100-gen-ai-apps-6/ | AI 消费应用 web/mobile 排名、流量/使用热度 | 应用层热度和份额 proxy | 不是收入数据 |
| Stanford AI Index | https://hai.stanford.edu/ai-index/2026-ai-index-report | 宏观 AI adoption、产业、成本趋势 | 宏观背景和长期趋势 | 不适合单公司 ARR |
| Forbes AI 50 | https://www.forbes.com/lists/ai50/ | AI 私营公司名单、估值、融资、类别 | 建立 company universe | 收入字段有限，部分需订阅或手工整理 |

### ARR/商业化表建议字段

| 字段 | 说明 |
|---|---|
| company | 公司 |
| product | ChatGPT、Claude、Cursor、Perplexity、Manus 等 |
| category | model_lab / coding / search / agent / image_video / vertical_ai |
| metric_type | ARR / annualized_revenue / revenue_run_rate / adoption_rate / traffic_rank / app_rank |
| metric_value | 数值 |
| currency | USD 等 |
| period | 对应时间点 |
| source | Sacra / Ramp / Menlo / a16z / official / press |
| source_url | 来源链接 |
| confidence | high / medium / low |
| notes | 是否为估算、是否为样本 proxy、是否为公司公告 |

## 四、建议采集优先级

| 优先级 | 模块 | 源 |
|---|---|---|
| 1 | GPU 公开报价 | AIMultiple、GetDeploying、Vast.ai、RunPod |
| 1 | Token 官方/聚合价格 | OpenRouter、LiteLLM、models.dev、官方 pricing |
| 1 | 模型性能 | Artificial Analysis |
| 2 | hyperscaler 官方价格 | AWS、GCP、Azure |
| 2 | 商业化 proxy | Sacra、Ramp、Menlo、a16z |
| 3 | 期货/金融化价格 | Ornn、ICE、Silicon Data |

## 五、最小可用版本

第一版 tracker 可以只做 3 张表：

1. `gpu_prices_daily`
2. `model_token_prices`
3. `ai_company_commercial_metrics`

推荐更新频率：

| 表 | 频率 | 说明 |
|---|---|---|
| gpu_prices_daily | 每日 | 价格和库存变化快 |
| model_token_prices | 每日或每周 | 新模型发布时需要临时刷新 |
| ai_company_commercial_metrics | 每月 | ARR 低频，且多为公开碎片 |

## 六、使用提醒

1. 不要把 marketplace 最低价当作可稳定采购价。
2. 不要把 list price、spot price、reserved price、forward/futures price 混成一个数。
3. 不要把 Ramp adoption 当 ARR。
4. 不要把 Sacra/The Information/媒体估算当公司公告。
5. Token API price 和真实推理成本是两件事：前者是售价，后者要用 GPU 成本和吞吐推算。
6. 每条 ARR/收入数据都必须保留 `source_url`、`period`、`confidence`。

