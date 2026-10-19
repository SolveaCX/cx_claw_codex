# HUMAN_REVIEW

## 功能概述

人工审核或人工补充信息节点。适合需要内部人员审批、确认、填充字段的流程。

HUMAN_REVIEW 是流程内的人工任务：审核或填写完成后，流程继续走出边。它不是客服会话转人工；
需要把当前用户会话交给人工客服时使用 `TRANSFER_TO_HUMAN` 或具备真实转人工能力的节点。

## 创建方式

```json
{
  "key": "review_refund",
  "type": "human_review",
  "method": "approval",
  "description": "Review whether refund can be approved."
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| method | `approval` / `fill` |
| description | 给审核人的说明；支持 `[[var:[...]]]` 上游变量模板 |
| fields | fill 模式需要填写的字段 |
| fields[].id | fill 字段 id；下游 selector 第三段使用该值，建议显式写稳定 id |
| fields[].fieldName | fill 字段名，必填 |
| fields[].fieldType | `text` / `attachment` / `options` |
| fields[].options | `options` 类型必填，不能为空且不能重复 |
| midway_message_strategy | 审核等待期间普通用户消息的处理：`ignore`（默认）/ `handle` |

## Edges

- approval：必须有 `AGREE` + `REJECT`。
- fill：仅 `SOURCE`。

## Resource Dependencies

fill 模式字段需确认业务字段定义。

## 限制

- approval 双出边必须完整。
- `description` 必填。
- `description` 可插入变量模板：`[[var:["CODE","<code_node_id>","summary"]]]`。
- 变量模板支持上游 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW`；工具状态可用 `["TOOL", node_id, "ACTION_STATUS_NAME"]`。
- `AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- fill 模式必须有 `SOURCE` 出边。
- fill 模式字段必须有 `fieldName`；`options` 字段必须配置选项。
- 下游引用 fill 结果用 `["HUMAN_REVIEW", "<this_node_id>", "<field_id>"]`。
- 如果后续要引用 fill 结果，`fields[].id` 必须稳定；不要用展示名当 selector。
- 不用它代替普通用户确认；用户确认用 QUESTION。

## Common Mistakes

- approval 忘记 REJECT 分支。
- description 变量模板引用非上游节点，或 EXTRACT 使用了 `name` 而不是 `id`。
- fill 字段没有稳定 `id`，导致下游无法可靠引用人工填写结果。
