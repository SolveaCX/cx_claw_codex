# TOOL

## 功能概述

调用单个外部 HTTP 工具拿结构化数据。下游可接 IF_ELSE；工具定义的 actionStatus 与当前业务分支完全一致时，也可直接按 actionStatus 出边。

它把调用、入参、结果和状态暴露在画布上。action status 是工具声明的离散结果；当判断依赖多个返回字段、系统字段或布尔组合时，可将 TOOL 输出交给 IF_ELSE。TOOL 本身不生成对客回复，也不等待用户。

## 创建前审计

写 TOOL 节点前必须从真实工具定义建立审计表，不只看工具名或旧 prompt：

| 审计项 | 来源 | 用途 |
|---|---|---|
| `requestParam.items[]` | 工具详情 | 决定 `input_params`，包括必填、类型、object/array 子字段 |
| `responseParam.items[]` | 工具详情 | 决定下游 IF_ELSE / CODE / HUMAN_REVIEW 可引用的字段路径 |
| `actionStatuses[]` | 工具详情 | 决定是否可以 `enable_action_status=true` 以及每个状态下游 |

只有 actionStatus 名称、工具合同和目标业务分支三者能对齐时，才用工具状态出边。若流程按返回体字段、系统变量、多个字段组合或代码计算结果判断，应该 `TOOL -> IF_ELSE` 或 `TOOL -> CODE -> IF_ELSE`。

chatflow 运行时的 TOOL 节点只读取画布上的 `inputParams`、`tool.id/type/enableActionStatus` 后调用工具；节点实现本身不会根据工具详情自动补齐必填参数，也不会猜测缺失参数该绑定哪个变量。工具入参是否完整、TOOL 出参 path 是否存在，必须用真实工具详情和 compile / validate 审计完成。不要只离线编译后就认定工具绑定正确。

## 创建方式

```json
{
  "key": "lookup_order",
  "type": "tool",
  "tool_id": 12345,
  "input_params": [
    {"name": "orderId", "variableSelector": {"system": {"category": "Order", "path": [3248, 3249]}}, "varType": "string"}
  ]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| tool_id | 必填，项目已有工具 id |
| tool_type | 工具插件类型，默认 `EXTERNAL_HTTP_CALL`；维护已有非 HTTP 工具时保留实际类型 |
| input_params[].name | 参数名，与工具定义一致 |
| input_params[].text | 固定值 |
| input_params[].variableSelector | 参数来源 |
| input_params[].children | object 参数的子字段绑定 |
| input_params[].varType | 类型 |
| enable_action_status | 是否按工具 action status 出边 |

## Edges

- 默认 `SOURCE`。
- `enable_action_status=true` 时，TOOL 直接从工具原始结果 `raw_result["__status"]` 取状态名作为 `output_handle`；缺失时运行时抛 `ToolInvokeError("Tool result missing action status")`。
- 状态名使用工具定义中的原始名称。
- 只有工具定义的 actionStatus 完整、互斥且覆盖当前业务分支时才直接出边；否则用 `SOURCE -> IF_ELSE` 或 `SOURCE -> AGENT` 解读工具结果。
- 多个 actionStatus 不能因为都“失败”就合并到同一个转人工节点；只有责任、用户轮次、回复合同、模板/NO_REPLY 和转人工原因一致时才共享下游。

## Output Variables

TOOL 成功后写入的节点输出形态是：

```json
{
  "name": "<tool node title>",
  "tool_result": "<parsed_result>"
}
```

下游引用工具出参时读取的是 `tool_result`，按返回结构逐层写路径：`{"tool":"lookup_order","path":["order","shipping_method_no"]}`。嵌套字段不能写成单段 `field: "order.shipping_method_no"`。

工具状态不是普通出参。判断状态名用：

```json
{"variableSelector": {"tool_status": "lookup_order"}}
```

完整 selector 是 `["TOOL", "<tool_node_id>", "ACTION_STATUS_NAME"]`，运行时会读取最近一次该 TOOL 结果中的 `tool_result.__status`。如果工具直接出边和下游 IF_ELSE 都依赖状态，必须确认工具解析后的 `parsed_result` 也保留 `__status`，否则直接出边可用但 IF_ELSE 读不到状态。

判断返回体字段才用：

```json
{"variableSelector": {"tool": "lookup_order", "path": ["order", "shipping_method_no"]}}
```

不要在未确认 `responseParam` 的情况下凭经验写 `status`、`data.status`、`result.status`。如果只有 actionStatus 可用，就按 actionStatus 出边或在 IF_ELSE 中引用 `tool_status`。

## Resource Dependencies

```bash
npx --yes @shulex/cxclawctl@latest api list-plugins --pretty
npx --yes @shulex/cxclawctl@latest api list-ai-fields --pretty
```

`--bind-tool-params` 只是辅助，不是业务决策来源：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/chatflow/chatflow_builder.py compile ... --bind-tool-params
```

