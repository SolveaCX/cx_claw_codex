---
name: agent-analytics
description: Shulex 客服智能体（AI Agent）运营数据分析。用于统计指标、趋势、排行、报表和运营下钻；badcase 或单次会话根因排查由 shulex-support 主责，本 skill 可按需提供统计和样本辅助证据。
requires:
  libs: [solvea-api]
---

# Agent Analytics

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。
本 skill 用于查询和分析 Agent 运营数据。

**边界规则：** 如果用户要求解释某次会话为什么异常，或提到 badcase、异常回复、失败节点、报错、卡住、答非所问，由 `shulex-support` 负责主诊断；本 skill 仍可在需要时提供整体指标、趋势或样本下钻，不单独替代根因诊断流程。

在本 skill 中，数据分析页面中的**工单即 Agent 会话记录**，也是收件箱数据。统计指标默认通过系统正式的 Agent 看板（`/chatReport` 对应的 `chat-report/*` 接口）获取，工单明细和完整对话通过 Agent 会话记录接口获取。历史过渡的 `/dashboard` 页面已下线，禁止对其对接。

## 场景分流

- 查询统计指标、趋势、字段口径或页面对应接口：默认读取 `references/chat-report-fields.md`。
- 只有用户明确要求“旧版报表”“/report”“statement”或“返回旧版”时，才读取标记为旧版的 `references/report-fields.md` 并调用 `report-*`。
- 查询工单明细、筛选样本、分页或单条完整对话：读取 `references/transcript.md`。
- 同一个问题同时需要统计和样本时，先读取 `chat-report-fields.md` 获取整体指标，再读取 `transcript.md` 下钻解释；若用户指定旧版，则把前者替换为标记为旧版的 `report-fields.md`。

## 固定执行顺序

1. **确认分析目标**：明确用户要看的指标、比较维度和期望结论。
2. **确认时间范围**：缺少时间范围时必须询问用户，不默认查询本月、最近 30 天或前端默认窗口。
3. **应用时区和过滤条件**：Agent 看板使用 `startDate` / `endDate`（`YYYY-MM-DD`），可选 `botId`、`channel`（或 `touchPoint`）、`intentId`、`agentId`；前端未选择渠道表示全部渠道，不要自动补 `LIVE_CHAT`。标记为旧版的 `report-*` 才使用毫秒时间戳和 `timeOffset=8`。
4. **分别调用接口**：每个统计或 Agent 会话记录请求独立执行。不要使用 `&&` 把整批命令串起来，避免一个接口失败后跳过全部后续数据。
5. **阶段性输出进展**：每完成一类指标，简要说明已拿到什么、缺少什么、下一步查什么。
6. **按需下钻 Agent 会话记录**：复用当前查询的日期范围和适用过滤条件；`analytics inbox-scripts` 或 chat ID 可作为下钻入口。分页直到 `hasNext=false` 才能声称明细完整。
7. **形成结论**：说明时间范围、时区、过滤条件、数据完整性、不可用指标和异常变化。

## 数据边界

- 某个接口失败时，把对应指标标记为**不可用**，继续请求其他独立指标。
- 权限问题造成的静默零值、真实业务零值和后端异常必须区分，不能统一解释成“没有工单”。
- 抽样 Agent 会话记录只能解释具体案例或提供定性线索，不能替代整体统计，也不能用少量样本推导总体比例。
- 多段时间数据合并时，计数可以求和；比例必须根据合并后的分子和分母重新计算，不能直接平均各段比例。
- AI 回复与预期或历史水平出现明显变化时，必须指出变化幅度、发生时间和受影响维度；证据不足时明确写成待验证假设。

## CLI 入口

所有数据通过以下资源化入口获取：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" analytics <action> ... --pretty
```

常用命令：

| 场景 | 命令 |
|---|---|
| 服务能力（工单量、进线解决率、转人工率） | `analytics tickets` |
| 服务能力（消息量、AI 回复率） | `analytics messages` |
| 服务质量（CSAT 满意度、点赞点踩数、满意率） | `analytics satisfaction` |
| 服务质量（首响时效、AI/人工平均首次响应耗时） | `analytics first-response` |
| 服务收益（AI 售后挽回率） | `analytics return-retention` |
| 风险与质检（规则命中与预警） | `analytics inspection-results` |
| 意图工单分布与趋势 | `analytics intents` |
| 智能体工单分布与趋势 | `analytics agents` |
| 会话下钻查询脚本 | `analytics inbox-scripts` |
| 旧版报表（仅用户明确指定） | `api report-*` |
| 旧版知识、LiveChat、质检、自学习等 | `api report-*`（仅用户明确指定旧版） |
| 收件箱 Agent 会话记录明细 | `transcript list` |
| 单条完整 Agent 会话记录 | `transcript get` |

CLI 命令、参数和字段口径以本 skill 的 references 为准。遇到未知命令或字段时先回读对应 reference，不要猜测接口。

## 回复要求

- 先给核心结论，再给可核对的数据表和指标口径。
- 趋势图使用 `render_chart`；比例轴在标题或轴名称中注明 `%`，不要使用不受支持的 formatter。
- 明确列出失败接口、缺失指标、分页是否完成和结论置信度。
- 用户需要文件时只生成 HTML 或 Markdown；未要求文件时直接在回复中说明结果。
