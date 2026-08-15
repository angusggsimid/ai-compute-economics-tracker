# AI Compute Economics

用于沿时间轴追踪 AI 需求、GPU 租赁价格与可用性、活跃模型 Token 牌价，以及美国和中国云厂商资本开支证据。

- 正式说明：[README_v2.md](README_v2.md)
- 产品入口：`html_dashboard/ai_compute_economics_monitor.html`
- 部署文件：`public/index.html`
- 数据与方法：`tracker_data/backfills/`、`research/`、`docs/`
- 本地启动：在项目根目录运行 `python3 -m http.server 8767 --directory html_dashboard`
- 本地地址：`http://127.0.0.1:8767/ai_compute_economics_monitor.html`
- Vercel：<https://trackerv2-git-main-angusggsimids-projects.vercel.app>
- EdgeOne：<https://ai-compute-tracker-fpypxnc7.edgeone.cool>

项目完整架构、采集方式、刷新机制、测试和数据边界见 `README_v2.md` 与 `ARCHITECTURE.md`。
