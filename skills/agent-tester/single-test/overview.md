# 单 case 测试

这里的“单测”指一次测试一个 Agent。执行测试必须调用 `live_test.start`，不要通过脚本、临时 JSON 或本地状态文件自行调用 Chat 接口。

## 场景路由

| 场景 | 读取文档 |
|---|---|
| 用户指定 Agent、直接给问题、说“随便测一下”或要求继续探索 | `direct-test.md` |
| 用户给出历史 ChatId，要求复测 badcase、验证修复或比较变化 | `badcase-retest.md` |

先读本文件，再只读命中的场景文档。

## 两种调用方式

`case` 和 `message` 必须且只能提供一个：

- **固定用例**：传 `case.turns`，一次工具调用自动按顺序执行全部用户问题，并在内部复用同一个测试 ChatId。直接测试和 badcase 复测优先使用这种方式。
- **灵活探索**：传 `message` 执行一轮；继续同一对话时，把上次结果中的 `chatId` 原样传回。适用于 Agent 根据上一轮结果临时生成下一问。

## metadata 确认（单测必做）

用户没有明确说明 metadata 策略时，调用 `live_test.start` 前必须先提醒并确认：本次是否需要固定 metadata（例如订单号、用户邮箱、商品或渠道），以保证路由和工具上下文符合预期。用户确认不需要后，才省略 metadata；不要默认为空，也不要自行编造值。

## 参数契约

| 参数 | 必填 | 规则 |
|---|---|---|
| `agentId` | 是 | 目标 Agent ID。不要传名称。 |
| `botId` | 否 | 默认使用当前 CXClaw 请求携带的 Bot ID；只有当前请求没有 Bot ID 时才向用户确认。 |
| `flowVersion` | 否 | 工具入参默认省略；`live_test.start` 会调用 `chatflow/queryGraph/latest`，取得当前用户草稿或最新发布版本，再将实际版本明确写入测试请求。 |
| `touchPoint` | 否 | 默认 `LIVE_CHAT`，传入时统一使用大写值。 |
| `case` | 二选一 | `{ "caseId"?: string, "turns": [{ "message": string }] }`。至少一轮。 |
| `message` | 二选一 | 灵活探索模式的一条用户问题。 |
| `chatId` | 否 | 只在 `message` 模式继续上一轮测试对话时传入。固定 `case` 模式由工具内部维护。 |
| `metadata` | 否 | 经用户确认后，仅追加完成测试所需的业务上下文。 |
| `option` | 否 | 仅追加接口支持的其它选项。 |

调用示例：

```json
{
  "contextId": "<currentContextId>",
  "agentId": 2584,
  "botId": 80,
  "flowVersion": 17,
  "touchPoint": "LIVE_CHAT",
  "case": {
    "caseId": "optional-case-name",
    "turns": [
      {"message": "我的订单什么时候发货？"},
      {"message": "请帮我确认一下这个订单。"}
    ]
  },
  "metadata": {"order_number": "A-1001"},
  "option": {}
}
```

## 工具固定字段

不要在外部传入或覆盖以下字段：

- `option.debug`
- `option.verbose`
- `metadata.specified_agent_id`
- `metadata.specified_flow_version`
- `metadata.show_chat_flow`

`live_test.start` 会固定注入 `debug=true`、`verbose=true` 和三个路由 metadata。外部同名字段会被忽略，不能用它们改变测试目标。

CHAT_FLOW 草稿按当前用户隔离，版本号为 `-userId`。保存草稿不会递增 `meta.chatFlowVersion`；只有发布才生成新的正版本并更新该字段。因此 Agent 刚修改并保存草稿后，调用 `live_test.start` 时不用自行计算 `flowVersion`：工具会查询当前登录用户的草稿版本，并把该负数版本明确写入测试请求。若已发布且草稿已删除，工具会改用最新发布版本。只有明确回放某个历史或已发布版本时才在工具入参中显式传正版本号。

## 接口与进度

