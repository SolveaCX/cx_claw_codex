# MULTI_AGENT

legacy MULTI_AGENT 只作为存量形态维护。用户没有明确指定旧 multi 形态时，多节点、多分支、工具状态分支或人工节点默认用 CHAT_FLOW。

## 先判定模式

| 输入特征 | 模式 | 先读 |
|---------|------|------|
| 用户要求新建 MULTI_AGENT / multi agent / multiAgentGraph | 不支持新建 | `workflow.md` 的“不支持新建” |
| 用户提供已有 MULTI_AGENT agent_id / 完整旧 JSON，要求查看、解释或审计 | 读取解释 | `workflow.md`、`graph-spec.md` |
| 用户明确要求更新已有 MULTI_AGENT | 存量更新 | `workflow.md`、`update.md` |
| 用户要求迁移 / 转新版 / 转 CHAT_FLOW，或输入含 `multiAgentGraph` / `agentEdges` / `classifierPlugin` | 迁移 | `workflow.md`、`graph-spec.md`、`migration/principles.md`，再按大小读 `migration/small.md` 或 `migration/large.md` |

用户只要表达“迁移 / 转新版 / 转 CHAT_FLOW / 从旧 agent 转过来”，本文件就是第一入口。不要先去
`../chatflow/overview.md` 做节点选择；先按本文件和 `workflow.md` 完成旧结构理解、大小判定和迁移计划。
目标 CHAT_FLOW source 明确后，才回到 `../chatflow/graph-spec.md`、`../chatflow/node-selection.md` 和对应
`../chatflow/nodes/*.md` 校验目标节点字段。

## 固定原则

- 不新建 MULTI_AGENT；新建多节点流程推荐 `../chatflow/overview.md`。
- 已有 MULTI_AGENT 可读取、解释、必要兼容更新、迁移。
- 旧图证据读取优先级：结构化 action/tool/plugin > `agentEdges` > `prompt` > `displayPrompt`。
- `displayPrompt` 默认是前端展示噪音和人工审计来源，不作为迁移后的模型输入。
- 迁移允许 PE 改写、节点合并和拆分；节点数可增可减，但必须由可执行合同决定，并输出 coverage 和 changed_items。

## 文档职责

| 文件 | 职责 |
|------|------|
| `overview.md` | 入口分流和边界 |
| `workflow.md` | 查看、解释、更新、迁移的操作步骤 |
| `graph-spec.md` | legacy JSON 字段、前端噪音清洗、证据优先级 |
| `update.md` | 仅更新已有 MULTI_AGENT 的完整对象更新规则 |
| `migration/principles.md` | 迁移保真、coverage、合并、PE 改写规则 |
| `migration/small.md` | 短小 legacy 图直接迁移流程 |
| `migration/large.md` | 长图 analyzer + 并发 batch；只确认合并问题和最终全局图 |
| `graph-structure.md` / `orchestration.md` / `migrate-to-chatflow.md` | 历史兼容跳转页；不要作为主流程读取 |

## 触发信号

- 用户明确说 MULTI_AGENT、multi agent、agent_graph、旧 agent、legacy graph、迁移到 chatflow。
- 用户明确说创建新的 multi、创建 MULTI_AGENT、更新 MULTI_AGENT。
- 输入 JSON 含 `multiAgentGraph`、`agentEdges`、`classifierPlugin`。
- 用户要求先转 Mermaid、先分解、分步骤迁移旧图。
- 旧图中有 `usedPlugins[].meta.toolAfterExecuteActions` 或工具 `actionStatuses`。

如果用户只是说“流程图、多节点、条件分支、工具状态分支、人工节点”，但没有明确指定 legacy multi，回到 `../chatflow/overview.md`。
