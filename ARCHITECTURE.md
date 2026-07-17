# Tracker v2 Architecture

## 时间序列产品层（2026-07-12）

```text
OpenRouter public model rankings chart
  -> production_market_facts / openrouter_usage:model_total_tokens
  -> 52 周总量、4 周均线、公开 Top 3 模型身份

OpenRouter models API + OpenRouterList change-point ledger
  -> scripts/backfill_openrouter_active_prices.py
  -> canonical_slug 到历史 model id 映射
  -> 活跃价格层级、组合 input/output 牌价、按需单模型历史

Foundry Signals public history endpoints
  -> scripts/backfill_foundry_signals.py
  -> 每日供应商中位价、low/high、30 日均线、provider count
  -> GPU 价格分面、供应商变更标记、代际溢价、原频率 availability

line_ready_observation + canonical_observation + production_market_facts_analysis
  -> html_dashboard/build_time_series_dashboard.py
  -> html_dashboard/v4/time_series_snapshot.json
  -> html_dashboard/ai_compute_economics_monitor.html
```

线上部署链路已经与本地 DuckDB 解耦：OpenRouter、Foundry、模型价格和 CAPEX 均先落入 `tracker_data/backfills/*.json`，再由正式构建器生成 `public/index.html`。GitHub Actions 负责每日刷新、测试和提交；Vercel 只托管 `public/`，数据更新不依赖用户电脑开机。

发布质量门由 `scripts/validate_deploy_refresh.py` 统一执行。OpenRouter、Foundry 和活跃模型牌价必须为当天 `fresh`；SEC CAPEX 保留季度自然频率，抓取失败时只有五家公司最近官方值均在 150 天内才允许以 `current_for_frequency` 继续发布。任何来源缺失、缓存超期或页面测试失败都会返回非零状态，GitHub 不提交，Vercel 与 Sites 保留上一版。

Sites 同步在发布前优先读取 Vercel 正式响应并比较 `public/index.html` 的原始字节哈希。若运行环境只对 `*.vercel.app` 出现 DNS、TLS 或边缘网络错误，允许使用 Vercel 管理 API 作为受限备用证明，但必须同时满足：部署为 `READY`、目标为 `production`、项目 ID 与本地绑定一致、`githubCommitSha` 与本地 HEAD 完全相同。Sites 发布后优先做带私密访问凭证的 HTTP 回读；若回读仅被 Cloudflare 边缘拒绝，则以 Sites connector 的 deployment `succeeded`、固定 live URL 和最新 version `commit_sha` 等于刚推送 HEAD 完成闭环。任何数据、测试、部署状态或提交不一致仍然硬失败。

正式页面只把可比较时间序列作为主体。OpenRouter frontend 未单列的模型不得记为 0；活跃组合的 `Others / 无法匹配` 保留为可见灰色缺口，牌价 tooltip 显示匹配覆盖率。4 次订单薄/云价格快照和内部质量指标不进入主图。CAPEX 保留原生季度/事件频率，不与日频、周频合成总分。

## 正式链路

```text
公开源/API/页面
  -> data_sources/market_facts.py
  -> production_market_facts（原始、可追溯、不可静默删除）
  -> production_market_facts_canonical（完全重复观测归并）
  -> production_market_facts_analysis（质量资格过滤）
  -> canonical_observation（稳定 series_id / 自然频率 / 证据等级）
  -> series_definition + series_quality
  -> line_ready_observation / event_observation / matched_panel_index
  -> thesis_state.py（四时钟独立状态与证据链）
  -> html_dashboard/build_monitor_artifact.py（六展项只读数据契约）
  -> html_dashboard/v3/artifact.json（标准 manifest / snapshot / sources）
  -> Data Analytics portable artifact builder
  -> html_dashboard/ai_compute_economics_monitor.html
```

质量事件独立走：

```text
采集或解析失败
  -> production_data_quality_events（完整历史）
  -> production_data_quality_events_latest（每个 affected_key 最新状态）
  -> dashboard 失败暴露表
```

## 文件职责

