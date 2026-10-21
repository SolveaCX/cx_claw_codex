# M10：ChatFlow 服务排查

M10 是 CHAT_FLOW 运行时排查索引。负责从会话记录、graph 配置和日志里确认图是否按预期执行；节点字段、图规范和节点选型不要在这里重复维护，按需读取 agent-builder 的 chatflow 文档。

---

## 边界

M10 只处理已经进入 CHAT_FLOW 之后的问题：

- graph 定义加载、解析、校验失败。
- 节点没有进入、执行异常、输出错误。
- 边路由、`sourceHandle`、`output_handle` 不一致。
- 条件、变量系统字段、上游节点输出读取异常。
- RAG / KU / tool / 子图 / 人审节点在 chatflow 内部的传参、路由和结果消费异常。
- graph 没有正常结束，或停在等待用户输入、人审、子图等状态。

---

## 排查顺序

### 1. 读取当前生效 graph / 配置

从会话记录的 `strategyAction`、`context.ext` 或已知测试结果确认 `agentId`，然后执行：

```bash
python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py inspect --agent-id <agentId> --pretty
```

只要本轮确认进入 CHAT_FLOW，报告前必须读取当前生效的 ChatFlow 图配置。读取图配置的目的不是只做节点/边校验，而是看到全局业务流程，理解失败节点的上游来源、下游去向、变量和工具结果如何传递，必要时给出准确可行的配置建议。

`chatflow_run_info` 只能说明“实际跑了哪些节点”，不能说明“图上原本应该怎么连、节点怎么配、上下游业务和数据流是什么、用户后台当前看到的是否就是这张图”。

`get-agent` 只返回 Agent 元信息，不等于已经读取 ChatFlow 图。inspect 成功前不得输出最终报告，也不得只凭会话记录给出修改节点配置的强建议。

需要补充 Agent 类型、版本等元信息时，可执行：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-agent --id <agentId> --pretty
```

关注点：

- 当前线上生效图是否就是用户以为的那张图。
- 对比运行记录中的 `flow_version`、节点 id 和当前 graph。当前图与历史运行版本无法对应时，只能说明当前状态，不能据此断言历史配置根因。
- 节点 title / id / type 是否能和 `chatflow_run_info`、日志对上。
- 按 `node_id` 在 graph 中定位失败节点，不要只按 title 猜节点。
- CODE 节点报错时，读取 CODE 节点的实际 `source_code`、输入变量选择器和输出字段，确认报错语句确实存在于当前生效配置。
- 核对失败节点的入边和出边，说明它为什么被执行、失败后原本会走向哪里。
- 上一节点 `output_handle` 是否能在 graph 边里找到对应 `sourceHandle`。
- 失败节点的上游业务意图、变量来源、工具/知识结果来源是否合理。
- 失败节点的下游回复、转人工、继续追问或结束路径是否符合业务目标。
- 条件、变量、工具入参、模板、知识目录、子图版本是否和业务预期一致。
- 完整 graph 里的 `NOTE` / `CUSTOM_NOTE` 是画布注释，不参与运行，不要把未连线 NOTE 当作 badcase 根因。

如果 agentId / graphId 无法从会话记录的 `strategyAction` 或 `context.ext` 确认，再查询相关 Agent 配置。拿不到图配置时，报告里必须写明“图配置未能确认”，不要只凭执行日志断定配置根因，也不要给出依赖全局流程判断的强建议。

### 2. 对齐会话执行记录

优先读取：

| 字段 | 含义 |
|------|------|
| `messages[].context.ext.chatflow_run_info` | 节点执行序列、节点状态、部分节点输出 |
| `messages[].context.ext.graph_finished` | graph 是否正常结束 |
| `messages[].type/reason/reasonDesc` | 最终回复类型和失败原因 |
| `messages[].context.metadata.ai_fields` | 条件、变量和工具节点可能依赖的变量系统字段 |
| `messages[].context.timing.__stage_time_total` | 本轮总耗时，辅助判断是否有慢节点 |

常见信号：

| 会话记录信号 | 下一步 |
|----------------|-------|
| `chatflow_run_info` 为空 | 回 M3 / M5，先确认是否真的进入 CHAT_FLOW |
| `graph_finished=false` | 找最后一个执行节点，确认是异常、等待用户输入、人审 interrupt，还是子图未完成 |
| 某个预期节点未出现 | 查上一节点的 `output_handle`、`goto`、routing map 和 graph 边 |
| 条件节点无匹配分支 | 查变量来源、条件配置、`FALSE` / default 兜底边 |
| RAG / KU 节点有执行但内容为空或不准 | M10 只确认 query、知识目录、结果消费；召回内部质量跳 M9 |
| TOOL 节点执行后分支不对 | 查工具入参、原始返回、action status / result routing、下游字段消费 |
| 停在 `USER_INPUT`，或上一节点 `output_handle=WAIT` | 先判断是否正常等待下一轮用户输入，不要直接判定 graph 异常 |
| 停在 `HUMAN_REVIEW` | 先判断是否正常等待人审 resume |
| 停在 `SUB_GRAPH` | 同时查外层 `SUB_GRAPH` 节点和内层 namespace / 子图执行日志 |

### 3. 定位到节点后读 chatflow 文档

报告前必须读取对应 chatflow 文档，避免只按报错字面推断。

| 问题类型 | 必读说明 |
|----------|----------|
| 图结构、边、source JSON、全局校验 | `/skills/agent-builder/references/chatflow/graph-spec.md` |
| 节点选型、是否该用模板/问题/工具/Agent/变量节点 | `/skills/agent-builder/references/chatflow/node-selection.md` |
| 具体节点字段、约束、常见误用 | `/skills/agent-builder/references/chatflow/nodes/<node>.md` |

节点文档映射规则：

- 节点类型转小写并用短横线连接，例如 `IF_ELSE` -> `nodes/if-else.md`，`RAG_REPLY` -> `nodes/rag-reply.md`。
- 特殊节点按文件名读取：`TRANSFER_TO_HUMAN` -> `transfer-to-human.md`，`VARIABLE_PROCESS` -> `variable-process.md`，`SUB_GRAPH` -> `sub-graph.md`。
- `USER_INPUT` 和 `AGENT_TOOL` 是运行时注入节点，优先读其归属业务节点文档；例如 `QUESTION` 等待用户输入时读 `question.md`，`AGENT_TOOL` 工具调用时读 `agent.md` 和 `tool.md`。
- `WAIT` 不是 source graph 里的业务节点；它是运行时 handle，表示节点选择进入注入的 `USER_INPUT`。

### 4. 最后查聚焦日志

日志用于确认会话记录和 graph 无法完全解释的运行时事实。先按 `/skills/shulex-support/references/badcase-analysis/text/sls-query.md` 定位 GPT 侧 trace；进入 chatflow 后读取“跨服务 trace 拼接”，优先用 `armsTrace`。

日志没查到时，报告中写清“日志未能确认”的原因，不要把推断写成日志事实。

---

## 运行模型

chatflow 服务把前端配置的 JSON graph 转成 LangGraph 后执行：

```text
JSON graph
  -> get_or_load_graph_def()
  -> GraphJSONLoader.load_from_dict()
  -> GraphJSONLoader.inject_builtin_nodes()
  -> GraphBuilder.build_graph()
  -> GraphExecutor.execute_stream()
  -> FlowService.execute_flow_stream()
