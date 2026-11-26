# 邮箱、聊天与语音渠道接入

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## 邮箱

先问清或从上下文识别邮箱服务商和产品所选方式；纯咨询时说明进入 Email 集成、选择页面支持的方式、由客户完成授权/转发配置及验证。DNS、端口、转发目标等必须来自当前产品说明，不生成通用值让客户照填。

已有连接先 integration email-list/get，涉及收取范围再查 folders；Gmail 连接使用 integration gmail-list 辅助定位。配置正确仍无邮件时需要已有邮件的时间/文件夹或返回错误作为证据。下一步具体指向授权、收件范围或产品验证提示；不发送测试邮件，不宣称已验证投递。

先查邮箱列表/详情和文件夹，核对客户的邮箱服务商及接入方式；DNS、转发、OAuth 授权由客户在产品处理，本期不发送验证邮件。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration gmail-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration email-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration email-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration email-folders` | **id**:string | 单次响应；保留服务端分页字段 |

## LINE 与 WhatsApp

指导客户在对应渠道卡片完成平台授权及账号选择，平台账号、号码与产品显示名称应一致。操作后先 list，再按返回的渠道标识 get；核对状态和账号/号码。查询只验证已有连接信息，消息是否送达要有已有消息证据。客户卡在平台账号权限/验证步骤时依照当前页面提示答疑，不索要验证码、密钥或代发测试消息。

查渠道 ID、显示名称和状态；不要索取 access token，不发验证码或测试回复。模板审核查询使用工单配置能力。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration line-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration line-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration whatsapp-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration whatsapp-get` | **id**:string | 单次响应；保留服务端分页字段 |

## LiveChat 与电话

LiveChat：先确认目标站点和 Agent；客户从产品安装入口取得其专属安装信息并自行部署。已有 botId 时查 config/setup，核对配置是否属于目标 Agent；客户说已安装仍不显示时，先核对实际站点与当前产品安装说明，不能仅凭配置存在判断前端已加载。

电话：先确认项目和目标号码，客户在产品完成可用的授权/绑定步骤；list 后以 phoneId 查详情。仅核对已有号码与绑定，不购买号码、不发起通话。没有运行证据时止于配置验证。


用 botId 查 LiveChat 当前配置/安装信息，用 projectId 和 phoneId 查号码。读取 setup 是查看安装信息，不会代客户安装；页面专属配置未覆盖时明确说明。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration livechat-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration livechat-config` | source:string, t:integer, **botId**:string | 单次响应；保留服务端分页字段 |
| `integration livechat-setup` | **botId**:string | 单次响应；保留服务端分页字段 |
| `integration phone-list` | search:string, page:integer, limit:integer, **projectId**:string | 单次响应；保留服务端分页字段 |
| `integration phone-get` | **projectId**:string, **phoneId**:string | 单次响应；保留服务端分页字段 |