| 文件 | 职责 |
|---|---|
| `tracker_v2.py` | DuckDB schema、生产写入合同、canonical/analysis/latest views |
| `production_store.py` | 生产事实和质量事件的数据对象 |
| `data_sources/market_facts.py` | 来源采集、解析、快照、异常隔离 |
| `html_dashboard/build_monitor_artifact.py` | 只读 state/series/event/quality views，生成六展项标准 artifact |
| `html_dashboard/v3/artifact.json` | 图表、表格、来源查询、口径和有界生产数据快照 |
| `html_dashboard/ai_compute_economics_monitor.html` | 唯一正式产品；自包含、离线、只读、可打开来源明细 |
| `html_dashboard/build_time_series_dashboard.py` | 正式时间序列页面与 reviewed snapshot 构建器 |
| `scripts/backfill_litellm_key_model_prices.py` | 历史研究回填工具；正式页面已不读取固定代表模型牌价 |
| `scripts/backfill_openrouter_cost_index.py` | 抓取 OpenRouter 周榜；剔除未完成周；按 start-date 保留窗口与本地完整周去重合并（同日上游优先）；缓存损坏/schema 不符硬失败；至少 52 周真实可追溯序列 |
| `scripts/backfill_openrouter_active_prices.py` | 保存 OpenRouter 当前模型别名与 OpenRouterList 871 模型调价账本、原始快照和哈希 |
| `scripts/backfill_foundry_signals.py` | 保存 Foundry 原始历史，并生成供应商中位价、区间、30 日均线与 availability |
| `test_suite/test_openrouter_cost_index.py` | 滚动窗口挤出、完整周过滤、start-date 边界、缓存损坏/schema、去重合并、不足 52 周硬失败、幂等 |
| `test_suite/test_time_series_dashboard.py` | 防止截断榜单被记零、稀疏快照冒充趋势、Token 成本覆盖缺口回归 |
| `html_dashboard/build_html_dashboard.py` | Phase 1 历史审计页面构建器，不再是正式入口 |
| `test_suite/test_data_contract.py` | schema、去重、资格、质量状态合同 |
| `test_suite/test_market_facts.py` | 来源解析与异常字段隔离 |
| `test_suite/test_series_layer.py` | series 稳定性、周期完整性、资格门、事件和 matched-panel 合同 |
| `scripts/run_phase3_daily.py` | 每日采集、并发锁、运行日志和核心来源 SLA 闭环 |
| `scripts/backfill_gpuperhour_snapshots.py` | 从本地结构化 JSON 快照回填 exact-config 历史 |
| `thesis_state.py` | Supply/Capacity/Demand/Commitment 独立状态机、报告和变化记录 |
| `test_suite/test_thesis_state.py` | 幅度/持续/广度/深度、proxy 限制、季度门槛和 guidance 方向测试 |

## Phase 2 派生视图

| View | 作用 |
|---|---|
| `canonical_market_observation` | 把市场事实规范成稳定 observation |
| `canonical_observation` | 合并市场事实、美国 CAPEX actual 和官方事件 |
| `series_definition` | 每个 series 的固定身份、自然频率和覆盖范围 |
| `series_quality` | chart/inflection/90D 三层资格和 reason code |
| `line_ready_observation` | 只保留周期完整且达到最低门槛的时序点 |
| `event_observation` | 只保留初始事实和真实数值变化，重复快照不重复发事件 |
| `matched_panel_candidate` | 暴露 GPU 候选及拒绝原因 |
| `matched_panel_member` | 固定配置且达到门槛的 panel 成员 |
| `matched_panel_index` | 固定成员、起点 100、带覆盖率和 7D/30D 变化的 panel index |
| `source_collection_policy` | 每个来源的频率、stale 阈值、关键性和历史策略 |
| `source_freshness` | fresh/stale/missing、UTC age 和来源覆盖 |
| `pipeline_health_latest` | 每条生产 pipeline 的最新运行状态 |
| `series_collection_gap` | series 层的缺日、覆盖率和 stale 状态 |

## 归档边界

- `dashboard_v2.py`：旧 Streamlit UI，仅供参考。
- `html_dashboard/ai_compute_trend_board.html`：旧单页趋势板，仅供历史对照。
- `decision_engine.py` 和旧 CSI：未读取 canonical analysis layer，不是当前判断引擎。
- `../compute-tracker/`：旧静态原型。

## Phase 5 展示合同

- Compute Price：H100/H200/B200 exact-config 历史积累与 10 日门槛；固定面板合格前不画价格曲线。
- Market Depth：最新可用 offer 数与 exact-config P25/P50/P75 横截面。
- Cloud：官方 VM-hour 快照；spot/on-demand/low-priority 分开，不伪装为 per-GPU-hour。
- Model Economics：真实 `price_change` 事件；不把重复 catalog snapshot 画成连续曲线。
- Demand：OpenRouter 完整周 public proxy，4W MA 独立基期 100；不能升级为 official inflection。
- Commitment：同一季度 US CAPEX 可比柱状图 + US/China 原生频率事件账本；不做日频插值。

## Phase 6 验收合同

- 六个核心投资问题必须在 60 秒内得到“可观察事实”或“明确不可判断”，不能用文案填补数据缺口。
- 任意 dashboard 数据必须能追到 source query、canonical observation、stable series、raw snapshot 和 hash。
- 图例隐藏后可见曲线与图例状态同步重算；来源弹窗、1440px 和 390px 均必须通过。
- MIG、零价格、未完成周、重复 ARR、稀疏 catalog、变动样本组成和单季度 CAPEX 均不得形成趋势。
- 产品验收与投资结论分开：产品可以 PASS，同时拐点结论保持 Observing。
- 边界：不接证券价格、股票日线、组合仓位、交易收益率或自动买卖建议。
