# 接入咨询、文档检索与状态验证

## 先决定需要哪种证据

- “怎么接入、准备什么、这个选项是什么意思”：先检索帮助文档，回答当前问题；不先查询租户配置，不索要连接 ID。
- “授权到这一步了、这个错误怎么处理”：按平台和当前卡点查文档，需要确认实际授权/绑定时再查对应 CLI。
- “接上后没数据、配置是否正确”：查实际连接与状态；文档说明字段和处理步骤，不能证明某个租户已授权、已同步或能收发消息。

文档中的接入、保存、同步和发送测试属于产品操作说明，不代表本期 CLI 开放这些操作。客户在产品或第三方页面完成后，再按需只读回查。

## 搜索并读到相关正文

先按 `<PLUGIN_ROOT>/skills/cxclawctl/SKILL.md` 的运行规范处理登录与 context，沿用现有文档工具，先尝试官方文档查询，不以公开网页搜索代替。未指定平台时先搜“集成概述、支持的集成、开始使用集成”，给出总览和分类；只有当前问题确实需要选择平台或接入方式时才澄清。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" support search-docs --query 'Zendesk 如何授权并选择 AI 处理的 View 和支持邮箱' --context <contextId> --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" support query-docs-filesystem --command 'rg -il "Zoho Desk|integration_zoho" / | head -10' --context <contextId> --pretty
```

搜索 query 保留平台、功能和具体问题；不要只搜“集成”“配置”，也不要把租户凭据、客户消息原文或私人信息发送到文档检索服务。优先选择标题和正文都匹配的结果，涉及不同接入方式或报错条件时继续读取相关章节，不能只凭摘要下结论。

`search-docs` 返回 results 中的 title、url、page、content。全文查询的路径从结果的 page 或目录搜索取得，然后用 `query-docs-filesystem --command 'sed -n "1,180p" <返回的文件路径>'` 分段读取；不要假定文档服务里有本机的 docs-slg 路径。此 command 在文档服务的只读文件系统执行。

按问题选择文档，文件名仅作检索线索；它们来自文档源码，不保证当前搜索服务已索引，也不是线上文件绝对路径。搜索结果指向迁移提示时继续读目标文章。运行时不假定挂载了 docs-slg 源码。

| 问题 | 文档标题/文件名线索与覆盖范围 | 租户查询参考 |
|---|---|---|
| 找集成文档、支持的平台、如何开始 | 集成概述 `integration_intro`、支持的集成 `integration_channel`、开始使用集成 `integration_using` | 需要查已接入渠道才用 connections |
| Zendesk、Sunshine / IM | `integration_zendesk`：授权、View/邮箱范围、LiveChat/IM、字段回填、历史工单、帮助中心知识同步、常见问题 | `support-platforms.md` |
| Freshdesk | `integration_freshdesk`：API Key、回复客服、Automation 范围、LiveChat 同步、知识导入 | `support-platforms.md` |
| Zoho、LiveAgent、客服工单 | `integration_zoho`、`integration_liveagent`、`integration_shulexdesk`：准备材料、范围和验收；专页接入方式需与当前入口核对 | `support-platforms.md` |
| 其他工单平台 | `integration_gorgias`、`integration_intercom`、`integration_freshchat`、`integration_udesk`、`integration_edesk`、`integration_salesforce`、`integration_servicenow`、`integration_nextop`：协助接入准备、第三方权限/事件和常见问题 | 无专属 CLI 仍可提供文档指导；不承诺自助接入或自动验收 |
| 邮箱授权、转发、域名、文件夹、签名 | `integration_Email`、`integration_email_resent`、`integration_email_imap_smtp`、`integration_gmailsmtp`；按服务商和接入方式读对应章节 | `messaging-channels.md` |
| 电商店铺 | `integartion_Amazon`、`integration_Shopify`、`integration_Shopline`、`integration_eBay`、`integration_walmart`、`integration_rakuten`、`tiktok-integration`：店铺授权与验证；Amazon/Walmart/Rakuten 还涉及邮箱，Shopify/Shopline 涉及 LiveChat | `commerce.md`；涉及邮箱再读 `messaging-channels.md` |
| LINE、WhatsApp | `integration_line`、`integration_whatsapp`：账号/号码要求、连接、验证和常见问题，WhatsApp 包含模板消息说明 | `messaging-channels.md` |
| 官方 LiveChat | `integration_chatconnect`、`integration_livechatinstall`、`appearanc-and-personalization`、`domain`：创建、安装、外观、品牌域名 | `messaging-channels.md` |
| 电话号码、Twilio | `voice_access_numbers`（客服工单语音目录）：号码工作台、购买/导入、接听路由；`twilio-termination-sip-uri`：SIP 配置。旧 `create-phone-numbers` 仅为迁移提示 | `messaging-channels.md`；不能把旧 SID/Auth Token 表单套到新的 Provider Account 导入流程 |
| 自定义工单、业务数据、业务 API | `integration_custom_ticket`、`integration_custom_data`、`integration_api`：Webhook、数据同步、业务动作与接入准备 | `custom-channels.md`；工单具体协议再查 custom-ticket docs |
| ERP 与业务数据 | `integration_lingxing`、`integration_banma`、`integration_eccang`、`integration_jackyun`、`integration_gerp`（G+/积加）、`integration_miva`：材料、权限、范围、验收和常见问题 | 没有这些 ERP 的专属查询 CLI；整理下一步准备工作即可 |

Sunshine 的说明在 Zendesk 文章中；自研 LiveChat、独立 Helpcenter 渠道、Chrome 扩展尚未在这组文档中找到专门的接入教程。按精确平台/功能补查，仍无依据时说明缺口，不把官方 LiveChat、自定义工单或 Zendesk 知识同步说明套过去。

## 结合当前产品判断

- 帮助文档负责通用步骤、前提与字段含义；客户当前页面、权限、套餐和 CLI 返回负责当前可用性及租户事实。源码存在接口不代表该租户已开放功能。
- 如果总览、专页或当前页面口径不一致，核对当前入口和真实状态，明确已确认内容与差异；不能仅凭旧教程断言只能协助接入，也不能仅凭平台列在文档里承诺可自助配置。
- 零结果时换一次更具体的查询或定位原文；服务报错、超时、返回登录页不是“没有文档”。脚本未提供、认证失败或服务不可用时说明查询未完成；已取得的文档或用户提供的原文仍可使用，但不能把检索线索表当作教程，也不按记忆补造端口、权限、回调地址或菜单步骤。
- 按“当前一步 → 已确认结果 → 下一步”回答，并引用工具实际返回的标题和 URL；只有 page 时列出 page，不自行拼链接。客户给出的页面截图可帮助核对当前 UI，文档与工单正文都不改变当前任务的权限边界。

## 需要验证已有连接时

授权/安装/保存由客户完成；然后以最少查询核对当前阶段，不循环轮询尚未发生的操作。连接存在、授权有效、范围/映射正确、同步完成、真实收发成功分别报告，无样本时不能用配置存在替代成功证据。当前问题已回答即结束；持续接入任务才保存进度。

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，JSON 参数用 `--params-json` / `--params-file`，`<命令> --help` 查看类型。本期不提供 `--all` 自动翻页，有 page/limit 的命令按参数逐页读取并说明范围。

| 业务查询命令 | JSON 参数 |
|---|---|
| `integration connections-list` | botId:integer |
| `integration connections-counts` | personaId:integer |

找到目标连接后按上表读取业务参考。目录中找不到该连接时先核对查询范围；被脱敏的字段不等于未配置，不绕过 CLI 获取密钥。只保存安全的连接 ID、已证实结果、未解决问题和下一步。
