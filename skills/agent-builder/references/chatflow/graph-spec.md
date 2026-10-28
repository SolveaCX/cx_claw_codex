# CHAT_FLOW 图规范

本文件描述 source JSON、边、全局校验和写回命令。节点字段细节看 `references/nodes/*.md`，节点选型看 `references/node-selection.md`。

## Source JSON

Agent 编写 source JSON，再用 CLI 编译成完整平台 `chatFlowGraph`。source 只放业务必要字段，节点 id、position、handle、默认 config、共享 `$finish` / `$transfer` 由 builder 补齐。

```json
{
  "entry": "ask_platform",
  "nodes": [
    {
      "key": "ask_platform",
      "type": "question",
      "mode": "USER_REPLY",
      "question": "Please choose a platform.",
      "replies": ["TikTok", "Amazon", "Shopify"]
    },
    {"key": "tiktok_reply", "type": "reply", "reply_type": "TEMPLATE", "template_id": 12345}
  ],
  "edges": [
    {"from": "ask_platform", "on": "TikTok", "to": "tiktok_reply"},
    {"from": "ask_platform", "on": "OTHER", "to": "$transfer"},
    {"from": "tiktok_reply", "to": "$finish"}
  ]
}
```

## Node Keys And Titles

- 每个节点必须有稳定 `key`，供 edges 引用。
- `title` 可选，默认用 `key`；builder 会把空格、中文、`/` 等清洗成 ASCII。
- `position` 可选；有明确坐标时保留，没有时自动布局。
- source 里通常不写 `$start`、`$finish`、`$transfer` 节点本体，边里引用特殊 key 即可。

## Node Types

| type | 节点说明 |
|------|----------|
| `start` | `nodes/start.md`，通常省略，用顶层 `entry` 自动生成 |
| `finish` / `$finish` | `nodes/finish.md` |
| `reply` | `nodes/reply.md` |
| `llm` | `nodes/llm.md` |
| `question` | `nodes/question.md` |
| `agent` | `nodes/agent.md` |
| `intent` | `nodes/intent.md` |
| `if_else` | `nodes/if-else.md` |
| `tool` | `nodes/tool.md` |
| `rag_reply` / `knowledge` | `nodes/rag-reply.md` |
| `knowledge_reply` | `nodes/knowledge-reply.md`，仅已有图兼容 |
| `transfer` / `$transfer` | `nodes/transfer-to-human.md` |
| `collect_order` | `nodes/collect-order.md`，即将下线，仅存量兼容 |
| `variable_process` | `nodes/variable-process.md` |
| `code` | `nodes/code.md` |
| `human_review` | `nodes/human-review.md` |
| `sub_graph` | `nodes/sub-graph.md` |
| `business_track` | `nodes/business-track.md` |
| `variable_extract` | `nodes/variable-extract.md`，仅已有图兼容 |
| `variable_assignment` | `nodes/variable-assignment.md`，仅已有图兼容 |

## Edges

边只写业务语义，不直接写底层 `sourceHandle`：

```json
{"from": "ask_platform", "on": "TikTok", "to": "tiktok_reply"}
{"from": "intent", "on": "OTHER", "to": "$transfer"}
{"from": "rag", "on": "LACK_KNOWLEDGE", "to": "$transfer"}
{"from": "reply", "to": "$finish"}
```

`on` 会自动解析为 QUESTION reply id、INTENT id、IF_ELSE case id、AGENT nextStep id，或固定 handle：`SOURCE`、`OTHER`、`FALSE`、`TRUE`、`LACK_KNOWLEDGE`、`RESOLVED`、`UNRESOLVED`、`AGREE`、`REJECT`。

必须显式连出的兜底边：

- QUESTION(USER_REPLY)：所有 reply + `OTHER`
- INTENT：所有 intent + `OTHER`
- 流程图中的 `Y/N` 默认表示条件结果（Y=条件满足，N=条件不满足）.
- IF_ELSE：所有 case + `FALSE`
- RAG_REPLY：`TRUE` + `LACK_KNOWLEDGE`
- KNOWLEDGE_REPLY：`RESOLVED` + `UNRESOLVED`
- HUMAN_REVIEW approval：`AGREE` + `REJECT`

## Variable Selector

变量选择器是跨节点传递数据的数组协议。引用上游提取结果时，第三段必须是完整 graph 里的 extract `id`，不是 `name`。前端新建 extract 时用 `getUuid()` 生成该 `id`；source JSON 用 `alias` 给 builder 引用，compile 后会替换成 UUID。

