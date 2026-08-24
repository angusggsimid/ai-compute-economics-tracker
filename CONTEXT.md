# CONTEXT

## 2026-08-23 E1 判断层上线：四时钟每日自动评估（双向化）

- `thesis_engine.py` 接入每日管线（阻塞步骤）：JSON 底表 → 四时钟状态 → `tracker_data/thesis_states/latest-*` 入库 + 页面顶部时钟卡片。
- C1 已落地：loosening/intensifying 双向 Watch；Confirmed 要求方向+持续性+家族去重。
- 首个自动结论：Supply Price **Confirmed·intensifying**（B200/H200 90D +16~24%，SemiAnalysis 与 Ornn 双来源交叉确认）；Demand Trend（proxy 封顶）；Capacity/Commitment Observing（积累中）。
- 教训：排序键含价格会破坏同日多点的时序——时序点只能按时间稳定排序。

## 2026-08-24 判断层全量完成：四时钟全双向 + E2 面板指数 + 归档审计

- Commitment 经 guidance 修订规则升级 **Inflection Watch·intensifying**（Meta/Alphabet 上修）；Supply Price Confirmed·intensifying——监控器首次输出双时钟同向的紧缩确认叙事。
- 页面：时钟卡片展开证据链、E2 固定面板指数展项、移动端适配；thesis_states 增加每日归档与当月审计文件。
- 第 10 源 Epoch AI 芯片出货（Capacity 长锚）；neocloud 数据集季度归档策略记入待办；OPENROUTER_API_KEY 等用户提供。

## 2026-08-23 T1/T2 外部参考层已接入

- 新增两个非阻塞采集脚本并入每日管线（共九源）：
  - `backfill_reference_indices.py`：Ornn OCPI（成交型 GPU 指数，3mo 滚动窗口每日快照累积）、Ornn OTPI（4 lab 已实现 token 价）、SemiAnalysis 综合指数全历史（2023 起，含 H100 1Y 合约价区间）→ `reference_index_history.json`
  - `backfill_neocloud_prices.py`：adriannutiu/gpu-rental-prices CC BY 4.0 数据集（34 家供应商逐 offer 带来源 URL）→ `neocloud_provider_price_history.json`，作为 matched-panel 面板成员池
- 定位：成交型/调查型外部基准，交叉验证自采报价层；当前不进主图。信息源失败暴露但不阻塞发布。
- 待办（后续批次）：E1 状态机移植到 JSON 管线、C1 双向拐点规则、Epoch AI Chip Sales/Data Centers 接入（CSV 端点已验证 `epoch.ai/data/ai_chip_sales_*.csv`）、Demand 时钟 OPENROUTER_API_KEY 决策。

## 2026-08-23 重新接入 GPU 订单簿每日快照

- 用户决定：订单簿深度数据必须重新积累（Supply Price 拐点条件需要"offer 数/深度随价格下降而扩大"的证据；时点观测缺口无法回填）。
- 新增 `scripts/backfill_gpu_orderbook.py`：GPUPerHour/Vast/RunPod 三源独立采集，按 (date, source, series) 累积 offer 数、GPU 总数、P25/P50/P75 到 `tracker_data/backfills/gpu_orderbook_history.json`；unit 语义 gpuperhour/vast=offers、runpod=types（型号挂牌取最低可用按需档）。口径延续 Phase 1：MIG、$0 价、不可用档位价、未验证 offer 全部剔除。
- 接入定位：非阻塞信息源——失败暴露在 `deploy_refresh_status.json`（fresh/partial/failed）但不阻塞主链路发布；页面当前不展示该层，未来接入 Supply Price 深度证据或 UI 时升级为硬门槛。
- 验证：本地五源链路全绿；新增 10 项解析/合并测试，相关 21 项测试通过；GPUPerHour limit=100 实测对全部 9 个家族全覆盖（returned==total）。首日 24 行，H100 订单簿中位 $3.29（7 月中旬 DuckDB 读数 $2.90 同口径可比）。
- 教训沉淀：旧 DuckDB 轨道 2026-07-12 停更一个月才被发现——非阻塞源必须有状态可见性，这是本次把 orderbook 写进每日 status 文件的原因。

## 2026-08-15 自动化维护约定

- 用户要求：此后由助手持续维护本项目的自动化链路，不再新增发布渠道。
- 当前链路（唯一）：GitHub Actions `refresh-dashboard.yml` 每日 `00:17 UTC` 刷新四源数据 → 发布门/测试门 → push 到 main → Vercel 与 EdgeOne 各自经 GitHub 集成自动部署；本机无任何定时任务。
- 维护要点：Actions run 失败时先看 `refresh_and_build.py` 数据源状态与测试输出；EdgeOne 项目 `makers-p5qz8uawwwgl` 为控制台 OAuth 绑定，push 即部署，无 token 依赖；不要恢复 Sites、CLI 上传或任何本机定时任务。
- EdgeOne 地址：`https://ai-compute-economics-tracker-vlhs40vz.edgeone.cool`（公开）；Vercel 地址保持登录保护。

