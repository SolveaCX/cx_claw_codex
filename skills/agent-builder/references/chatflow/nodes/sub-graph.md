# SUB_GRAPH

## 功能概述

调用另一个 CHAT_FLOW。当前后端 parser 禁止 SUB_GRAPH 有出边，因此它是终止型子流程调用节点。

## 创建方式

```json
{
  "key": "run_return_flow",
  "type": "sub_graph",
  "target_agent_id": 2496,
  "context_turn_limit": 5
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| target_agent_id | 被调用的 CHAT_FLOW agent id |
| agent_id / agentId / targetAgentId | source JSON 可用别名，最终写成 `targetAgentId` |
| context_turn_limit | 1-10，默认 5 |

## Edges

禁止出边。

## Resource Dependencies

先查可用 agent：

```bash
npx --yes cxclaw@latest api list-agents --pretty
```

## 限制

- 无出边。
- 必须有入边。
- `target_agent_id` 必填，且必须是可转成整数的 CHAT_FLOW agent id。
- `context_turn_limit` 必须在 1-10 之间。
- 如果子流程后还要回主流程，不适合 SUB_GRAPH；改用 AGENT next_steps 或拆回主流程。

## Common Mistakes

- 给 SUB_GRAPH 连出边，后端 parser 会失败。