完整 graph 使用数组。SYSTEM selector 必须保留前端级联菜单的完整字段路径：

```json
["SYSTEM", "Custom", 123]
["SYSTEM", "Order", 3248, 3249]
["TOOL", "<tool_node_id>", "field", "subField"]
["TOOL", "<tool_node_id>", "ACTION_STATUS_NAME"]
["EXTRACT", "<extract_node_id>", "9f0a4b17-2a2c-48f3-8e8b-8a7a9b2d0f52"]
["CODE", "<code_node_id>", "normalized_order_no"]
["LLM", "<llm_node_id>", "text"]
["LLM", "<llm_node_id>", "structured_output", "summary"]
["AGENT", "<agent_node_id>", "reason"]
["HUMAN_REVIEW", "<review_node_id>", "field_id"]
["NODE", "<node_id>"]
["SELF", "9f0a4b17-2a2c-48f3-8e8b-8a7a9b2d0f52"]
```

约束：

- `SYSTEM` 第一段后依次是 `bizType` 和完整字段 id 路径。`OrderNumber(3249)` 位于 `OrderInformation(3248)` 下时，必须写 `["SYSTEM", "Order", 3248, 3249]`，不能省略父字段 id。
- `EXTRACT` 用于 `VARIABLE_EXTRACT` / `VARIABLE_PROCESS` 的提取结果；第三段是提取项 `id`，通常是 UUID。
- `CODE` 第三段是 code output `fieldName`。
- `LLM` 只能引用 `text`（固定三段）或 `structured_output`。结构化结果的 selector 形如 `['LLM', node_id, 'structured_output', '<schema property>', ...]`，且上游 LLM 必须启用 `structuredOutput`。
- `AGENT` 第三段是 `next_steps[].params[].name`，只在对应 nextStep 路由到当前下游路径后有值。
- `HUMAN_REVIEW` 第三段是 fill 字段 `id`。
- `NODE` 只用于 `VARIABLE_EXTRACT` / `VARIABLE_PROCESS` 的 `additional_data`，表示把上游节点完整输出补充给提取上下文；不要用于 TOOL 入参、IF_ELSE、CODE 输入。
- `SELF` 只用于 `VARIABLE_PROCESS.assignments[].source`，引用本节点刚提取出的 extract `id`。
- `TOOL` 的 `ACTION_STATUS_NAME` 只用于允许状态映射的字段：IF_ELSE、CODE 输入、HUMAN_REVIEW 变量模板。
- 变量只能引用当前节点的上游节点输出，不要引用同级、下游或未连通节点。

source JSON 可用简写，builder 会替换成真实节点 id：

```json
{"variableSelector": {"tool": "lookup_order", "field": "status"}}
{"variableSelector": {"tool": "lookup_order", "path": ["order", "shipping_method_no"]}}
{"variableSelector": {"tool_status": "lookup_order"}}
{"variableSelector": {"code": "normalize_items", "field": "has_items"}}
{"variableSelector": {"llm": "summarize_case", "field": "summary"}}
{"variableSelector": {"node": "ask_order"}}
{"variableSelector": {"extract": "extract_info", "alias": "order_no_value"}}
{"variableSelector": {"system": {"category": "Custom", "path": [123]}}}
{"variableSelector": {"system": {"category": "Order", "path": [3248, 3249]}}}
```

`list-ai-fields` 返回 Chatflow 画布可用的树形字段，用于 SYSTEM selector。source 的 `path` 必须从顶层字段开始逐级写到目标字段；不要只复制叶子字段的 `id`。

AGENT 的 `ai_field_ids` 还要通过前端 Agent 范围校验，必须从 `list-agent-ai-fields` 选择。两个命令对应生产前端的两套字段数据源，不要混用。

`queryAiFields` 背后依赖字段服务 `field/internal/list`，部分环境会短暂不可用并返回类似 `tars: Name does not resolve`。遇到这种错误时，不要把它判断为 graph schema 错误：

- 不需要变量系统字段的新建 / 修改，可以继续 compile / validate；builder 会跳过字段存在性校验并输出 warning。
- 需要精确绑定 `SYSTEM` selector 或 `ai_field_ids` 时，先使用已知字段 id、已有 graph 中的字段 id，或等字段服务恢复后重试。
- 不要因为 `queryAiFields` 不可用就把变量写进 prompt。

