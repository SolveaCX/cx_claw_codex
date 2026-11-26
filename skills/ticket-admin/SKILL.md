---
name: ticket-admin
description: 查询并解释工单系统配置：自动规则、触发器、字段与表单、SLA策略、队列、满意度调查、WhatsApp模板、工具栏扩展、AI打标、成员角色、团队、排班和容量。不保存或执行修改。
---

# 工单配置

调用 CLI 前先读取 `../cxclawctl/SKILL.md`，沿用当前会话的 `--context <contextId>`。本文命令通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 执行，表格中的简写补在该入口后；`--help` 无需登录。`<WORKSPACE>` 指 `CXCLAW_WORKSPACE` 指定目录，默认 `~/.cxclaw/workspace`；状态与交付目录还可分别由 `CXCLAW_STATE_DIR`、`CXCLAW_OUTPUT_DIR` 覆盖，以 CLI 返回的绝对路径为准。


面向用户统一称“客服工单”；“售后工单（产品支持工单）”与“Inbox（Agent 会话记录）”分别按其产品语境称呼，内部服务名称和接口路径不作为产品名称解释。

先识别是解释配置还是排查具体客服工单；具体工单事实由 ticket-helper 提供，本 Skill 核对规则配置。用户未说菜单名时按问题选路径，已知菜单时用下方菜单索引。

| 用户问题 | 读取 | 判断重点 |
|---|---|---|
| 为什么自动关单/合并、怎么分单 | `<PLUGIN_ROOT>/skills/ticket-admin/references/automation.md` | 当前设置与触发条件；需要事件证据时再查触发器 |
| 某条规则为什么执行/未执行 | `<PLUGIN_ROOT>/skills/ticket-admin/references/triggers.md` | 规则配置、静态匹配与实际执行分别判断 |
| 夜间是否计时、为什么没分给某团队、容量怎么限制 | `<PLUGIN_ROOT>/skills/ticket-admin/references/routing-sla.md` | SLA、队列、排班与容量的关联 |
| 字段不显示、成员看不到菜单、AI 标签如何配置 | `<PLUGIN_ROOT>/skills/ticket-admin/references/workspace-settings.md` | 布局、角色权限或 AI 打标策略 |
| 满意度为什么没发、模板是否可用、触达进度如何 | `<PLUGIN_ROOT>/skills/ticket-admin/references/outreach-satisfaction.md` | 配置/审核/已有执行状态；不触发发送 |

先查最少的配置，按响应补关联项。说明“当前配置如何工作”与“历史上实际发生什么”的区别；没有事件证据不能只凭现在的规则推断历史原因。

按设置菜单名称定位业务文档；先读当前配置，再解释影响范围和建议。菜单可能受用户权限和灰度控制；下表表示本期查询范围，不代表每项功能已经全量验收。

| 设置菜单分组 | 产品菜单 | 本期查询与参考文档 |
|---|---|---|
| 效率 | 自动规则 | 分单规则、合并/关单、表单邮件识别：`<PLUGIN_ROOT>/skills/ticket-admin/references/automation.md` |
| 效率 | 触发器 | 规则、分类、条件选项、静态预览、执行记录：`<PLUGIN_ROOT>/skills/ticket-admin/references/triggers.md` |
| 效率 | Webhook | 独立菜单，当前读取能力有缺口：`<PLUGIN_ROOT>/skills/ticket-admin/references/triggers.md` |
| 工单 | 字段与表单 | 字段定义、展示分组及顺序：`<PLUGIN_ROOT>/skills/ticket-admin/references/workspace-settings.md` |
| 工单 | SLA策略 | 策略、元数据与匹配预览：`<PLUGIN_ROOT>/skills/ticket-admin/references/routing-sla.md` |
| 工单 | 队列 | 队列、渠道、语言与激活状态：`<PLUGIN_ROOT>/skills/ticket-admin/references/routing-sla.md` |
| 工单 | 满意度调查 | 模板、版本与自动发送现值：`<PLUGIN_ROOT>/skills/ticket-admin/references/outreach-satisfaction.md` |
| 工单 | WhatsApp模板 | 账号、模板定义与审核状态：`<PLUGIN_ROOT>/skills/ticket-admin/references/outreach-satisfaction.md` |
| 工单 | 工具栏扩展 | 配置查询，第三方运行数据/测试未接：`<PLUGIN_ROOT>/skills/ticket-admin/references/workspace-settings.md` |
| AI | AI 打标 | 策略现值：`<PLUGIN_ROOT>/skills/ticket-admin/references/workspace-settings.md` |
| 坐席配置 | 成员（含角色） | 成员、角色和权限：`<PLUGIN_ROOT>/skills/ticket-admin/references/workspace-settings.md` |
| 坐席配置 | 团队 | 团队配置：`<PLUGIN_ROOT>/skills/ticket-admin/references/routing-sla.md` |
| 坐席配置 | 排班 | 营业日历与时段：`<PLUGIN_ROOT>/skills/ticket-admin/references/routing-sla.md` |
| 坐席配置 | 容量 | 容量规则与默认值：`<PLUGIN_ROOT>/skills/ticket-admin/references/routing-sla.md` |

读取对应路径。工单工作台视图、已有触达计划等菜单外配置分别见上表自动规则、满意度调查对应文档的补充章节，不把它们当作当前设置侧栏菜单。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-triggers
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-trigger-preview --params-json '{"id":"<规则ID>","ticketNumber":"<工单号>"}'
```

- 预览仅解释静态条件；`eventContextRequired` 表示缺少事件上下文，不能断言规则历史上一定执行/不执行。
- 队列/容量定义与实时负载分开，实时监控归 ticket-analytics；单张工单事实归 ticket-helper。
- WhatsApp 模板仅查询定义和审核状态，不生成或发送回信。
- 不创建、保存、删除、排序、发布、启停、重算、重试、测试发送或生成第三方凭据。
- 调用外部 API 的侧栏扩展测试和 runtime/data 本期不开放；配置缺失或未支持的信息如实说明。
- AI 字段定义复用现有 CLI：

| 命令 | 关键参数 | 使用时机 |
|---|---|---|
| `node "<PLUGIN_ROOT>/plugin-cli.mjs" field list` | `--page 1 --page-size 50 --keyword <名称> --pretty` | 查 AI 字段定义列表 |
| `node "<PLUGIN_ROOT>/plugin-cli.mjs" field get` | `--id <字段ID> --pretty` | 查字段类型、选项和定义 |

不要调用初始化、删除或 switch，即使后端方法是 GET。需要修改时仅给出建议，本期不执行。
