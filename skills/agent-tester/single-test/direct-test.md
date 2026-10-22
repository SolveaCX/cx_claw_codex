# 直接测试

用户只给 Agent 名称时，先查询并精确匹配：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-agents --pretty
```

默认使用定位的 `agentId`、当前 Bot ID、`LIVE_CHAT` 和当前用户草稿。用户说“随便测一下”但未给问题时，使用“你好，请介绍一下你可以帮助我处理哪些问题？”。

无论问题看起来是否简单，只要用户没有明确 metadata 策略，开始测试前都要询问一次：是否需要固定 metadata（例如订单号、用户邮箱、商品或渠道）？用户明确“不需要”才省略；不得默认空 metadata 或自行编造业务值。

明确的问题使用固定 `case`；一轮也使用 `case.turns`，多个已确定的问题放进同一次 `live_test` 调用：

```json
{
  "agentId": 2584,
  "case": {"turns": [{"message": "我的订单什么时候发货？"}]}
}
```

只有下一问必须根据前一轮 AI 回复决定时，使用探索式 `message`；继续同一对话时回传上次结果的 `chatId`，新的独立测试不要复用旧 ChatId。metadata 仅补经用户确认的真实业务字段，例如 `order_number` 或 `CustomerEmail`。

完成后按 `overview.md` 获取完整会话并分析 AgentAction。
