# MULTI_AGENT Migration Principles

本文件只定义 legacy MULTI_AGENT 迁移时的保真原则：旧图证据、coverage、业务职责和目标节点类别候选。旧图字段和清洗规则看 `../graph-spec.md`；具体分批流程按 `small.md` 或 `large.md`。完成迁移 plan 后，必须切到 `../../chatflow/overview.md`、`graph-spec.md`、`node-selection.md` 和已选节点的 `nodes/*.md` 写目标 source；不要在本文件推断目标节点字段、默认边或执行命令。

## 目标

迁移目标不是逐字复刻旧 PE，也不是按旧 `agents[]` 数量一比一生成节点。目标是把旧图的可执行语义迁成更清晰、可校验、可维护的 CHAT_FLOW。

## 结构化语义不可降级

迁移前必须从 legacy index 建立 `migration_contracts`：classifier、template、interaction、branch 等结构化
合同，以及每个非空 PE 的完整 `prompt_reviews` 合同。它们是 source 的输入约束，不是迁移报告的可选说明。
脚本只确定性读取图字段、资源和完整 PE，不用自然语言短语或正则猜测 PE 中的动作类别。

- legacy `TEMPLATE_REPLY` 或用户输入模板必须保留模板合同。先查现有模板；找不到时询问是否提供/新建等价模板，或由用户确认采用等价回复策略；在 coverage 记录该确认，不要自行改写为普通文案。
- legacy classifier 的已配置 category 是闭集：不得新增、删除或重命名。分类 action 的 `matchStatus` 不是可自由补写的新意图；名称/描述缺失时才补齐描述，并保留原 category id/name。
- 一个 action group 的动作顺序是合同。包含模板/用户等待后再 SWITCH、TRANSFER 或 FINISH 时，必须保持先后关系，不能只迁移最终动作。
- 工具 status、地区/渠道/商品等条件分支、以及用户确认/选择都是保护分支。没有完整 merge contract 时不得汇入泛化 AGENT 或共享后续节点。

## 对话展示合同（强制）

state 文件用于跨轮继续、并发 worker 交换和审计，不得要求用户下载文件才能完成确认。交互频率由迁移模式决定：

- small 模式按 `small.md` 展示旧图理解和映射草稿；
- large 模式的 batch context、局部计划、coverage 和局部图全部是内部产物，不逐 batch 展示或确认；只在
  所有 worker 合并后集中提出去重的 blocking `open_questions`，问题解决后再展示唯一的全局
  `sop_mapping` Mermaid 供最终结构确认；
- 最终迁移报告和确认用的全局 Mermaid 必须直接出现在对话中，不能只返回文件路径；除非用户明确要求
  下载或留档，不复制到 `/workspace/outputs/`。

`sop_mapping` 草稿可标 `candidate_nodes`；用户确认最终全局图后填入 `selected_nodes`。每个块必须显示责任
和节点类别，每条关系显示条件或下一步语义。coverage 明细只在用户要求或发现缺口时展示。

