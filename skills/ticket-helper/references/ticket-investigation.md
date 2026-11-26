# 查看工单列表、详情与处理过程

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-helper/<唯一文件名>.json` 保存。

## 按用户目标执行

| 用户目标 | 先查 | 何时再查/结束 |
|---|---|---|
| 看状态、负责人、渠道 | ticket get | 详情足以回答就结束，不读完整消息 |
| 找一批客服工单 | ticket list | 先解析名称条件，展示匹配记录及分页；用户要全量再取完 |
| 看客户说了什么/已有回复 | ticket messages | 需要原文格式才查 message-origin/response-content；不生成回信 |
| 为什么状态或负责人变了 | ticket get + ticket activity | 根据事件再补 notes/messages；配置原因交 ticket-admin |
| 是否超时/满意度如何 | 从详情取 ticketId，再查 SLA 或 satisfaction | 区分当前状态、历史事件和评价，证据足够即停止 |
| 查标签/字段 | ticket tags / ticket fields | 标签树与批量查询见 `<PLUGIN_ROOT>/skills/ticket-helper/references/tags.md`，无需先拉全量历史 |

给用户“当前事实 + 对应记录/时间 + 未确认部分”。无法定位对象时先消歧；接口失败不当作无工单，空消息不当作无客户问题。

## 查看工单列表与单张详情

用户要查看一张工单时，直接用 `ticket get` 读取详情；这里不需要运行分析脚本或生成报表。只有关键词、客户姓名或状态时先筛选；目录名称转 ID 的方法见 `<PLUGIN_ROOT>/skills/ticket-helper/references/classification.md`。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket list` | 常用：viewId、keyword、ticketNumber、ticketStatusList、agentIdList、tagList、channelList、createTimeBegin/createTimeEnd；page/pageSize | 支持 `--all`；全部参数与类型见 `ticket list --help` |
| `ticket get` | **ticketNumber**:string | 单次响应；保留服务端分页字段 |

有工单号时：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket get --params-json '{"ticketNumber":"ST-123"}'
```

只有关键词或其他条件时，用 `ticket list --params-json '{"keyword":"物流"}'` 列出匹配工单，再定位具体记录。详情中核对主题、当前状态、负责人、渠道及客户；完整消息必须另查 messages。自定义字段值用 `ticket fields --params-json '{"ticketNum":"ST-123"}'`，工单标签见 `<PLUGIN_ROOT>/skills/ticket-helper/references/tags.md`。

## 查看消息、备注与操作记录

按时间拼接消息、备注与操作记录，引用消息 ID。原始内容用于解释已有回复；本期不拟稿或回信。附件与录音返回下载 URL，不能声称文件已保存。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket messages` | before:string, limit:integer, **ticketNumber**:string | 支持 `--all`；检查截断 |
| `ticket notes` | **ticketNumber**:string | 单次响应；保留服务端分页字段 |
| `ticket message-origin` | **ticketNumber**:string, **messageId**:string | 单次响应；保留服务端分页字段 |
| `ticket response-content` | **ticketNumber**:string, **responseId**:string | 单次响应；保留服务端分页字段 |
| `ticket previous` | **ticketNumber**:string | 单次响应；保留服务端分页字段 |
| `ticket channel-status` | **ticketNumber**:string | 单次响应；保留服务端分页字段 |
| `ticket channel-errors` | 无 | 单次响应；保留服务端分页字段 |
| `ticket activity` | **ticket_number**:string | 单次响应；保留服务端分页字段 |
| `ticket attachment` | **messageId**:string, **ticketId**:string, **type**:string | 单次响应；保留服务端分页字段 |
| `ticket recording` | **voiceCallId**:string, **artifactId**:string | 单次响应；保留服务端分页字段 |
| `ticket batch-failures` | **taskId**:string | 单次响应；保留服务端分页字段 |
| `ticket batches` | startCreatedAt:string, endCreatedAt:string, creatorId:integer, assigneeId:integer, subject:string, status:string, page:integer, pageSize:integer, sort:string, order:string | 支持 `--all`；检查截断 |

## 核对 SLA 与评价

内部 ticketId 从详情取，不与工单号互换。把规则目标、当前计时、事件和评价分开说明；查询无记录不等于达标。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket sla-projection` | **ticketId**:string | 单次响应；保留服务端分页字段 |
| `ticket sla-metrics` | **ticketId**:string | 单次响应；保留服务端分页字段 |
| `ticket sla-events` | **ticketId**:string | 单次响应；保留服务端分页字段 |
| `ticket satisfaction` | **ticketId**:string | 单次响应；保留服务端分页字段 |
| `ticket conversation-satisfaction` | **projectId**:integer, **chatId**:string | 单次响应；保留服务端分页字段 |

## 筛选条件的选择

- 客服/渠道/标签只给名称：先读 `<PLUGIN_ROOT>/skills/ticket-helper/references/classification.md` 查目录 ID，重名时消歧；不要把名称放进 ID 数组。
- 时间条件先确认字段含义：创建时间用 createTimeBegin/createTimeEnd；满意度提交时间用 satisfactionSubmitTimeBegin/End。ISO 时间携带时区；不能把“最近回复”偷换成创建时间。
- 其他筛选按 `ticket list --help` 选择，包括客户、店铺、订单、SLA、未读和语音条件；不支持的范围明确说明。需要复杂全量分析时归 ticket-analytics。
- 工单号查询不能误用内部 ticketId。列表中的 id 可用于后续内部 ID 查询；标签单查的 ticketNum 仍是对外工单号。
