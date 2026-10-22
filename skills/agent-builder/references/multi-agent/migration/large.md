# 迁移模式：large legacy MULTI_AGENT -> CHAT_FLOW

用于长旧版 `multiAgentGraph`、`displayPrompt` 很长、agent/action/tool 较多，或用户要求“先拆解、再分步迁移”的场景。脚本负责确定性解析、清洗、分块和进度；多个隔离 worker 可并发理解有预算的 batch，协调器负责合并、去重问题和最终确认。`prepare-batches` 只准备并发 wave，不启动 worker；只有协调器在同一轮并列发出多个 `task` tool call 时，运行时才会真正异步并发。

开始前先读 `../graph-spec.md` 和 `principles.md`。本文件只产出旧图证据、coverage、业务职责、候选节点类别和迁移决策。不要在这里填写目标节点字段、默认边，或重复目标图的构图、编译、校验、发布规则。

## 执行要求

| 工作 | 执行者 | 结果 |
|---|---|---|
| 读取 raw JSON、裁剪前端噪音 | 脚本 | 可复用的语义索引 |
| 抽取工具、动作、边、模板、知识能力并完整保留 PE | 脚本 | 结构化证据、`prompt_reviews` 和风险分级 |
| 理解 PE 中的可执行语义、固定话术和等待点 | 无交互 worker | 基于全文与流程上下文的 `discovered_blocks`；不使用短语/正则分类 |
| 拓扑、SOP、合并/拆分合同 | 模型 | 可合并的旧图理解 |
| 每个 batch 的语义映射和 coverage | 无交互 worker | 独立 batch plan，不生成 Mermaid |
| 进度、batch 选择、plan 合并和 checkpoint | 协调器 + 脚本 | 无共享写竞态的可恢复状态 |
| 目标 source、资源绑定、边、编译、校验、发布 | CHAT_FLOW 阶段 | 按 `../../chatflow/` 文档执行 |

模型在本文件阶段只能把 `TOOL`、`QUESTION`、`REPLY`、`INTENT`、`IF_ELSE`、`LLM`、`AGENT`、`TRANSFER_TO_HUMAN`、`FINISH`、`VARIABLE_PROCESS` 等写成**候选类别**。完成一个确认过的迁移计划后，才进入 CHAT_FLOW 文档确定实现。

## 大图的有界执行

大图必须按“脚本确定结构，模型做局部语义决策”执行。不要让模型反复读取完整 legacy JSON 或在对话中累积全图状态。

1. `inspect`：脚本生成索引、chunk、流程理解 seed 和 `progress.json`。
2. `claim`：协调器用 `prepare-batches` 一次认领最多 N 个互不重叠的 batch，生成 worker manifest。
3. `workers`：协调器在同一轮为 manifest 中每个 batch 并列发出一个 `task` tool call；worker 各自只读一个 context、只写一个 plan，不询问用户、不修改共享 progress、不生成 Mermaid。
4. `merge`：协调器用 `merge-batch-plans` 串行合并所有已完成 plan、去重问题并更新 checkpoint；还有 pending chunk 时继续下一 wave。
5. `questions`：所有 batch 完成后，只向用户集中提出合并后的 blocking `open_questions`；worker 不自行确认。
6. `mapping`：问题解决后生成唯一一张全局 SOP → 节点映射 Mermaid，作为唯一结构确认门。
7. `handoff`：全局图确认后，转到 CHAT_FLOW 文档按确认的流程块实现目标图。

这里的并发分三层，不能混称：`prepare-batches --parallelism N` 只证明一次切出了 N 个互不重叠的 context；
manifest 中有 N 个 batch 只证明它们可并发；同一 assistant turn 中出现 N 个 `task` tool call，且运行时等待
全部结果后再 merge，才是实际异步并发。若协调器逐个调用、等待、再调用，即使 `parallelism=4` 也只是串行批处理。
运行时不支持同轮多 tool call 时，显式退化为 `parallelism=1`，不要声称并发。

默认 batch 上限为 4 个 chunk、12 条 action edge、20,000 个 prompt evidence 字符。单个 SCC 超出预算时必须整体保留并在 `budget_exceptions` 中留痕；不能为了凑预算把环拆开。提高工具运行上限只能提供缓冲，不能替代 batch 边界。

