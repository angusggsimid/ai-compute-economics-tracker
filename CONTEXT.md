# CONTEXT

## 2026-07-13 项目迁移至独立工作区

- AI Compute Economics 的代码、真实数据、快照、研究资料、GitHub/Vercel 配置和独立 Sites 工程已从混合项目目录迁入 `/Users/agg/Documents/AI Compute Economics`。
- 原路径 `/Users/agg/Documents/New project 2/tracker_v2` 保留为指向新项目的兼容链接，避免旧书签、命令和本地服务失效。
- Codex 每日 Sites 同步任务改用新项目作为工作目录；GitHub 仓库、Vercel 项目、Sites project id 和线上固定地址均保持不变。
- 两份此前散落在外部目录的用户研究已归档到 `research/ai-compute-tracker-sources.md` 与 `research/credential-free-data-architecture-research.txt`。
- 迁移验收时发现 GitHub 部署依赖遗漏导致 CAPEX 使用上一版数据，已补齐依赖；真实刷新四源全部 `fresh`，CAPEX 24 条、失败来源 0。
- 同时修复当前未完成周进入 OpenRouter 曲线造成的尾部假跌；正式序列只保留 52 个完整周，结束于 2026-07-06。
- 目标回归 33 passed；浏览器为 13 个 SVG、32 条 CAPEX 表格行、无横向溢出和控制台错误。

## 2026-07-12 删除固定模型牌价并改为活跃组合

- 用户确认删除整个 `Token价格` section，以及固定代表模型 output/input 两图；正式构建器不再要求或读取 LiteLLM 固定模型历史文件。
- 原 `OpenRouter 头部模型更替` 改为 `OpenRouter 活跃模型组合更替`：52 根独立周柱，每周按 9 个公开命名模型和 `Others` 的真实 Token 份额堆叠，不连接跨周面积，因此未披露模型不会被伪造为 0。
- 最新周下方显示全部 9 个活跃模型及 `Others`，共 10 项；桌面 5 列 × 2 行，移动端 2 列，避免空白占位。
- 页面从 15 个 SVG 收口到 13 个 SVG：12 张默认时间序列图 + 1 张按需单模型历史；旧标题和 `Token价格` section 均为 0。
- 完整 dashboard 回归测试 40 passed；浏览器组合图 520 个真实 segment、52 周、最新 10 项、0 空图、0 console error/warn；390px 下为 2 列且无横向溢出。
- 本地查验地址：`http://127.0.0.1:8767/ai_compute_economics_monitor.html`。

## 2026-07-12 GPU 与活跃模型价格体系完成

- 用户批准一次性完成六项：Foundry 三代 GPU 中位价/区间/30日均线/供应商变更，availability 分面且 H200 三点不连线，GPU 代际溢价；OpenRouter 活跃模型价格层级、活跃组合 input/output 牌价和按需单模型价格历史。
- Foundry 价格从来源混合平均改为每日 `provider_prices` 中位数，保留 source low/high、provider count 和 tracker 计算的 30 日均线；三代卡各 210 日，供应商数量变化在图内垂直标记。
- 新增 `scripts/backfill_openrouter_active_prices.py`：OpenRouter models canonical slug 映射到 OpenRouterList 871 模型账本，保留原始快照、SHA-256、抓取时间和许可证风险说明。
- 活跃集合使用最近 4 个完整周命名模型 Token 量，累计覆盖 80%、最多 12 个；当前 8 个，DeepSeek R1 不再进入主视图。免费只在 `:free` 明确时记零，其余未映射与 Others 保留为灰色 Unknown。
- 正式页面默认 14 张时序图，另有 1 张按需单模型历史。活跃价格层级 52 周每周加总 100%；组合 input/output 各 52 周点 + 49 个 4W MA 点，tooltip 显示 coverage。
- 目标数据与 dashboard 回归测试 40 passed；浏览器 15 SVG、0 空图、0 console error/warn；H200 availability 3 点、0 path；日期 2026-06-01 后 basket points 101→12、premium points 420→82；390px 宽度 390px。
- 本地查验地址：`http://127.0.0.1:8767/ai_compute_economics_monitor.html`。

## 2026-07-12 Foundry Signals GPU 历史接入

- 用户明确选择 Foundry Signals 的 GPU Price 与 GPU Availability 数据进入正式页面。
- 新增 `tracker_v2/scripts/backfill_foundry_signals.py`，抓取两个无需凭证的公开端点，保留原始快照、SHA-256、抓取时间和标准化历史文件；接口或 schema 变化会直接失败，不静默沿用假数据。
- 正式单页 GPU 区改为 Foundry 两张独立时间图：H100/H200/B200 日度混合租赁价，以及可用率历史。价格 tooltip 保留 low/high；availability 允许月度点连续显示。
- 数据边界：Foundry 没有公开 API 稳定性承诺或明确数据许可证，网站称数据为 illustrative，且供应商覆盖曾变化；页面将其标为第三方公开代理，不作为官方成交指数。
- OpenRouterList 经核验不是可调用服务 API，而是 GitHub 静态 JSON/CSV；公开读取无需 key/费用，历史账本包含模型首末出现日期、是否仍存在、input/output 每百万 token 调价点，但许可证文件仍有占位符，因此暂不作为核心生产数据源。

## 2026-07-12 数据语义审计与正式页面收口

- 用户指出模型厂商份额中 OpenAI/Google/Qwen 被显示为 0、集中度/免费份额/工具活动缺少投资含义、GPU/云端历史过短、Token 成本存在缺口。
- 核验确认 OpenRouter frontend 周榜只单列少量头部模型和 `Others`；未单列厂商实际份额未知，旧图把未知当零，已从正式页面删除。
- 正式页面由 10 图收敛为 5 图：52 周 OpenRouter Token 总量、52 周公开 Top 3 模型更替、53 周固定模型 output/input 牌价、10 日 GPU 聚合租赁价；CAPEX 保留底部原频率表。
- 删除集中度、免费模型份额、工具/图像活动、4 快照订单薄、4 快照云价、使用结构加权成本和价格匹配覆盖率。数据仍留在生产/审计层，不作为主产品证据。
- 新增 `scripts/backfill_litellm_key_model_prices.py` 和 `tracker_data/backfills/litellm_key_model_prices_1y.json`，按 53 个 Git as-of commits 重建固定模型牌价；DeepSeek Chat output 从 `$1.70/1M` 降至 `$0.42/1M`，其余四个代表模型在覆盖期内持平。
- 长期数据边界：真实 OpenRouter 厂商份额需要 API key；GPUs.io 12M/ALL price history 需要 Pro key；AWS Spot 官方只回看 90 天且需要凭证；Azure retail catalog 不是市场 Spot 历史。
- 验证：目标测试 3 passed；1440px/390px 无横向溢出；日期切到 2026-01-12 后 Top 3 数字和所有时间轴同步更新；本地地址仍为 `http://127.0.0.1:8767/ai_compute_economics_monitor.html`。

## 2026-07-12 时间序列产品重构

- 用户明确纠正产品目标：主产品必须沿时间轴观察 AI 需求、GPU/云算力价格、Token 单位成本和模型份额迁移，不能再以最新截面、准备度或事件柱图作为主体。
- 正式页面已重写为六张时间序列图：OpenRouter 周度 Token 总量、厂商可见份额、H100/H200/B200 日租赁价、可用 GPU 报价数量、同 SKU 云实例价格指数、OpenRouter 使用结构加权 Token 单价；CAPEX 只保留底部原频率事件表。
- 新接入 OpenRouter 页面公开 `model-rankings-chart`：19 个周度点覆盖 2026-03-02 至 2026-07-06，生产底表保留每周模型、厂商、Others 和总 Token 量。
- 新增 LiteLLM 历史价格回填：按周匹配当时 commit 的模型价格目录；成本图只显示命名模型价格匹配覆盖率 >=35% 的周，避免低覆盖周伪精确。
- 云价格按同一 SKU 首个抓取日=100 展示，tooltip 保留真实 USD/VM-hour；不同 VM 规格不再在绝对价格轴上互相压缩。
- 页面支持 3M/6M/1Y/全部、开始/结束日期和逐图图例开关，筛选后所有坐标轴按可见数据重算。
- 正式构建器：`tracker_v2/html_dashboard/build_time_series_dashboard.py`；数据快照：`tracker_v2/html_dashboard/v4/time_series_snapshot.json`；正式页面路径不变。
- 验证：目标测试 24 passed；浏览器桌面与 390px 移动端通过，日期筛选和图例重算通过，控制台无产品错误。
- 用户进一步指出份额图表类型、四快照图误导和图表数量偏少。复核发现生产库已有 52 周 OpenRouter 数据，但页面只读取了 19 周；另有全局结束日期取错，导致 GPU 报价和云价格 4 个快照只显示前 2 个。
- 已将 OpenRouter 扩展为完整 52 周，并新增厂商 100% 堆叠构成、Top 1/Top 3 集中度、免费模型可见份额、工具调用与图像处理活动；正式页面共 10 张图。
- GPU 报价与云价格明确标记为 4 次快照，使用大点和虚线辅助对照，不再包装成成熟趋势；Token 成本新增 19 周价格匹配覆盖率柱，逐周解释价格线断点。
- 全局最大日期改为从所有数据集计算，当前为 2026-07-12；新增回归测试防止最新稀疏快照再次被日期控件隐藏。

## 2026-07-11 算力 Tracker Phase 6 已完成

- 正式规划确认只有 Phase 0-6，共七个阶段。此前口头扩展的证券日线/事件收益/证券映射不是产品范围，相关代码、表和 4,940 条临时日线已完整回退。
- Phase 6 投资场景验收通过：六个核心问题均能得到可观察事实或明确不可判断，不用文案替代证据。
- Commitment 补入商业化证据卡：26 个公开 ARR/adoption series，真实正修订 0、负修订 0；重复快照不算变化。
- H100 depth 与 OpenRouter demand 完成到 raw snapshot/hash 的逐行追溯；所有卡片、图和表保留可打开的查询来源。
- Demand legend 重算通过：可见曲线 2 -> 1，图例状态 true -> false；标准来源弹窗、1440px、390px 和横向溢出检查全部通过。
- Phase 1-6 正式链路测试 68 passed、0 failed；验收报告为 `tracker_v2/docs/PHASE6_INVESTOR_ACCEPTANCE_2026-07-11.md`。
- 最终状态：产品验收 PASS；投资拐点仍是 Observing / partial evidence。GPU fixed panel 只有 3/10 日，不能画假趋势或升级判断。
- 产品边界：只监控 AI compute economics，不接证券价格、股票日线、组合仓位或交易收益率。

## 2026-07-11 算力 Tracker Phase 5 已完成

- 正式产品入口切换为 `tracker_v2/html_dashboard/ai_compute_economics_monitor.html`；旧 `ai_compute_trend_board.html` 仅作历史参考。
- 新增 `build_monitor_artifact.py` 与 `v3/artifact.json`，所有卡片、图表、表格均保留标准来源查询、过滤口径和 reviewed snapshot。
- 单页只有六个互不重复展项：Compute Price、Market Depth、Cloud、Model Economics、Demand、Commitment；各自保留自然频率，不设跨频率全局日期控件，不合成总分。
- Supply 当前只有 3/10 个有效日，页面明确展示证据积累门槛，不画假 H100/H200/B200 价格线；订单薄、云 VM-hour、模型真实调价事件、OpenRouter 4W MA、同季度 US CAPEX 和 US/China 事件账本均已接入。
- OpenRouter 两条 4W MA 各自以首个完整窗口=100；US CAPEX 柱状图只比较 2026-03-31 同期四家公司，Oracle FY2026 年度值留在事件账本，避免年/季混比。
- 可移植 HTML 标准验收通过：validation/package/verification passed，1440px/390px、来源弹窗、横向溢出均通过；逐段浏览器截图确认六图进入视口后均正常渲染。
- 修复 `set_default_db_path(None)` 未清理测试环境变量的问题；Phase 1-5 正式链路测试 63 passed、0 failed。完整 legacy suite 剩余 2 个旧报告断言仍要求已废止的固定总分语义，未恢复。
- 本地查验地址：`http://127.0.0.1:8767/ai_compute_economics_monitor.html`。

## 2026-07-11 算力 Tracker Phase 4 已完成

- 新增 `thesis_state.py`，只读取 canonical/series/event/freshness 数据层，不读取 legacy CSI、`gpu_prices_daily` 或 CAPEX 日频插值。
- 四个状态独立输出 `Unobservable / Observing / Trend / Inflection Watch / Confirmed`，不合成总分、不输出固定 confidence。
- Supply Price 当前 `Observing`：237 个 exact series，但 fixed matched panel=0；升级必须同时满足 30D 幅度、至少两个 GPU 的广度和订单簿深度确认。
- Capacity 当前 `Observing`：只有 3 个有效订单簿日期，first offers=192、latest=232，但不足 10 日，不能称趋势。
- Demand 当前 `Trend`：10 个 chart-ready OpenRouter proxy series；工具调用 4 周 +27.3%，图像处理 +11.7%；因 official inflection series=0，blocker=`proxy_not_inflection_eligible`。
- Commitment 当前 `Observing`：CAPEX actual 5、官方事件 9、中国 CAPEX 5、商业化事件 26；sequential CAPEX companies=0。自动识别 positive guidance companies=1、negative=0，构成资本开支未转弱的反证。
- 新 CLI：`state-report --production` 输出版本化 JSON/Markdown、latest 文件和状态 transition。每条 evidence 保留 series/event/observation id。
- 每日 runner 已接入状态报告；数据更新后自动记录四时钟状态和升级/降级。
- 验证：Phase 1-4 相关测试 55 passed；runner audit-only SUCCESS；JSON 中不存在 composite score/confidence 字段。
- 下一阶段为 Phase 5：从零重写单页 UI，只读取新的 line/event/state views。

## 2026-07-11 算力 Tracker Phase 3 已完成

- GPUPerHour 采集器现在同时保留原订单簿，并生成 exact-config 日度价格：billing、variant、region、GPU count、security、deployment、provider 和 GPU family 全部进入稳定身份。
- 同配置多 offer 按日计算 median，notes 保留 min/max/offer count/offer ids；unknown variant/region 和 gpu_count=0 不得进入 matched series。
- 从 27 个本地结构化 GPUPerHour JSON 快照回填 477 条事实，覆盖 2026-07-06、07-08、07-11。当前 exact-config series=237；至少 2 日=146；3 日=94；chart-ready=0。
- 新增 `source_collection_policy`、`source_freshness`、`pipeline_health_latest`、`series_collection_gap`。freshness 使用 UTC 比较，修复本地时区导致 age 多算 8 小时的问题。
- 第一轮真实 runner 成功：market-facts rows_loaded=16,308，quality_events=29；核心 GPUPerHour/RunPod/Vast 均 fresh。ComputePrices GPU catalog/trend 两个 secondary policy stale，未伪装为 fresh。
- 新增 `scripts/run_phase3_daily.py`：并发锁、20 分钟超时、JSON 日志、dry-run、audit-only、核心源 SLA 失败退出。日志位于 `tracker_data/phase3_runs/`。
- launchd plist 模板已通过 `plutil -lint`，但未安装到 `~/Library/LaunchAgents`，符合系统任务安装需确认的规则。
- 验证：Phase 1-3 相关测试 49 passed；当前单页 HTML 已用最新生产库重建。
- 下一阶段为 Phase 4 独立投资命题状态机；Phase 3 runner 需要持续每日运行，exact series 达 10 日后才自动进入 line-ready。

## 2026-07-11 算力 Tracker Phase 2 已完成

- 新增稳定序列层：`canonical_market_observation`、`canonical_observation`、`series_definition`、`series_quality`、`line_ready_observation`、`event_observation`、`matched_panel_candidate/member/index`。
- `series_id` 不使用 run id、抓取 URL 或快照路径；同一经济序列不会因采集技术变化断裂。美国 CAPEX actual 与官方 guidance/RPO 已从独立生产表纳入统一事件层。
- chart、inflection、90D 三层资格分开；日频至少 10 日才可画，30D 至少 20 个有效日，90D 至少 60 个有效日，覆盖率均要求 >=80%。周频未完成周期在 canonical 层剔除。
- 公开 proxy 可以画线但不能触发 inflection。OpenRouter 原始最新周 2026-07-06 未完成，line-ready 最新为 2026-06-29。
- 生产结果：14,413 个 series definition；13 个 chart-eligible series（3 个 ComputePrices aggregate trend、10 个 OpenRouter proxy）；0 个 inflection、0 个 90D。
- GPU matched-panel 当前诚实为空：224 个普通租赁序列缺 exact variant/region/GPU count/billing，3 个 ComputePrices aggregate trend 的 provider count 波动，reason=`aggregate_composition_not_fixed`。
- 事件层：token price change 61 条；美国 CAPEX actual 5 条；官方 guidance/RPO/capacity event 9 条；中国 CAPEX 5 条。重复价格快照不重复生成 change event。
- 验证：相关数据合同、来源和 dashboard 查询测试 46 passed。下一阶段为 Phase 3 持续采集与历史回填，重点是从现在起积累 exact-config GPU venue series。

## 2026-07-11 算力 Tracker Phase 0/1 已完成

- 唯一正式项目入口已收敛到 `tracker_v2`；当前产品为单页 HTML，生产库为 DuckDB `ai_compute_tracker_production.db`。旧 `compute-tracker`、Streamlit `dashboard_v2.py` 和 legacy CSI 已标记 archive/demo。
- 新增 `production_market_facts_canonical`：按日期、轨道、实体、指标、数值、单位、维度、供应商和 source id 去除完全重复观测，但保留不同价格，避免误删真实配置差异。
- 新增 `production_market_facts_analysis`：隔离 production ineligible、非正价格和 RunPod MIG 切片；原始表不删除。
- 新增 `production_data_quality_events_latest`：125 条历史质量事件收敛为 23 个 affected key 的最新状态。
- RunPod parser 已阻止 MIG、不可用 cloud tier 和 `<=0` 价格进入新事实；被隔离数量通过质量事件暴露。
- HTML 已改读 analysis view；GPU 主趋势改为 ComputePrices 同源同口径 10 日序列；OpenRouter 自动排除未完成周；GPUMarkets 30D delta 字段修复；token 趋势要求至少 5 个不同日期。
- 生产审计：raw 18,135；canonical 17,908；analysis 17,302；隔离 606；canonical 完全重复组 0；analysis RunPod 非正价格 0、MIG 0。
- 验证：目标数据合同、采集器与 dashboard 查询共 39 passed；HTML 已重建。桌面和 390px 移动端均无溢出、无 console error/warning；日期筛选会同步刷新 KPI 和图表数据点。当前查验地址 `http://127.0.0.1:8766/ai_compute_trend_board.html`。
- 下一阶段是 matched-panel、series registry、独立频率状态机与拐点判断，不继续给旧页面加壳。

## 2026-07-10 算力 Tracker 重立项审查

- 已完成对旧 `compute-tracker`、Streamlit `tracker_v2`、单页 HTML、生产 DuckDB、数据合同、决策引擎、数据源审计和历次修复记录的回顾。
- 正式重构构思与计划：`tracker_v2/docs/PROJECT_REFRAME_2026-07-10.md`。
- 核心结论：保留采集器、快照、provenance、生产隔离和解析测试；归档旧 UI 与 legacy CSI；重建 canonical series、matched-panel、独立频率状态机和单页 chart-first 产品。
- 当前关键审查结果：`production_market_facts=18,135`，其中 `token_price=14,383`；token 单序列最多 3 个日期；GPU rental 同 provider/variant 最多 4 个日期；CAPEX actual 每家公司只有 1 个季度；quality events 125 行但只有 23 个 affected keys；完整语义重复 477 行。
- 已确认当前产品问题：RunPod 零价/MIG 污染、GPUMarkets 30D delta 渲染为 n/a、未完成 OpenRouter 周导致尾部假跌、旧 `DecisionEngine` 不读取新增 `production_market_facts`。
- 本轮没有改产品代码；只完成审查、重立项方案、项目记录和后续验收标准。

本次更新：

- 继续执行 active goal，把 `tracker_v2` 首选交付面固定为单文件 HTML：`tracker_v2/html_dashboard/ai_compute_trend_board.html`，不回到旧 Streamlit tab。
- 数据层新增三类真实公开源：GPUMarkets `fixings.csv` 写入 `gpu_market_fixing`，Vast bundles API 写入 `vast_offer_snapshot`，RunPod `gpuTypes` GraphQL 写入 `runpod_gpu_price_snapshot`。本轮生产更新 `inserted_market_facts=17,280`，当前 `production_market_facts=18,135`，质量事件 `125`。
- Dashboard extract 当前核心样本：`gpuRental=114`、`gpuMarketFixing=10`、`orderbook=33`（GPUPerHour/RunPod/Vast.ai）、`cloudInstance=18`、`openrouterProxy=26`、`tokenPrice=67`、`modelPrice=16`、`multimodal=44`、`commercialization=26`。
- HTML 展示顺序改为三段十图：GPU 租赁趋势、GPUMarkets fixing/30D delta、三源订单薄、官方云 VM-hour、OpenRouter token archive、OpenRouter activity proxy、token 输出价、模型输出成本、多模态成本、ARR/商业化信号，底部保留美国+中国 CAPEX 表和 quality events。
- 图表 renderer 修复：少于 3 个日期点只画点不连线；多于 5 条线不做终点直标，避免右侧标签堆叠；日期筛选和 legend/source 隐藏后坐标轴按可见数据重算。
- 已验证：`python3 -m py_compile data_sources/market_facts.py html_dashboard/build_html_dashboard.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py test_suite/test_data_quality.py test_suite/test_data_contract.py test_suite/test_report_quality.py test_suite/test_production_database_path.py -q`：53 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`。
- 浏览器 QA：桌面和 390px 移动端均为 10 张图卡、2 个表、12 个 SVG、0 个默认空图、控制台 0 error/warn、无横向溢出；日期筛选和订单薄 source legend 触发重绘。截图：`tracker_v2/output/playwright/html_trend_dashboard_20260708_desktop_r2.png`、`tracker_v2/output/playwright/html_trend_dashboard_20260708_mobile_r2.png`。
- 文档已更新：`tracker_v2/research/github_data_source_audit_2026-07-08.md`、`tracker_v2/research/dashboard_chart_contract_2026-07-08.md`、`tracker_v2/README_v2.md`、`tracker_v2/docs/FIX_LOG_2026-07-08.md`。
- 完整 `pytest test_suite -q` 曾运行 4 分 23 秒只完成 3 项后人工中断；本轮验收以目标相关的 53 项测试、生产更新、质量门和浏览器 QA 为准。
- 当前本地查验地址：`http://127.0.0.1:8765/ai_compute_trend_board.html`，对应服务仍在运行。

