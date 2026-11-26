# 邮箱、聊天与语音渠道接入

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

本期 integrations 命令不提供 `--all` 自动翻页；有 page/limit 的命令按参数逐页读取并说明范围。JSON 快照用 `--output <WORKSPACE>/outputs/integrations/<唯一文件名>.json` 保存。

## 邮箱

服务商与接入方式决定要读 OAuth、转发还是 IMAP/SMTP 文档；端口、DNS、应用密码和转发步骤从对应原文取得。已有连接查 email list/get，收取范围查 folders，Gmail 用 gmail list 辅助定位。收不到邮件需结合已有邮件时间/文件夹或错误；不发送验证邮件，不把配置存在当作投递成功。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration gmail-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration email-list` | keyword:string | 单次响应；保留服务端分页字段 |
| `integration email-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration email-folders` | **id**:string | 单次响应；保留服务端分页字段 |

## LINE 与 WhatsApp

授权、号码和账号要求查对应帮助文档；已有连接先 list，再以返回 ID 查 get，核对账号/号码和状态。模板审核查询复用 ticket-admin；不索要验证码或 token，不发送测试消息。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration line-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration line-get` | **id**:string | 单次响应；保留服务端分页字段 |
| `integration whatsapp-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration whatsapp-get` | **id**:string | 单次响应；保留服务端分页字段 |

## LiveChat 与电话

网站安装查 LiveChat 文档，电话号码优先查 `voice_access_numbers`；新号码工作台与旧 Twilio 导入页的材料不同，以当前页面为准。LiveChat 使用已知 botId 查 config/setup，但配置存在不代表网站已安装；电话先按 projectId 查 list，再以 phoneId 查 get。只核对已有安装信息、号码和绑定，不安装网站脚本、不购买号码或发起通话。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `integration livechat-list` | 无 | 单次响应；保留服务端分页字段 |
| `integration livechat-config` | source:string, t:integer, **botId**:string | 单次响应；保留服务端分页字段 |
| `integration livechat-setup` | **botId**:string | 单次响应；保留服务端分页字段 |
| `integration phone-list` | search:string, page:integer, limit:integer, **projectId**:string | 单次响应；保留服务端分页字段 |
| `integration phone-get` | **projectId**:string, **phoneId**:string | 单次响应；保留服务端分页字段 |
