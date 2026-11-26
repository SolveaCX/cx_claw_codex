---
name: ticket-helper
description: 查看与筛选客服工单列表、单张工单详情、消息原文、备注、人工/AI标签、标签树及批量标签、字段、客户、订单、物流、SLA、评价、附件和已有任务记录。处理时间线与问题解释，不生成或发送回信。
---

# 工单助手

调用 CLI 前先读取 `../cxclawctl/SKILL.md`，沿用当前会话的 `--context <contextId>`。本文命令通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 执行，表格中的简写补在该入口后；`--help` 无需登录。`<WORKSPACE>` 指 `CXCLAW_WORKSPACE` 指定目录，默认 `~/.cxclaw/workspace`；状态与交付目录还可分别由 `CXCLAW_STATE_DIR`、`CXCLAW_OUTPUT_DIR` 覆盖，以 CLI 返回的绝对路径为准。


面向用户统一称“客服工单”；“售后工单（产品支持工单）”与“Inbox（Agent 会话记录）”分别按其产品语境称呼，内部服务名称和接口路径不作为产品名称解释。

先用当前页面、链接、明确产品名称和已有对话确定对象：客服工单是租户处理客户问题的工单；售后工单也叫产品支持工单，是租户向 Shulex 提交的问题；Inbox 也叫 Agent 会话记录。编号前缀不能单独决定对象。只有孤立编号或“查工单”且上下文不足时，简短询问所属产品，不依次尝试多套接口。

用户要“查工单、看详情、看消息、看标签、按条件列出工单”时由本 Skill 承接，包括一次查看多张工单；只有统计指标、分布趋势和分析报表才进入 ticket-analytics。
先定位工单号；只有姓名/标签名时先查目录，遇到重名不要猜 ID。
按业务任务读取参考文档，命令及参数就在对应步骤中：

| 业务任务 | 参考文档 |
|---|---|
| 查看工单列表、单张详情、消息、备注、SLA 和评价 | `<PLUGIN_ROOT>/skills/ticket-helper/references/ticket-investigation.md` |
| 查看标签、标签树、名称搜索与批量标签 | `<PLUGIN_ROOT>/skills/ticket-helper/references/tags.md` |
| 客户、关联工单、订单和物流 | `<PLUGIN_ROOT>/skills/ticket-helper/references/customer-orders.md` |
| 解析筛选目录中的客服、渠道、品牌和字段 | `<PLUGIN_ROOT>/skills/ticket-helper/references/classification.md` |

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket get --params-json '{"ticketNumber":"<工单号>"}'
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket messages --params-json '{"ticketNumber":"<工单号>","limit":50}' --all --max-pages 20
```

- 工单号、内部 ticketId、messageId、responseId、customerId、外部平台工单 ID 不互换。内部 ID 从详情解析。
- `ticket messages` 必须检查 pagination；读取范围不足时补页，触及上限时说明截断。
- 只读取回答当前问题需要的证据：看标签查标签，看状态查详情；解释处理过程才补消息/备注/操作记录，涉及超时才查 SLA。证据已足够时停止，不为凑齐资料遍历所有查询。
- 标签返回的 userTags/aiTags 分开；只查询，不绑定、解绑或更改备注。
- 输出 JSON 可用 `--output <WORKSPACE>/outputs/ticket-helper/<唯一文件名>.json` 保存；先读取再分析。
- 附件/录音命令返回下载地址与适用的有效期；不能将仅获取地址描述为已下载文件。
- 不标记已读、不修改任何工单/客户/订单、不退款、不启动同步、不提交审核、不拟稿、不写草稿、不发送。
- 多工单的统计分析与报表由 ticket-analytics 承接；单纯列出/查看工单仍在本 Skill；配置解释需要时调用 ticket-admin 的共享查询。
- CLI 按业务参考文档选择命令，用 `<命令> --help` 核对参数；没有命令时明确能力缺口，不直接 curl 或拼写操作。
