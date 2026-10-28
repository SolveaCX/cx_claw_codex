# Chatflow 工作流

## 大图的流程块实现

整体流程图已经确认且单次上下文不适合实现整张大图时，按确认图中的稳定流程块分别实现 source fragment，
不要把整份大图重新塞回一次模型上下文。流程块来自当前任务已经确认的设计，不依赖任何特定上游图格式或
迁移字段。每个 fragment 只包含该流程块的 `nodes` 和块内 `edges`，节点 `key` 必须全局唯一；fragment
不写 `entry`，也不能写到另一流程块的边。

最终 integration 文件只拥有全图 `entry` 和流程块之间的边，不定义节点。例如：

```json
{
  "entry": "collect_order",
  "edges": [
    {"from": "collect_order", "to": "lookup_order"}
  ]
}
```

所有 fragment 完成后，先合并 source，再只编译一次最终 source：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow merge-source \
  --fragment-file /workspace/state/agent-builder/chatflow/<task>/blocks/collect_order.json \
  --fragment-file /workspace/state/agent-builder/chatflow/<task>/blocks/lookup_order.json \
  --integration-file /workspace/state/agent-builder/chatflow/<task>/blocks/integration.json \
  --out-file /workspace/state/agent-builder/chatflow/<task>_source.json \
  --pretty
