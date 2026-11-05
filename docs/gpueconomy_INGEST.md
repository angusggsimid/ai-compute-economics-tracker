# GPU Economy 数据接入（P2-1 / P2-2）

GPU Economy 在本项目里是**二级参考层**：用于覆盖检查和口径对照，不覆盖、不替换自有 primary 报价，也不参与自有中位、provider 数或周指数计算。

## 1. 来源与许可

| 项 | 值 |
|---|---|
| 数据入口 | https://gpueconomy.com/data |
| 原始文件 | `prices.json`、`gpus.json`、`providers.json`、`history.json`、`token-cost.json`、`changelog.json`、`price-index.json` |
| License | CC BY 4.0（https://creativecommons.org/licenses/by/4.0/） |
| Attribution | `GPU Economy (https://gpueconomy.com)` |
| Methodology version | `1.33.63` |
| Methodology changelog | https://gpueconomy.com/methodology/changelog |
| 源数据更新时间 | `2026-11-03T12:48:20.451387+00:00` |
| 本地快照入库时间 | `2026-11-04T09:12:14Z`（复制/校验时间，不是源站抓取时间） |
| 页面引用串 | `GPU Economy · CC BY 4.0 · methodology 1.33.63 · data 2026-11-03`（页面从 `crosscheck.json` 动态生成，数据未加载时显示 `methodology — · data —`） |

本项目的派生结果（重算中位、crosscheck、覆盖率）不是 GPU Economy 官方发布的数字；引用时必须同时保留 attribution、license、methodology version 和 data date。

原始文件直链为 `https://gpueconomy.com/<文件名>`，例如 https://gpueconomy.com/prices.json、https://gpueconomy.com/gpus.json；每个文件的 `url` 也记录在 `metadata.json` 的 `files[]` 中。

## 2. 快照目录与校验

```
tracker_data/external/gpueconomy/
└── 2026-11-03/
    ├── metadata.json
    ├── prices.json.gz
    ├── gpus.json.gz
    ├── providers.json.gz
    ├── history.json.gz
    ├── token-cost.json.gz
    ├── changelog.json.gz
    └── price-index.json.gz
```

每个 `.gz` 都是上游 JSON 的原样内容，用 `gzip -9 -n` 语义压缩（`GzipFile(compresslevel=9, mtime=0)`，不存文件名），因此同一份输入可复现相同字节。

| 文件 | count | count 单位 | bytes_gz | sha256_gz |
|---|---:|---|---:|---|
| `prices.json.gz` | 1,399 | rows | 89,621 | `b72b213ffc4d5e18c46fadf8949243d79c421dc2a48cd704a2d4dcd43689d849` |
| `gpus.json.gz` | 82 | gpus | 3,523 | `face904b2a99ea66020de0143a2c68fcf246bc11ba4429dea0f20c2c47df4798` |
| `providers.json.gz` | 127 | providers | 56,888 | `2aab9289b14825ed05f8544dcff2677b16ced10b1a525cfd65fdac224a3c41d2` |
| `history.json.gz` | 1,773 | model-weeks | 40,173 | `0d2d23e4d7456745785ad881017281dd2436eba5d9e7dd4ba84d374677db6e55` |
| `token-cost.json.gz` | 20 | benchmark-runs | 1,381 | `125cc601a3be9aa5e06e02e83817f5cff5e1ad2f96ae1f709d8875b9b8e56e13` |
| `changelog.json.gz` | 12,848 | moves | 330,805 | `3c806e075327db0aaade669f56fb7c6a04dee6f00e1ffe77c5371d145de88200` |
| `price-index.json.gz` | 9 | weekly-points | 11,273 | `e2c1e9b529aae8a7d38348c5ede399a5e33ee1e54b1913b06eb01baaee4851bf` |

合计：raw `11,214,018` 字节，gzip `533,664` 字节。`providers.json.gz` 的 127 条是 provider 记录，其中 121 家 `scraped=true`；另有 151 条 `not_listed` 记录（上游标注的未上架/不可用主体），不是 151 家可比 provider。

`metadata.json` 顶层包含：`source`、`source_url`、`fetched_at`、`data_updated_at`、`methodology_version`、`methodology_changelog`、`license`、`license_url`、`attribution`、`compression`、`files[]`、`file_count`、`total_bytes_raw`、`total_bytes_gz`、`counts`、`notes`。每个 `files[]` 条目记录 `path`、`source`、`url`、`count`、`count_unit`、`count_detail`、`bytes_raw`、`bytes_gz`、`sha256_raw`、`sha256_gz`。

### 校验方法

