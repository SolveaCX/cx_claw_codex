# 电商店铺接入与同步查询

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## 查店铺和授权详情

**准备**：确认平台、店铺/站点、目标 Agent，以及需要订单还是商品数据。指导客户在对应电商集成卡片完成授权并核对选中的店铺；授权账号权限以平台页面为准。

**推进**：客户授权后先查平台 list，以店铺和站点匹配连接；有多个匹配时先消歧，再用该平台支持的 get 查询。eBay/Shopify 的 state 只能用受信任产品上下文里已有的值；缺少时仅报告列表可验证的信息并引导产品内核对，不能索要 OAuth state 或伪造它。

**结果**：分别说清找到哪家店铺、可读取哪些配置、哪些字段未验证；需要数据同步才进入下一节，不把“已授权”写成“订单已同步”。

客户完成授权后，先查店铺列表并确认平台、站点和目标 Agent。eBay/Shopify get 需要授权 state，不是列表 id；不得凭 ID 构造 state，缺少时回到产品授权详情定位。

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

先选 orders、products 或 catalog，catalog 所需 projectId 从当前项目上下文取。读已有任务的状态、范围和时间；客户已启动同步但无记录时核对项目/店铺和时间范围。若尚未启动，需要客户在产品执行后再回查，本期不发起任务。只有返回完成状态且范围吻合时才报告对应同步完成；商品同步完成不代表订单同步完成。

区分订单、产品与目录同步。只读已有任务，不能发起同步；没有任务记录不等于任务失败。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration sync-orders` | 无 | 单次响应；保留服务端分页字段 |
| `integration sync-products` | 无 | 单次响应；保留服务端分页字段 |
| `integration sync-catalog` | **projectId**:integer | 单次响应；保留服务端分页字段 |
