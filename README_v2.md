# AI 算力与商业化 Tracker v2

## 唯一正式入口

| 层 | 正式位置 | 状态 |
|---|---|---|
| 原始生产事实 | `ai_compute_tracker_production.db / production_market_facts` | 保留全部来源事实，不直接供图表使用 |
| 规范事实 | `production_market_facts_canonical` | 去除完全重复观测，保留冲突价格供聚合 |
| 分析事实 | `production_market_facts_analysis` | 隔离不合格、零价和 RunPod MIG 记录 |
| 质量状态 | `production_data_quality_events_latest` | 每个受影响字段只显示最新状态 |
| 当前产品 | `html_dashboard/ai_compute_economics_monitor.html` | 时间序列正式单页；需求、价格、成本与份额均以日期为横轴 |

旧 `dashboard_v2.py`、旧 CSI/DecisionEngine 和根目录 `compute-tracker/` 均为 archive/demo，不能用于证明当前产品完成。

重建当前 HTML：

```bash
cd /Users/agg/Documents/New\ project\ 2
python3 tracker_v2/scripts/backfill_openrouter_cost_index.py --reuse-commits
python3 tracker_v2/scripts/backfill_foundry_signals.py
python3 tracker_v2/scripts/backfill_openrouter_active_prices.py
python3 tracker_v2/html_dashboard/build_time_series_dashboard.py
```

旧 `html_dashboard/ai_compute_trend_board.html`、`build_html_dashboard.py` 和 v3 截面 artifact 只保留作历史审计，不再是产品入口。

当前正式页面默认展示 12 张时间序列图：52 周 OpenRouter Token 总量、每周活跃模型组合更替、活跃模型 output 价格层级、活跃组合 input/output 牌价、三代 GPU 中位租赁价分面、GPU 代际溢价、三代 GPU availability 分面。单模型价格历史按需展开；CAPEX 仅在底部按季度/事件原频率展示。

## GitHub + Vercel 自动更新

正式部署不读取本地 DuckDB。`scripts/refresh_and_build.py` 会分别刷新 OpenRouter、Foundry Signals、活跃模型牌价和 SEC CAPEX，来源失败时保留上一份已验证数据并把状态写入 `tracker_data/deploy_refresh_status.json`。构建结果复制到 `public/index.html`，Vercel 只负责托管该静态目录。

GitHub Actions 工作流位于 `.github/workflows/refresh-dashboard.yml`，每天 `00:17 UTC`（香港时间 `08:17`）运行。刷新和测试通过后只提交数据 JSON、正式 HTML 和刷新状态；Vercel 监听私有仓库的主分支并自动发布。

- 私有仓库：`https://github.com/angusggsimid/ai-compute-economics-tracker`
- 正式网站：`https://trackerv2-git-main-angusggsimids-projects.vercel.app`（Vercel 登录保护；始终跟随主分支最新生产部署）
- Sites 私密镜像：`https://ai-compute-economics-tracker.angusgu456396.chatgpt.site`

Codex 自动化 `AI Compute Tracker｜Sites 每日同步` 每天香港时间 `09:00` 检查 GitHub 当日刷新。只有四个来源均为 fresh、页面测试通过时才构建并发布 Sites 新版本；失败或 degraded 时保留上一版 Sites，不覆盖线上内容。

本地执行同一条生产链路：

```bash
python3 scripts/refresh_and_build.py
python3 -m pytest test_suite/test_time_series_dashboard.py -q
```

需要提交的生产数据位于 `tracker_data/backfills/`。`tracker_snapshots/`、DuckDB、截图、缓存和本地环境文件均被 `.gitignore` 排除。

OpenRouter frontend 榜单只单列少量头部模型和 `Others`，所以页面不再计算厂商总份额；未单列或未映射模型统一进入灰色 `Others / 无法匹配`，绝不写成 0。活跃模型由最近 4 个完整周的命名模型 Token 量筛选，累计覆盖 80%、最多 12 个；当前筛出 8 个，DeepSeek R1 等不活跃历史模型不会进入主视图。组合牌价按已匹配命名模型的公开 Token 量加权并显示 coverage，代表 visible listed-price exposure，不代表真实账单。

