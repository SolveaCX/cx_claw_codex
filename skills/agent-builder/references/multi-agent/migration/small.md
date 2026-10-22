# 迁移模式：small legacy MULTI_AGENT -> CHAT_FLOW

输入是旧版 `multiAgentGraph`（扁平 `agents[]` + `agentEdges[]`）时使用本文件。目标不是复述旧
prompt，也不是按 old agent 数量建同样数量的节点，而是还原并保留入口、客户意图、工具、动作分支、
模板回复、人工接管、结束和内部流转等**可执行业务语义**。

开始前先读 `../graph-spec.md` 和 `principles.md`。本文件只负责短图的旧图取证、coverage、语义映射
和用户确认；它不定义目标节点字段、默认边或构图/校验命令。

短图不强制跑 analyzer，但必须产出等价的 topology 摘要：唯一入口、可达节点、显式 edge、
`SWITCH_AGENT` 控制边、动作分支和终端。如果已有 analyzer 产物，优先使用其中的 `topology` /
`flow_understanding.seed.json` / `migration_contracts`；图小不是跳过 classifier 闭集、模板资源、用户
交互和动作顺序对账的理由。

## 触发和分流

符合任一条件即进入迁移模式：

- 文本包含 `multiAgentGraph` / `agentEdges` / `classifierPlugin`；
- 用户给当前环境旧版 agent_id 并要求迁移 / 转新版 / 一键迁移；
- 顶层 JSON 形如 `[{"category":"TEXT","meta":{"multiAgentGraph":...}}]`。

否则走 `/skills/agent-builder/references/chatflow/workflow.md`；图片或流程图输入先读
`/skills/agent-builder/references/chatflow/visual-translation.md`。

符合任一条件时，停止本文件的短图流程并改读 `large.md`：

- `displayPrompt` 远大于 `prompt`，或含大量 HTML 展示内容；
- 顶层含大量前端画布、审计或非执行字段，需要裁剪；
- `usedPlugins[].meta.toolAfterExecuteActions` 或工具 `actionStatuses` 是主要流程来源；
- agent/action/tool 数量较多，需要先生成 Mermaid、chunk 和 batch；
- prompt 与 action 中的模板、目标 agent 或知识配置存在冲突。

长图先执行：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py inspect \
  --input /workspace/state/agent-builder/multi-agent/read_<old_agent_id>_raw.json \
  --out-dir /workspace/state/agent-builder/multi-agent
```

## 迁移阶段的产物

| 文件 | 用途 |
|------|------|
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/` | analyzer 索引、topology、coverage 和迁移计划 |
| `/workspace/state/agent-builder/multi-agent/mapping_rules.json` | 用户确认过、可跨任务复用的模糊映射规则 |
| `/workspace/outputs/agent-builder/` | 仅在用户明确要求下载/留档时使用 |

目标 source、graph、编译、校验和部署均由 `../../chatflow/workflow.md` 管理；不要在本文件中创建临时
Python 构图脚本或复制目标图命令。

## Step 1：解析旧图并还原拓扑

短小图可以由模型直接解析；长图必须由脚本解析。无论方式，都必须记录：

- `agents[]` 的 id、名称、prompt、`displayPrompt`、`usedPlugins` 和结构化 meta；
- `agentEdges[]` 的显式流转；
- classifier 与工具的 `toolAfterExecuteActions`、`actionStatuses`；
- 模板、人工接管、结束和知识能力配置；
- 每个非空 PE 的完整原文和 SHA-256。模型必须结合结构化资源、动作边、上下游职责阅读全文，语义识别其中的
  模板、转人工、普通工具、固定完整话术、等待点和流程控制；不得按 `template id`、`reason`、
  `use/call tool`、三引号等固定写法或语言专用正则分类。短图也要按 `principles.md` 生成等价的
  `prompt_reviews[].discovered_blocks`，不能只保留 prompt 摘要；
- 可达性、入口和缺失目标的 action。

`agentEdges[]` 只记录“上游模型可以选择调用的相邻职责”，不是确定性流程边。旧图 Mermaid 中应以虚线
标识这类关系；SOP 映射时由模型根据职责和用户轮次决定保留为模型可选路由、吸收进同一职责，或在独立
`SWITCH_AGENT` 证据/用户确认后形成确定性流程。不要把它直接抄成目标图的一条连线。

`displayPrompt` 中的 `{{ToolName}}` 必须提取为 `tool_references` 并与 `usedPlugins` / 系统能力 /
action 对账。仅 display-only 的未绑定 chip、HTML 壳和“use this tool”之类泛化措辞都保留 audit warning；
只有 prompt 中明确可执行的调用缺少结构化依赖时才进入 `open_questions`。

