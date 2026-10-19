# `/report` 统计接口与字段契约

本文描述 `/report` 页面使用的统计接口与字段。前端主要通过 `/api_v2/as_bot/statement/*` 请求 analysis-service 的统计数据。

## 页面能力与命令

| `/report` 场景 | 前端接口 | CLI 命令 |
|---|---|---|
| 工单量、解决、转人工 | `POST /api_v2/as_bot/statement/transcript` | `report-transcript` |
| 消息量、AI 消息回复 | `POST /api_v2/as_bot/statement/message` | `report-message` |
| Agent 绩效 | `POST /api_v2/as_bot/statement/agent` | `report-agent` |
| 意图分布与下钻 | `POST /api_v2/as_bot/statement/transcript/intent` | `report-intent` |
| 满意度汇总 | `POST /api_v2/as_bot/statement/satisfaction/feedback` | `report-satisfaction` |
| 满意度明细 | `POST /api_v2/as_bot/statement/satisfaction/message` | `report-satisfaction-list` |
| 评分分布 | `POST /api_v2/as_bot/statement/feedback` | `report-feedback` |
| 知识使用 | `POST /api_v2/as_bot/statement/knowledge` | `report-knowledge` |
| 转人工原因 | `POST /api_v2/as_bot/statement/transcript/reason2` | `report-escalation` |
| 三级原因下钻 | `POST /api_v2/as_bot/statement/transcript/reason/three/level` | `report-escalation-drilldown` |
| Agent 周趋势图 | `POST /api_v2/as_bot/statement/graph/agent` | `report-agent-weekly-graph` |
| 自学习 | `POST /api_v2/as_bot/statement/self-learning` | `report-self-learning` |
| LiveChat 漏斗 | `POST /api_v2/as_bot/livechat/report/summary` | `report-livechat` |
| LiveChat 明细 | `POST /api_v2/as_bot/livechat/report/table` | `report-livechat-table` |
| AI 质检概览 | 质检 count 接口 | `report-inspection` |
| AI 质检趋势 | 质检 history 接口 | `report-inspection-history` |

## 请求参数

Report 通用请求与 analysis-service `FilterRequest` 对齐：

| 字段 | 规则 |
|---|---|
| `beginTimestamp` | 必填，目标时区开始日期的 `00:00:00.000`，毫秒 |
| `endTimestamp` | 必填，目标时区结束日期的 `23:59:59.999`，毫秒 |
| `projectId` | CLI 根据当前项目自动发送 |
| `timeOffset` | 前端浏览器 UTC 小时偏移；例如北京时间为 `8` |
| `botId` | 可选；未选择 Bot 时不发送 |
| `touchPoint` | 可选；前端未选择渠道时不发送，表示全部渠道 |
| `agentId` | Agent 明细或 Agent 下钻时发送 |
| `firstIntentId` | 意图下钻时发送；CLI 使用 `--intent-id` |
| `dateUnit` | 按接口需要发送 `DAY`、`WEEK` 或 `TOTAL` |

缺少时间范围时必须询问用户。时区默认使用中国时区（`Asia/Shanghai`，`UTC+8`），请求固定发送 `timeOffset=8`；仅当用户明确指定其他时区时，才按用户时区计算日期边界并覆盖 `timeOffset`。

### 与前端日期选择器对齐

- `/report` 公共日期选择器不允许选择今天之后的数据，页面最大日期为昨天。
- 两个日期相差不能超过 30 天。用户要求更长范围时，按前端可选择的窗口拆段请求。
- 拆段后计数求和；比例按合并后的分子和分母重新计算，禁止平均分段百分比。
- Report 和后续 Agent 会话记录下钻必须复用完全相同的毫秒边界、时区与适用过滤条件。

## 时间粒度

- `DAY`：日趋势。`timestampStr` 通常是 `年-年内第几天`，例如 `2026-92`，要转换为实际日期后展示。
- `WEEK`：周趋势。`timestampStr` 通常是 `年-第几周`，不要当成自然日期。
- `TOTAL`：整个请求时间段的汇总，用于总览和分段汇总。
- analysis-service 的 `DateUnit` 还包含 `MONTH`，但 `/report` 前端当前不把它作为页面能力使用。需要自然月数据时，按月分别请求 `TOTAL` 最稳妥。