OpenRouterList 保存 871 个模型的调价点和生命周期，但仓库许可证保留占位字段、没有单独数据许可，因此只作为有明确来源标注的辅助历史。旧 LiteLLM 固定代表模型牌价已从正式页面删除，因为活跃模型组合 input/output 牌价更贴近当前真实调用结构。Foundry Signals 没有公开 API 稳定性承诺或明确的数据许可证，网站称数据为 illustrative，且供应商覆盖曾变化；页面改用每日供应商中位价、最低–最高区间、30 日均线和供应商数量变更标记，不把混合平均价直接解释为市场涨跌。

当前 Phase 3 数据审计口径：GPUPerHour 已开始每日写入 exact-config facts，并从 27 个本地原始快照回填历史。当前有 237 个精确配置 series：146 个覆盖至少 2 日、94 个覆盖 3 日、0 个达到 10 日画线门槛。核心 GPUPerHour/RunPod/Vast 来源 fresh；ComputePrices GPU catalog/trend 两个次级源 stale，状态明确暴露。

每日 runner：

```bash
cd /Users/agg/Documents/New\ project\ 2/tracker_v2
python3 scripts/run_phase3_daily.py --dry-run
python3 scripts/run_phase3_daily.py
python3 scripts/run_phase3_daily.py --audit-only
```

项目内提供 `ops/com.agg.ai-compute-tracker.phase3.daily.plist.example`，但没有擅自安装到系统 LaunchAgents。

独立投资命题状态：

```bash
python3 tracker_v2.py state-report --production --db ai_compute_tracker_production.db
```

当前状态为 Supply Price `Observing`、Capacity `Observing`、Demand `Trend`、Commitment `Observing`。四者不合成总分；输出位于 `tracker_data/thesis_states/latest-thesis-state.json` 和 `.md`。每日 runner 会在数据更新后自动生成新的状态快照并记录升级/降级。

> 当前生产版的目标不是复刻 gpus.io 的 GPU 租赁表，而是把 **GPU 租赁价格、官方云 GPU spot/实例价格、模型 token/API 价格、AI 应用 ARR 公开信号、云厂商 CAPEX/官方事件** 放在同一套可追溯数据底表里，告诉用户现在能不能支持“算力稀缺溢价松动/破裂”的二级市场判断。

---

## 当前生产版边界

当前生产版先回答一个问题：

> **GPU 和 token 成本是否正在下降，同时 AI 应用商业化和云厂商 CAPEX/官方指引是否足以改变二级市场对硬件、云厂商、应用层的判断？**

硬性约束：

- 不把日频 GPU/token、事件型 ARR、季度 CAPEX 硬合成一个总分。
- 没有真实来源、快照和 hash 的数据不进入 production 判断。
- GPU 租赁 per-GPU-hour 与官方云 VM-hour 分开展示，避免口径混算。
- 当前阶段不输出旧 `No Signal / WARN / 15%` 总分；该逻辑没有读取新的 canonical 分析层。
- 旧 L2/L3/CSI 是 demo/legacy 研究原型，不作为当前 production dashboard 的主结论。

---

## 🚀 快速开始

```bash
cd /Users/agg/Documents/New\ project\ 2/tracker_v2

# 1. 初始化生产 schema（默认不加载 seed/demo 数据）
python3 tracker_v2.py init --db ai_compute_tracker_production.db

# 2. 查看生产数据状态
python3 tracker_v2.py status --quality --db ai_compute_tracker_production.db

# 3. 一键生产更新：GPU、SEC CAPEX、官方事件、OCPI/proxy policy，
#    market-facts，随后自动运行质量门和 source-backed report
python3 tracker_v2.py update --production --db ai_compute_tracker_production.db

# 4. 生产报告：没有真实生产数据时会输出 NO_PRODUCTION_DATA 或 FAIL_SEED_ONLY
python3 tracker_v2.py report --production --db ai_compute_tracker_production.db

# 5. 生成正式 dashboard 数据契约
python3 html_dashboard/build_monitor_artifact.py

# 6. 清空 production 表必须显式确认，且不会清 legacy/demo 表
python3 tracker_v2.py reset-production-db --confirm-real-data-reset --db ai_compute_tracker_production.db
```