TOOL 单层出参可用 `field`；嵌套出参必须用从顶层开始的 `path` 数组，编译结果为 `["TOOL", node_id, "order", "shipping_method_no"]`。不要写点号字段 `"order.shipping_method_no"`，也不要加 `"output"` 中间层。

提示词变量机制：

- CHAT_FLOW 不感知 `metadata` 路径；所有节点都禁止写 `metadata.xxx`、`metadata.ai_fields.xxx` 或类似点号路径。变量系统字段在进入图后只通过 ai-fields 暴露，并由 `SYSTEM` selector 或 `ai_field_ids` 读取。
- 如果还需要从 `AttachmentSummary` 等已有系统字段中二次提取，或对 TOOL / CODE / AGENT 输出做转换、赋值，使用 `VARIABLE_PROCESS`。
- AGENT 和 `REPLY(PROMPT)` 的变量入口是变量系统字段：source 写 `ai_field_ids`，完整 graph 写 `agentData.aiFieldIds` 或 `replyContent.aiFieldIds`。AGENT 的 source `prompt` 可使用 `{#LibraryBlock id=<字段id> type=variable name="<字段名>" #}` 表达变量 chip；模板、普通工具和转人工动作按 `nodes/agent.md` 使用各自 LibraryBlock。builder 编译时写入完整 graph 的 `displayPrompt`、派生运行时 `prompt`，并自动补齐普通工具 ID 以及模板/转人工真实系统插件 ID 到 `usedPlugins`。
- AGENT / `REPLY(PROMPT)` 不渲染 `[[var:...]]`。如果它们必须稳定使用上游节点输出，先用 `VARIABLE_PROCESS.assignments` 写入 `SYSTEM` 字段，再通过 `ai_field_ids` 引用。
- `REPLY(DYNAMIC_TEMPLATE)`、LLM `prompt` 和 HUMAN_REVIEW `description` 会渲染 `[[var:<selector>]]`。完整 graph 使用 selector 数组，例如 `[[var:["CODE","<code_node_id>","summary"]]]`。source JSON 可在模板中写 selector 简写，例如 `[[var:{"code":"summarize_case","field":"summary"}]]`，builder 会替换为真实节点 id。
- RAG_REPLY 用 `query_selector` 指定检索 query，不在 prompt 里插变量。

## Compiled Graph Shape

`compile` 生成的完整 `meta.chatFlowGraph` 包含：

- `nodes`：`id` 唯一，`type` 通常为 `CUSTOM`，`position` 为 `{x, y}`，`data.category` 为节点类型。
- `edges`：每条边必须包含非空的 `id`、`source`、`sourceHandle`、`target`、`targetHandle`、`type`；`id` 全图唯一，`source`、`target` 必须引用现有节点，当前只允许 `type: default`。
- `viewport`：`{x, y, zoom}`。

已有完整 graph 可包含 `type: CUSTOM_NOTE`、`data.category: NOTE` 的画布注释节点；详见 `nodes/note.md`。NOTE 不参与运行，不需要连线。

不要生成或保留前端测量字段，例如 `measured`。

## Runtime Handles

source JSON 不写 `WAIT` 节点，也不要手动创建 `USER_INPUT` / `AGENT_TOOL` 节点。

后端解析 graph 时会注入内部节点：

- `USER_INPUT`：为 `AGENT`、`QUESTION`、`COLLECT_ORDER`、`KNOWLEDGE_REPLY` 注入等待用户输入的回环；`REPLY` 如果有出边，也会先 `WAIT -> USER_INPUT -> 原下游`；`RAG_REPLY` 的 `TRUE` 分支如果有出边，也会先等待用户下一轮输入再进入原 `TRUE` 下游。
- `AGENT_TOOL`：为每个 `AGENT` 注入内部工具执行节点；AGENT 调外部 plugin 或知识工具时会走 `AGENT -> AGENT_TOOL -> AGENT`，不作为业务节点手写。

排查日志或 transcript 时，`output_handle=WAIT` 通常表示当前节点已回复用户并等待下一轮输入；真正出现在执行路径里的内部节点是 `USER_INPUT`。

## Resource Queries

