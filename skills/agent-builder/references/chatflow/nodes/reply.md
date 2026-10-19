# REPLY

## 功能概述

发送一段话给用户，然后沿唯一 `SOURCE` 出边继续后续流程。`PROMPT` 由 LLM 按提示词生成回复；
`TEMPLATE` 使用固定模板；`DYNAMIC_TEMPLATE` 先渲染上游变量，再把结果按会话语言翻译后发送。

REPLY 不是只能做终端。凡是业务语义是“先对用户说一段固定/可生成的话，再继续进入同一个后续路径”，
都可以用 REPLY 表达。它不负责判断分支，也不调用工具；分支判断应放在上游或下游的 INTENT /
IF_ELSE / QUESTION / AGENT 中。

REPLY 发送的是用户可见内容。需要知识检索回答时用 `RAG_REPLY`；需要内部摘要、改写或抽取时用
`LLM`；需要发送后立即人工接管时用 `TRANSFER_TO_HUMAN` 的回复配置。

## 创建方式

```json
{"key": "confirm_platform", "type": "reply", "reply_type": "TEMPLATE", "template_id": 12345}
```

```json
{"key": "explain_policy", "type": "reply", "prompt": "Explain the return policy politely and concisely."}
```

```json
{"key": "reply_with_order", "type": "reply", "prompt": "Answer using the OrderNumber field if present.", "ai_field_ids": [2742]}
```

```json
{
  "key": "reply_with_summary",
  "type": "reply",
  "reply_type": "DYNAMIC_TEMPLATE",
  "template_content": "Order summary: [[var:{\"code\":\"summarize_case\",\"field\":\"summary\"}]]"
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| prompt | `reply_type` 缺省或为 `PROMPT` 时使用 |
| reply_type | `PROMPT` / `TEMPLATE` / `DYNAMIC_TEMPLATE`，默认 `PROMPT` |
| template_id | `TEMPLATE` 必填 |
| template_content | `DYNAMIC_TEMPLATE` 必填；完整 graph 中可嵌入 `[[var:[...]]]` selector 模板，source 可使用 selector 简写 |
| ai_field_ids | PROMPT 可用的变量系统字段 id 数组；完整 graph 字段为 `aiFieldIds` |
| use_long_memory | PROMPT 是否注入长记忆，默认 false |
| disable_prev_node_results | PROMPT 是否不注入前序节点结果，默认 false |

## Edges

仅 `SOURCE` 单出边。运行时如果 REPLY 有出边，chatflow 后端会注入 `WAIT -> USER_INPUT -> 原下游`，也就是先把回复发给用户并等待下一轮用户输入，再继续进入原下游节点。

如果只是发送最终话术后结束，连 `$finish`；如果发送话术后转人工，连 `$transfer` 或显式 `TRANSFER_TO_HUMAN`。不要让 REPLY 承担分支判断。

如果语义是“发送模板/话术后继续路由到同一个确定目标”，REPLY 表达这段发送动作：

```text
上游分支 -> REPLY(TEMPLATE 或 PROMPT) -> 后续处理节点
```

如果发送后要按用户回答分支，不要让 REPLY 直接多出边；改用 `REPLY -> QUESTION`，由 QUESTION
收集用户回复并分流。

## Resource Dependencies

使用模板前先查模板库：

```bash
cxclawctl api list-templates --keyword "platform" --pretty
```

模板查询底层走 `/project/{projectId}/templates/filter`。

## 限制

- `TEMPLATE` 必须有 `template_id`。
- `DYNAMIC_TEMPLATE` 必须有非空 `template_content`，不使用 `template_id` 或 `ai_field_ids`。
- 动态模板的完整 selector 例如 `[[var:["CODE","<code_node_id>","summary"]]]`；只能引用当前 REPLY 的上游输出。可用 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW` 或 `NODE` selector，工具状态可用 `ACTION_STATUS_NAME`。
- `DYNAMIC_TEMPLATE` 是确定性的变量渲染与翻译，不是让 LLM 重写模板内容。需要模型措辞时用 `PROMPT`。
- `PROMPT` 必须写生成要求，可以控制回复内容、语气、必须包含/避免的信息；不要只写用户可见的一句话。
- `aiFieldIds` 必须是变量系统字段 id 数组，例如 `[2742]`。
- 字段服务不可用时不要新增未知 `aiFieldIds`；先用固定话术、模板，或复用已有 graph 中已确认字段 id。
- 需要上游节点输出稳定进入 prompt 时，先用 VARIABLE_PROCESS 赋值到 SYSTEM 变量系统字段，再在 `ai_field_ids` 引用该字段。
- 后端会把 `ai_field_ids` 对应字段作为额外系统上下文注入；上游节点结果也可能作为历史节点结果注入，但不要把它当成稳定 prompt 变量。
- REPLY 不承担路由、工具调用、条件判断。
- REPLY 只有一个下游；需要多个下游时，必须由相邻路由节点承担分支。
- REPLY 中写“请提供/请上传/请确认”只是发送提示，不表示已收集或已确认；必须连接 QUESTION 才会等待用户输入。
- `PROMPT` / `TEMPLATE` / `DYNAMIC_TEMPLATE` 各自只使用对应字段；不要在普通 PROMPT 中写 `[[var:...]]`。

## Common Mistakes

- 把固定话术写进 `PROMPT`。固定话术优先用模板；需要模型生成时才用 PROMPT。
- 用 REPLY 问用户选项并期待分支。需要分支时用 `QUESTION(USER_REPLY)`。
- 因为 REPLY 后还要继续流程，就误以为不能用 REPLY；REPLY 可以发送后接一个确定下游。
- 想在 prompt 稳定使用上游输出，却没有先赋值到变量系统字段。
- 动态模板把 selector 写成普通文本，或在 `template_content` 中引用下游/未连通节点。
