# 策略管理

Strategy（策略）定义了：当某个条件（意图、触点、实体等）满足时，执行什么动作，例如路由到 Agent、回复模板、AI 回复、转人工或不处理。

## 条件构建（Condition）

先调 `list-entities` 获取可用条件实体（apiName、apiType、source、metadata），然后组装 condition：

```json
{
  "and": [
    {"rules": [{"apiName": "__touch_point", "apiType": "TEXT", "source": "SYSTEM", "relation": "IN", "values": ["LIVE_CHAT"]}]},
    {"rules": [{"apiName": "__intent_ids", "apiType": "TEXT", "source": "SYSTEM", "relation": "IN", "values": [9750]}]}
  ]
}
```

`__intent_ids` 的 values 字段使用 `int(intent_id)`，不要用字符串。

## 动作类型（Action）

| 类型 | 说明 | 必需字段 |
|------|------|---------|
| `AGENT` | 路由到指定 Agent | agentId |
| `TEMPLATE_REPLY` | 回复固定模板 | templateId |
| `TEMPLATE_REPLY_AND_TRANSFER_TO_AGENT` | 模板回复后转人工 | templateId |
| `AI_REPLY` | AI 生成回复 | - |
| `AI_REPLY_AND_TRANSFER_TO_AGENT` | AI 回复后转人工 | - |
| `DO_NOTHING` | 不做任何操作 | - |

## API

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 可用实体列表 | GET | `/api_v2/gpt/project/{pid}/entities` | 获取 apiName、apiType、source |
| 创建策略 | POST | `/api_v2/gpt/project/{pid}/strategy?v4=true` | 必须带 v4=true |
| 更新策略 | PUT | `/api_v2/gpt/project/{pid}/strategy/{id}?v4=true` | 必须带 v4=true |
| 启用/禁用策略 | - | - | 通过 toggle-strategy CLI |

## CLI

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-entities --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-strategies --pretty

${PLUGIN_ROOT}/bin/cxclaw-launcher api create-strategy \
  --data '{"name":"退款路由","trigger":"MESSAGE","condition":{...},"action":{"type":"AGENT","agentId":2270}}'

${PLUGIN_ROOT}/bin/cxclaw-launcher api update-strategy --id <strategy_id> \
  --data-file /workspace/state/solvea-kit/update_strategy.json

${PLUGIN_ROOT}/bin/cxclaw-launcher api toggle-strategy --id <strategy_id> --enable
${PLUGIN_ROOT}/bin/cxclaw-launcher api toggle-strategy --id <strategy_id> --disable
```

## 原则

- 创建/更新策略接口参数由 SolveaClient 自动处理，无需额外传参。
- `__intent_ids` 的 values 字段使用 int，不要使用字符串形式。
- 配置策略后必须执行 `toggle-strategy --enable` 启用，否则不生效。
- 测试 CHAT_FLOW 时，必须先创建策略将意图路由到 Agent，再通过 chat 接口发送匹配消息测试；不能用 `metadata.specified_agent_id` / `metadata.specified_agent_data` 这类强制 agent 路由直接测试 CHAT_FLOW Agent。
- Agent 构建、工具配置和 CHAT_FLOW 图不在本文档维护，走 `agent-builder`。
