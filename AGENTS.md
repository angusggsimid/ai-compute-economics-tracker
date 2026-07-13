# AGENTS.md

本项目默认遵守全局规则：

`/Users/agg/.codex/AGENTS.md`

## 本项目补充规则

1. 审查文档 `docs/REVIEW_*.md` 只读，不直接修改。
2. 修复结果统一写入 `docs/FIX_LOG_YYYY-MM-DD.md`，按问题编号记录。
3. 不把占位数据、模拟数据、未验证结果包装成真实结论。
4. 唯一正式产品入口是 `html_dashboard/ai_compute_economics_monitor.html`；旧 Streamlit、旧 MVP 和 `ai_compute_trend_board.html` 仅作历史参考。
5. 每轮 `FIX_LOG` 必须写明本地查验地址，并确保服务已启动。
6. 本项目本地 Git 与 GitHub Actions 统一使用 `281128372+angusggsimid@users.noreply.github.com`，避免 Vercel Hobby 阻止部署。

## 数据决策系统优先级

当任务涉及 tracker、monitor、dashboard、决策体系、投资研究系统时，必须先完成数据和判断，再做产品封装。

执行顺序固定为：

1. 明确要帮助用户判断什么。
2. 建立真实数据底表：数值、日期、来源、单位、频率、口径、解释力。
3. 定义数据如何 track、如何去重、哪些剔除。
4. 建立决策规则和反证条件。
5. 输出最小可用判断。
6. 最后才做 UI、dashboard 或产品封装。

硬性约束：

1. 没有真实数据底表时，不允许交付产品壳。
2. 没有最小可用判断时，不允许声称 tracker 完成。
3. “显示数据缺失”只能算风险暴露，不能算完成。
4. 验收必须包含“是否对用户决策有用”，不能只看构建通过、页面可访问、控制台无错误。
