# CHAT_FLOW

把流程描述、流程图或已有 CHAT_FLOW 修改需求，整理成可校验、可部署的 `chatFlowGraph`。

## 先判定模式

| 输入特征 | 模式 | 先读 |
|---------|------|------|
| 文字描述 / 流程图截图 / PDF | 新建 | `workflow.md`、`node-selection.md`；图片输入再读 `visual-translation.md` |
| 已有 CHAT_FLOW agent_id / graph + 修改要求 | 增量 | `workflow.md`、`graph-spec.md` |

新建 / 增量模式确定后：

1. 先用 `node-selection.md` 选节点类型，不要凭节点名猜。
2. 对每个最终会使用的候选节点读取对应 `nodes/<node>.md`；字段、出边和 runtime 行为按节点文档确认。节点文档是功能合同，不是 PE/Role 提示词。
3. 新建图或用户明确提供 source 时，写 source JSON 前读 `graph-spec.md`；已有 CHAT_FLOW 的增量修改先按 `workflow.md` 执行 `inspect`，完整 graph 就是后续修改、校验和保存草稿的输入。
4. 只读将要使用的 `nodes/<node>.md`，按节点说明填写字段。
5. 编译、校验、写回、发布流程按 `workflow.md` 执行。

任何节点只要出现必填配置、输入字段、输出字段、变量 selector、资源 id、模板、知识库目录、工具参数、状态分支或等待语义无法从现有上下文唯一确定，都必须提出 `open_questions`，列出“新建资源/变量、使用哪个现有项、转人工或不迁该自动化”等可执行选项和影响；用户确认前不得凭名称相似自动绑定，不得伪造输出字段、资源 id、TOOL 出参路径、CODE 输出字段或下游分支。

新建图禁止使用即将下线节点。订单号/订单信息场景禁止选择 `COLLECT_ORDER`；除非是在维护已有图并必须保留
已存在行为，否则应使用变量系统订单字段、`QUESTION(VARIABLE)`、`TOOL`、`IF_ELSE` / 工具状态分支和必要的
`AGENT` 组合表达。

新建图的变量节点只选择 `VARIABLE_PROCESS`；`VARIABLE_EXTRACT` / `VARIABLE_ASSIGNMENT` 只维护已有图。INTENT 节点的 `prompt` 是可选的全局识别 PE，默认使用 `None`；`history_round_limit` 默认使用 `None`，交由后端默认策略。只有当用户需求明确包含跨意图的统一识别规则、边界或优先级时才生成 prompt；生成后先向用户确认是否启用，用户不需要时保留 `prompt: null`。

只要候选里出现 AGENT，必须读 `nodes/agent.md` 的 `next_steps And Transfer Tools`：`next_steps` 只生成流程内跳转工具，AGENT 自主转人工使用标准 `transferHuman` LibraryBlock，不能把转人工配置成 nextStep。不要把 AGENT 当作任意业务步骤的默认容器。

## 工作文件

- source：`/workspace/state/agent-builder/chatflow/*_source.json`（新建或整图重建时）
- 大图 fragment / integration：`/workspace/state/agent-builder/chatflow/<task>/blocks/`
- graph：`/workspace/state/agent-builder/chatflow/*_graph.json`（已有图 inspect 后的 patch 也属于此类）
- state：`/workspace/state/agent-builder/chatflow/`，跨轮复用，文件名稳定
- outputs：`/workspace/outputs/agent-builder/chatflow/`，只放用户明确需要下载或留档的文件
- 需要用户确认后继续执行的配置、source、graph 必须写 state，不写 tmp

继续已有 CHAT_FLOW 时，先 `inspect` 拉当前完整 graph，并将它作为本次维护的工作文件。

## 固定原则

- 新建图使用 source JSON；整体重建可使用 source -> compile；已有 CHAT_FLOW 的增量修改使用 inspect 得到的完整 `chatFlowGraph`，包括新增/删除节点、修改边和调整条件分支。
- 大图先按已确认的流程块完成 keyed source fragment，再合并为唯一 source 并只编译一次；不合并已编译 graph。
- 固定动作使用 `chatflow_builder.py` CLI，不写临时 Python 脚本，不 import builder 函数。
- `compile` / `validate` 有 error 必须先修同一个 source 或 graph 文件，再重新执行。
- 新建、发布前必须让用户确认；增量修改默认保存草稿，不发布。
- 工具状态确定后必然发送的固定回复优先查模板并使用 `REPLY(TEMPLATE)`；若固定话术是某个上下文判断节点
  的 PE/输出约束，则逐字保留在该节点实际使用的文本字段，不能仅因它是固定话术就强制改成 REPLY。
  需要用户选择并分支时用 `QUESTION(USER_REPLY)`。
- CHAT_FLOW 不感知 `metadata` 路径；禁止在任何节点 prompt、selector、条件、工具入参或代码输入里写 `metadata.xxx`。变量系统字段通过 ai-fields 暴露，使用 `SYSTEM` selector 或相应节点的 ai-field 绑定；支持变量模板的节点可直接引用已连通上游 selector。
- AGENT / `REPLY(PROMPT)` 通过 `ai_field_ids` 读取变量系统字段；需要稳定使用上游输出时，先用 `VARIABLE_PROCESS` 赋值到 SYSTEM 字段。`REPLY(DYNAMIC_TEMPLATE)` 与 LLM 模板按各自节点文档使用 `[[var:...]]`。
- 图中不能有环；多轮追问交给节点 `maxRounds`，不要在图层回连上游节点。
