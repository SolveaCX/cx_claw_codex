# M1：入口模块

**职责**：`BotController` 接收外部请求，统一转发到核心 chat 方法。

---

## 三条 HTTP 入口

所有入口最终汇聚至同一个核心方法：
`BotController.chat(Bot, Cactus, BotChatRequest, Consumer<StreamChatResponse>)`

| 入口 | 路径 | 触发方式 | Consumer |
|------|------|----------|---------|
| 同步 | `POST /bot/{botId}/chat` | 直接 HTTP | null |
| 流式 | `POST /bot/{botId}/chat/stream` / `chatStream` | SSE | lambda 写 SSE |
| 异步 | `POST /bot/{botId}/chat/async` | Kafka `@KafkaListener` | null |

异步路径：请求写 Kafka → `@KafkaListener` 消费 `BotChatAsyncTask` → 解包 → 调用同一 `chat()` 方法。

---

## 核心 chat() 方法

```
chat(Bot, Cactus, BotChatRequest, Consumer)
  → 初始化 thread context、chatAliveKey、performance profile
  → beforeChat()         ← 前置处理（权限、限流等）
  → bot.chat()           ← DefaultChatbot.chat()（主逻辑）
  → afterChat()          ← 同步票据、inbox、Prometheus 指标、perf 对象
```

**日志**：`CHAT[{}]: botId = {}, tenantId = {}, userId = {}, request = {}`

---

## HumanReview 旁路

在 `DefaultChatbot.chat()` 内，某些场景会跳过意图识别 + 策略匹配，**直接**进入 `agentService.executeAgent()`：

- **HumanReview 通过**：上一轮人工审核通过后，下一轮直接继续 Agent 执行
- **多轮 Agent 对话**：`useLastTurnParseResult=true` 时跳过 intent parse，复用上轮结果

HumanReview 旁路时，会话记录中无 `strategyName`，意图识别相关字段也不更新。

---

## 分析要点

- `HTTP_ASPECT` 是 SLS 中标记入口请求的关键字，用于定位 trace（见 `sls-query.md`）
- chatId 在 `rest` 字段里（不是 `ext_2`）
- **异步的 trace 在 Kafka 处断开**：生产端 trace_A 与消费端 trace_B 是两条独立 trace，但日志里有 `span` 字段可以跨 Kafka 串联（入口日志里的 span 值 = 消费端日志的 span 值）。M2~M8 的日志落在消费端 trace_B 下。详见 `sls-query.md` 的「异步路径」小节。
- `trace_A.timestamp` 与 `trace_B.timestamp` 差值 ≈ 消息排队时间，可用于判断消费积压
- `context.timing.__stage_time_total` 在 `afterChat()` 后保存，覆盖消费端端到端时间（异步时不含排队）