也可以用环境变量固定本次会话的生产库路径：

```bash
export AI_COMPUTE_TRACKER_DB=ai_compute_tracker_production.db
python3 tracker_v2.py init
python3 tracker_v2.py update --production
python3 tracker_v2.py report --production
```

旧的 `ai_compute_tracker.db` 只作为 demo/test artifact 保留；真实生产闭环不要写入或读取它。

当前生产验收摘要：

- Production DB: `ai_compute_tracker_production.db`
- Portable HTML dashboard: `html_dashboard/ai_compute_economics_monitor.html`
- Artifact builder: `html_dashboard/build_monitor_artifact.py`
- Canonical artifact: `html_dashboard/v3/artifact.json`
- Current product: 4 independent state cards, 6 non-duplicated exhibits, 2 commercialization evidence cards, 3 compact evidence tables, source modal on every chart/table/card.
- Current data boundary: matched H100/H200/B200 panels have 3 valid days versus the 10-day chart threshold, so no fake GPU price line is shown; OpenRouter demand uses complete-week 4W moving averages; model prices use real change events; US CAPEX bars compare calendar Q1 2026 only; Oracle FY2026 annual and China evidence remain in the native-frequency ledger.
- Phase 6 investor acceptance: `docs/PHASE6_INVESTOR_ACCEPTANCE_2026-07-11.md`.
- Current QA: portable artifact validation/package/verification passed; 1440px and 390px viewports passed; legend recomputation passed; 68 Phase 1-6 tests passed, 0 failed.
- Final scope: this product ends at AI compute economics evidence. It does not ingest security prices, stock daily data, portfolio positions or trading returns.
- GitHub source audit: `research/github_data_source_audit_2026-07-08.md`
- Chart contract: `research/dashboard_chart_contract_2026-07-08.md`
- Four-track market facts: `production_market_facts=18,135`，覆盖 GPU 租赁/spot、GPUMarkets fixing + 1D/7D/30D delta、GPUPerHour/Vast/RunPod 当前可用订单薄、ComputePrices 7 日公开趋势、GPUs.io 30/90 日 movers、AIMultiple / GetDeploying 聚合 GPU 价格指数、AWS/Azure 官方云实例价格、OpenRouter/LiteLLM/models.dev token/API 价格、CostGoat 模型质量/价效比公开 proxy、AI 应用 ARR 公开信号、Ramp AI Index 企业付费采用率、Seedance 多模态生成成本。
- Source-backed report: `tracker_data/20260705T143710Z-production-source-backed-decision-brief.md`
- Acceptance summary: `tracker_data/20260705T144531Z-production-acceptance-summary.md`
- Product completion audit: `docs/PRODUCT_COMPLETION_AUDIT_2026-07-06.md`
- Dashboard smoke screenshot: `tracker_data/dashboard_v2_production_smoke.png`
- Usable dashboard screenshot: `tracker_data/dashboard_v2_usable_trend_smoke.png`
- Repaired decision dashboard screenshot: `tracker_data/dashboard_v2_repaired_decision_smoke.png`
- Four-track dashboard screenshot: `tracker_data/dashboard_v2_four_track_smoke.png`
- Cloud spot dashboard screenshot: `tracker_data/dashboard_v2_cloud_spot_smoke.png`
- Decision cards dashboard screenshot: `tracker_data/dashboard_v2_decision_cards_smoke.png`
- GPU trend dashboard screenshot: `tracker_data/dashboard_v2_gpu_trend_smoke.png`
- Enterprise adoption dashboard screenshot: `tracker_data/dashboard_v2_adoption_smoke.png`
- Seedance multimodal cost screenshot: `tracker_data/dashboard_v2_seedance_smoke.png`
- GPUs.io trend dashboard screenshot: `tracker_data/dashboard_v2_gpusio_smoke.png`
- Market regime dashboard screenshot: `tracker_data/dashboard_v2_regime_smoke.png`
- Official CAPEX/RPO dashboard screenshot: `tracker_data/dashboard_v2_official_events_smoke.png`
- Model value dashboard screenshot: `tracker_data/dashboard_v2_model_value_smoke.png`
- GPUPerHour available order book screenshot: `tracker_data/dashboard_v2_gpuperhour_smoke.png`
- Redesigned overview screenshot: `tracker_data/dashboard_v2_redesign_overview.png`
- Professional single-page dashboard screenshots:
  - `tracker_data/dashboard_v2_professional_final_top.png`
  - `tracker_data/dashboard_v2_professional_final_mid.png`
  - `tracker_data/dashboard_v2_professional_final_bottom.png`
  - `tracker_data/dashboard_v2_professional_final_mobile.png`
