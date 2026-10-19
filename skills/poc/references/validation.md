# POC 验证清单

## 基础验证

- `/poc` 空参数会询问起点。
- “接着上次”会优先读取 `/workspace/state/poc/progress.json`。
- 顶层 state 只保存路径引用，不复制底层完整 state。

## 阶段验证

- xlsx 分类路径可生成报告。
- no-excel 路径可展示固定 7 意图。
- POC 业务阶段不更新 X-Token。
- Fallback agent 创建后可回填 `--poc-fallback-agent-id`。
- 知识库阶段可跳过。
- POC 批测跳过 Fallback，只测业务 agent。
- 手册生成前已确认品牌、官网、账号邮箱。
