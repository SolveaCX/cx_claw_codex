# COLLECT_ORDER

## 功能概述

订单号收集专用兼容节点，用于维护已有电商客服订单场景。该节点即将下线，新建 CHAT_FLOW 默认不要使用。

新建订单号相关流程时，先确认变量系统是否已有订单号字段，再按业务合同组合：

- 只需要向用户要订单号：`QUESTION(VARIABLE)`，变量选择订单号字段。
- 已有订单号后要查订单或物流：订单查询 `TOOL`，工具 actionStatus 完整时直接按状态出边，否则接 `IF_ELSE` 判断结构化字段。
- 需要模型多轮判断订单问题、解释工具结果或选择下一步：`QUESTION(VARIABLE)` -> `AGENT(next_steps)`，必要时把订单查询工具绑定到 AGENT。
- 需要把上游结果稳定给 AGENT / REPLY prompt 使用：先用 `VARIABLE_PROCESS.assignments` 写入变量系统字段，再让下游通过 `ai_field_ids` 读取。

## 创建方式

```json
{"key": "collect_order", "type": "collect_order", "max_rounds": 5}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| max_rounds | 最大追问轮数 |
| collect_order_exception | 维护已有图时的异常回复数组；也接受 `collectOrderException`。每项含 `key`、`type=REPLY/TEMPLATE`、`reply` 或 `template_id` |

## Edges

通常 `SOURCE` 进入后续订单处理节点。

## Resource Dependencies

依赖项目启用订单相关变量系统字段。需要确认字段时查 `list-ai-fields`。

## 限制

- 仅用于维护已有图、复刻旧行为，或用户明确要求保留 `COLLECT_ORDER` 兼容节点。
- 新建图默认使用 `QUESTION(VARIABLE)` 收集订单号，不使用本节点。
- 失败路径通常由节点内部异常配置或后续兜底转人工处理。
- 维护已有异常配置时，每个异常项如果 `type=TEMPLATE` 必须有 `templateId`；否则必须有非空 `reply`。
- 和 QUESTION / AGENT 一样，运行时会等待用户输入；不要在图层手动画回环。

## Common Mistakes

- 新建图继续使用本节点，导致依赖即将下线能力。
- 只因为字段叫订单号就选择本节点；新图应优先走变量系统字段 + QUESTION / TOOL / IF_ELSE / AGENT。
- 在 source JSON 顶层写 `collectOrderException` 但没有放进 `config`，builder 不会自动识别。
