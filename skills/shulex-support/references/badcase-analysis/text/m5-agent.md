# M5：Agent 执行模块

**职责代码**：`AgentService.executeAgent()`

---

## 三种 Agent 类型

策略 action 为 `AGENT` / `FLOW_AGENT` 时，进入 `executeAgent()`。根据 `agent.type` 分三个分支：

| 类型 | 特征 | 执行方式 |
|------|------|---------|
| `CHAT_FLOW` | 图形化节点流程 | `agentAlgClient.invokeChatFlow()` 流式 |
| `MULTI_AGENT` | 多 Agent 图路由 | `agentAlgClient.invokeAiAgent()` 流式（单次） |
| `SINGLE_AGENT`（else） | 单 Agent 循环调用 | `agentAlgClient.invokeAiAgent()` 流式循环（最多 10 次） |

**MAX_TURN_EXCEED**：在进入分支前检查：
- 条件：`currentAgentTurn > maxInvokeCount`（默认 30）
- 结果：`TO_AGENT + MAX_TURN_EXCEED`
- **无日志**，仅在会话记录目标回复的 `reason` 中体现

---

## CHAT_FLOW 分支

### 核心流程

```
agentAlgClient.invokeChatFlow(flowRequest, debug, flowResponse -> {
  switch (flowResponse.eventEnum) {
    CHAT_STARTED  → 记录 prepareTimeMillis
    NODE_STARTED  → 存 runInfoList（后续写入 chatflow_run_info）
    NODE_FINISHED → 存 runInfoList（含 node_id、status、out_handle、outputs、elapsed_time）
    MESSAGE_DELTA → 流式推送内容片段
    MESSAGE       → 处理 text（AI 回复）/ tool_request / tool_response
    CHAT_FINISHED → 存 finishedData（status、error、handoff、graph_finished）
  }
})
```

### finishedData.status 映射

| status | 结果 | 备注 |
|--------|------|------|
| `success` | `MESSAGE` 或 `NOTHING` | graph_finished=true 时加 AGENT_HAS_FINISHED reason |
| `failed` | `STOPPED`（或 `TO_AGENT`） | ToolInvokeError / GraphNodeMissingError → TO_AGENT |
| `transfer_to_human` | `MESSAGE` 或 `TO_AGENT` + handoff | reason 来自 handoff.reason |

### 信号判断

会话记录的 `context.ext.chatflow_run_info` 已存储节点序列，**优先从这里分析**，通常不需要查日志：

| 信号 | 含义 |
|------|------|
| `graph_finished=false` 且对话结束 | 流程未到终止节点（缺少出边） |
| 节点序列与预期不符 | IF_ELSE/INTENT 走了错误分支 |
| `type=STOPPED` + status=failed | 看 error.node_id 和 error.name |
| `reason=MAX_TURN_EXCEED` | agentTurn > maxInvokeCount（无日志） |

### Log 层

```bash
# ChatFlow 错误日志（精确匹配）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND (rest:"chatflow return error" OR rest:"chatflow run failed" OR rest:"chatflow no finished data")' \
  --line 10
```

**精确错误字符串**：
```
executeAgent[<chatId>]: chatflow return error, msg={}
executeAgent[<chatId>]: chatflow run failed, errorObj={}    ← 含 node_id、node_title
executeAgent[<chatId>]: chatflow no finished data
executeAgent[<chatId>]: chatflow unknown finishdata type={}
```

---

## MULTI_AGENT 分支

### 核心流程

```
agentAlgClient.invokeAiAgent(aiAgentRequest, aiAgentResponse -> {
  switch (aiAgentResponse.eventEnum) {
    conversation_message_completed:
      type=answer       → isReturnUserMsg=true → 返回 MESSAGE
      type=function_call → isCallTool=true → 处理工具类型
    conversation_chat_failed → isCallFail=true → STOPPED
  }
})
```

### function_call 工具路由

| toolType | 处理 |
|----------|------|
| `TRANSFER_TO_HUMAN` | TO_AGENT 或 MESSAGE + handoff；reason 来自 reason_description |
| `FINISH_AGENT` | MESSAGE 或 NOTHING + AGENT_HAS_FINISHED |
| `KNOWLEDGE_AI_REPLY` | 调用 `aiReplyService.aiReply()`（→ M7） |

