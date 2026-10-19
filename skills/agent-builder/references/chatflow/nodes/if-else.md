# IF_ELSE

## 功能概述

对已有变量、工具输出或系统字段做确定性条件判断。多个 `cases` 按顺序表达 `if / elif`，未命中时的 `FALSE` 表达 `else`；它不理解自然语言，只比较已经存在的结构化值。

它不理解自然语言，而是读取已经存在的结构化值，按 cases 的条件组合输出对应 handle；没有命中时走 FALSE。适合枚举、存在性、数值、日期和布尔判断，也可表达多个条件的 AND/OR 组合。

## Source 选择

IF_ELSE 的第一步是确定判断对象，不是先写 case 名称：

| 要判断的内容 | source JSON 简写 | 完整 graph selector | 说明 |
|---|---|---|---|
| 工具 actionStatus | `{"tool_status": "lookup_order"}` | `["TOOL", "<tool_node_id>", "ACTION_STATUS_NAME"]` | 运行时读取最近一次 TOOL 输出的 `tool_result.__status`；不是 `status` 字段 |
| 工具返回体字段 | `{"tool": "lookup_order", "path": ["order", "shipping_method_no"]}` | `["TOOL", "<tool_node_id>", "order", "shipping_method_no"]` | 运行时从 `tool_result` 开始逐层取值；路径必须来自 `responseParam.items[]` |
| 变量系统字段 | `{"system": {"category": "Order", "path": [3248, 3249]}}` | `["SYSTEM", "Order", 3248, 3249]` | 完整 selector 只能是 3 段或 4 段；第三/第四段是字段 id |
| CODE 输出 | `{"code": "normalize_items", "field": "item_count"}` | `["CODE", "<code_node_id>", "item_count"]` | 运行时从 `exec_result[fieldName]` 读取；field 必须是 CODE `outputs[].fieldName` |
| LLM 输出 | 用完整 selector | `["LLM", "<llm_node_id>", "text"]` 或 `["LLM", "<llm_node_id>", "structured_output", "..."]` | text 固定三段；structured_output 可继续下钻 |
| AGENT 输出 | 无推荐简写；用完整 selector | `["AGENT", "<agent_node_id>", "param_name"]` | param 必须来自已连通 nextStep 的 `params[].name` |

常见错误是把工具 actionStatus 当作普通字段写 `{"tool":"x","field":"status"}`，或把返回体字段当成 actionStatus。除非 `responseParam` 真实存在 `status` 字段，否则不能写 `status`。

当工具详情里同时出现普通返回字段和 actionStatus 时，先判断业务语义：
- 旧流程按“工具执行动作状态”走分支，且状态名与 actionStatus 对齐：选 `tool_status` / `ACTION_STATUS_NAME`。
- 旧流程按订单状态、物流单号、退款金额、商品数组等返回体内容判断：选 TOOL 出参 path。
- 需要对多个字段组合、数组长度、对象字段归一化后判断：先 `TOOL -> CODE`，再在 IF_ELSE 里选 CODE output。
- 需要判断变量系统字段，例如订单号、邮箱、国家、附件字段：选 SYSTEM，不要伪造 TOOL `status`。

validator 会检查 selector 引用的节点必须是当前 IF_ELSE 的上游 predecessor；不能引用同级、下游或未连通节点。需要先经过 CODE 转换时，边必须是 `TOOL -> CODE -> IF_ELSE`，再在 IF_ELSE 中引用 CODE 输出。

## 创建方式

