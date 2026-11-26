# 产品报表对照

用户问指标、趋势、绩效或产品报表时先走本页，无需读取 latest_task 或建立快照任务。

1. 从页面/对话取得产品报表、时间范围、时区及筛选。缺少会改变结果的条件才补问；用户说“今天”可用服务端今日指标，但应标明其口径。
2. 按下表选接口。先取足以回答问题的一份统计，不遍历所有报表；产品未提供的指标/图表标识不可猜。
3. 对比接口的指标定义、日期粒度、单位、分母和更新时间。同比/环比要保持筛选与口径一致。不同版本报表不能无说明互换。
4. 只有需要解释异常或验证分组时才下钻表格/样本；页数不足须标明截断。统计值为零、无数据与请求失败分开。
5. 给结论、业务口径、范围和限制即可结束。要求下载/完整报告时再读 `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/delivery.md`；标准统计无法回答时才转明细快照分析。

| 产品页 | CLI 命令 | 关键输入 |
|---|---|---|
| 数据总览 | ticket reports-overview | startDate/endDate 和渠道/客服过滤 |
| 今日工单 | ticket reports-today | 服务端今日口径 |
| 新增工单 | ticket reports-growth | dateType/queryMetrics；日期范围 |
| 回复概览 | ticket reports-responses | dateType；日期范围 |
| 消息处理表现 | ticket reports-performance-v1 | 与当前前端一致的旧统计契约 |
| UTC 绩效 | ticket reports-performance-v2 | 明确 timezone 及时间范围，不能默默替换 V1 |
| 数据更新时间 | ticket reports-freshness | 无 |
| 队列监控/等待 | ticket reports-queues / ticket reports-waiting | 等待列表传 queueId |
| 看板概览/单图/表格 | ticket reports-dashboard / ticket reports-chart / ticket reports-table | domain/tabKey；单图另传 chartKey，表格另传 tableKey |

全部命令使用 `node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket <action>`；参数见下方业务查询，或对应命令的 `--help`。

| domain | 已有 tabKey |
|---|---|
| support | tickets、efficiency、assignee、updates、unsolved、satisfaction、sla |
| chat | chats、efficiency、satisfaction、activity、concurrency |
| voice | calls、efficiency、activity |

先查询 dashboard，使用响应实际提供的 chart/table 标识；没有标识就报告缺口，不猜 key。表格保留 pageNum/pageSize 和服务端总量，完整导出不能只导出第一页。

复杂历史明细取数见 `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/workflow.md`，完整报告交付见 `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/delivery.md`。raw 接口的自然日窗口当前仅支持 Asia/Shanghai；旧统计、V2 绩效、新看板分别有自己的时间参数，不混用。后端缺失指标不能填 0；当前快照计算必须标注来源和采集时刻。

产品前端引用的独立 SLA summary 接口尚未在本地后端闭环；查询 SLA 看板或已知工单证据，不调用猜测接口。不创建远程导出任务；可以对完整已取数结果在本地生成文件，并保留口径及截断信息。

## 产品报表取数

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-analytics/<唯一文件名>.json` 保存。

### 历史指标与绩效

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket reports-overview` | timezone:string, startDate:string, endDate:string, startTime:string, endTime:string, channelList:array, agentIdList:array, supportEmailIdList:array, platformList:array, channelIdList:array, dateType:string, replyAgentQueryType:string, queryMetrics:string, dataType:string | 单次响应；保留服务端分页字段 |
| `ticket reports-growth` | timezone:string, startDate:string, endDate:string, startTime:string, endTime:string, channelList:array, agentIdList:array, supportEmailIdList:array, platformList:array, channelIdList:array, **dateType**:string, replyAgentQueryType:string, **queryMetrics**:string, dataType:string | 单次响应；保留服务端分页字段 |
| `ticket reports-responses` | timezone:string, startDate:string, endDate:string, startTime:string, endTime:string, channelList:array, agentIdList:array, supportEmailIdList:array, platformList:array, channelIdList:array, **dateType**:string, replyAgentQueryType:string, queryMetrics:string, dataType:string | 单次响应；保留服务端分页字段 |
| `ticket reports-performance-v1` | timezone:string, startDate:string, endDate:string, startTime:string, endTime:string, channelList:array, agentIdList:array, supportEmailIdList:array, platformList:array, channelIdList:array, dateType:string, replyAgentQueryType:string, queryMetrics:string, dataType:string | 单次响应；保留服务端分页字段 |
| `ticket reports-performance-v2` | **timezone**；日期范围、时区及渠道/客服过滤；完整参数见命令 --help | 单次响应；保留服务端分页字段 |
| `ticket reports-raw` | **startTime**:string, **endTime**:string, timeRangeType:string, page:integer, pageSize:integer | 支持 `--all`；检查截断 |

### 当前监控与筛选选项

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket reports-today` | 无 | 单次响应；保留服务端分页字段 |
| `ticket reports-freshness` | 无 | 单次响应；保留服务端分页字段 |
| `ticket reports-options` | 无 | 单次响应；保留服务端分页字段 |
| `ticket reports-queues` | 无 | 单次响应；保留服务端分页字段 |
| `ticket reports-waiting` | **queueId**:string | 单次响应；保留服务端分页字段 |

### Support / Chat / Voice 下钻

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket reports-dashboard` | **domain**、**tabKey**；startDate/endDate；渠道/客服/团队过滤；table 可传 pageNum/pageSize | 单次响应；保留服务端分页字段 |
| `ticket reports-chart` | **domain**、**tabKey**、**chartKey**；startDate/endDate；渠道/客服/团队过滤；table 可传 pageNum/pageSize | 单次响应；保留服务端分页字段 |
| `ticket reports-table` | **domain**、**tabKey**、**tableKey**；startDate/endDate；渠道/客服/团队过滤；table 可传 pageNum/pageSize | 支持 `--all`；检查截断 |
