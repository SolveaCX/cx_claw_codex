# Agent 会话记录与收件箱明细

`get-transcript` 获取单条 Agent 会话记录详情。后端对象名为 `Transcript`，业务说明统一称“Agent 会话记录”。

在 `agent-analytics` 中，数据分析页面中的工单指 Agent 会话记录，也是收件箱数据。

统计指标先读取 `report-fields.md` 并调用 Report；只有需要核对明细、寻找样本或查看完整对话时才使用本文命令。

## 命令与接口

| CLI 命令 | 接口 | 用途 |
|---|---|---|
| `list-transcripts` | `POST /api_v2/gpt/project/{projectId}/transcripts/filter` | 收件箱 Agent 会话记录摘要列表 |
| `get-transcript` | `GET /api_v2/gpt/project/{projectId}/transcript/{chatId}?isCompare=true` | 单条完整会话 |
| `export-transcripts` | `POST /api_v2/gpt/project/{projectId}/transcripts/export/async` | 提交异步导出 |
| `get-export-tasks` | `POST /api_v2/gpt/label/project/{projectId}/getLabelTask` | 查询导出状态 |

## 与 Report 对齐的过滤条件

`list-transcripts` 支持：

- `--begin-ts` / `--end-ts`
- `--touch-point`
- `--bot-id`
- `--agent-id`
- `--intent-id`
- `--handoff true|false`
- `--debug`
- `--page` / `--page-size`

下钻时必须复用 Report 的时间范围、时区对应的毫秒边界，以及适用的 Bot、渠道、Agent、意图条件。前端未选择渠道时不要追加 `--touch-point`，表示全部渠道。

```bash
cxclawctl api list-transcripts \
  --begin-ts "$BEGIN_MS" \
  --end-ts "$END_MS" \
  --page 1 \
  --page-size 50 \
  --pretty
```

筛选 LiveChat 已转人工 Agent 会话记录：

```bash
cxclawctl api list-transcripts \
  --begin-ts "$BEGIN_MS" \
  --end-ts "$END_MS" \
  --touch-point LIVE_CHAT \
  --handoff true \
  --page 1 \
  --page-size 50 \
  --pretty
```

## 分页完整性

收件箱接口返回：

- `pageIndex`
- `pageSize`
- `hasNext`
- `list`

`totalCount` 已废弃，通常不能作为可靠总量。**当前页长度不是总量**，CLI 也不会再用当前页长度伪造 `total`。

完整拉取流程：

1. 从 `--page 1` 开始。
2. 记录当前页 `list` 数量并保存 `chatId` 去重。
3. 当 `hasNext=true` 时将页码加一，保持其他参数完全不变。
4. 直到 `hasNext=false` 才算分页完成。
5. 最终说明实际获取数量；接口总量不可用时明确写“总量不可用”。

未读取到 `hasNext=false` 时，禁止将已获取数据描述为全部 Agent 会话记录。

## 单条完整对话

`list-transcripts` 只返回摘要。需要查看消息内容、AgentAction、转人工上下文或具体异常时，再调用：

```bash
cxclawctl api get-transcript \
  --chat-id <chatId> \
  --pretty
```

不要对列表中的所有 Agent 会话记录无差别获取完整详情。优先根据 Report 指标、时间点、Agent、意图或转人工条件选择有解释价值的样本。

## 抽样结论边界

- 抽样用于解释具体异常、寻找共同模式或展示典型对话。
- 样本数量、筛选方式和是否随机必须在结论中说明。
- 样本不能替代 Report 的总体计数和比例。
- Report 指标不可用时，只能输出“样本中观察到”，不能升级成整体原因或总体占比。
- AI 回复与原 badcase、历史表现或预期明显不同时，要指出变化发生在哪一轮、哪个 AgentAction 或哪个业务节点。

## 异步导出

只有确实需要大量明细文件时才使用：

```bash
cxclawctl api export-transcripts \
  --begin-ts "$BEGIN_MS" \
  --end-ts "$END_MS" \
  --time-offset 8 \
  --pretty

cxclawctl api get-export-tasks --pretty
```

轮询到任务 `status=SUCCESS` 后再使用返回的文件地址。