向用户先展示以下内容，不要一上来写目标图：

```text
## 旧 Multi 流程理解
| 阶段 | 输入/用户轮次 | 旧证据 | 分支/出口 | 风险 |

## SOP 拆解
| SOP 步骤 | 触发条件 | 处理动作 | 用户可见回复/等待 | 下游 |
```

同时贴一段简版 Mermaid，展示入口、主干、动作分支和终端。存在不可达节点、多个入口或 action 缺少目标时，
先作为 blocking 问题处理，不能靠补猜测的边继续。先让用户确认 SOP；coverage 留在 plan 中审计，只有
存在缺口或用户要求明细时才展示表格。

## Step 2：做语义映射和 coverage

按拓扑顺序映射，但先归一化业务职责，不按 `agents[]` 数量建节点。每个映射要同时考虑 old agent、
结构化 action 和 prompt，避免先丢语义再补。

迁移计划只写业务职责和目标节点类别候选；以下是常见候选，不是字段或出边规则：

| Legacy 语义 | 候选类别 |
|---|---|
| 自然语言分类 | `INTENT` |
| 已绑定的外部 HTTP 调用 | `TOOL` |
| 工具结果后的确定性判断 | `IF_ELSE` |
| 收集客户信息 | `QUESTION` |
| 向客户发送模板或话术 | `REPLY` |
| 内部总结、改写、抽取或中间文本生成 | `LLM` |
| 开放式判断、真实工具自主选择或流程内选择 | `AGENT` |
| 人工接管 | `TRANSFER_TO_HUMAN` |
| 正常结束 | `FINISH` |
| 变量抽取、归一化或上下文传递 | `VARIABLE_PROCESS` |
| 已启用且目录完整的旧知识能力 | 知识回复候选，具体类别在目标图阶段决定 |

`SWITCH_AGENT` 是旧控制流证据，不是外部工具。仅承担跳转的 old agent 标记为 `edge_only`；独立 SOP、
用户交互、资源调用或分支职责才需要保留为候选节点。每个 old agent、真实 tool、explicit edge 和
action edge 都必须在 coverage 中标记为 `preserved`、`merged`、`split`、`rewritten`、`edge_only` 或
`open_question`，并给出证据。

explicit edge 的 `mapped_to` 可以写对应职责块或模型可选路由能力；不得默认写成固定的目标节点连线。

知识能力只按旧语义判断：直接 `directoryIds` 或
`meta.knowledgeAiReplyConfig.directoryIds` 都是目录证据；后者的 `enable` 优先。明确 `enable=false`
且目录为空只保留 audit。已启用或启用状态未知且目录为空，才是 blocking 问题：要求用户提供目录或
明确移除该能力。不要把仅 display 的知识占位符当成缺失依赖。

模板、人工接管和结束动作需要分别记录资源、先后顺序和用户可见语义。不同模板 id、不同人工接管原因、
不同前置话术或不同结束语义默认不能合并；是否采用等价回复策略必须经用户确认。

每个完整 PE 都要进入 `coverage.prompt_reviews`，回写全文 hash 和 `reviewed_full_prompt=true`；语义识别出的
每个块按源顺序进入 `discovered_blocks`，带精确 source span/quote。SOP → 节点类别确认后，再为每个块选择
`target_type`：上下文决定且需留在多轮 AGENT 内的模板/工具/转人工用 `AGENT_LIBRARY_BLOCK`；确定性动作
分别选择 `REPLY_TEMPLATE` / `TOOL_NODE` / `TRANSFER_NODE`；等待点选择合同允许的多轮或交互节点承载方式。
固定话术先使用通用 `NODE_PROMPT_FIELD`，不把它写死为 REPLY；进入 CHAT_FLOW source 实现并读完所选节点
合同后，再用 `render_path` 指向该节点的真实 PE/文本字段。LibraryBlock、plugin 绑定和内容 hash 由与 large
模式相同的合并/渲染规则根据结构化语义派生，不让模型或人工逐 case 拼字符串。未映射完不得转入 CHAT_FLOW
source 阶段。

## Step 3：生成 SOP → 节点映射 Mermaid 并确认

保留旧 prompt 中的业务目标、判断标准、客服话术边界和工具结果解释；剥离旧引擎专用的工具指令、
编辑器占位符和 HTML 壳。清理不能抹掉结构化动作：每一项要么落入 mapping plan 的业务职责，
要么有 audit 或 open question 记录。