- Latest HTML dashboard QA: 10 chart cards, 12 SVG charts, 2 tables, 3 visually separated sections, 0 default missing charts, desktop/mobile console 0 error/warn, 390px mobile without horizontal overflow, date filter and source legend toggles redraw charts.
- First-principles overview screenshot: `tracker_data/dashboard_v2_first_principles_overview.png`
- First-principles evidence screenshot: `tracker_data/dashboard_v2_first_principles_evidence.png`
- Inflection watchlist overview screenshot: `tracker_data/dashboard_v2_inflection_watchlist_overview.png`
- Inflection watchlist evidence screenshot: `tracker_data/dashboard_v2_inflection_watchlist_evidence.png`
- Visual-first overview screenshot: `tracker_data/dashboard_v2_visual_first_overview.png`
- Visual dashboard overview screenshot: `tracker_data/dashboard_v2_visual_dashboard_overview.png`
- Visual dashboard mobile screenshot: `tracker_data/dashboard_v2_visual_dashboard_mobile.png`
- Four-layer visual overview screenshot: `tracker_data/dashboard_v2_four_layer_visual_overview.png`
- Four-layer visual mobile screenshot: `tracker_data/dashboard_v2_four_layer_visual_mobile.png`
- Four-layer visual mobile mid screenshot: `tracker_data/dashboard_v2_four_layer_visual_mobile_mid.png`
- Cloud spot in order book overview screenshot: `tracker_data/dashboard_v2_cloud_spot_in_orderbook_overview.png`
- Cloud spot in order book mobile screenshot: `tracker_data/dashboard_v2_cloud_spot_in_orderbook_mobile.png`
- Clean overview screenshot: `tracker_data/dashboard_v2_clean_overview.png`
- Clean price tab screenshot: `tracker_data/dashboard_v2_clean_price.png`
- Clean cloud tab screenshot: `tracker_data/dashboard_v2_clean_cloud.png`
- Clean apps tab screenshot: `tracker_data/dashboard_v2_clean_apps.png`
- Clean evidence tab screenshot: `tracker_data/dashboard_v2_clean_evidence.png`
- Clean mobile tab screenshots: `tracker_data/dashboard_v2_clean_mobile_overview.png`、`tracker_data/dashboard_v2_clean_mobile_price.png`、`tracker_data/dashboard_v2_clean_mobile_cloud.png`、`tracker_data/dashboard_v2_clean_mobile_apps.png`、`tracker_data/dashboard_v2_clean_mobile_evidence.png`
- Final non-duplicated tab screenshots: `tracker_data/dashboard_v2_final_overview.png`、`tracker_data/dashboard_v2_final_price.png`、`tracker_data/dashboard_v2_final_cloud.png`、`tracker_data/dashboard_v2_final_apps.png`、`tracker_data/dashboard_v2_final_evidence.png`
- Final expanded-detail screenshots: `tracker_data/dashboard_v2_final_price_expanded.png`、`tracker_data/dashboard_v2_final_cloud_expanded.png`、`tracker_data/dashboard_v2_final_apps_expanded.png`、`tracker_data/dashboard_v2_final_evidence_expanded.png`、`tracker_data/dashboard_v2_final_evidence_all_expanded.png`
- Final mobile screenshots: `tracker_data/dashboard_v2_final_mobile_overview.png`、`tracker_data/dashboard_v2_final_mobile_price.png`、`tracker_data/dashboard_v2_final_mobile_cloud.png`、`tracker_data/dashboard_v2_final_mobile_apps.png`、`tracker_data/dashboard_v2_final_mobile_evidence.png`
- Finance bridge screenshots: `tracker_data/dashboard_v2_finance_bridge_overview.png`、`tracker_data/dashboard_v2_finance_bridge_evidence.png`、`tracker_data/dashboard_v2_finance_bridge_mobile_overview.png`
- Source caption screenshots: `tracker_data/dashboard_v2_source_captions_overview.png`、`tracker_data/dashboard_v2_source_captions_price.png`、`tracker_data/dashboard_v2_source_captions_cloud.png`、`tracker_data/dashboard_v2_source_captions_apps.png`、`tracker_data/dashboard_v2_source_captions_evidence.png`、`tracker_data/dashboard_v2_source_captions_mobile_overview.png`
- Token change screenshots: `tracker_data/dashboard_v2_token_change_apps.png`、`tracker_data/dashboard_v2_token_change_apps_expanded.png`、`tracker_data/dashboard_v2_token_change_mobile_apps.png`
- Single-page trend board screenshots: `tracker_data/dashboard_v2_single_trend_board_full.png`、`tracker_data/dashboard_v2_single_trend_board_mobile_full.png`
- Public source expanded trend board screenshots: `tracker_data/dashboard_v2_public_sources_trend_board.png`、`tracker_data/dashboard_v2_public_sources_trend_board_mobile.png`
- Analyst + Swiss polish screenshots: `tracker_data/dashboard_v2_analyst_swiss_polish_desktop.png`、`tracker_data/dashboard_v2_analyst_swiss_polish_mobile.png`
- Latest HTML dashboard screenshots: `output/playwright/html_trend_dashboard_20260708_desktop_r2.png`、`output/playwright/html_trend_dashboard_20260708_mobile_r2.png`
- 当前判断：`quality_gate=WARN`、`decision_state=No Signal`、`confidence=15%`。这代表数据已经真实接入，但还不能判断“算力稀缺溢价破裂”。
- HTML 版补充说明：当前首选交付面是 `html_dashboard/ai_compute_trend_board.html`，不是继续修旧 Streamlit tab。HTML 版用顶部全局日期控件刷新所有图，每张图 legend/source 开关会重算该图坐标轴；OpenRouter 官方 daily token/app rankings 因缺 `OPENROUTER_API_KEY` 未写入生产表，页面改用 `Socialpranker/token-history` archive 和 OpenRouter public frontend proxy，并明确标注 stale/sparse/proxy。
- Dashboard 已收口为单页 `AI Compute Price & Cost Trends`，不再使用 `总览 / 价格 / 云厂商 / 应用 / 证据库` tab，也不再默认展示长文字判断、投资桥或折叠解释。页面只按 `GPU 与云实例价格`、`OpenRouter/Token/模型成本`、`云厂商 CAPEX 官方说明` 三段展示带时间或明确日期的价格/成本/商业化信息：GPU 租赁价格趋势、GPUMarkets fixing 与 30D delta、GPUPerHour/Vast/RunPod 当前可用订单薄、官方云 GPU 实例价格、OpenRouter token 用量、OpenRouter activity proxy、Token 输出价格趋势、模型输出价、多模态生成成本、ARR/商业化信号。底部 CAPEX 表用静态表格列出美国 5 家 source-backed CAPEX 与官方说明，并保留中国厂商 source-backed / manual-verified 口径限制，不插入估算值。
- 四轨监控已接入 GPUMarkets fixings CSV、Vast bundles API、RunPod gpuTypes GraphQL、ComputePrices GPU/LLM/Trend API、GPUPerHour Offers API、GPUs.io Trends、AIMultiple GPU Index、GetDeploying GPU pages、OpenRouter Models API、LiteLLM model_prices JSON、models.dev API、CostGoat LLM API comparison、ARR.club public homepage、Ramp AI Index public article、BytePlus ModelArk pricing、seedance2.ai public pricing、Azure Retail Prices API、AWS current Spot JSON。当前 dashboard extract 包括 `gpuRental=114`、`gpuMarketFixing=10`、`orderbook=33`、`cloudInstance=18`、`openrouterProxy=26`、`tokenPrice=67`、`modelPrice=16`、`multimodal=44`、`commercialization=26`。GPUMarkets 当前是 fixing + delta，不声称完整历史；Vast/RunPod 当前是订单薄/底价快照，后续靠本地快照积累历史。官方事件层现在有 `production_official_events=9`：META 2026 capex `$125-145B` vs prior `$115-135B`、GOOGL Cloud backlog `>$460B`、ORCL RPO `$638B`、AMZN TTM PPE increase `$59.3B` tied to AI、MSFT demand still exceeds supply。硬件现货 GPU 成交价、GCP 官方 spot/API key、AWS 90 天 spot history、Vast host market metrics history、ARR 历史与 source links、Artificial Analysis API、Sacra、SemiAnalysis GPU Pricing Index 仍是缺口，页面以 quality events 暴露，不插入假数据。