一键校验（建议每次刷新后和构建前都跑）：

```bash
python3 scripts/ingest_gpueconomy.py --verify tracker_data/external/gpueconomy/2026-11-03
```

它会逐文件检查：

- `metadata.json` 必填字段、`file_count`、7 个必需文件是否齐全；
- `metadata.json.methodology_version` 为 `N.N.N`，并与解压后的 `prices.json.methodology_version` 一致；
- 所有声明文件的 `data_updated_at` 与 `prices.json` 一致；
- 落盘的 `.gz` 字节数与 `sha256_gz`；
- 解压后的字节数与 `sha256_raw`；
- `prices/gpus/providers/history/token-cost/changelog/price-index` 的 count。

手工抽查单个文件：

```bash
shasum -a 256 tracker_data/external/gpueconomy/2026-11-03/prices.json.gz
# 与 metadata.files[].sha256_gz 对比

gzip -dc tracker_data/external/gpueconomy/2026-11-03/prices.json.gz | shasum -a 256
# 与 metadata.files[].sha256_raw 对比

gzip -dc tracker_data/external/gpueconomy/2026-11-03/prices.json.gz \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["prices"]))'
# 与 metadata.files[].count 对比
```

`load_external()` 在构建时默认选择 `tracker_data/external/gpueconomy/` 下最新的 `YYYY-MM-DD` 目录（当前 `2026-11-03`），并做同样的 gz/raw 字节数和 sha256 校验；同时校验 metadata 的 `methodology_version` 格式及与 `prices.json` 的一致性。快照损坏或版本不一致会直接让构建失败，不会静默降级成 0 或空表。

## 3. 刷新命令

### 3.1 从本地目录刷新（`--from-dir`）

先把 7 个上游 JSON 下载到同一个本地目录，然后：

```bash
python3 scripts/ingest_gpueconomy.py \
  --from-dir /tmp/gpu-research \
  --date 2026-11-03 \
  --out tracker_data/external/gpueconomy
```

### 3.2 直接联网刷新（`--url`）

也可以让脚本自己下载 7 个文件：

```bash
python3 scripts/ingest_gpueconomy.py \
  --url https://gpueconomy.com/data \
  --date 2026-11-03 \
  --out tracker_data/external/gpueconomy
```

- `--url` 会从 data page 或 base URL 推导出 7 个 JSON 的 URL，用 `urllib` 下载（带 User-Agent 和 timeout），然后走与 `--from-dir` 完全相同的校验、gzip、metadata 流程。
- `--url` 与 `--from-dir` 互斥；`--timeout` 可调单文件下载超时，默认 30 秒。
- 下载失败会明确报 URL 和异常，不会写半成品快照。`--url` 的下载路径由测试用 monkeypatch 验证；本轮文档更新未实际联网跑（未验证 live 下载）。
- 构建本身仍只读仓库内快照，不联网；`gpu_external.SNAPSHOT_DIR` 自动取最新日期目录（当前 `2026-11-03`），只有显式 `--url` 的 ingest 会访问网络。

### 3.3 通用校验与刷新后步骤

- `--date` 必须等于 `prices.json` 的 `data_updated_at` 日期；不传时默认取该日期。
- `--fetched-at` 可显式指定入库时间；不传时用当前 UTC 时间。
- 脚本先校验再写文件：7 个文件缺一即失败；逐文件检查 `license`、`data_updated_at` 和 attribution（`token-cost.json` 上游没有 attribution，按快照 attribution 继承并在 `metadata.notes` 说明）；`prices.json` 的 9 个必需行字段和 `usd_per_gpu_hour == listed_price_hour / gpu_count * (fx_rate or 1)` 会逐行复算（容差 `$0.01`）；`prices.providers` 必须等于 `providers.json` 中 `scraped=true` 的 121 家，`prices.gpus` 必须等于 `gpus.json` 的 82 张。
- `prices.json.methodology_version` 必须存在且匹配 `N.N.N`（当前 `1.33.63`）；其他文件如声明 `methodology_version`，必须与 `prices.json` 一致；所有文件的 `data_updated_at` 必须一致。`--verify` 也会校验 metadata 与 `prices.json` 的 `methodology_version` 一致，并校验所有声明文件的 `data_updated_at`。
- 刷新后跑一次 `--verify`，再重建页面和公开数据：

```bash
python3 scripts/ingest_gpueconomy.py --verify tracker_data/external/gpueconomy/2026-11-03
uv run --python 3.12 --with-requirements requirements-deploy.txt python html_dashboard/build_time_series_dashboard.py
```

