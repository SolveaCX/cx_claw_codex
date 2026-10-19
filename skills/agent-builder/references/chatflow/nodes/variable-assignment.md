# VARIABLE_ASSIGNMENT

## 功能概述

变量赋值兼容节点。仅用于兼容已有图；新建优先使用 `VARIABLE_PROCESS`。

## 创建方式

```json
{
  "key": "set_variables",
  "type": "variable_assignment",
  "assignments": [
    {"id": "assign-001", "operation": "OVER_WRITE", "source": ["TOOL", "lookup_order", "status"], "target": [["SYSTEM", "Custom", 2742]]}
  ]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| assignments[].id | 赋值项 id |
| assignments[].operation | `OVER_WRITE` / `CLEAR` / `CONSTANT` |
| assignments[].source | variableSelector 或常量 |
| assignments[].target | 目标 variableSelector 二维数组 |
| assignments[].forceOverride | 是否强制覆盖 |

## Edges

仅 `SOURCE`。

## Resource Dependencies

目标变量系统字段先查 `list-ai-fields`。

## 限制

- 新建默认不用。
- 每个 assignment 必须有 `id/operation/target`。
- `CONSTANT` 操作必须有非空 `source`。
- `OVER_WRITE` 的 `source` 引用上游变量，支持 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW`。
- `OVER_WRITE` 的 `source` 不使用工具状态 `ACTION_STATUS_NAME`；需要状态判断时用 IF_ELSE 或 TOOL actionStatus 出边。
- `AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- `target` 只能是 `SYSTEM` 变量二维数组，如 `[["SYSTEM", "Custom", 2742]]`。
- EXTRACT selector 第三段是 extract `id`，不是 `name`。
- 能迁成 `VARIABLE_PROCESS` 时优先迁移。

## Common Mistakes

- 新建图继续使用旧节点。
- 把 `source` 写成 extract `name`；应引用 extract `id`。
