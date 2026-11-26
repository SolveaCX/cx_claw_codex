# 分配、容量、日历与 SLA

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-admin/<唯一文件名>.json` 保存。

## 分配与容量

1. 用户问队列配置先 `ticket admin-queues` 定位，再 `ticket admin-queue` 读目标；队列名称不唯一时先消歧。激活状态用 `ticket admin-routing-activation`，不要把有配置等同于已启用。
2. 仅在规则引用团队、日历或容量时，用 teams、calendars/calendar、capacity/capacity-get/capacity-default 补齐关联。按实际返回引用选 ID，不遍历所有详情。
3. 回答队列条件、分配范围、排班和容量约束；实时负载交 ticket-analytics。没有成员在线/负载证据时，不断言某人当前可接单。

先看队列及激活状态，再关联团队、语言、日历和容量配置。实时排队人数由 ticket-analytics 查询，不能从配置推断当前负载。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-queues` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-queue` | **queueId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-queue-channels` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-queue-languages` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-routing-activation` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-teams` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-calendars` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-calendar` | **calendarId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-capacity` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-capacity-get` | **ruleId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-capacity-default` | 无 | 单次响应；保留服务端分页字段 |

## SLA 规则解释

1. 用 `ticket admin-sla-policies` 定位策略，`ticket admin-sla-metadata` 解释指标与条件；核对优先级、时间目标和引用日历。
2. 问“夜间计时吗”只需核对策略关联的日历、时区和营业时段；以实际返回为准，未知时区不要自行套用本地时间。
3. 需要验证匹配时才做 sla-preview，工单字段快照必须来自已取得的详情；把匹配结果、目标时长与真实 SLA 事件区分。
4. 回答适用条件和计时规则，缺少历史事件就止于配置解释，不宣称已经证实超时根因。

查策略与字段目录后，向 sla-preview 传入明确的 ticket 字段快照。当前后端按传入 ticket 匹配，不会仅凭 ticketId 补齐工单；预览不生成 SLA 指标。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-sla-policies` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-sla-metadata` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-sla-preview` | ticketId:integer, priority:string, **ticket**:object | 单次响应；保留服务端分页字段 |
