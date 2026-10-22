# MULTI_AGENT Graph Spec

本文件只解释 legacy MULTI_AGENT 的旧 JSON 结构、证据优先级和清洗规则，不包含目标图映射。

## 输入形态

analyzer 和人工阅读都应支持三种输入：

```json
{"id": 123, "type": "MULTI_AGENT", "meta": {"multiAgentGraph": {"agents": [], "agentEdges": []}}}
```

```json
[{"category": "TEXT", "meta": {"multiAgentGraph": {"agents": [], "agentEdges": []}}}]
```

```json
{"entryAgentId": "agent_a", "agents": [], "agentEdges": []}
```

## 核心字段

| 字段 | 说明 |
|------|------|
| `entryAgentId` | 旧图入口 agent id；没有时用入边推断 |
| `agents[]` | 子 agent 列表 |
| `agents[].id/name/type` | 子 agent 标识、名称、类型 |
| `agents[].prompt` | 旧 PE，保留业务语义，但不能覆盖结构化 action/tool 证据 |
| `agents[].displayPrompt` | 前端展示内容，常含 HTML 和占位符；默认不作为模型输入 |
| `agents[].usedPlugins[]` | 真实绑定工具 |
| `agentEdges[]` | 显式 old agent 跳转 |
| `meta.classifierPlugin` | 旧分类器及其 action |
| `meta.templateReplyPlugin` | 模板回复结构能力 |
| `meta.transferToHumanPlugin` / `transferToHumans[]` | 转人工结构能力 |
| `meta.finishAgentPlugin` | 结束结构能力 |
| `meta.knowledgeAiReplyPlugin` | 旧知识回复配置 |

## 工具字段

| 字段 | 说明 |
|------|------|
| `usedPlugins[].id/name/type` | 工具 id、名称、类型 |
| `usedPlugins[].meta.externalHttpCallConfig.requestParam` | 外部工具入参 |
| `usedPlugins[].meta.externalHttpCallConfig.responseParam` | 外部工具出参 |
| `usedPlugins[].meta.externalHttpCallConfig.actionStatuses[]` | 工具状态分支 |
| `usedPlugins[].meta.toolAfterExecuteActions[]` | 工具执行后的结构化 action |

`toolAfterExecuteActions[].actions[]` 常见 action：

| type | 旧图控制语义 |
|------|----------|
| `SWITCH_AGENT` | 跳到另一个 old agent |
| `TEMPLATE_REPLY` | 执行模板回复动作 |
| `TRANSFER_TO_HUMAN` | 发起人工接管动作 |
| `FINISH_AGENT` | 结束当前处理 |

### 运行时控制语义

Java `MultiAgentService.getLangGraphStructure` 会把 legacy multi 转成 agent_graph 结构：

- `entryAgentId` 作为唯一入口。
- `agentEdges[]` 会转成 `agent_edges[fromAgentId] = [toAgentId...]`。
- 每个 agent 的内置 meta plugin 和 `usedPlugins[]` 都会变成 agent 可调用工具。
- 每个工具保留自己的 `toolAfterExecuteActions`；外部工具的 action 配置保存在 multi graph 里，刷新工具定义时会补回。

Python agent_graph 运行时会把 `agentEdges[]` 变成 `transfer_to_<agent_name>` 的 `SWITCH_AGENT`
工具，只暴露给对应上游 agent；工具 action 中的 `SWITCH_AGENT.value` 是目标 agent id，运行时再
查成目标 agent name 并跳转。读取旧图时应按以下方式理解：

- `SWITCH_AGENT` 是控制流，不是外部 HTTP 工具。
- `agentEdges[]` 表示模型可主动选择的相邻 agent；`toolAfterExecuteActions[].actions[].type=SWITCH_AGENT`
  表示某个工具状态或分类结果命中后自动进入目标 agent。
- 目标 agent 是否承载独立 SOP 职责、工具、用户轮次、回复或判断，应作为后续迁移的语义证据；纯跳转壳必须被明确标记，不能与独立职责混淆。

`toolAfterExecuteActions` 的匹配规则：

- 外部 HTTP / 订单 / 物流工具按返回的 `__status` 匹配 `matchStatus`。
- classifier 按分类返回的 `category` 匹配 `matchStatus`。
- `matchStatus == null` 是兜底 action，运行时按列表顺序取第一条匹配项。
- 同一个匹配项里的 `actions[]` 是动作序列；可能先有 `TEMPLATE_REPLY` 或
  `user_input_template_*`，再 `SWITCH_AGENT` / `TRANSFER_TO_HUMAN` / `FINISH_AGENT`。
  因此迁移时不能只看最终动作，必须保留“先回复/模板，再跳转/转人工/结束”的组合语义。

## 证据优先级

