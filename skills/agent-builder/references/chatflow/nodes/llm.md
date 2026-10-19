# LLM

## 功能概述

纯模型处理节点。用于生成文本、总结、改写、抽取或把上游信息整理成后续节点可用的结果。

LLM 的结果供下游节点使用，不直接作为对客回复发送。它不等待用户、不调用外部工具，也不自己决定多条出边；需要这些能力时选择对应节点。

LLM 和 AGENT 的边界：

- `LLM`：只调模型，不调用外部工具，不使用 `next_steps` 做路由。
- `AGENT`：需要模型自主调用真实工具，或需要通过 `next_steps` 选择后续节点。
- `REPLY(PROMPT)`：只负责对用户发送一段回复，不用于生成内部中间结果。

## 创建方式

```json
{
  "key": "summarize_case",
  "type": "llm",
  "prompt": "Summarize the customer's issue and [[var:{\"system\":{\"category\":\"Order\",\"path\":[2742]}}]] for downstream decision making.",
  "history_round_limit": 3,
  "structured_output": {
    "enabled": true,
    "schema": {
      "type": "object",
      "properties": {
        "summary": {"type": "string"},
        "needs_handoff": {"type": "boolean"}
      },
      "required": ["summary"]
    }
  }
}
```

需要按上游图片/附件 URL 调模型时，开启 vision 并给出 URL selector：

```json
{
  "key": "inspect_attachment",
  "type": "llm",
  "prompt": "Describe the image for downstream processing.",
  "vision": {
    "enabled": true,
    "detail": "high",
    "media_selectors": [["SYSTEM", "Customer", 2780]]
  }
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| prompt | 模型处理指令；完整 graph 字段为 `promptTemplate` |
| history_round_limit | `0` 不带历史（默认）；`-1` 全部历史；正数带最近 N 轮 |
| use_long_memory | 是否注入长记忆，默认 false |
| vision.enabled | 是否附加图片输入，默认 false |
| vision.detail | `auto` / `low` / `high`，默认 `auto` |
| vision.media_selectors | 图片 URL 或 URL 数组的上游 selector；source 可写 `media_selectors` 或 `mediaSelectors` |
| structured_output.enabled | 是否要求模型按 JSON Schema 输出对象 |
| structured_output.schema | 开启时必填；根必须是 `type: object` 且有 `properties` |

## Edges

仅 `SOURCE` 单出边。LLM 不承担多分支路由；需要根据 LLM 结果分支时，后接 `IF_ELSE`、`INTENT` 或 `AGENT(next_steps)`。

## Output Variables

普通文本输出使用：

```json
{"variableSelector": {"llm": "summarize_case", "field": "text"}}
```

完整 graph selector：

```json
["LLM", "<llm_node_id>", "text"]
```

开启 `structured_output` 后，下游可以选择整个结构化对象或对象字段：

```json
{"variableSelector": {"llm": "summarize_case", "path": ["structured_output", "summary"]}}
```

完整 graph selector：

```json
["LLM", "<llm_node_id>", "structured_output", "summary"]
```

`structured_output` 未开启时，不得引用该路径。

## Resource Dependencies

变量模板通过标准 selector 读取上游 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW` 或 `NODE` 输出；图片 selector 必须在当前 LLM 的上游路径上，并在运行时解析成 HTTP(S) 图片 URL。

## 限制

- 必须有入边和 `SOURCE` 出边。
- `prompt` / `promptTemplate` 必须非空。
- 不绑定 `plugins` / `usedPlugins`；需要工具调用时用 AGENT 或 TOOL。
- 不配置 `next_steps`；需要模型选择下游时用 AGENT。
- prompt 会渲染 `[[var:[...]]]`。source 模板可用 selector 简写，例如 `[[var:{"code":"normalize_case","field":"summary"}]]`；编译后会替换为真实 node id。
- `vision.enabled=true` 时至少配置一个 `media_selectors`；每个 selector 的值必须在运行时解析为 HTTP(S) 图片 URL 或 URL 数组。
- `structured_output.enabled=true` 时 schema 根必须是 object，`required`（若存在）必须是数组。
- 旧 `aiFieldIds`、`modelId`、`outputs` / `outputVariables` 不属于当前 LLM 运行时契约；source 顶层使用这些字段会被 builder 拒绝，已有 graph 出现它们时 validator 只会警告其被忽略。

## Common Mistakes

- 用 LLM 调外部 HTTP 工具；应使用 AGENT with plugins 或 TOOL。
- 用 LLM 做多出口路由；应使用 AGENT(next_steps)、INTENT 或 IF_ELSE。
- 用 REPLY(PROMPT) 生成内部摘要，导致内容发给用户。
- 把 `summary` 直接写成 `['LLM', node_id, 'summary']`；当前运行时要么取 `text`，要么取 `structured_output` 路径。