用 analyzer 生成映射图：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder migration emit-mapping-mermaid \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --out-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/sop_mapping.mmd
```

### Prompt 引用审计

迁移阶段先审计旧 PE / prompt 的业务语义和可执行引用，不直接写目标 PE。每个非空 PE 必须以完整文本和
SHA-256 进入 `migration_contracts.prompt_reviews`；`prompt_evidence` 只是可截断摘要，不能替代完整审阅输入。
语义 worker 结合 PE 全文、结构化资源、动作边和上下游流程理解每个动作，记录它的来源位置、业务职责、
绑定证据、执行顺序及缺失依赖。

- `displayPrompt` 中仅用于渲染的 chip、HTML 壳和泛化工具措辞保留 audit warning，不逐条询问。
- worker 语义上确认存在可执行调用，但无法确定具体模板、工具或转人工原因时，才进入 `open_questions`；
  analyzer 不根据 `call/use/reason/following template` 等字面写法自行下结论。
- analyzer 仅把 PE 已渲染出的无歧义 runtime 语法（带具体 ID 的 `template_reply tool`、带明确
  reason 的 `Transfer_To_Agent`、以及与源 Agent 已绑定工具同名的 `<tool_name> tool`）写入
  `protected_refs`。这些引用不是语义分类结果，只是防止 worker 漏掉或改写已经确定的执行绑定；对应
  `discovered_blocks` 必须保持相同 source span、类型和 ID/name/reason，除非记录了显式 resolved drop。
- worker 必须把模板、人工接管、普通工具、固定完整话术和等待点按源顺序写入
  `coverage.prompt_reviews[].discovered_blocks`；流程内跳转、finish 和工具状态分支写入
  `control_semantics`，不得误标成人工接管。固定话术、等待点及其他自然语言动作仍必须由 worker 阅读
  全文和流程上下文判断，`protected_refs` 不能替代这部分审阅。

### Prompt semantic review 合同（强制）

analyzer 的每个 `migration_contracts.prompt_reviews[]` 至少输出：

- `contract_id`、`agent_id`、完整 `prompt`、`prompt_sha256`、`prompt_char_count` 和
  `review_mode=full_semantic_review`；存在无歧义 runtime 工具语法时还包含带稳定 ID、精确
  `source_span` / `source_quote` 和绑定字段的 `protected_refs`；
- batch coverage 必须回写相同 `source_prompt_sha256`、`reviewed_full_prompt=true`、`decision`、
  `mapped_to`、`reason`、`discovered_blocks` 和 `control_semantics`；
- 每个 `discovered_blocks[]` 必须有稳定 `block_id`、`kind`、源顺序 `sequence`、精确 `source_span` /
  `source_quote`、`decision`、`target_type`、`mapped_to`、`reason`；
- 模板语义输出具体整数 `template_id`；合并器动态派生标准 Template LibraryBlock、
  `required_used_plugins=[]` 和 `required_plugin_types=["TEMPLATE_REPLY"]`；实际插件 ID 由目标项目的
  Chatflow 专用插件目录在联网 compile 时解析；
- 转人工语义输出原文精确 `transfer_reason`；合并器动态派生标准 transferHuman LibraryBlock、
  唯一稳定的块实例 `tool_id`、`required_used_plugins=[]`、
  `required_plugin_types=["TRANSFER_TO_HUMAN"]` 和 `transfer_to_humans=[]`；块实例 ID 不是插件 ID，
  实际插件 ID 同样由目标 Chatflow 项目按类型解析；
- 普通工具语义输出已绑定的整数 `tool_id` / `tool_name`；合并器动态派生 Tool LibraryBlock 和对应
  plugin id。无法确定绑定时输出 `decision=open_question`，禁止猜 id；
- 固定话术使用 `kind=FIXED_WORDING` 并输出完整 `content`；合并器派生 `content_sha256` 和
  `must_preserve_verbatim=true`。它的目标统一是 `NODE_PROMPT_FIELD`，batch worker 只映射到业务流程块，
  不预设为 REPLY；全局节点类别确认后，协调器按所选节点合同填写真实 `render_path`。承载者可以是 AGENT，
  也可以是其他按其节点合同使用 PE/文本指令的节点；内容不能截断或概括；
- 等待点输出 `WAIT_FOR_USER`。若由 AGENT 承载，还要提供将写入目标 prompt 的明确
  `rendered_instruction`，不能只靠隐含语气表示等待；
- `target_options`、`library_block`、`required_plugin_types`、内容哈希等协议字段全部由合并器根据结构化 `kind` 派生，
  worker 不手写协议字符串，也不按话术案例拼接块。

`target_type` 必须来自合并器派生的 `target_options`。没有具体模板 ID、工具 ID、转人工 reason，固定话术
不完整，或全文 hash / source span 对不上时不得进入 source 生成；只有用户明确解决并记录 resolution 的删减
可以不映射。

### 先还原流程，再设计节点（强制）

`agents[]` 是 legacy 引擎的运行单元，不是 CHAT_FLOW 的节点清单。先用入口、显式边、
工具状态、隐式 action 和终端动作还原流程图，再按“职责 + 分支 + 数据依赖”设计目标图。
目标节点数不以 old agents 数量为上限或下限：一个 old agent 内嵌的工具、分类、状态分支、模板回复、
等待点和终端动作在 CHAT_FLOW 中可能展开成多个可观察节点，因此目标图完全可能远多于 old agents。
节点数量只能由完整可执行合同决定，不能把“图更短”本身当成迁移目标。

禁止把每个 old agent 机械复制成一个 `AGENT`。连续的纯判断/话术 agent 应先判断能否合并为一个
职责单元；真实工具、action status、用户输入、固定模板、知识回答、转人工和结束按各自业务合同
选择候选节点类别。只有职责不可合并时才保留独立 `AGENT`。
若仍把每个 old agent 一一保留为一个 `AGENT`，必须在 `changed_items` 中给出每个节点的独立结构证据；不能只凭 agent name、
prompt 长度或旧图数量作理由。

### 流程图保真门（先骨架，后合并）

生成 source 前必须先输出 `flow_skeleton`，至少包含：入口、主干阶段、每个工具的 status
分支、每个 classifier 的完整分支集合、用户交互点、模板回复、转人工/结束终端，以及各分支
最终汇合点。Mermaid 和 source 的节点可以多于或少于 old agents，但不能少掉这些**分支签名**。

进入 source 阶段前，migration plan 必须有已确认的 `sop_mapping`。它按业务流程块而非 old agent 记录职责、
候选/确认的节点类别及块间关系：

```json
{
  "sop_mapping": {
    "blocks": [
      {
        "id": "collect_order",
        "responsibility": "收集订单信息",
        "candidate_nodes": ["QUESTION"],
        "selected_nodes": ["QUESTION"]
      }
    ],
    "relations": [
      {"from": "collect_order", "to": "lookup_order", "condition": "信息齐全"}
    ]
  }
}
```

`id` 在同一计划中必须唯一，关系只能连接已声明的块。进入 source 阶段前每个块都必须有
`selected_nodes`；节点字段、资源和出边实现仍在目标图文档阶段确定。

当 `selected_nodes` 包含 `AGENT` 时，在该块增加 `selection_reason`，说明为什么它需要开放式多轮处理、
自主工具选择或非结构化结果解释，以及为什么 `INTENT`、`QUESTION`、`REPLY`、`TOOL`、`IF_ELSE`、`LLM`
不能完整表达该职责。该理由缺失只进入 source audit warning，不因文字理由不够详细而阻断构图。

source 完成后用 `audit-migration-source` 对照 plan、index 和 source。校验分级固定为：损坏 JSON/source
结构、重复节点 key、边指向真实不存在的节点，以及显式 `source_nodes` / `rendered_to` 指向不存在节点属于
error；节点类别建议、AGENT 理由、泛化/单一 next step、SOP 关系和仅有 `mapped_to` 的 coverage 去向差异
属于 warning。warning 必须展示和核对，但不自动阻断 compile，也不能为了清零 warning 把合法的模型决策
改成确定性路由。

跨轮恢复、多 worker / agent 交接或人工编辑 source 后继续迁移时，可以由迁移侧用 `emit-handoff` 记录
index、plan、source 的规范化 JSON hash，再由接手方显式运行 `verify-handoff`。同一轮、同一执行者紧邻完成
source → compile 时不要求 handoff。handoff 只记录已有校验结果，不新增门禁，也不会把任何 warning 提升为
error；只有显式验证发现内容自记录后发生变化时，才返回统一的 `STALE_MIGRATION_PLAN`。通用 CHAT_FLOW
builder 不读取这些 legacy 产物，避免把迁移协议写入通用 source schema。

迁移默认按 chunk / 阶段保留流程边界，但执行时按有预算的 batch 读取和 checkpoint。每个 chunk
必须在内部 plan 中记录输入、用户轮次、资源调用、分支集合、出参和下游目标，再决定是否合并；一个 batch
只承载拓扑相邻且不超过预算的一组 chunk。非必要不合并流程：如果只是为了让图更短、让多个
出边有同一个 target、或复用一个泛化处理节点，而没有 `merge_groups` 证明合同一致，视为迁移风险。
`merge_groups` 必须说明 same inputs、same user turn、same resources/tool contract、same branch set、
same downstream semantics；缺任一项就先拆开，后续再由用户/产品确认是否合并。

以下单元默认是保护单元，除非结构化证据完全一致，否则不能合并：

- 不同 chunk / 阶段的出参，即使目标节点名称或 prompt 相似；
- 不同 `actionStatuses` / `matchStatus`，即使目标 agent 名称相似；
- 不同业务维度下的 classifier 或路由树（例如地区、渠道、商品范围、客户类型）；
- 不同业务主线或处理结果（例如换货、退款、预约、投诉升级）；
- 不同工具、不同工具参数/结果字段、不同 `template_id` 或不同转人工 reason；
- 不同用户轮次：收集信息、确认/拒绝、补字段、成功通知不能仅凭话术相似合并。
- `matchStatus == null` 的兜底 action 不能丢；它通常表达工具/分类未命中时的默认 SOP 出口。
- 同一个 `toolAfterExecuteActions` 匹配项里同时出现模板/用户输入模板和
  `SWITCH_AGENT` / `TRANSFER_TO_HUMAN` / `FINISH_AGENT` 时，必须保留“先回复再跳转/转人工/结束”
  的组合语义，不能只迁最终动作。
- 不同转人工职责必须先拆成 `handoff_groups`；退款、物流、订单核验等不同升级原因不能默认汇聚。
  只有职责、分支原因、用户轮次和转人工前置回复合同完全一致时才允许复用。
- 不同终端动作必须先拆成 `terminal_action_groups`：模板回复、带回复 finish、带回复转人工、无回复 finish
  是不同合同。不同 template id/content、不同分支原因、不同用户轮次、不同后续终态，不能映射到同一个
  回复、人工接管或结束职责。只有完全无回复的 `FINISH_AGENT` 可以合并为同类结束职责。
- legacy classifier 已有意图 `name` / `desc` 时优先保留；缺失时才根据流程补写。补写的 `name` 必须是用户可理解的业务分类名，简短但能表达流转含义（例如 `Continue_Replacement`、`Refund_Approved`），不能使用 `order_status` 这类技术字段名；`desc` 使用简短英文句子。

允许合并的条件必须同时满足：业务职责相同、输入变量相同、用户轮次相同、结构化工具/模板
相同、下游分支集合相同。`SWITCH_AGENT` 只表达流转边，不是外部工具或目标节点；只有目标 agent 具有
独立行为或用户交互时才创建节点。

显式 `agentEdges[]` 与 action `SWITCH_AGENT` 都要进入 coverage，但语义不同：前者只是当前 agent 可调用的
相邻职责，是否调用由模型决定；后者是工具状态/分类结果命中后的确定性流转。不得把一条
`agentEdges[]` 自动编译成目标图的确定性连线、`next_steps` 或固定节点对。模型必须结合 SOP、职责、用户轮次
和结构化证据决定它是：保留为 AGENT 的模型可选路由、吸收到同一职责单元，还是在用户确认或独立
`SWITCH_AGENT` 证据存在时形成确定性流程。coverage 记录该决定和理由，不要求写成 `target_a -> target_b`。

### Legacy action 的语义映射

| legacy 控制语义 | 必须保留的业务合同 | 目标节点类别候选 |
|---|---|---|
| 显式 `agentEdges[]` | 当前 old agent 可主动切到相邻 old agent；不是外部工具调用，也不是确定性边 | 模型可选路由证据；由 SOP 决定保留、吸收或经确认后结构化 |
| action `SWITCH_AGENT` 无回复 | 命中 `matchStatus` 后确定性进入下一 SOP 职责 | 下游职责的候选节点类别 |
| action `SWITCH_AGENT` 带模板/话术 | 先发送指定话术，再进入下一 SOP 职责 | `REPLY` 加下游职责 |
| action `TEMPLATE_REPLY` | 保留模板资源和继续/结束时序 | `REPLY` |
| action `TRANSFER_TO_HUMAN` | 保留人工接管原因，以及是否先回复 | `TRANSFER_TO_HUMAN` |
| action `FINISH_AGENT` | 保留是否先回复及结束语义 | `FINISH`，必要时搭配 `REPLY` |

`toolAfterExecuteActions.matchStatus == null` 是旧运行时的兜底出口，必须保留为可达的兜底处理或明确终态；
不能当作缺失状态忽略。一个匹配项里可能包含多条 action，迁移时按动作序列保留组合语义，不要只取最后一条。

迁移计划必须增加：

```json
{
  "flow_skeleton": {"stages": [], "protected_branches": [], "merge_points": []},
  "merge_groups": [
    {
      "mapping_key": "issue_detail",
      "merged_from": ["old_a", "old_b"],
      "same_inputs": true,
      "same_user_turn": true,
      "same_resources": true,
      "same_branch_set": true,
      "same_downstream_semantics": true,
      "evidence": []
    }
  ],
  "handoff_groups": [
    {"group_key": "handoff_refund", "responsibility": "refund escalation", "mapping_key": "handoff_refund", "evidence": []}
  ],
  "terminal_action_groups": [
    {"group_key": "reply_refund_policy", "action_type": "TEMPLATE_REPLY", "mapping_key": "reply_refund_policy", "evidence": []}
  ],
  "node_decision": {"old_agent": "merge|preserve|split|edge_only", "reason": "..."}
}
```

允许变化：

- 多个只承担话术、内部跳转或轻量判断的 old agent，可合并为一个职责单元，并在 `AGENT`、`INTENT` 或 `REPLY` 等候选类别中选择。
- 只承担内部总结、改写、抽取或中间文本生成的 old agent，应与面向用户回复职责区分；候选类别通常是 `LLM`。
- 旧 PE 中的流程内跳转和 finish 指令必须从目标 prompt 中剥离，并在 `control_semantics` 对账；模板回复、
  转人工、普通工具、固定话术和等待点先由全文语义审阅写入 `discovered_blocks`，再决定是渲染成目标
  AGENT LibraryBlock、写入所选节点的实际 PE/文本字段，还是拆成独立结构化节点。渲染 chip 提取出的工具引用先进入资源对账，
  再决定保留、清理或提出 open question，不能直接丢弃。
- 旧 prompt 中重复、HTML 污染、编辑器占位符、旧工具调用话术必须清理。
- legacy 的隐式 action 分支可改写成 `TOOL`、`IF_ELSE`、`INTENT` 或 `QUESTION` 等候选职责。

不允许变化：

- 丢失任何真实外部工具调用、action status、模板回复、转人工、finish、KB 启用状态。
- 把不同模板 id、不同转人工前置话术、不同 finish 话术合并成一个无差异节点。
- 把旧 PE 里的可执行动作只保留成新 prompt 普通文字，没有 LibraryBlock 或独立节点。
- 因为新图看起来简单，就省略旧图中可执行的业务分支。
- 没有证据时凭 agent name 猜节点类型。

## Coverage 表

迁移 plan 必须包含 coverage。每个 old agent、真实 tool、explicit edge、action edge 都要有去向。
analyzer 会为它们生成稳定的 `agent_id`、`tool_key`、`edge_id`、`action_id`；coverage 必须引用这些 ID，不能只按名称或数量填写。

```json
{
  "coverage": {
    "agents": [
      {
        "old_id": "agent_lookup",
        "old_name": "lookup_order",
        "mapped_to": ["tool_lookup_order", "intent_order_issue"],
        "decision": "split",
        "reason": "HTTP 调用与状态分支拆成可观察的职责；旧 PE 工具指令删除。"
      },
      {
        "old_id": "agent_shipping_reply",
        "old_name": "shipping_information",
        "mapped_to": ["agent_after_lookup"],
        "decision": "merged",
        "reason": "只承担工具结果解释和后续选择，无独立工具/action；合并后仍保留该业务职责。"
      }
    ],
    "tools": [
      {
        "old_tool_key": "tool_abc123",
        "old_tool_id": 8299,
        "old_tool_name": "get_order_info",
        "mapped_to": "tool_lookup_order",
        "decision": "preserved",
        "reason": "The structured lookup capability is retained."
      }
    ],
    "resources": [
      {
        "resource_id": "resource_abc123",
        "mapped_to": "tool_lookup_order",
        "decision": "preserved",
        "reason": "The resource is the structured HTTP tool contract."
      }
    ],
    "actions": [
      {
        "action_id": "action_abc123",
        "from_old_agent": "agent_lookup",
        "match_status": "ORDER_NOT_FOUND",
        "action_type": "TRANSFER_TO_HUMAN",
        "mapped_to": "handoff_order_not_found",
        "decision": "preserved"
      }
    ],
    "explicit_edges": [
      {
        "edge_id": "agent_edge_abc123",
        "from_old_agent": "agent_a",
        "to_old_agent": "agent_b",
        "routing_semantics": "model_selectable",
        "mapped_to": ["agent_order_resolution"],
        "decision": "merged",
        "reason": "保留为该职责单元内由模型决定是否切换的能力，不生成确定性目标边。"
      }
    ]
  }
}
```

batch worker 必须从 `coverage_required` 逐项原样回写稳定标识：agent 用 `old_id`，tool 用
`old_tool_key`，action / explicit edge / resource 分别用 `action_id` / `edge_id` / `resource_id`，合同项用
`contract_id`。`old_tool_id` 和名称只作为证据字段；同一个真实插件可能被多个 old agent 复用，因此不得只用
`old_tool_id` 标识 coverage 项。

`decision` 只能使用：

- `preserved`：语义一比一保留。
- `merged`：语义合并进某个新节点。
- `split`：一个 old agent 拆成多个 CHAT_FLOW 节点。
- `rewritten`：旧 PE / action 被结构化改写，行为保留但表达方式变化。
- `dropped`：明确废弃，必须写原因和证据；默认不能使用。旧计划中的 `dropped_with_reason` 作为兼容别名，
  校验语义与 `dropped` 相同；新计划统一写 `dropped`。
- `open_question`：证据不足，必须问用户。

## 合并规则

可以合并：

- 只含业务说明、无真实 `usedPlugins`、无 `toolAfterExecuteActions`、无 template/transfer/finish/KB 配置的 old agent。
- 连续多个只负责 LLM 判断下一步的 old agent，且可由一个合并后的职责单元清楚表达。
- 多个完全相同的无回复结束终端。
- 多个完全相同的无回复人工接管终端。

不能合并：

- 不同真实外部工具。
- 不同 `actionStatuses` 或不同 `matchStatus` 分支。
- 不同 template id/content。
- 不同 TEMPLATE_REPLY / FINISH_AGENT with reply / TRANSFER_TO_HUMAN with reply 的终端合同。
- 不同转人工类型：直接转人工、转人工节点内模型生成话术后转人工、模板回复后转人工。
- 一个带回复的转人工和一个无回复转人工。
- KB 启用状态、目录或标签不同的知识回答。
- 用户明确希望在 CHAT_FLOW 画布上保留为独立可观察步骤的 old agent。

合并后必须在 coverage 中写出 old agent 去向。用户要求 Mermaid 时，Mermaid 展示迁移后的结构时也要标出“merged from: old_a, old_b”。

## PE / Prompt 改写

迁移后的 PE 可以变，但必须满足：

- 保留业务目标、判断标准、话术边界、工具结果解释方式。
- 删除旧引擎的普通文字工具指令：`template_reply tool`、`transfer_to_agent tool`、`finish_agent`、
  `call <agent> agent`；需留在目标 AGENT 内的模板/转人工/普通工具改为标准 LibraryBlock。
- 删除 `{{Template_Reply}}`、`{{Transfer_To_Agent}}`、`<span style=...>` 等旧编辑器展示壳；壳内的工具名先提取到 `tool_references`，再与 plugin/action 对账。
- 把真实工具调用、流程内流转、模板、转人工和结束分别记录为结构化业务职责；模板、转人工、普通工具、
  固定完整话术和等待点还必须进入完整 PE 的 `prompt_reviews.discovered_blocks` coverage。
- legacy `TRANSFER_TO_HUMAN` / `Transfer_To_Agent` 是人工接管动作，不是普通业务工具；不得与业务工具混淆。
- 具体字段、出边和资源绑定只在 CHAT_FLOW 文档阶段确定。

如果 prompt 改写导致客服话术、拒答边界、工具结果解释发生语义变化，必须列入 `changed_items`，并入最终
全局图确认；若缺少决策依据，则先作为 blocking `open_questions` 集中询问。

## 模型理解旧结构的方法

不要直接让模型读完整 old JSON 后生成 CHAT_FLOW。按证据层理解：

1. `entryAgentId` 定入口。
2. `agents[].usedPlugins` 定真实工具。
3. `usedPlugins[].meta.externalHttpCallConfig.actionStatuses` 定工具状态分支。
4. `usedPlugins[].meta.toolAfterExecuteActions` 和 `classifierPlugin.meta.toolAfterExecuteActions` 定隐式动作边。
5. `agentEdges[]` 定显式 old agent 跳转。
6. `meta.templateReplyPlugin`、`transferToHumanPlugin`、`finishAgentPlugin`、`knowledgeAiReplyPlugin` 定结构能力。
7. `prompt` 必须全文审阅以补业务语义、可执行动作和固定话术，但不能覆盖结构化证据；识别依赖上下文语义，
   不依赖固定英文短语或正则案例。
8. `displayPrompt` 默认不作为模型输入；其中的 HTML 只作为渲染壳清洗，但 `{{ToolName}}` 必须提取到 `tool_references`。找不到结构化 plugin/action 的 display-only 引用保留为 audit warning，不能静默丢弃；只有明确可执行的 prompt 调用缺少绑定时才进入 `open_questions`。

结论必须来自上述证据链。证据冲突时，以 action/tool/plugin 结构优先；prompt 冲突进入 `open_questions`。

## 结果报告

coverage 中的 `open_question` 或 `dropped` 默认都是未解决状态，会阻塞 source 生成。若经过用户/产品确认，必须显式写成：

```json
{
  "decision": "dropped",
  "resolved": true,
  "resolution": "用户确认该不可达节点不迁移",
  "mapped_to": [],
  "reason": "没有入口且无控制边"
}
```

`resolved` 只有为布尔值 `true` 且 `resolution` 非空时才生效；已解决的 `dropped` 可以没有
`mapped_to`，其他已解决的 `open_question` 仍必须给出最终映射。`dropped_with_reason` 只用于兼容旧计划，
也遵循完全相同的 `resolved` / `resolution` 规则。这样既保留不确定性审计轨迹，又不会让校验器把已确认的
删减误判成未完成。

迁移结果必须报告：

- old agents N -> 目标职责单元 N，并列出 merged/split/dropped 数量。
- 已确认 SOP → 节点类别 Mermaid，以及每个流程块的职责和条件关系。
- tools N -> preserved N / open_question N。
- action edges N -> migrated N / open_question N。
- discovered prompt blocks N -> AGENT_LIBRARY_BLOCK N / 独立节点 N / open_question N，并列出模板 ID、转人工 reason、
  普通工具 ID、固定话术和等待点的去向。
- PE cleanup：删除了哪些旧工具指令，保留了哪些业务规则。
- changed_items：PE、节点数量、节点合并、终端合并、KB 处理等行为可能变化点。
- 进入目标图阶段后的校验和 replay 状态。

对每个包含 PE 可执行块的 old agent，还必须输出一条可回读的渲染记录；没有对应类别时写 `none`，不能省略
整个检查维度：

```text
Agent: <old agent name/id>

Templates:
- <template id> -> AGENT LibraryBlock | REPLY(TEMPLATE), rendered/read back status

Transfers:
- <exact reason> -> AGENT LibraryBlock | TRANSFER_TO_HUMAN, rendered/read back status

Business tools:
- <tool id/name> -> AGENT LibraryBlock | TOOL, binding status

Fixed wording and waits:
- <contract id> -> <target node + render_path>, verbatim/hash check, wait target

Bindings:
- usedPlugins: <target Chatflow plugin ids>; TEMPLATE_REPLY / TRANSFER_TO_HUMAN are resolved by type
- transferToHumans: []

Verification:
- validate: passed | failed
- inspect readback: passed | failed
- published: no | yes
```

这份记录从最终 plan、目标 graph 和 inspect 回读生成，不由 batch worker 面向用户输出。默认只保存草稿，除非
用户明确要求发布，`published` 必须为 `no`。