## 2026-08-15 停止 Sites 发布并彻底清理，仅保留 Vercel

- 用户决定：不再同步发布到 ChatGPT Sites，正式线上渠道只保留 Vercel（`https://trackerv2-git-main-angusggsimids-projects.vercel.app`）。
- 已删除 Codex 定时任务 `ai-compute-tracker-sites`（`~/.codex/automations/ai-compute-tracker-sites/` 整个目录）。
- 已删除本地 `sites_app/` 目录（约 759MB，从未被 git 跟踪，无历史损失）；`.gitignore` 移除 `sites_app/` 条目。
- 已清理 `README.md`、`README_v2.md`、`ARCHITECTURE.md` 中的 Sites 地址、Sites 同步自动化和 Sites 发布门描述；`docs/FIX_LOG_*` 历史记录保持原样不改写。
- GitHub Actions `refresh-dashboard.yml` 每日刷新 → push → Vercel 自动发布链路不变，全程云端，本机无定时任务。
- 已核查：仓库与本机均无腾讯云 EdgeOne 发布配置或 CLI，本项目从未发布到 EdgeOne；EdgeOne 账号下唯一的托管项目是 `marathon`，与本项目无关。

## 2026-08-15 新增 EdgeOne Pages 自动双发布

- GitHub Actions 提交推送后新增 `Deploy to EdgeOne Pages` 步骤：`npx edgeone@1.6.28 pages deploy public -n ai-compute-tracker -e production -a global --json`，API token 存于仓库 secret `EDGEONE_PAGES_API_TOKEN`（来自 `~/.edgeone` 2026-07-19 CLI 登录生成的 token）。
- EdgeOne 项目 `ai-compute-tracker`（`makers-2skmd9vvyabl`，Upload 直传类型）；本地首测部署 `dp6wwp87f7zg` 成功。
- EdgeOne 公开地址：`https://ai-compute-tracker-fpypxnc7.edgeone.cool`（无登录保护，与 Vercel 的登录保护不同）；回读 HTTP 200、标题正确、generatedAt 与产物一致。
- 发布顺序：数据门/测试门 → 提交 push（Vercel 自动部署）→ EdgeOne 上传；EdgeOne 步骤在 push 之后，失败不影响 Vercel，但会让 Actions run 标红。
- 后续（同日，最终方案）：改为 marathon 同款 push 自动部署。API 创建的 Github 项目 `RepoOwner` 为空、push 不触发（事件路由只在控制台 OAuth 流程建立）；改经控制台「导入 Git 仓库」创建项目 `ai-compute-economics-tracker`（`makers-p5qz8uawwwgl`，main、输出目录 `public/`、无构建），push `be4de9e` 后约 30 秒自动部署成功，机制与 marathon 一致。正式 EdgeOne 地址：`https://ai-compute-economics-tracker-vlhs40vz.edgeone.cool`（公开、无登录保护）。
- 已清理：Actions 中的 EdgeOne CLI 上传步骤与 `EDGEONE_PAGES_API_TOKEN` secret 已移除；旧项目 `makers-2skmd9vvyabl`（Upload）与 `makers-rhz4zld7xqk4`（API Github）已通过 `DeletePagesProject` 删除。EdgeOne 账号下现仅 `marathon` 与本项目两个 Github 绑定项目。

## 2026-07-22 AI Compute Tracker Sites 每日同步

- GitHub Actions 当日手动触发 run `29883558801` 成功；刷新数据提交 `b2d01a0`，本地 `git pull --ff-only` 完成。
- 发布门通过：generatedAt=`2026-07-22T01:37:13Z`，status=`ready`、publishable=`true`；OpenRouter usage、Foundry Signals、OpenRouter active prices 均 fresh；SEC CAPEX 满足 `current_for_frequency` 且五家公司 cache current。
- 指定回归测试 12 passed。
- Vercel production deployment `READY`，projectId=`prj_QtBKCz4MqPcNU0HjC3XCa3MBC1ri` 与本地一致，`meta.githubCommitSha`=`b2d01a0` 等于本地 HEAD；正式响应原始字节与 `public/index.html` 的 SHA-256 均为 `1f389976b5f903e45e3e73ab02ddb4acab908394182d9709118ac19b77672846`。
- Sites 同步并构建成功，来源提交 `c5dd082`；version 7 部署状态 `succeeded`。固定地址 `https://ai-compute-economics-tracker.angusgu456396.chatgpt.site/dashboard.html` 回读 HTTP 200，标题正确，generatedAt 为当日。

## 2026-07-20 AI Compute Tracker Sites 每日同步