- `touchPoint=LIVE_CHAT` 时，工具内部只调用 `/api_v2/gpt/bot/{botId}/chat/stream`。
- 其它 touchPoint 只调用同步 `/api_v2/gpt/bot/{botId}/chat`。
- 两条路径不允许 fallback。流式路径提取 AI 增量和最终 AgentAction，不把完整 SSE events 放入工具结果。
- Live Test 卡片通过 `live_test.status` 的持久化快照展示用户问题、AI 流式回复、每轮状态和总进度。
- 不要因为工具已经展示实时进度而额外创建过程文件。

## 独立 case 串行约束

同一个 `contextId` 同时只允许一个 LiveTest。多个独立 case 即使都已确定，也必须逐个执行；禁止在同一批工具调用中发出多个 `live_test.start`。

每个独立 case 固定执行完整链路后再进入下一个：

```text
live_test.start
  → live_test.status，等待终态
  → live_test.transcript
  → 下一个 case 的 live_test.start
```

需要新 ChatId 隔离变量或上下文的场景分别执行独立 case。只有各轮属于同一段连续对话、需要复用 ChatId 时，才合并到一个 `case.turns`；不能为了减少调用而把互相独立的覆盖场景合并成多轮对话。

## 执行顺序与阶段反馈

1. 参数确定后，先用一句话说明目标 Agent、测试轮数和即将开始测试，再调用 `live_test.start`。
2. 使用 `live_test.status` 的 `afterRevision + waitMs` 等待终态；逐轮问题、回复和状态已经由 Live Test 组件展示，不要重复输出相同进度。
3. 测试结束后调用 `live_test.transcript` 获取完整执行详情。完成后说明完成轮数、成功或失败状态以及新 ChatId。
4. `live_test.transcript` 完成后再输出逐轮结论；不要把读取会话动作描述成新的测试轮次。
5. 有多个独立 case 时，完成当前 case 的第 1～4 步后再启动下一个；不得并发或抢先调用下一次 `live_test.start`。

`live_test.start` 入参会提供给用户查看，因此只传本次测试真正需要的 Agent、case/message、渠道和业务 metadata。不要把 baseline、原会话全文、分析草稿或内部固定字段塞入工具参数。

## 工具结果

`live_test.start` 返回 `testRunId` 和初始 `snapshot`；`live_test.status` 返回最新快照：

```json
{
  "testRunId": "ltr_xxx",
  "status": "succeeded",
  "chatId": "new-test-chat-id",
  "agentId": 2584,
  "flowVersion": -11302,
  "revision": 8,
  "turns": [
    {"index": 0, "user": "...", "assistant": "...", "status": "succeeded"}
  ]
}
```

失败时 `status=failed` 并包含 `error`。结果过大时可能出现 `truncated=true`，但 `chatId`、轮次和消息 ID 必须保留。

## 获取 AgentAction

工具完成后使用 `contextId + testRunId` 调用一次 `live_test.transcript`。不要为每一轮分别请求；一次完整会话已经包含所有消息及其执行过程。

## 输出结论

按轮次输出：

1. 用户问题和 AI 回复摘要。
2. AgentAction 类型、handoff、原因。
3. 实际 Agent、意图和策略。
4. 工具调用、工具错误和关键结果。
5. Chatflow 节点路径、图状态和耗时。
6. 与原 badcase 有基线时，指出路由、工具、节点和回复业务语义的显著变化。
7. 当前轮是成功、失败还是需要人工判断。

显著变化不自动等于失败，但必须明确指出。不要生成单测报告、过程文件或内部状态文件，直接在聊天回复中给出结构化结论。

当测试出现 `SYSTEM_ERROR`、图状态失败、工具报错或没有最终 AgentAction 时，展示当前测试 ChatId，并引导用户使用该 ChatId 进入 `shulex-support` 的 Agent 会话诊断场景。用户已经要求排查根因时可直接衔接，不要再次询问 ChatId。
