# ChatReport (Agent 看板) 字段与接口

本文描述系统当前正式的 `/chatReport`（数据分析 - Agent 看板）页面使用的 `chat-report/*` 接口。标签、知识、自学习、转人工、LiveChat、满意度明细、质检详情和导出继续使用 `report-fields.md` 中列出的当前详情页接口。原实验性 `/dashboard` 页面已下线，不得再对接到其接口。

## 指标命令与字段对照

命令入口：`node "<PLUGIN_ROOT>/plugin-cli.mjs" analytics <action>`。每次调用携带当前会话的 `--context`。

日期格式为 `YYYY-MM-DD`；所有命令均可加 `--pretty` 格式化输出。

| 命令 | 用途 | 必填参数 | 可选筛选参数 | 返回字段说明 |
|---|---|---|---|---|
| `analytics tickets` | 服务能力（未按 Agent / 意图筛选的工单量、解决率、转人工率） | `--start-date`、`--end-date` | `--bot-id`、`--touch-point` | 工单计数 |
| `analytics messages` | 服务能力（未按 Agent / 意图筛选的消息量、AI 回复率） | `--start-date`、`--end-date` | `--bot-id`、`--touch-point` | 消息计数 |
| `analytics satisfaction` | 服务质量（CSAT 满意度与点赞点踩） | `--start-date`、`--end-date` | `--bot-id`、`--touch-point` | 满意度 |
| `analytics first-response` | 服务质量（首次响应时效） | `--start-date`、`--end-date` | `--bot-id`、`--touch-point` | 首次响应 |
| `analytics return-retention` | 服务收益（RMA 挽回率） | `--start-date`、`--end-date` | `--bot-id`、`--touch-point` | 退货挽回与质检 |
| `analytics inspection-results` | 风险与质检趋势 | `--start-date`、`--end-date` | 无 | 每日质检结果数 |
| `analytics inspection-results-by-type` | 风险与质检按类型汇总 | `--start-date`、`--end-date` | 无 | 日期、类型、名称、数量 |
| `analytics intents` | 意图分布、趋势及指定意图的工单量、解决率、转人工率、消息量、回复率 | `--start-date`、`--end-date` | `--bot-id`、`--touch-point`、`--intent-id` | 日期与维度、工单计数、消息计数 |
| `analytics intent-top` | 首页意图 Top | `--start-date`、`--end-date` | `--bot-id`、`--touch-point`、`--top-n` | `rows`、`totalCount` |
| `analytics agents` | 智能体分布、趋势及指定 Agent 的工单量、解决率、转人工率、消息量、回复率 | `--start-date`、`--end-date` | `--bot-id`、`--touch-point`、`--agent-id` | 日期与维度、工单计数、消息计数 |
| `analytics agent-top` | 首页 Agent Top | `--start-date`、`--end-date` | `--bot-id`、`--touch-point`、`--top-n` | `rows`、`totalCount` |
| `analytics api-calls` | 工具调用每日趋势和工具详情 | `--start-date`、`--end-date` | `--bot-id`、`--touch-point`、`--tool-id` | 工具、状态、耗时、`script` |
| `analytics api-calls-summary` | 工具调用汇总与 Top 工具 | `--start-date`、`--end-date` | `--bot-id`、`--touch-point`、`--top-n` | 汇总、每日总量、工具列表、`script` |
| `analytics inbox-scripts` | 会话下钻筛选脚本 | 无 | 无 | 会话下钻脚本 |

全部日期型命令还可用 `--time-type MESSAGE_CREATED_AT|TICKET_CREATED_AT` 指定统计时间字段。页面默认值由模块决定；没有业务依据时不要自行覆盖。

## 返回字段说明

以下说明对应每日统计记录；`inbox-scripts` 返回脚本映射。工单指 Agent 会话记录，统计排除调试数据。

### 日期与维度

| 字段 | 定义 |
|---|---|
| `date` | 统计日期，`YYYY-MM-DD`，按中国时区（Asia/Shanghai）划分。工单、满意度、首响和挽回按工单创建日期归属；当前 CLI 的消息统计按消息创建日期归属。 |
| `intentId`、`intentName` | 首次识别意图的 ID、名称；`intentId=0` 表示无意图，名称可能为空。 |
| `agentId`、`agentName` | Agent ID、名称。工单按调用 Agent 归属，消息按各消息的 Agent 归属；无 Agent 归属的数据不计入对应维度，不能直接用 Agent 分组之和代替全量报表。名称查不到时可能返回 ID 文本。 |

日期范围包含首尾两天，单次最多 31 天。维度报表每条记录对应“日期 + Agent / 意图”，工单计数和消息计数分别遵循各自的日期口径；不提供满意度、首响、挽回或质检字段。

