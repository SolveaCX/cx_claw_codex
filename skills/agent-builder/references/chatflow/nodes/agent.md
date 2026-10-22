# AGENT

## 功能概述

让 LLM 承担一个局部、开放式的问题处理职责：在多轮上下文中综合判断、自主选择已绑定工具、解释
非结构化结果，并在当前职责确实结束后决定是否把流程交给另一个明确的下游职责。

AGENT 是运行时 LLM 节点，不是通用流程容器，也不是给每个简单任务套一层 prompt 后再用
`next_steps` 跳转的流程节点。适合 AGENT 的职责通常至少满足一项：

- 需要多轮对话才能诊断、澄清或收敛结果，当前节点会直接回复并继续等待用户；
- 是否调用某个工具、调用顺序或调用时机必须由模型结合自然语言上下文决定；
- 工具、知识或用户输入是非结构化的，需要模型解释后继续处理；
- 当前职责有一个或多个真正不同的后续业务动作，且必须由模型根据不断变化的上下文决定是否以及何时交接。

以下职责已有专用节点，不使用 AGENT：

- 只把自然语言分到有限类别：`INTENT`；
- 流程必须取得客户字段、附件、选择或确认后才能继续：`QUESTION`；
- 只发送模板、固定话术或生成一段对客回复：`REPLY`；
- 调用一个确定工具并按状态/字段分支：`TOOL` 加 actionStatus 出边或 `IF_ELSE`；
- 对结构化值做条件判断：`IF_ELSE`；生成内部文本：`LLM`；知识检索并回答：`RAG_REPLY`；
- 确定结束或转人工：`FINISH` / `TRANSFER_TO_HUMAN`。

选择 AGENT 时必须写出“为什么不能由上述专用节点表达”。仅因为旧图中的节点类型是 Agent、旧 PE
很长、当前步骤需要 LLM，或步骤完成后还有下游，都不能证明应创建 AGENT。

## 创建方式

```json
{
  "key": "troubleshoot_device",
  "type": "agent",
  "prompt": "Diagnose the device issue over multiple turns, use the bound diagnostic tool when needed, and hand off only after troubleshooting reaches an explicit outcome.",
  "plugins": [12345],
  "ai_field_ids": [2744],
  "enable_knowledge_base": true,
  "knowledge_directory_ids": [32951],
  "knowledge_keyword_ids": [11, 13],
  "knowledge_keyword_selector": ["SYSTEM", "Custom", 301],
  "next_steps": [
    {
      "id": "START_REPLACEMENT",
      "title": "start_replacement",
      "prompt": "Use only after troubleshooting is exhausted, replacement is eligible, and the customer has chosen replacement so the downstream flow must collect replacement details."
    },
    {
      "id": "FINISH_RESOLVED",
      "title": "finish_resolved",
      "prompt": "Use only after the customer confirms that the issue is resolved and the downstream node only needs to close the flow.",
      "params": [
        {"name": "resolution", "type": "string", "describe": "Short description of the confirmed resolution", "required": false}
      ]
    }
  ]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| prompt | source 阶段唯一需要 AI 编写的提示词；builder 会写入完整 graph 的 `displayPrompt`，并派生运行时 `prompt` |
| plugins / usedPlugins | 可调用工具 id 数组，例如 `[12345]` |
| ai_field_ids | prompt 可用的变量系统字段 id 数组；完整 graph 字段为 `aiFieldIds` |
| enable_kb / kb_dirs | 是否启用知识库和目录 |
| knowledge_keyword_ids | knowledgeKeywordIds；固定隔离关键词 ID 数组 |
| knowledge_keyword_selector | knowledgeKeywordSelector；变量选择器，运行时值为隔离关键词名称或名称数组；按变量实际来源选择 `SYSTEM` / `TOOL` / `EXTRACT` / `CODE` / `LLM` / `AGENT` / `HUMAN_REVIEW` |
| max_rounds | 最大轮数，默认 10 |
| max_rounds_exceeded_action | `TRANSFER_TO_HUMAN`（默认）或 `FORCE_NEXT_STEP`；后者仅在存在可用的流程内分支工具时有意义 |
| use_long_memory | 是否把长记忆注入模型上下文，默认 false |
| disable_prev_node_results | 是否不注入前序节点结果，默认 false |
| next_steps | 仅在 AGENT 需要由模型决定是否/何时交接给明确下游职责时配置；只生成内部流转工具，不是业务工具或转人工工具；source JSON 必须写对象数组，不使用字符串简写 |
| next_steps[].id | 必填，出边 handle，edges 的 `on` 使用该值 |
| next_steps[].title | 必填，分支名；推荐使用小写字母、数字和下划线，例如 `accept_wait` |
| next_steps[].prompt | 必填，内部流转工具描述，用来告诉 LLM 何时选择该分支 |
| next_steps[].params | 可选，流转时让 LLM 补充的参数，支持 string / number / boolean |
| next_steps[].params[].name | 有 params 时必填；同一 AGENT 内必须唯一，格式 `/^(?!\d)[A-Za-z0-9_-]{1,64}$/` |
| next_steps[].params[].type | 有 params 时必填；string / number / boolean |
| next_steps[].params[].describe | 有 params 时必填；说明该参数业务含义 |
| next_steps[].params[].required | 可选，默认 false；控制 LLM 调用内部流转工具时该参数是否必填 |

## Prompt Contract

AGENT 的提示词必须写成可执行指令，不写成普通客服话术。默认使用固定结构：

```text
# Role
<当前节点的业务角色，只描述这个节点负责什么>

