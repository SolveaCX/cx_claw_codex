# 电商店铺接入与同步查询

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## 查店铺和授权详情

先按平台文档解释店铺/站点和接入步骤。授权后 list 定位店铺，再使用对应 get。eBay/Shopify get 的 state 只能来自受信任产品上下文，不是列表 id；缺少时说明可验证范围，不索要或伪造 OAuth state。已授权与订单/商品已同步分别判断。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration tiktok-settings` | 无 | 单次响应；保留服务端分页字段 |
| `integration tiktok-apps` | 无 | 单次响应；保留服务端分页字段 |
| `integration amazon-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration ebay-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration shopify-list` | keyword:string, personaId:integer | 单次响应；保留服务端分页字段 |
| `integration walmart-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration rakuten-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration amazon-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration ebay-get` | **state**:string | 单次响应；保留服务端分页字段 |
| `integration shopify-get` | **state**:string, personaId:integer | 单次响应；保留服务端分页字段 |
| `integration shopline-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration shopline-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration shopify-countries` | **channelId**:string | 单次响应；保留服务端分页字段 |

## 检查同步进度

按订单、商品或目录区分已有任务，catalog 的 projectId 来自当前项目。核对状态、范围和时间；无记录不等于失败，未完成不报成功。客户尚未启动时按文档指导产品操作，不由 CLI 发起同步。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration sync-orders` | 无 | 单次响应；保留服务端分页字段 |
| `integration sync-products` | 无 | 单次响应；保留服务端分页字段 |
| `integration sync-catalog` | **projectId**:integer | 单次响应；保留服务端分页字段 |