本次更新：

- 按用户要求停止在旧 Streamlit UI 上继续修补，改为先做 GitHub 数据源审计，再用生产库真实数据生成一个单文件 HTML 趋势 dashboard。
- 新增 GitHub 前五数据源审计：`tracker_v2/research/github_data_source_audit_2026-07-08.md`。结论是核心可用项目为 `BerriAI/litellm`、`infracost/infracost`、`runpod/runpod-python`、`vast-ai/vast-sdk`、`Socialpranker/token-history`；其中 RunPod/Vast/OpenRouter official rankings 当前缺 API key，不能写生产数据。
- 新增图表合同：`tracker_v2/research/dashboard_chart_contract_2026-07-08.md`。明确 10 张图和 CAPEX 表的数据源、频率、字段、验收标准和失败暴露方式。
- 新增 HTML 构建脚本与产物：`tracker_v2/html_dashboard/build_html_dashboard.py`、`tracker_v2/html_dashboard/ai_compute_trend_board.html`、`tracker_v2/html_dashboard/data/ai_compute_dashboard_extract.json`。HTML 使用嵌入数据 + 原生 SVG，不依赖 Streamlit；顶部日期范围会刷新所有图，每张图 legend 开关会按可见 series 重算坐标轴。
- HTML 真实数据覆盖：`production_market_facts=17,851`、OpenRouter frontend proxy 13 个周频点、token-history archive 12 个 daily 文件但按模型最大覆盖仅 3 天，页面已标注 stale/sparse；中国云 CAPEX 已显示 Alibaba Cloud、Tencent Cloud、Baidu AI Cloud、Huawei Cloud 和 ByteDance 缺口口径。
- 已验证：`python3 -m py_compile tracker_v2/html_dashboard/build_html_dashboard.py` 通过；`python3 tracker_v2/html_dashboard/build_html_dashboard.py` 成功；`python3 -m pytest tracker_v2/test_suite/test_dashboard_queries.py tracker_v2/test_suite/test_market_facts.py -q`：27 passed；Chrome Playwright 验证桌面 10 张图卡、2 个表、12 个 SVG、默认缺失卡 0、390px 移动端无横向溢出、日期筛选和 legend 隐藏会触发重绘、控制台 0 error/warn。
- 新截图证据：`tracker_v2/output/playwright/html_trend_dashboard_desktop.png`、`tracker_v2/output/playwright/html_trend_dashboard_mobile_default.png`。交付文件为 `tracker_v2/html_dashboard/ai_compute_trend_board.html`；QA 时临时使用 `http://127.0.0.1:8765/ai_compute_trend_board.html`，服务已关闭。

本次更新：

- 按用户强烈反馈重做 `tracker_v2` 单页 dashboard 的专业图表表达，不再以“有图、不报错、移动端不溢出”作为验收标准，而是以第三方投资人/商务场景可读性为验收核心。
- 主要修复 6 类问题：页面背景不再白茫茫，改为灰底 + 黑色 hero + IKB 蓝分区线；4 个 section 改成清楚的信息带；9 张图全部补齐图内标题、X/Y 轴标题、必要图例或直标、来源 caption；GPU/Token 等关键趋势图改为全宽；多线图图例从默认拥挤状态改为终点直标或底部横向图例；商业化双子图改为全宽并拉开子图间距。
- 图表安排现在是单页 4 段 9 张 exhibit：`GPU 现货与租赁价格`、`云厂商 GPU 实例价格`、`API、模型与应用端单位经济`、`云厂商 CAPEX 官方说明`。GPU 租赁趋势、云实例价格趋势、Token 输出价趋势和商业化信号均给足宽度，减少读图成本。
- 已验证：`python3 -m py_compile dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q`：27 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=17,520`。Browser 桌面验收：9 张图、9 个图内标题、9 组 X/Y 轴、缺失卡 0；390px 移动端验收：9 张图、4 个 section、无横向溢出。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_professional_final_top.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_professional_final_mid.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_professional_final_bottom.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_professional_final_mobile.png`。当前本地查验地址为 `http://127.0.0.1:8503`。

本次更新：

- 继续执行 active goal：按 `data-analytics:build-dashboard` 的多年数据分析师视角和 `guizang-ppt-skill` 的瑞士国际主义/简洁演示美学，对 `tracker_v2` 单页 dashboard 做图表表达和视觉 polish。
- 主要修复了 4 个会影响读者判断的问题：`聚合价格指数` 不再用单日时间轴，改成按 GPU 横向展示 low/median/high 价格区间；`ARR / 商业化信号` 不再把 ARR 和采用率混在同一 y 轴，改成上下两个子图；`模型输出价` 和 `多模态生成成本` 的长标签被压缩为可读短名；全局 Plotly 配色收成 IKB 蓝 + 灰阶为主，减少红/紫/绿等多色干扰。
- 细节上修复了云实例长期图日期轴全是 `Jan 1` 的问题，改成年份轴；token 图减少默认模型数并将来源口径改为 `public token catalogs`，避免只标 OpenRouter/ComputePrices。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q`：27 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=17,520`。Browser 桌面复验：9 张图、缺失卡 0、无毫秒时间戳、商业化图不混单位、无横向溢出；390px 移动端复验同样通过。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_analyst_swiss_polish_desktop.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_analyst_swiss_polish_mobile.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已按用户补充的信息源研究继续补齐 `tracker_v2`，不是再做 UI 外壳：新增真实生产源 `LiteLLM model_prices JSON`、`models.dev API`、`AIMultiple GPU Index`、`GetDeploying GPU page`，并把 Vast.ai API 明确作为 `AUTH_REQUIRED` 质量事件暴露。
- 新增 `gpu_rental_index` 生产轨道，用于 AIMultiple / GetDeploying 这种聚合指数和页面级价格区间。它不混入 `gpu_rental` 可报价/可租赁曲线，避免把指数源当成可成交订单。
- 单页趋势看板新增 `聚合价格指数` 图，并继续保持 `GPU`、`Cloud Instance`、`API & Applications`、`CAPEX` 四段。当前页面共有 9 张趋势/截面图，无旧 tab、无长文字解释、无折叠说明。
- 本轮真实生产更新写入 `inserted_market_facts=16,741`，当前生产库 `production_market_facts=17,520`。新增样本包括 AIMultiple H100 median `$2.99/GPU hr`、H200 median `$4.00/GPU hr`、B200 median `$6.11/GPU hr`、B300 median `$7.92/GPU hr`；GetDeploying 9 个 GPU 页面写入 low/high/offer count；LiteLLM 与 models.dev 写入 token price catalog，共覆盖 `token_price=14,368` 条生产 facts。
- 质量门仍是 `WARN`，不是完成信号。原因包括 ComputePrices 旧 429、ORNN/OCPI 未授权、AWS 90 天 spot history/GCP/Vast.ai/Sacra/Artificial Analysis/SemiAnalysis 等授权或订阅缺口。所有缺口都进入 quality events，没有插入估算值。
- 已验证：`python3 -m py_compile data_sources/market_facts.py dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py -q`：27 passed；`python3 tracker_v2.py update --production --only market-facts --db ai_compute_tracker_production.db` 成功；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`；Browser 验证桌面和 390px 移动端 9 张趋势卡、缺失卡 0、移动端无横向溢出。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_public_sources_trend_board.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_public_sources_trend_board_mobile.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 按用户最新要求，把 `tracker_v2` dashboard 从 `总览 / 价格 / 云厂商 / 应用 / 证据库` 五个 tab 收口为单页 `AI Compute Price & Cost Trends` 趋势看板；旧 query 参数不再进入旧 tab，统一展示同一页。
- 单页只保留时间相关价格/成本/信息图和底部 CAPEX 表，不再放投资判断桥、长文字说明或折叠解释。当前页面分为 `GPU`、`Cloud Instance`、`API & Applications`、`CAPEX` 四段。
- 新增或上提 8 张图：GPU 租赁价格趋势、GPUs.io 30/90 日价格变化、GPUPerHour 可用订单簿、官方云 GPU 实例价格、Token 输出价格趋势、模型输出价、ARR/商业化信号、多模态生成成本。
- 数据边界保持诚实：GPU 租赁、云实例、token 输出价使用多日生产事实；订单簿、ARR/商业化、模型价效比、多模态成本目前主要是截面图，不包装成连续历史；底部 CAPEX 静态表显示美国 5 家 source-backed CAPEX 和官方说明，中国云厂商行明确标注 `未接入 / 暂无 source-backed 生产事实`。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 24 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Browser 与系统 Chrome 验证单页 8 张 Plotly 图、旧 tab 导航 0、桌面/390px 移动端无横向溢出、无应用 console error。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_single_trend_board_full.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_single_trend_board_mobile_full.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 继续按目标推进 `tracker_v2`，本轮只补一个金融判断上最关键的缺口：应用页新增 `Token 价格变化` 主图，用已有真实 `token_price` 生产事实展示 output token 单价的首日到最新日变化。
- 图表口径保持诚实：只使用 `production_market_facts.track='token_price'` 且 `metric='output_price_per_1m_tokens'` 的多日快照；同一模型/厂商按日期取 median；单日快照不进入变化图；不把 `model_value_score` 的横截面价格混入 token 历史。
- 当前真实样本显示：GPT-5 `2026-06-23 $15.00/1M -> 2026-07-06 $12.50/1M`，变化 `-16.7%`；Gemini 3 Flash `-66.7%`；Gemini 2.5 Flash `+100.0%`；DeepSeek V4 Pro `-15.3%`。页面明确标注这是公开源离散快照，不是连续价格曲线。
- `应用` tab 现在四张主图分别回答四个不同问题：`Token 价格变化`、`高质量模型输出价`、`商业化差值`、`多模态生成成本`。展开区新增 token 变化明细表，并保留 CostGoat、ARR/Ramp、Seedance 明细表。
- `证据库` 的 `模型/API成本` 状态已从单纯 `横截面可观察` 升级为 `离散趋势可观察`，但仍保留 Artificial Analysis、任务质量归因和连续历史缺口，不把该图包装成强交易信号。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 23 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`；内置 Browser 验证应用页新增 token 图、展开交互、控制台 0 error/warn；系统 Chrome Playwright 保存桌面、展开态、390px 移动端截图，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_token_change_apps.png`、`dashboard_v2_token_change_apps_expanded.png`、`dashboard_v2_token_change_mobile_apps.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 继续按目标推进 `tracker_v2`：为总览、价格、云厂商、应用 tab 的主图补上轻量来源/日期/口径脚注，避免用户在金融判断时分不清实时订单簿、90日 movers、官方 VM-hour、公开 proxy 和商业化信号。
- 新增脚注口径包括：GPUs.io material movers、GPUPerHour available order book、Azure/AWS official VM-hour、CostGoat public proxy、Ramp payment adoption、ARR.club public signal、BytePlus/seedance2.ai 成本口径。
- 验收中发现并修复一个真实 UI bug：第一版脚注 HTML 被 Streamlit Markdown 识别成代码块显示；已改为顶格渲染，复验确认无 raw HTML。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`；内置 Browser 验证总览脚注与控制台健康；Python Playwright 验证五个 tab 和 390px 移动端，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_source_captions_overview.png`、`dashboard_v2_source_captions_price.png`、`dashboard_v2_source_captions_cloud.png`、`dashboard_v2_source_captions_apps.png`、`dashboard_v2_source_captions_evidence.png`、`dashboard_v2_source_captions_mobile_overview.png`。

本次更新：

- 已按金融视角审查 `tracker_v2` 当前 presentation：现有五个 tab 已能扫描真实数据，但总览底部原 `拐点监控` 更像状态提醒，不足以显著表达“证据如何改变二级市场判断”。
- 总览已改为 `投资判断桥`：四张卡分别把价格层、官方层、应用层、质量门映射为 `支持叙事松动 / 反证未解除 / 观察接棒 / WARN 15%`，结论明确为“现在只够降低单一稀缺叙事权重”，不能把硬件链直接转空。
- 证据库新增两张图形化摘要：`信号就绪结构` 和 `信号升级阻碍`。折叠区不全部图表化，原始明细和审计表继续保留为表格，只有对判断有直接帮助的就绪度/阻碍内容上提为图。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`；Python Playwright 验证总览、证据库和 390px 移动端，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_finance_bridge_overview.png`、`dashboard_v2_finance_bridge_evidence.png`、`dashboard_v2_finance_bridge_mobile_overview.png`。

本次更新：

- 已新增产品完成度审计文件：`/Users/agg/Documents/AI Compute Economics/docs/PRODUCT_COMPLETION_AUDIT_2026-07-06.md`。
- 审计结论：当前产品已经具备最小可用判断价值，但不能标记为完整完成。它能支持 `No Signal / WARN / 15%` 的保守判断；但硬件成交价、ORNN/OCPI、AWS 90 天 spot history、GCP spot、ARR 深源、Artificial Analysis 等关键证据仍缺，不能升级为强交易信号。
- 审计确认当前价值边界：能降低“算力持续紧缺”单一叙事确定性；不能输出硬件链全面转空；能观察应用层接棒线索；不能把应用层估值切换当作确认信号。

本次更新：

- 已按用户继续反馈优化 `tracker_v2` 五个 tab：各 tab 之间不再重复同一张图。`总览` 保留跨层摘要图；`价格` 改为 `代际价格压力` 和 `订单簿深度`；`云厂商` 保留 `H100 云实例价格` 和 `官方 CAPEX/RPO`；`应用` 改为 `高质量模型输出价`、`商业化差值`、`多模态生成成本`；`证据库` 不再复用总览的拐点监控图，只展示质量门、覆盖层、信号就绪度、判断规则和缺口。
- 已统一主流程折叠区格式：价格、云厂商、应用的展开内容均改成 `说明块 + 明细表`，移除旧的 Streamlit 多选控件/红色标签和重复图表。证据库折叠区也补统一说明块。
- 当前真实读数仍未改变：A100/H100 旧卡组 90d 平均 `-22.0%`，H200/B200 前沿卡组 90d 平均 `+7.7%`；订单簿深度为 A100 `62`、H100 `48`、H200 `20`、B200 `15`；应用页显示 Anthropic/OpenAI 采用率差 `2.1%`、ARR public 差 `$22.00B`。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`；Playwright 用系统 Chrome 验证五个 tab 桌面、展开态和 390px 移动端，图表标题不重复，`price/cloud/apps` 主流程展开态 multiselect 数为 0，证据库全部 9 个折叠区展开后 multiselect 数为 0，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_final_overview.png`、`dashboard_v2_final_price.png`、`dashboard_v2_final_cloud.png`、`dashboard_v2_final_apps.png`、`dashboard_v2_final_evidence.png`，以及 `dashboard_v2_final_price_expanded.png`、`dashboard_v2_final_apps_expanded.png`、对应 `dashboard_v2_final_mobile_*.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已按用户截图反馈收口 `tracker_v2` dashboard：总览底部删除原生折叠项 `判断规则`、`信号就绪度`、`为什么现在还是 No Signal`，并删除全站技术 footer `Rendered at ... Production decisions read ...`。
- 已把 `总览 / 价格 / 云厂商 / 应用 / 证据库` 五个 tab 逐页改成同一逻辑：顶部一句当前读法，主体先给图形化读数，详细表格和审计项放到下方折叠区；折叠区统一为白底深字，避免低对比度“隐藏内容”。
- 当前五页信息结构：`总览` 保留四层图和拐点监控；`价格` 展示 90 日价格变化 + 当前订单簿；`云厂商` 展示 H100 云实例价格 + 官方 CAPEX/RPO；`应用` 展示模型价效比 + 商业化信号 + Seedance 成本；`证据库` 展示质量门、真实事实数、覆盖层、主要缺口、拐点监控、信号就绪度和判断规则。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 用系统 Chrome 验证五个 tab 桌面和 390px 移动端，均无 `Rendered at` footer、无 Traceback、控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_clean_overview.png`、`dashboard_v2_clean_price.png`、`dashboard_v2_clean_cloud.png`、`dashboard_v2_clean_apps.png`、`dashboard_v2_clean_evidence.png`，以及对应 `dashboard_v2_clean_mobile_*.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已继续补齐用户明确要求的 `云厂商 spot instance 价格`：首页 `当前可用订单簿` 卡底部新增 Azure/AWS H100 spot 对照。
- 口径上保持分离：GPUPerHour 仍是 GPU rental order book 的 per-GPU-hour；Azure/AWS 读数标注为 H100 spot `VM hr`，不参与订单簿散点位置，也不与 neocloud per-GPU-hour 混算。
- 当前生产样本：GPUPerHour H100 `$1.07/GPU hr`、H200 `$2.45/GPU hr`、B200 `$3.95/GPU hr`；Azure H100 spot `$1.42/VM hr`；AWS H100 spot `$2.53/VM hr`。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 用系统 Chrome 验证桌面与 390px 移动端订单簿卡，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_cloud_spot_in_orderbook_overview.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_cloud_spot_in_orderbook_mobile.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已继续按用户 pasted research 对齐首页范围：研究要求同时跟踪算力租赁价格、模型/API 成本、AI 应用 ARR/商业化。上一版首页已有 GPU 价格、当前可用订单簿、模型价效比，但缺应用商业化视觉层。
- 首页新增第四张核心图 `应用商业化信号`：Ramp 企业支付采用率用百分比条形展示，ARR.club 公开 ARR 信号用独立小读数展示，避免把百分比和 USD ARR 混在同一坐标轴。
- 当前首页四层视觉为：`90日价格变化`、`当前可用订单簿`、`高质量模型价效比`、`应用商业化信号`。真实样本包括 Ramp Overall AI adoption `50.6%`、Anthropic `34.4%`、OpenAI `32.3%`，ARR.club Anthropic `$47.00B`、OpenAI `$25.00B`。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 用系统 Chrome 验证桌面和 390px 移动端中段，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_four_layer_visual_overview.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_four_layer_visual_mobile.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_four_layer_visual_mobile_mid.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 根据用户反馈“又回去了、文字太多、图表太少、UI 不好看”，继续把首页从解释型页面压成视觉驾驶舱。
- 首页去掉大标题、长 hero 和三张解释卡，改为一条紧凑状态栏 + 三张真实数据图：`90日价格变化`、`当前可用订单簿`、`高质量模型价效比`。原先的 `判断规则`、`信号就绪度`、`为什么还是 No Signal` 继续默认折叠。
- 三张首页图均来自生产底表：A100 80GB 90d `-36.9%`、H100 90d `-7.1%`、H200 90d `8.1%`、B200 90d `7.2%`；H100 当前可用最低 `$1.07`、`48` offers；CostGoat high-quality value leader `xiaomi/mimo-v2.5` value `289.3`。
- 视觉上采用苹果式浅色、低边框、短标签，不把解释文字放在首屏主区域；移动端 390px 宽度已截图检查，没有明显重叠。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 22 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 用系统 Chrome 验证桌面与移动端截图，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_visual_dashboard_overview.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_visual_dashboard_mobile.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已新增 `拐点监控` 模块，继续在现有真实数据上做减法和判断显性化，不新增数据源、不伪造数据。
- 首页和证据库现在直接显示三条会改变二级市场判断的触发器：`硬件链转负` 当前未触发（H200 90d `8.1%`、B200 90d `7.2%`、H100 order book `$1.07/GPU hr / 48 offers`）；`云厂商由压制转受益` 当前为反向约束（官方 CAPEX/RPO 仍偏扩张）；`应用层价值接棒` 当前观察中（CostGoat leader `xiaomi/mimo-v2.5` value `289.3`，Anthropic/OpenAI adoption spread `2.1%`）。
- `拐点监控` 的触发条件明确写入页面：前沿卡 H200/B200 同步转负且 H100 低价订单簿有深度，才提高硬件链负面权重；云厂商需要闲置算力变现扩大且 CAPEX/RPO 不再继续上修；应用层需要模型/API 价效比与 ARR/采用率/用量连续改善。
- 证据库里拐点监控表和信号就绪度表均默认折叠，保持苹果式简单视图；详细表格按需展开。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 21 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 用系统 Chrome 验证总览和证据库，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_inflection_watchlist_overview.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_inflection_watchlist_evidence.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已按用户要求不在旧 UI 上继续修补，而是从第一性原理和用户偏好重排 `tracker_v2` dashboard：第一屏先回答“当前该采取什么投资动作”，再展示支撑证据。
- `总览` 现在以 `继续观察` 开场，同时保留机器状态 `No Signal / WARN / 15%`。核心解释为：GPU 价格层已代际分化，但官方 CAPEX/RPO 没有转弱，因此只能降低对单一稀缺叙事的确定性，不能升级为硬件链转空信号。
- 首页新增两个决策面板：`怎么用它` 写清三条触发规则（硬件链转负、云厂商转正、应用层转正）；`信号就绪度` 明确区分 GPU 租赁价格可观察、云厂商 CAPEX/RPO 为反证层、模型/API 成本为横截面、应用商业化为弱信号、授权指数/硬件成交仍是缺口。
- `证据库` 不再默认展开长缺口明细；现在先显示完整信号就绪度和“当前最影响判断的缺口”，再把来源健康、proxy 历史、完整读数、旧版审计按需折叠。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 20 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 用系统 Chrome 验证总览与证据库，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_first_principles_overview.png`、`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_first_principles_evidence.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已停止新增数据源，改为在现有 `production_market_facts=3,118` 和 `production_official_events=9` 基础上收口产品展示。
- Dashboard 主界面已按“苹果式清楚简单菜单 + 按需展开说明”重新设计，不再沿用旧首页堆图表结构。新的信息架构为 `总览 / 价格 / 云厂商 / 应用 / 证据库`，菜单用同页 URL 链接实现，避免 Streamlit tabs/状态控件点击不稳。
- `总览` 当时只展示当前判断 `No Signal`、三张核心卡（GPU 价格、可用订单簿、模型价效比）、一张 90 日价格变化图和三层证据链；后续已继续收口，当前总览不再保留“为什么现在还是 No Signal”原生折叠项。
- `价格 / 云厂商 / 应用` 分别围绕用户二级市场判断拆开：GPU 代际分化和订单簿、官方 CAPEX/RPO 是否转弱、模型价效比和商业化信号；完整图表和审计信息均默认折叠。
- 已验证：`python3 -m py_compile dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 19 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright 验证 `价格 / 云厂商 / 应用 / 证据库` 同页导航均通过，控制台 0 error/warn。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_redesign_overview.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已新增 GPUPerHour Offers API 生产轨道 `gpu_available_offer`，补上当前可用 GPU 租赁订单簿。该轨道只写 `available=true`、`currency=USD`、目标 GPU family 匹配的 offer；H200 查询使用 exact slug，避免 GH200 污染 H200。
- 当前生产库有效事实为 `production_market_facts=3,118`：`gpu_rental=284`、`gpu_available_offer=181`、`gpu_rental_trend=24`、`gpu_market_trend=95`、`cloud_instance_price=262`、`token_price=1,399`、`model_value_score=820`、`app_commercialization=15`、`multimodal_generation_cost=38`。
- GPUPerHour 当前 available=true order book 样本：H100 `48` 个可用 offer、最低 `$1.07/GPU hr`；H200 `20` 个可用 offer、最低 `$2.45/GPU hr`；B200 `15` 个可用 offer、最低 `$3.95/GPU hr`；B300 `2` 个可用 offer、最低 `$7.39/GPU hr`。
- Dashboard 首页新增 `可用GPU订单簿` 指标和 `GPUPerHour 当前可用订单簿` 图表；硬件链决策读数加入 H100/H200/B200 当前可用最低价和 offer 深度。该轨道不与 ComputePrices/gpus.io 合并计算 median，避免口径混乱。
- 口径限制：GPUPerHour 是当前租赁 offer order book，不是硬件买卖成交价。硬件现货 GPU 成交价仍未接入，后续需要 eBay sold listings、渠道报价或其他二手成交源，并区分 ask 与成交。
- 已验证：`python3 -m py_compile data_sources/market_facts.py dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py -q` 18 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=3,118`；Playwright smoke 确认 `可用GPU订单簿 9 GPUs`、`H100 min $1.07/GPU hr / offers 48`、硬件读数中的 H100/H200/B200 order book 可见。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_gpuperhour_smoke.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已新增 CostGoat LLM API comparison 公开 proxy，补上模型 API “质量 / 价格 / 价效比”横截面。当前生产库有效事实为 `production_market_facts=2,937`：`gpu_rental=284`、`gpu_rental_trend=24`、`gpu_market_trend=95`、`cloud_instance_price=262`、`token_price=1,399`、`model_value_score=820`、`app_commercialization=15`、`multimodal_generation_cost=38`。
- CostGoat 样本覆盖 205 个模型，每个模型写入 `quality_score`、`input_price_per_1m_tokens`、`output_price_per_1m_tokens`、`value_score_per_output_dollar`。当前 high-quality value leader 是 `xiaomi/mimo-v2.5`：quality `81`、output `$0.28/1M`、value `289.3`；旗舰质量 leader 是 `openai/gpt-5.5`：quality `100`、output `$30.00/1M`、value `3.3`。
- Dashboard 首页和 Four-track tab 已新增“模型质量 / 价格 / 价效比”图表：output price vs quality scatter、top value bar、厂商筛选和最低质量分筛选。AI 应用/API 决策卡同步加入 CostGoat 价效比证据，明确它支持观察应用/API routing 的毛利改善空间。
- 口径限制已写入页面和文档：CostGoat 是公开 proxy，不替代 Artificial Analysis 授权 benchmark；Artificial Analysis API 仍需要账号/API key。ComputePrices 本轮仍有 `429 Too Many Requests`，ORNN/OCPI 仍未授权，所以总判断仍是 `No Signal / WARN / 15%`，不能输出“算力稀缺溢价破裂”交易信号。
- Dashboard 缓存 TTL 已从 300 秒降为 30 秒，避免生产库刷新后页面继续显示旧样本数。当前服务已重启并可在 `http://127.0.0.1:8503` 查验。
- 已验证：`python3 -m py_compile data_sources/market_facts.py tracker_v2.py dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py -q` 16 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=2,937`；Chrome smoke 确认 `模型价效比 205 models`、CostGoat、`xiaomi/mimo-v2.5`、Artificial Analysis 缺口可见，31 张 Plotly 图，无 Traceback/重复 widget。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_model_value_smoke.png`。下一步如果继续补数据，应优先补硬件现货成交价、GCP key/AWS 90 天 spot history、ARR 深源和 ORNN/OCPI 授权指数。