Demo seed 仅用于本地演示和旧测试，不能作为生产判断，也不会被 production report 当作证据：

```bash
# DEMO ONLY：加载旧 seed 数据并构建 seed 派生 L2/L3/CSI
python3 tracker_v2.py init --demo-seed

# DEMO ONLY：运行旧硬编码样例更新
python3 tracker_v2.py update --demo
```

---

## 当前 production dashboard 功能

| 模块 | 数据表 | 当前价值 | 不能做什么 |
|---|---|---|---|
| 当前判断 | `production_*` + `data_quality.py` | 给出 `No Signal / WARN / confidence`，避免把缺口包装成结论 | 不能在官方确认不足时输出 cracking call |
| 二级市场决策读数 | `production_market_facts` + quality gate | 分硬件链、云厂商、应用/API、ARR、总判断写出证据、含义和反证条件 | 不替代交易建议，不在 WARN 状态下输出方向性 call |
| GPU 租赁/spot | `production_market_facts` | ComputePrices 聚合租赁价横截面，含 spot/on-demand/reserved | 不取代 gpus.io 的完整交互表 |
| 当前可用 GPU 订单簿 | `production_market_facts` | GPUPerHour OpenAPI 的 `available=true` offer，含 provider、region、GPU count、security tier、host specs | 不是硬件现货成交价，也不是 30/60/90 天趋势 |
| GPU 租赁趋势 | `production_market_facts` | ComputePrices public tier H100/H200/B200 7 日趋势 | 不是 30/60/90 天 regime call |
| GPUs.io 30/90 日 movers | `production_market_facts` | 浏览器渲染 gpus.io trends，跟踪 material movers 的 30d/90d delta | 不是完整 API，H100 不在 movers 不等于 H100 没变化 |
| 官方云实例价格 | `production_market_facts` | Azure Retail Prices + AWS current Spot，按 VM-hour 展示 | 不按 GPU 数量强行归一化，不等同 neocloud per-GPU-hour |
| Token/API 价格 | `production_market_facts` | ComputePrices LLM + OpenRouter 当前价格；应用页展示 output token 单价离散首尾变化 | 不是连续价格曲线，仍需要 Artificial Analysis、分任务质量验证和更稳定历史 |
| 模型质量/价效比 | `production_market_facts` | CostGoat public Next.js data，含质量分、输入/输出价、value score | 不是 Artificial Analysis；Theozard/CostGoat 口径需作为公开 proxy 使用 |
| AI 应用商业化 | `production_market_facts` | ARR.club public homepage 公开信号 + Ramp AI Index 企业付费采用率 | 不是完整 ARR 历史，也不是 Sacra 深度财务；Ramp 采用率不等于收入 |
| 多模态生成成本 | `production_market_facts` | BytePlus Seedance 官方 token 单价 + seedance2.ai credits 表 | 官方 USD/token 与第三方 credits 不能混算，不能直接等同单次视频美元成本 |
| CAPEX actual | `production_capex_actuals` | SEC companyfacts 官方 CAPEX actual | CAPEX 里包含非 AI 支出，需要 earnings call 修正 |
| 官方 CAPEX/RPO 事件 | `production_official_events` | SEC/官方 source-backed 事件覆盖 MSFT/AMZN/GOOGL/META/ORCL，用来反证价格层是否足以推出 capex cut | 不代表所有 guidance 历史，也不等同应用层需求兑现 |
| 失败源/授权源 | `production_data_quality_events` | 明确暴露 ORNN、GCP、AWS history、ARR Pro/Sacra 等缺口 | 不能用估算填补缺口 |