### 工单计数

单位均为工单数。“进线”按会话的 AI 进线标记统计；“处理”按 AI 已回答标记统计；“解决”按未转人工统计，不要求工单关闭，也不等同于用户确认问题已解决。

| 字段 | 定义 |
|---|---|
| `totalTicketCount` | 当前筛选范围内的总工单数；满意度、挽回报表中的同名字段含义相同。 |
| `aiIncomingTicketCount` | 标记为 AI 进线的工单数。 |
| `handoffTicketCount` | 已转人工的工单数，包含 AI 进线和非 AI 进线。 |
| `aiIncomingHandoffTicketCount` | AI 进线工单中已转人工的数量。 |
| `aiIncomingProcessedTicketCount` | AI 进线工单中 AI 已回答的数量，之后转人工也可计入。 |
| `aiNonIncomingProcessedTicketCount` | 非 AI 进线工单中 AI 已回答的数量。 |
| `aiIncomingResolvedTicketCount` | AI 进线工单中未转人工的数量。 |
| `aiNonIncomingResolvedTicketCount` | 非 AI 进线工单中未转人工的数量。 |

### 消息计数

单位均为消息条数。统计服务侧 `role=ASSISTANT` 的可见消息（未设置可见性也计入），排除 AI 的非消息动作；包含人工回复，不包含用户消息。

| 字段 | 定义 |
|---|---|
| `totalMessageCount` | 符合上述条件的全部消息数。 |
| `aiIncomingMessageCount` | 上述消息中带 AI 进线标记的数量，可包含转人工后的人工回复。 |
| `aiReplyMessageCount` | 上述消息中由非人工角色发出的回复数（`actionType=MESSAGE`）。 |
| `aiIncomingReplyMessageCount` | AI 进线消息中由非人工角色发出的回复数；用于 AI 进线回复率的分子。 |

### 满意度

会话评分、消息评价和综合评价是三套口径：会话评分按是否转人工归属 AI / 人工；消息评价按消息发送方归属；综合评价读取会话保存的最终评价分类，不能把前两类计数直接相加。未评价不计入满意或不满意。

| 字段 | 定义与单位 |
|---|---|
| `satisfactionTicketCount` | 已有综合评价的工单数，每个工单计一次。 |
| `satisfactionRecoveryRate` | 满意度回收率：`satisfactionTicketCount / totalTicketCount`。 |
| `sessionAiSatisfiedCount`、`sessionAiUnsatisfiedCount` | 未转人工工单的会话评分为满意 / 不满意的工单数。 |
| `sessionHumanSatisfiedCount`、`sessionHumanUnsatisfiedCount` | 已转人工工单的会话评分为满意 / 不满意的工单数。 |
| `messageAiSatisfiedCount`、`messageAiUnsatisfiedCount` | AI 消息获得满意 / 不满意评价（点赞 / 点踩）的条数；同一工单可贡献多条。 |
| `messageHumanSatisfiedCount`、`messageHumanUnsatisfiedCount` | 人工消息获得满意 / 不满意评价的条数；同一工单可贡献多条。 |
| `overallAiSatisfiedCount`、`overallAiUnsatisfiedCount` | 综合评价归为 AI 满意 / 不满意的工单数，对应 `LIKE_AI` / `DISLIKE_AI`。 |
| `overallHumanSatisfiedCount`、`overallHumanUnsatisfiedCount` | 综合评价归为人工满意 / 不满意的工单数，对应 `LIKE_HUMAN` / `DISLIKE_HUMAN`。 |
| `sessionAiSatisfactionRate`、`sessionHumanSatisfactionRate` | 各自会话评分的满意数 /（满意数 + 不满意数）。 |
| `messageAiSatisfactionRate`、`messageHumanSatisfactionRate` | 各自消息评价的满意数 /（满意数 + 不满意数），即消息点赞率。 |
| `overallSatisfactionRate` | AI 与人工的综合满意工单数之和 / 综合满意与不满意工单总数。 |

### 首次响应

首响从工单创建时间起算，到首次可见的 AI / 人工回复为止；人工首响也从工单创建时起算，不从转人工时起算。AI 与人工分别计数，同一工单可同时进入两类样本。

| 字段 | 定义与单位 |
|---|---|
| `aiFirstResponseTicketCount`、`humanFirstResponseTicketCount` | 有 AI / 人工首次回复的工单数，分别作为对应平均时长的分母。 |
| `aiFirstResponseDurationTotal`、`humanFirstResponseDurationTotal` | AI / 人工首次回复耗时之和，单位为秒。 |
| `aiAverageFirstResponseDuration`、`humanAverageFirstResponseDuration` | 对应首响总时长 / 对应首响工单数，单位为秒。 |
| `overallAverageFirstResponseDuration` | AI 与人工首响总时长之和 / 两类首响工单数之和，单位为秒；分母不是去重后的总工单数。 |

