# 安全策略

## 报告漏洞

本项目是只读数据监控器，不处理用户输入、不存储凭证。若你发现安全问题（如数据管道被注入、依赖漏洞），请通过 GitHub [Security Advisories](https://github.com/angusggsimid/ai-compute-economics-tracker/security/advisories/new) 私密报告，勿直接开 issue。

## 数据安全边界

- 仓库不含任何 API 密钥；所有采集均走公开免鉴权渠道
- CI 密钥（如有）仅存于 GitHub Actions Secrets
- 数据文件均为公开渠道快照，附来源与 SHA256