---

## 🏗️ 数据模型

在 v1 的 5 张表基础上，v2 新增 4 张表：

| 表名 | 说明 | 数据频率 |
|------|------|----------|
| `gpu_prices_daily` | GPU 价格（H100/A100/B200 等） | 日度 |
| `capex_quarterly` | 云厂商季度 CAPEX actuals | 季度 |
| `ocpi_daily` | Ornn H100 算力指数 | 日度 |
| `csi_history` | 复合稀缺性指数历史 | 日度 |
| `signals` | 生成的投资信号 | 事件驱动 |
| `capex_guidance` | **v2 新增** CAPEX 指引 + revision 跟踪 | 季度事件 |
| `earnings_calendar` | **v2 新增** 财报日历 | 季度事件 |
| `capex_daily_implied` | **v2 新增** L2 Forward Curve（日度摊薄） | 日度 |
| `capex_nowcast` | **v2 新增** L3 Nowcast（高频 proxy） | 日度 |

---

## 🧪 测试

```bash
# 单元测试（28 项）
python3 -m pytest test_suite/test_unit.py -v

# 集成测试（13 项）
python3 -m pytest test_suite/test_integration.py -v

# 全部测试
python3 -m pytest test_suite/ -v
```

**测试覆盖场景**：
- 6 种 mock 数据场景（baseline / guidance_cut / guidance_raise / missing_data / frequency_mismatch / spike）
- 频率转换（step_hold / linear_interp / forward_curve）
- CSI 边界、权重、regime 阈值
- Edge cases（空数据库、单条记录、重复数据、极端 spike、负 CAPEX）
- 端到端 pipeline（完整数据流验证）
- Dashboard SQL 查询验证
- 性能测试（2 年数据插入 + 聚合查询 < 1s）

