# AI Compute Economics 项目规则

- `docs/REVIEW_*.md` 只读；修复按编号写入 `docs/FIX_LOG_YYYY-MM-DD.md`。
- 不把占位、模拟或未验证数据包装成真实结论。
- 唯一正式入口是 `html_dashboard/ai_compute_economics_monitor.html`；旧 Streamlit、MVP 和 `ai_compute_trend_board.html` 仅作历史参考。
- `FIX_LOG` 写明本地查验地址，并确保服务可访问。
- Git 与 GitHub Actions 使用 `281128372+angusggsimid@users.noreply.github.com`，避免 Vercel Hobby 拒绝部署。
- 数据产品按“真实底表 → 口径与去重 → 决策规则 → 最小判断 → UI”执行；验收必须判断是否真的帮助用户决策。
