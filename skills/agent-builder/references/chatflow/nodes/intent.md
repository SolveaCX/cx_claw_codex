# INTENT

## 功能概述

根据上下文识别用户意图并分流。意图直接定义在节点内，不调用系统意图创建接口。

INTENT 是业务分类路由节点，等价于“把客户表达归入有限客户意图，再进入对应处理流程”。每个 intent
都应该代表一个可解释的客户意图和后续 SOP 路径，不是技术状态名的包装，也不是把所有分支汇入一个
泛化 AGENT 的前置分类壳。

## INTENT 全局 prompt 与历史

`prompt` 默认 `null`。只有需求明确需要配置该节点的单独pe时才生成，并在生成后询问用户是否启用；用户拒绝则保留 `prompt: null`。每个 intent 仍须有清晰 `desc` 和独立可解释的下游路径。`history_round_limit` 默认 `null`，仅在用户明确指定历史范围时配置。

## 创建方式

```json
{
  "key": "intent_router",
  "type": "intent",
  "prompt": "Classify the user's request using the intent boundaries below. Choose the most specific matching intent; use OTHER when unclear or out of scope.",
  "intents": [
    {"id": "order_issue", "name": "Order_Issue", "desc": "User asks about an order."},
    {"id": "refund_request", "name": "Refund_Request", "desc": "User wants a refund."}
  ]
}
```

## 创建参数

| 字段                 | 说明                                                                                                     |
|----------------------|----------------------------------------------------------------------------------------------------------|
| intents[].id         | 必填，作为出边 handle                                                                                    |
| intents[].name       | 意图名，默认英文 ASCII                                                                                   |
| intents[].desc       | 新定义意图必填，描述识别的规则、边界                                                                     |
| intents[].intentId   | 可选，复用已有系统意图                                                                                   |
| intents[].examples   | 可选示例话术                                                                                             |
| prompt               | 可选的意图节点全局识别提示（PE）。未明确需要时为 `null`；仅在确有跨意图边界、优先级或范围约束时配置      |
| use_chat_history     | 是否结合历史，默认 true                                                                                  |
| history_round_limit  | 可选，编译为 `historyRoundLimit`；默认 `None/null`（交由后端默认策略），`-1` 表示全部历史，正数表示最近 N 轮（1-10）。 |

## Edges

每个 intent 一条边，另加 `OTHER`。

`intents` 可写对象数组。edges 的 `on` 可使用 intent `id` 或 `name`，最终按 `id` 生成 handle。复用系统意图时写 `intentId`；新定义意图时必须写清楚 `name` 和 `desc`。

每个客户意图默认必须进入不同的处理路径。多个 intent 共享同一个下游只在以下条件全部满足时允许：

- 客户意图虽然表达不同，但业务处理动作完全一致；
- 需要收集的字段、调用工具、模板/回复合同、转人工原因和终态完全一致；
- `mapping_explanations` 写明共享理由。

否则不能把多个 intent 都连到同一个 generic AGENT 或同一个泛化处理节点。遇到多个意图当前看起来
处理相似时，优先拆出共享的后置子流程：`INTENT -> 不同业务入口 -> 共享工具/回复/转人工节点`，
而不是直接让所有 intent 指向同一个大 AGENT。

## Resource Dependencies

如要复用已有意图，先查意图：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-intents --pretty
```

## 限制

- 每条意图必须有 `name + desc` 或 `intentId`。
- name 不能重复。
- 每个 intent handle 和 `OTHER` 都必须连边。
- 每个 intent 的出边目标必须能读出对应客户意图的处理路径；无证据不要全部汇入同一个 AGENT。
- `useChatHistory` 完整 graph 默认为 true；source 通常不用改。

## Common Mistakes

- 写 `description` 字段。source JSON 使用 `desc`。
- 只写 name 不写 desc，导致后端校验“意图描述为空”。
- 把分类结果全部接到同一个处理 AGENT，导致意图节点只剩形式分类，没有实际 SOP 分流。
- 用技术字段或工具状态当 intent 名称；INTENT 应描述客户意图，结构化字段判断用 IF_ELSE 或 TOOL status。