# Task
<本节点要完成的判断、工具调用、信息解释或多轮对话任务>

# Constraints
- <必须遵守的业务边界>
- <不能做的动作，例如不要直接退款、不要承诺未确认事项>

# Tools And Routing
- <何时调用哪个真实工具；工具必须已绑定在 plugins 中>
- <何时调用 transfer_to_<step>_node 进入 next_steps 分支>
- <何时调用真实转人工工具；不要把转人工写成 next_steps 分支>
```
## 变量引用优先级

用户说“引用某变量/某内容”时，先确认它是否其实是上游工具的出参字段：

1. 读取工具定义和实际返回 schema，确认 `TOOL` selector 的完整 path；
2. 若不是工具出参，再查 `list-ai-fields`，选择已有 `SYSTEM` 变量字段；
3. 若仍不存在，再用 `VARIABLE_PROCESS` 抽取/赋值到 SYSTEM；
4. AGENT/REPLY prompt 内部变量引用时需说清楚来源(system、tool、node..)。

如果节点不需要工具或下游选择，省略 `# Tools And Routing`。如果只有固定回复、模板、转人工、
finish、字段判断或工具 status 路由，不要创建 AGENT；改用 REPLY、TRANSFER_TO_HUMAN、IF_ELSE、
TOOL、INTENT 或 QUESTION。

### next_steps And Transfer Tools

`next_steps` 只表达 AGENT 可以选择的**流程内职责交接**。运行时会把每个 next step 生成为
`transfer_to_<step>_node` 内部流转工具；语义是“结束当前 AGENT，并让另一个节点开始执行一个明确的
后续业务动作”。它不是任务清单、执行顺序或通用的“完成后下一步”，不能因为当前简单任务后面还有节点，
就为 AGENT 创建 `success`、`done`、`continue`、`next` 一类 next step。

创建每个 `next_steps[]` 前必须同时满足：

1. 当前职责本身符合 AGENT 的准入条件，而不是可由 INTENT、QUESTION、REPLY、TOOL、IF_ELSE 或 LLM 表达；
2. AGENT 在当前节点内可能经历多轮回复或自主工具调用，交接时机需要由模型判断；
3. 选择该 step 后确实有另一个节点要执行独立动作，例如开始收集 replacement 信息、进入退款处理子流程或结束已解决会话；
4. step 的选择条件来自非结构化上下文；若由工具 status、布尔值、枚举或固定顺序唯一决定，应在图上结构化路由。

若 AGENT 合理存在，但完成后永远进入同一个确定下游，使用一个 `SOURCE` 出边，不创建单个 next step。
若 AGENT 不满足准入条件，先替换成专用节点，再使用该节点自己的出边语义。

常见拆分如下：

| 业务需求 | 正确表达 | 不要这样建 |
|---|---|---|
| 判断客户消息属于退款、换货还是其他 | `INTENT -> 各意图下游` | `AGENT + refund/replacement/other next_steps` |
| 必须取得订单号后继续 | `QUESTION(VARIABLE) -> SOURCE` | `AGENT 询问订单号 + got_order next_step` |
| 发送政策说明后进入确定下游 | `REPLY -> SOURCE` | `AGENT 发送话术 + continue next_step` |
| 调工具后按明确状态分支 | `TOOL -> actionStatus` 或 `TOOL -> IF_ELSE` | `AGENT 调工具 + success/fail next_steps` |
| 多轮排障后，由模型确认应开始 replacement | `AGENT -> start_replacement next_step` | 把排障中的每个小步骤都拆成 next step |