实际行为：
- 仅在 `queryAiFields` 可用时生效；字段服务不可用时会被跳过并产生 warning。
- 只尝试自动绑定工具定义中 `required=true` 且 `source=LLM` 的参数。
- 只按内置常见字段名映射或变量系统字段直接同名匹配生成 `SYSTEM` selector。
- 找不到匹配字段时只打印 warning，不会生成 `open_questions`，也不会替你判断是否该新建变量或改成 QUESTION。
- 已经写在 `input_params` 里的参数不会被覆盖。

因此不能依赖 `--bind-tool-params` 自动解决业务字段绑定；它只能作为最后的辅助补齐和校验。

## 限制

- 必填参数必须绑定变量系统字段或固定值。
- 找不到明确来源的必填参数时，不得按名称相似自动绑定现有变量；必须输出 `open_questions`，让用户选择新建变量、使用哪个现有变量、改为 `QUESTION(VARIABLE)` 收集、转人工或不迁该自动化。
- chatflow 运行时解析 `inputParams` 时，如果顶层参数解析结果是 `None`，会直接从 `tool_args` 中省略该参数；这不是“已绑定空值”。必填参数不能依赖运行时发现，必须在创建审计和 validate 阶段拦住。
- 固定 `text` 绑定到 `varType=object/array` 时，运行时会 `json.loads(text)`；必须写合法 JSON，不能写 Python 字面量或自然语言描述。
- `variableSelector` 绑定到 `varType=array` 时，如果取到的是非 list，运行时会包装成单元素数组；这只是兼容机制，不代表可把单个商品字段当成完整商品数组使用。
- array/object 参数（如 `itemVos`、`refundProducts`、`productList`）必须确认数组元素结构和同一商品记录的一致性；无法保证时不要把单个商品字段拼成数组执行补发/退款，优先询问或转人工。
- validator 会按真实 `requestParam.items[]` 检查所有 required 参数；object 参数会递归检查 `objectItems`，完整缺失路径会类似 `address.line1`。
- array 参数在 validator 中按叶子处理；它只校验该数组参数本身是否配置，不理解数组元素是否来自同一商品记录。涉及补发/退款商品数组时必须人工审计来源一致性。
- 工具定义里 `source=CUSTOMIZE` 或非 LLM 的必填参数不会被 `--bind-tool-params` 自动补齐；需要根据工具定义和业务语义手写 `text` 或明确 selector，并通过真实 validate 校验。
- object 参数的必填子字段必须逐层写入 `children`，字段名与工具定义 `objectItems[].name` 一致。运行时会把 object 的 `children` 解析成 `{child.name: child_value}`。
- array 参数的 `children` 在运行时会被解析成列表元素；数组元素是对象时，子项也必须按 object 结构显式表达，不能只把多个平铺字段塞进同一个 array。
- `input_params[].name` 必须和工具定义 `requestParam.items[].name` 一致；object 子字段同理。
- `input_params[].variableSelector` 引用上游变量，支持 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW`。
- `input_params[].variableSelector` 不使用工具状态 `ACTION_STATUS_NAME`；需要按工具状态分支时用 TOOL 自身的 actionStatus 出边或下游 IF_ELSE。
- `input_params[].variableSelector` 只能引用当前 TOOL 的上游节点输出；validator 会拒绝引用同级、下游或未连通节点。
- `AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- EXTRACT selector 第三段是 extract `id`，不是 `name`。
- TOOL 只负责调用，不负责解释复杂结果。
- 使用 actionStatus 前必须确认状态定义完整、互斥，且能准确覆盖当前业务分支；否则使用工具结构化输出接 IF_ELSE。

## Common Checks

- 多个下游业务节点需要由 IF_ELSE 或 actionStatus 明确承接。
- 参数名与工具定义一致。
- 引用变量时确认被引用节点在当前 TOOL 上游。
- object 参数的必填子字段都已绑定，不只绑定父级 object。
- compile 前确认每个必填参数都有来源说明：`SYSTEM` 字段、上游 TOOL/CODE/QUESTION 输出、固定值，或已记录为阻塞 open question。QUESTION(VARIABLE) 的结果通常先进入变量系统字段，再用 `SYSTEM` selector 绑定工具入参。
- compile 报缺必填参数时，先回到参数审计表补来源，不要临时绑定同名/近似变量来压过校验。
- validate 报 `references invalid TOOL output path` 时，先核对真实 `responseParam.items[]`；数组字段不能继续向内写子路径，object 字段才可逐层引用。
