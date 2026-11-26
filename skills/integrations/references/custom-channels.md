# 自研渠道与外部数据接入

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## 自研工单和 LiveChat

准备材料和 Webhook 使用方式先读帮助文档；实际工单请求协议再用 `integration custom-ticket-docs` 获取，不发明 payload，也不照搬为 LiveChat 协议。客户保存后 list/get 核对安全配置，历史同步问题查 status/progress；真实交互需要已有样本。专属 Webhook 由客户在产品获取，不回显凭据或调用任意测试接口。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration custom-ticket-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration custom-ticket-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration custom-ticket-history-status` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration custom-ticket-history-progress` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration custom-livechat-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration custom-livechat-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration custom-livechat-history-status` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration custom-livechat-history-progress` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration custom-ticket-docs` | 无 | 单次响应；保留服务端分页字段 |

## 自定义数据/API

按帮助文档解释配置和用途，已有 custom-data 查 list/get，API 用 projectId 查 list。本版没有任意 API 详情或执行入口；列表可见只证明资源存在，不证明外部调用成功。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration custom-data-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration custom-data-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration api-list` | **projectId**:integer | 单次响应；保留服务端分页字段 |