本次更新：

- 已补齐官方 CAPEX/RPO 确认层：`production_official_events=9`，覆盖 MSFT/AMZN/GOOGL/META/ORCL，`OFFICIAL_EVENT_MISSING` 已从质量门消失。
- 官方事件源已改为可重抓、可校验 proof excerpt 的 SEC/官方路径：META FY2026 capex `$125-145B` vs prior `$115-135B`；GOOGL Cloud backlog `>$460B`；ORCL RPO `$638B`；AMZN TTM PPE increase `$59.3B` tied to AI；MSFT demand still exceeds supply。
- Dashboard 首屏新增 `官方 CAPEX/RPO 5/5 hyperscalers`，Hyperscaler 决策卡现在明确写出：官方 CAPEX/RPO/需求层仍偏扩张，不支持把旧卡降价直接解释成云厂商 CAPEX 下修。当前总判断仍为 `No Signal / WARN / 15%`。
- 质量门已修正 stale failure 问题：旧的官方 IR 403 质量事件仍留在审计表，但同一家公司后续已有更新 source-backed 官方事件时，不再作为当前质量门缺口显示。当前 validate 仍为 `WARN`，主要剩余问题是 ComputePrices 429、ORNN/OCPI 未授权、GCP/AWS history/ARR 深源缺口。
- 已验证：`python3 -m py_compile data_quality.py dashboard_v2.py data_sources/official_events.py` 通过；`python3 -m pytest test_suite/test_data_quality.py test_suite/test_dashboard_queries.py test_suite/test_official_events.py test_suite/test_market_facts.py -q` 29 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`production_official_events=9`、无 `OFFICIAL_EVENT_MISSING`；Chrome smoke 确认 `5/5 hyperscalers`、META/GOOGL/ORCL/AMZN 官方读数可见，旧官方 403 不再显示为当前缺口。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_official_events_smoke.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。

本次更新：

- 已把 GPUs.io 30/90 日 movers 从“图表数据”上提为首页“市场状态”读数。当前市场状态显示为 `代际分化`：A100 80GB 90d `-36.9%`，H200 90d `+8.1%`，B200 90d `+7.1%`。
- 这条判断只来自 `production_market_facts` 的 `gpu_market_trend/price_delta_90d_pct`，不使用 seed、mock 或手工估算。含义是：旧卡/非前沿算力价格松动，但 H200/B200 仍偏紧；单一“算力持续紧缺”叙事变弱，但仍不能输出硬件链全面转空或 `Scarcity Premium Cracking` call。
- Dashboard 首屏新增 `市场状态` 指标，`_decision_explanation` 改为先说明 `代际分化 / No Signal`，再说明仍缺 ComputePrices 足够历史、官方云 spot 历史、CAPEX 指引和 ARR 深源。新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_regime_smoke.png`。
- 已验证：`python3 -m py_compile dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_market_facts.py -q` 13 passed；Chrome smoke 确认首页 `代际分化`、`A100 80GB 90d -36.9%`、`H200 90d 8.1%`、`B200 90d 7.1%` 可见，27 张 Plotly 图，无 Traceback/重复 widget。
- 当前本地查验地址仍是 `http://127.0.0.1:8503`。下一步如果继续补数据，应优先补硬件现货成交价、GCP key/AWS 90 天 spot history、ARR 深源和 ORNN/OCPI 授权指数。

本次更新：

- 已新增 `gpu_market_trend` 生产轨道，接入 GPUs.io Trends 页面的 30/90 日 material movers。普通 requests 被 Cloudflare 拦截时，collector 会用本机 Chrome 浏览器渲染正文并保存 rendered text 快照；不是用搜索摘要或手工填数。
- 当前生产库有效事实为 `production_market_facts=2,111`：`gpu_rental=284`、`gpu_rental_trend=24`、`gpu_market_trend=90`、`cloud_instance_price=262`、`token_price=1,399`、`app_commercialization=14`、`multimodal_generation_cost=38`。
- GPUs.io 样本：A100 80GB `+5.6% 30d / -36.9% 90d`，H200 `+6.5% 30d / +8.1% 90d`，B200 `-0.2% 30d / +7.1% 90d`，Tesla V100 `+42.9% 30d / -41.7% 90d`。当前硬件链读数改为“代际分化”：旧卡 90 日下跌，但 H200/B200 仍偏紧，不能推出全市场算力过剩。
- Dashboard 首屏新增 `GPUs.io 30/90日` 指标和两张图，硬件链决策卡同步加入 GPUs.io 证据。新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_gpusio_smoke.png`。
- 已验证：`python3 -m py_compile data_sources/market_facts.py dashboard_v2.py tracker_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py test_suite/test_data_quality.py test_suite/test_decision_engine.py test_suite/test_data_contract.py -q` 34 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=2,111`；Chrome smoke 确认页面有 27 张 Plotly 图、356 个交互控件、GPUs.io/H200/A100/B200 读数可见、控制台 0 error/warn。
- 本次 live update 仍暴露 ComputePrices Trend/LLM `429 Too Many Requests`；ComputePrices GPU API 本轮恢复写入，GPUs.io / BytePlus / seedance2.ai / Azure / AWS / ARR.club / Ramp 正常写入。仍未完成：硬件现货成交价、GCP API key、AWS 90 天 history、ARR 深源、ORNN/OCPI 授权指数。

本次更新：

- 已新增 `multimodal_generation_cost` 生产轨道，接入 BytePlus ModelArk 官方 Seedance 2.0 token 单价和 seedance2.ai 第三方 credits 扣费表；两类单位分开展示，不把 `USD/1M tokens` 与 `credits` 混算。
- 当前生产库有效事实为 `production_market_facts=2,016`：`gpu_rental=281`、`gpu_rental_trend=24`、`cloud_instance_price=262`、`token_price=1,399`、`app_commercialization=12`、`multimodal_generation_cost=38`。
- Seedance 样本：BytePlus 官方 Seedance 1080p no-video input `$7.70/1M tokens`、4K with-video input `$2.40/1M tokens`；seedance2.ai Seedance 2.0 720p no-video 5s example `60 credits`、Seedance 2.0 Mini 480p with-video 5s example `16 credits`。
- Dashboard 首屏新增 `多模态生成成本` 指标，AI 应用/API 决策读数加入 Seedance 成本证据，新增 BytePlus 官方 token 单价图和 seedance2.ai credits 图。新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_seedance_smoke.png`。
- 已验证：`python3 -m py_compile data_sources/market_facts.py dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py test_suite/test_data_quality.py test_suite/test_decision_engine.py -q` 27 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=2,016`；Chrome smoke 确认页面有 23 张 Plotly 图、324 个交互控件、Seedance/BytePlus/credits 可见、控制台 0 error/warn。
- 本次 live update 仍暴露 ComputePrices `429 Too Many Requests`：GPU rental、GPU trend、ComputePrices LLM 本轮未刷新，旧生产快照保留，质量事件明确显示限流；未插入假数据。

本次更新：

- 已把 Ramp AI Index public article 接入 `production_market_facts` 的 `app_commercialization/business_adoption_share` 轨道，不把它包装成 ARR：Anthropic `34.4%`、OpenAI `32.3%`、overall AI adoption `50.6%`，口径为企业卡和 invoice 支付采用率。
- 当前生产库有效事实为 `production_market_facts=1,978`：`gpu_rental=281`、`gpu_rental_trend=24`、`cloud_instance_price=262`、`token_price=1,399`、`app_commercialization=12`。Dashboard 首屏新增 `企业采用率` 指标，AI 应用商业化图表新增 Ramp 采用率横向柱状图，二级市场读数卡同步写入 Ramp 证据。
- 本次 live update 暴露 ComputePrices `429 Too Many Requests`：GPU rental、GPU trend、ComputePrices LLM 本轮未刷新，旧生产快照仍保留，质量事件明确显示限流；未插入假数据。
- 当前本地查验地址仍是 `http://127.0.0.1:8503`，已用生产库后台重启。新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_adoption_smoke.png`。
- 已验证：`python3 -m py_compile data_sources/market_facts.py dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_dashboard_queries.py test_suite/test_data_quality.py test_suite/test_decision_engine.py -q` 26 passed；`python3 tracker_v2.py validate-data --production --db ai_compute_tracker_production.db` 退出码 0、`quality_gate=WARN`、`production_market_facts=1,978`；Chrome smoke 确认页面有 19 张 Plotly 图、284 个交互控件、Ramp 34.4/32.3/50.6 可见、控制台 0 error/warn。

本次更新：

- 已按用户最新口径把 `tracker_v2` 从单一 GPU/CAPEX tracker 扩成四轨市场监控：GPU 租赁/spot、模型 token/API 价格、AI 应用商业化 ARR 公开信号，以及原有 CAPEX/official events 质量门。
- 新增生产表 `production_market_facts` 与 `market-facts` 更新目标，真实接入 ComputePrices GPU API、ComputePrices GPU Trend API、ComputePrices LLM API、OpenRouter Models API、ARR.club public homepage、Ramp AI Index public article、Azure Retail Prices API、AWS EC2 current Spot JSON；当前生产库有效事实为 `production_market_facts=1,978`，其中 `gpu_rental=281`、`gpu_rental_trend=24`、`cloud_instance_price=262`、`token_price=1,399`、`app_commercialization=12`。
- Dashboard 首屏现在显示“四轨市场监控”：H100 spot median、Azure H100 spot VM-hour min、OpenAI output median、top ARR company，并提供 GPU 租赁、官方云实例价格、token 价格、ARR 公开信号的可交互图表；新增 `Four-track market facts` 标签页查看明细和授权/缺口事件。
- 当前仍然保持 `decision_state=No Signal`、`quality_gate=WARN`、`confidence=15%`。原因是：GPU/Token/ARR/官方云实例价格已经有横截面数据，但趋势拐点还需要继续沉淀本地快照；硬件现货 GPU 价格、GCP API key、AWS 90 天 spot history、ARR 历史/source links、ORNN/OCPI 授权指数仍未完成。
- 已显式暴露 7 个授权/缺口事件：ARR.club Pro、Sacra、Artificial Analysis API、SemiAnalysis GPU Pricing Index、AWS 90 天 spot history、GCP Pricing API、OCI 动态 spot/source normalization。未插入估算值或占位值。
- 已根据用户“还不如 gpus.io”的反馈修正产品定位：GPU 租赁横截面不再声称是核心差异化；README 已把旧 L2/L3/CSI 宣传降为 demo/legacy，不作为当前 production dashboard 主结论。
- 已新增“二级市场决策读数”首屏文字卡：分别覆盖硬件/算力基础设施、Hyperscaler 云厂商、AI 应用/API、AI 应用商业化、总判断。每张卡都写明证据、二级市场含义、反证/升级条件；当前总判断仍是 `No Signal / WARN`，强调“降低对单一稀缺叙事的确定性，但不输出 cracking call”。
- 已修正 token 与 ARR 展示口径：token 图按 normalized vendor 合并 `OpenAI/openai/~openai` 等重复厂商；ARR 图改为 `public ARR signal`，避免包装成审计 ARR 或完整私企财务。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_decision_cards_smoke.png`。Chrome smoke 确认首屏含硬件链、云厂商、应用/API、ARR、总判断五张读数卡，15 张 Plotly 图、14 个筛选控件，控制台 0 error/warn。
- 已新增 ComputePrices public tier GPU 7 日趋势：H100 +7.6%、H200 +14.4%、B200 +28.7%。首屏增加 `GPU 7日趋势` 指标和 `GPU 租赁公开趋势` 折线图；决策卡同步改为“短期价格没有给出单边下行确认”。新截图：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_gpu_trend_smoke.png`。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_four_track_smoke.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。
- 已验证：`python3 -m py_compile dashboard_v2.py data_sources/market_facts.py tracker_v2.py production_store.py data_quality.py` 通过；`python3 -m pytest test_suite/test_market_facts.py test_suite/test_data_contract.py test_suite/test_dashboard_queries.py test_suite/test_data_quality.py test_suite/test_decision_engine.py -q` 30 passed；Chrome smoke 确认页面有 13 张 Plotly 图、8 个筛选控件，无 Streamlit duplicate key、无 Traceback、控制台 0 error/warn。
- 本轮使用 skill：`data-analytics:build-dashboard`、`build-web-apps:frontend-testing-debugging`、`browser:control-in-app-browser`。

本次更新：

- 已按用户反馈修复 `tracker_v2` dashboard 的核心问题：页面不再把 `production_gpu_prices` 原始报价行聚合成“历史趋势”，因为该表混有官方单日价格页、ComputePrices 聚合报价、重复 provider 行，容易制造伪趋势。
- 现在首屏的价格历史只来自 `production_public_proxy_prices` 的 ComputePrices public proxy：`quote_count >= 3` 的日期才进入趋势线，低样本日期默认暴露为“低样本 proxy 日期”，不连线、不参与趋势判断。
- 官方价格页 RunPod/Lambda 现在只作为“当前快照”展示：生产库里这部分目前只有 2026-07-05 单日快照，不能包装成历史趋势。
- 当前真实数据判断保持保守：`decision_state=No Signal`、`quality_gate=WARN`、`confidence=15%`；页面明确写出“不能证明算力稀缺溢价已经破裂”。真实库 proxy history 为 28 行，其中只有 5 行达到 adequate row 口径，按日期看是 3 个可用 proxy 日期；官方事件仍只有 2 行，AMZN/GOOGL/META/ORCL guidance/RPO 缺口仍在。
- 已修复 GPU evidence tab 的数据混乱：图表层折叠重复报价样本，原始 raw rows 默认放入审计用 expander，不再让重复行放大分布。
- 新截图证据：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_repaired_decision_smoke.png`。当前本地查验地址仍是 `http://127.0.0.1:8503`。
- 已验证：`python3 -m py_compile dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py test_suite/test_data_quality.py test_suite/test_decision_engine.py -q` 20 passed；Streamlit HTTP 200；in-app Browser smoke 通过，首屏有 No Signal 解释、proxy history、低样本披露、价格页快照，且不再出现旧 `H100/H200 历史 GPU 价格趋势` 和 `Composite Scarcity Index`。
- 本轮使用 skill：`build-web-apps:frontend-testing-debugging`、`browser:control-in-app-browser`。

本次更新：

- 已按用户反馈重做 `tracker_v2` dashboard 可用性：第一屏现在不再是数据覆盖表，而是 `当前判断 / 数据质量门 / 判断置信度 / H100-H200 价格历史 / 生产行数` + 历史 GPU 价格趋势图 + 缺口摘要 + 来源健康。
- 历史价格趋势只读生产表 `production_gpu_prices`，按 `date + gpu_model + source_type` 聚合 `median/min/max/quote_count`。ComputePrices 是公开聚合报价历史；RunPod/Lambda pricing page 当前只有单日快照，页面明确不把它伪装成历史趋势。
- 当前真实生产库中 H100/H200 聚合报价合计覆盖 17 个 quote-date；单个 H100/H200 各有 14 个 quote-date。当前判断仍是 `No Signal / WARN / 15%`，因为官方报价页只有 1 个快照日，AMZN/GOOGL/META/ORCL 官方 guidance/RPO 仍缺 source-backed 事件，ORNN/OCPI 未配置授权源。
- 新增执行计划：`/Users/agg/Documents/AI Compute Economics/dashboard-usable-product-plan.md`，U1/U2/U3/U4 均已完成；U1 用子进程模拟用户指出“像数据验收页而不是 Tracker”，U2 子进程落地趋势数据契约，主线程完成 UI 改造和浏览器验收。
- 新截图：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_usable_trend_smoke.png`；当前本地查验地址仍是 `http://127.0.0.1:8503`。
- 已验证：`python3 -m py_compile dashboard_v2.py` 通过；`python3 -m pytest test_suite/test_dashboard_queries.py -q` 4 passed；`curl http://127.0.0.1:8503` 返回 200；Chrome browser smoke 验证首屏包含历史趋势、缺口、来源健康，且没有旧 `Composite Scarcity Index` 主指标。
- 本轮使用 skill：`parallel-task`。

本次更新：

- `tracker_v2` 闭环计划 T12 已完成：生产源现在落在独立数据库 `/Users/agg/Documents/AI Compute Economics/ai_compute_tracker_production.db`，不再把真实生产闭环默认写入旧的 `ai_compute_tracker.db`。
- 已新增显式 DB 路径机制：CLI 子命令支持 `--db`，也支持 `AI_COMPUTE_TRACKER_DB`；`ProductionStore` 已改为运行时读取活动 DB 路径，避免 collector 回写旧库。
- T12 第一次 live run 暴露并修复了一个真实 bug：主脚本以 `__main__` 运行时，collector 再导入 `tracker_v2` 会形成第二份模块状态，导致采集写入旧库、校验读取生产库。已通过模块 alias + 环境变量传播修复，并新增防回归测试。旧 `ai_compute_tracker.db` 未被覆盖或 reset，但第一次失败尝试确实触碰过其 production 表；后续生产源以 `ai_compute_tracker_production.db` 为准。
- 当前独立生产库真实行数：`production_gpu_prices=128`（官方价格页 28、聚合页 100）、`production_capex_actuals=5`、`production_official_events=2`、`production_public_proxy_prices=84`、`production_data_quality_events=4`、`production_pipeline_runs=4`；生产库里的 legacy/demo 表保持为空。
- 当前生产判断：`quality_gate=WARN`、`decision_state=No Signal`、`cli_exit_semantics=WARN_CAPEX_CONFIRMATION_MISSING`。含义是：有真实 GPU 价格和 SEC CAPEX actual，但缺少可比较趋势和多家公司官方 guidance/RPO 确认，不能输出“算力稀缺溢价破裂”。
- 最终生产报告：`/Users/agg/Documents/AI Compute Economics/tracker_data/20260705T143710Z-production-source-backed-decision-brief.md`。
- T10/T13 已完成：`dashboard_v2.py` 现在是 production-first dashboard，默认读取 `AI_COMPUTE_TRACKER_DB` 或 `ai_compute_tracker_production.db`；第一屏显示当前判断、质量门、置信度、生产行数、数据覆盖和失败源，不再把旧 CSI 放在主位置。
- 当前本地查验地址：`http://127.0.0.1:8503`，启动命令是 `AI_COMPUTE_TRACKER_DB=ai_compute_tracker_production.db python3 -m streamlit run dashboard_v2.py --server.port 8503 --server.address 127.0.0.1 --server.headless true`。
- 最终验收摘要：`/Users/agg/Documents/AI Compute Economics/tracker_data/20260705T144531Z-production-acceptance-summary.md`；dashboard 截图：`/Users/agg/Documents/AI Compute Economics/tracker_data/dashboard_v2_production_smoke.png`。
- 已验证：旧单元测试 28 passed；旧集成测试 13 passed；生产闭环测试 74 passed；`validate-data --production --db ai_compute_tracker_production.db` 退出码 0；生产报告生成退出码 0；Streamlit HTTP 200；Chrome browser smoke 通过。
- 下一步如果继续做数据质量提升，应优先补 AMZN/GOOGL/META/ORCL 的 source-backed official guidance/RPO 事件，并持续积累多日 GPU 官方报价快照。
- 本轮使用 skill：`parallel-task`。