---

## 📁 文件结构

```
tracker_v2/
├── tracker_v2.py                    # 核心 CLI（init/update/report/status/align）
├── dashboard_v2.py                  # Streamlit 双时间轴看板
├── ai_compute_tracker.db            # DuckDB 数据库（9 张表）
├── requirements.txt                 # Python 依赖
├── research_brief.md                # 技术方案文档（研究员产出）
├── README_v2.md                     # 本文件
├── tracker_data/                    # 数据目录
│   └── report_v2_*.txt              # 每日报告
└── test_suite/                      # 测试套件
    ├── test_unit.py                 # 28 项单元测试
    ├── test_integration.py          # 13 项集成测试
    ├── test_data_generator.py       # Mock 数据生成器
    ├── test_report.md               # 测试报告
    └── dashboard_checklist.md       # 视觉验证清单
```

---

## 🔧 CLI 命令

```bash
python3 tracker_v2.py init --db ai_compute_tracker_production.db # 初始化生产库 schema only，不加载 seed
python3 tracker_v2.py init --demo-seed                      # DEMO ONLY：加载旧 seed + L2/L3 + CSI
python3 tracker_v2.py update --production --db ai_compute_tracker_production.db                   # 一键生产闭环：采集四类源、质量门、source-backed report
python3 tracker_v2.py update --production --only gpu-prices --db ai_compute_tracker_production.db # 只刷新指定生产 target
python3 tracker_v2.py update --production --only capex-actuals --db ai_compute_tracker_production.db
python3 tracker_v2.py update --production --only official-events --db ai_compute_tracker_production.db
python3 tracker_v2.py update --production --only public-proxy-prices --db ai_compute_tracker_production.db
python3 tracker_v2.py update --production --only market-facts --db ai_compute_tracker_production.db
python3 tracker_v2.py update --demo                         # DEMO ONLY：运行旧硬编码样例更新
python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db            # 校验生产数据合同
python3 tracker_v2.py report --production --db ai_compute_tracker_production.db                   # 只读 production_*；seed-only 时 FAIL_SEED_ONLY
python3 tracker_v2.py status --quality --db ai_compute_tracker_production.db                      # 查看 source_type 和 production 质量计数
python3 tracker_v2.py reset-production-db --confirm-real-data-reset --db ai_compute_tracker_production.db  # 只清 production_* 表
AI_COMPUTE_TRACKER_DB=ai_compute_tracker_production.db streamlit run dashboard_v2.py               # production-first dashboard
python3 tracker_v2.py status                                # 查看 legacy + production 表状态
python3 tracker_v2.py align                                 # DEMO/legacy：手动触发 L2/L3 重建
```

