# Desk 当前工单列表接口

`solvea-desk fetch-tickets` 忠实封装 `/api_v2/tars/api/ticket/list`：把受支持的请求条件传给后端，按接口分页拉取，并将响应列表原样写入 `datasource.xlsx` 的 `data` sheet。脚本不增加业务筛选语义，也不修改返回结果集。

## 请求参数说明

分页和视图参数使用独立 CLI 参数：

| CLI 参数 | 后端字段 | 说明 |
|---|---|---|
| `--view-id` | `viewId` | 工单视图 ID，默认 `1`；视图条件与当前用户数据权限共同生效 |
| `--page-size` | `pageSize` | 每页数量，范围 1～100 |
| `--sort` | `sort` | 排序字段，默认 `last_update_time` |
| `--order` | `order` | `ASC` 或 `DESC`，默认 `DESC` |
| `--max-pages` | 不下发 | 客户端安全上限 |
| `--max-rows` | 不下发 | 客户端安全上限 |

业务过滤条件通过 `--filters-json` 或 `--filters-file` 传入 JSON 对象。字段名与 Tars `TicketListPageDTO` 一致，并在 Elasticsearch 查询阶段执行。

`page`、`pageSize`、`viewId`、`sort`、`order` 不允许放进过滤对象，避免覆盖脚本控制的分页与视图参数。

| 维度 | JSON 字段 | 值类型/含义 |
|---|---|---|
| 工单号 | `ticketNumber`、`ticketNumberList` | 字符串、字符串数组 |
| 状态 | `ticketStatusList` | 字符串数组 |
| 渠道/平台 | `channelList`、`platformList` | 字符串数组 |
| 店铺/邮箱/电话入口 | `channelIdList`、`supportEmailIdList`、`supportPhoneList` | ID 数组、ID 数组、字符串数组 |
| 当前负责人 | `agentIdList` | 用户 ID 数组，不接受姓名 |
| 回复人条件 | `replyUserList` | 用户 ID 数组；这是列表查询条件，不等于报表事实中的 `responder` |
| 标签 | `tagList`、`noTag` | ID 数组、布尔值 |
| 客户 | `customerEmail`、`customerName`、`customerEmailFull`、`customerPhone` | 字符串 |
| 创建时间 | `createTimeBegin`、`createTimeEnd` | 带 offset 的 ISO-8601 时间字符串 |
| 综合搜索 | `keyword` | 匹配正文、备注、主题、客户、工单号或订单号等后端搜索字段 |
| 市场/订单 | `marketList`、`orderId` | 字符串数组、字符串 |
| 品类/品牌 | `categoryList`、`brandList` | 字符串数组 |
| 处理状态 | `humanHandling`、`myTicket`、`snoozed`、`scheduled` | 布尔值 |
| 排除项 | `notSpam`、`notNotification` | 布尔值 |
| Bot/Persona | `botIdList`、`personaId` | ID 数组、ID |
| 未读/发送失败 | `unread`、`sendFailure` | 布尔值 |
| Campaign | `campaignName` | 字符串 |
| Voice | `lastVoiceAnswerType`、`lastVoicePhoneType` | 字符串 |

示例：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-tickets \
  --view-id 1 \
  --filters-json '{"channelList":["ebay"],"agentIdList":[474501],"ticketStatusList":["open","pending"]}' \
  --page-size 100 \
  --sort last_update_time \
  --order DESC