1. `entryAgentId` 定入口。
2. `usedPlugins[]` 定真实工具。
3. `externalHttpCallConfig.actionStatuses[]` 定工具状态分支。
4. `toolAfterExecuteActions[]` 和 `classifierPlugin.meta.toolAfterExecuteActions[]` 定隐式动作边。
5. `agentEdges[]` 定显式 old agent 跳转。
6. template / transfer / finish / KB meta tools 定结构能力。
7. `prompt` 只补业务语义和话术边界。
8. `displayPrompt` 只做前端噪音检测、占位符审计和人工核对。

证据冲突时，以 action/tool/plugin 结构优先；prompt 冲突进入 `open_questions`。

## 前端噪音清洗

### 工具渲染壳与真实工具语义必须分开

旧 multi 的 `displayPrompt` 不是纯展示文本。编辑器会把工具插入渲染成类似：

```html
<span style="color: #00CDAC">{{Obtain_Package_OrderDetails}}</span>
```

这里的 `<span>`、`style` 和嵌套标签是展示壳；`Obtain_Package_OrderDetails` 是工具引用，
不能因为清洗 HTML 而丢失。解析时必须同时保留三类证据：

| 证据 | 作用 | 处理方式 |
|------|------|----------|
| `displayPrompt` 中的 `{{ToolName}}` | 编辑器插入的工具 chip | 去掉标签和样式，提取为 `tool_references` |
| `agents[].usedPlugins[]` | 当前 old agent 真正绑定的外部工具 | 保留 id/name/type、请求/响应参数和状态 |
| `meta.*Plugin` / `classifierPlugin` | 系统工具、分类器和模板/转人工能力 | 保留工具类型、配置和 action |

`tool_references` 必须与结构化工具证据做对账：

- 引用与 `usedPlugins` 或系统 plugin 匹配：视为已绑定可执行资源，保留其 id/type/action 证据；
  后续映射由迁移文档决定。
- 引用只出现在 `displayPrompt`，但结构化 plugin 存在：保留 plugin 证据，记录为渲染引用。
- 引用只出现在 `displayPrompt`，找不到结构化 plugin：不得静默删除，但只写入 audit warning，
  不生成用户问题。PE 中是否存在可执行引用，由 batch worker 结合完整 PE、结构化资源和流程上下文做
  语义判断；analyzer 不用 `call/use <name> tool` 等短语正则生成 blocking 结论。worker 确认存在动作但仍
  无法确定绑定时，才写入 `open_questions`。
- `Template_Reply`、`Transfer_To_Agent`、`Finish_Agent` 不是普通文案，分别按旧系统动作/终端
  语义记录；其中 template id、transfer reason 和 action status 优先从结构化字段取值。

系统知识占位符 `{{KB_Reply}}` 可按 `name=KB_Reply`、`source=SYSTEM`、
`type=KNOWLEDGE_AI_REPLY` 识别。知识配置既可能直接位于 `knowledgeAiReplyPlugin.directoryIds`，也可能
位于 `knowledgeAiReplyPlugin.meta.knowledgeAiReplyConfig.directoryIds`；后者的启用状态优先。明确
`enable=false` 的 KB 只保留 audit。已启用或启用状态未知的 KB 目录为空才是
blocking 风险：提供可用 directory id 或明确移除该能力。没有插件的 display-only `KB_Reply` 同样只是
audit；只有结构化 SYSTEM 能力或明确可执行 prompt 调用缺失时才进入 blocking open question。

必须清掉或降权：

- `createdAt`、`updatedAt`、`createdBy`、`updatedBy`、`createAtLong`、`updateAtLong`
- `displayData`、`positions`、`viewport`、前端画布样式
- 完整 `displayPrompt` HTML 文本
- `<span style=...>`、嵌套标签和孤立 `style="...">` 这类展示壳
- 已经提取为 `tool_references` 的原始占位符文本

清洗后保留：

- `prompt` 的业务语义片段。
- `prompt_review.prompt` 中经可恢复编码修复后的完整 PE、SHA-256 和字符数；它不受 evidence 预算截断。
- `prompt_review.protected_refs` 中已经由 PE runtime 语法明确表达的模板、转人工和已绑定业务工具引用；
  每项保留稳定 ID、精确 span/quote 和原始绑定，供合并校验防漏防篡改。自然语言中的固定话术、等待点和
  其他动作不由该字段推断，仍交给全文语义审阅。
- `displayPrompt` 的纯文本摘要、长度、占位符名、是否含 HTML。
- 从渲染 chip 提取的 `tool_references` 及其结构化绑定状态。
- 结构化 action/tool/template/transfer/finish/KB 证据。

## Analyzer 产物

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py inspect \
  --input /workspace/state/agent-builder/multi-agent/read_<agent_id>_raw.json \
  --out-dir /workspace/state/agent-builder/multi-agent \
  --pretty