在用户确认 SOP 后，按流程块（不是按 old agent）写 `sop_mapping`。草稿先写候选类别；节点映射得到
用户确认后，将每个块的确认类别写入 `selected_nodes`：

```json
{
  "sop_mapping": {
    "blocks": [
      {
        "id": "collect_order",
        "responsibility": "Collect the order information",
        "candidate_nodes": ["QUESTION"],
        "selected_nodes": ["QUESTION"]
      },
      {
        "id": "lookup_order",
        "responsibility": "Look up the order and route by result",
        "candidate_nodes": ["TOOL", "IF_ELSE"],
        "selected_nodes": ["TOOL", "IF_ELSE"]
      }
    ],
    "relations": [
      {"from": "collect_order", "to": "lookup_order", "condition": "order information complete"}
    ]
  }
}
```

生成 Mermaid 并直接贴给用户确认：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py emit-mapping-mermaid \
  --plan-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/migration_plan.json \
  --out-file /workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/sop_mapping.mmd
```

图中每个流程块必须显示其职责和候选/确认节点类别，边必须显示条件。它取代节点映射表作为用户确认界面；
coverage 仍在 plan 中，不逐项占用对话。映射未确认时不得写 source。

只对会改变可执行语义的缺口提问：缺失真实工具/模板、启用或未知启用的空知识目录、不可达或断开的
结构边、无法恢复的关键动作合同。每个问题给出 2–3 个可执行选项、推荐项、影响和是否阻塞；不要把
audit warning 逐条抛给用户。

## Step 4：交给目标图阶段实现

coverage 完整、SOP → 节点映射 Mermaid 和必要的用户决定确认后，停止使用本文件推断实现细节，依次读取：

1. `../../chatflow/overview.md`
2. `../../chatflow/workflow.md`
3. `../../chatflow/graph-spec.md`
4. `../../chatflow/node-selection.md`
5. 每个已选类别对应的 `../../chatflow/nodes/*.md`

目标图阶段才决定 source 字段、资源绑定、边、编译、校验和部署。迁移计划是该阶段的语义输入；目标图
实现或校验发现缺少业务信息时，回到本文件补 evidence / coverage / 用户确认，而不是在目标图中猜测。
source 完成后、compile 前先运行 `legacy_graph_analyzer.py audit-migration-source --plan-file ...
--index-file ... --source-file ... --out-file ... --pretty`，再运行
`validate-prompt-block-rendering --plan-file ... --index-file ... --source-file ... --pretty`。前者会阻断损坏
source 结构、真实不存在的边端点，以及显式 `rendered_to` / `source_nodes` 指向不存在节点；节点类别、
AGENT/next step 选择和只有 `mapped_to` 的 coverage 去向疑点只给 warning；后者检查可执行 prompt block
是否真实渲染。若 source key 与流程块 id 不同，先在 coverage 项填写 `rendered_to`。
同一轮完成 source → compile 不要求 handoff。只有任务需要跨轮恢复、多 worker / agent 交接，或 source
可能被人工编辑时，才建议运行 `emit-handoff --plan-file ... --index-file ... --source-file ... --out-file ...
--pretty`，并由接手方在 compile 前显式运行 `verify-handoff`。handoff 只记录现有 validation 和 warning，
不新增阻断；文件未变化即验证通过，发生变化才返回 `STALE_MIGRATION_PLAN`。该合同只属于迁移侧，不改
通用 Chatflow compile。

## 迁移摘要和自检

向用户报告：

- 旧图入口、主干、分支、用户轮次、人工接管和终端的理解；
- 已确认的 SOP → 节点映射 Mermaid；
- 每个 old agent、tool、explicit edge、action edge 的 coverage；
- 合并、拆分、改写和经用户确认的删减及其影响；
- 真正阻塞项、已解决项和仍需确认项；
- 进入目标图阶段后的实现、校验和回放状态（若已执行）。

完成迁移计划前逐项检查：

- 所有结构化工具、动作、模板、知识能力和终端都有证据与 coverage；
- `displayPrompt` 的噪音没有被误判成可执行依赖；
- 每个合并都有相同输入、用户轮次、资源、分支和下游语义的证据；
- 每个 SOP 流程块都在 Mermaid 中显示了确认的节点类别和条件关系；
- 每个 `open_question` 都是必要且可执行的；
- 已选节点类别只是候选，尚未在本文件填写目标字段或默认边；
- 进入目标图阶段前已读取相应的 CHAT_FLOW 文档。