真正的转人工是 AGENT 可调用的 `TRANSFER_TO_HUMAN` 系统动作。需要模型结合上下文决定是否升级时，
在 `displayPrompt` 中插入 `transferHuman` LibraryBlock；该块会转换成运行时转人工指令，联网 compile
再从 Chatflow 专用插件目录按 `type=TRANSFER_TO_HUMAN` 找到当前项目的真实 ID 并放入 `usedPlugins`。
`transferToHumans` 仍保持空数组。模型执行后，AGENT 节点结束并输出 `TRANSFER` / handoff
状态，不再按 `next_steps` 选择下游节点。达到 `max_rounds` 后仍未完成时，AGENT 也会按超轮兜底转人工
结束，不会自动选择某个 next step。

因此有三种出口，必须分清：

| 出口 | 配置位置 | 运行语义 |
|---|---|---|
| 流程内分支 | `next_steps` + 对应边 | 生成 `transfer_to_<step>_node` 内部工具，进入下游节点 |
| AGENT 自主转人工 | `displayPrompt` 中的 `transferHuman` LibraryBlock + `usedPlugins` 中真实 `TRANSFER_TO_HUMAN` 插件 ID | AGENT 输出 transfer / handoff，流程结束到人工 |
| 确定性转人工 | 独立 `TRANSFER_TO_HUMAN` 节点或 `$transfer` | 上游结构化分支直接转人工 |

只有“模型完成当前开放式职责后，需要触发某个明确的后续业务动作，且交接条件必须由模型判断”才放进 `next_steps`。
如果分支结果是转人工，优先让 AGENT
调用真实转人工工具；如果转人工条件是确定性的，直接在画布上接 `TRANSFER_TO_HUMAN` 或 `$transfer`。
判断标准不是名字里有没有 `transfer`：`transfer_to_<step>_node` 是 nextStep 内部跳转工具；
`TRANSFER_TO_HUMAN` 才是人工接管工具。

AGENT 提示词里不能只写“根据上下文处理问题”“你是客服”这类泛化指令。每个 AGENT 都必须说明：
输入来源、可调用工具、何时回复用户、何时等待用户、何时选择哪个 `next_steps`。选择 AGENT
时要说明为什么该职责不能被结构化节点替代。

### Prompt / displayPrompt

source JSON 阶段只维护一个 `prompt` 字段，减少上下文和双写错误。builder 编译完整 graph 时会保留两个字段：

- `agentData.displayPrompt`：等于 source `prompt`，给前端编辑器和客户审阅使用，可包含 `LibraryBlock` chip。
- `agentData.prompt`：由 `displayPrompt` 转换得到，给 chatflow 运行时模型使用；后端 AGENT 执行只读取这个字段，不把 `displayPrompt` 额外注入模型上下文。

模型基于节点职责决定是否引用某个变量或工具；不要为了“看起来完整”强行插入或绑定。只有模型决定提示词正文
需要展示该变量或工具引用时，才在 source `prompt` 中使用前端可识别的 `LibraryBlock`；前端会把它渲染成变量块 / 工具块，
而不是普通文本。变量作为运行时上下文注入但提示词正文不需要出现引用时，
可以只通过 `ai_field_ids` / `aiFieldIds` 表现为提示词下方的变量绑定区，例如 `Platform ×`。

维护已有 AGENT 的提示词时，优先从 inspect 得到的 `displayPrompt` 确认当前客户可见文本；在用户确认修改前，按
整体输出规则展示受影响片段的 `diff`，清楚对比原指令与拟更新内容。

### 可执行 LibraryBlock

模型需要结合上下文决定是否执行模板、转人工或普通工具，且该职责需要留在多轮 AGENT 内时，必须在
source `prompt` 中插入以下块，不能只写“调用 xxx”的普通文字。

变量块：

```text
{#LibraryBlock id=127609 type=variable name="c_order_number" #}
```

模板回复块；`id` 是具体模板内容 ID，不是 `TEMPLATE_REPLY` 系统插件 ID：

```text
{#LibraryBlock id=1769 type=tool name=template_reply tool=template_reply #}
```

普通业务工具块：

```text
{#LibraryBlock id=31893 type=tool name=Logistics_Anomaly_Register tool=Logistics_Anomaly_Register #}
```

