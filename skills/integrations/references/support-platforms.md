# 客服平台接入与诊断

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## Zendesk

**准备与接入**：确认 Zendesk 站点 subdomain、目标 Agent 及期望处理的 View/支持邮箱；客户使用可完成授权的账号进入产品的 Zendesk 集成入口，按页面完成授权并保存处理范围。纯咨询说明这些步骤即可。

**验证顺序**：
1. 授权后读 `integration zendesk-settings`；只有已有授权流程返回 attemptId 时才查 auth-result，不为查询重新发起授权。
2. 对照客户目标查 views、supportAddresses，涉及处理人再查 agents；配置了字段映射才读对应字段目录和 mapping，比较实际引用 ID。
3. 仍异常或客户要求验收时，用 diagnose 查返回的失败/跳过步骤；给定外部 ticketId 时用 trace 定位已有样本，外部 ID 不当作客服工单号。
4. 先报告授权/范围是否已验证，再报告样本证据；没有样本时给待验证项，不说“接入全部成功”。客户需修改的配置指出产品入口与目标值，但不代为保存。

客户在产品完成授权后，先读 settings 与授权结果；再核对客服、View、支持邮箱和映射。diagnose 查失败步骤，trace 用已有外部工单做证据；不能用配置存在证明真实收发成功。

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

**准备与接入**：先明确 Zoho Desk 还是 IM、所属区域/组织以及目标 Agent。客户在对应集成页完成授权，确认组织和处理范围；不能拿 Desk 的结果证明 IM 已配置。

**验证顺序**：
1. 对已授权连接查 auth-status 与 settings；orgId 来自实际配置/用户明确上下文，不猜组织 ID。
2. 用 departments/views 核对处理范围，再读 bot-binding；只有字段或意图处理问题才读相应 mapping/process-rules/intent-tagging。
3. 范围正确仍无处理证据时才 diagnose；保留无样本、跳过和失败步骤。ticketId 按字符串传入，sampleLimit 只控制读取样本量。
4. 授权成功但绑定不符时，下一步是客户在配置页纠正绑定后回查；无样本时提示尚未验证真实处理，不重授权碰运气。

先核对组织与授权状态，再读部门/View 和 Bot 绑定；字段映射区分工单字段、AI 字段和变量。diagnose 的 sampleLimit 最大 50；无样本时不推断渠道正常。

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

先从客户可见集成卡片确认平台和接入目标，指导客户按卡片授权/保存；角色与权限范围以实际授权页为准。授权后只读该平台 settings，涉及客服选择再查 agents，涉及历史数据才查 history-status。Freshdesk automations 用于核对已有自动规则。没有专属诊断接口时止于配置证据，不承诺 Webhook、消息收发或全链路已经通过。

Freshdesk、LiveAgent 和 Sunshine 各读自己的 settings/agents/history。没有专属诊断命令时依据配置答疑，不套用 Zendesk 的诊断接口。

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
