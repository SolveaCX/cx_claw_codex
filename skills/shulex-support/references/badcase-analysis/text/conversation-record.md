# 会话记录读取

`get-transcript` 获取单条会话记录详情。后端对象名为 `Transcript`，诊断说明统一称“会话记录”。

## 基本原则

始终结合用户的问题描述读取会话记录。先定位用户认为有问题的目标轮次、实际结果和预期结果，再查看影响该问题的字段及必要的前置轮次。不要脱离问题描述扫描所有字段，也不要从单个字段直接跳到根因。

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-transcript --chat-id <chatId> --pretty
```

CLI 默认请求 `isCompare=true`，因此每条消息通常同时返回保存的 `context` 和根据当前资源生成的 `contextComparison`。

## 读取顺序

1. 从用户描述提取异常现象、目标轮次、实际结果和预期结果。
2. 在 `messages[]` 中定位目标用户消息和对应回复。
3. 多轮上下文可能影响结果时，再向前读取必要轮次，不默认分析整段会话。
4. 读取目标回复的 `context`，还原意图、策略、Agent、知识、工具和流程信号。
5. 读取 `contextComparison` 判断历史资源后来是否被修改或删除。
6. 将直接事实、当前状态和推断分开记录，再进入对应模块。

## 四层结构

### 会话层

| 字段 | 用途 |
|------|------|
| `chatId` | 会话标识 |
| `touchPoint` | email、livechat 等入口，会影响检索和回复链路 |
| `subject` / `snippet` | 邮件主题和摘要，只作上下文，不能代替原始消息 |
| `createdAt` | 会话开始时间，查询日志的时间基准 |
| `handoff` / `handoffAt` / `takeoverAt` | 是否转人工及人工介入情况 |
| `stat` / `error` / `debug` | 会话状态、顶层错误和调试标记 |
| `metadata.__bot_id` | Bot ID；不是稳定的顶层 `botId` 字段 |
| `messages[]` | 原始用户、AI、人工和流程消息 |

### 消息层 `messages[]`

| 字段 | 用途 |
|------|------|
| `id` / `turn` / `createdAt` | 定位目标消息、轮次和时间 |
| `role` / `messageRole` | USER、ASSISTANT、人工等角色 |
| `content` / `attachments` | 原始消息和附件，优先于摘要 |
| `type` | MESSAGE、TO_AGENT、STOPPED、CONFUSED、HUMAN_REVIEW 等动作结果 |
| `handoff` / `reason` / `reasonDesc` | 本条消息是否转人工及原因 |
| `reasonList` / `reasonsDescList` | 同一回复的多个原因 |
| `filteredContent` | 回复被检查或拦截时的原始候选内容 |
| `context` | 该轮保存的执行上下文 |
| `contextComparison` | 保存上下文与当前资源的比较结果 |

`type`、`reason`、意图、策略等通常属于目标回复，不要误当成会话顶层字段。

### 执行上下文 `messages[].context`

按问题读取，不要求每次全部展开：

| 字段 | 用途 |
|------|------|
| `mixedQuery` | 原始问题、用户 query、知识 query 及翻译/改写结果 |
| `intents[]` / `intent` / `originIntent` | 候选意图及兼容字段；值不同是排查信号，不自动等于意图漂移 |
| `strategyId` / `strategyName` / `strategyAction` | 命中策略及动作 |
| `metadata` | 变量系统字段和运行元数据；`ai_fields` 等值位于此层 |
| `retrievedKus` | 历史召回的 QA 候选、分数、排名及是否实际生效 |
| `directoryIds` | 本轮知识检索范围 |
| `documentQaContext` / `recommendProductContext` | 实际使用的文档、chunk 和商品上下文 |
| `toolCalls` | 工具名、参数和错误信息 |
| `aiContent` / `filteredContent` | LLM 原始回复及后处理前后的差异线索 |
| `metadata.real_time_inspection_tags` | 实时质检命中的标签；是本轮送检结果的首要事实证据 |
| `currentPrompt` | Prompt 线索，注意下面的历史快照限制 |
| `context.timing.__stage_time_total` | 本轮总耗时；不要使用不存在的 `perf.total` |
| `ext` | Agent/ChatFlow 执行信息，如 `invoke_agent_id`、`chatflow_run_info`、`graph_finished`、`ai_agent_history_msg` |

### 当前状态比较 `messages[].contextComparison`

| 字段 | 用途 |
|------|------|
| `chatContext` | 用当前资源信息补充后的上下文 |
| `contextModifiedList` | 历史使用的知识、意图或策略后来被修改/删除 |
| `unusedKus` | 历史候选全部未生效时展示的知识 |
| `kuFolderCount` | 历史知识涉及的目录数量 |
| `entities` / `strategyAction` | 当前可展示的实体与策略动作 |

`contextComparison` 不是重新执行目标轮次，也不会重新跑意图、知识召回、工具或 Agent。

## 历史与当前状态边界

- `context` 主要来自当次保存的执行上下文，可作为历史事实来源。
- `contextComparison` 是读取时与当前资源的比较结果，不能当成当次运行配置。
- 当历史 `currentPrompt` 为空时，后端可能用当前 Agent Prompt 补填；因此它不一定是历史运行快照。
- 当前 Agent、意图、策略、知识或 ChatFlow 图只能说明现在的配置。要证明历史运行时配置，需结合保存的版本、`contextModifiedList` 或日志。

## 常见路由

| 会话记录信号 | 下一步 |
|--------------|--------|
| 意图、策略与预期不符 | M2 / M3 |
| 变量系统字段缺失或错误 | M4 |
| Agent 类型、调用轮次或工具循环异常 | M5 / M6 |
| 召回内容正确但 `aiContent` 或最终回复错误 | M7 |
| `retrievedKus`、query、目录、排序或使用知识异常 | M9 |
| `metadata.real_time_inspection_tags` 有值，或回复被合规原因拦截/转人工 | M12 |
| `ext.chatflow_run_info` 出现节点执行或路由问题 | M10 |
| 算法 rewrite / NER / reply / check 异常 | M11 |
