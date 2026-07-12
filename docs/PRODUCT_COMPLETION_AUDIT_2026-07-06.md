# PRODUCT_COMPLETION_AUDIT_2026-07-06

## 结论

当前产品已经具备最小可用判断价值：它能把 GPU 租赁/订单簿、官方云实例价格、模型/API 成本、应用商业化、云厂商 CAPEX/RPO 放在同一套 production 数据底表上，并给出 `No Signal / WARN / 15%` 的保守判断。

但它还不能标记为完整完成。原因是：若要把二级市场判断从“观察”升级到强信号，仍缺硬件成交价、ORNN/OCPI、AWS 90 天 spot history、GCP spot、ARR 深源、Artificial Analysis 等关键证据层。

## 目标拆解与当前证据

| 目标要求 | 当前证据 | 状态 |
|---|---|---|
| 跟踪 GPU 租赁/spot 价格 | `production_market_facts` 中 `gpu_rental=284`、`gpu_available_offer=181`、`gpu_rental_trend=24`、`gpu_market_trend=95` | 已可用，但不是硬件成交价 |
| 跟踪云厂商 spot instance 价格 | `cloud_instance_price=262`，Azure/AWS H100 spot/on-demand 已入库 | 部分可用，缺 GCP key 与 AWS 90 天 history |
| 跟踪模型 token/API 成本 | `token_price=1,399`，`model_value_score=820`，CostGoat/OpenRouter/ComputePrices 公开 proxy 已入库 | 已可用，但 Artificial Analysis 授权 API 缺失 |
| 跟踪 Seedance / 多模态生成成本 | `multimodal_generation_cost=38`，BytePlus token 与 seedance2.ai credits 分开入库 | 已可用，不能把 token USD 和 credits 混算 |
| 跟踪 AI 应用 ARR / 商业化 | `app_commercialization=15`，ARR.club public + Ramp adoption 已入库 | 弱信号可用，缺 ARR 历史/source links/Sacra 深源 |
| 跟踪云厂商 CAPEX/RPO 官方层 | `production_official_events=9`，覆盖 MSFT/AMZN/GOOGL/META/ORCL | 已可用，当前反而是“未转弱”的反证 |
| 图表清晰且不重复 | 五个 tab 已拆分不同问题：总览、价格、云厂商、应用、证据库各自承担不同图表 | 已完成本轮验收 |
| 收起内容格式一致 | 主流程折叠区为说明块 + 明细表；证据库全展开后 `multiselects=0` | 已完成本轮验收 |
| 文字分析反映实际情况 | 页面保留 `No Signal / WARN / 15%`，并显式暴露缺口 | 当前合格，不能升级为强交易信号 |

## 当前关键真实读数

| 层 | 读数 | 解释 |
|---|---:|---|
| 旧卡/上一代 90 日价格压力 | `-22.0%` | A100/H100 组松动 |
| 前沿卡 90 日价格压力 | `+7.7%` | H200/B200 仍偏紧，不支持全市场过剩结论 |
| H100 当前可用订单簿 | `48 offers`，最低 `$1.07/GPU hr` | GPUPerHour available=true；最低价用 min，不用 median |
| Azure H100 spot | `$1.42/VM hr` | 官方 VM-hour，不与 per-GPU-hour 混算 |
| AWS H100 spot | `$2.53/VM hr` | 官方 VM-hour，不与 per-GPU-hour 混算 |
| CostGoat high-quality output leader | `xiaomi/mimo-v2.5`，`$0.28/1M output`，quality `81` | 可观察应用/API routing 毛利改善空间 |
| Anthropic vs OpenAI adoption spread | `+2.1%` | Ramp 企业支付采用率口径 |
| Anthropic vs OpenAI public ARR spread | `$22.00B` | ARR.club public signal，不是完整审计 ARR |
| 官方 CAPEX/RPO 层 | `5/5 hyperscalers` | 当前偏扩张，是硬件链转负的反证 |

## 最大未完成项

| 缺口 | 当前暴露方式 | 为什么重要 |
|---|---|---|
| 硬件现货 GPU 成交价 | `gpu_contract_index:AUTH_REQUIRED`、硬件成交价仍缺 | 租赁价不能等同二手硬件成交价 |
| ORNN/OCPI 或等价授权指数 | `ornn_ocpi:DATA_SOURCE_UNAVAILABLE` | 原始叙事里要求跟踪 H100 算力指数 |
| AWS 90 天 spot history | `cloud_spot_aws_history:AUTH_REQUIRED` | 当前 AWS 只有横截面，不能做连续拐点 |
| GCP spot | `cloud_spot_gcp:AUTH_REQUIRED` | 三大云厂商缺一块 |
| ARR 深源与 source links | `app_arr_history:AUTH_REQUIRED`、`private_company_financials:AUTH_REQUIRED` | 当前 ARR 只能当公开弱信号 |
| Artificial Analysis API | `model_quality_price:AUTH_REQUIRED` | CostGoat 是公开 proxy，不能替代授权 benchmark |
| ComputePrices 限流 | `SOURCE_UNAVAILABLE` 429 events | 公开 API 可用性不稳定，需保留旧快照并暴露失败 |

## 当前产品是否对二级市场判断有价值

有价值，但价值边界明确：

- 能降低“算力持续紧缺”单一叙事的确定性，因为旧卡价格松动、H100 低价订单簿有深度。
- 不能输出硬件链全面转空，因为 H200/B200 仍偏紧，且官方 CAPEX/RPO 层未转弱。
- 能观察应用层接棒线索，因为模型输出价、Ramp adoption、ARR public signal 和 Seedance 成本已接入。
- 不能把应用层估值切换当作确认信号，因为 ARR 深源、历史与私企财务仍缺。

## 本轮验收

- `python3 -m py_compile dashboard_v2.py tracker_v2.py`：通过
- `python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q`：22 passed
- `python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db`：退出码 0，`quality_gate=WARN`
- Playwright / system Chrome：
  - 五个 tab 桌面截图通过
  - 五个 tab 390px 移动端截图通过
  - 图表标题不重复
  - `price/cloud/apps` 主流程展开态 `multiselects=0`
  - 证据库 9 个折叠区全部展开后 `multiselects=0`
  - 无 `Rendered at` footer、无 Traceback、控制台 0 error/warn

