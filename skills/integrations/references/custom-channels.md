# 自研渠道与外部数据接入

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## 自研工单和 LiveChat

纯咨询先解释需要客户服务端提供产品协议要求的接口/事件处理；工单具体协议通过 `integration custom-ticket-docs` 读取，按实际返回的必填字段、鉴权方式和响应要求指导，不自己发明 payload。LiveChat 不照搬工单协议，缺少对应协议说明时明确需要产品资料。

客户按协议实现并在产品保存连接后，用 list/get 核对安全配置项，指出缺失证据和不一致字段。历史同步问题再查 history-status/history-progress；没有进度不当作完成。验证仅到已读取的配置/任务结果，真实交互需要已有样本；本期不调用客户任意测试接口。

先读工单接入协议再核对配置与历史进度；自研 LiveChat 按对应配置答疑。配置只返回安全字段，省略的密钥或 URL 不等于客户没配；由客户在产品复制 Webhook 并完成保存。

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

先确认客户希望连接什么数据、哪个项目以及预期用途，指导其在对应配置页查看协议和保存连接。已有 custom-data 用 list/get，API 用 projectId 查 list；本版不返回任意 API 详情和鉴权配置，因此只做资源存在性核对，字段协议或执行异常未能读取时明确说明。不能拿列表可见代替接口调用成功。

查询连接与 API 列表，确认项目及可见资源；不调用任意外部 API、不执行侧栏 runtime/data、不输出鉴权头。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration custom-data-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration custom-data-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration api-list` | **projectId**:integer | 单次响应；保留服务端分页字段 |