- GitHub Actions `refresh-dashboard.yml` 当日 run `29715950899` 成功，数据提交 `5dd9420`；`validate_deploy_refresh.py` 通过，generatedAt=`2026-07-20T04:03:07Z`，status=`ready`，publishable=`true`，OpenRouter usage、Foundry Signals、OpenRouter active prices 为 fresh，SEC CAPEX 为 current_for_frequency 且五家公司 cache current。
- `test_time_series_dashboard.py` 与 `test_deploy_refresh.py` 共 12 项通过。
- Vercel production deployment `READY`，项目 ID 与本地配置一致，Git SHA=`5dd9420`；正式响应原始字节 SHA-256 与 `public/index.html` 同为 `9649516c705bef43cdee4cb432bea884a708c10ccebe05246ed52c1c8232d319`。
- Sites `sites_app` 同步并构建成功，HEAD=`d66d745`；版本 6、部署状态 `succeeded`，固定地址 `https://ai-compute-economics-tracker.angusgu456396.chatgpt.site` 回读 HTTP 200，标题正确，generatedAt 为当日。Connector 同时确认 current_live_url 与最新 version commit_sha 一致。

## 2026-07-17 修复 Sites 每日同步的网络误阻断

- 今日 GitHub Actions run `29552746276` 成功，提交 `b8b4b20`；发布门通过，目标测试 12 项通过，数据生成时间为 `2026-07-17T03:35:56Z`。
- Sites 自动任务失败点不是数据或构建，而是本机网络将 `*.vercel.app` 解析到错误地址，`vercel curl` 与直接 curl 均超时；Vercel 管理 API 正常返回生产部署 `READY`、`target=production`，且 `githubCommitSha=b8b4b20...` 与本地主分支完全一致。
- 自动任务改为两级 Vercel 验证：优先读取正式响应并比较原始字节哈希；若仅因 `vercel.app` DNS、TLS 或边缘网络错误无法读取，则必须通过 Vercel 管理 API 同时验证 `READY`、`production`、正确项目 ID、部署 Git SHA 等于本地 HEAD，其他错误仍停止发布。
- Sites 回读同样允许在 Cloudflare 直接回读被本机网络拦截时，以 Sites connector 的 deployment `succeeded`、固定 live URL 和最新 version `commit_sha` 等于刚推送 HEAD 作为发布闭环；数据门、测试门和版本一致性门均未降低。
- 今日 Sites 已补发 version 4，来源提交 `7acbe40`，部署状态 `succeeded`，固定地址保持不变；构建测试 2 项通过。

## 2026-07-14 OpenRouter 滚动窗口历史保留

- GitHub Actions run `29303721784` 失败：上游 OpenRouter 周榜滚动接口返回 52 点，其中 `2026-07-13` 为未完成周；剔除后只剩 51 个完整周，`test_time_series_dashboard.py` 的至少 52 周断言失败。
- 现场核验（2026-07-14/15 UTC）：upstream raw `2025-07-21`…`2026-07-13`（52）、complete 51、本地 backfill 仍有完整周 `2025-07-14`…`2026-07-06`（52）；merge 后 52，仅本地保留 `2025-07-14`。
- 修复：`scripts/backfill_openrouter_cost_index.py` 将本地完整周与上游完整周按日期去重合并（同日上游优先，`--start-date` 为保留窗口下界）；永不纳入未完成周；合并后仍不足 52 或上游失败则硬失败；缓存损坏/schema 不符硬失败，禁止静默当空历史成功。`history_provenance` 记录 local-only 周、上一版原始响应哈希与覆盖统计；本地独有周缺 provider composition 或原始来源哈希时同样硬失败。
- 新增/加固 `test_suite/test_openrouter_cost_index.py`：滚动挤出、去重、start-date 边界、损坏/schema、不足 52、首次无缓存、幂等、合并满 52。
- 相关测试 33 passed；未降低 52 完整周门槛、未伪造数据。2026-07-15 完整真实刷新状态为 ready/publishable：OpenRouter 合并为 52 个完整周，52 个周日期均有 provider composition，provenance 保留上一版 OpenRouter 原始响应 SHA-256；Foundry、活跃模型牌价与 SEC CAPEX 同时 fresh。本地查验 `http://127.0.0.1:8767/ai_compute_economics_monitor.html`。
- GitHub Actions workflow_dispatch run `29388301304` 在 29 秒内成功，发布门与 dashboard 7 项测试通过，并自动提交 `38445e8`；Vercel 随后进入 Ready，正式响应与 `public/index.html` SHA-256 同为 `6e166e0a2d1026c6f313572cd46df303afd8c4816643c7dde153f168a6b6806c`。

## 2026-07-13 修复 GitHub、Vercel 与 Sites 自动发布链路

