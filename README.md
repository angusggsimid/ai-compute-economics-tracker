# AI Compute Economics Monitor

> 用独立频率的证据链回答一个问题：**算力稀缺溢价是否正在松动或加剧？**

[![CI](https://github.com/angusggsimid/ai-compute-economics-tracker/actions/workflows/refresh-dashboard.yml/badge.svg)](https://github.com/angusggsimid/ai-compute-economics-tracker/actions/workflows/refresh-dashboard.yml)

**线上地址**
- EdgeOne：https://ai-compute-economics-tracker-vlhs40vz.edgeone.cool （公开）
- Vercel：https://trackerv2-git-main-angusggsimids-projects.vercel.app （登录保护）

这不是又一个"把更多图表塞进一页"的仪表盘。它是一套**面向二级市场投资者的证据系统**：每个数字可回溯到原始快照与哈希，每条曲线有可比性门槛，每个结论自带反证条件。

---

## 核心方法论：四时钟

四个时钟各自按**原生频率**独立评估，不混频、不合总分：

| 时钟 | 频率 | 回答的问题 | 当前状态 |
|---|---|---|---|
| **Supply Price** | 日频 | GPU 租赁价格是否松动/紧缩（幅度×持续×广度×深度） | 见线上页面 |
| **Capacity & Utilization** | 日/周频 | 低价是否伴随供给（订单簿深度）扩大 | 见线上页面 |
| **Demand & Unit Economics** | 周/月/事件 | 模型降价是否换来调用量上升 | 见线上页面 |
| **Commitment & Monetization** | 季度/事件 | CAPEX/guidance/RPO 是否确认 | 见线上页面 |

状态机：`Unobservable → Observing → Trend → Inflection Watch → Confirmed`，**双向**（松动 Watch 与紧缩 Watch 并行评估）。纪律：

- 证据不足时输出低状态并说明阻塞项，绝不用文案升级
- 公开 proxy 用量封顶 Trend，不冒充官方拐点
- 横截面绝不连线成趋势；季度数据不插值
- **每个结论自带反证条件**（页面时钟卡片可展开查看）

## 数据来源（12 个，全部公开渠道）

| 层 | 来源 | 说明 |
|---|---|---|
| 用量 | OpenRouter 周榜 | 52 完整周滚动，未完成周剔除 |
| 价格（报价层） | Foundry Signals | 日度中位价/区间/供应商明细/可用率 |
| 价格（成交层） | Ornn OCPI | 成交型 GPU 指数（免费层滚动窗口，每日快照累积） |
| 价格（综合层） | SemiAnalysis 公开指数 | H100/A100/B200 日线全史 + H100 1Y 合约调查区间 |
| 价格（面板层） | Foundry providerPrices | 固定成员、起点=100 的面板指数，杜绝构成漂移 |
| 价格（定盘层） | gpu-markets | 12 场地 spot/on-demand/reserved 定盘 |
| 订单簿深度 | GPUPerHour / Vast.ai / RunPod | 逐条报价快照，时点观测按日累积 |
| 供应商广度 | adriannutiu/gpu-rental-prices | 34 家逐 offer，CC BY 4.0，含 Zenodo 历史回填 |
| 牌价账本 | OpenRouter 活跃模型 | 968 模型调价点（change-point ledger） |
| Token 实现价 | Ornn OTPI | 按 lab 成交加权实现价 |
| 吞吐基准 | inference-cost-truth | 676 个带引用的吞吐数据点（CC BY 4.0） |
| CAPEX | SEC companyfacts + 官方披露 | 美国五家季度 + 中国厂商事件，原频率不插值 |
| 成本锚 | FRED | CPI（名义→实际平减）+ 美国电价（OPEX 底座） |
| 供给锚 | Epoch AI | 芯片出货季度估算 |

## 自动化架构

```
GitHub Actions（每日 00:17 UTC）
  ├─ 11 个采集任务（4 阻塞 + 7 积累型信息源，失败暴露但不阻塞）
  ├─ 发布门（freshness 校验）+ 测试门（pytest）+ 浏览器门（Playwright 运行时零错误）
  ├─ thesis_engine 四时钟评估 → 状态归档 + 月度审计
  ├─ 构建单页 dashboard → 提交推送
  ▼
push 同时触发 Vercel 与 EdgeOne Pages 的 GitHub 集成自动部署
```

全程云端，本机零参与。任何一关失败即不发布，线上保留上一版。

## 项目历史

- **2026-07 初**：v1 MVP（CSI 复合指数 + Streamlit）——被数据审查证伪：18k 行事实中 79% 是 token_price，但单序列最多 3 个日期。**行数不等于趋势**。
- **2026-07-10**：重立项（`docs/PROJECT_REFRAME_2026-07-10.md`）。保留采集器/快照/provenance，废弃 CSI 与固定置信度，重建为四时钟状态机 + 可比序列层。
- **2026-07-11**：Phase 0–6 一日完成并通过投资人验收（68 项测试）。
- **2026-07-12**：重构为时间序列产品（12 图），上线 Actions + Vercel。
- **2026-08**：停用 Sites 镜像；接入 EdgeOne 双部署；订单簿/成交指数/合约层/面板指数/吞吐/成本锚陆续接入；判断层全双向化并进入每日管线。
- 完整演进记录见 [`CONTEXT.md`](CONTEXT.md) 与 [`docs/`](docs/)。

## 本地运行

```bash
pip install -r requirements-deploy.txt
python3 scripts/refresh_and_build.py          # 刷新+构建
python3 scripts/validate_deploy_refresh.py    # 发布门校验
python3 -m pytest test_suite/test_time_series_dashboard.py  # 测试
python3 -m http.server 8767 --directory public # 本地预览
```

关键脚本：[`thesis_engine.py`](thesis_engine.py)（四时钟）、[`scripts/refresh_and_build.py`](scripts/refresh_and_build.py)（管线）、[`scripts/browser_smoke.py`](scripts/browser_smoke.py)（浏览器门）、[`html_dashboard/build_time_series_dashboard.py`](html_dashboard/build_time_series_dashboard.py)（页面构建）。

## 文档

- [`ARCHITECTURE.md`](ARCHITECTURE.md) —— 架构与数据契约
- [`docs/ROADMAP_ADJUSTMENT_2026-08-23.md`](docs/ROADMAP_ADJUSTMENT_2026-08-23.md) —— 路线校准（双向拐点/外部锚/分层输入）
- [`docs/THESIS_STATE_CONTRACT.md`](docs/THESIS_STATE_CONTRACT.md) —— 状态机契约
- [`docs/FIX_LOG_*.md`](docs/) —— 全部修复记录
- [`lessons.md`](lessons.md) —— 方法论教训

## 许可与声明

- 代码：MIT（见 [LICENSE](LICENSE)）
- 数据：各上游许可不同（CC BY 4.0 / 免费层署名引用），已在各数据文件的 `attribution`/`sources` 字段逐一声明的为准
- **免责声明**：本项目只输出数据证据与状态，不构成投资建议，不接证券价格，不输出买卖信号。