```

输出目录：

```text
/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/
  index.full.json
  index.ai.json
  overview.mmd
  chunks.json
  progress.json
  batches/worker_manifest.json
  batches/<batch>.context.json
  batches/<batch>.plan.json
```

| 文件 | 用途 |
|------|------|
| `index.full.json` | 完整语义索引，供人工审计 |
| `index.ai.json` | 已裁剪、可给模型读取的语义输入 |
| `overview.mmd` | 旧图 Mermaid 总览 |
| `chunks.json` | chunk 清单 |
| `progress.json` | batch 可恢复进度；并发状态以 `active_batch_ids[]` 为准，`current_batch_id` 只兼容单 worker 旧目录 |
| `batches/worker_manifest.json` | 一个并发 wave 的隔离输入/输出路径和 worker 合同 |
| `batches/<batch>.context.json` | worker 只读的有界输入 |
| `batches/<batch>.plan.json` | worker 独立写入的语义计划；不写共享 progress 或局部 Mermaid |

`index.full.json` / `index.ai.json` 还包含统一 `resources[]`：外部 plugin、SYSTEM chip、知识能力和
未识别引用都必须在其中有 `resource_kind`、证据来源和目标映射。迁移 coverage 应引用这份清单，
不要分别从 prompt、usedPlugins 和 meta 再次猜测同一资源。

图结构事实位于 `topology`：`control_edges` 只包含结构化 `SWITCH_AGENT` 的确定性控制流；
`model_selectable_edges` 单列 `agentEdges[]` 的模型可选跳转。`reachable_agent_ids` 表示旧运行时可达性，
`deterministically_reachable_agent_ids` 只按确定性控制流计算。AI 建立 SOP 时必须区分二者，不能把
`model_selectable_edges` 自动变成目标图边；`overview.mmd` 用虚线展示它们。`unreachable_agent_ids` 非空时
仍是阻塞风险，不能静默补边或丢弃。

`index.ai.json` 中每个 agent 都带精简 `action_edges`，保留来源、工具、`match_status`、动作类型、
目标和模板状态，但不带前端 raw 字段。这样 AI 可以按 agent 读取完整分支合同，又不会把整份 legacy
JSON 或 HTML 噪音重复塞入上下文。

PE 还带 `prompt_review`、`prompt_quality` / `prompt_evidence.encoding_quality`：

- `clean`：未发现明显编码异常；
- `mojibake_suspected`：疑似 UTF-8/Latin-1 错解码；
- `replacement_character`：出现 Unicode replacement character `�`。

分析器会把经可恢复编码修复后的完整 PE 写入 `prompt_review.prompt`，并记录 `prompt_sha256` /
`prompt_char_count`；这是 worker 的强制全文审阅合同。另将 HTML 噪音和 legacy 工具指令清洗到
`agent.prompt` / `prompt_evidence.evidence`，仅用于紧凑的流程摘要。`prompt_evidence.encoding_quality`
记录清洗前质量，`prompt_evidence.cleaned_encoding_quality` 记录清洗后质量；编码问题本身不是迁移阻塞项。

`coverage_required.prompt_reviews` 会把完整 PE 原样带进对应 batch，即使 `prompt_evidence` 因预算被截断也不
截断。worker 输出 `discovered_blocks` 和 `control_semantics`；`merge-batch-plans` 再根据结构化 kind、具体
模板/工具 id、精确转人工 reason 和完整固定话术派生 LibraryBlock、plugin 绑定与内容 hash。自然语言识别和
协议渲染因此分层：前者由模型理解流程，后者由脚本确定性生成。固定话术使用通用
`NODE_PROMPT_FIELD`，最终按已选节点合同填写 `render_path`；analyzer 不把它预设成 REPLY。

索引还包含 `coverage_manifest`，为 agents、tools、resources、explicit edges、action edges 和
`prompt_reviews` 提供稳定 ID。最终 migration plan 必须按 ID 对账；只按节点数量相等不能证明迁移完整。

并发生成/恢复 batch context（每批默认 4 个 chunk、12 条 action edge、20000 evidence 字符）：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py prepare-batches \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.ai.json \
  --chunks-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/chunks.json \
  --progress-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/progress.json \
  --out-dir /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches \
  --parallelism 4 \
  --pretty
```

协调器读取 manifest 后并发运行 worker；每个 worker 只读取自己的 context、写自己的 plan，不向用户提问、
不生成 Mermaid，也不修改 `progress.json`。worker 全部结束后由 `merge-batch-plans` 串行合并和更新共享进度。

生成 migration plan 后，先用脚本检查流程骨架、节点决策和 coverage：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py validate-migration-plan \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json \
  --pretty
```

该检查未通过时只能继续补迁移 plan，不能进入完整的迁移产物生成阶段。
