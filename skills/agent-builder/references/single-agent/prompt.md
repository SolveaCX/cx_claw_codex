# SINGLE_AGENT Prompt

Prompt 要写职责、边界、工具使用条件和回复要求，不要把路由流程、模板回复、转人工策略全塞进去。流程复杂时改用 CHAT_FLOW。

## 必守规则

- `prompt` 和 `displayPrompt` 保持一致。
- prompt 提到的外部能力必须有真实工具绑定。
- 固定话术优先走模板库或 CHAT_FLOW REPLY(TEMPLATE)，不要让 SINGLE_AGENT 硬背长固定文本。
- 需要变量系统字段时先查 `list-ai-fields`，并确认对应字段会在运行时进入上下文。

## 常见错误

- prompt 写“调用订单工具”，但 `usedPlugins` 没有订单工具 id。
- prompt 要求多分支跳转，但 Agent 本体没有稳定路由能力。
- 只改 `displayPrompt`，导致页面展示和实际执行不一致。