转人工块；`name` 必须是业务要求的精确 reason，`tool_id` 是当前块的唯一数字实例 ID，不是插件 ID。
同一 AGENT 内每个转人工块都必须不同，不要复制示例 ID：

```text
{#LibraryBlock tool_id=1790057523341 type=transferHuman name="want refund" transferType=INSTRUCTION action=NOT_REPLY templateContent="" templateId= #}
```

块前后仍要写完整执行过程：触发条件、首次调用、调用后是否等待、客户下一轮接受/坚持时分别做什么，
不能只把块孤立地贴进 prompt。例如：

```text
## Refund request
If the customer requests a refund and no longer wants a replacement, first call:

{#LibraryBlock id=1769 type=tool name=template_reply tool=template_reply #}

After the template is sent, wait for the customer's next reply.

- If the customer accepts continuing with replacement, continue the replacement flow.
- If the customer still insists on a refund, use:

{#LibraryBlock tool_id=1790057523342 type=transferHuman name="want refund" transferType=INSTRUCTION action=NOT_REPLY templateContent="" templateId= #}
```

builder 会解析并严格校验这些块：

- 模板块的 `id` 保持具体模板内容 ID；联网 compile 从 `/api_v2/gpt/chatflow/queryPlugin`
  (`forAgentNode=true`) 按 `type=TEMPLATE_REPLY` 解析真实系统插件 ID，并追加到 `usedPlugins`。
- 普通工具块自动把块内工具 ID 追加到 `usedPlugins`，保留已有工具并去重。
- 转人工块的 `tool_id` 只标识 PE 块实例；联网 compile 按 `type=TRANSFER_TO_HUMAN` 解析真实插件 ID
  并追加到 `usedPlugins`，`transferToHumans` 仍为空数组。
- 编译后的 `displayPrompt` 保留 LibraryBlock；runtime `prompt` 自动转换成可执行文字，两者必须同步。
- 转人工 runtime 名称固定为 `Transfer_To_Agent`，大小写与前端 `formatChatflowAgentPrompt` 一致。
- LibraryBlock 必须保持单行；PE 的 `/\{#LibraryBlock\s+(.+?)\s*#\}/g` 不会解析跨行属性。
- 普通工具块的 `id` 必须存在于 `usedPlugins` 和当前 Chatflow 插件目录，`name` / `tool` 必须与该
  plugin 的真实名称一致。模板回复和转人工则按系统 plugin type 双向对账：有块必须有对应
  `usedPlugins`，绑定了对应系统 plugin 也必须有块，避免 PE chip 与运行时工具能力只保留一边。
- 联网 compile 新建这些系统动作时必须从 Chatflow 插件目录取得真实类型绑定，目录不可用或缺少类型都会
  失败；普通 validate / update / publish 的模板或插件元数据查询暂时不可用时只告警并跳过该项远端校验，
  查询成功后确认资源不存在、模板状态不是 `ENABLED` 或对应系统插件类型未绑定时才校验失败。
- PE 的 LibraryBlock 属性没有通用转义/解码合同。自动迁移不得把包含 `#}`、双引号、反斜杠、换行/
  控制字符，或形如 `key=` 的独立属性 token 写进 `name` / reason；这些值无法在 PE 中无损表达，必须改用
  独立节点或先调整值。普通空格、Unicode 和不构成 `#}` 的单独 `#` 可以保留。

提示词正文渲染和运行时绑定是两层，不要混为一谈：

| 层 | 字段/格式 | 作用 |
|---|---|---|
| 提示词正文渲染 | variable / tool / template_reply / transferHuman LibraryBlock | 让前端显示可执行块，并让 builder 派生 runtime prompt |
| 运行时绑定 | `ai_field_ids` / `plugins`，完整 graph 为 `aiFieldIds` / `usedPlugins` | 让 AGENT 运行时能读取变量、调用工具 |

因此，提示词正文插入变量块后仍应检查对应 `ai_field_ids`；工具和模板的 plugin 绑定由 builder 自动补齐，
validate 会再次对账。模型决定提示词正文需要显示变量/工具/模板/转人工引用时，不要只写纯文本名称；
纯文本描述不会变成可执行动作。

只有在提示词正文确实需要引用某个变量或可执行动作时，才用 `{#LibraryBlock ... #}` 表达；如果不需要
在提示词正文中引用，只做运行时上下文注入，可只保留 `ai_field_ids` 变量绑定。找不到具体模板内容 ID、
工具 ID 或转人工 reason 时，记录缺口并判断是否补绑定、改写为独立节点或提问；禁止把任何猜测或系统
插件 ID 写成模板块的 `id`。