会话中断或上下文压缩后，先读取 `progress.json`、worker manifest 和已完成 plan。恢复时以
`active_batch_ids[]` 为准并重新发出同一批 context；不得重新挑选 chunk 或重新分析全图。`current_batch_id`
只兼容旧的单 worker 目录，多 batch 时应为空。

## 先理解旧流程，再映射候选

在处理任何 batch 前，先根据 `overview.mmd`、`index.ai.json` 和工具/action 索引输出 `flow_skeleton`。它至少包含：

- 唯一入口、阶段、汇合点和终端；
- 每个工具及其状态/结果分支；
- 每个 classifier 的完整分类集合；
- 用户补充信息、确认、模板回复、人工接管、固定完整话术、等待点和结束的顺序；
- 不同地区、渠道、商品、客户类型或处理结果形成的独立业务主线；
- 可达性事实和跨 batch anchor。

每个 chunk / 阶段必须写清输入、用户轮次、资源调用、分支集合、输出语义和下游职责。多个单元想合并时，`merge_groups` 必须证明输入、用户轮次、资源合同、分支集合和下游语义一致；仅名称或 prompt 相似不够。

以下默认是保护单元，除非结构化证据完全一致，不得合并：

- 不同 action status、模板、人工接管原因、结束语义或用户轮次；
- 不同外部工具、工具参数/结果合同或知识启用状态；
- 不同业务主线、分类树或处理结果；
- 同一个动作组中“先回复再跳转/人工接管/结束”的动作顺序；
- `matchStatus == null` 的兜底出口。

`SWITCH_AGENT` 是旧控制流，不是外部工具。仅承担跳转且没有独立 SOP 的 old agent 应标记为 `edge_only`；有独立用户交互、资源调用、判断或终端职责时才进入候选节点映射。

`agentEdges[]` 与 `SWITCH_AGENT` 不可混写：前者只是模型可选择的相邻职责，不能进入 batch 的确定性
control topology，也不能自动生成目标图边；后者才是结构化结果命中的确定性流转。batch context 会把
`agentEdges[]` 单列为模型可选证据，模型根据 SOP 决定保留、吸收或在最终全局计划中结构化，不因旧边存在而
机械生成一对一连线。

## 固定脚本流程

先执行 inspect：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py inspect \
  --input /workspace/state/agent-builder/multi-agent/read_<old_agent_id>_raw.json \
  --out-dir /workspace/state/agent-builder/multi-agent
```

它会生成稳定目录：

```text
/workspace/state/agent-builder/multi-agent/migrate_<old_agent_id>_<agent_name>/
  index.full.json
  index.ai.json
  overview.mmd
  chunks.json
  flow_understanding.seed.json
  migration_plan.template.json
  coverage.template.json
  progress.json
