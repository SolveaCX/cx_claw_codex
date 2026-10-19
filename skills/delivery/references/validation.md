# Delivery 验证清单

## 基础验证

- `/delivery` 空参数会询问起点。
- “接着上次”会优先读取 `/workspace/state/delivery/progress.json`。
- 顶层 state 只保存路径引用。

## 阶段验证

- xlsx 分类路径可生成报告。
- Delivery 创建默认更新 X-Token。
- 知识库阶段为必做，除非用户明确确认已有并通过后端状态验证。
- 回归测试支持历史抽样和上传用例。
- partial 续跑由 delivery runner 负责。
