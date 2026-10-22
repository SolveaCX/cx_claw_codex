# TRANSFER_TO_HUMAN

## 功能概述

终止当前流程并转人工。支持直接无回复转人工、节点内模型生成话术后转人工、节点内固定模板后转人工。

TRANSFER_TO_HUMAN 表达的是客服会话接管。一旦执行，当前 chatflow 不再继续走后续节点。它不同于 `HUMAN_REVIEW` 的流程内审核，也不同于 `AGENT.next_steps` 的流程内跳转。

## 创建方式

```json
{"key": "handoff", "type": "transfer"}
```

```json
{"key": "handoff_with_template", "type": "transfer", "transfer_type": "TEMPLATE", "template_id": 12345}
```

## 创建参数

| 字段 | 说明                                                    |
|------|---------------------------------------------------------|
| transfer_type | `NO_REPLY` / `PROMPT` / `TEMPLATE`，默认 `NO_REPLY`     |
| prompt | PROMPT 类型时使用的模型生成提示词                         |
| template_id | TEMPLATE 时必填                                         |
| ai_field_ids | PROMPT 可注入的变量系统字段 id 数组                    |
| disable_prev_node_results | PROMPT 是否不注入前序节点结果，默认 false             |
| explain | 写入人工接管结果的说明；缺省时使用节点标题             |

## Edges

无出边。普通默认无回复转人工可直接用 `$transfer`。

## Resource Dependencies

TEMPLATE 转人工先查模板：

```bash
npx --yes cxclaw@latest api list-templates --keyword "handoff" --pretty
```

## 限制

- 不要使用 AGENT `transferToHumans` 字段。
- 确定性转人工路径应显式节点化为 `TRANSFER_TO_HUMAN` 或 `$transfer`。
- 如果转人工由 AGENT 在多轮判断中自主决定，按 `agent.md` 在 prompt 中插入标准 `transferHuman`
  LibraryBlock；联网 compile 会把真实 `TRANSFER_TO_HUMAN` 系统插件 ID 加入该 AGENT 的 `usedPlugins`，
  但独立 `TRANSFER_TO_HUMAN` 节点本身不写插件，也不要把转人工伪装成 AGENT `next_steps`。
- `NO_REPLY` 不需要 `prompt` 或模板。
- `PROMPT` 必须有 `prompt`。
- `PROMPT` 可用 `ai_field_ids` 注入变量系统字段；普通 `[[var:...]]` 模板不在此节点渲染。需要上游节点输出时，先桥接到 SYSTEM 字段，不能默认增加普通 REPLY 节点改变终止语义。
- `TEMPLATE` 必须有 `template_id`。
- 有不同回复内容的转人工路径不要合并成同一个 transfer 节点。
- 不同业务职责、不同 action status 或不同 transfer reason 不要全部连到同一个 `$transfer`。
- 如果确实要共享一个 transfer，必须在设计说明中写明相同职责、相同用户轮次、相同回复合同和合并证据。
- `PROMPT` 表示该转人工节点自身先由模型生成一段对客话术，然后执行转人工；它不是前置分类节点。
- `TEMPLATE` 表示该转人工节点自身先发送固定模板，然后执行转人工。
- 转人工节点的 PE 是面向模型的pe，作用是用来让模型生成面向客户的回复。

## Common Mistakes

- 把“先回复再转人工”直接连 `$transfer`，导致回复丢失。
- 多个不同模板共用一个 transfer 节点。
