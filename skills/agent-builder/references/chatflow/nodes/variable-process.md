# VARIABLE_PROCESS

## 功能概述

提取上下文变量、给变量系统字段赋值，或先提取再赋值。也是把上游节点输出转换成 AGENT / REPLY prompt 可读变量系统字段的桥接节点。

`shulex-gpt` 会在进入 CHAT_FLOW 前抽取已配置的变量系统字段。这些字段进入图后已可读取；如果需要从 `AttachmentSummary` 等字段中继续提取新参数，仍可使用本节点。

VARIABLE_PROCESS 不向用户发送消息，也不等待用户输入；它处理的是当前上下文里已经存在的文本、变量或上游节点结果。需要向用户补收字段时用 `QUESTION`。

## 创建方式

```json
{
  "key": "process_variables",
  "type": "variable_process",
  "additional_data": [{"node": "previous_reply"}],
  "variables": [
    {"alias": "order_no_value", "name": "order_no", "describe": "Order number", "type": "string"}
  ],
  "assignments": [
    {"id": "assign_order", "operation": "OVER_WRITE", "source": ["SELF", "order_no_value"], "target": [["SYSTEM", "Custom", 2742]]}
  ]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| variables / extracts | 提取项，source 写 name/describe/type；需要后续引用时加 alias，compile 后 alias 会变成完整 graph 的 UUID `id` |
| assignments | 赋值项，必填 id/operation/target |
| additional_data | 提取时额外拼接的上游变量选择器数组；source 可写 selector 简写，完整 graph 为 `additionalData: [["SYSTEM",...], ["TOOL",...], ["NODE",...]]` |
| use_chat_history | 是否使用历史 |

## Edges

仅 `SOURCE`。

## Resource Dependencies

赋值到变量系统字段前查：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-ai-fields --pretty
```

## 限制

- 至少有 extract 或 assignment。
- source extract 必须有 `name/describe/type`，需要后续引用时必须有 `alias`；已有完整 graph 必须有 `id/name/describe/type`，其中 `id` 通常是前端或 builder 生成的 UUID。
- extract `name` 格式 `/^(?!\d)[A-Za-z0-9_-]{1,64}$/`。
- assignment 必须有 `id/operation/target`。
- `CONSTANT` 操作必须有非空 `source`。
- `additional_data` 只能引用上游 `SYSTEM` / `TOOL` / `CODE` / `AGENT` / `HUMAN_REVIEW` / `NODE`，用于补充提取上下文；不引用 `SELF`。
- `additional_data` 不使用工具状态 `ACTION_STATUS_NAME`；`AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- `assignments[].source` 在 `OVER_WRITE` 时可引用上游变量，或用 `["SELF", "<extract_alias>"]` 引用本节点刚提取的值；compile 后会替换成 extract UUID `id`。
- `assignments[].source` 不使用工具状态 `ACTION_STATUS_NAME`。
- `assignments[].target` 只能是 `SYSTEM` 变量二维数组，如 `[["SYSTEM", "Custom", 2742]]`。
- AGENT / REPLY prompt 需要稳定使用上游输出时，先在这里把 `TOOL` / `EXTRACT` / `CODE` / `AGENT` selector 赋值到 `SYSTEM` 变量系统字段，再让下游节点通过 `ai_field_ids` 读取。
- 下游引用本节点提取结果时用 `["EXTRACT", "<this_node_id>", "<extract_id>"]`；第三段是 extract `id`，不是 `name`。
- 收集用户输入优先用 `QUESTION(VARIABLE)`。
- 已有变量系统字段可直接用 `SYSTEM` selector 读取；需要二次提取、转换或赋值时再使用本节点。

## Common Mistakes

- 新建图继续使用即将下线的 `VARIABLE_EXTRACT` / `VARIABLE_ASSIGNMENT`。
- 只想问用户信息却用变量处理节点。
- 用 extract `name` 引用输出，例如 `["EXTRACT", node_id, "order_no"]`；source 用 `alias`，完整 graph 用 UUID `id`。
- 需要给 AGENT / REPLY prompt 使用的上游输出，没有先赋值到 SYSTEM 变量系统字段。