### 退货挽回与质检

| 字段 | 定义与单位 |
|---|---|
| `retentionTriggeredTicketCount` | 标记为触发退货挽回的工单数，按工单计数而非调用次数。 |
| `retentionSuccessTicketCount` | 标记为退货挽回成功的工单数。 |
| `retentionTriggerRate` | 退货挽回触发率：`retentionTriggeredTicketCount / totalTicketCount`。 |
| `retentionSuccessRate` | 退货挽回成功率：`retentionSuccessTicketCount / retentionTriggeredTicketCount`。 |
| `inspectionResultCount` | 平台规则与风险预警类别的质检结果条数，不是去重工单数，也不是全部质检类别的总量。 |

### 会话下钻脚本

`inbox-scripts` 返回“分组 → 指标 → ES 查询 JSON 字符串”，用于筛选符合该指标的收件箱会话，本身不返回统计值或会话明细。

| 返回分组 | 指标键与含义 |
|---|---|
| `TICKET` | `TOTAL` 全部工单；`AI_INCOMING` AI 进线；`AI_RESOLVED` 未转人工；`AI_PROCESSED` AI 已回答；`AI_INCOMING_RESOLVED` AI 进线且未转人工；`AI_INCOMING_PROCESSED` AI 进线且 AI 已回答。 |
| `MESSAGE` | `TOTAL`、`AI_INCOMING`、`AI_REPLY`、`AI_INCOMING_REPLY` 分别筛选包含对应消息计数条件的会话。 |
| `DIMENSION` | `NO_INTENT` 筛选无首次意图的会话。 |
| `RETURN_RETENTION` | `TRIGGERED` 触发挽回；`SUCCESS` 挽回成功。 |
| `SATISFACTION` | `RECOVERED_TICKET` 已有综合评价的会话。 |

下钻脚本描述指标条件，使用时仍需带上本次查询的时间和业务筛选条件。

### 意图与 Agent Top

- 意图行：`intentId`、`intentName`、`totalTicketCount`、`rate`。
- Agent 行：`agentId`、`agentName`、`totalTicketCount`、`rate`。
- `totalCount` 是当前筛选范围的总工单数；`rate` 是该行工单数占总量的比例。
- Top 只用于首页排行。查看某个维度详情时，继续调用 `analytics intents` 或 `analytics agents` 并传对应 ID。

### 工具调用

`analytics api-calls-summary` 返回 `toolCount`、`totalCount`、`successCount`、`failedCount`、`unknownCount`、`successRate`、`avgLatencyMs`、`successAvgLatencyMs`、`dailyTotals`、`items` 和总量 `script`。

`items[]` 与 `analytics api-calls` 的每日记录包含：

- `toolId`、`toolName`、`toolType`
- `totalCount`、`ticketCount`
- `successCount`、`failedCount`、`unknownCount`、`successRate`
- `avgLatencyMs`、`successAvgLatencyMs`、`maxLatencyMs`
- `statusDistribution`
- `script`、`failedScript`

`statusDistribution` 的每个状态可返回 `{count, script}`。详情页点击总调用量、单工具或状态分布时，使用对应 `script` 进入收件箱；接口没有独立分页或导出能力，不得声称可以导出工具调用报表。

## 汇总与核心公式

以下工单和消息公式同样适用于 Agent / 意图维度的对应计数字段。多日统计先汇总分子、分母再计算比例，不平均每日比例。首响同样先累加总时长和样本数，再相除；展示为分钟时除以 60。

本页日报的 `*Rate` 字段返回小数比例（如 `0.8` 表示 `80%`），保留四位小数；平均时长保留两位小数。接口在分母为 0 时返回 `0`，分析时应结合分母标注“无样本 / 不可计算”，不能据此评价表现为 0%。

- **AI 进线回复率**：`aiIncomingReplyMessageCount / aiIncomingMessageCount * 100%`
- **AI 进线解决率**：`aiIncomingResolvedTicketCount / aiIncomingTicketCount * 100%`
- **AI 转人工率**：`aiIncomingHandoffTicketCount / aiIncomingTicketCount * 100%`
- **AI 满意度 (CSAT)**：`overallAiSatisfiedCount / (overallAiSatisfiedCount + overallAiUnsatisfiedCount) * 100%`
- **人工满意度 (CSAT)**：`overallHumanSatisfiedCount / (overallHumanSatisfiedCount + overallHumanUnsatisfiedCount) * 100%`
- **AI RMA 挽回率**：`retentionSuccessTicketCount / retentionTriggeredTicketCount * 100%`
