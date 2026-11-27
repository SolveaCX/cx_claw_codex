# CXClaw 排查工作台：两端维护边界

工作台消费已诊断、已脱敏的 `schemaVersion: 1` 数据。业务分类、证据与修复建议由 skill 生成；渲染器负责字段和引用校验、展示及固定 10 列 XLSX，不替代逐条诊断。

| 内容 | 插件仓库 cx_claw_codex | 线上仓库 solvea-kit |
|---|---|---|
| 业务流程 | skills/shulex-support/references/badcase-analysis/ | app/domain/slg/skills/shulex-support/references/badcase-analysis/ |
| HTML/CSS/JS | src/workflows/assets/badcase-workbench.* | app/domain/slg/skills/shulex-support/assets/badcase-workbench.* |
| 渲染 | src/workflows/badcase-report.ts | app/domain/slg/skills/shulex-support/scripts/badcase_report.py |
| 入口 | badcase render --data-file ... --output-dir ... | python3 /skills/shulex-support/scripts/render_badcases.py --data-file ... |
| 文件位置 | 调用方传入实际目录 | bootstrap 注入 workspace；state 存诊断数据，outputs/shulex-support 每次创建唯一目录 |

三个前端模板文件保持字节一致，不在数据生成阶段改模板。JSON字段、分类候选、引用校验及XLSX列序同时维护；Markdown在插件用marked、线上用Python markdown解析，都保留原文并输出安全HTML及Excel纯文本。HTML内嵌本次Excel，独立文件下载不依赖同目录HTTP地址。线上原有Python沙箱依赖已含markdown/openpyxl，渲染无需Node。

Skill同步时保留运行时差异：插件context和CLI命令、线上租户注入和Python接口、各自目录规范及现有产品分流。历史版本查询使用queryGraph，核对agentId/version/graph；未指定版本保留queryGraph/latest行为，不能把返回草稿认作发布图。

修改后用同一份合成数据在两端生成并检查：分类下钻、未确认Agent、同会话多个case、返回保留筛选、会话Markdown、chatId复制、空批次、窄屏、内嵌Excel与独立文件一致。客户会话样本只在本机临时目录验证，不提交到仓库。

线上相关测试：test_badcase_report、test_solvea_api_agents、test_shulex_support_badcase_text_contract、test_shulex_support_badcase_chatflow_contract、test_shulex_support_skill_contract；插件运行badcase-report/report-markdown测试及仓库检查。插件完成验证后执行bun run dev:plugin并核对宿主安装缓存；线上遵循现有服务部署及启动时skill同步，不在开发阶段改生产文件。

本迁移限于skill、独立脚本、静态模板和图配置查询参数。服务协议、SSE与test-ui没有改动；真实在线预览权限与下载策略仍需在发布环境验收。