本次更新：

- `tracker_v2` 闭环计划 T8 已完成：新增生产决策引擎 `/Users/agg/Documents/AI Compute Economics/decision_engine.py`，生产报告现在输出 gate-based `decision_state`，不再把旧 CSI 当主结论，也不写 `csi_history`。
- 当前真实生产库的决策结果是 `decision_state=No Signal`、`confidence=15%`、`quality_gate=WARN`。原因不是“没数据”，而是目前只有单日 GPU/ComputePrices 快照，CAPEX 每家公司只有 1 个 official actual，且 AMZN/GOOGL/META/ORCL 暂无 source-backed official event，所以趋势和官方确认不足，不能输出 `Scarcity Premium Cracking`。
- 已验证：`python3 -m pytest test_suite/test_decision_engine.py -q` 7 passed；`python3 -m pytest test_suite/test_data_quality.py test_suite/test_ocpi_policy.py test_suite/test_gpu_pricing_sources.py test_suite/test_sec_capex.py test_suite/test_official_events.py -q` 33 passed；`python3 tracker_v2.py report --production` 退出码 0，输出 source-backed decision，未出现 CSI 主指标。
- 下一步是 T9：把当前生产报告从命令行状态输出升级成 source-backed decision brief，要求每个 evidence row 都有 `source_url` 或 snapshot，seed-only/quality FAIL 时不输出 regime call。
- 本轮使用 skill：`parallel-task`。

本次更新：

- `tracker_v2` 闭环计划 T6/T7 已完成：T6 把 ORNN/OCPI 生产路径改为授权源不可用事件，并把 ComputePrices 派生指标单独命名为 `public_gpu_price_proxy`；T7 新增质量门 `data_quality.py`，把真实生产数据、legacy seed、source failures 转成 `PASS`/`WARN`/`FAIL` 和 reason table。
- 当前生产库已有真实 source-backed 数据：`production_gpu_prices=128`、`production_capex_actuals=5`、`production_official_events=2`、`production_public_proxy_prices=84`、`production_data_quality_events=5`、`production_pipeline_runs=2`。
- `python3 tracker_v2.py validate-data --production` 当前返回 `quality_gate=WARN`、退出码 0。主要 WARN 原因：legacy seed/direct/composite_public 仍在旧表但被 production gate 忽略；AMZN/GOOGL/META/ORCL 暂无 source-backed official event；ORNN/OCPI 无授权 feed；Meta/Alphabet/Oracle 官方页面当前 re-fetch 不可用或被阻断。
- 已验证：`python3 -m pytest test_suite/test_ocpi_policy.py -q` 4 passed；`python3 -m pytest test_suite/test_data_quality.py -q` 9 passed；`python3 -m pytest test_suite/test_ocpi_policy.py test_suite/test_gpu_pricing_sources.py test_suite/test_sec_capex.py test_suite/test_official_events.py -q` 24 passed。
- T7 worker 在最终回传前网络流断，但文件已落地且主线程完成本地验收、计划状态已补为 Completed。下一步是 T8：用质量门和真实数据重建不混频的 L1/L2/L3 决策状态，禁止 production 再使用旧 CSI 作为主结论。
- 本轮使用 skill：`parallel-task`。

本次更新：

- `tracker_v2` 闭环计划 T5 已完成：新增官方 guidance / RPO / capacity comment 事件层，主文件为 `/Users/agg/Documents/AI Compute Economics/data_sources/official_events.py`。
- 已新增 source-backed YAML：`/Users/agg/Documents/AI Compute Economics/data/manual_official_events.yml`。每条事件必须有官方 URL、公告日期、ticker/company、event_type、metric、value/range、unit、短 source excerpt 和 `collector_name=manual_sourcebacked_yaml`；缺 proof 会进入 rejected/quality，不进生产。
- live update 已执行：`python3 tracker_v2.py update --production --only official-events` 插入 2 条 Microsoft 官方页面验证通过的生产事件（`capacity_comment`、`management_capacity_comment`）；Meta、Alphabet、Oracle 候选 IR 页面当前返回不可用/阻断状态，已写入 `SOURCE_UNAVAILABLE` quality events 并保存快照到 `/Users/agg/Documents/AI Compute Economics/tracker_snapshots/official_events/`。
- 已更新计划文件 T5 状态、log 和 files；未提交 commit，原因是父级 Git 仍把整个 `tracker_v2` 基线和并行 worker 改动视为 untracked，无法安全做孤立 T5 commit。
- 验证结果：T5 单测 5 passed；seed/isolation + integration surface + data contract 18 passed。
- 本轮使用 skill：`parallel-task`。

本次更新：

- `tracker_v2` 闭环计划 T3 已完成：新增 GPU pricing source adapters，主文件为 `/Users/agg/Documents/AI Compute Economics/data_sources/gpu_pricing.py`。
- 已实现 RunPod 官方 HTML、Lambda 官方 HTML、ComputePrices H100/H200 聚合页解析；每条生产价格行保留 `source_url`、`snapshot_path`、`raw_payload_hash`、`observed_at`、`fetched_at`，ComputePrices 行保留实际 provider、quote date/age 和 aggregator 来源属性，不与官方报价平均。
- live update 已执行：`python3 tracker_v2.py update --production --only gpu-prices` 处理 145 条解析观察，生产表当前分源计数为 RunPod 6、Lambda 22、ComputePrices H100 63、ComputePrices H200 37，GPU pricing 质量事件 0；snapshot 保存到 `/Users/agg/Documents/AI Compute Economics/tracker_snapshots/gpu_prices/`。
- 已更新计划文件 T3 状态、log 和 files；未提交 commit，原因是父级 Git 仍把整个 `tracker_v2` 基线和并行 worker 改动视为 untracked，且 T4/T5 同时改了共享 CLI/test surface，无法安全做孤立 T3 commit。
- 验证结果：T3 单测 8 passed；seed/isolation + integration surface + data contract 18 passed。
- 本轮使用 skill：`parallel-task`。

本次更新：

- `tracker_v2` 闭环计划 T4 已完成：新增 SEC companyfacts 官方 CAPEX actual collector，主文件为 `/Users/agg/Documents/AI Compute Economics/data_sources/sec_capex.py`。
- collector 读取 `company_config.py` 的 MSFT/AMZN/GOOGL/META/ORCL CIK 与 CAPEX XBRL tag；AMZN 使用 `PaymentsToAcquireProductiveAssets`；生产路径不使用 yfinance 作为 CAPEX official 主源。
- live update 已执行：`python3 tracker_v2.py update --production --only capex-actuals` 插入 5 条 `production_capex_actuals` official eligible rows，snapshot 保存到 `/Users/agg/Documents/AI Compute Economics/tracker_snapshots/sec_capex/`。
- 已更新计划文件 T4 状态、log 和 files；未提交 commit，原因是父级 Git 仍把整个 `tracker_v2` 基线和并行 worker 改动视为 untracked，无法安全做孤立 T4 commit。
- 验证结果：T4 单测 7 passed；seed/isolation + integration surface + data contract 18 passed。

本次更新：

- 已按用户要求使用 `swarm-planner` 方法，为 `/Users/agg/Documents/AI Compute Economics` 生成一次性闭环执行计划：
  - `/Users/agg/Documents/AI Compute Economics/tracker-v2-real-data-closure-plan.md`
- 计划目标：把 `tracker_v2` 从 seed/demo 型 tracker 改造成真实数据驱动的决策产品。核心门槛是生产路径不消费 seed/mock/reference 数据，每条证据必须带来源、快照、哈希、时间和数据质量状态。
- 已按子进程对抗式审查修订计划：新增 `T1.5 Integration Surface`，统一 production schema/upsert/API/CLI 骨架；修正 T9/T10/T12 依赖；要求 T14 来源政策阻塞 T3/T4/T5/T6；禁止生产模式写入或展示 CSI 主指标；生产库改为 `ai_compute_tracker_production.db`，不覆盖当前 seeded DB。
- 下一步推荐：用 `$parallel-task` 执行该计划，不用 `super-swarm`。

本次更新：

- 已安装 `am-will/swarms` 多代理编排 skill 集合到全局目录 `/Users/agg/.codex/skills`：`swarm-planner`、`parallel-task`、`parallel-task-tmux`、`co-design`、`super-swarm`、`parallel-task-spark`、`super-swarm-spark`。
- 已在 `/Users/agg/.codex/config.toml` 启用 `multi_agents = true`，否则 `parallel-task` 无法真正 spawn 子代理。
- 已同步上述 skill 到 OneDrive 备份目录 `/Users/agg/Library/CloudStorage/OneDrive-个人/Research report/Codex Research/skill`，并更新 `SKILL_SYNC_MANIFEST.md` 与 `SKILL_USAGE.md`。
- 使用建议：默认只用 `swarm-planner` 生成显式依赖计划，再用 `parallel-task` 按 wave 执行；`super-swarm` 会忽略依赖图，不适合当前 tracker_v2 这类数据决策系统。

本次更新：

- 已按用户要求把 Kimi workspace 的 `tracker_v2` 复制到本项目目录：`/Users/agg/Documents/AI Compute Economics`。后续以这份为基底，不再继续修旧的静态 `compute-tracker`。
- 已为 `tracker_v2` 新增项目级 `AGENTS.md`，明确真实数据优先、seed/mock/reference price 不能包装成生产结论。
- 已修正复制后测试里的旧绝对路径，测试现在优先导入本目录 `tracker_v2.py`，不再依赖 `/Users/agg/Documents/kimi/workspace/tracker_v2`。
- 迁移验证：`python3 tracker_v2.py status` 可读取本目录数据库；`python3 -m pytest test_suite/test_unit.py -q` 通过 28 项；`python3 -m pytest test_suite/test_integration.py -q` 通过 13 项。
- 当前观察：迁移后的数据库仍有大量 `seed_data` / `seed_guidance`，下一步要把真实 GPU 价格源和官方 CAPEX/RPO 接入 L1，再重建 L2/L3。

旧方案记录，已废弃：

- 已按用户要求重做为独立产品：`compute-tracker/`。它不再绑定原 Next.js 财经工作台，不接左侧导航、不接股票池、不接 research service。
- 已移除原系统左侧导航中的“算力 Tracker”入口，并删除原 `/compute-tracker` 页面文件。
- 独立产品采用 bottom-up 流程：有什么数据 -> 如何 track -> 如何解释 -> 去重剔除 -> 合成逻辑。当前结论是“未确认破裂：报价有松动线索，但容量缺证”。
- 独立产品当前数据源来自 `compute-tracker/data/signals.json`，每条数据都记录来源、时间、单位、频率、采集方式、解释力、去重规则和是否进入合成。
- 已补入真实价格数据：RunPod 官方 H100/H200/B200/B300 GPU-hour 报价、Lambda 官方 H100/B200 集群报价、Nebius 官方 H100/H200/B200/B300 报价、ComputePrices H100/H200 跨供应商报价快照。价格层当前 4 条进入合成，不再是空框架。
- 三个子进程已完成：公开市场研究给出数据宇宙和剔除规则；产品构建给出独立工作台结构；测试环境给出独立性、bottom-up、数据真实性、渲染与运行验收标准。
- 验证结果：`compute-tracker` 的 `npm run check` 通过，13 条来源通过 schema 检查；原 Next.js 工作台构建通过且路由列表不含 `/compute-tracker`；独立服务运行在 `http://127.0.0.1:4180`；桌面与 390px 移动端浏览器检查控制台 0 错误、无横向溢出；筛选、展开来源、导出研究摘要均可用。

旧方案记录，已废弃：

- 用户复核指出 `/compute-tracker` 数据层缺口过多，判断成立；本轮已把页面结论从“完成闭环”降级为“框架可用，数据未闭环”。
- 页面新增数据覆盖率和缺口清单：开源价格采集入口已确认，但 H100/H200/B200 GPU-hour 数值快照、容量/库存、折扣/租期、ORNN/OCPI 指数仍未接入。
- Capex / 订单事件日志已补入 AMZN 与 ORCL 官方事实：AMZN Q1 2026 cash capex $43.2B；ORCL FY26 capex $55.663B、RPO $638B。当前官方 capex 事实仍不支持“算力稀缺破裂”确认。
- 当前验收结论改为：频率隔离和 capex 官方来源通过；价格数据、容量验证未通过。产品只能作为监控准备页，不是完整 Tracker。
- 最新构建：Next.js Webpack 构建通过。下一步需要接入可复现价格快照和容量样本。

本次更新：

- 已新增 `AI 算力稀缺溢价 Tracker` 产品页，入口为 `/compute-tracker`，并接入左侧导航。
- 页面按“三层闸门”展示：价格预警、容量验证、Capex 确认；明确禁止把日频、周/月频、季频指标硬加权成一个总分。
- 页面登记真实可追溯来源：`becloudready/gpu-price` 作为价格层开源采集入口，Microsoft / Meta / Alphabet 官方财报或电话会作为 capex 层事实来源；没有本地价格快照时不显示伪价格。
- 页面新增反证与替代解释、来源质量评估、验收闸门，覆盖公开市场研究子进程提出的频率隔离、口径清楚、演示标记、反证可见、质量风险可见要求。
- 本轮采用多进程模式：公开市场研究、产品构建、测试环境三个子进程并行，主进程负责整合和最终验收；最终完成需要四方投票全票通过。
- 原本产品页曾完成框架级查验，但经用户复核后已降级；该入口已被独立产品 `compute-tracker/` 替代。
- 本轮使用 skill：`e20`、`build-web-apps:frontend-app-builder`、`build-web-apps:frontend-testing-debugging`。

当前项目是中文财经助理，主线为 `apps/web` Next.js 工作台 + `services/research` Python 研究服务。

本次更新：

- 已按 Product Design 二轮审查建议完成全部修复，并做三轮复审：
  - 新增 `docs/PRODUCT_DESIGN_AUDIT_R3_2026-06-03.md`。
  - 新增截图证据目录 `docs/product_design_audit_r3_2026-06-03/`。
  - 移动端导航改为顶部短栏，模块横向滑动，当前个股压缩展示，修复左侧导航占满首屏的问题。
  - 顶部全局搜索改为“跳转搜索”，股票池添加搜索改为“查找可加入标的”，区分跳转和添加两种意图。
  - 技术研究页首屏新增“点位来源”，展示当前价、确认位、失效位、来源和距离。
  - 消息雷达首屏新增“先看原文”，展示 1-3 条关键新闻原文、来源、时间和命中词。
  - 数据源状态页首屏新增“需要处理的组件”，直接点名问题组件、影响页面和处理动作。
  - 首页右栏从“股票池快照”改成“为什么要看这些”，展示每只股票进入关注的原因。
  - 新增 `/favicon.ico`，控制台不再出现 favicon 404。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 验证结果：TypeScript 通过；Python 编译通过；Next.js build 通过；关键页面 6/6 返回 200；favicon 返回 200；复审控制台 0 错误。
- 本轮使用 skill：Product Design、playwright。

本次更新：

- 已使用 Product Design 插件完成第二轮产品审查：
  - 新建 `docs/PRODUCT_DESIGN_AUDIT_R2_2026-06-03.md`。
  - 新建截图证据目录 `docs/product_design_audit_r2_2026-06-03/`，覆盖首页、股票池、个股总览、技术研究、消息雷达、研究报告、数据源状态、移动端首页、移动端个股页、股票池搜索 NVDA。
  - 主要结论：上一轮统一判断头、首页三栏任务、消息影响路径、投资假设和数据源仪表盘方向有效，但还没有完全解决“结论和证据分离”“移动端首屏不可用”“数据源状态不够可执行”的问题。
  - 最高优先级体验问题：手机端左侧导航占掉首屏，用户打开后看不到真正判断内容。
  - 下一步建议：移动端改短导航；技术页首屏加入点位来源小图；消息页首屏展示 1-3 条关键原文；数据源状态直接指出问题组件和影响页面；区分“跳转搜索”和“添加搜索”；补 favicon。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 本轮使用 skill：Product Design、playwright。

本次更新：

- 已根据 Product Design 审查建议完成一轮产品编排层调整：
  - 新增统一 `DecisionHeader`，个股总览、技术研究、消息雷达、研究报告、数据源状态页共享同一套“当前判断 / 数据新鲜度 / 下一步动作”入口。
  - 新增过期数据降级逻辑：超过 24 小时提示谨慎，超过 72 小时直接提示“先刷新再判断”，避免旧缓存继续包装成有效结论。
  - 首页“优先处理队列”改为三栏任务制：必须复核、可以等待、数据问题，让用户先知道今天该处理什么。
  - 消息雷达增加“命中实体”和“影响路径”，说明新闻为什么被选中、会影响哪个判断环节。
  - 研究报告页新增“投资假设”，把长期研究从指标堆叠改成商业模式、增长、估值、外部预期、资金行为五个待验证问题。
  - 数据源状态页新增“对页面的影响”，说明行情、消息、研究报告、机构观点、资金行为分别影响产品哪一部分；能力矩阵改为折叠显示。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 验证结果：TypeScript 检查通过；Python 编译通过；Next.js build 通过；首页、09988 总览、09988 技术、09660 消息、09988 研究报告、09988 数据源状态均返回 200，且新结构文字已在页面中渲染。
- 本轮使用 skill：Product Design。

本次更新：

- 已按用户点名的 Product Design 插件流程完成一次全产品设计审查：
  - 真实启动本地产品，走首页、股票池、个股总览、技术研究、消息雷达、研究报告、数据源状态等核心路径。
  - 保存截图证据到 `docs/product_design_audit_2026-06-03/`。
  - 新建 `docs/PRODUCT_DESIGN_AUDIT_2026-06-03.md`。
  - 审查结论：产品能力已经很多，但核心短板是编排层和信任层。下一轮应优先做统一 `Decision Header`、过期缓存降级、首页任务重排、消息入选理由强化、研究报告假设驱动和数据源状态瘦身。
  - 本轮未修改功能代码。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。

本次更新：

- 已完成缓存与刷新机制专项优化：
  - 新增 `services/research/research_engine/refresh_policy.py`，把刷新策略从全量快照一套 TTL 改为模块独立 TTL。
  - 当前刷新频率：行情交易时段 15 分钟 / 非交易 6 小时；技术 30 分钟 / 6 小时；消息 30 分钟 / 2 小时；机构观点 24 小时；资金行为 4 小时 / 12 小时；基本面 12 小时 / 24 小时；首页组合缓存 15 分钟。
  - 后台队列刷新模块时不再被全量 snapshot TTL 拦住；模块按自己的 TTL 判断是否过期。
  - 新增股票后自动排队刷新 6 个模块：market、news、technical、analyst_view、capital_flow、fundamental。
  - 模块刷新失败后增加 20 分钟退避，避免失败源被页面访问反复触发；手动刷新仍可强制执行。
  - `CacheStatusBar` 在刷新完成后自动触发页面更新，减少用户手动刷新浏览器的需求。
  - 新增 `tools/verify_refresh_strategy.py`，用于验证模块 TTL、空模块、schema mismatch 和首页缓存过期逻辑。
  - 新建 `docs/CACHE_REFRESH_STRATEGY_2026-05-11.md` 记录策略、频率和验证结果。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 验证结果：Python 编译通过；TypeScript 检查通过；Next.js build 通过；`verify_refresh_strategy.py` 通过；`verify_provider_contracts.py` 通过；首页、09988 总览、09988 研究报告、09988 数据源状态均返回 200；09988、600036、MSFT 模块状态稳定，队列为空。

本次更新：

- 已修复研究报告页“资金行为/机构观点”问题：
  - 港股南向资金不再使用旧的 AkShare 参数，改为 `stock_hsgt_stock_statistics_em(symbol="南向持股", start_date, end_date)`，09988、00700、09660 均能返回真实南向持股变化。
  - 港股资金行为不再把同一份南向数据重复显示为“主资金”和“南向”，只保留南向持股、内部人、机构/基金持仓等真实分项。
  - A股机构观点不再只有 Tushare 权限占位，新增 AkShare 同花顺盈利预测；600036 可显示“机构预测可参考”和机构预测明细，但目标价仍如实显示不足。
  - 修复模块缓存迁移覆盖问题：读取旧 snapshot 时不再用旧空模块覆盖已经刷新的 `capital_flow` / `analyst_view` 模块缓存。
  - 研究报告资金行为区新增分项卡片，明确展示每个资金源是否真实可用、失败原因或权限不足，不再只显示“可用分项：暂无”。
  - 新增 `tools/verify_provider_contracts.py`，用 AkShare 函数签名和真实样本检查数据源契约，避免再次靠记忆改接口参数。
  - 更新 `lessons.md`：数据源接口改动必须先查签名、跑真实样本、再看页面。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 验证结果：Python 编译通过；TypeScript 检查通过；Next.js build 通过；provider contract 检查通过；09988、600036、MSFT 研究报告页 HTTP 200；样本缓存显示 09988/00700/09660 港股南向可用，600036 北向和 A股机构预测可用，MSFT/AAPL 美股机构持仓和内部人可用。

本次更新：

- 已按用户决定删除“情绪观察”一级模块：
  - 左侧导航删除“情绪观察”，当前模块变为 7 个：盘前任务、股票池、个股研究、技术研究、消息雷达、研究报告、数据源状态。
  - 删除前端页面 `/sentiment` 和 `/stocks/[symbol]/sentiment`。
  - 个股总览删除“情绪面”证据卡，不再把热度/讨论量包装成投资判断。
  - 首页删除“情绪观察”和社媒探针状态，数据源摘要只展示可验证的数据组件。
  - 数据源状态页删除“社媒 / 情绪面解析”，改为行情、消息、机构观点、资金行为、研究数据五类仪表。
  - 后端删除 `sentiment` 模块刷新、模块缓存、状态汇总、调度优先级和 `SentimentProbe` 能力注册。
  - 删除 `services/research/research_engine/sentiment.py` 和 `social_sources.py`。
  - 保留消息雷达内部的新闻内容倾向字段，但前端改为“消息倾向/消息风险”，不再作为独立情绪页。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 验证结果：Python 编译通过，TypeScript 检查通过，Next.js 构建通过；首页、09988 个股页、09988 数据源页返回 200；`/sentiment` 和 `/stocks/09988/sentiment` 返回 404；09988 模块列表已不包含 `sentiment`。