```

## AI 输入裁剪

AI 不直接读取完整 raw JSON。`index.ai.json` 只用于理解拓扑、角色、分支和风险；工具请求参数、模板正文或
某个 old agent 的完整业务 PE，只在处理对应 batch 时按需读取，不能把 `index.full.json` 整体塞进模型上下文。

检索这些 JSON 产物时，不要反复用内置 `grep` / `read_file` 搜索同一个大文件。跨多个工具 id、old agent id、
action status、template id 或变量 selector 的核对，必须优先用一次 `execute` 批处理。JSON 的结构摘要、筛选、
字段投影和统计优先使用 `jq` 生成紧凑输出，不得把完整 JSON 回传模型；复杂跨文件关联、复杂转换或生成逻辑
才使用短 Python 脚本。例如，读取指定工具的摘要：

```bash
jq -c --argjson wanted '["24655", "24992", "26918"]' '
  def compact_value:
    if . == null then null
    elif type == "object" then {kind: "object", key_count: length, keys: (keys | .[:20])}
    elif type == "array" then {kind: "array", count: length}
    else {kind: type, preview: (if type == "string" then .[0:160] else . end)}
    end;
  .tools[]
  | select((.id | tostring) as $id | $wanted | index($id))
  | {
      tool_key,
      agent_id,
      id,
      name,
      tool_type: .type,
      request_param_summary: (.request_param | compact_value),
      response_param_summary: (.response_param | compact_value),
      action_status_count: ((.action_statuses // []) | length),
      action_status_names: ([((.action_statuses // [])[]? | .name)] | .[:20])
    }
' /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json
```

命令输出只保留迁移需要的字段，并限制 key、状态名和字符串预览长度；如结果较长，写入
`/workspace/tmp/agent-builder/*.json` 后再读摘要。只有要审计具体片段时，才读取相应 offset。

`unreachable_agents_count > 0` 或 `risk_items.type=unreachable_agent` 是真正的 blocking 项。必须恢复来源 edge 或获得用户确认的删减决定，不能静默丢弃。

一次领取或恢复一个并发 wave：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py prepare-batches \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.ai.json \
  --chunks-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/chunks.json \
  --progress-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/progress.json \
  --out-dir /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches \
  --manifest-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches/worker_manifest.json \
  --parallelism 4 \
  --max-chunks 4 \
  --max-action-edges 12 \
  --max-evidence-chars 20000
```

该命令由协调器调用一次并原子替换共享 progress 文件；每个 batch 使用唯一的 `<batch>.context.json` 和
`<batch>.plan.json`。已有 active batch 会原样恢复，context 误删时可用 `emit-batch-context --batch-id <id>`
重建。命令输出中的 `workers_started=false` 是刻意设计：协调器读取 manifest 后，必须在同一轮并列派发
全部 worker。worker 不写共享 progress，因此 worker 之间没有共享写竞态；`prepare-batches` 和
`merge-batch-plans` 仍是单协调器串行 checkpoint，不能由两个协调器同时调用。`prepare-batch` 和单 chunk
命令只兼容已有迁移目录，新的大图流程不使用。

并发 worker 全部写完 plan 后，由协调器合并；worker 禁止直接调用 `update-batch-progress`：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py merge-batch-plans \
  --base-plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.template.json \
  --manifest-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches/worker_manifest.json \
  --progress-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/progress.json \
  --out-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --open-questions-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/open_questions.json \
  --mermaid-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/sop_mapping.mmd \
  --pretty
```

合并器会读取 progress 中所有已完成 batch plan，而不只读取当前 wave；因此可重复执行多轮
`prepare-batches → 并发 worker → merge-batch-plans`。只要仍有 pending chunk，或仍有未解决
`open_questions`，就不会生成 `sop_mapping.mmd`。

## Step 1：建立全局骨架（内部）

读取 `index.ai.json` 后，把摘要、SOP 拆解、chunk 清单和风险分级写入 migration plan；不生成目标 source，
也不要求用户先确认骨架。可以发送一句简短进度更新，但不展示中间 Mermaid 或 coverage 表。

```text
Source: <id> "<name>"
Entry: <agent>
Agents: N
Tools: N
Explicit edges: N
Action edges: N
Chunks: N

## 旧 Multi 流程理解
| 阶段 | 输入/用户轮次 | 旧证据 | 分支/出口 | 风险 |

## SOP 拆解
| SOP 步骤 | 触发条件 | 处理动作 | 用户可见回复/等待 | 下游 |
```

这一阶段不向用户提问。会改变可执行语义的缺口先记录为 batch `open_questions` 候选；未绑定 display chip、
HTML 壳和泛化的 “use this/that tool” 只记 audit warning。协调器完成全部 batch 后再统一去重、集中询问。

## Step 2：按 batch 写迁移计划

每个 worker 只读取 manifest 指定的 `<batch>.context.json`。`coverage_required.prompt_reviews` 是必读合同；
其中 `prompt` 始终是完整 PE，不受 `prompt_evidence` 的字符预算和截断影响。worker 必须逐份阅读全文，并结合
同一 context 中的 tools、resources、action edges、cross-batch anchors 和上下游职责理解语义。不得用
`template id`、`reason`、`following template`、`wait for reply` 等字面模式或语言专用正则代替语义判断。
worker 直接写 `<batch>.plan.json`，不得在对话中展示或等待用户确认。

worker plan 内部必须同时记录旧职责、结构化证据、保留语义、合并/改写理由，以及每个 Prompt 引用的
资源/动作证据、目标承载方式、清理项和缺口。模板、人工接管、普通工具、固定完整话术和等待点按 PE 中的
源顺序写入 `coverage_delta.prompt_reviews[].discovered_blocks`；内部跳转、finish 和 actionStatus 分支写入
`control_semantics`。合同中的 `protected_refs` 只标记 PE 已渲染出的无歧义 runtime 工具语法；worker 必须
以相同 source span 和具体 ID/name/reason 覆盖它们（显式 resolved drop 除外），同时仍要阅读全文识别无法
由该确定性集合覆盖的固定话术、等待点和上下文动作。

batch plan 是语义合同，不是目标图 schema。以下是单个 batch 的语义片段；它用于合并到 analyzer
生成的完整 `migration_plan.template.json`，不能单独作为 `validate-migration-plan` 的输入：

```json
{
  "batch_id": "batch_001",
  "chunk_ids": ["chunk_00_entry", "chunk_01_lookup"],
  "skeleton_stage": "order_lookup",
  "flow_skeleton_delta": {
    "stages": ["order_lookup"],
    "protected_branches": ["ORDER_NOT_FOUND"]
  },
  "old_semantics": [
    {"source": "agent prompt", "summary": "collect order information"},
    {"source": "tool actionStatus", "summary": "route by lookup result"}
  ],
  "candidate_nodes": [
    {
      "mapping_key": "collect_order",
      "type": "QUESTION",
      "responsibility": "Collect the required order information."
    },
    {
      "mapping_key": "lookup_order",
      "type": "TOOL",
      "responsibility": "Call the structured order lookup capability."
    }
  ],
  "node_decision_delta": [
    {
      "old_id": "agent_collect_order",
      "candidate_nodes": ["QUESTION", "AGENT"],
      "reason": "The legacy prompt combines collection and contextual policy handling.",
      "evidence": ["agent prompt"]
    }
  ],
  "flow_relations": [
    {
      "from_responsibility": "order lookup",
      "condition": "ORDER_NOT_FOUND",
      "next_responsibility": "human handoff"
    }
  ],
  "sop_mapping": {
    "blocks": [
      {
        "id": "collect_order",
        "responsibility": "Collect the required order information.",
        "candidate_nodes": ["QUESTION"]
      },
      {
        "id": "lookup_order",
        "responsibility": "Call the structured order lookup capability.",
        "candidate_nodes": ["TOOL", "IF_ELSE"]
      }
    ],
    "relations": [
      {"from": "collect_order", "to": "lookup_order", "condition": "order information complete"}
    ]
  },
  "coverage_delta": {
    "agents": [
      {
        "old_id": "agent_collect_order",
        "mapped_to": ["collect_order"],
        "decision": "rewritten",
        "reason": "The legacy prompt mixed information collection with routing."
      }
    ],
    "tools": [
      {
        "old_tool_key": "<coverage_required.tools[].old_tool_key>",
        "old_tool_id": 8299,
        "mapped_to": ["lookup_order"],
        "decision": "preserved",
        "reason": "The structured lookup capability is retained."
      }
    ],
    "actions": [
      {
        "action_id": "<action_id>",
        "from_old_agent": "agent_lookup",
        "match_status": "ORDER_NOT_FOUND",
        "action_type": "TRANSFER_TO_HUMAN",
        "mapped_to": ["human_handoff"],
        "decision": "preserved",
        "reason": "The handoff branch remains explicit."
      }
    ],
    "prompt_reviews": [
      {
        "contract_id": "prompt_review_collect_order",
        "source_prompt_sha256": "<context prompt_sha256>",
        "reviewed_full_prompt": true,
        "decision": "preserved",
        "mapped_to": ["collect_order"],
        "reason": "The complete PE governs this multi-turn responsibility.",
        "control_semantics": [
          {
            "kind": "FLOW_INTERNAL_JUMP",
            "source_quote": "Continue with replacement handling",
            "mapped_to": ["replacement_flow"]
          }
        ],
        "discovered_blocks": [
          {
            "block_id": "refund_template",
            "kind": "TEMPLATE_REPLY",
            "sequence": 0,
            "source_span": {"start": 120, "end": 165},
            "source_quote": "Send the configured refund retention response.",
            "template_id": 1769,
            "decision": "preserved",
            "target_type": "AGENT_LIBRARY_BLOCK",
            "mapped_to": ["collect_order"],
            "reason": "Context determines whether the first response is needed."
          },
          {
            "block_id": "refund_policy_wording",
            "kind": "FIXED_WORDING",
            "sequence": 1,
            "source_span": {"start": 166, "end": 260},
            "source_quote": "<directive plus the exact customer-facing paragraphs>",
            "content": "<all customer-facing paragraphs copied verbatim>",
            "decision": "preserved",
            "target_type": "NODE_PROMPT_FIELD",
            "mapped_to": ["collect_order"],
            "reason": "The wording is part of the same multi-turn responsibility."
          },
          {
            "block_id": "wait_after_policy",
            "kind": "WAIT_FOR_USER",
            "sequence": 2,
            "source_span": {"start": 261, "end": 294},
            "source_quote": "Pause until the customer responds.",
            "rendered_instruction": "After sending the policy, wait for the customer's next reply before continuing.",
            "decision": "preserved",
            "target_type": "AGENT_WAIT",
            "mapped_to": ["collect_order"],
            "reason": "The next decision depends on a new customer turn."
          },
          {
            "block_id": "refund_handoff",
            "kind": "TRANSFER_TO_HUMAN",
            "sequence": 3,
            "source_span": {"start": 295, "end": 348},
            "source_quote": "Escalate with the exact reason want refund if they insist.",
            "transfer_reason": "want refund",
            "decision": "preserved",
            "target_type": "AGENT_LIBRARY_BLOCK",
            "mapped_to": ["collect_order"],
            "reason": "Escalation remains contextual after the waiting turn."
          }
        ]
      }
    ]
  },
  "prompt_cleanup": ["remove legacy structural instructions"],
  "open_questions": []
}
```

`coverage_delta` 必须逐项复制 `coverage_required` 中的稳定标识，不能重算或只写显示字段：agent 用
`old_id`，tool 必须用 `old_tool_key`（`old_tool_id` 可能跨 agent 重复），action / explicit edge / resource
分别用 `action_id` / `edge_id` / `resource_id`，其余合同项用 `contract_id`。

`coverage_required` 的每个 section 都是本 batch 的强制清单，包括 agents、tools、actions、explicit edges、
resources 及适用的 classifier/template/interaction/branch/prompt 合同；`coverage_delta` 必须逐项回写决定。
共享资源或跨 batch edge 可在多个 batch 出现，各 worker 只写本 batch 有证据的目标，合并器会对
`mapped_to` / `rendered_to` / `source_nodes` 做并集并保留逐 batch 理由。

`coverage_delta.prompt_reviews` 必须覆盖 context 的每个 `coverage_required.prompt_reviews`，回写相同 PE hash，
并让每个 `discovered_blocks[].source_quote` 与完整 PE 的 `source_span` 精确对应。worker 输出的是结构化语义，
其中每个 `protected_refs[]` 都必须由同 span、同 kind、同具体绑定的 discovered block 覆盖；
不手写 LibraryBlock、`required_used_plugins`、`required_plugin_types`、`target_options` 或内容哈希；`merge-batch-plans` 根据 kind 和
具体 id/reason/content 动态派生这些协议字段。固定话术不因最终选择哪一种可承载 PE/文本指令的节点而省略；
batch worker 将它映射为通用 `NODE_PROMPT_FIELD`，不预设成 REPLY。最终全局节点类别确认后，协调器按实际
节点合同填写 `render_path`，它可以指向 AGENT 或其他真实承载该 PE/文本指令的节点字段。
`validate-migration-plan` 会先核对全文审阅、source span、内容哈希和映射决定；目标 source 写完后的
`validate-prompt-block-rendering` 再核对 `render_path` 和逐字保留结果。

每个 old agent、真实 tool、explicit edge、action edge 都必须有 coverage。允许 `merged`、`split`、`rewritten` 或 `edge_only`，但每项都要有 evidence；`dropped` 必须有用户确认。
汇总 batch fragments 时，以 analyzer 生成的 `migration_plan.template.json` 为完整计划骨架，保留其
流程骨架、合并合同、节点选择和所有 coverage section；不要自行删字段或改造成目标图 schema。

禁止为单个 batch 生成或展示 Mermaid。局部 `sop_mapping` 只作为 JSON 片段参与确定性合并；跨 batch
anchor 在最终全局图中统一呈现。

### 知识能力和 open questions

旧知识能力的目录既可能位于直接 `directoryIds`，也可能位于
`meta.knowledgeAiReplyConfig.directoryIds`；后者的启用状态优先。

- 明确 `enable=false` 且目录为空：保留 audit，不提问。
- 已启用或启用状态未知且目录为空：blocking；要求提供目录或明确移除该能力。
- 仅 display-only 的知识占位符：audit warning，不伪造缺失依赖。
- worker 结合完整 PE 和流程上下文确认存在可执行工具/模板/终端语义，但具体绑定仍无法确定：blocking
  open question。不能仅因命中某个词语就提问。

worker 为每个 open question 给出稳定 id、2–3 个可执行选项、推荐项、影响和 `blocking=true`，但不得直接
询问用户。协调器按 id/问题语义去重后一次性展示。例如空知识目录的推荐项可以是“提供可用目录”；其他选项
是“确认移除该能力”或“用户指定一个现有目录”。不要用目标节点的内部名替代业务决策。

`merge-batch-plans` 把所有 fragments 汇总进完整 `migration_plan.json`，合并 `sop_mapping.blocks` / `relations`
并保留稳定 id 与跨 batch 关系。交互顺序固定：

1. 还有 pending chunk：继续下一并发 wave，不展示图或提问。
2. 所有 batch 完成但有 `open_questions`：只展示去重后的问题；把用户答案写回相关 plan，设置
   `resolved=true`、非空 `resolution` 和最终 coverage 决策后重新 merge。
3. 所有 batch 完成且问题为 0：合并器才写出 `sop_mapping.mmd`，直接展示这一张整体大图并请求最终确认。

全局 Mermaid 是唯一结构确认门：每个流程块必须显示节点类别，跨 batch 边必须显示业务条件。用户确认后，
把各块确认类别写入 `selected_nodes`；不再改用节点映射表，也不为 display/audit warning 额外提问。随后才用
analyzer 检查 coverage 和计划结构：

若本次任务还要求创建目标草稿，最终全局图确认中同时写清目标环境、agent 名称和“仅保存草稿、不发布”；
上下文无法确定这些信息时，把它们并入前面的合并 `open_questions`，不要在进入 CHAT_FLOW 阶段后再增加一轮
确认。若用户只要求迁移方案，则最终确认后只保留 plan/source 产物，不写入环境。

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py validate-migration-plan \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json \
  --pretty
```

未通过时只补旧图 evidence、coverage 或迁移决策；不要直接改写目标图来掩盖缺口。

## Step 3：切换到 CHAT_FLOW 实现

全局 SOP → 节点映射 Mermaid 确认后，开始实现目标图前必须依次读取：

1. `../../chatflow/overview.md`
2. `../../chatflow/workflow.md`
3. `../../chatflow/graph-spec.md`
4. `../../chatflow/node-selection.md`
5. 每个候选类别实际选中的 `../../chatflow/nodes/*.md`

目标图阶段才确定 source 字段、资源绑定、边、编译、校验和部署。按
`coverage.prompt_reviews[].discovered_blocks[].target_type` 消费每一条 PE 可执行语义：选择
`AGENT_LIBRARY_BLOCK` 时使用合并器派生的标准 `library_block`；固定话术按 `NODE_PROMPT_FIELD` 的
`render_path` 写入已选节点的实际 PE/文本字段并保留完整 `content`，不预设节点类别；等待点使用明确
`rendered_instruction`；选择独立节点时按对应节点文档实现。保留每个确认 SOP 流程块的稳定 id、块内语义和
块间关系，交由 CHAT_FLOW 工作流逐块实现并形成最终图；不要在本 plan 中填写目标实现细节。
若最终 source 节点 key 与 `mapped_to` 的流程块 id 不同，在对应 coverage 项补 `rendered_to: [<source key>]`。
一个 coverage 项同时映射多个流程块和多个 source 节点时，不能靠两个数组的位置或笛卡尔积猜对应关系；必须在
每个 `sop_mapping.blocks[]` 中显式填写 `source_nodes`。
写完 source 后、compile 前先执行迁移专用对账：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py audit-migration-source \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json \
  --source-file /workspace/state/agent-builder/chatflow/<task>_source.json \
  --out-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/source_audit.json \
  --pretty

npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py validate-prompt-block-rendering \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json \
  --source-file /workspace/state/agent-builder/chatflow/<task>_source.json \
  --pretty
```

`audit-migration-source` 把损坏的 source 结构、重复 key、真实不存在的边端点，以及显式 `rendered_to` /
`source_nodes` 指向不存在节点列为 blocking error；AGENT 是否应换成专用节点、泛化 next step、单 next step、
SOP 类别差异、只有 `mapped_to` 的 coverage 去向疑点和关系不可达输出 warning，要求协调器展示并核对，但
不阻断 compile。不要为了消灭 warning 强行改节点；结合业务语义处理。
`validate-prompt-block-rendering` 按 target type 检查具体 LibraryBlock、模板/工具 ID、完整固定话术和等待承载节点；通过后仍须按
CHAT_FLOW 文档 compile / validate，以检查 `displayPrompt`、runtime `prompt`、插件绑定和在线模板状态。

同一轮由同一执行者紧邻完成 source → compile 时，不要求 handoff。只有任务需要跨轮恢复、多 worker / agent
交接，或 source 可能被人工编辑时，才建议记录交接快照：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py emit-handoff \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json \
  --source-file /workspace/state/agent-builder/chatflow/<task>_source.json \
  --out-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_handoff.json \
  --pretty
```

`emit-handoff` 记录 index、plan、source 的规范化 JSON hash 和当时已有的 validation / warning。它始终产出
快照，不新增阻断，也不会把 warning 提升为 error；`validation_passed` 只描述记录时的校验状态。

发生上述交接时，由接手方在 CHAT_FLOW `compile` 前显式验证 handoff：

```bash
npx --yes @shulex/cxclawctl@latest script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py verify-handoff \
  --handoff-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_handoff.json \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --index-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.full.json \
  --source-file /workspace/state/agent-builder/chatflow/<task>_source.json \
  --pretty
```

文件未变化即验证通过，即使快照记录了既有 validation finding；任一内容变化才返回
`STALE_MIGRATION_PLAN` 并列出变化的 artifact。此时重新检查变化、按需执行 audit / prompt rendering 并生成
新 handoff。handoff 完全属于 MULTI_AGENT 迁移侧，通用 `chatflow_builder.py compile` 不读取 migration
plan，也不承担 legacy 规则。
按已确认的全局 plan 分片实现，避免重新把完整旧图或完整目标图塞回同一个 agent run。若目标图阶段发现
缺少业务信息，回到本文件补充 evidence、coverage 或用户确认；不要自行猜测。

## 迁移验收与回放

迁移报告必须直接贴在对话中，至少包含：

- 入口、阶段、分支、用户轮次、人工接管和终端的旧图理解；
- 已确认的全局 SOP → 节点映射 Mermaid；
- old agents、tools、explicit edges、action edges 的 coverage 数量和明细；
- semantic prompt reviews / discovered blocks 的总数，以及模板、转人工、普通工具、固定话术、等待点分别映射到 AGENT LibraryBlock
  还是独立节点；
- 合并、拆分、改写、用户确认删减的原因和影响；
- 已解决和仍阻塞的 open questions；
- 从 CHAT_FLOW 阶段返回的实现、校验和发布状态（若已执行）。

编译通过只说明目标图结构可用，不等于迁移语义一致。若任务会替换生产流程，至少保留一个 synthetic smoke case；若有历史会话来源，再保留一个真实 transcript case。回放报告要比较：

- 最终回复或用户可见结果；
- 人工接管、结束和关键业务决策是否变化；
- 工具/分支语义是否仍覆盖；
- 是否残留旧编辑器占位符、HTML 噪音或不可调用的旧工具指令。

无法取得真实会话、登录态或目标运行结果时，明确写出缺口；不要把未回放说成已通过。

## 自检清单

- 同一 wave 的 worker 可并发，但每个 worker 只处理一个有预算、可恢复的 batch；
- worker 只写独立 plan，没有修改共享 progress、询问用户或生成局部 Mermaid；
- SCC 未被拆开，恢复时未新开重复 batch；
- 模型没有读取完整 raw JSON，也没有逐 chunk 发命令；
- 每个非空 PE 都按完整文本和 hash 审阅，`prompt_evidence` 截断没有影响 `prompt_reviews`；
- worker 基于流程语义输出 `discovered_blocks` / `control_semantics`，没有用话术短语或正则案例分类；
- LibraryBlock、plugin 绑定和固定话术 hash 由合并器从结构化语义动态派生；
- 所有旧图资源、动作、分支和终端都有证据及 coverage；
- display-only 引用没有制造无意义的 open question；
- 只有启用/未知启用且目录为空的知识能力才阻塞；
- 每个合并都有输入、用户轮次、资源、分支和下游语义一致的证据；
- 每个 SOP 流程块均出现在唯一的全局映射 Mermaid，且用户已确认全局图；
- 迁移计划只包含候选/确认的节点类别，不包含目标字段、默认边或目标图命令；
- 写目标图前已切换并遵守相应的 CHAT_FLOW 文档。
