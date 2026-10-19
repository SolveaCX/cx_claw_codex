# M7：回复生成排查

M7 负责知识或业务上下文进入回复模型之后的 Prompt 组装、LLM 生成、格式化和检查。query、召回范围、排序、相关性和使用知识本身的问题转 M9；ChatFlow 内先按 M10 确认 graph 和节点。

## 当前主路径

普通 AI 回复的知识路径：

```text
AiReplyService.aiReply
  -> 构建 KnowledgeSearchReq
  -> qa-bot searchKnowledge
  -> contextContent / systemContent
  -> livechat: invokeGpt
     非 livechat: ShulexService docReply
  -> aiContent
  -> postHandle / product card / format
  -> 最终 AgentAction
```

qa-bot 当前会把最终使用的 QA、文档和商品组装到上下文，再进入生成链路。知识上下文为空时通常返回 `CONFUSED + LACK_OF_KNOWLEDGE`；生成内容为空时返回 `TO_AGENT + AI_CONTENT_IS_EMPTY`。

## 诊断顺序

1. 先按 M9 确认哪些知识 `effect=true`、哪些文档 chunk 或商品实际进入上下文。
2. 对比 `context.aiContent` 与最终 `messages[].content`。
3. 检查 Prompt/PE、知识上下文和历史消息是否同时包含冲突指令。
4. 若 `aiContent` 已正确，继续检查格式化、语言处理、输入输出检查和过滤。

| 现象 | 判断 |
|------|------|
| 使用知识错误或缺失 | M9 召回问题 |
| 使用知识正确，但 `aiContent` 结论错误 | Prompt、上下文冲突或生成不遵循 |
| `aiContent` 正确，最终回复错误 | 后处理、格式化或算法检查 |
| `filteredContent` 有值且 `metadata.real_time_inspection_tags` 或 reason 指向合规/质检 | 转 M12 |
| `filteredContent` 有值但没有质检信号 | 原回复被检查或拦截，结合 reason 转 M8/M11 |
| `AI_CONTENT_IS_EMPTY` | LLM 返回空、超时或异常，转 M8 |
| 回复语言错误 | 检查请求语言、模型输出和语言后处理 |

## Prompt 证据边界

- 会话记录保存的 Agent 历史、知识 tool response 和 `aiContent` 是重要运行事实。
- `currentPrompt` 为空时，读取会话记录的接口可能用当前 Agent Prompt 补填；它不一定是历史运行快照。
- `get-agent` 返回的是当前配置，不能单独证明目标轮次收到同一 Prompt。
- 要确认运行时完整 Prompt、PE 和知识上下文是否注入，查询该轮实际 LLM 请求日志。

因此只能在运行时请求得到验证后写“Prompt 已注入但模型未遵循”；否则应写“当前配置存在该规则，但运行时注入尚未确认”。

## 配置与日志

按调用路径读取当前 Agent 或 ChatFlow 图。ChatFlow 的 Agent/RAG/回复节点由 M10 负责定位，M7 只分析其生成输入和输出。

聚焦日志：

```text
aiReply[<chatId>]: useKnowledgeSearch=
aiReply[<chatId>]: aiContent=
aiReply[<chatId>]: formatAiContent=
invokeGpt[<chatId>]
detected response language
chatflow call kbreply
```

日志用于确认实际 system prompt、历史消息、知识上下文、模型原始输出和后处理。没有运行时请求证据时，不要把知识冲突、Prompt 优先级或模型行为写成确定根因。

## 建议边界

- 知识内容冲突：回 M9 统一知识口径。
- Prompt 与知识冲突：明确优先级并消除冲突，随后用原 badcase 回归。
- 生成未遵循已确认的运行时规则：缩短和强化规则、减少冲突上下文，并增加针对性测试。
- 后处理改变正确答案：提供 `aiContent` 与最终 content 对比，交对应检查模块修复。
- 任何配置建议都必须保持原业务口径，不擅自加强限制、承诺或风险结论。