本次更新：

- 已修复技术研究页用户反馈：
  - 60 分钟线切换后不再空白，日线和 60 分钟线会使用各自正确的时间格式。
  - 图表新增“当前价格”和“当前成交量”文字标识，避免只看到红色高亮但不知道含义。
  - “成本与近端区域”的远端/近端压力百分比不再溢出。
  - “证据链”的解释图标回到卡片内部，分组标题同步展示通过/观察/未通过数量。
  - 证据链顶部统计改为从实际 `signals` 重新计算，避免展示数字和底层证据不一致。
- 已修复港股 AkShare 新闻召回：
  - 港股不再依赖财联社全市场快讯作为公司新闻。
  - 改为用动态公司关键词调用东方财富搜索，优先公司简称、代码等实体词，并保留实体过滤。
  - 实测 09660 地平线和 09988 阿里巴巴的 AkShare 原始新闻与相关候选已恢复到正常数量。
- 已调整左侧八个模块顺序：
  - 盘前任务、股票池、个股研究、技术研究、消息雷达、情绪观察、研究报告、数据源状态。
- 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 验证结果：Python 编译通过，TypeScript 检查通过，Next.js 构建通过；09660 技术页和消息页 HTTP 均为 200；浏览器真实页面已检查 60 分钟图表、图表标识、证据链、成本区域和消息雷达。

本次更新：

- 已完成用户路径与 UI 反映测试：
  - 模拟港股用户、A股用户、美股用户，从首页进入个股，再点击消息雷达、情绪观察、研究报告、数据源状态。
  - 修复个股页缓存失败态：个股相关 6 个页面全部改为动态渲染，避免继续显示旧的“数据暂不可用”。
  - 修复 JSON 清洗：后端响应和缓存写入会把 `NaN` / 无穷值清成空值，日期转字符串。
  - 修复空模块缓存阻塞页面：模块读取不再同步等待慢源，空模块交给后台刷新。
  - 个股总览情绪卡现在直接显示实际来源，例如“行为热度组合”或 “ApeWisdom”。
  - 新建 `docs/USER_FLOW_UI_REFLECTION_TEST_2026-05-10.md`。

- 已完成 15 只股票页面与数据抓取测试：
  - 样本：5 只港股、5 只 A股、5 只美股。
  - 页面访问：15/15 股票、75/75 页面返回 200。
  - 发现并修复旧社媒缓存问题：港股/A股旧缓存仍显示雪球或东方财富股吧优先；现在会自动迁移到行为热度组合。
  - 发现并修复模块缓存空值问题：`analyst_view` 和 `capital_flow` 缓存存在但内容为空时会自动回填。
  - 发现并修复机构观点日期序列化问题：缓存写入现在会把日期转为字符串。
  - 新建 `docs/PRODUCT_TEST_15_STOCKS_DATA_2026-05-10.md`。
  - 当前结论：港股/A股社媒主源已反映为行为热度组合；美股主源为 ApeWisdom；A股机构观点仍需 Tushare 权限。

- 已完成 Blueprint 三组整体更新：
  - 第一组：BaoStock 估值字段、Marketaux/Alpha/GDELT 新闻增强、行为热度能力注册。
  - 第二组：新增 `analyst_view` 机构观点、`capital_flow` 资金行为、`market_structure` 市场结构，并接入缓存、调度、个股页、研究报告页和数据源状态页。
  - 第三组：新增 Tushare provider，接入 Tushare 估值/财务/资金/质押能力，补入 QVIX、基金持仓、可转债和 Finnhub ESG。
  - 新建 `docs/PRODUCT_TEST_BLUEPRINT_FULL_2026-05-10.md`，并更新三组验收记录。
  - 当前验证：Python 编译通过、后端能力注册测试通过、模块缓存摘要测试通过、关键 TSX 页面类型检查通过、Next.js build 通过、页面 HTTP 查验通过。
  - 当前本地查验地址：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 当前构建方式：`NEXT_TEST_WASM=1 ./node_modules/.bin/next build --webpack`；本机原生 SWC 有签名问题，生产查验使用 `NEXT_TEST_WASM=1 ./node_modules/.bin/next start -p 4173`。

- 已升级产品集成 Blueprint：
  - 更新 `docs/PRODUCT_INTEGRATION_BLUEPRINT_2026-05-10.md`。
  - 按用户要求，以 `docs/PRODUCT_CAPABILITY_INTEGRATION_STRUCTURE_2026-05-10.md` 为主设计，Blueprint 只作为代码现实和接口补充。
  - 新增未来研发方向：能力归集层、判断编排层、原生能力优先、冲突可见、自动适配、数据透明。
  - 新增 V37-V46 完整升级安排：能力契约、消息与情绪质量、机构观点、资金行为、基本面、市场结构、Decision Header 2.0、数据源状态仪表盘、后台刷新编排、产品验证体系。
  - 当前关键决定：下一步正式研发必须先做 V37 能力契约，不应直接从单个接口接入开始。

- 已完成产品能力整合结构报告：
  - 新建 `docs/PRODUCT_CAPABILITY_INTEGRATION_STRUCTURE_2026-05-10.md`。
  - 把八源能力图谱转成产品结构蓝图，明确后续产品不按 API 源堆功能，而按行情、技术辅助、消息、情绪热度、机构观点、资金行为、基本面、市场结构八层组织。
  - 报告定义了 8 个页面如何承接能力、8 个技术栈如何进入产品、冲突时采用原生/自研/第三方的判断规则，以及接入前后的产品结构变化。
  - 当前关键决定：新增能力必须先进入能力层，输出统一 `Insight Card`，再由 `Decision Header` 编排成用户可执行的下一步判断；本轮不改代码。

- 已完成八源能力图谱汇总：
  - 新建并更新 `docs/DATA_PROVIDER_CAPABILITY_MAP_2026-05-10.md`。
  - 汇总 AkShare、BaoStock、Yahoo Finance/yfinance、Finnhub、Marketaux、Alpha Vantage、Tushare、ApeWisdom，并补充 GDELT。
  - 已把 `docs/PRODUCT_FINDINGS_AKSHARE_GAPS_2026-05-10.md` 合并进总能力图谱，补入 AkShare 重大遗漏、页面映射、专项接入包、provider 拆分和产品路线关系。
  - 当前关键决定：后续不再按“数据源”堆功能，而是按行情、技术辅助、情绪热度、消息、机构观点、资金行为、基本面、市场结构等能力层组织 provider。

- 已汇总产品侧 AkShare 能力发现：
  - 新建 `docs/PRODUCT_FINDINGS_AKSHARE_GAPS_2026-05-10.md`。
  - 立即可用的重大补充包括：港股分析师评级/目标价、港股估值/成长/规模对比、港股分红、北向个股持仓、内部人交易、市场宽度、A股历史估值百分位、龙虎榜机构动向。
  - 建议接入顺序：港股基本面增强包、A股资金和市场结构包、跨市场事件信号包、低频研究材料包。
  - 产品原则：后台刷新、分层展示、动态适配新增股票、不包装失败数据。

- 已完成 AkShare 本地源码复盘：
  - 扫描 `akshare/stock`、`stock_feature`、`stock_fundamental`、`news`，确认很多有用能力不在行情/新闻主路径里。
  - 新建 `docs/AKSHARE_SOURCE_REVIEW_2026-05-10.md`。
  - 实测可用接口包括：千股千评评分历史、筹码分布、沪深港通个股持仓、百度投票、港股财务指标、美股财务指标、港股盈利预测、雪球基础资料、东方财富热词、相关热股。
  - 标记不稳定接口包括：投资者互动、机构调研、东方财富研报、融资融券、大单成交、百度估值、热榜总表。
  - 形成架构建议：AkShare 后续拆成 `akshare_market`、`akshare_attention`、`akshare_capital`、`akshare_fundamental`、`akshare_research_material` 五类 provider，避免一个慢接口拖累整体。

- 已完成行为热度组合源接入：
  - 新增 `behavior_heat` 组合源，A股/港股优先读取东方财富人气榜、雪球讨论排行、百度股市通热搜。
  - 东方财富人气榜支持 A股 `SH/SZ` 代码和港股 5 位代码，可读取当前排名和 10 分钟粒度排名曲线。
  - 雪球 Screener 支持 A股/港股，无需登录读取 `tweet7d` 和 `follow`；不读取帖子正文，因此只做关注度，不做方向判断。
  - 百度股市通热搜接入为大众搜索热度补充；未进入榜单时明确显示未命中。
  - A股/港股社媒主源从股吧帖子量升级为行为数据优先，股吧降级为文本样本补充。
  - 新建 `docs/PRODUCT_TEST_BEHAVIOR_SOCIAL_HEAT_2026-05-10.md`。
  - 抽样 09660、09992、03690、01810、09868、600036、002594、300750、688981、000858，10/10 真实探针成功。
  - 验证：Python 语法检查通过。

- 已继续完成港股社媒热度源：
  - 港股社媒主源从雪球公开入口改为东方财富港股吧，代码格式为 `HK00700`、`HK09988`、`HK09660`。
  - 东方财富股吧现在支持 A 股和港股；港股方向判断额外要求标题命中公司实体词，样本不足时只显示热度，不计算方向。
  - 新增富途 / moomoo、AASTOCKS 利好利淡、经济通评论、Investing.com 评论为港股候选源；雪球保留候选源；未验证稳定前不入分。
  - 访问测试：moomoo 社区页可打开但真实帖子由前端加载；Investing.com 评论页本地 403；经济通个股评论页和 AASTOCKS 个股页可访问，但定位为观点/新闻反应补充，不是主社区热度。
  - 新建 `docs/PRODUCT_TEST_HK_SOCIAL_HEAT_2026-05-10.md`。
  - 抽样 00700、09988、09660、01810、03690：均返回真实热度样本；腾讯、小米、美团可进入社媒试算；阿里、地平线只显示热度。
  - 验证：Python 编译通过。

- 已按算法团队新闻源清单完成公司新闻/官方公告源接入：
  - 港股 AkShare 优先尝试 `stock_news_em("09660.HK")`，再走已过滤的公司新闻逻辑；不再把财联社全市场快讯作为港股公司新闻兜底。
  - 美股 Finnhub company-news 已作为主力公司新闻源，窗口扩到 7 天，并预标公司新闻。
  - 新增 A 股 Tushare `anns_d` 官方公告源，注册为增强源；需要 `TUSHARE_TOKEN` 和接口权限。
  - 新增港股 HKEXnews 官方披露源，注册为增强源；通过 HKEX active stock list 把股票代码转成内部 `stockId`。
  - Marketaux 已改为港股/美股按股票代码查询，例如 `9660.HK`、`MSFT`，仅作为英文增强源。
  - 新建 `docs/NEWS_SOURCE_INTEGRATION_2026-05-10.md`；更新 `README.md`、`.env.example`、`requirements.txt`。
  - 验证：Python 编译通过；09660 港股东方财富返回标题命中公司新闻；09988 无关东方财富新闻被过滤；MSFT Finnhub 返回 20 条；00700 HKEXnews 返回官方披露 PDF；600036 A 股东方财富返回 10 条。
  - 当前本地未检测到 `MARKETAUX_API_TOKEN` 和 `TUSHARE_TOKEN`，对应增强源会显示缺少凭证，不会伪装成功。

- 已开始推进 A 股社媒热度源：
  - 东方财富股吧已从公开页面探针升级为公开股吧 API，按 A 股 6 位代码读取帖子、时间、阅读和评论。
  - A 股情绪层继续区分“讨论热度”和“观点方向”：股吧阅读/评论只进入热度和社媒试算，不直接包装成看多/看空。
  - 新增金十微博舆情作为 A 股备用热度源；只有公司进入 24 小时微博舆情榜时才展示。
  - 新增淘股吧为 A 股候选源，但因公开入口和个股映射未验证，暂不抓取、不入分。
  - 热度标签已收紧：冷启动或缺少足够 24/48 小时对比时，不写“异常升温”；高阅读/高评论只写“高热度”。
  - 新建 `docs/PRODUCT_TEST_A_SHARE_SOCIAL_HEAT_2026-05-10.md`，并更新 `docs/SOCIAL_SENTIMENT_BEST_PRACTICES_2026-05-09.md`。
  - 抽样 002594、601318、300760、601899、688981、000333：东方财富股吧均返回真实样本；金十微博舆情对比亚迪备用源验证成功。
  - 验证：Python 编译通过。

- 已开启并推进一小时新闻模块循环测试：
  - 目标：不断新增股票，检索新闻，核查新闻机制规则，迭代修正，再换新公司验证。
  - 使用港股、美股、A股三条线并行测试，并使用 sub-agents 分别做市场专项诊断。
  - 新建 `docs/NEWS_LOOP_TEST_2026-05-09.md`。
  - 覆盖超过 50 只新增/模拟新增股票。
  - 已完成通用修复：港股 code-only 中文名称富化、A股 AkShare 名称兜底、保存层精确搜索富化、系统识别理由清洗、英文公司名后缀清理、普通词 ticker 严格匹配、关注理由只做搜索扩展、东方财富个股流精准标注收紧、资金/持仓/榜单/ETF/技术突破类低信号过滤、selected_count 回填修正。
  - 验证：Python 编译通过；Next.js build 通过；前端首页 200；Research API watchlist 200。

- 已按用户要求把新闻模块修复收口为动态机制，而不是单票补丁：
  - `AkShare` 港股新闻源不再盲信 `stock_info_global_cls(symbol=name)`，只有标题真实命中公司实体词才标注为公司新闻。
  - `AkShare` 的匹配词改为统一来自 `CompanyProfile`，新增股票会自动获得公司名、简称、代码、市场代码等匹配词。
  - `prepare_rows()` 只信任带 `precision_matched_terms` 的预标注新闻，避免全市场快讯被假精准放行。
  - 港股 `Google News RSS` 已保留大陆简体优先查询 + 香港繁体补充查询。
  - `Forza Horizon / 极限竞速` 排除从 09660 单票补丁改为基于公司名含“地平线/Horizon”的通用排除规则。
  - 验证 09660：原始 39 条、实体候选 21 条、入选 5 条；AkShare 超时不再生成假新闻，Yahoo 无关候选未入选。

- 已完成 10 用户产品体验模拟：
  - 新建 `docs/USER_SIMULATION_10_USERS_2026-05-09.md`。
  - 覆盖首页、股票池、阿里消息、地平线消息、Shopify 新增股票消息、MSFT 技术、AAPL 研究报告、招商银行数据源、泡泡玛特情绪、移动端快速查看。
  - 页面均可访问，缓存速度表现很好；动态新闻引擎对新增股票可用。
  - 主要问题：股票池页两个搜索框含义不清；缓存时间表达不直观；技术页仍过载；弱覆盖新闻的行动语气应降级；关注理由不应过度进入搜索词包；数据源状态页需要更直白说明“对当前结论的影响”。

- 已完成 V36 动态新闻引擎：
  - 新增 `services/research/research_engine/news/company_profile.py`，把新增股票自动转成公司实体档案：代码、市场代码、名称变体、产品/业务线、排除词和搜索词。
  - 新闻召回改为精准主源优先：公司级 API、Google News、Yahoo Finance；广播 RSS、华尔街见闻、GDELT、行业媒体、RSSHub、Marketaux、Alpha Vantage 改为按需增强。
  - 新增实体匹配：公司新闻、业务线新闻、高管相关新闻、产品/业务线弱匹配；Yahoo Finance 搜索结果必须通过实体匹配，避免小港股噪音新闻被当作公司新闻。
  - 新增股票后自动入队刷新 `market` 和 `news` 模块，前台继续读缓存，不在用户打开页面时阻塞抓取。
  - 新闻结果新增 `entity_profile` 和 `recall_diagnostics`；个股消息雷达页新增“自动召回”“公司档案”“召回漏斗”。
  - 新建 `docs/PRODUCT_TEST_NEWS_DYNAMIC_ENGINE_2026-05-09.md`。
  - 抽样：09992、03690、SHOP 覆盖稳定；09660 明确标记“实体匹配偏弱”，不再用无关新闻凑满。
  - 验证：Python 编译通过；Next.js build 通过；首页、股票池、09660/SHOP 消息雷达页 200。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。

- 已完成公司级新闻覆盖最佳实践研究：
  - 新建 `docs/NEWS_COVERAGE_BEST_PRACTICES_2026-05-09.md`。
  - 调研 OpenBB、Finnhub、Marketaux、NewsCatcher、Event Registry 等新闻/金融数据平台做法。
  - 核心结论：解决消息雷达覆盖差，不能继续靠堆 RSS，而要做“公司实体驱动的新闻召回系统”。
  - 推荐架构：Company Entity Master -> 多路召回 -> 实体对齐 -> 事件聚类 -> 精排 -> 后台缓存。
  - 推荐指标：raw_count、entity_matched_count、selected_event_count、source_diversity、freshness_lag、false_positive_rate。
  - 下一版重点应从“加新闻源”转为“重构新闻引擎召回与实体对齐层”。

- 已完成消息雷达覆盖不足诊断和第一轮修复：
  - 新建 `docs/NEWS_COVERAGE_DIAGNOSIS_2026-05-08.md`。
  - 抽样检查阿里、腾讯、泡泡玛特、地平线、百度、美团的新闻源状态、原始候选、相关候选、入选新闻。
  - 结论：目前真正稳定贡献入选新闻的源主要是 `Google News RSS`；AkShare/华尔街见闻/广播 RSS 多数是全市场快讯或频道流，raw 有数据但相关候选经常为 0；行业媒体容易超时；Marketaux/Alpha Vantage 本地 `.env` 未启用。
  - 已修复港股 AkShare 新闻读取顺序，先尝试公司级接口，失败再回退全市场财联社快讯。
  - 已修复 Marketaux credential 名称不一致问题，从 `MARKETAUX_API_KEY` 改为 `MARKETAUX_API_TOKEN`。
  - 已新增百度集团到 catalog、alias、板块代理和新闻关键词包，避免百度港股只用英文名导致中文新闻命中不足。
  - 验证：Python 编译通过；6 只股票新闻模块刷新通过且状态 idle；阿里/腾讯/泡泡玛特/百度/美团均能入选 5 条；地平线仍只有 2 条，根因是缺少第二个稳定公司级新闻源。

- 已按 OpenBB 研究结论完成 V35 OpenBB-style 数据接入层第一轮落地：
  - 新建 `docs/PRODUCT_TEST_V35_OPENBB_DATA_ACCESS_2026-05-08.md`。
  - 新增 `services/research/research_engine/data_access/`，包含标准查询对象、统一结果对象、provider 能力模型、注册表、查询执行器和异常层。
  - 新闻 `source_plan()` 改为从 provider registry 自动生成，覆盖公司新闻、通用资讯、广播 RSS、增强源，不再按市场手写固定列表。
  - 行情结果新增 `provider_coverage` 和 `execution_trace`，记录日线、benchmark、sector 的实际来源。
  - 新闻结果新增 `provider_coverage`、`execution_trace` 和 `display` 字段。
  - 基本面结果新增 provider coverage，并补齐美股 yfinance 字段：EV/EBITDA、Beta、目标价、分析师数量。
  - 技术指标新增 Clenow 动量质量分、Parkinson 波动率和 1 年波动分位。
  - 数据源状态页新增“能力矩阵”，并在行情/新闻解析区展示本次执行痕迹。
  - 验证：Python 编译通过、TypeScript 检查通过、Next.js build 通过；首页和阿里数据源状态页均 200；阿里能力矩阵返回 15 个能力；market/news 模块刷新后状态均 idle。
  - 当前服务：产品 `http://127.0.0.1:4173` 使用生产模式；Research API `http://127.0.0.1:4174`。

- 已完成 OpenBB 源码研究：
  - 新建 `docs/OPENBB_RESEARCH_2026-05-07.md`。
  - 阅读 OpenBB 官方仓库 README、LICENSE，并通过 sparse clone / `git show` 深入查看核心源码。
  - 重点拆解了 `Fetcher`、`Provider`、`Provider Registry`、`RegistryMap`、`QueryExecutor`、`ProviderInterface`、`Router.command`、`OBBject`、标准行情模型、标准公司新闻模型、yfinance 行情 provider、FMP/Biztoc 新闻 provider 和 MCP server。
  - 核心结论：OpenBB 最值得参考的是“标准模型 + provider 注册 + 统一查询执行器 + 多入口复用”，不是 UI，也不是直接拿数据源代码。
  - 许可判断：OpenBB 为 AGPL-3.0，只能学习架构思想，不能复制源码进入项目。
  - 对本项目的启发：下一步可把行情、新闻、基本面、情绪统一到轻量 OpenBB-style data access layer，再接入现有 Fincept-style DataHub 刷新调度。

- 已完成 FinceptTerminal 源码研究：
  - 克隆并阅读 `Fincept-Corporation/FinceptTerminal` 关键源码与文档。
  - 新建 `docs/FINCEPT_TERMINAL_RESEARCH_2026-05-07.md`。
  - 核心结论：最值得参考的是 DataHub 数据编排层，而不是 C++/Qt UI 或直接复制数据源代码。
  - 可吸收方向：topic 化数据订阅、Producer 策略、TTL/最小刷新间隔/in-flight 去重、DataHub stats、新闻源分层和事件聚类、数据源注册表。
  - 许可判断：FinceptTerminal 根目录为 AGPL-3.0 + 商业许可，后续只能学习架构思想，不能复制代码。

- 已按 `docs/FINCEPT_RESEARCH_SYNTHESIS_2026-05-07.md` 完成新闻精准化和 DataHub 方向收口：
  - 新增 `services/research/research_engine/news/sources/rss_broadcast.py`，接入 CNBC、Nikkei Asia、SCMP Business、HKEX News 广播 RSS，作为新闻候选补充层。
  - 修复 09660 地平线机器人关键词：不再自动使用单独 `Horizon`，并加入 Horizon Investments / Horizon Quantum / Horizon Advisory / Horizon Blue Cross 等排除词。
  - 新闻相似事件去重阈值从 0.72 调整为 0.60，重复报道会合并计数。
  - 新闻结果新增 `source_explanation`，说明每个来源的原始数量、相关候选、入选数量和剔除原因。
  - 消息雷达页面新增“来源筛选解释”区块，重点新闻显示同类报道合并数和匹配类型。
  - 新建 `docs/PRODUCT_PLAN_DATAHUB_ORCHESTRATION_2026-05-07.md`，把 DataHub 数据编排层作为下一次大版本方向。