```

只下推值已经明确的条件。用户只给负责人姓名时不要猜 `agentId`；可以下推其他已知条件，再在响应字段 `agent` 上完成本地分析。

接口不支持按 `lastMessageTime`、`lastResponseTime`、`firstAgentResponseTime` 或 `lastUpdateTime` 传时间范围。用户要求这些口径时，先按后端已有条件拉取，再由 `analysis step` 对响应字段进行筛选。不要创造额外的 fetch 参数或偷偷替换时间字段。

脚本根据响应 `total` 判断是否还有下一页；没有 `total` 时以当前页是否满页兜底。`manifest.json.truncated=true` 表示命中 `max-pages` 或 `max-rows`，不能声称已经获取全部工单。原始分页响应保存在 `tmp_task_dir/raw_page_*.json`，仅用于排查和重放。

## 响应参数说明

这是当前用户权限和指定 `viewId` 下的**当前工单列表快照**，不是历史报表事实。工单后来被重新分配、回复或关闭后，再次拉取时字段可能变化。

| 字段 | 含义 | 使用提醒 |
|---|---|---|
| `id` | 工单内部 ID | 对应报表快照的 `ticketId` |
| `ticketNumber` | 对外工单编号 | 展示和跨快照关联优先使用 |
| `channel` / `channelId` | 渠道及渠道授权 ID | `channelId` 可区分店铺或渠道实例 |
| `customerEmail` / `customerName` / `customerPhone` | 当前客户信息 | 输出时注意隐私 |
| `area` / `language` | 地区和语言 | 空值表示当前工单没有可用值 |
| `touchMethod` | 工单创建/触达方式 | 枚举以接口实际返回为准 |
| `creatorId` / `creator` | 创建人 ID / 姓名 | 当前展示值 |
| `createTime` | 工单创建时间 | 接口按 UTC 序列化，分析时转换到业务时区 |
| `ticketType` | 工单类型 | 枚举以接口实际返回为准 |
| `ticketStatus` | 当前工单状态 | 不是历史时点状态 |
| `subject` / `title` | 工单主题和标题 | 两者可能相同或其中一项为空 |
| `agentId` / `agent` | 当前负责人 ID / 姓名 | 不代表某一条历史回复的实际发送人 |
| `notes` / `lastNotes` | 备注相关字段 | 以实际返回内容为准 |
| `lastMessageTime` | 最近客户来信时间 | 不等于回复时间 |
| `lastResponseTime` | 当前记录的最近回复时间 | 后续回复会改变这个值 |
| `firstAgentResponseTime` | 客服首次回复时间 | 可与 `createTime` 计算当前列表口径的首响时效 |
| `sendFailureTime` | 最近发送失败时间 | 为空表示没有可用记录 |
| `lastUpdateTime` | 最近来信与最近回复中的较晚时间 | 默认列表排序字段对应的业务时点 |
| `slaHours` / `slaMinutes` | 当前剩余 SLA | 动态值，不适合作为历史处理时长 |
| `read` | 当前是否已读 | 当前状态 |
| `supportEmail` | 售后邮箱 | 由后端补充的展示字段 |
| `tagInfoList` | 标签完整路径信息 | 通常为嵌套 JSON，可辅助分类 |
| `customerStatus` | 当前客户状态 | 当前状态 |
| `replied` | 最后一封来信是否已回复 | 只描述当前最后一封来信 |
| `lastMessageContent` | 最后一封客户来信内容 | 可用于正文分类；不是完整消息历史 |
| `snoozed` / `snoozedTime` | 稍后处理状态和时间 | 当前状态 |
| `botId` / `botName` | Bot ID / 名称 | 由工单索引和后端补充字段组成 |
| `scheduled` / `scheduledTime` | 定时处理状态和时间 | 当前状态 |
| `voiceAnswerType` / `voiceDuration` / `voicePhoneType` | Voice 接听类型、时长和方向 | 仅相关 Voice 工单有值 |
| `voiceSummary` / `voiceMessageType` | Voice 摘要和消息子类型 | 仅相关 Voice/SMS 工单有值 |
| `providerDeliveryStatus` | SMS 服务商送达状态 | 仅 SMS 工单有值 |

与 `/api_v2/tars/api/ticket/report/raw/page` 历史报表事实的关键边界：

- 当前列表的 `agent` 是当前负责人；报表事实的 `responder`、`resolver` 分别表示实际回复人和解决人。
- 当前列表提供 `subject`、`title`、`lastMessageContent`；报表事实不提供消息正文。
- 当前列表时间字段反映当前记录；报表事实按回复日/解决日或创建日形成时间范围。
- 联合分析时优先用 `ticketNumber`，内部 ID 则用 `id` 对应报表的 `ticketId`，并注明两个快照的生成时间。