```

随后对这份唯一 source 执行 `compile` 和 `validate`。不要分别编译流程块，也不要合并已编译的 graph JSON；
后者会重复生成入口、节点 id、布局和共享终端。

## 新建

1. 如果输入是截图或 PDF，先读 `visual-translation.md` 得到结构化摘要。
2. 读 `node-selection.md` 形成候选节点组合。
3. 在写 source 前，必须先向用户展示拟构建 Mermaid、节点职责、边条件（默认将 Y 解释为“条件满足”、N 解释为“条件不满足”，并说明是否存在用户确认语义）、等待/收集点和不确定点；结构性流程未经用户确认不得 compile 或 deploy。若当前任务已经有确认过的整体流程图，直接复用该确认，不重复增加确认轮次。
4. 在最终选择节点前，必须读取每个候选节点对应的 `nodes/*.md` 定义，确认 role、edges、
   prompt/字段约束和常见误用；不要只凭节点名理解用途。
5. 普通小图按 `graph-spec.md` 写 source JSON 到 `/workspace/state/agent-builder/chatflow/<task>_source.json`；
   大图按上一节写流程块 fragment，再合并为这份 source。
6. 再次按已选节点的 `nodes/*.md` 补齐字段和资源 id。
   AGENT 内需要模型自主决定是否执行的模板、普通工具和转人工动作使用 `nodes/agent.md` 定义的标准
   LibraryBlock；确定性动作仍使用对应独立节点，不能只写普通文字描述。
7. 检查变量来源：CHAT_FLOW 不感知 `metadata` 路径，所有节点都禁止写 `metadata.xxx`。AGENT / `REPLY(PROMPT)` 如需稳定使用上游输出，先用 `VARIABLE_PROCESS` 桥接到变量系统字段；`REPLY(DYNAMIC_TEMPLATE)`、LLM 和 HUMAN_REVIEW 的模板可直接使用其支持的上游 selector。
8. 编译同一份 source：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow compile \
  --source-file /workspace/state/agent-builder/chatflow/<task>_source.json \
  --graph-file /workspace/state/agent-builder/chatflow/<task>_graph.json \
  --pretty
```

9. 校验同一份 graph：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow validate \
  --graph-file /workspace/state/agent-builder/chatflow/<task>_graph.json \
  --pretty
```

10. 失败就改同一个 source 后重新 compile + validate。若只出现 `queryAiFields` / `field/internal/list` / `tars: Name does not resolve` 相关 warning，说明变量字段服务不可用；没有字段 id 依赖的图可继续后续确认，不要改图结构绕开。
    含 LibraryBlock 的 AGENT 还要核对：模板块使用具体模板内容 ID、模板状态为 `ENABLED`、`usedPlugins`
    已包含普通工具 ID，并从 Chatflow 专用插件目录按类型绑定当前项目真实的 `TEMPLATE_REPLY` /
    `TRANSFER_TO_HUMAN` 系统插件 ID；同时确认 `transferToHumans=[]`、runtime `prompt` 与 `displayPrompt`
    同步、nextStep 没有被误当成人工接管。
11. 校验通过后，对同一份 graph 执行 `deploy --phase preview`，向用户展示环境、租户、Agent 名称和图摘要。
    preview 只生成短时确认凭证，不创建 Agent。
12. 用户确认后，对同一份 graph 执行 `deploy --phase commit --confirmation-token-stdin --idempotency-key <key>`；
    确认凭证只通过 stdin 输入，不放进命令参数、文件或日志。一次创建多个 CHAT_FLOW agent 时，顺序执行；
    不要用 shell `&` 并发部署多个 agent。
13. commit 成功后执行一次 `inspect` 回读；逐个检查 LibraryBlock 仍为标准格式。默认只保存草稿，
    除非用户明确要求发布，不执行 `publish`。

本地无网络或尚未准备登录态时，可在 compile 和 validate 后加 `--offline` 做结构预检。离线模式跳过远端 AI 字段、插件存在性和插件参数合同检查；上传前必须联网复核。

## 增量修改

1. 先 inspect 拉当前图，并写入本次 patch graph：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow inspect \
  --agent-id <agent_id> \
  --out /workspace/state/agent-builder/chatflow/patch_<agent_id>_graph.json \
  --pretty
```

2. inspect 得到的完整 graph 是已有流程的编辑基线。已有 ChatFlow 的维护沿用 inspect 得到的 patch graph，可在这份 patch graph 上修改节点字段、增删节点、修改边、拆分条件分支或调整路由等，保持未涉及节点及其原始配置不变。
3. validate patch graph 通过后默认 update 保存草稿，不发布：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow update \
  --agent-id <agent_id> \
  --graph-file /workspace/state/agent-builder/chatflow/patch_<agent_id>_graph.json \
  --phase preview \
  --pretty
```

4. 用户确认预览后，用 `--phase commit --confirmation-token-stdin --idempotency-key <key>` 保存草稿。
5. 用户明确确认发布后，对同一份 graph 先执行 `publish --phase preview`，确认后再对同一份 graph 执行
   `publish --phase commit --confirmation-token-stdin --idempotency-key <key>`：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent-builder chatflow publish \
  --agent-id <agent_id> \
  --graph-file /workspace/state/agent-builder/chatflow/patch_<agent_id>_graph.json \
  --phase preview \
  --pretty
```

## 变更方案说明

- 新建图方案，或增量任务涉及新增 / 删除节点、修改边、调整条件分支、改变入口出口或路由关系等结构性修改时，面向用户的说明里应附一段 Mermaid，概括修改后的流程结构，帮助用户确认理解是否一致。
- 大图不要完整铺开，优先展示受影响子图，并保留这段子图与上游入口、下游出口的连接关系；必要时再补一句未展示区域保持不变。
- Mermaid 必须根据 inspect 得到的现有图、待写入的 source / graph 以及 validate 结果生成。条件边使用真实出边语义或 handle；代码节点必须明确标成代码节点，并展示它实际连接的上下游，不能因为代码内容复杂就从图中省略。
- 只修改 prompt、话术、模型参数、工具入参映射或单个节点内部字段，且不改变节点和边时，不强制输出 Mermaid。
- 对已有图、节点配置或提示词提出修改方案时，用户确认前按整体输出规则用 `diff` 展示受影响片段的前后差异；结构性修改可同时提供 Mermaid 和 diff，分别说明流程关系与具体配置变化。
- 用户确认前展示的是“拟修改结构”；update / deploy 后展示的是实际校验通过的结构。不要把尚未写入的方案描述成已经生效。
- Mermaid 只用于解释，不能替代 source JSON、graph JSON 或 validate。图示与实际 graph 不一致时，以校验通过的 graph 为准，并立即修正图示。

## 状态和留档

- 工作中的 source / graph 放 `/workspace/state/agent-builder/chatflow/`。
- 大图的 fragment 与 integration 放 `/workspace/state/agent-builder/chatflow/<task>/blocks/`；合并后的唯一 source
  仍放 `/workspace/state/agent-builder/chatflow/<task>_source.json`。
- 文件名稳定，跨轮覆盖，便于继续。
- 等用户确认后继续执行的配置文件也放 `/workspace/state/agent-builder/chatflow/`，不要放 `/workspace/tmp/`。
- 只有用户明确要求下载或留档，才复制到 `/workspace/outputs/agent-builder/chatflow/`。

## 禁止

- 不写临时 Python 脚本承载构图、校验、部署。
- 不 import `agent-builder chatflow`。
- 不用 `update-agent --id ... --data-file graph.json` 写回纯 graph。
- 不在用户确认前新建或发布。
- 不在任何节点 prompt、selector、条件、工具入参或代码输入里写 `metadata.xxx`；变量系统字段通过 ai-fields
  暴露，需要变量时按节点契约使用 `SYSTEM` selector、`ai_field_ids` 或支持的上游变量模板。