```json
{
  "key": "check_order_status",
  "type": "if_else",
  "cases": [
    {
      "id": "SHIPPED",
      "conditions": [
        {"variableSelector": {"tool": "lookup_order", "path": ["order", "shipping_method_no"]}, "comparisonOperator": "NOT_EMPTY"}
      ]
    }
  ]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| cases[].id / name | 出边 handle |
| cases[].logicalOperator | `AND` / `OR`，默认 `AND` |
| conditions[].variableSelector | 判断字段 |
| conditions[].comparisonOperator | 比较操作 |
| conditions[].value | 比较值 |

## Edges

每个 case 一条边，另加 `FALSE`。运行时按 `cases` 顺序依次评估，命中第一个 case 后用该 `case.id` 作为 `output_handle` 和路由 handle；全部未命中时用 `FALSE` handle，并在输出数据里记录 `matched_case_id: "else"`。

## Resource Dependencies

判断变量系统字段先查 `list-ai-fields`；判断工具结果需确认上游 TOOL 输出字段。

变量系统字段在进入 CHAT_FLOW 前由 `shulex-gpt` chat 链路统一抽取，因此可直接用 IF_ELSE 判断。嵌套字段必须使用 `list-ai-fields` 返回的完整 id 路径，例如 `["SYSTEM", "Order", 3248, 3249]`。

判断工具字段前必须查工具详情的 `responseParam` 或可验证的完整 graph 输出配置；只看到旧 prompt 里的“状态”“成功”“失败”不等于有可引用字段。判断代码输出前必须读取 CODE 节点的 `outputs`，不能引用 `source_code` 中临时变量。

完整 graph 校验会用 plugin metadata 构建 TOOL 可用出参路径：object 子字段可继续下钻，array 字段按叶子处理。若工具没有 metadata 或离线校验，路径错误可能不会被发现；涉及真实工具分支时必须带项目资源执行 compile / validate。

## 限制

- 所有 case 和 `FALSE` 必须连边。
- 至少有一个 case；每个 case 至少有一个 condition。
- 每个 condition 必须有 `variableSelector` 和 `comparisonOperator`。
- 除 `EMPTY` / `NOT_EMPTY` 外，condition 必须有非空 `value`。
- `varType: boolean` 的 `value` 推荐使用前端保存的字符串 `"true"`、`"false"`；运行时也能把布尔值或 `"1"/"yes"` 转成 true，但不要依赖非前端格式。
- `varType: array` 只能做空值或长度比较；运行时不支持 `CONTAINS` / `NOT_CONTAINS`，会抛节点执行错误。需要判断数组元素内容时先用 CODE 拆出稳定 output。
- `variableSelector` 引用上游变量，支持 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW`。
- 判断工具状态映射用 `["TOOL", "<tool_node_id>", "ACTION_STATUS_NAME"]`。
- `AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- TOOL 输出 selector 不加 `"output"` 层。
- TOOL 嵌套输出使用分段 `path`，例如 `{"tool":"lookup_order","path":["order","shipping_method_no"]}`；不要写点号字段。
- TOOL 数组出参按叶子字段处理，不要直接写 `["items", "0", "sku"]` 或假设 validator 会理解数组元素路径；需要拆数组时先用 CODE 输出稳定标量。
- EXTRACT selector 第三段是 extract `id`，不是 `name`。
- SYSTEM selector 不能省略嵌套字段的父级 id。
- CODE selector 可以是 `["CODE", node_id]` 或 `["CODE", node_id, fieldName]`；IF_ELSE 判断具体字段时必须使用三段式，并且 `fieldName` 存在于 CODE outputs。运行时不支持 `["CODE", node_id, "obj", "field"]` 这种继续下钻。

## Common Mistakes

- 用 IF_ELSE 判断自然语言语义。语义判断应使用 `AGENT(next_steps)` 或 `INTENT`。
- 忘记 `FALSE` 兜底。
- 引用不存在的 TOOL 输出路径，例如未确认 `responseParam` 就写 `["status"]`。
- 需要判断工具 actionStatus 却写成普通 TOOL 字段；应使用 `tool_status` 或完整图的 `ACTION_STATUS_NAME`。
- 引用 CODE 中没有声明为 output 的临时变量；下游只能读 `outputs[].field_name`。
- 引用不是当前 IF_ELSE 上游的 TOOL / CODE 节点；需要先补边或重排图。
- boolean 条件把 `value` 写成 `["true"]`、布尔值或其它文本；前端标准格式是字符串 `"true"`、`"false"`，数组会被运行时整体字符串化并可能造成反向误判。
- 用 `["EXTRACT", node_id, "order_no"]` 引用提取结果；应使用提取项 id。