- 查明当天 GitHub 定时任务先失败、后手动恢复；根因是部署依赖遗漏、时间序列固定长度断言和 CAPEX 抓取失败被误报 fresh。
- 修复 `sec_capex` 假 fresh：采集脚本现在输出 `fresh / current_for_frequency / blocked`，并逐家公司记录最近官方 CAPEX 日期与年龄；五家公司任一缺失或超过 150 天即阻止发布。
- `refresh_and_build.py` 新增独立 `publishable` 门，blocked/degraded 时不再覆盖 `public/index.html`，并返回失败状态阻止 GitHub 提交。
- 新增 `scripts/validate_deploy_refresh.py`，GitHub Actions 与 Codex Sites 自动任务统一使用同一发布规则，避免两条链路口径漂移。
- 真实四源刷新通过：OpenRouter 52 个完整周、Foundry 633 条价格/49 条 availability、OpenRouterList 871 个历史模型、CAPEX 24 条且本地 SEC 五源抓取成功。
- GitHub Actions run `29235376461` 成功并提交 `071d860`；Vercel 正式响应与 `public/index.html` SHA-256 完全一致，线上数据时间为 `2026-07-13T08:25:56Z`。
- Codex Sites 任务于香港时间 16:40 由调度器真实自启动，发布门与 12 项测试通过，Sites version 2 部署 succeeded；固定地址最终 HTTP 200，版本来源提交为 `f27126e`。
- 自动任务已恢复为每天香港时间 09:00；Vercel 校验固定使用 CLI 原始响应字节，Sites 回读携带已有 bypass token 并跟随重定向。

## 2026-07-13 项目迁移至独立工作区

- AI Compute Economics 的代码、真实数据、快照、研究资料、GitHub/Vercel 配置和独立 Sites 工程已从混合项目目录迁入 `/Users/agg/Documents/AI Compute Economics`。
- 原路径 `/Users/agg/Documents/New project 2/tracker_v2` 保留为指向新项目的兼容链接，避免旧书签、命令和本地服务失效。
- Codex 每日 Sites 同步任务改用新项目作为工作目录；GitHub 仓库、Vercel 项目、Sites project id 和线上固定地址均保持不变。
- 两份此前散落在外部目录的用户研究已归档到 `research/ai-compute-tracker-sources.md` 与 `research/credential-free-data-architecture-research.txt`。
- 迁移验收时发现 GitHub 部署依赖遗漏导致 CAPEX 使用上一版数据，已补齐依赖；真实刷新四源全部 `fresh`，CAPEX 24 条、失败来源 0。
- 同时修复当前未完成周进入 OpenRouter 曲线造成的尾部假跌；正式序列只保留 52 个完整周，结束于 2026-07-06。
- 目标回归 33 passed；浏览器为 13 个 SVG、32 条 CAPEX 表格行、无横向溢出和控制台错误。

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

---

> 注：2026-07-10 重立项之前的旧 trend-board 时代日志与无关项目记录已清理（1326 行），完整历史见 git log 与 docs/archive/。

---
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

- 浏览器登录 Vercel并读取部署页，确认 Blocked 不是构建问题，而是提交作者 `(local-device)` 未被识别为 Hobby 团队成员；Vercel通知邮件也给出相同原因。
- tracker_v2 本地 Git 身份和 GitHub Actions 提交身份均改为 GitHub 账户专属地址 `281128372+angusggsimid@users.noreply.github.com`。
- 手动提交 `7476fbe` 触发 Vercel Ready；随后真实运行 GitHub Actions，机器人提交 `840f3d6` 同样触发 Vercel Ready，正式地址 13 张 SVG、24 条 CAPEX、0 console error/warn。

## 2026-07-19 Sites 每日同步

- GitHub `refresh-dashboard.yml` 当日 run `29672415958` 成功；`git pull --ff-only` 更新到 `73d6410`。
- 发布门通过：`generatedAt=2026-07-19T03:52:29Z`、`status=ready`、`publishable=true`，OpenRouter usage / Foundry Signals / OpenRouter active prices 为 fresh，SEC CAPEX 满足季度频率门；指定测试 `12 passed`。
- Vercel 部署 READY、production、项目 ID 正确，`vercel ls` 的 `meta.githubCommitSha=73d6410d...` 与本地 HEAD 一致；正式响应读取因本机边缘网络 curl 28 超时，采用允许的管理 API 备用证明。
- Sites 同步 `sites_app/public/dashboard.html`，构建产物和打包校验通过；Sites 提交 `12b0f361`，保存 version 5 并部署 `succeeded`。
- Sites 固定地址保持 `https://ai-compute-economics-tracker.angusgu456396.chatgpt.site`。带 bypass token 回读遇 Cloudflare 403 challenge，按规则用 connector 确认 deployment succeeded、固定 live URL、最新 version commit_sha 三项一致。
