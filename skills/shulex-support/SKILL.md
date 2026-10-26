---
name: shulex-support
description: Shulex 产品支持统一入口。凡用户提到 badcase、异常回复、失败节点、报错、卡住、排查，或提供 ChatId / 会话 ID / External ID 要求定位会话，优先使用本 skill；也用于产品咨询、功能需求和售后工单。
requires:
  libs:
    - solvea-api
---

# Shulex Support

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。
处理 Shulex 产品咨询、Agent 会话诊断和售后工单。先判断用户属于哪一种场景，只进入对应流程；不要先把三套材料全部读完。

## 入口优先级

**Agent 会话诊断优先于运营分析。** 用户只要描述异常、badcase、错误、失败、卡住、答非所问，或要求根据 ChatId / 会话 ID / External ID 查原因，主流程先进入本 skill 的 Agent 会话诊断场景，读取 `references/badcase-analysis/overview.md`。如需整体指标或样本统计，可再调用 `agent-analytics` 提供辅助证据，不要因此改变 badcase 的主责入口。

只有用户明确要统计指标、趋势、排行、分页列表或运营报表，且不要求解释某次会话异常时，才使用 `agent-analytics`。

## 场景分流

| 用户意图 | 处理方式 |
|---|---|
| 咨询产品使用、配置、排障、售后政策 | 读取 `references/product-docs.md`，基于产品文档回答 |
| 提出功能需求、产品改进建议，或明确说“提个需求/希望支持/能不能增加” | 读取 `references/tickets.md`，按 `ticket_feature` 整理需求工单；先确认明细再创建 |
| 提供 ChatId / 会话 ID / 外部会话 ID，要求分析 badcase、异常回复、失败节点或语音通话问题 | 读取 `references/badcase-analysis/overview.md`，按文本 / 语音流程诊断 |
| 明确要提交工单，或文档查询无法解决 | 读取 `references/tickets.md`，收集必要信息并确认后创建 |
| 查询某个工单怎么样了 | 读取 `references/tickets.md`，根据工单号查询状态和最新消息 |
| 继续补充某个工单的问题 | 读取 `references/tickets.md`，根据工单号追加用户消息 |
| 只提供任意 ID，未说明目的 | 默认按会话 ID 进入 Agent 会话诊断；只有 `ST...` 开头或用户明确说“售后工单/查询工单/追加工单”时才走售后工单 |
| 只说"售后""工单"但目标不清楚 | 先问用户目标；确认后再读取 `references/tickets.md` |

## 处理原则

1. **先分流再处理**：ChatId 会话异常直接诊断；普通产品问题先查文档；用户提出功能需求/改进建议，或明确要提单、诊断后需要人工跟进时，进入工单流程。
2. **不伪造工单状态**：没有查到工单或当前运行时没有可用接口时，直接说明无法确认，不要编造状态、客服回复或预计处理时间。
3. **区分会话 ID 与售后工单号**：ChatId、会话 ID、外部会话 ID用于 Agent 会话诊断，也可作为 `agent_badcase` 工单的扩展字段；孤立 ID 默认视为会话 ID。只有 `ST...` 开头的 ID，或用户明确提到售后工单、查询工单、追加工单时，才把 ID 当售后工单号处理。
4. **信息最小化**：提交工单只收集当前问题需要的信息，不主动索要无关隐私。
5. **邮箱可选**：有邮箱时可用于后续通知；没有邮箱也不阻塞工单链路。
6. **先确认后提交**：调用 `create-ticket` 之前，必须先把整理好的工单明细列给用户，得到用户明确确认后才提交，绝不能直接创建。