- 已完成 `docs/REVIEW_2026-05-06-R22.md` 修复：
  - 新建 `docs/FIX_LOG_2026-05-06.md`，按 R22 问题编号记录修复、验证和遗留说明。
  - 修正后台刷新状态：模块化刷新成功且五个模块缓存齐全时，会把旧整股 failed 状态恢复为 idle，避免旧失败状态误导页面。
  - 顺带排查 09660 港股行情滞后对 09988 的影响：09988 当前同样识别 AkShare 滞后到 `2026-05-05`，并切到 Yahoo 最新 `2026-05-06`。
  - 后台失败记录从只保存错误类型改为保存“错误类型 + 具体信息”，后续可以直接看出是否和行情路由、日期比较、源超时有关。
  - `market` 模块刷新已改为轻量刷新，只取日线、60 分钟线和事件日历，不再跑完整快照，避免行情刷新被新闻/估值/基本面拖到超时。
  - 修正 A 股 AkShare 新闻路由：东方财富个股新闻成功时不再继续拉广泛财联社快讯；东方财富个股新闻标记为“公司新闻”精准来源。
  - A 股新闻主源等待时间调到 8 秒，避免把正常秒级波动误判成 Timeout。
  - 复核 09988 AkShare：当前 AkShare 港股返回的是财联社全市场快讯，不是阿里公司级新闻，因此继续不强行入选。
  - 验证：Python 编译通过；09988/09660/600036 整股刷新状态均 idle 且错误数 0；09988/09660 行情均切到 Yahoo 最新 `2026-05-06`；600036 AkShare 代理失败后切 BaoStock 最新 `2026-05-06`；600036 新闻模块 8 个候选、5 条入选，其中 AkShare 10 条候选、3 条入选；09988 新闻模块 11 个候选、5 条入选；首页、09988 数据源状态页、600036 消息页均 200。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。

- 已完成 09660 地平线行情审查和修正：
  - 新建 `docs/DATA_AUDIT_09660_2026-05-06.md`。
  - 查明 `7.31` 不是收盘价，而是技术确认位；页面当前价格原本是 AkShare 的 `2026-05-05` 收盘 `7.05`。
  - 发现真实架构问题：港股主源 AkShare 更新慢，Yahoo 已有 `2026-05-06` 数据但路由没有自动比较新旧。
  - 修正港股行情路由：如果 Yahoo 日期更新，则自动切换 Yahoo，并写明 AkShare 滞后原因。
  - 页面价格标签从“当前收盘价”改为“最新价 / 最近收盘”，避免盘中 Yahoo 数据被误读成正式收盘。
  - 验证后 09660 当前使用 `yahoo-chart:9660.HK`，最新日期 `2026-05-06`，最新价 `7.01`，页面 200。

- 已完成 V34 长期研究工作台：
  - 新建 `docs/PRODUCT_TEST_V34_FUNDAMENTAL_WORKBENCH_2026-05-06.md`。
  - 研究报告页 `/stocks/[symbol]/report` 从“估值卡片 + 待补材料”升级为完整长期研究工作台。
  - 页面现在包含：长期结论、估值判断、业绩节奏、资金与持仓、研究三角、数据可信度、长期研究问题。
  - 缺失数据明确显示“数据不足”，不包装成结论。
  - 验证：Python 编译、TypeScript 检查、Next.js build 通过；首页、MSFT、09988、600036、AAPL 研究报告页均 200。
  - 当前前端使用生产模式 `http://127.0.0.1:4173`；开发模式会触发本机文件监听数量上限，导致路由误判 404。

- 已完成 V33.5 首页组合级模块，V33 收口：
  - 新建 `docs/PRODUCT_TEST_V33_5_PORTFOLIO_MODULE_2026-05-06.md`。
  - `services/research/main.py` 新增 `portfolio_preflight()`，用 `module_cache` 保存组合级首页摘要。
  - 首页 `/api/dashboard/preflight/summary` 现在优先读取 `__PORTFOLIO__ / portfolio` 缓存。
  - 股票池 symbol 列表变化时会自动重建组合缓存，避免新增/删除股票后首页继续读旧组合。
  - 验证：Python 编译、TypeScript 检查、Next.js build 通过；首页 200；preflight summary 返回 `portfolio_cache.status = hit`。
  - V33 已完成：模块缓存、模块刷新、消息/情绪/技术/报告/总览页模块化读取、首页组合缓存均已落地。

- 已完成 V33.4 个股总览页模块化读取：
  - 新建 `docs/PRODUCT_TEST_V33_4_OVERVIEW_MODULE_PAGE_2026-05-06.md`。
  - 个股总览页 `/stocks/[symbol]` 已从完整 snapshot 切到 `market + technical + news + sentiment + fundamental` 模块组合。
  - 新增页面内 `composeOverviewSnapshot()`，只为兼容现有 UI 拼出总览所需字段，不触发完整研究计算。
  - 验证：Python 编译、TypeScript 检查、Next.js build 通过；MSFT 和 09988 个股总览页均 200。
  - 当前剩余：首页仍需 portfolio module；后续可补单模块接口或 overview 接口降低传输。

- 已完成 V33.3 技术页模块化读取：
  - 新建 `docs/PRODUCT_TEST_V33_3_TECHNICAL_MODULE_PAGE_2026-05-06.md`。
  - `apps/web/lib/api.ts` 新增 `getStockModuleBundle()`，一次读取多个模块。
  - 技术研究页 `/stocks/[symbol]/technical` 已从完整 snapshot 切到 `market + technical` 模块组合。
  - 技术页 UI 和交互不变，仍保留时间框架切换、图表、证据链、历史验证和指标展开。
  - 验证：Python 编译、TypeScript 检查、Next.js build 通过；MSFT modules 和 MSFT technical 页面均 200。
  - 当前剩余：个股总览页仍需 overview composer；首页仍需 portfolio module；后续可补单模块接口降低传输。

- 已完成 V33.2 页面改读对应模块：
  - 新建 `docs/PRODUCT_TEST_V33_2_MODULE_PAGES_2026-05-06.md`。
  - `/api/stocks/{symbol}/modules` 现在返回 `stock` 和每个模块的 payload。
  - 模块缺失时会自动入队刷新对应模块。
  - 个股消息雷达 `/stocks/[symbol]/news` 已从完整 snapshot 切到 `news` 模块。
  - 个股情绪观察 `/stocks/[symbol]/sentiment` 已从完整 snapshot 切到 `sentiment` 模块。
  - 个股研究报告 `/stocks/[symbol]/report` 已从完整 snapshot 切到 `fundamental` 模块。
  - 验证：Python 编译、TypeScript 检查、Next.js build 通过；MSFT modules、MSFT news、MSFT sentiment、09988 report 均 200。
  - 当前未切：技术研究页仍需 `technical + market` 组合；个股总览页仍需多模块 composer；首页仍需 portfolio module。

- 已完成 V33 第一版模块化缓存和刷新：
  - 新建 `docs/PRODUCT_TEST_V33_MODULE_REFRESH_2026-05-06.md`。
  - 新增 `module_cache` 和 `module_refresh_jobs` 两张 SQLite 表。
  - 完整快照生成后会自动拆成 `market / technical / news / sentiment / fundamental` 五个模块缓存。
  - 刷新接口支持模块参数，例如 `/api/stocks/09988/refresh?module=fundamental` 和 `/api/research/refresh?module=news`。
  - 后台队列支持模块优先级：行情、新闻优先，基本面和情绪靠后。
  - `snapshot/status` 会返回五个模块的缓存和刷新状态。
  - 前端 `CacheStatusBar` 已展示五个模块按钮，用户可以按模块刷新。
  - 修复 macOS 多线程后台 worker 中基本面 `fork` 子进程崩溃问题，改为 `spawn`。
  - 抽样验证：MSFT 模块缓存可用；阿里 `09988` 基本面模块可单独刷新，摘要为“估值合理；业绩转负”；首页、MSFT 个股页、09988 研究报告页均 200。
  - 当前仍是“模块层 + 旧快照兼容”，还不是彻底的 snapshot composer；V33.2 应把技术页、消息页、报告页分别改为只读对应模块。

- 已完成 2026-05-06 产品架构审查：
  - 新建 `docs/PRODUCT_ARCHITECTURE_REVIEW_2026-05-06.md`。
  - 从金融产品架构视角抽样测试：首页、股票池、MSFT/09988 个股页、研究报告页、数据源状态页、缓存接口、数据源健康接口、搜索和刷新接口。
  - 结论：产品能力已经足够丰富，主要矛盾变成“大快照系统”拖慢页面、刷新和模块验证。
  - 缓存接口表现很好：`snapshot/cached` 约 0.014 秒，`data-health` 约 0.009 秒；但页面仍在 1 秒以上，说明前端页面和全局布局仍有服务端等待。
  - 后台刷新方向正确，但当前队列是单 worker + 整只股票完整快照，缺少行情、新闻、技术、基本面、社媒的模块化优先级。
  - V32 基本面在 MSFT 可用，但 09988 仍显示研究/资金估值不可用，说明港股/A股基本面刷新和旧缓存迁移还没有形成稳定闭环。
  - 建议下一步 V33 先做模块化缓存和刷新：`market / technical / news / sentiment / fundamental` 分模块缓存、分模块刷新、分模块状态展示。

- 已完成 V31 产品测试：
  - 新建 `docs/PRODUCT_TEST_V31_2026-05-05.md`，记录首页、股票池、个股总览、消息雷达、情绪观察、技术研究、研究报告、数据源状态的主路径测试。
  - 验证阿里巴巴 8 个核心页面均可访问，个股页面读缓存后约 0.2 秒级返回。
  - 验证新增股票真实路径：在股票池搜索 `NVDA`，选择 NVIDIA 加入股票池，自动进入 `/stocks/NVDA`；首次无缓存时后台刷新启动，约 20 秒后缓存建立完成。
  - 修复股票池搜索两个交互问题：搜索按钮导致结果面板关闭、输入后立即搜索可能丢弃结果。
  - 修复本地开发地址问题：`next.config.ts` 加入 `allowedDevOrigins: ["127.0.0.1"]`，避免 127.0.0.1 下前端资源被 Next.js dev 拦截。
  - 已验证：Python 编译通过、TypeScript 检查通过、前端核心页面 200、Research 缓存/状态/手动刷新接口通过。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。

- 已完成数据源状态页架构调整：
  - 新增轻量接口 `GET /api/stocks/{symbol}/data-health`，只读取股票信息和已有缓存，不触发完整 `snapshot` 研究计算。
  - 数据源状态页从“接口状态表”改为“系统仪表盘”：总体可信度 + 四个仪表 + 影响范围 + 四个解析 section。
  - 四个仪表分别对应：行情/技术面、新闻/消息面、社媒/情绪面、研究/资金估值。
  - 新闻解析展示每个源的原始数量、入选数量、失败原因，并在已有数据下展示入选新闻和原文链接。
  - 研究解析补齐估值源、资金源、PE、ROE 等状态表达。
  - 已更新 `docs/PRODUCT_PAGE_DEFINITIONS_2026-05-04.md` 和 `docs/USER_EVAL_DATA_SOURCES_2026-05-05.md`。
  - 已验证：Python 语法检查通过、Next.js build 通过；09988、09660、MSFT、AAPL、600036、601899、09888、AMD、BRK-B、AXTI 的 API 和页面均 200，且不再出现“数据暂不可用”。
- 已完成数据源状态页 10 用户模拟评价：
  - 抽取 10 只股票：09988、09660、MSFT、AAPL、600036、601899、09888、AMD、BRK-B、AXTI。
  - 发现 10 只中只有阿里和 MSFT 完整加载，其余 8 只进入“数据暂不可用”，说明该页冷启动体验严重不足。
  - 新建 `docs/USER_EVAL_DATA_SOURCES_2026-05-05.md`，记录 10 类用户评价、共性问题和建议方向。
  - 结论：数据源状态页定位正确，但目前更像接口状态表；下一步应改为“结论可信度面板”，并使用轻量接口保证秒开。
- 已完成用户登录/交互路径模拟检查：
  - 使用本地页面路径模拟“进入首页 -> 查看股票池 -> 进入阿里/微软个股 -> 切换消息/情绪/技术/报告/数据源 -> 搜索标的”。
  - 发现首页摘要仍跳旧全局页，已改为基于当前优先个股进入 `/stocks/[symbol]/news`、`/sentiment`、`/data-sources`。
  - 发现港股个股页可能因为研究服务慢请求长时间等待，已给 6 个个股页面加入 9 秒失败保护；超时显示“数据暂不可用”，不展示半成品结论。
  - 新增 `docs/PRODUCT_INTERACTION_TEST_2026-05-05.md` 记录模拟路径、问题和验证结果。
  - 已验证：Next.js build 通过；首页、股票池、阿里巴巴 6 个个股页面、MSFT 个股页与技术页、搜索 `阿里` / `MSFT` 均通过。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已按用户结构反馈完成 V28.9 页面层级重构：
  - 新建 `docs/PRODUCT_PAGE_DEFINITIONS_2026-05-04.md`，定义 8 个左侧栏目各自的页面职责、内容顺序和交互规则。
  - `AppShell` 左侧 8 个导航入口改为同级真实页面：盘前任务、股票池、个股研究、消息雷达、情绪观察、技术研究、研究报告、数据源状态。
  - 左下角改为“当前个股”切换器，显示当前股票，可从股票池切换；切换时保留当前栏目，例如技术研究页切换股票后仍停留在技术研究。
  - 新增个股级独立页面：
    - `/stocks/[symbol]/news`
    - `/stocks/[symbol]/sentiment`
    - `/stocks/[symbol]/technical`
    - `/stocks/[symbol]/report`
    - `/stocks/[symbol]/data-sources`
  - 个股研究页 `/stocks/[symbol]` 已回归 overview，不再包含“专业技术研究”折叠栏。
  - 核心证据卡现在分别链接到对应独立页面。
  - 已验证：Next.js 生产构建通过；TypeScript 检查通过；`/stocks/MSFT`、`/stocks/MSFT/news`、`/stocks/MSFT/sentiment`、`/stocks/MSFT/technical`、`/stocks/MSFT/report`、`/stocks/MSFT/data-sources`、`/stocks/09988/technical` 均 HTTP 200。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已按用户反馈重构“专业技术研究”：
  - `apps/web/components/StockTechnicalPanel.tsx` 不再只是旧技术面收纳版，已重排为“技术决策工作台”。
  - 新阅读顺序：技术结论、行动卡、时间框架、图表证据、价格地图、证据链、历史验证、专业展开。
  - 已从技术研究里移除新闻/情绪/资金/估值的大块内容，避免技术页继续变成能力大杂烩。
  - `apps/web/app/globals.css` 新增 `ta-*` 技术研究样式，跟 V28 左侧工作台和极简 block 风格统一。
  - 已验证：Next.js 生产构建通过；TypeScript 检查通过；`/stocks/MSFT` 和 `/stocks/09988` HTTP 200；页面可见“先定时间框架 / 图表证据 / 价格地图 / 证据链 / 专业展开”等新结构。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成 V28 蓝图对照和产品测试：
  - 新建 `docs/PRODUCT_TEST_V28_BLUEPRINT_REVIEW_2026-05-04.md`。
  - 对照 `docs/PRODUCT_REDESIGN_BLUEPRINT_2026-05-04.md`，确认 V28 已完成左侧导航、顶部控制、首页任务队列、个股 Decision Header、Insight Cards、消息雷达、情绪观察和数据源状态的第一版骨架。
  - 已验证：TypeScript 检查通过、Next.js 生产构建通过、首页/股票池/MSFT 个股页/消息雷达/情绪观察/数据源状态 6 个页面 HTTP 200。
  - 已验证：搜索接口 `MSFT` 返回 Microsoft，搜索接口 `阿里` 返回阿里巴巴港股。
  - 当前主要缺口：独立技术研究页和研究报告页还没有真实页面骨架；“为什么排前面”等深层交互还不够；本轮没有完成真实截图级视觉验收。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已开启 V28 产品重构第一版：
  - 新增 `apps/web/components/AppShell.tsx`。
  - 前端主结构改为左侧纵向导航、顶部全局控制、右侧内容工作区。
  - 顶部新增全局搜索、中文/英文切换、日间/夜间主题切换和数据状态入口。
  - 首页重构为“盘前任务页”，重点展示今日总判断、优先处理队列、消息雷达、情绪观察、数据源状态和重点事件。
  - 个股页重构第一屏，新增 Decision Header、价格条、核心 Insight Cards 和折叠式专业技术研究区。
  - 旧 `StockTechnicalPanel` 暂不删除，作为专业展开层保留。
  - 已验证：Next.js 构建通过、TypeScript 检查通过、首页 HTTP 可见 V28 文案、MSFT 个股页 HTTP 可见核心证据卡和专业展开入口、`/watchlist` HTTP 200。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已继续推进 V28 股票池页：
  - `apps/web/app/watchlist/page.tsx` 重构为“研究对象管理器”。
  - 股票池页新增总览指标、添加标的入口、已关注标的管理说明。
  - `WatchlistManager` 改为 V28 表格式管理体验，支持研究入口、重视程度、关注理由和删除动作。
  - `AppShell` 优化当前个股页面里的技术研究和研究报告锚点跳转。
  - 已验证：TypeScript 检查通过、Next.js 构建通过、`/watchlist` 可见“我正在关注什么 / 添加标的 / 已关注标的”、首页和 MSFT 个股页仍正常。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成 V28.8 任务页拆分：
  - 新增 `apps/web/app/news/page.tsx`，把消息雷达升级为独立“事件处理中心”。
  - 新增 `apps/web/app/sentiment/page.tsx`，把情绪观察升级为独立“市场参与者反应”页面。
  - 新增 `apps/web/app/data-sources/page.tsx`，把数据源状态升级为独立“可信度中心”。
  - `AppShell` 左侧导航改为真实页面入口：`/news`、`/sentiment`、`/data-sources`。
  - 首页的消息雷达、情绪观察、数据源状态改为摘要 + 查看全部入口。
  - 已验证：TypeScript 检查通过、Next.js 构建通过、`/news`、`/sentiment`、`/data-sources`、首页均可访问并出现关键文案。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成产品能力编排层研究：
  - 深度参考 ChartMill 的 NVDA 个股页和 TradingView 的 CVM 个股页。
  - 新建 `docs/PRODUCT_ORCHESTRATION_RESEARCH_2026-05-04.md`。
  - 已补充用户偏好的 UI 方向：左侧纵向导航、右侧内容工作区、中文/英文切换、日间/夜间模式。
  - 新建 `docs/PRODUCT_REDESIGN_BLUEPRINT_2026-05-04.md`，从零重新定义产品结构、UI、交互、字体、主题和内容层级。
  - 核心结论：后续不要继续按“技术、新闻、情绪、社媒、资金流”等能力堆页面，而要按用户任务编排。
  - 建议 V28 以“Decision Header + Insight Card + 任务标签 + 首页任务队列”为主线，把现有能力统一组织成用户可执行的研究路径。
  - 参考来源：ChartMill `https://www.chartmill.com/stock/quote/NVDA/profile`、TradingView `https://www.tradingview.com/symbols/AMEX-CVM/`。
- 已完成 V27：
  - 真实外部社媒探针试跑已接入。
  - Reddit RSS 探针已接入；MSFT 实测成功，解析到 8 条公开讨论样本。
  - 东方财富股吧公开页探针已接入；招商银行单独探针实测成功，解析到 8 条公开讨论样本。
  - 雪球公开入口实测返回 WAF 页面，页面会明确显示失败原因，不伪装成已接入。
  - 个股页新增真实探针结果、社媒试算分、正/负/中数量和公开样本展示。
  - 首页组合探针概览新增真实成功数和社媒试算数。
  - 缓存版本升级为 `research-v27-social-live-probe`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、招商银行社媒探针单测、preflight API、首页 HTML、MSFT 个股页 HTML、首页 HTTP、MSFT 个股页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`；前端使用生产预览启动。
- 已完成 V26 收口：
  - V26.3：首页新增组合级“V26 社媒探针”，展示可外部验证、不可入分、本地阻塞数量和下一批验证股票。
  - V26.4：个股页新增“不可入分”门槛，列出真实社媒数据进入情绪分前必须满足的条件。
  - V26.5：个股页新增下一步外部验证动作，例如 MSFT 显示用 Reddit 验证公开讨论入口、时间戳和讨论量。
  - 缓存版本升级为 `research-v26-final-social-probe-gate`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT 强制刷新 API、preflight API、首页 HTML、MSFT 个股页 HTML、首页 HTTP、MSFT 个股页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`；前端使用生产预览启动。
- 已完成 V26.2：
  - 社媒探针新增本地预检查结果。
  - 预检查展示市场匹配、代码可用、外部抓取是否运行。
  - 当前不访问外部社媒，不生成情绪分；MSFT 显示“可进入外部验证”，同时明确“外部抓取：未运行”。
  - 缓存版本升级为 `research-v26-2-social-probe-readiness`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT 强制刷新 API、MSFT 个股页 HTML、首页 HTTP、MSFT 个股页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`；前端使用生产预览启动。
- 已完成 V25.5 / V26.1：
  - 个股页新增“该股票下一优先源”，例如 MSFT 优先 Reddit。
  - 新增 `social_sources.py`，把 Reddit、雪球、东方财富股吧沉淀为真实社媒源探针契约。
  - 每个源明确接入方式、要采集的字段、验证清单和阻塞风险。
  - 探针层只验证数据可得性和字段质量，验证通过前不参与新闻分、情绪分或行动提示。
  - 缓存版本升级为 `research-v26-1-social-source-probe`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT 强制刷新 API、preflight API、首页 HTML、MSFT 个股页 HTML、首页 HTTP、MSFT 个股页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`；前端使用生产预览启动。
