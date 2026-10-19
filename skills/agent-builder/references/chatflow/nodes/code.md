# CODE

## 功能概述

执行少量确定性数据转换。不要用它承载业务 prompt、复杂流程或外部接口调用。

## CODE 节点使用方法

适合字段标准化、文本拆分/合并、日期/数字转换、从已存在结构化输入提取稳定字段、或者做字段的类型转换，更换变量名等。

```json
{
  "key": "normalize_platform", "type": "code",
  "inputs": [{"field_name": "raw", "variable_selector": {"tool": "lookup", "path": ["platform"]}}],
  "source_code": "value = str(inputs.raw).strip().lower()\nreturn {'platform': value}",
  "outputs": [{"field_name": "platform", "field_type": "String"}]
}
```

声明 inputs/outputs；所有路径都 `return`；只做纯计算，不访问网络/文件，不写长循环；异常数据返回空值/false/说明字符串交给下游判断。不要在 CODE 内写整段业务流程。chatflow 会把 `sourceCode` 包装成一个内部函数执行，函数体里已存在局部变量 `inputs`。

CODE 只处理已经存在的上游值。写代码前先确认每个 input 的 selector 和每个 output 的下游用途；缺少 input 来源时先用 `QUESTION(VARIABLE)`、`VARIABLE_PROCESS` 或 TOOL 补齐，不要在代码里编造默认业务值。

## 创建方式