**转人工 reason 判断**（来自 `toolArgs.reason_description`）：
- `Lack of knowledge` → `LACK_OF_KNOWLEDGE`
- `Knowledge irrelevant` → `KNOWLEDGE_NOT_RELEVANT`
- `tool action` → `CALL_TOOL_STATUS_TO_HUMAN` 或 `HANDOFF_TOOL_STATUS`
- `llm invoke` → `CALL_AGENT_TRANSFER_TO_HUMAN`

### Log 层

```bash
# MULTI_AGENT 流式日志（含完整 aiAgentResponse，token 消耗大）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"multiAgent stream"' --line 20

# MULTI_AGENT 失败
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"multiAgent, call fail"' --line 5
```

**精确日志字符串**：
```
executeAgent[<chatId>]: multiAgent stream, aiAgentResponse={}
executeAgent[<chatId>]: multiAgent, call fail, reason={}
executeAgent[<chatId>]: multiAgent, call kb_reply fail, knowledgeAiReplyRes={}
```

---

## SINGLE_AGENT 分支

### 核心流程

```
while (currentLoopCount++ < 10):  // 最多循环 10 次
  agentAlgClient.invokeAiAgent(aiAgentRequest, response -> {
    conversation_message_completed:
      type=answer        → return MESSAGE（退出循环）
      type=function_call → callPluginId → 执行工具 → 追加 tool_response 消息 → 下一轮循环
    conversation_chat_failed → return STOPPED
  })

// 超过 10 轮未返回 → STOPPED + AGENT_TIMEOUT
```

### 工具调用类型

| pluginType | 处理 |
|------------|------|
| `EXTERNAL_HTTP_CALL` | 调用外部 HTTP 接口（→ M6） |
| `FINISH_AGENT` | 结束 Agent，返回模板回复 |
| `TRANSFER_TO_HUMAN` | 转人工（带话术或空） |
| `KNOWLEDGE_AI_REPLY` | 调用知识库（→ M7） |
| `PRODUCT_RECALL` | Shopify 商品检索 |
| `QUERY_SHOPIFY_ORDER` | 订单查询 |
| `LOGISTICS_17_TRACK` | 物流追踪 |

### Log 层

```bash
# SINGLE_AGENT 每轮调用（含完整请求，token 大，按需查）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"call ai agent,"' --line 10

# SINGLE_AGENT 工具调用结果
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"call tool, currentLoopCount"' --line 10

# SINGLE_AGENT 失败
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"call ai agent stream" AND rest:"call fail"' --line 5
```

**精确日志字符串**：
```
executeAgent[<chatId>]: call ai agent, currentLoopCount={}, aiAgentRequest={}
executeAgent[<chatId>]: call ai agent stream, currentLoopCount={}, aiAgentResponse={}
executeAgent[<chatId>]: call tool, currentLoopCount={}, pluginName={}, request={}, response={}
executeAgent[<chatId>]: call ai agent stream, currentLoopCount={}, call fail, reason={}
```

---

## Config 层

```bash
npx --yes @shulex/cxclawctl@latest api get-agent --id <agentId> --pretty
```

检查点：
- `agent.type`：确认是 CHAT_FLOW / MULTI_AGENT / SINGLE_AGENT
- `meta.maxInvokeCount`：MAX_TURN_EXCEED 阈值（默认 30）
- CHAT_FLOW：`meta.chatFlowGraph` 中的节点定义和边配置
- SINGLE_AGENT：`usedPlugins` 列表和 `prompt`
- MULTI_AGENT：`meta.multiAgentGraph` 中的子 Agent 配置

---

## 常见根因与建议

| 根因 | 建议 |
|------|------|
| MAX_TURN_EXCEED | 检查循环分支，确保有终止出口；或调大 `maxInvokeCount` |
| CHAT_FLOW graph_finished=false | 补充缺失的终止出边 |
| CHAT_FLOW chatflow run failed | 从 errorObj.node_id 定位失败节点 |
| SINGLE_AGENT AGENT_TIMEOUT（10轮用尽）| 检查是否陷入工具调用循环；看每轮的 aiAgentRequest 是否有进展 |
| SINGLE_AGENT call fail | 看 errorReason/codeMsg，通常是 LLM 服务异常（→ M8） |
| MULTI_AGENT call fail | 同上 |
| 转人工 reason 不符合预期 | 检查 TRANSFER_TO_HUMAN 工具的 reason_description 逻辑 |
