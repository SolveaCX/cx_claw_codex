# 客服平台接入与诊断

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## Zendesk

授权与配置步骤先查帮助文档（检索线索见 `onboarding.md`）。对已有连接，先读 settings；已有 attemptId 才查 auth-result。按问题查 views、supportAddresses、agents 和字段映射；仍异常时用 diagnose 看失败/跳过步骤，或用外部 ticketId 查 trace。外部工单 ID 不当作客服工单号；配置存在不证明真实收发成功。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration zendesk-settings` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-agents` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-views` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-support-addresses` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-ticket-fields` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-ai-field-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-ai-variable-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-ticket-field-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zendesk-auth-result` | **attemptId**:string | 单次响应；保留服务端分页字段 |
| `integration zendesk-diagnose` | ticketId:integer, sampleLimit:integer | 单次响应；保留服务端分页字段 |
| `integration zendesk-trace` | externKeyId:integer, **ticketId**:string | 单次响应；保留服务端分页字段 |
| `integration zendesk-history-status` | 无 | 单次响应；保留服务端分页字段 |

## Zoho

Zoho 专页与集成总览可能对协助/自助接入口径不一致；先读区域/组织与 Department/View，再以当前入口确认接入方式，区分 Desk 与 IM。已有连接依次核对 auth-status/settings、departments/views、bot-binding；涉及字段或意图才读 mapping/process-rules/intent-tagging。orgId 来自实际上下文，不猜 ID；diagnose 的 sampleLimit 最大 50，无样本不推断链路正常。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration zoho-settings` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-auth-status` | orgId:string | 单次响应；保留服务端分页字段 |
| `integration zoho-bot-binding` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-intent-tagging` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-process-rules` | orgId:string | 单次响应；保留服务端分页字段 |
| `integration zoho-ticket-fields` | orgId:string | 单次响应；保留服务端分页字段 |
| `integration zoho-departments` | orgId:string | 单次响应；保留服务端分页字段 |
| `integration zoho-views` | orgId:string, departmentId:string | 单次响应；保留服务端分页字段 |
| `integration zoho-ai-field-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-ai-field-config` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-ticket-field-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-custom-field-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-ai-variable-mapping` | 无 | 单次响应；保留服务端分页字段 |
| `integration zoho-diagnose` | ticketId:string, orgId:string, sampleLimit:integer | 单次响应；保留服务端分页字段 |
| `integration zoho-history-status` | 无 | 单次响应；保留服务端分页字段 |

## 其他客服平台

按实际平台检索接入说明，不把协助接入平台当作自助配置。已有连接读各自 settings，涉及客服再查 agents，历史数据问题再查 history-status；Freshdesk automations 核对已有自动规则。无专属诊断命令时止于配置证据，不套用 Zendesk diagnose。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration freshdesk-settings` | 无 | 单次响应；保留服务端分页字段 |
| `integration liveagent-settings` | 无 | 单次响应；保留服务端分页字段 |
| `integration sunshine-settings` | 无 | 单次响应；保留服务端分页字段 |
| `integration sunshine-history-status` | 无 | 单次响应；保留服务端分页字段 |
| `integration freshdesk-agents` | 无 | 单次响应；保留服务端分页字段 |
| `integration freshdesk-automations` | 无 | 单次响应；保留服务端分页字段 |
| `integration liveagent-agents` | 无 | 单次响应；保留服务端分页字段 |
| `integration shulex-ticket-status` | 无 | 单次响应；保留服务端分页字段 |
| `integration shulex-ticket-emails` | 无 | 单次响应；保留服务端分页字段 |