当前目录只有 `2026-11-03` 一份快照（交付物尚未 commit，即将由 Sentinel 统一 commit）。新日期会在 `tracker_data/external/gpueconomy/` 下生成同级目录；脚本没有自动清理旧日期的策略，是否只保留最新一份需要在提交前人工决定。

## 4. 归一化口径

### 4.1 可比报价

crosscheck 的 external median 从 `prices.json` 重算，不使用 `gpus.json.rate_card_median` 直接做差值：

```text
market == "on_demand"
status == "live"
price_scope != "marketplace_floor"
listed_currency == "USD"
每个 provider 取 min(usd_per_gpu_hour)
再对 provider 值取 median
```

- 每家 provider 只算一票，取该 provider 符合条件的最低价。
- P25/P75 用 `(n-1)*p` 线性插值；`n < 4` 时留空。
- `gpus.json.rate_card_median` 含 serverless 和非 USD 报价，只作为 `ext_median_published` 审计值，不参与 `diff_pct`。

### 4.2 六个 market

- `on_demand`：主可比口径。
- `spot`、`serverless`：按同样规则可算差值，但 note 明确“spot 可被收回”“serverless 按秒/共享，不能当整租”。
- `reserved`：GPU Economy 拆成无期限/1y/3y，我方不保留期限，不可比。
- `community`：GPU Economy 混 marketplace floor 与实例供给，我方把 floor 单列为 marketplace，语义不等价。
- `marketplace`：只是 GPU Economy community 里的 floor 子集，不是等号。
- `public/data/external/gpueconomy.json` 与 `crosscheck.json` 的 `rules.comparable` 已同步为：“on_demand 是主口径；spot/serverless 按同一 live/非 floor/USD/每 provider min 规则可计算差值，但不能与整租 on-demand 混读；reserved/community/marketplace 因期限或 floor 语义不可比。”

### 4.3 H100 两条线

H100 不合并 `h100` 和 `h100-sxm`：

- `match_id="h100"`：形态未标注的 H100，作为主对照。2026-11-03 快照实测 median `3.97`（18 家）。
- `benchmark_id="h100-sxm"`：行业 SXM 基准，独立展示。实测 median `3.29`（37 家）。
- `h100-pcie`、`h100-nvl` 只作为 context/覆盖参考，不并入主 median。
- 我方 H100 同日混 80GB SXM、80GB PCIe、94GB NVL，所以即使 provider 重叠，也不是同 SKU 的 provider 级等价比较。
- 因此 H100 的 coverage 是 `mixed`（页面显示“SKU 混合”警告），不是绿色 `ok`。on_demand 仍保留卡级 `diff_pct=-8.4%`，但它只是混合 SKU 的卡级口径差，不能当 provider 级等价差。
- SXM 基准只在 `on_demand` 显示；H100 `spot` / `reserved` 的 `ext_benchmark_median=None`，页面不得显示 SXM 基准。

### 4.4 A100

我方 A100 同日混 40GB 和 80GB；GPU Economy 只取 `a100-80`。因此 A100 标记 `sku_mismatch`：保留 `ext_median` 和 overlap 作覆盖参考，但 `diff_pct=null`，所有 market 都不给差值。

### 4.5 Provider 对齐

只对明确别名做映射：`massedcompute→massed`、`ovh→ovhcloud`、`gmicloud→gmi-cloud`、`thundercompute→thunder`、`digitalocean→paperspace`（且只认 `region=="GPU Droplets"` 的 Paperspace 行）。其他 provider 不做模糊匹配。

### 4.6 crosscheck own 样本门槛

`crosscheck.json` 使用 `CROSSCHECK_MIN_OWN_PROVIDERS=8`：我方 provider 少于 8 家时，无论 external 覆盖多少，一律标 `coverage="thin"`、`comparable=false`、`diff_pct=null`，不显示口径差。

当前例子（on_demand）：GH200 own 3 / ext 4、RTX 4090 own 4 / ext 16、RTX 5090 own 4 / ext 20、MI300X own 5 / ext 7，全部是“样本偏薄”、差值 `—`；H100 reserved own 3 / ext 1 也是 thin。H100 on_demand own 24 / ext 18 / overlap 16 仍是 `mixed`，保留卡级 `-8.4%`。

### 4.7 方法版本与 overlap 定义

`crosscheck.json` 顶层区分三个版本字段：

- `own_methodology_version="2026-11-04.1"`：AI Compute Economics 的方法版本。
- `ext_methodology_version="1.33.63"`：GPU Economy 的外部方法版本。
- `methodology_version="1.33.63"`：与 `ext_methodology_version` 同值，仍指外部版本。

