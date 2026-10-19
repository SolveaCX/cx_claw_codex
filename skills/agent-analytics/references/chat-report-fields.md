# ChatReport (Agent 看板) 字段与接口

本文描述系统当前正式的 `/chatReport`（数据分析 - Agent 看板）页面使用的 `chat-report/*` 接口。默认所有 Agent Analytics 统计查询都使用这些接口；只有用户明确要求旧版 `/report`、`statement` 或“返回旧版”时才使用标记为旧版的 `report-fields.md`。原实验性 `/dashboard` 页面已下线，不得再对接到其接口。

## 公共参数

所有主指标接口都是 `POST /api_v2/as_bot/chat-report/{metric}`，请求 Body JSON 参数为：

- `startDate`、`endDate`：必填，`YYYY-MM-DD`。
- `botId`：可选，Bot ID。
- `touchPoint`（或 CLI `--channel`）：可选，渠道名。
- `intentId`：可选，意图 ID。
- `agentId`：可选，Agent ID。

## 指标命令与字段对照

| CLI 命令 | 接口路径 | 对应前台板块 | 主要返回字段 |
|---|---|---|---|
| `chat-report-tickets` | `/tickets` | 服务能力（解决率/转人工率） | `totalTicketCount`、`aiIncomingTicketCount`、`handoffTicketCount`、`aiIncomingHandoffTicketCount`、`aiIncomingResolvedTicketCount` 等 |
| `chat-report-messages` | `/messages` | 服务能力（AI 回复率） | `totalMessageCount`、`aiIncomingMessageCount`、`aiReplyMessageCount`、`aiIncomingReplyMessageCount` |
| `chat-report-satisfaction` | `/satisfaction` | 服务质量（CSAT 满意度与点赞点踩） | `totalTicketCount`、`satisfactionTicketCount`、`satisfactionRecoveryRate`、`sessionAiSatisfiedCount`、`sessionAiUnsatisfiedCount`、`sessionHumanSatisfiedCount`、`sessionHumanUnsatisfiedCount`、`messageAiSatisfiedCount` (AI 点赞数)、`messageAiUnsatisfiedCount` (AI 点踩数)、`messageHumanSatisfiedCount`、`messageHumanUnsatisfiedCount`、`sessionAiSatisfactionRate`、`messageAiSatisfactionRate`、`overallSatisfactionRate` |
| `chat-report-first-response` | `/first-response` | 服务质量（首次响应时效） | `aiFirstResponseTicketCount`、`humanFirstResponseTicketCount`、`aiFirstResponseDurationTotal`、`humanFirstResponseDurationTotal`、`aiAverageFirstResponseDuration`、`humanAverageFirstResponseDuration`、`overallAverageFirstResponseDuration` |
| `chat-report-return-retention` | `/return-retention` | 服务收益（RMA 挽回率） | `totalTicketCount`、`retentionTriggeredTicketCount`、`retentionSuccessTicketCount` |
| `chat-report-inspection-results` | `/inspection-results` | 风险与质检 | `inspectionResultCount` (平台规则与风险预警数) |
| `chat-report-intents` | `/intents` | 深度分析（意图工单分布与趋势） | 意图列表及各意图的工单数、进线解决数、转人工数等 |
| `chat-report-agents` | `/agents` | 深度分析（智能体工单分布与趋势） | 智能体列表及各智能体的工单数、进线解决数、转人工数等 |
| `chat-report-inbox-scripts` | `/inbox-scripts` | 会话下钻筛选脚本 | 获取按各指标下钻收件箱会话时的 ES 查询脚本 |

### 核心公式

- **AI 进线回复率**：`aiIncomingReplyMessageCount / aiIncomingMessageCount * 100%`
- **AI 进线解决率**：`aiIncomingResolvedTicketCount / aiIncomingTicketCount * 100%`
- **AI 转人工率**：`aiIncomingHandoffTicketCount / aiIncomingTicketCount * 100%`
- **AI 满意度 (CSAT)**：`messageAiSatisfiedCount / (messageAiSatisfiedCount + messageAiUnsatisfiedCount) * 100%`
- **人工满意度 (CSAT)**：`messageHumanSatisfiedCount / (messageHumanSatisfiedCount + messageHumanUnsatisfiedCount) * 100%`
- **AI RMA 挽回率**：`retentionSuccessTicketCount / retentionTriggeredTicketCount * 100%`
