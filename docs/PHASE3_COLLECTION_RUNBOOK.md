# Phase 3 Collection Runbook

## 每日闭环

```bash
cd /Users/agg/Documents/New\ project\ 2/tracker_v2
python3 scripts/run_phase3_daily.py
```

Runner 会：

1. 获取互斥锁，拒绝并发重复运行。
2. 执行 production market-facts 更新。
3. 重建 DuckDB 派生 views。
4. 检查核心来源 freshness。
5. 写入 `tracker_data/phase3_runs/*.json`。
6. 生成 `tracker_data/thesis_states/` 四时钟状态快照和 transition。
7. 更新失败或核心源 stale/missing 时返回非零状态。

## 只检查状态

```bash
python3 scripts/run_phase3_daily.py --audit-only
```

## 历史回填

```bash
python3 scripts/backfill_gpuperhour_snapshots.py --dry-run
python3 scripts/backfill_gpuperhour_snapshots.py
```

回填只读取数据库已经引用的本地原始 JSON snapshot，不访问新来源、不生成估算值。

## Source SLA

- Core daily：GPUPerHour、RunPod、Vast，36 小时后 stale。
- Secondary daily：ComputePrices、Azure、AWS、模型价格目录，48-72 小时后 stale。
- Weekly proxy：OpenRouter frontend rankings，216 小时后 stale。

## launchd

模板：`ops/com.agg.ai-compute-tracker.phase3.daily.plist.example`，默认每天 08:30 执行。模板已通过格式校验，但当前未安装到系统。