节点依赖外部资源时，先查询再写 id：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-templates --keyword "platform" --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" tool list --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-ai-fields --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent list --pretty
```

资源查询口径：

- 模板查询走 `POST /api_v2/gpt/project/{projectId}/templates/filter`，用于按 keyword/status/scenes 查可用模板。图搭建页面的 `GET /templates` 适合前端全量渲染，不适合作为 agent 搜索模板的主要入口。
- 联网 `compile` / `validate` / `deploy` / `update` / `publish` 会回查图中 REPLY、QUESTION、TRANSFER、COLLECT_ORDER 及 AGENT LibraryBlock 引用的模板；模板缺失或状态不是 `ENABLED` 时校验失败。离线模式只能做结构预检，不能声称模板状态已通过。
- 工具查询使用 `list-plugins`，重点看工具 id、入参、出参和 actionStatus 配置。
- 变量系统字段查询使用 `list-ai-fields`。该服务不可用时，先跳过字段存在性校验，不要阻断无字段依赖的图创建。
- AGENT `ai_field_ids` 可用范围查询使用 `list-agent-ai-fields`。

## Global Constraints

- START 必须且只能有一个。
- FINISH 不强制唯一；默认使用单个共享 `$finish`，减少无意义终端节点。
- FINISH、TRANSFER_TO_HUMAN、SUB_GRAPH 无出边；SUB_GRAPH 后端 parser 强制禁止出边。
- 图中不能有环；不要用回连表达多轮。
- 所有运行节点必须从 START 可达；NOTE / CUSTOM_NOTE 是画布注释，不参与运行，不要求连接。
- 除 START / NOTE 外，节点 title 不能为空、纯空格或重复。
- AGENT 完整 graph 的 `prompt` 和 `displayPrompt` 必须非空；source 阶段只写一个 `prompt`，由 builder 派生两个完整 graph 字段；LibraryBlock 的 display/runtime 文本和绑定必须通过对账；`transferToHumans` 必须为空数组。
- LLM `promptTemplate` 必须非空；LLM 不绑定工具、不配置 next_steps。
- INTENT 节点可选配置全局识别 PE：source 使用 `prompt`，未配置时编译为 `config.prompt: null`；`history_round_limit` 编译为 `config.historyRoundLimit`，默认 `null`（交由后端默认策略）；每条意图仍需要 `name + desc` 或 `intentId`。
- 即将下线节点默认不新建：`COLLECT_ORDER`、`KNOWLEDGE_REPLY`、`VARIABLE_ASSIGNMENT`、`VARIABLE_EXTRACT`、`AGENT version=1`。

## CLI

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow --help --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow compile \
  --source-file /workspace/state/agent-builder/chatflow/chatflow_source.json \
  --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json \
  --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow validate \
  --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json \
  --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow inspect \
  --agent-name Example_Chatflow \
  --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow deploy \
  --agent-name Example_Chatflow \
  --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json \
  --phase preview \
  --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow update \
  --agent-id 2496 \
  --graph-file /workspace/state/agent-builder/chatflow/patch_2496_graph.json \
  --phase preview \
  --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow publish \
  --agent-id 2496 \
  --graph-file /workspace/state/agent-builder/chatflow/patch_2496_graph.json \
  --phase preview \
  --pretty
```

## Write Discipline

- 新建 agent：校验通过后先 `deploy --phase preview`；展示环境、租户、名称和图摘要，用户确认后再用
  `--phase commit --confirmation-token-stdin --idempotency-key <key>` 提交。
- 多个新建 agent 必须逐个 `deploy`，不要在同一条 shell 命令里用 `&` 并发部署。平台
  `createAgent` 在同租户/项目并发创建时可能返回泛化 `System Error`；builder CLI 会按 idempotency key
  记录本地提交状态，且不会自动重试非幂等的创建请求，但操作层仍应顺序创建，避免部分创建成功、
  部分失败后路由状态不完整。
- 增量修改：`update` 同样先 preview，确认后 commit；默认保存草稿，不发布。
- 发布：只有用户明确确认 preview 后，才对同一份 graph 文件执行 `publish --phase commit`。
- 部署失败不要回滚；输出错误、agent_id、graph 文件路径。

## Common Failures

- `Invalid 'tools[N].function.name'`：节点 title 含空格、中文或 `/`，让 builder 清洗或手动改英文 key。
- `GraphDefParseError`：优先检查 AGENT `transferToHumans` 是否非空、SUB_GRAPH 是否有出边。
- TOOL `inputParams` 缺必填参数：source 写 `input_params`，或 compile 加 `--bind-tool-params`。
- IF_ELSE 总走 FALSE：检查 variableSelector 是否多了 `"output"`。
- RAG_REPLY 没有可检索目录时永远 LACK_KNOWLEDGE：`knowledgeDirectoryIds` 未配置或为空。