用户明确给出必须逐字保留的固定完整话术时，没有模板 ID 也不得概括或删段。节点选择先由整体流程决定；
如果最终由 AGENT 承载，就把完整话术逐段写入 `prompt`，并明确发送后的等待/继续行为。不要因为发现固定
话术就在本节点文档中把流程强制改成 REPLY；其他承载节点按各自节点合同写入实际 PE/文本字段。

## Edges

- 无 `next_steps`：仅 `SOURCE`。
- 有 `next_steps`：每个 step id 一条边；运行时 LLM 调用对应内部流转工具后，按 step id 路由。
- `next_steps` 的边必须指向流程内节点；不要把人工接管写成某个 next step 再接转人工。
- `next_steps[].params` 会作为 AGENT 输出参数传给被选中的下游路径；下游用 `["AGENT", "<this_node_id>", "<param_name>"]` 引用。
- AGENT 没有 `next_steps` 且没有 `SOURCE` 出边时，validator 只给 warning；除非明确设计为终端对话节点，否则应连出 `SOURCE` 或配置 `next_steps`。

模型看到的分支工具名是 `transfer_to_<分支名>_node`。例如：

```text
next_steps[].title = accept_wait
模型调用的工具名 = transfer_to_accept_wait_node
```

### Runtime Workflow

1. 进入 AGENT 后，模型会收到当前会话、选中的 `ai_field_ids`、可用业务工具，以及 `next_steps` 生成的分支工具。未开启 `disable_prev_node_results` 时，还会带上前序节点结果。
2. 模型调用普通业务工具时，Chatflow 先执行工具，再回到同一个 AGENT。模型会结合工具结果继续调用其他工具、回复用户或选择下一步；普通工具执行成功不代表节点已经完成。
3. 模型直接回复文本而没有调用工具时，本轮回复发送给用户，流程停在当前 AGENT 等待下一条用户消息。用户继续回复后仍进入当前 AGENT。
4. 只有模型调用 `transfer_to_<分支名>_node`，当前 AGENT 才结束并进入对应下游节点。系统根据该 `next_steps[].id` 选择出边，不根据提示词文本猜测分支。
5. 分支工具带有 `params` 时，模型调用工具时填写的参数会随该分支输出，下游节点可通过 AGENT selector 引用。
6. 模型调用真实转人工工具时，AGENT 直接输出 transfer/handoff 并结束到人工，不走 `next_steps`。
7. `max_rounds` 统计 AGENT 回复用户并等待下一轮输入的次数，不统计节点内部连续调用普通业务工具的次数。达到上限时，默认按超轮转人工结束；只有配置 `FORCE_NEXT_STEP` 且运行时可用流程内分支工具时，模型才会被要求选择一个 next step。无 next step 时该配置会退回转人工。

只有工具结果是非结构化的、必须由模型解释，而且 AGENT 本身也符合准入条件时，才把查询工具放入
`plugins`，并按需要配置 `next_steps`。工具已有明确 actionStatus，或结果字段可确定判断时，使用独立
`TOOL` 加状态边 / `IF_ELSE`；不要为了路由方便把确定性工具调用塞进 AGENT。