`public/data/external/gpueconomy.json` 顶层也带 `own_methodology_version="2026-11-04.1"`。

`rules.overlap_definition` 明确：

```text
overlap = 我方该卡最新一天 on-demand provider 集合
          ∩ GPU Economy 同卡 family provider 集合
H100 family = h100 + h100-sxm + h100-pcie
overlap_count_match 只用 match_id 求交
```

因此本实现的 H100/H200/A100 overlap 是 16/12/12；facts-external §9.4 的历史 provider 池口径是 17/14/13。两者不是同一个定义，引用时要写清来源。

### 4.8 自有 monthly 与外部数据无关

本项目的 `monthly` 是自有 on-demand 日频固定 panel（见 `docs/FIX_LOG_2026-11-04.md`），不读取 GPU Economy 的 monthly/hourly 数据，也不进入 `crosscheck.json`。不要把两者混成同一个 panel，也不要用 external 数据去补自有 monthly 的空月。历史月会随底表回填重算，不是不可变快照；只有周指数有 final 冻结。

## 5. 不可比项与 UI 文案规则

### 不可比/弱可比项

- H100 的 80GB SXM / 80GB PCIe / 94GB NVL 混合。
- A100 的 40GB / 80GB 混合。
- H200 141GB 与部分 143GB NVL；B200/B300 存在 180/186/192GB、262/270/280/288GB 等实例变体。
- RunPod 等 provider 同日可能挂多个配置，provider 级价格不等于同一 SKU。
- 因此 external 只能做卡级覆盖/口径参考，不能做 provider 级等价替换。

### UI 文案

- 外部值永远标 `source_layer="gpueconomy"`，不能叫“我们的中位”或“我们的指数”。
- 差值统一叫 **“口径差”**，不叫“价差/溢价/成交价差”；全卡表显示“我方/外部”家数，选中行显示“我方 N 家 / 外部 M 家 / 重叠 K”，旁边显示 coverage 和 `as_of`。
- `coverage="thin"` 或 `own_thin=true` 时，口径差强制显示 `—`，不显示“可比”。
- coverage 映射：`mixed → SKU 混合（warn）`、`sku_mismatch → 型号不一致（bad）`、`ok → 可比`、`thin → 样本偏薄`、`none → 暂无外部`、`stale → 外部滞后`。
- H100 coverage 为 `mixed`，页面显示“SKU 混合”，不是绿色 `ok`；`-8.4%` 是卡级口径差，不是 provider 级等价差。
- H100 的 `h100` 主行和 `h100-sxm` 基准行分开展示，基准行明确“仅行业基准，不合并”；SXM 基准只在 on_demand 显示，H100 spot/reserved 不显示。
- A100 显示 `sku_mismatch` /“型号不一致”，差值显示 `—`。
- 没有外部对应卡/市场时显示“暂无外部对照”，不硬凑数字。
- 页面 attribution 从 `crosscheck.json` 动态读取 `methodology_version`、`data_updated_at`、`license_url`；meta、note、selected 三处 `CC BY 4.0` 都链接到 `https://creativecommons.org/licenses/by/4.0/`。数据未加载时显示 `methodology — · data —` + license fallback。
- `crosscheck.json` 异步加载失败时显示“外部对照暂不可用”；主图、指数和自有中位不受影响。
- listed rate 不是成交价、不是可用容量；页面保留该 caveat。

## 6. 历史回执复算

`public/data/receipts/index.json` 列出所有可复算的 card × ISO week，共 196 条（115 published / 54 withheld / 27 thin）。公开站点只保留每卡最新一周的回执；历史周用 CLI 复算：

```bash
python3 scripts/reproduce_receipt.py --card H100 --week 2026-W44 --out /tmp/h100-w44.csv
```

- 输出 17 列，列名与页面 `_landscapeReceipt` 一致：`card, iso_week, vintage, methodology_version, published_median, published_index, p25, p75, provider_count, provider, provider_id, usd_per_gpu_hour, date, source_url, quotes, included, excluded_by`。
- final 周优先读 `tracker_data/index_snapshots/<ISO_WEEK>.json` 的冻结值；其后的 provisional 周以冻结周 `receipt.included` 的 provider 值和冻结 index 为锚点，重新计算 index/linkPairs，冻结周自身不改。
- 找不到 card/week 时非零退出；数据或快照读取错误退出 2。
- 测试可用 `--snapshot-dir` 指定临时快照目录，避免在仓库里生成文件。
- 实测 H100 `2026-W44`：199 条 quote 行 = 24 included + 175 excluded。