```

排查时重点对齐这些运行时对象：

| 对象 | 排查价值 |
|------|----------|
| `node_results` | 和会话记录的 `chatflow_run_info` 对齐，确认失败或异常输出来自哪个节点 |
| `output.output_handle` | 当前节点实际选择的出边 handle |
| `output.goto` / `Command.goto` | 当前节点实际跳转的下一节点 |
| `execution_path` | 判断节点是否漏走、重复走、或卡在等待/人审/子图 |
| `current_node_name` | `graph_finished=false` 时定位最后卡点 |
| `extra_info.node_extra_info.enter_count` | 判断是否超过 `maxRounds` 或多轮重复等待 |
| `aifield_overrides` | 变量系统字段被 chatflow 内部抽取/赋值覆盖时必须看 |
| `sub_graph_reply_turns` / `sub_graph_path` | SUB_GRAPH badcase 要同时看外层图和内层图 |

注意：

- `USER_INPUT`、`AGENT_TOOL` 是运行时注入节点，可能不在前端原始 graph 中。
- `WAIT` 是 `sourceHandle` / `output_handle`，不是业务节点类型。看到 `output_handle=WAIT` 通常表示当前业务节点进入等待用户下一轮输入。
- 节点名字可能来自 `data.func_name` 或 `data.title`。查日志时同时用 node title、node id、node name 搜索。
- 如果某节点成功执行但没进预期下一节点，优先对齐当前节点的 `output_handle` 和 graph 边的 `sourceHandle`。
- 如果上游已经通过 tars 提前抽取变量系统字段，chatflow 条件和变量节点可能直接消费 `metadata.ai_fields`，不一定会看到 GPT 发起的抽取日志。

---

## 按现象排查

| 现象 | 先看 | 关键判断 |
|------|------|----------|
| 图加载或解析失败 | `get_or_load_graph_def`、graph 配置、`graph-spec.md` | 是 graph 数据缺失、JSON 不合法、节点字段不符合约束，还是后端 parser 规则拦截 |
| 节点没进入 | 上一节点 `output_handle/goto`、graph 边 `sourceHandle` | 上一节点是否走了预期 handle；graph 是否缺对应边 |
| 条件分支不对 | 变量来源、条件配置、`if-else.md` | 变量是否为空；比较符和变量类型是否匹配；是否有 `FALSE` 兜底 |
| 问题节点卡住 | `QUESTION` 节点结果、`question.md`、`USER_INPUT` | 是正常等待用户输入、选项未命中、必填变量缺失，还是轮次达到上限 |
| 回复内容不对 | `REPLY` 节点配置、模板/Prompt、上游节点输出 | 固定话术是否应使用模板；是否禁用了上游结果；模板或变量是否缺失 |
| RAG / KU 没答好 | query、知识目录、召回结果、结果消费 | M10 判断 chatflow 侧 query 和消费；召回内部质量跳 M9 |
| TOOL 入参或路由不对 | 工具配置、入参映射、原始返回、action status | 入参来源是否正确；工具返回是否包含路由字段；下游是否消费了正确字段 |
| AGENT 工具调用异常 | `agent.md`、`tool.md`、绑定工具、next_steps | 工具是否绑定；Agent 是否走到工具调用；next_steps 是否和出边匹配 |
| CODE 节点失败 | `code.md`、resolved inputs、source code、outputs | 先看输入是否解析成功，再看代码运行异常、超时、输出字段/类型 |
| 变量节点不生效 | `variable-process.md`、变量来源、LLM response、assignments | 抽取和赋值分开判断；确认目标变量系统字段是否被覆盖 |
| SUB_GRAPH 失败 | 外层 SUB_GRAPH、子图版本、内层执行路径、`sub-graph.md` | 只看外层节点不够，真正失败点可能在内层图 |
| HUMAN_REVIEW 未继续 | interrupt / resume 日志、`human-review.md` | 是正常等待人审，还是 resume 数据缺失/异常 |
| graph 未结束 | 最后一个节点、`graph_execution_error`、ERROR | 区分正常等待、配置缺边、节点异常、外部服务异常 |

---

## Log 层

### graph 入口、加载、执行

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"get_or_load_graph_def" OR rest:"graph_execution_start" OR rest:"graph_execution_finished" OR rest:"graph_execution_error")' \
  --line 10
```