```json
{
  "key": "normalize_order",
  "type": "code",
  "inputs": [
    {"field_name": "order_no", "variable_selector": {"system": {"category": "Order", "path": [3248, 3249]}}}
  ],
  "source_code": "return {\"normalized\": str(inputs.order_no).strip()}",
  "outputs": [
    {"field_name": "normalized", "field_type": "String"}
  ]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| inputs[].field_name / fieldName | 输入变量名；编译后完整 graph 使用 `fieldName` |
| inputs[].variable_selector / variableSelector | 输入来源；编译后完整 graph 使用 `variableSelector` |
| source_code / sourceCode | Python 函数体代码；编译后完整 graph 使用 `sourceCode`，运行时已有 `inputs` 局部变量 |
| outputs[].field_name / fieldName | 输出名；编译后完整 graph 使用 `fieldName` |
| outputs[].field_type / fieldType | `String` / `Number` / `Boolean` / `Object` / `Array`；编译后完整 graph 使用 `fieldType` |

## Input / Output 引用规则

CODE 的 input 是对上游 selector 的命名包装。运行时会先逐个解析 `inputs[].variableSelector`，再把结果组成顶层 `inputs` 字典；`source_code` 内优先通过 `inputs.<field_name>` 访问：

```json
{
  "key": "build_refund_payload",
  "type": "code",
  "inputs": [
    {"field_name": "order_id", "variable_selector": {"system": {"category": "Order", "path": [3248, 3249]}}},
    {"field_name": "tool_status", "variable_selector": {"tool_status": "lookup_order"}},
    {"field_name": "items", "variable_selector": {"tool": "lookup_order", "path": ["order", "items"]}}
  ],
  "source_code": "items = inputs.items if isinstance(inputs.items, list) else []\nreturn {\"item_count\": len(items), \"has_items\": len(items) > 0}",
  "outputs": [
    {"field_name": "item_count", "field_type": "Number"},
    {"field_name": "has_items", "field_type": "Boolean"}
  ]
}
```

下游 IF_ELSE / TOOL 引用 CODE 输出时，只能引用 `outputs[].field_name`。CODE 节点运行成功后写入的节点输出形态是：

```json
{
  "exec_result": {"<fieldName>": "<assembled value>"},
  "stdout": "<print output or null>"
}
```

变量选择器的 `CODE` 分支只读取 `exec_result`，不读取 `stdout`。

```json
{"variableSelector": {"code": "build_refund_payload", "field": "has_items"}}
```

source 简写会编译为完整 selector：

```json
["CODE", "<code_node_id>", "has_items"]
```

运行时只支持完整 selector 写成 `["CODE", "<code_node_id>"]` 或 `["CODE", "<code_node_id>", "fieldName"]`。IF_ELSE / TOOL 入参需要具体字段时应使用三段式。不能引用代码里的临时变量、局部对象路径或未声明字段，也不能写 `["CODE", node_id, "obj", "field"]`。需要输出对象/数组时，将整个对象声明为一个 output；若下游必须判断对象内部字段，优先在 CODE 中拆成稳定的标量 outputs。

CODE input 的 selector 同样必须引用当前 CODE 的上游 predecessor。比如要整理工具返回数组，图上必须先有 `TOOL -> CODE`，然后 CODE input 才能引用该 TOOL 输出；不能跨图引用未连通工具。

## Edges

通常 `SOURCE`；作为终止转换节点时可无出边。

## Resource Dependencies

输入引用变量系统字段或上游节点时，先确认对应 id / key。

## 输出映射规则

`return` 的值会按 `outputs` 组装到 `exec_result`：

- `return dict`：按 `outputs[].fieldName` 取同名 key；缺失 key 输出 `None`；多余 key 会被忽略。
- `return list/tuple`：按 `outputs` 顺序一一映射，长度必须和 output 数量完全一致。
- 单 output 时可以直接 `return` 标量，运行时会自动包装成 `{fieldName: value}`。
- 多 output 时不能返回标量。
- 没有 output 的 CODE 配置会被校验拒绝；不要写“只 print 不 return”的代码节点。
- 输出类型按 `fieldType` 校验：`String` 要求字符串但会把数字/布尔转成字符串；`Number` 接受 int/float 或可转数字字符串，但拒绝 bool；`Boolean` 必须是 bool；`Object` 必须是 dict；`Array` 必须是 list。
- 输出值为 `None` 时允许通过类型校验，交给下游 IF_ELSE 用 `EMPTY` / `NOT_EMPTY` 或兜底逻辑处理。

## 限制

- 必须声明 `source_code` 和至少一个 output。
- 每个 input 必须有 `field_name` 和 `variable_selector`。
- `inputs[].variable_selector` 引用上游变量，支持 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW`。
- 判断工具状态映射时可用 `["TOOL", "<tool_node_id>", "ACTION_STATUS_NAME"]`。
- TOOL 出参 selector 会按真实 plugin `responseParam` 校验：object 字段可下钻，array 字段按叶子处理；需要遍历数组时，把整个数组作为 CODE input，在 `source_code` 内处理。
- `AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。
- EXTRACT selector 第三段是 extract `id`，不是 `name`。
- 每个 output 必须有 `field_name` 和 `field_type`。
- input/output 的 `field_name` 必须是合法 Python 标识符，不能重复，不能使用 Python 关键字，不能使用 `inputs`、`__inputs__`、`__chatflow_entry__`、`__builtins__` 或 dunder 形态。
- `source_code` 必须在所有执行路径上 `return`。
- 输入通过 `inputs.<field_name>` 访问；不要直接使用裸变量名。
- 使用 `inputs.<field_name>` 时，`field_name` 必须已经在 `inputs` 中声明；校验器会检查这种直接属性引用。动态下标访问不适合作为迁移默认写法，因为字段缺失更难在编译期暴露。
- 返回值优先使用 dict，key 必须对应 output 的 `field_name`；单输出可返回标量，多输出必须返回 dict 或等长 list/tuple。
- 返回 dict 不能包含下游要依赖但未在 `outputs` 声明的业务字段；validator 只允许下游引用 `outputs[].fieldName` 中存在的字段。
- 需要给 TOOL 组装 object/array 入参时，必须先确认工具 `requestParam` 子字段结构；无法确认 item identity 或数组元素结构时输出 `open_questions`，不要在 CODE 中把多个不相关字段拼成可执行补发/退款参数。
- 允许 import 只有 `math`、`json`、`datetime`、`re`。
- 可用内置函数仅限常见纯函数：`len/range/enumerate/zip/min/max/sum/sorted/reversed/any/all/abs/round/map/filter/list/dict/set/tuple/str/int/float/bool/isinstance/print`。
- 使用 `for` / `while` / `if` / 列表、字典、集合推导等普通控制流，但必须保证所有路径最终 `return`。
- 禁止 `eval/exec/compile/__import__/open/input/globals/locals/vars/dir/getattr/setattr/delattr/breakpoint/type`。
- 禁止 async/yield/class、dunder 访问、危险属性访问（如 `.sys/.codecs/.builtins/._os`）。
- 运行时提供常见异常类（如 `Exception`、`ValueError`、`KeyError`、`IndexError`、`TypeError` 等），但迁移代码不要依赖异常驱动主流程；遇到异常业务数据时优先返回空数组、空对象、`false` 或说明性字符串，由下游节点判断。
- 不要主动 `raise` 作为业务分支；主动抛错会使 CODE 节点失败，而不是进入某个下游 case。
- 运行时有超时、代码长度、输入大小、stdout、结果大小、内存限制；不要生成大循环、大对象或大量日志。
- 不调用外部 HTTP；外部调用用 TOOL 或 AGENT with tools。

## Common Mistakes

- 把 input 字段当成同名 Python 变量使用；输入应从 `inputs` 对象读取。
- 用 extract `name` 当 selector 字段；应使用 extract `id`。
- 用 CODE 写业务判断大流程。
- 忘记声明输出字段。
- 写 `result = {...}` 但没有 `return`。
- `return {"status": ...}` 后下游引用 `code.status`，但 outputs 没有声明 `status`。
- 以为可以引用 `["CODE", node_id, "obj", "field"]`；当前 CODE selector 只校验到 output 字段名，复杂对象内部字段应拆成单独 output。
- 以为 CODE 可以直接读取全局变量、当前会话或工具完整结果；必须通过 `inputs` 显式传入。
- 用 CODE 伪造缺失的订单、地址、商品数组、退款商品或工具状态；这些属于业务数据缺口，应询问用户或转人工。
- 用 `raise Exception(...)` 表示业务分支；这会导致 CODE 执行失败，不会生成可供 IF_ELSE 判断的 output。
- 依赖 `print` 结果给下游使用；下游 CODE selector 只读 `exec_result`，不读 `stdout`。
- 用 `os/requests/pandas/open` 读文件或调接口。
- 通过代码节点做网络请求、文件处理、长文本生成或复杂业务决策。
