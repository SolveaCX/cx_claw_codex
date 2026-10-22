# QUESTION

## 功能概述

向用户提问。`USER_REPLY` 用于按用户选择分支；`VARIABLE` 用于收集变量系统字段。

它是画布中明确的“等待用户”节点：发送提问后流程暂停，收到新消息后才通过对应 reply handle 或收集结果继续。适合信息补全、确认、否认和有限选项；不承担外部调用或复杂推理。

## 创建方式

```json
{
  "key": "ask_platform",
  "type": "question",
  "mode": "USER_REPLY",
  "question": "Please choose a platform: TikTok, Amazon, or Shopify.",
  "replies": ["TikTok", "Amazon", "Shopify"],
  "max_rounds": 3
}
```

```json
{
  "key": "collect_email",
  "type": "question",
  "mode": "VARIABLE",
  "question": "Please provide your email.",
  "variables": [2744]
}
```

```json
{
  "key": "ask_platform_with_template",
  "type": "question",
  "mode": "USER_REPLY",
  "question_type": "TEMPLATE",
  "question_template_id": 12345,
  "replies": ["TikTok", "Amazon", "Shopify"]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| mode | `USER_REPLY` / `VARIABLE` |
| question_type | `PROMPT` / `TEMPLATE`，默认 `PROMPT` |
| question | `PROMPT` 提问文案 |
| question_template_id | `TEMPLATE` 提问模板 id |
| replies | USER_REPLY 的选项 |
| variables | VARIABLE 模式收集的变量系统字段 ids |
| max_rounds | 最大追问轮数，默认 5 |
| condition | VARIABLE 多字段收集完成条件：`AND` / `OR`，默认 `AND` |
| use_chat_history | 识别/收集时是否使用会话历史，默认 true |

## Edges

- USER_REPLY：每个 reply 一条边，另加 `OTHER`。
- VARIABLE：仅 `SOURCE`。

`replies` 可写字符串数组，也可写对象数组：

```json
[
  {"id": "TIKTOK", "name": "TikTok"},
  {"id": "AMAZON", "name": "Amazon"}
]
```

对象写法更稳定；edges 的 `on` 可使用 reply `id` 或 `name`，最终按 `id` 生成 handle。字符串写法会用清洗后的名称作为 `id`。

## Resource Dependencies

VARIABLE 模式先查变量系统字段：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-ai-fields --pretty
```

## 限制

- USER_REPLY 的 `replies[].name` 必须能清洗为 ASCII。
- USER_REPLY 每个 reply 必须有非空 `id` 和 `name`，`name` 不能重复。
- USER_REPLY 必须连完全部 reply 和 `OTHER`。
- `PROMPT` 必须有 `question`；`TEMPLATE` 必须有 `question_template_id`。
- 必须至少配置 `variables` 或 `replies`。
- VARIABLE 模式必须配置 `variables`；USER_REPLY 模式必须配置 `replies`。
- QUESTION 自身负责多轮追问和等待用户输入；不要用图层回环实现追问。
- “请提供/请上传”只有在 QUESTION 中才构成真实收集；如果需要先解释收集原因，可用 `REPLY → QUESTION`，不能用 REPLY 代替 QUESTION。

## Common Mistakes

- 想要分支却用 REPLY。
- 忘记 `OTHER` 兜底边。
- 为多轮追问画环；应使用 `max_rounds`。
- 模板提问写成 `reply_type=TEMPLATE`。QUESTION 使用 `question_type=TEMPLATE`。