## Resource Dependencies

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-plugins --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-agent-ai-fields --pretty
```

`ai_field_ids` 只能从 `list-agent-ai-fields` 选择；该命令与前端 Agent 字段范围校验一致。`list-ai-fields` 是 Chatflow 画布的 SYSTEM selector / Prompt 字段接口，不能替代 Agent 范围校验。字段服务偶发不可用时可以先不用 `ai_field_ids`，或复用已有 graph 中已确认的字段 id；不要把字段服务错误当成节点配置错误。启用知识库前需要确认目录 id。

## 限制

- 使用 version 2。
- `usedPlugins` 必须是工具 id 数组，例如 `[12345]`，不要写成 `[{"id": 12345}]`。
- `aiFieldIds` 必须是变量系统字段 id 数组，例如 `[2744]`。
- `enable_kb=true` 时通常配置 `kb_dirs`；未配置目录时没有可检索范围。固定隔离关键词使用 `knowledgeKeywordIds`，动态隔离关键词使用 `knowledgeKeywordSelector`。
- `knowledgeKeywordIds` 只能填 `kb-builder` 查询到的数字 ID；`knowledgeKeywordSelector` 的运行时值必须是关键词名称或名称数组，不要填关键词 ID。
- `knowledgeKeywordSelector` 必须引用真实存在且位于 AGENT 上游路径的变量/节点输出；模型根据关键词来源自动选择 selector 类型。
- `knowledgeKeywordIds` 与 `knowledgeKeywordSelector` 默认互斥；后端合并语义未明确时不要同时配置。
- 完整 graph 中 `prompt` 和 `displayPrompt` 都必须非空；source 阶段只写一个 `prompt`，由 builder 派生完整 graph 的两个字段。
- 需要上游节点输出稳定进入 prompt 时，先用 VARIABLE_PROCESS 赋值到 SYSTEM 变量系统字段，再在 `ai_field_ids` 引用该字段。
- 后端会把 `ai_field_ids` 对应字段作为额外系统上下文注入；上游节点结果也可能作为历史节点结果注入，但不要把它当成稳定 prompt 变量。
- `transferToHumans` 必须为空数组；不要用它配置 AGENT 节点。需要模型结合上下文决定升级时，在
  `displayPrompt` 使用标准 `transferHuman` LibraryBlock，并让联网 compiler 按类型把隐藏的
  `TRANSFER_TO_HUMAN` 系统插件真实 ID 绑定到 `usedPlugins`；不要手写或复用旧 Multi-Agent 插件 ID。
  确定性转人工仍使用独立 `TRANSFER_TO_HUMAN` 节点或 `$transfer`。
- 不要把多个业务阶段机械映射成多个 AGENT 后再用边串联；每个 AGENT 都必须有不可结构化替代的理由。
- 迁移或重建时，来源流程中的一个 Agent 节点、一条节点连接或一句“切换到其他 Agent”指令，都不能直接映射为目标 AGENT 或 `next_steps`；必须按目标职责重新通过准入检查。
- 如果真实外部工具的执行结果有明确 actionStatus 分支，优先拆成独立 TOOL 节点；只有需要 LLM 自主选择是否调用工具时，才放入 `plugins`。
- 如果 AGENT 后面只是固定流转、模板回复、finish 或转人工，改用结构化节点；不要把这些动作写进 prompt 让模型执行。
- AGENT 经准入后若确需模型选择多个流程内下游，必须用 `next_steps`，不能多条 `SOURCE` 出边。
- `next_steps` 只表示流程内下游；转人工不要作为 `next_steps` 项。
- 每个 `next_steps[]` 都必须有非空 `id`、`title`、`prompt`，并且必须连出对应边。
- `next_steps[].title` 推荐使用小写下划线格式，例如 `accept_wait`；提示词引用该分支时写完整工具名 `transfer_to_<title>_node`。历史流程中已有其他命名格式时，只要前端必填项和分支连线校验通过，也可以保留。
- `next_steps[].prompt` 应描述选择该分支的业务条件，不要只重复 `title`。
- 有 `params` 时，每个参数都必须写清楚 `name`、`type`、`describe`。
- `params[].name` 是下游变量 selector 的第三段，必须稳定且唯一。

## Common Mistakes

- prompt 里写“调用某工具”，但 `plugins` 没有真实工具 id。
- 手写或复用旧 Multi-Agent 的 hidden/system 插件 ID；目标 Chatflow 的 `TEMPLATE_REPLY` /
  `TRANSFER_TO_HUMAN` ID 必须由联网 compiler 通过插件类型解析后写入 `usedPlugins`。
- 用 AGENT 承载本可由 TOOL actionStatus、IF_ELSE、QUESTION、REPLY 或 TRANSFER_TO_HUMAN 表达的确定性流程。
- 为了复刻已有节点数量，把多个业务阶段一对一迁成 AGENT。
- 给 AGENT 一个简单的一次性任务，再创建 `success` / `done` / `continue` next step 跳到下一节点。
- 想在 prompt 稳定使用上游输出，却没有先赋值到变量系统字段。
- `usedPlugins` 写成对象数组，导致前端调用工具显示 `[object Object]`。
- 把模板回复、转人工、业务工具只写成普通 prompt 文字，没有插入标准 LibraryBlock；或把本可确定执行的动作藏在 AGENT，而不拆成结构化节点。
- 把转人工配置成 `next_steps` 分支，例如 `need_human` 后再接 `$transfer`。
- 已确认需要由 AGENT 选择多个职责交接分支，却没有配置 `next_steps`。
- `next_steps` 用字符串简写，导致没有 `prompt`，前端发布校验会失败。
- 下游引用了未定义的 `next_steps[].params[].name`。
