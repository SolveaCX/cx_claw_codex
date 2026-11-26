---
name: ticket-analytics
description: 客服工单运营分析：指标、趋势、客服绩效、满意度、SLA、队列及 Support/Chat/Voice 报表。支持复杂明细分析、XLSX 快照和完整报告；Inbox 运营分析归 agent-analytics。
---

# 客服工单分析

调用 CLI 前先读取 `../cxclawctl/SKILL.md`，沿用当前会话的 `--context <contextId>`。本文命令通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 执行，表格中的简写补在该入口后；`--help` 无需登录。`<WORKSPACE>` 指 `CXCLAW_WORKSPACE` 指定目录，默认 `~/.cxclaw/workspace`；状态与交付目录还可分别由 `CXCLAW_STATE_DIR`、`CXCLAW_OUTPUT_DIR` 覆盖，以 CLI 返回的绝对路径为准。


面向用户统一称“客服工单”；“售后工单（产品支持工单）”与“Inbox（Agent 会话记录）”分别按其产品语境称呼，内部服务名称和接口路径不作为产品名称解释。

先用当前页面、链接、明确产品名称和已有对话确定对象：客服工单是租户处理客户问题的工单；售后工单也叫产品支持工单，是租户向 Shulex 提交的问题；Inbox 也叫 Agent 会话记录。编号前缀不能单独决定对象。只有孤立编号或“查工单”且上下文不足时，简短询问所属产品，不依次尝试多套接口。

单张详情、消息、标签和单纯列出工单由 ticket-helper 承接；本 Skill 处理数量、分布、趋势、绩效和分析报表。跨 Skill 主责分工保持不变。

先明确业务指标、时间范围/当前时点、时区和必要筛选。已有页面或对话范围可直接沿用并说明；历史统计缺时间范围且上下文无法确定时再问，不默认本月。不因问了“趋势”就自动制作下载报告。

| 用户目标 | 最短执行路径 | 读取 |
|---|---|---|
| 查指标、趋势、绩效、产品看板或当前队列 | 查对应统计接口，直接给结论和口径；通常无需 task、XLSX 或分析脚本 | `<PLUGIN_ROOT>/skills/ticket-analytics/references/product-reports.md` |
| 正文分类、复杂筛选或标准接口不能回答的归因 | 先确定所需明细，再取历史事实/当前快照分析；结果足够即可回答 | `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/workflow.md`；当前快照字段见 `<PLUGIN_ROOT>/skills/ticket-analytics/references/tickets/query.md` |
| 明确要完整报告、下载文件或更新已有报告 | 保留合适的数据来源，再生成所需交付物；不重新索要已知条件 | `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/delivery.md` |

- 统计查询不读取 latest_task。仅做快照分析时读取 `<WORKSPACE>/state/ticket-analytics/latest_task.json`；不存在是新任务，按快照工作流取数。
- 新任务只写 `<WORKSPACE>/state/ticket-analytics/`、`<WORKSPACE>/outputs/ticket-analytics/` 和 `<WORKSPACE>/tmp/ticket-analytics/`，不读取旧 Skill 的状态目录。
- 只查询，不修改工单、配置或启动远程任务，不生成对客回信。
- 当前负责人不等于历史回复人/解决人；分页截断不能声称全量，缺失指标不能填零。
- 对话内图表按需要生成；完整报告统一用 `node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics render-report`，不重写模板。
- 具体工单的问题解释交给 ticket-helper；规则定义归 ticket-admin；接入问题归 integrations。
