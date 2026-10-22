# Badcase 复测

本场景用于根据历史 ChatId 重放客户问题，验证修复，并比较原会话与新测试的 AgentAction。不要生成预期字段，也不要让模型自拟预期后再据此判定。

## 读取原会话

执行：

```bash
npx --yes cxclaw@latest api get-transcript \
  --chat-id <historicalChatId> \
  --pretty
```

从原会话中：

- 只提取客户 `USER` 消息，保持原顺序。
- 不重放原 AI、人工客服、系统或流程消息。
- 为每轮 USER 消息保留紧随其后的原 AgentAction，作为本地 baseline，仅用于测试后比较，不传入 `live_test`。
- 原会话发生转人工，或 AgentAction 为 `TO_AGENT`、`STOPPED`、`HUMAN_REVIEW` 后停止提取后续轮次。
- 记录原回复、Agent、意图、策略、工具调用、节点路径、图状态和 handoff 信息。

## 确定请求参数

按以下优先级确定：

- `agentId`：用户显式指定的目标 Agent优先，否则使用原 AgentAction 实际调用的 Agent。
- `botId`：当前 CXClaw 请求携带的 Bot ID 优先；没有时使用原会话 Bot ID；仍无法确定才询问。
- `flowVersion`：用户显式版本优先，否则工具入参省略；`live_test` 会通过 `chatflow/queryGraph/latest` 取得当前用户草稿或最新发布版本，再将实际版本明确写入测试请求。复测修复时不要默认使用历史旧版本。
- `touchPoint`：用户显式值优先，其次使用原会话 touchPoint，仍缺失时默认 `LIVE_CHAT`。
- `metadata`：经用户确认后，只复制完成测试确实需要的业务字段。

不要复制旧 ChatId、运行状态、内部路由字段或工具固定注入的 metadata。

开始复测前，若用户未明确 metadata 策略，必须提醒并确认：是否固定复用原会话 metadata（例如订单号、用户邮箱、商品或渠道），还是不带 metadata 验证默认路由。只复制用户确认需要的字段，不能默认带入或自行补值。

## 调用 live_test

将提取出的全部客户问题组成一个固定 `case`，一次调用 `live_test`：

```json
{
  "agentId": 2584,
  "touchPoint": "LIVE_CHAT",
  "case": {
    "caseId": "historical-chat-id",
    "turns": [
      {"message": "第一轮客户问题"},
      {"message": "第二轮客户问题"}
    ]
  },
  "metadata": {
    "order_number": "A-1001"
  }
}
```

不要把 baseline、原 AI 回复、原 ChatId 或预期字段放入工具参数。多轮问题必须在同一个 `case.turns` 中提交，由工具内部维护新 ChatId。

## 读取新会话

工具完成后，获取结果中的新 ChatId，再执行一次：

```bash
npx --yes cxclaw@latest api get-transcript \
  --chat-id <newTestChatId> \
  --pretty
```

按 USER 消息顺序将新 AgentAction 与原 baseline 对齐。不要仅根据 `live_test.messages` 的回复文本判断是否修复，因为完整路由、工具和节点信息在会话记录中。

## 对比结论

逐轮比较：

1. AgentAction 类型和 handoff 是否变化。
2. 实际 Agent、意图、策略是否变化。
3. 工具是否新增、减少、报错或得到不同关键结果。
4. Chatflow 节点路径和图状态是否变化。
5. AI 回复的业务结论、关键事实和下一步建议是否发生显著变化。
6. 原问题是否仍复现、已修复、出现新问题，或证据不足需要人工判断。

回复文本不同不自动代表失败；但回答结论、订单状态、承诺、路由、工具行为或节点路径发生明显变化时必须指出。

如果新测试出现系统错误、工具错误、失败节点或没有最终 AgentAction，先给出测试结论和新 ChatId，再主动引导进入 `shulex-support` 的 Agent 会话诊断场景。用户已经要求定位或修复时，直接使用新 ChatId 衔接排查。
