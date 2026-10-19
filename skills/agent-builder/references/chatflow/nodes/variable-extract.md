# VARIABLE_EXTRACT

## 功能概述

变量提取兼容节点。仅用于兼容已有图；新建优先使用 `VARIABLE_PROCESS`。向用户收集信息优先使用 `QUESTION(VARIABLE)`。

## 创建方式

```json
{
  "key": "extract_params",
  "type": "variable_extract",
  "variables": [
    {"alias": "order_no_value", "name": "order_no", "describe": "Order number", "type": "string"}
  ],
  "additional_data": [{"node": "previous_node"}]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| variables / extracts | 提取项，source 写 name/type/describe；需要后续引用时加 alias，compile 后 alias 会变成完整 graph 的 UUID `id` |
| additional_data | 提取时额外拼接的上游变量选择器数组；source 可写 selector 简写，完整 graph 为 `additionalData: [["SYSTEM",...], ["TOOL",...], ["NODE",...]]` |
| use_chat_history | 是否使用历史 |

## Edges

仅 `SOURCE`。

## Resource Dependencies

引用上游节点输出或变量系统字段前，先确认对应 id。

## 限制

- 新建默认不用。
- 至少有一个提取项。
- source 每个提取项必须有 `name/describe/type`，需要后续引用时必须有 `alias`；已有完整 graph 必须有 `id/name/describe/type`，其中 `id` 通常是前端或 builder 生成的 UUID。
- `name` 格式 `/^(?!\d)[A-Za-z0-9_-]{1,64}$/`。
- `additional_data` 只能引用上游 `SYSTEM` / `TOOL` / `CODE` / `AGENT` / `HUMAN_REVIEW` / `NODE`，用于补充提取上下文。
- `additional_data` 不使用工具状态 `ACTION_STATUS_NAME`；`AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- 下游引用本节点提取结果时用 `["EXTRACT", "<this_node_id>", "<extract_id>"]`；第三段是 extract `id`，不是 `name`。
- 只想收集用户输入时，用 `QUESTION(VARIABLE)`。

## Common Mistakes

- 把用户提问收集误建成变量提取。
- 用 `NODE_OUTPUT` 或 extract `name` 写 selector；source 用 `alias`，完整 graph 用 UUID `id`。
