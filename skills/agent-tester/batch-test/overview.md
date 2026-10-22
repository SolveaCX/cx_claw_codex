# 系统批量测试

批测必须对齐系统入口：生成并填充系统模板兼容 xlsx，提交下载中心任务，再按需查询进度。不要使用 POC / Delivery 的本地并发脚本、状态或报告协议。

## 入口路由

先执行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" api get-agent --id <agentId> --pretty`：

| 类型 | 系统入口 | task type | 数据 | 上限 |
|---|---|---|---|---|
| `CHAT_FLOW` | Chatflow 画布“批量多轮测试” | `MULTI_TURN_REPLY` | 一个 case 多 turn | 600 case |
| 其他 Agent | 菜单“批量测试” | `REPLY` | 一个 case 一个 question | 200 case |

不要把 Chatflow 降级为菜单批测，也不要将普通 Agent 当作多轮 Chatflow 任务。

### case 数量建议

- 1-10 个 case：如果需要即时查看每轮回复、节点和调试信息，可使用 `live_test`。
- **超过 10 个 case：优先生成系统模板并提交下载中心批测任务**，不要把每个 case 拆成多个 `live_test`。
- Chatflow 批测使用 `MULTI_TURN_REPLY`；普通 Agent 批测使用 `REPLY`。

## 创建测试表

用户可以给问题列表/文件、ChatId 列表，或要求按条件找一批历史对话。JSON 仅是 skill 在后台归一化输入给脚本的中间产物，**不要要求用户创建、上传或确认 JSON**。

先向用户展示可读的测试集表格并确认，再在后台生成 JSON 和 xlsx。表格至少展示：case 名称、来源（手工问题/ChatId/历史筛选）、轮次、用户问题、固定 metadata、目标模式；订单号、邮箱等 metadata 不得编造。用户确认后才执行生成和提交。

脚本内部使用 case JSON 生成第 1 行说明、第 2 行表头的系统兼容 xlsx：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py create-sheet \
  --mode chatflow --cases-file /workspace/outputs/agent-tester/chatflow_cases.json

node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py create-sheet \
  --mode agent --cases-file /workspace/outputs/agent-tester/agent_cases.json
```

Chatflow JSON：

```json
[{"case_name":"refund-follow-up","turns":[{"question":"我要退款","metadata":{"order_number":"A-1001"}},{"question":"订单号就是 A-1001"}]}]
```

普通 Agent JSON：

```json
[{"case_name":"shipping","question":"我的订单什么时候发货？","metadata":{"order_number":"A-1001"}}]
```

### `REPLY` 模板的 `meta_data` 格式

普通 Agent（`REPLY`）批测模板的 `meta_data` 列目前必须填写为**纯文本键值对**，多个字段用英文或中文分号分隔：

```text
touchPoint: LIVE_CHAT; order_number: A-1001
```

请按上述格式填写，`LIVE_CHAT`、`EMAIL` 等渠道值使用系统枚举值。

Chatflow 表头是 `case_name, chat_id, metadata_1, question_1, ai_answer_1, ...`；普通 Agent 是 `question, origin_answer, ai_answer, similarity, judgement, reason, chat_id, meta_data, fail_reason`。所有系统输出列保持空白。xlsx 输出到 `/workspace/outputs/agent-tester/`，状态写到 `/workspace/state/agent-tester/latest_batch_test.json`。

## 提交和查询

默认不指定 `specified_agent_id` 或 `specified_flow_version`，让任务从最外层意图识别和系统策略路由开始执行。只有用户明确要求锁定某个 Chatflow Agent（例如验证该 Agent 的草稿或已发布版本）时，才先用 `get-chatflow-graph --agent-id <agentId>` 取得实际 version，并同时传入 Agent 和版本；不要只传其中一个。历史预览或调试面板打开时，画布不允许提交。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py submit \
  --mode chatflow --file <generated.xlsx> --bot-id <botId>

# 只有明确指定 Chatflow Agent / 版本时追加：
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py submit \
  --mode chatflow --file <generated.xlsx> --bot-id <botId> \
  --agent-id <agentId> --flow-version <currentVersion>

node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py submit \
  --mode agent --file <generated.xlsx> --bot-id <botId>
```

脚本获取临时 S3 凭证并上传 xlsx。默认 Chatflow 请求不带路由 metadata；仅在指定模式下才携带 `specified_agent_id` 和 `specified_flow_version`。提交接口只返回 `success`，不返回 taskId；随后按类型查询下载中心，选本次时间相符的最新任务：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py get-tasks --mode chatflow
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-tester/scripts/batch_test_sheet.py get-tasks --mode agent
```

`WAIT_TAG` 是等待中，`TAGGING` 是执行中，`SUCCESS` 完成且 `file` 可下载，`FAIL` 是失败；`successCount / totalCount` 为当前进度。除非用户明确要求，不要阻塞式轮询。
