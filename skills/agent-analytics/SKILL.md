---
name: agent-analytics
description: Shulex 客服智能体（AI Agent）运营数据分析。用于统计指标、趋势、排行、报表和运营下钻；badcase 或单次会话根因排查由 shulex-support 主责，本 skill 可按需提供统计和样本辅助证据。
---

# Agent Analytics

本 skill 用于查询和分析 Agent 运营数据。

**边界规则：** 如果用户要求解释某次会话为什么异常，或提到 badcase、异常回复、失败节点、报错、卡住、答非所问，由 `shulex-support` 负责主诊断；本 skill 仍可在需要时提供整体指标、趋势或样本下钻，不单独替代根因诊断流程。

在本 skill 中，数据分析页面中的**工单即 Agent 会话记录**，也是收件箱数据。统计指标默认通过系统正式的 Agent 看板（`/chatReport` 对应的 `chat-report/*` 接口）获取，工单明细和完整对话通过 Agent 会话记录接口获取。历史过渡的 `/dashboard` 页面已下线，禁止对其对接。

## 场景分流

- 查询首页指标、意图/Agent 排行、工具调用和标准趋势：读取 `references/chat-report-fields.md`。
- 查询标签、知识、自学习、转人工原因、LiveChat、满意度明细、质检详情或导出：读取 `references/report-fields.md`。这些接口仍由当前系统详情页使用，不按“旧版”限制调用。
- 查询工单明细、筛选样本、分页或单条完整对话：读取 `references/transcript.md`。
- 同一个问题同时需要统计和样本时，先按模块读取统计 reference，再读取 `transcript.md` 下钻解释。

## 固定执行顺序

1. **确认分析目标**：明确用户要看的指标、比较维度和期望结论。
2. **确认时间范围**：缺少时间范围时必须询问用户，不默认查询本月、最近 30 天或前端默认窗口。
3. **应用时区和过滤条件**：`analytics` 使用 `startDate` / `endDate`（`YYYY-MM-DD`）；详情模块的 `report <action>` 按页面契约使用毫秒时间戳或日期字符串。前端未选择渠道表示全部渠道，不要自动补 `LIVE_CHAT`。Transcript 下钻把同一日期范围换算成 `beginTimestamp` / `endTimestamp` 毫秒边界。
4. **分别调用接口**：每个统计或 Agent 会话记录请求独立执行。不要使用 `&&` 把整批命令串起来，避免一个接口失败后跳过全部后续数据。
5. **阶段性输出进展**：每完成一类指标，简要说明已拿到什么、缺少什么、下一步查什么。
6. **按需下钻 Agent 会话记录**：复用当前查询的日期范围和适用过滤条件；`analytics inbox-scripts` 或 chat ID 可作为下钻入口。分页直到 `hasNext=false` 才能声称明细完整。
7. **形成结论**：说明时间范围、时区、过滤条件、数据完整性、不可用指标和异常变化。

## 数据边界

- 某个接口失败时，根据错误信息和文档修正用法；无法恢复的指标标记为**不可用**，继续请求其他独立指标。
- 权限问题造成的静默零值、真实业务零值和后端异常必须区分，不能统一解释成“没有工单”。
- 抽样 Agent 会话记录只能解释具体案例或提供定性线索，不能替代整体统计，也不能用少量样本推导总体比例。
- 多段时间数据合并时，计数可以求和；比例必须根据合并后的分子和分母重新计算，不能直接平均各段比例。
- AI 回复与预期或历史水平出现明显变化时，必须指出变化幅度、发生时间和受影响维度；证据不足时明确写成待验证假设。

## CLI 入口

正式 Agent 看板统计通过以下资源化入口获取：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" analytics <action> ... --pretty
```

常用命令：

| 场景 | 命令 |
|---|---|
| 服务能力（未按 Agent / 意图筛选的工单量、进线解决率、转人工率） | `analytics tickets` |
| 服务能力（未按 Agent / 意图筛选的消息量、AI 回复率） | `analytics messages` |
| 服务质量（CSAT 满意度、点赞点踩数、满意率） | `analytics satisfaction` |
| 服务质量（首响时效、AI/人工平均首次响应耗时） | `analytics first-response` |
| 服务收益（AI 售后挽回率） | `analytics return-retention` |
| 风险与质检（规则命中与预警） | `analytics inspection-results` |
| 风险与质检按类型汇总 | `analytics inspection-results-by-type` |
| 意图分布、趋势及指定意图的工单量、解决率、转人工率、消息量、回复率 | `analytics intents` |
| 意图排行 | `analytics intent-top`（可选 `--top-n`） |
| 智能体分布、趋势及指定 Agent 的工单量、解决率、转人工率、消息量、回复率 | `analytics agents` |
| Agent 排行 | `analytics agent-top`（可选 `--top-n`） |
| 工具调用趋势、状态与会话下钻 | `analytics api-calls`（可选 `--tool-id`） |
| 工具调用汇总与 Top 工具 | `analytics api-calls-summary`（可选 `--top-n`） |
| 会话下钻查询脚本 | `analytics inbox-scripts` |
| 标签、知识、自学习、转人工、LiveChat、满意度和质检详情 | 对应 `report <action>` |
| 收件箱 Agent 会话记录明细 | `transcript list` |
| 单条完整 Agent 会话记录 | `transcript get` |

CLI 命令、参数和字段口径以本 skill 的 references 为准。遇到未知命令或字段时先回读对应 reference，不要猜测接口。

## 回复要求

- 先给核心结论，再给可核对的数据表和指标口径。
- 趋势图使用 `render_chart`；比例轴在标题或轴名称中注明 `%`，不要使用不受支持的 formatter。
- 明确列出失败接口、缺失指标、分页是否完成和结论置信度。
- 用户需要文件时只生成 HTML 或 Markdown；未要求文件时直接在回复中说明结果。