- 已完成 V25.4：
  - 首页“情绪源状态”新增“建议下一接入源”。
  - preflight 新增 `sentiment_source_overview.next_source`，按高优先股票覆盖数和总覆盖数选择下一源。
  - 当前股票池建议先验证雪球，并说明覆盖数量、选择理由和下一步动作。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页 HTML、首页 HTTP、MSFT 个股页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`；前端使用生产预览启动。
- 已完成 V25.3：
  - 情绪源新增市场相关优先级和下一步接入动作。
  - 美股优先 Reddit，A股优先东方财富股吧，A股/港股优先雪球；所有源仍明确标注未接入。
  - 首页情绪源状态会显示每个源的高优先标的数量和下一步验证动作。
  - 缓存版本升级为 `research-v25-3-sentiment-source-priority`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、preflight API、首页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成 V25.2：
  - 首页新增“情绪源状态”。
  - preflight 新增 `sentiment_source_overview`，汇总新闻代理覆盖数量、真实社媒源数量和待接入源数量。
  - 首页会显示 Reddit、雪球、东方财富股吧的接入状态，明确当前情绪层仍主要依赖新闻代理。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.8 收口，并进入 V25.1：
  - V24 收口：新闻/情绪工作流已覆盖个股页、首页消息雷达、首页组合情绪概览。
  - V25.1 新增独立 `sentiment_intelligence` 情绪信号层。
  - 情绪信号层明确区分新闻热度代理和真实社媒源状态，不把新闻热度伪装成社媒情绪。
  - 个股页新增“情绪信号层”，展示新闻代理、新闻分、热度、可信度，以及 Reddit / 雪球 / 东方财富股吧的接入状态。
  - 缓存版本升级为 `research-v25-1-sentiment-intelligence`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、MSFT 个股页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.7：
  - 首页“情绪面概览”新增风险观察、机会观察、复核等待三类分组。
  - `sentiment_overview` 新增 `action_groups`，按操作提示把股票池分组，并返回数量和代表标的。
  - 首页能先分清风险、机会和需要复核的线索，再进入消息面雷达看细节。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.6：
  - 首页“情绪面概览”新增组合级处理重心。
  - `sentiment_overview` 新增 `action_focus`、`action_summary`、`action_rows`。
  - 首页会显示当前处理重心，以及每类消息处理动作覆盖几只标的和代表股票。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.5：
  - 首页“消息面雷达”接入 `action_priority`，直接显示消息面操作提示。
  - `news_alerts` 新增 `action_label`、`action_rank`、`action_note`、`confidence_label`、`coverage_label`。
  - 首页消息雷达排序纳入操作提示优先级，优先展示更需要处理的消息。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.4：
  - `event_digest` 新增 `action_priority`，综合情绪风险、可信度、热度变化和来源覆盖。
  - 个股页“新闻/情绪”新增“消息面操作提示”，把消息面归纳为提高观察、风险观察、复核原文、等待催化或暂不参与判断。
  - 该提示不输出买卖指令，只说明消息面现在如何参与研究判断。
  - 缓存版本升级为 `research-v24-4-news-action-priority`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、MSFT 个股页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.3：
  - `event_digest` 新增 `source_coverage`，解释最终入选新闻覆盖了哪些来源层次。
  - 来源覆盖会区分市场新闻、行业媒体、官方文件和增强源，并显示当前缺口。
  - 个股页“新闻/情绪”新增“来源覆盖”卡片，用户可以判断这批消息是覆盖较全、覆盖中等还是覆盖偏窄。
  - 缓存版本升级为 `research-v24-3-source-coverage`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、MSFT 个股页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.2：
  - `event_digest` 新增 `confidence_profile`，解释情绪结论可信度，考虑样本数、来源多样性、行业/官方来源、事件集中度和平均相关度。
  - `event_digest` 新增 `heat_change`，用 24 小时内新闻数量和前一日新闻数量判断升温、降温或平稳。
  - 个股页“新闻/情绪”新增“情绪可信度”和“热度变化”两张卡片。
  - 缓存版本升级为 `research-v24-2-sentiment-confidence`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、MSFT 个股页 HTML、首页 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24.1：
  - 新闻筛选从“标题完全相同才去重”升级为“同类事件相似标题合并”。
  - 个股页新闻收敛到最多 5 条精选，优先覆盖不同事件类型。
  - 每条新闻新增 `selected_reason`，前端展示“为什么入选”；同类转载会通过 `duplicate_count` 标注合并数量。
  - 缓存版本升级为 `research-v24-1b-news-selection-reason`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、首页/个股页 HTTP、服务状态。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V24：
  - 个股详情页“新闻/情绪”新增“情绪风险”块，展示风险等级、原因、行动提示和驱动因素。
  - `event_digest` 新增 `risk_profile`，根据消息热度、倾向、正负面数量、来源多样性和主事件生成。
  - 缓存版本升级为 `research-v24-news-risk-profile`，旧缓存会迁移补齐新字段。
  - 首页预检改为优先读取本地缓存，避免版本升级后同步刷新多只股票导致首页等待过久。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT API、首页 API、首页/个股页 HTTP、页面 HTML 内容检查。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V22 收口，并进入 V23 第一轮：
  - 首页“今日新闻”升级为“重点事件”，每条展示关联股票、事件类型、观察标签、新闻分和相关度。
  - 盘前摘要 `news` 后端统一过滤 `news-router` 占位新闻，不再让内部占位内容进入首页事件流。
  - V23 新增组合级 `sentiment_overview`，首页新增“情绪面概览”，直接显示股票池整体情绪、偏正/偏负/中性数量、高热度数量和负面风险标的。
  - V23 已补充风险提示：`news_alerts` 增加 `risk_label`、`risk_note`、`risk_rank`，首页“消息面雷达”和“情绪面概览”直接显示风险等级、原因和下一步观察。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页/泡泡玛特详情页 HTTP、浏览器页面复验。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V22 第一轮：
  - `news_intelligence` 新增 `event_digest`，把新闻列表总结为消息热度、主事件、整体倾向、正/负/中数量、重点事件和行动含义。
  - 证据矩阵里的“消息面”改为读取事件摘要，不再只显示正负面条数。
  - 个股详情页“新闻/情绪”新增事件解读卡片，用户可以直接看到“最近 48 小时这批新闻怎么用”。
  - 缓存版本升级为 `research-v22-news-event-digest`。
  - 修复缓存升级后的页面稳定性：普通访问先迁移旧缓存并补齐事件摘要，避免同步重算行情和新闻导致详情页超时；强制刷新仍会重新拉取真实数据。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、`09992` 新闻 API、首页/阿里/泡泡玛特页面 HTTP、浏览器页面复验。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V22 第二轮：
  - `event_digest` 新增 `sentiment_bars`、`source_mix`、`source_rows`、`reliability_note`。
  - 个股详情页事件解读卡片新增“情绪分布”和“来源结构”。
  - 新闻分现在可以解释为：哪些情绪占比、哪些来源类别参与、来源可靠性如何。
  - 缓存版本升级为 `research-v22b-news-source-structure`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、`09992` API、首页/泡泡玛特页面 HTTP、浏览器页面复验。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V22 第三轮：
  - `event_digest` 新增 `watch_items`，根据主事件、情绪、热度和来源数量生成“下一步观察”。
  - 个股详情页事件解读卡片新增“下一步观察”，把消息面转成后续确认项。
  - 缓存版本升级为 `research-v22c-news-watch-items`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、`09992` API、首页/泡泡玛特页面 HTTP、浏览器页面复验。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V22 第四轮：
  - 盘前摘要 API 新增 `news_alerts`，按消息热度、新闻分和新闻数量排序。
  - 首页新增“消息面雷达”，展示股票池中消息正在升温的标的、主事件、新闻分和下一步观察。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、preflight API、首页/泡泡玛特页面 HTTP、浏览器页面复验。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成新闻与情绪面 V21.5：
  - 新增泛行业资讯源层：美股接 TechCrunch / The Verge / VentureBeat / Wired；A股和港股接 36氪 / 虎嗅 / 钛媒体 / 晚点 / 机器之心。
  - 新闻源状态新增分类：市场新闻、行业媒体、官方文件、增强源。
  - 个股详情页新闻列表显示来源分类；来源说明会标注行业媒体层是否参与。
  - 新闻事件类型扩展为技术/产品、战略/合作、竞争格局、融资/投资等。
  - 重点公司别名库扩展：阿里云/Qwen、腾讯云/微信/混元、泡泡玛特 Labubu、微软 Azure/Copilot、亚马逊 AWS、英伟达 Blackwell/CUDA 等。
  - 修复“阿里·某某”这类人名片段误判成阿里巴巴新闻的问题。
  - 首页增加预检超时保护：全股票池首次刷新太慢时，首页先显示股票池和空状态，不再 500。
  - 缓存版本升级为 `research-v21-industry-news`。
  - 已验证：Python 编译、TypeScript 检查、Next.js 生产构建、首页 HTTP、阿里详情页 HTTP、MSFT 新闻抽样。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完成 V21.5 审核复测：
  - 修复 `source_status.selected_count` 统计口径：现在只统计最终展示的 8 条新闻。
  - 修复覆盖说明：只有最终展示新闻里真的有行业媒体时，才写“行业媒体层已参与”。
  - 缓存版本升级为 `research-v21a-news-selected-counts`，避免旧快照继续沿用旧统计。
  - 首页盘前预检等待从 12 秒降到 7 秒，避免浏览器打开首页时因全股票池刷新过慢而超时。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、首页 HTTP、泡泡玛特详情页 HTTP、浏览器页面复验。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已处理 `docs/REVIEW_2026-05-02-R21.md`：
  - 修复 R21-BUG-1：`signals[*]` 现在全部补齐 `key` 和 `label`，前端或后续报告可以稳定按字段识别信号。
  - 顺手产品化 R21-OBS：历史验证分布如果高度集中在负收益区或正收益尾部，返回 `distribution_warning`，前端显示“分布偏斜”提示。
  - 缓存版本升级为 `research-v20-r21-signal-labels`。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/09988/600036 API 抽样、首页/MSFT 页面 HTTP。
- 已完成下一阶段产品方向 v19，把 `PRODUCT_PLAN_NEXT_DIRECTION_2026-05-02.md` 剩余项目一次做完：
  - Regime 区新增短线节奏说明，解释当前价相对 60 分钟 VPOC / Value Area 的位置。
  - 关键点位新增 `60分钟入场确认` 折叠区，说明 60min 收盘确认、量能确认、回踩确认。
  - 历史验证新增 6 桶收益分布，不再只显示均值和中位数。
  - K 线图新增 `日线 · 近120日 / 60分钟 · 近5日` 切换；60分钟图显示 MA20、VPOC、Value Area。
  - 新增 60 分钟成交量断层检测，关键点位区和 60分钟图会提示断层区间。
  - 缓存版本升级为 `research-v19-final-decision-tools`。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/09988/600036 API 抽样、首页/MSFT/09988/600036 页面 HTTP。
- 已完成下一阶段产品方向 v18：
  - 证据矩阵新增“短线节奏”行，读数来自当前价、60 分钟 VPOC、Value Area 和 60min RSI。
  - 证据矩阵新增“消息面”行，读数来自近 48 小时新闻分和正/负面条数。
  - 近端压力/支撑列表新增 ATR 倍数，让用户知道点位距离是“日内可触及”还是“远期结构位”。
  - 缓存版本升级为 `research-v18-decision-matrix`。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/09988/600036 API 抽样、首页 HTTP、MSFT 页面 HTTP。
- 已完成下一阶段产品方向 v17：
  - 关键点位新增风险收益比 R/R：返回盈利空间、风险空间、R/R、所需胜率和结论。
  - K 线图短线视角新增 60 分钟 VPOC 虚线、VAH/VAL 价格线和 Value Area 浅色带。
  - 缓存版本升级为 `research-v17-decision-quality`。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/09988/600036 API 抽样、首页 HTTP、MSFT 页面 HTTP。
- 已处理 `docs/REVIEW_2026-05-02-R20.md`：
  - 修复 `rsi14_60m` 可能为 `null` 的问题：60 分钟 RSI 现在显式使用 float 序列，并增加简单 RSI 兜底计算。
  - 修复 `levels.trigger_source` 为空的问题：短线/波段/中长线 levels 现在返回 `trigger_source` 和 `invalidation_source`。
  - 缓存版本升级为 `research-v16-r20-rsi-source`，避免旧快照继续显示空 RSI。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/09988/600036 API 抽样、首页 HTTP、MSFT 页面 HTTP。
- 已完成技术分析升级路线图 Phase 3：
  - 新增 K 线形态置信度评分，综合位置、成交量、动量和 AVWAP 位置，每个形态返回置信度、标签和原因。
  - 新增 Anchored VWAP：52 周低点成本线、最近高点套牢线，并返回锚点日期和当前偏离比例。
  - K 线图新增低点 AVWAP 和高点 AVWAP 两条线，图例与实际绘制同步。
  - 新增跨周期冲突检测：日线 RSI 与 60 分钟 RSI 背离、低于 60 分钟 VPOC、短周期过冷等情况会进入冲突提示。
  - 技术页新增 AVWAP 成本线区块、K 线置信度展示和 AVWAP 核心指标。
  - 缓存版本升级为 `research-v15-confidence-avwap`。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/09988/600036 API 抽样、首页 HTTP、MSFT 页面 HTTP、浏览器 DOM 核验。
- 已把 60 分钟数据从 Yahoo 单源升级为 `IntradayRouter` 多源路由：
  - A股：BaoStock → AkShare → Yahoo。
  - 港股：AkShare → Yahoo。
  - 美股：Yahoo → AkShare。
  - 新增 `intraday_status.route`，用于暴露实际尝试过的数据源顺序。
  - A股 `600036` 实测走 `baostock-60m:600036`，返回 228 根 60 分钟 K 线。
  - 港股 `09988` 实测 AkShare 因 ProxyError 失败后回退 Yahoo，返回 413 根 60 分钟 K 线。
  - 美股 `MSFT` 实测走 `yahoo-chart-60m:MSFT`，返回 421 根 60 分钟 K 线。
  - 缓存版本升级为 `research-v14-intraday-router`。
  - 已追加 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、600036/09988/MSFT API、首页 HTTP、招商银行页面 HTTP。
- 已完成技术分析升级路线图 Phase 2：
  - 新增板块相对强弱：`feature_set.market` 返回 `sector`、`sector_symbol`、`sector_return_3m`、`sector_rs_3m`。
  - 新增 60 分钟行情入口：使用 Yahoo Chart 1h 免费数据；失败时写入 `intraday_status.flags`，不阻断主流程。
  - 新增 60 分钟特征：近 5 日 swing high/low、VPOC、价值区间、60min RSI。
  - 短线关键点位已可优先读取 60min 局部高低点和 VPOC。
  - 新增财报事件上下文入口：美股尝试 Yahoo Finance calendarEvents，拿不到则为空，不伪造。
  - `FeatureEngineer.transform()` 已拆为兼容入口和 `transform_daily()`；`BacktestValidator` 显式调用 `transform_daily()`，不受 60 分钟数据影响。
  - 港股 Yahoo 代码格式修正为去前导 0，例如 `09988 -> 9988.HK`，阿里 60 分钟数据已恢复。
  - 缓存版本升级为 `research-v13-sector-rs-60min`。
  - 已新建 `docs/FIX_LOG_2026-05-02.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、MSFT/招商银行/阿里巴巴 API、首页 HTTP、招商银行页面 HTTP。
- 已开始执行技术分析升级路线图 Phase 1：
  - S/R 点位从固定 MA/55 日高低点升级为 swing high/low + MA/VWAP/MVWAP + 52 周结构位。
  - 短线、波段、中长线现在分别返回自己的执行位、失效位和近端压力/支撑点位栈。
  - 新增 OBV 背离、RSI 背离、ADX 斜率；低 ADX 但斜率抬升时不再简单归为纯震荡。
  - 技术页“关键点位”新增近端压力/近端支撑小地图。
  - 核心指标摘要移除 CCI 主展示，改为 ADX 斜率、RSI 背离、OBV 背离、ATR、MFI、CMF。
  - 缓存版本升级为 `research-v12-ta-phase1`。
  - 已追加 `docs/FIX_LOG_2026-05-01.md` 的 Phase 1 记录。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、`09988`/`MSFT` API、`/stocks/09988` HTTP、首页 HTTP。
- 已处理 `docs/REVIEW_2026-05-01-R19.md`：
  - 修复首页雷达判断顺序，接近失效位优先级高于接近触发位；招商银行已从 `near_trigger` 修正为 `near_invalidation`。
  - 港股通资金面代码匹配兼容 `00700/0700/700`；当前 AkShare 源仍未返回腾讯命中数据，页面保持“暂无数据”。
  - 美股 ROE 统一按 yfinance 小数口径转成百分比，避免 Apple 这类高 ROE 被误标为偏低。
  - 美股股息率优先用 `dividendRate / currentPrice * 100`，避免把每股分红额误当收益率。
  - 已追加 `docs/FIX_LOG_2026-05-01.md` 的 R19 记录。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、首页 HTTP、preflight API。
- 用户反馈 `http://127.0.0.1:4173` 打不开，已排查为前端服务停止，后端 `4174` 正常。
  - 已重新启动前端服务，当前产品页 `http://127.0.0.1:4173` 可访问。
  - 验证通过：首页 HTTP 200、`/stocks/BRK-B` HTTP 200、Research API HTTP 200。
- 已处理 `docs/REVIEW_2026-04-30-R18.md`，并顺手处理用户追加的两个问题：
  - 首页新增「关键点位监控」，后端 `build_preflight()` 返回 `level_alerts`，数据来自现有 snapshot，不新增网络请求。
  - 个股页新增「资金面」section：A股主力净流向、港股港股通持股、美股机构持仓；不可用时显示数据不足。
  - 个股页新增「估值参考」section：A股/港股优先 AkShare，美股 Yahoo Finance；当前环境下 `600036` 估值源 ProxyError，未伪造数据。
  - 资金面偏空与技术面未走坏时，会进入冲突提示。
  - 新增股票池后调用 `router.refresh()`，避免必须手动刷新页面才看到新增股票。
  - AXTI 历史验证保留真实 60 日均值 211.2%，但新增近似独立样本和极端行情提示；当前 AXTI 波段样本 20 个折算独立样本约 1 个，不能按稳定胜率理解。
  - 已追加 `docs/FIX_LOG_2026-05-01.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、首页 HTTP、`600036` API、`AXTI` API。
- 已修复全量代码审查提出的 7 个问题：
  - 停止使用模拟行情生成技术结论；真实行情不可用时返回“数据不足”结构。
  - 历史验证的 `benchmark_edge` 改为按日期对齐基准行情。
  - 单股 snapshot / technical 接口增加失败保护，异常时返回完整降级结构。
  - 快照缓存改为临时文件 + 原子替换，损坏缓存会自动失效。
  - 股票池更新/删除会检查响应状态，失败时显示错误。
  - 搜索联想会丢弃过期响应，避免旧结果覆盖新输入。
  - K 线图只初始化一次，切换时间框架只更新价格线，不重建整张图。
  - 已新建 `docs/FIX_LOG_2026-05-01.md`。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、首页 HTTP、BRK-B 详情页 HTTP、BRK-B API、无效代码数据不足结构。
- 已按用户要求结合 `CONTEXT.md`、`progress.md`、`findings.md`、产品路线图和近期审查文档，对当前 App 代码做全量代码审查。
  - 覆盖范围：`apps/web` Next.js 前端、`services/research` Python 研究服务、股票池搜索/保存、行情路由、技术指标、历史验证、新闻聚合、缓存与代理接口。
  - 审查方式：只读审查，不修改业务代码。
  - 验证结果：Python 编译通过、TypeScript 检查通过、Next.js 生产构建通过，首页、`BRK-B` 页面和 Research API 均返回 200。
  - 主要发现：模拟行情仍会继续生成技术结论、历史验证 benchmark 按数组位置对齐、单股详情页缺少失败保护、快照缓存非原子写入、股票池更新删除不检查失败、搜索存在过期响应覆盖风险、图表切换会重建整张图。
- 已修复技术页 tooltip、历史验证、指标解释和阿里新闻：
  - `量价 & 市场结构确认` 的感叹号解释框改为页面顶层浮层，避免被表格或窗口裁切。
  - 历史验证新增感叹号解释，说明均值/中位/胜率/MAE/vs 基准是什么。
  - 历史验证从完全同类状态扩展为“完全同类 + 相近状态”的滚动样本，并标注样本可能重叠，不等于独立交易次数。
  - 阿里波段 60 日样本从 4 扩到 43；均值 10.83%，中位 3.34%，MAE -9.27%，vs 基准 5.08%。
  - CCI/MFI 文案从“中性”改为“动量在常态区间 / 资金流在常态区间”。
  - KDJ-J 补充感叹号和解释。
  - 阿里新闻补充阿里云、Qwen、菜鸟、高德等别名，提高中文短别名权重；近 48 小时已入选 3 条新闻。
  - 验证通过：Python 编译、TypeScript 检查、Next.js 生产构建、`09988` 和 `BRK-B` 页面 HTTP。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已按用户要求模拟 10 个用户从股票池页面录入全新股票：
  - 覆盖 A股代码、A股中文名、港股 5 位代码、港股 4 位简写、美股 ticker、特殊美股代码 `BRK.B`。
  - 发现并修复搜索旧结果可误点的问题：新输入开始匹配时立即清空旧候选。
  - 发现并修复加入后跳转不稳定的问题：加入成功后直接进入个股详情页，不再先刷新股票池页。
  - 发现并修复港股 5 位代码识别问题：Yahoo 搜索使用去前导 0 的 `.HK` 代码，例如 `9888.HK`，返回后规范为 `09888`。
  - 已让已有 `待识别` 股票在再次搜索加入时自动补正真实名称；`09888` 和 `02318` 已补正。
  - 验证通过：Python 编译、TypeScript 检查、`09888/02318/1024` 搜索、股票池页面 HTTP。
  - `next build` 当前因本机 SWC 二进制签名异常失败，属于环境问题；前端 `4173` 和 Research API `4174` 仍已启动。
- 已消化 `docs/NEWS_INTELLIGENCE_SPEC_2026-04-30.md`，并调研 Finnhub 免注册替代方案：
  - 结论：没有单一 no-key 新闻 API 能完整替代 Finnhub。
  - 建议改为 no-key 多源新闻路由：A/HK 以 AkShare + RSSHub/华尔街见闻/财联社路线为主，美股以 GDELT + Yahoo Finance News + SEC EDGAR 为主，Google News RSS 只做兜底。
  - `open-market-data` skill 可提供 SEC/行情/财报事件源，但不是多媒体新闻聚合器。
  - 已补充 Marketaux、Alpha Vantage News、Finviz、RSSbrew 对比：Marketaux/Alpha Vantage 都需要 key；Finviz 适合作为美股辅助；RSSbrew 是自托管聚合工具，不是新闻源。
  - 深度调研后的推荐组合：默认启用 AkShare + RSSHub + GDELT + SEC EDGAR + Yahoo Finance News + Google News RSS；Marketaux / Alpha Vantage / Finviz 只做用户配置后的可选增强。
  - 已落地 `services/research/research_engine/news/` 多源新闻路由；`pipeline.py` 返回 `news_intelligence` 和兼容的 `news`。
  - 用户已提供 Marketaux 和 Alpha Vantage key，但产品原则保持不变：两者只做增强源，不作为主源；真实 key 只通过环境变量启用，不写入仓库。
  - 已新增 `.env.example`，`.gitignore` 已忽略 `.env` 和 `.env.*`。
  - 已验证：Python 编译通过；Next.js 构建通过；MSFT 主源足够时不调用增强源。
  - 用户反馈首页看不到新闻分后，已把首页“今日新闻”追加事件类型、情绪、新闻分、相关度，并重启前端/后端服务。
  - 当前页面：`http://127.0.0.1:4173/` 已显示新闻分；`http://127.0.0.1:4173/stocks/00992` 已显示新闻智能汇总。
  - 用户指出港股缺财联社/华尔街见闻、新闻分常为 0、新闻窗口太长后，已改为近 48 小时硬过滤，新增直接华尔街见闻源，财联社快讯可从标题解析日期，并扩展繁体/快讯情绪词。
  - 验证：招商银行 `600036` 近 48 小时新闻分为 `0.356`；阿里巴巴 `09988` 主源可用但近 48 小时无高相关个股新闻。
  - 用户要求从前端真实路径测试“加入股票池 -> 看新闻源/过滤/相关度”，已加入并检查美团 `03690`、小米 `01810`、中国平安 `601318`、JPM、LLY。
  - 已修复：短英文别名导致港股大盘新闻误入选；JPM 作为投行给其他公司评级时误入选；A股中文名搜索目录外股票失败；新美股 SEC CIK 覆盖不足。
  - 当前验证：`应流股份` / `紫金矿业` 可直接联想到真实 A股代码；`01810` 只保留小米资金动作新闻；`JPM` 不再入选 Celestica/TransUnion 这类被 JPM 评级的假相关新闻。
  - 已处理 `docs/REVIEW_2026-04-30-R17.md`：过滤首页/详情页 `news-router` 占位新闻，搜索结果按“我的股票池 / 其他匹配”分组，headline 去掉重复 Regime 前缀，新闻情绪补 `tops/slides` 等词，高管变动识别为公司治理，目标价/评级调整识别为分析师评级，触发位统一 2 位小数。
  - R17 缓存版本升级为 `research-v8-r17-cleanup`；验证通过：Python 编译、TypeScript 检查、Next.js build、首页/股票池/详情页 HTTP 检查。
  - 已新建 `docs/NEWS_SOURCE_RESEARCH_2026-04-30.md`。