## 核心指标结构

### Agent 会话记录与消息

`report-transcript` 和 `report-message` 都可能返回以下 bucket key，但两者数据层级不同：前者是工单级，后者是消息回复分析。不要混用两个接口的总量。

| key | 页面含义 | 使用规则 |
|---|---|---|
| `total` | 当前口径总量 | rate 类指标的分母 |
| `resolution` | 已解决或 AI 有效回复数量 | 以响应中的 `script` 为权威筛选口径 |
| `resolution_rate` | 解决率或页面展示的 AI 消息回复率 | 已是百分比值，不要再次乘 100 |
| `ai_answer` | AI 参与应答数量 | 与 `resolution` 不是同义字段 |
| `ai_answer_rate` | AI 应答占比 | 已是百分比值 |
| `escalation` | 转人工/升级数量 | 以响应中的 `script` 为权威 |
| `escalation_rate` | 转人工率 | 已是百分比值 |

`/report` 的“AI 消息回复率”页面读取 `report-message` 的 `resolution_rate`。分析时同时保留 `resolution` 和 `total`，跨时间段合并后重新计算。

### Agent

`report-agent` 的 `TOTAL[0].buckets[]` 通常按 Agent 分组：

- `key`：Agent ID。
- `name`：Agent 名称。
- `valueMap.total`：该 Agent 总量。
- `valueMap.ai_answer` / `ai_answer_rate`：AI 应答数量与比例。
- `valueMap.resolution` / `resolution_rate`：解决数量与比例。
- `valueMap.escalation` / `escalation_rate`：转人工数量与比例。
- `scriptMap`：下钻收件箱 Agent 会话记录时使用的查询脚本。

汇总多个 Agent 时先分别求和 `total`、`ai_answer`、`resolution`、`escalation`，再计算比例。

### Intent

`report-intent` 的 `TOTAL[0].buckets[]` 按意图分组，常见字段为 `key`、`name`、`valueMap`、`scriptMap`。意图趋势和详情页还会联合 `report-message` 获取消息级指标；不要把意图工单数当成消息数。

### 满意度

- `report-satisfaction` 返回 AI 与人工满意度汇总。
- `report-satisfaction-list` 是分页明细，列表 key 为 `satisfactions`，不是 `records`。
- `report-feedback` 返回评分分布，并按 `handoff` / `no_handoff` 区分人工与 AI。

### 知识、自学习与 LiveChat

- `report-knowledge` 是分页接口，返回知识使用、转人工数/率等字段；翻页时保留相同时间与过滤条件。
- `report-self-learning` 返回自学习主题统计与趋势。
- `report-livechat` / `report-livechat-table` 是 LiveChat 售前漏斗，不应代替通用 Agent 会话记录/消息指标。
- AI 质检使用 `YYYY-MM-DD` 参数，不使用 Report 毫秒参数；时间范围仍需与用户确认的一致。

## 失败与异常数据

- 每个接口单独执行，不要用 `&&` 串联整批请求。
- `report-escalation` 对应的 `reason2` 曾出现 `errno=-1`，根因可能是 analysis-service 在空聚合转换时异常。此时只能标记“转人工原因指标不可用”，不能自行补原因分布。
- `statement/transcript` 在错误账号权限下可能静默返回零值。零值与其他接口、收件箱 Agent 会话记录明细明显冲突时，优先检查权限，不要直接判断业务为零。
- 返回缺少目标 bucket、分页未完成或接口失败时，必须在最终结论中披露。
- 抽样会话只能帮助解释已有指标，不能代替缺失的整体指标。

## 示例

```bash
cxclawctl api report-message \
  --begin-ts "$BEGIN_MS" \
  --end-ts "$END_MS" \
  --time-offset 8 \
  --date-unit DAY \
  --pretty
```

指定渠道时才追加：

```bash
--touch-point LIVE_CHAT
```