### 通用节点更新、节点输入、节点错误

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"node_update" OR rest:"node_input_build_failed" OR rest:"node error" OR rest:"Unhandled node error" OR rest:"node_cancelled")' \
  --line 20
```

### 节点进入、条件、意图

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"node_enter" OR rest:"evaluate_condition" OR rest:"case_matched" OR rest:"no_case_matched" OR rest:"intent classification" OR rest:"load_intent_list")' \
  --line 20
```

### RAG / KU 节点

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"rag_reply query_from_selector" OR rest:"rag_summary" OR rest:"rag_reply retrieve" OR rest:"retrieve_query" OR rest:"kb_reply retrieve")' \
  --line 20
```

### 工具、Agent 工具、变量

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"tool_node args" OR rest:"tool_node result" OR rest:"tool_node routing" OR rest:"agent_tool_node" OR rest:"tool_executed" OR rest:"selected variable not found" OR rest:"variable extract" OR rest:"variable_assignment" OR rest:"variable_process")' \
  --line 20
```

### 代码、子图、人审、等待

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"code_node" OR rest:"sub_graph" OR rest:"human_review" OR rest:"_user_input" OR rest:"output_handle" OR rest:"enter finish node")' \
  --line 20
```

### fallback / ERROR

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"llm_call_with_fallbacks" OR severity:"ERROR")' \
  --line 20
```

如果 `armsTrace` 不可用，用 `chatId`、graphId / runId、接口路径、节点名和时间窗组合查询：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <begin> \
  --to <end> \
  --query 'rest:"<chatId>" AND (rest:"graph_execution" OR rest:"node_update" OR rest:"node_enter" OR rest:"tool_node")' \
  --line 20
```

---

## 报告口径

最终报告不要堆源码名。用业务语言先说发生了什么，再说明为什么，并给出最小证据：

- 必须写清楚节点 title / id / type，以及它前后走了哪条边。
- 配置问题标 `[可自行调整]`，说明用户可在后台检查哪个节点、模板、变量、工具或知识配置。
- 系统异常、parser 错误、服务 ERROR、外部接口异常标 `[需联系研发]`，给出 trace、armsTrace、节点名和关键日志。
- 如果只是停在 `USER_INPUT` 或人审等待，先说明这是等待态；只有超时、resume 失败、用户输入没有恢复执行时才判异常。
- 如果 NOTE 未连接、未从 START 可达，不要作为运行时根因；NOTE 是画布注释。
- 如果日志没查到，写“日志未能确认：<原因>”，不要伪造日志结论。