### 生产路径退出语义

| 状态 | 退出码 | CLI 行为 |
|---|---:|---|
| `PASS` | 0 | 可以输出 source-backed directional decision。 |
| `WARN_CAPEX_CONFIRMATION_MISSING` | 0 | 可以生成 evidence report，但不输出 `Scarcity Premium Cracking`。 |
| `WARN_GPU_ONLY` | 0 | 可以说明价格层观察，confidence cap 40%，不输出 regime call。 |
| `WARN` | 0 | 暴露 source failure / coverage warning，不输出无依据 cracking call。 |
| `FAIL` | 非 0 | 不输出投资结论，只解释缺什么和哪些源失败。 |
| `FAIL_SEED_ONLY` | 非 0 | 只说明当前是 seed/demo 或无生产证据，不把 seed 包装成生产数据。 |

`update --production` 的全量路径会跑四个生产 target 后统一收口；中间遇到 403/429、解析失败、授权源不可用等，会记录并打印源级 failure code，然后由最终质量门决定退出码。`update --production --only ...` 只运行指定 target，适合单源刷新或排障。

---

## ⚠️ 数据局限性与声明

1. **GPU 价格市场高度分散**：47+ 提供商，不同计费模式难以完全统一
2. **CAPEX 口径**：各公司财报中 CAPEX 可能包含非 AI 支出，需 earnings call 的 qualitative 修正
3. **Ornn OCPI**：完整数据需要 Bloomberg Terminal 订阅或 Ornn 直接授权
4. **云厂商 spot instance 官方价格**：Azure Retail Prices 和 AWS current Spot 已接入横截面；AWS 90 天 spot history 仍需要签名 API，GCP Pricing API 仍需要 key。未形成连续历史前，不能把云 spot 拐点当作已确认信号。
5. **硬件现货 GPU 价格**：尚未接入 eBay/渠道报价/二手成交等硬件买卖成交源；GPUPerHour 已补当前可用租赁订单簿，但这不是硬件二手成交价。
6. **AI 应用 ARR**：ARR.club 免费公开页只提供部分 public ranking；完整 ARR 历史、source links、Sacra 深度财务需要授权。
7. **多模态生成成本**：BytePlus 官方价格是 `USD/1M tokens`，seedance2.ai 是第三方 `credits` 扣费表；当前只用于成本横截面观察，不做 USD 总成本合成。
8. **模型价效比**：CostGoat public page 可作为无授权公开 proxy；Artificial Analysis API 仍需要账号/API key，未被 CostGoat 替代。
9. **L2 Forward Curve**：假设 guidance 在周期内均匀发生，实际可能有季节性偏差
10. **L3 Nowcast**：基于 GPU 价格 momentum 的简单 proxy，非结构性模型
10. **本系统仅供研究参考**，不构成投资建议。所有数据为第三方市场数据。

---

## 🗺️ 路线图

- [x] v1: MVP（基础三指标 + CSI + Streamlit）
- [x] **v2: 频率对齐（L1/L2/L3 + 双时间轴 + 领先/滞后分析）** ← 当前
- [ ] v3: 接入 Bloomberg API 获取 OCPI 实时数据
- [ ] v4: Earnings Call Transcript NLP（自动提取 guidance 变化）
- [ ] v5: 多因子回归模型（GPU price vs CAPEX vs Stock returns）
- [ ] v6: Web 部署 + 用户订阅 + 飞书/钉钉推送

---

> **核心观点**：v2 通过 L1→L2→L3 频率对齐，让季度 CAPEX 和日度 GPU 价格首次在同一个连续时间轴上可对比。当 L2 Implied 和 L3 Nowcast 之间出现显著 gap，或 L1 Actual 与 L2 Guidance 大幅偏离时，这就是"算力稀缺逻辑"出现裂痕的最早期信号。