- 已按用户要求参考 Notion block 风格重构 UI 和交互：
  - 全局从深色终端风格改为浅色极简 block 风格。
  - 使用浅灰背景、白色内容块、细边框、8px 内圆角、克制色彩。
  - 搜索结果改为浮层，按钮/链接/列表/表格行/Tab/details/tooltip 增加轻量 hover 和 focus 反馈。
  - K 线图同步改为浅色画布和浅色网格。
  - 已验证：Python 编译通过；Next.js 生产构建通过；首页、联想详情页、股票池页面 HTTP 访问通过。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已处理 `docs/REVIEW_2026-04-30-R15.md`：
  - Regime 英雄区删除重复的 `next_step` 和 `invalid_if`，行动条件只保留在“关键点位”卡片。
  - `pipeline.py` 新增 `clean_news_title()`，清理 Google News RSS 标题末尾的 ` - 来源名` 后缀。
  - 已验证：Python 编译通过；Next.js 生产构建通过；`00992` 页面返回 200；`00992` API 返回清理后的新闻标题。
  - 已追加 `docs/FIX_LOG_2026-04-30.md` R15 修复记录。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已处理 `docs/REVIEW_2026-04-30-R14.md`：
  - 删除技术页重复的 `decision-box`。
  - 删除「指标关系解读」bullet section，只保留结构化冲突卡片。
  - 证据矩阵从 4 列改为 3 列：证据 / 当前读数 / 方向；“怎么用”进入 hover。
  - 冲突卡片默认显示前 2 条，其余折叠到“更多解读”。
  - 历史验证改为一行紧凑展示。
  - 新闻免责声明上移到标题旁，每条新闻不再重复显示。
  - 底部指标卡片删除 RSI、ADX、量比、相对强弱，保留 CCI、ATR、MFI、CMF、KDJ-J、布林带宽度。
  - 已验证：Python 编译通过；Next.js 生产构建通过；`00992` 页面返回 200；`00992` API 返回 `research-v6-evidence-matrix`。
  - 已追加 `docs/FIX_LOG_2026-04-30.md` R14 修复记录。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已按 `docs/PRODUCT_ROADMAP_2026-04.md` 推进代码：
  - 新增 `services/research/research_engine/indicator_metadata.py`，覆盖核心指标的用途、正常区间、失效场景和行动影响。
  - 新增 `services/research/research_engine/conflict_rules.py`，输出结构化冲突解释。
  - `signals.py` 信号升级为证据矩阵字段：`current_reading`、`direction`、`indicator_keys`、`decision_use`。
  - `pipeline.py` 返回 `signal_summary`、`conflict_notes`、`indicator_metadata`，缓存版本升级为 `research-v6-evidence-matrix`。
  - 修复 `/snapshot?force=1` 未真正强制刷新的问题，`/technical?force=1` 同步支持。
  - 前端技术页把“量价 & 市场结构确认”改为证据矩阵，并给核心指标加 hover 解释。
  - 已验证：Python 编译通过；Next.js 生产构建通过；`09988` 和 `MSFT` API 均返回新结构。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已完整拆解 `tauricresearch/tradingagents`：
  - 本地源码版本：`7c37249f808f9c169ad2198dc384166e7ca7adf9`。
  - 许可证：Apache-2.0。
  - 已覆盖 analyst、researcher、trader、risk、portfolio manager、memory、reflection、checkpoint、CLI 和测试模块。
  - 结论：TradingAgents 最值得参考的是“分析师报告 -> 多空辩论 -> 交易提案 -> 风险审查 -> 投资组合结论 -> 事后复盘”的研究流水线。
  - 对本项目最有价值的吸收方向：结构化研究报告、支持/反对证据、机会/均衡/风险三视角、研究记忆、20/60/120 日事后复盘。
  - 不建议照搬完整 LangGraph 多智能体链路到日常技术面页面；更适合深度研究报告和组合复盘。
  - 已新建 `docs/TRADINGAGENTS_FULL_ARCHITECTURE_RESEARCH_2026-04-30.md`。
- 已研究 `tauricresearch/tradingagents` technical analyst 模块：
  - 仓库临时拉取到 `/private/tmp/tradingagents-src`。
  - 源码中 technical analyst 实际对应 `Market Analyst`。
  - 核心文件：`market_analyst.py`、`technical_indicators_tools.py`、`y_finance.py`、`stockstats_utils.py`、`interface.py`、`graph/setup.py`。
  - 结论：TradingAgents 的指标覆盖不如本项目当前指标层全面；最有价值的是“指标互补不冗余”、每个指标有 Usage/Tips、报告最后用表格总结。
  - 已新建 `docs/TRADINGAGENTS_TECHNICAL_ANALYST_RESEARCH_2026-04-30.md`。
  - 建议后续落地：新增指标说明字典、证据矩阵、冲突解释器；LLM 只做结构化结果改写，不接管判断。
- 已处理 `docs/REVIEW_2026-04-30-R13.md`：
  - 信号描述从问句改为可核验陈述，补充当前价、MA50、ADX、量比、MACD、相对基准等具体数值。
  - 技术页新增信号汇总结论：X 通过 / Y 观察 / Z 未通过，并给一句用户可理解的解读。
  - 新增 `interpretation` 解释框架：行动结论、观察条件、指标冲突说明、决策链。
  - 已主动解释 ADX 强但 Regime 仍为区间震荡的冲突。
  - K 线形态按最新优先展示；看涨和看跌形态同时出现时显示“近期多空形态交替，方向分歧”。
  - 历史验证样本小于 15 时显示“样本偏少”，并提示置信度有限。
  - ATR 摘要改为可用解释：占当前价比例和 1.5 倍 ATR 参考距离。
  - RSI > 70 提示改为“接近超买，关注能否维持”。
  - 新闻源过滤 90 天以前旧新闻；无近期新闻时显示“暂无 90 天内相关新闻”。
  - 缓存版本升级为 `research-v5-friendly-framework`。
  - 已用联想集团 `00992` 验证：页面显示指标关系解读、信号汇总、多空分歧提示、样本偏少提示，且不再出现 2022 旧新闻。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已处理 `docs/REVIEW_2026-04-30-R12.md`：
  - 价格摘要从多卡片纵向堆叠改为紧凑横排。
  - 多周期共振增加颜色方向和图例：`↑ 偏强 · → 震荡 · ↓ 偏弱`。
  - 「当前 Regime」已改为「当前市场状态」。
  - `BacktestValidator` 已实装，不再显示空壳占位。
  - 历史验证现在用历史 K 线滚动重算同类市场状态，并统计 20/60/120 日样本量、平均前向收益、中位数收益、胜率、最大不利波动中位数和相对基准优势。
  - 缓存版本升级为 `research-v4-backtest`。
  - `09988` 波段验证已返回真实统计：样本 4 次，60 日平均前向收益 31.77%，最大不利波动中位数 -7.34%。
  - 已更新 `docs/FIX_LOG_2026-04-30.md` 的 R12 修复记录。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已处理 `docs/REVIEW_2026-04-30-R11.md`：
  - 个股详情页第一屏新增价格摘要：当前收盘价、当日涨跌、52 周高低、成交量、最新日期。
  - 首页、股票池、个股详情页英文 eyebrow 已改为中文。
  - 侧边栏股票池导航不再只显示前三只，改为显示全部标的并支持滚动。
  - 技术页“价格图”已改为“K 线图”。
  - “指标与特征展开”前新增核心指标摘要：RSI、ADX、CCI、量比、相对强弱、ATR。
  - 新增“近期 K 线形态”板块，使用 `pandas-ta-classic` + `TA-Lib` 扫描最近 5 根 K 线；无形态时明确显示“近期无典型形态”。
  - 新增多周期共振摘要。
  - BaoStock 搜索和行情查询已移除锁内 `sleep` 重试，单次失败直接暴露。
  - 删除 `features.py` 中被 pandas-ta 替代的手写指标死代码。
  - 已更新 `docs/FIX_LOG_2026-04-30.md` 的 R11 修复记录。
  - 当前服务：产品 `http://127.0.0.1:4173`，Research API `http://127.0.0.1:4174`。
- 已为产品审查组生成产品形态截图，保存于 `docs/screenshots/`：
  - `01-home-workspace-desktop-visible.png`
  - `02-watchlist-search-suggest-desktop-visible.png`
  - `03-stock-detail-desktop-visible.png`
  - 另保留窄屏完整长图作为辅助。
  - `docs/screenshots/README.md` 说明每张图的页面和审查重点。
  - 为支持真实搜索状态截图，`/watchlist` 新增 `?q=` 初始搜索参数。
- 已处理 `docs/REVIEW_2026-04-30-R10.md`：
  - BaoStock 锁已提升为 `services/research/research_engine/providers/lock.py`，搜索和行情查询共用同一把锁。
  - 搜索框点击外部会关闭下拉。
  - 添加股票后调用 `router.refresh()`，返回股票池后能正确显示“已在股票池”。
  - 小写 ticker 如 `crm` 只返回精确匹配，不再混入 CRML/CRMD 等噪音。
  - 已安装并接入 `pandas-ta-classic`，指标层实际使用标准库计算 EMA、RSI、MACD、ADX/DMI、CCI、ATR、布林带宽度。
  - 已新增 `cache_schema_version = research-v2-pandas-ta`，指标引擎升级后旧缓存自动失效。
  - 已验证 `601899` 快照使用 `FinRL-style FeatureEngineer + pandas-ta-classic`。
- 已处理 `docs/REVIEW_2026-04-30-R9.md`：
  - BaoStock Provider 已加进程级锁，个股和基准查询共用同一把锁。
  - 已隐藏 BaoStock 的 `login success/logout success` 终端输出。
  - 目录外股票详情页会读取股票池保存名称，避免 `CRM` 详情页只显示代码。
  - 股票池搜索结果会识别已有标的，显示“已在股票池”，重复加入不覆盖原关注理由。
  - 已验证 `CRM` 加入后详情页名称为 `Salesforce, Inc.`。
  - 已追加 `docs/FIX_LOG_2026-04-30.md` R9 修复记录。
- 已完成股票池添加体验专项：
  - 模拟 20 个用户输入场景。
  - 搜索框已改成实时联想，下方自动出现股票名称和代码。
  - 支持中文未输完、代码未输完、拼音首字母、美股小写、A 股后缀、港股后缀。
  - `603308` 可通过 BaoStock 识别为应流股份，`crm` 可通过 Yahoo Search 识别为 Salesforce。
  - 无效中文、7 位数字、`HSI` 这类指数不再生成垃圾候选。
  - 重复加入不再覆盖原关注理由。
  - 已追加 `docs/FIX_LOG_2026-04-30.md` 股票池添加体验专项。
- 已处理 `docs/REVIEW_2026-04-30-R8.md`：
  - 修复股票池无法添加目录外新股票的问题。
  - 搜索不到内置目录时，会按代码生成候选项：6 位数字为 A 股、5 位数字为港股、字母为美股。
  - 已新增 BaoStock Provider，A 股路由调整为 AkShare → BaoStock → Yahoo。
  - 已修复 K 线图图例颜色、X 轴日期显示、技术页新闻外链 `rel`。
  - 已修复基准指数提示，只有所有基准 provider 失败时才显示“基准指数数据不可用”。
  - 已创建 `docs/FIX_LOG_2026-04-30.md`，包含本地查验地址。
- 已处理 `docs/REVIEW_2026-04-29-R7.md`：
  - ENV-1 已排查：不是简单 shell 代理变量问题，去掉代理变量后 AkShare A 股仍失败；设置 `NO_PROXY='*'` 后变为连接被远端断开。
  - A 股 AkShare 未标记为修复，继续保留 Yahoo 回退和 `quality_flags` 警告。
  - 已完成 lightweight-charts K 线图替换，技术研究页从旧 SVG 折线图切换为 K 线 + 成交量 + MA20/MA50/VWAP20。
  - 已启动本地服务并在 `http://127.0.0.1:4173/stocks/09988` 打开核验。
- 已新增项目根目录 `AGENTS.md`。
- 项目 `AGENTS.md` 引用全局规则 `/Users/agg/.codex/AGENTS.md`。
- 本项目补充保留审查/FIX_LOG 协作规则，以及禁止包装占位数据的约定。
- 已按用户要求安装全局 skills：
  - `/Users/agg/.codex/skills/using-superpowers`
  - `/Users/agg/.codex/skills/planning-with-files`
- `gsd-method-guide` 和 `OpenSpec` 未找到明确可安装的 Codex skill 来源，暂未安装。
- 已处理 `docs/REVIEW_2026-04-29-R5.md`：
  - snapshot 读取 4 小时缓存。
  - 首页新闻可点击。
  - 技术结论不再出现 `None`。
  - 删除 `PriceChart` 未使用参数。
- 已处理 `docs/REVIEW_2026-04-29-R6.md`：
  - 手动刷新绕过缓存。
  - 清理 `mt` 别名冲突并启动时检查别名冲突。
  - 接入 AkShare Provider 路由层，港股已走 AkShare。
  - 每轮 `FIX_LOG` 需要写明本地查验地址和服务状态。

近期关键决定：

- 已启动 V30 新闻精准化：新增 Finnhub 美股新闻主源、自动股票关键词引擎和 Google News 精准查询；非精确新闻源先过公司/业务线/高管关键词验证，再进入评分。
- 已按用户反馈修正 V30 方向：新增股票不能依赖逐只手工适配，系统会自动用股票代码、市场格式代码、股票名称和关注理由生成新闻查询包；手工词典只作为核心标的增强层。
- 已继续收口 V30 剩余项：A股个股新闻路径、RSSHub 智通财经补充源、新闻源并发路由、慢源时间预算、评分层读取精准匹配结果。
- V30 抽样结果：MSFT / AAPL / 09988 / 00700 / 000001 均入选 5 条；600519 入选 3 条，原因是近 48 小时高相关新闻不足，未放宽到旧新闻。
- 已完成 V31 后台刷新调度层第一版：
  - 后端新增 APScheduler + 串行刷新队列，不再让手动刷新阻塞用户页面。
  - SQLite 新增 `refresh_jobs` 表和 WAL 模式，记录刷新状态。
  - 新增 `/snapshot/cached`、`/snapshot/status`、`POST /refresh` 三个端点。
  - 首页摘要和个股页面改为优先读缓存，前端新增“读取缓存 / 手动刷新”状态栏。
  - 验证：缓存端点约 5ms、刷新入队约 11ms、状态查询约 2ms、首页约 0.98s、阿里个股页约 0.50s。
  - 已补后台刷新硬超时：单只股票刷新超过 90 秒会标记失败；服务重启会清理旧 running / queued 状态。
  - 当前前端 dev 服务有 `EMFILE` 文件监听警告，但页面可正常访问。
- 已完成 V30 / V31 自查并新建 `docs/SELF_AUDIT_V30_V31_2026-05-05.md`：
  - 修复 `POST /api/research/refresh` 入队后仍读取全股票池缓存的问题。
  - 清理自查触发的全量刷新测试队列。
  - 当前首页约 0.70s，阿里个股页约 0.10s，队列为空。
- 已新建 `docs/PROGRESS_SUMMARY_2026-05-02_TO_2026-05-05.md`，汇总 5月2日到 5月5日的版本推进、产品重构、消息/情绪/数据源状态和遗留方向。
- 后续如继续 V31，需要补首页专用摘要缓存和生产模式构建；当前已不再需要提醒评估“后台刷新调度层”，因为第一版已落地。
- 数据源状态页继续保持“系统仪表盘”定位，但移除低价值重复区块：不再展示“影响范围”和页面内“入选新闻”列表；行情缓存提示不得作为行情质量警告。

- 全局协作规则放在 `/Users/agg/.codex/AGENTS.md`。
- 项目级规则只写本项目特殊事项，不重复全局全文。
- 能确认来源的第三方 skill 才安装；找不到明确来源的名称不伪装安装成功。
- 下一阶段重点是 pandas-ta-classic 指标迁移、LLM 化 `assistant_summary`，以及 K 线图 hover/缩放体验。
- UI 重构后下一阶段重点：用真实浏览器继续检查移动端和长页面滚动体验，并考虑历史验证可视化。
- 2026-05-09 新闻循环测试已跑满一小时：通过主线程 + 港股/美股/A股子代理并行新增股票验证，收口为动态实体档案、标题级实体匹配、普通词 ticker 严格匹配、低信号过滤和跨源去重。详见 `docs/NEWS_LOOP_TEST_2026-05-09.md`。
- 2026-05-09 已完成社媒情绪最佳实践研究：新建 `docs/SOCIAL_SENTIMENT_BEST_PRACTICES_2026-05-09.md`。核心结论是把“社媒探针”升级为 Social Signal Engine，拆分 attention 和 sentiment；美股先接 ApeWisdom/Reddit 热度，A股先做东方财富股吧热度，港股雪球先做入口验证；未通过质量门槛前不进入情绪主结论。
- 2026-05-09 已落地 Social Signal Engine 第一版：新增 ApeWisdom 美股热度源，`sentiment_intelligence.social_signal` 输出 attention / sentiment / narratives / quality / samples；情绪页改为讨论热度、观点方向、入分状态和社媒信号仪表。AMD 验证可显示 Reddit 热度异常升温；600519/09988 公开社媒入口失败时明确不可入分。详见 `docs/PRODUCT_TEST_SOCIAL_SIGNAL_ENGINE_2026-05-09.md`。
## 2026-07-12 GitHub + Vercel 自动更新链路

- 正式 Dashboard 构建已移除本地 DuckDB 依赖，改读可版本化的 OpenRouter、Foundry、活跃模型价格和 CAPEX JSON。
- 新增 `tracker_v2/scripts/refresh_capex_history.py`：保留现有中美 CAPEX 历史，并通过 SEC companyfacts 自动追加美国五家公司最新官方值；失败时保留旧值并暴露状态。
- 新增 `tracker_v2/scripts/refresh_and_build.py`、GitHub Actions 每日 `00:17 UTC` 工作流、`vercel.json` 和 `public/index.html`。
- 首次全量自动刷新成功：OpenRouter 52 周、Foundry 630 条价格/49 条 availability、OpenRouterList 871 个模型、CAPEX 24 条；完整 dashboard 回归 40 passed。
- 私有 GitHub 仓库已创建并验证 Actions 在线执行成功；Vercel 已连接该私有仓库，主分支推送会自动发布到受登录保护的 `https://trackerv2-git-main-angusggsimids-projects.vercel.app`。

## 2026-07-12 Sites 私密镜像与每日同步

- Sites 项目首次私密发布成功：`https://ai-compute-economics-tracker.angusgu456396.chatgpt.site`。
- 独立 Sites 源位于 `tracker_v2/sites_app`，根地址跳转到与 Vercel 同源的自包含 `dashboard.html`；不复制第二套图表组件。
- 已创建 Codex cron 自动化 `ai-compute-tracker-sites`，每天香港时间 09:00 检查 GitHub 当日刷新、四源 fresh 状态和 Dashboard 测试；全部通过才保存并私密发布 Sites 新版本。
- 任一来源、测试、构建或发布失败时保留上一版 Sites，禁止 degraded 数据覆盖线上版本。
## 2026-07-12 修复 Vercel Deployment Blocked

- 浏览器登录 Vercel并读取部署页，确认 Blocked 不是构建问题，而是提交作者 `agg@Macbook-M1-Air.local` 未被识别为 Hobby 团队成员；Vercel通知邮件也给出相同原因。
- tracker_v2 本地 Git 身份和 GitHub Actions 提交身份均改为 GitHub 账户专属地址 `281128372+angusggsimid@users.noreply.github.com`。
- 手动提交 `7476fbe` 触发 Vercel Ready；随后真实运行 GitHub Actions，机器人提交 `840f3d6` 同样触发 Vercel Ready，正式地址 13 张 SVG、24 条 CAPEX、0 console error/warn。
