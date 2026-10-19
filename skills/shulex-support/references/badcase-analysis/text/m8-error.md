# M8：系统异常模块

**信号**：`type=STOPPED` + `reason=SYSTEM_ERROR` / `reason=AGENT_TIMEOUT` / 任意模块未捕获异常

---

## 核心逻辑

系统异常无特定职责模块，全局 AOP 捕获未处理异常后返回 `STOPPED + SYSTEM_ERROR`。

常见来源：
- LLM 调用超时或连接失败（agentAlgClient 异常）
- SINGLE_AGENT / MULTI_AGENT：`invokeAiAgent` 调用失败
- CHAT_FLOW 节点执行失败
- 外部 HTTP 工具接口异常
- 数据库/缓存访问失败
- NPE 或其他运行时异常

---

## Log 层（直接查，无 Config 层）

```bash
# 全局 ERROR 日志（最直接）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND severity:"ERROR"' --line 20
# → 类名、方法名、exception message、堆栈首行

# SINGLE_AGENT LLM 调用失败
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"call ai agent stream" AND rest:"call fail"' --line 5

# MULTI_AGENT LLM 调用失败
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"multiAgent, call fail"' --line 5

# CHAT_FLOW 特有错误（精确字符串）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND (rest:"chatflow return error" OR rest:"chatflow run failed" OR rest:"chatflow no finished data")' \
  --line 10

# 兜底：afterChat botChatEvent（包含 request + response 完整数据）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"afterChat[.*botChatEvent"' --line 5
```

**精确错误日志字符串**：
```
executeAgent[<chatId>]: call ai agent stream, currentLoopCount={}, call fail, reason={}
                                                                    ↑ SINGLE_AGENT（STOPPED）
executeAgent[<chatId>]: multiAgent, call fail, reason={}
                                               ↑ MULTI_AGENT（STOPPED）
executeAgent[<chatId>]: chatflow return error, msg={}
executeAgent[<chatId>]: chatflow run failed, errorObj={}            ← errorObj 含 node_id、node_title
executeAgent[<chatId>]: chatflow no finished data
executeAgent[<chatId>]: chatflow unknown finishdata type={}
chatflow callTool error chatId={}                                   ← 工具调用异常
aiReply[{}]: aiContent is empty                                     ← LLM 返回空 → TO_AGENT
```

**AGENT_TIMEOUT 特殊说明**：SINGLE_AGENT 超过 10 轮未返回 → `STOPPED + AGENT_TIMEOUT`，无独立 ERROR 日志，需看每轮 `call ai agent stream` 记录是否有进展（→ M5）。

---

## 分析要点

**从 ERROR 日志定位**：
- 哪个类（class）的哪个方法（method）抛了异常？
- exception message 是什么？
- 是否有 `reason` 字段？（SINGLE_AGENT/MULTI_AGENT call fail 的 reason 字段说明具体失败原因）

**SINGLE_AGENT / MULTI_AGENT call fail 的 reason 字段**：
- `codeMsg`：LLM 服务返回的错误码/描述
- `errorReason`：内部错误标识
- 通常是 LLM 服务端异常（rate limit、timeout、服务不可用）

**从 botChatEvent 兜底**：
- `afterChat[chatId]: botChatEvent={}` 包含完整 request + response
- `response.type`、`response.reason`、`response.reasonDesc` 直接可读

---

## 常见根因与建议

| 根因 | 建议 |
|------|------|
| LLM 服务异常（call fail） | 看 `reason` 中 codeMsg；检查 LLM provider 状态；通常是临时性 |
| SINGLE_AGENT AGENT_TIMEOUT | 看每轮 arguments 是否有进展；是否陷入工具调用死循环（→ M5） |
| CHAT_FLOW 节点执行失败 | 从 `errorObj.node_id` 定位节点，看节点配置和工具调用 |
| 外部 HTTP 工具接口异常 | 检查接口地址、鉴权、网络连通性（→ M6） |
| NPE / 配置字段缺失 | 从堆栈首行定位代码位置，检查相关配置是否完整 |
| agentAlgClient 连接失败 | 检查 ChatFlow/AI Agent 服务状态 |
