# 客户、订单与导入记录

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-helper/<唯一文件名>.json` 保存。

## 客户及关联工单

1. 只有姓名/邮箱时先用 `ticket customers-list` 查候选；已有 customerId 直接 `ticket customers-get`。同名时用已知邮箱/电话核对，不猜第一条。
2. 用户只问客户信息时就此回答；要关联工单时还需当前 ticketNumber，再用 `ticket related`。只有客户 ID、没有工单号时先按已确认的客户条件查 `ticket list`。
3. 返回客户身份匹配依据、请求的信息及关联工单范围。联系人空结果与查无权限分别说明。

先查客户详情再查关联工单；同名客户用邮箱或其他已知信息消歧。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket related` | **customerId**:integer, **ticketNumber**:string, page:integer, pageSize:integer, sort:string, order:string | 支持 `--all`；检查截断 |
| `ticket customers-list` | keyword:string, personaId:integer, emotionType:string, sortOrder:string, pageNum:integer, pageSize:integer | 支持 `--all`；检查截断 |
| `ticket customers-get` | **customerId**:string | 单次响应；保留服务端分页字段 |

## 订单和物流

1. 有客服工单号先 `ticket orders`，确认订单属于该客户和渠道。多个订单按订单号/时间消歧。
2. Shopify 详情使用返回的 channelAuthId 与订单 ID/名称；物流使用实际 orderNumber/trackingNumber，不将工单号当订单号。
3. 仅在用户问运输进度时再查物流。回答最近状态、时间和来源；接口未返回原因时不推断丢件、退款成功或履约完成。

先从工单取订单，按平台 ID 查询详情；物流需要订单号与运单号。只解释订单状态，不退款或修改。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket orders` | **ticketNumber**:string | 单次响应；保留服务端分页字段 |
| `ticket logistics` | **orderNumber**:string, **trackingNumber**:string | 单次响应；保留服务端分页字段 |
| `ticket shopify-order` | **channelAuthId**:integer, **shopifyOrderId**:string | 单次响应；保留服务端分页字段 |
| `ticket shopify-order-name` | **channelAuthId**:integer, **shopifyOrderName**:string | 单次响应；保留服务端分页字段 |

## 已有导入任务与文件

用户问当前导入先 `ticket customers-import-current`；有 taskId 直接 `ticket customers-import-task`。按返回状态、成功/失败数量及可用原因解释；任务仍进行时不要报完成。只有用户要文件才执行下面的下载命令，下载后给文件，不把获得 URL 当完成下载。

只查已有导入进度。导出和导入模板为直接文件下载，必须提供唯一 --output 路径，100 MiB 上限；下载模板不会提交导入任务。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket customers-import-current` | 无 | 单次响应；保留服务端分页字段 |
| `ticket customers-import-task` | **taskId**:string | 单次响应；保留服务端分页字段 |
| `ticket customers-export` | keyword:string, personaId:integer, emotionType:string, sortOrder:string | 文件下载，必须 --output；100 MiB 上限 |
| `ticket customers-import-template` | 无 | 文件下载，必须 --output；100 MiB 上限 |
