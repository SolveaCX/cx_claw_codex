---
name: integrations
description: 指导渠道与第三方平台接入、解答配置过程问题、读取已有连接/授权/映射/同步状态并诊断。支持 Zendesk、Zoho、电商、Email、LiveChat、自研渠道等。
---

# 集成助手

调用 CLI 前先读取 `../cxclawctl/SKILL.md`，沿用当前会话的 `--context <contextId>`。本文命令通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 执行，表格中的简写补在该入口后；`--help` 无需登录。`<WORKSPACE>` 指 `CXCLAW_WORKSPACE` 指定目录，默认 `~/.cxclaw/workspace`；状态与交付目录还可分别由 `CXCLAW_STATE_DIR`、`CXCLAW_OUTPUT_DIR` 覆盖，以 CLI 返回的绝对路径为准。


面向用户统一称“客服工单”；“售后工单（产品支持工单）”与“Inbox（Agent 会话记录）”分别按其产品语境称呼，内部服务名称和接口路径不作为产品名称解释。

先区分用户所处阶段，再读取 `<PLUGIN_ROOT>/skills/integrations/references/onboarding.md` 及对应平台文档。已知平台和上下文不要重复询问。

| 用户目标 | 进入方式 | 结束条件 |
|---|---|---|
| “怎么接入/需要准备什么” | 说明前提、产品操作步骤和验证方式；不要求先提供连接 ID，不默认查询租户数据 | 用户知道准备什么和下一步在哪里操作 |
| “正在授权/配置到这一步” | 只定位当前卡点；客户完成产品操作后，用现有查询回查 | 当前步骤已验证，或明确待客户完成的动作 |
| “接上后没数据/连接异常” | 定位已有连接，再按授权、范围/映射、同步、样本证据检查 | 给出已证实的问题、下一步及尚未验证部分 |

通用指导不创建进展文件。持续接入任务才保存阶段；恢复任务时重新读取会变化的授权/同步状态，不能把上轮快照当最新结果。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" integration connections-list --params-json '{"botId":123}'
node "<PLUGIN_ROOT>/plugin-cli.mjs" integration zendesk-settings
node "<PLUGIN_ROOT>/plugin-cli.mjs" integration zoho-diagnose --params-json '{"sampleLimit":3}'
```

- 使用运行时租户授权；不要让客户粘贴 token、密码、API key。授权和保存由客户在产品/第三方页面操作，随后回查状态。
- 连接存在、授权有效、配置完整、读取校验通过、真实收发成功分别报告；只读诊断不能证明真实收发成功。
- 诊断保留失败步骤、无样本和跳过原因；遇到未支持的平台/字段明确说明，不能拿别的平台结果代替。
- 不发起 OAuth、不创建凭据、不绑定/启停、不启动学习或同步、不发验证码、不执行 WhatsApp 测试回复。
- 脱敏后没有的字段不等于未配置；不能通过其他脚本绕过去取原始凭据或 metadata。
- 需要 Agent 本体信息直接复用：

| 命令 | 关键参数 | 使用时机 |
|---|---|---|
| `node "<PLUGIN_ROOT>/plugin-cli.mjs" agent get` | `--id <AgentID> --pretty` | 检查连接绑定的 Agent |

- 需要工单证据时读取 `<PLUGIN_ROOT>/skills/integrations/references/ticket-evidence.md`，直接调用共享 ticket CLI；不依赖 ticket-helper 已加载。
- 持续接入任务保存接入进展到 `<WORKSPACE>/state/integrations/onboarding_progress.json`，包含平台、连接 ID、当前步骤、已证实结果、未解决问题和下一步，不保存凭据。
