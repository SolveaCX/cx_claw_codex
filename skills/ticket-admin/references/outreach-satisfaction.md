# 触达记录、模板与满意度配置

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-admin/<唯一文件名>.json` 保存。

## 满意度与模板

1. 区分满意度问卷、WhatsApp 模板和普通模板，不把一类模板的状态用于另一类。
2. 满意度先查 templates，再按 templateId/language 查 versions；问自动发送才补 satisfaction-auto-send。开关开启只说明当前配置，某张工单是否发送还需对应处理记录。
3. WhatsApp 先查 accounts 得到 wabaId，再查 templates/template；保留模板名、语言和审核状态，不因存在模板就宣称可发送给所有客户。
4. 用户只是确认配置/审核结果时直接回答；缺少发送证据时说明“尚不能确认是否实际发送”，不测试发送。

只查配置、版本、语言和审核状态。自动发送开关的现值可以解释，但不能更改或发送消息。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-satisfaction-templates` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-satisfaction-versions` | templateId:integer, language:string | 单次响应；保留服务端分页字段 |
| `ticket admin-satisfaction-auto-send` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-whatsapp-accounts` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-whatsapp-templates` | **wabaId**:string, page:integer, limit:integer, includeTotal:boolean, name:string | 支持 `--all`；检查截断 |
| `ticket admin-whatsapp-template` | **name**:string, **language**:string, **wabaId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-templates` | page:integer, size:integer | 支持 `--all`；检查截断 |

## 追踪已有触达

1. 先定位计划，再查 runs 和目标 run；时间范围、状态和计划 ID 保持一致。
2. 总体进度足够就结束；用户追问具体客户失败时才查 recipients/attempts，追问导入行才查 import/import-rows。
3. 分别给成功、失败、处理中及缺失范围；失败原因引用返回值，重试/重跑只给建议。这里是已有任务查询，不是本期回信能力。

从计划定位 run，再查接收人、发送尝试和导入行；各层 ID 不互换。只能解释已有结果，不重试、启动或提交任务。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-outreach-plans` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-outreach-runs` | **planId**:string, page:integer, pageSize:integer | 支持 `--all`；检查截断 |
| `ticket admin-outreach-run` | **planId**:string, **runId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-outreach-import` | **importId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-outreach-attempts` | **recipientId**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-outreach-recipients` | **planId**:string, **runId**:string, page:integer, pageSize:integer | 支持 `--all`；检查截断 |
| `ticket admin-outreach-import-rows` | **importId**:string, afterRow:integer, limit:integer, validOnly:boolean | 单次响应；保留服务端分页字段 |
