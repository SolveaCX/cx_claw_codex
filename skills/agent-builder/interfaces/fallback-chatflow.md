# Fallback Chatflow Interface

公开能力：按调用方给定的业务目的创建兜底 CHAT_FLOW agent。

## Boundary

调用方只声明兜底 agent 的业务目的和输出要求，不维护 CHAT_FLOW graph、节点字段或构图规则。

首版允许由 `agent-builder` 的 chatflow reference 创建，不强制提供固定脚本。

## Input

```json
{
  "name": "Fallback Agent",
  "purpose": "out_of_scope_reply",
  "complexity": "simple_reply | guided | custom",
  "reply_text": "",
  "language": "zh-CN",
  "brand_name": ""
}
```

## Output

调用方需要得到一份创建记录：

```json
{
  "agent_id": 12345,
  "agent_name": "Fallback Agent",
  "agent_type": "CHAT_FLOW",
  "creation_record_path": "/workspace/outputs/agent-builder/fallback_chatflow_<ts>.json"
}
```

## Guarantees

- 创建结果必须是 CHAT_FLOW agent。
- 输出必须包含可回填给其他能力的 `agent_id`。
- 创建完成后需要回读验证 agent 存在。

## Non-guarantees

- 兜底 graph 的节点结构不对调用方暴露。
- 当前是否通过 reference 或脚本创建不对调用方保证。
- 后续仍通过 `agent-builder chatflow deploy` 创建兜底 Chatflow，调用方 interface 不变。
