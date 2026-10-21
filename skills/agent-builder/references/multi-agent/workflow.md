# MULTI_AGENT Workflow

## 不支持新建

用户要求新建 MULTI_AGENT 时，直接说明：

```text
MULTI_AGENT 是 legacy 形态，不支持新建，因为路由和工具动作分散在旧 graph/prompt/meta tools 中，不好维护。新建多节点流程请改用 CHAT_FLOW。
```

然后切到 `../chatflow/overview.md`。

## 查看 / 解释已有 MULTI_AGENT

1. 如果用户只给 agent_id，先取完整对象：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-agent --id <agent_id> --pretty
```

2. 将完整对象保存到：

```text
/workspace/state/agent-builder/multi-agent/read_<agent_id>_raw.json
```

3. 按 `graph-spec.md` 读取旧图字段。如果 graph 很大或 `displayPrompt` 含大量 HTML，必须先跑 analyzer：

```bash
python3 /skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py inspect \
  --input /workspace/state/agent-builder/multi-agent/read_<agent_id>_raw.json \
  --out-dir /workspace/state/agent-builder/multi-agent \
  --pretty
```

4. 解释结果必须区分：

- old agents / tools / explicit agentEdges / action edges 数量。
- 入口 agent。
- 真实外部工具和 actionStatus。
- template / transfer / finish / KB 结构能力。
- prompt 中疑似旧工具指令和前端占位符。
- 风险项：dangling ref、KB 空目录、模板缺失、prompt/action 冲突。

纯查看/解释任务的结果必须直接展示在对话里。可以保留 `overview.mmd`、`index.ai.json` 等 state 文件作为审计
证据，但不要让用户下载文件才能看到流程。迁移任务的交互门按 small / large 文档执行；large 模式不得把
每个 batch 的局部图或计划逐轮展示给用户。

## 更新已有 MULTI_AGENT

只有用户明确要求更新已有 MULTI_AGENT 时才进入 `update.md`。更新前必须先解释当前结构，并让用户确认 Mermaid、agent 清单、工具清单和 action 清单。

## 迁移到 CHAT_FLOW

本节只负责分流和执行顺序；迁移保真规则以 `migration/principles.md` 为准，具体步骤以
`migration/small.md` 或 `migration/large.md` 为准。

1. 先读 `graph-spec.md` 和 `migration/principles.md`，确认旧图证据、coverage 和 PE 改写要求。
2. 按大小选择：
   - 短小图：`migration/small.md`
   - 长图、HTML 噪音多、工具/action 多、用户要求先拆解：`migration/large.md`
3. 迁移前必须先理解旧结构，不直接把完整 raw JSON 交给模型生成 CHAT_FLOW。
4. small 模式按 `migration/small.md` 确认；large 模式只集中确认 blocking `open_questions` 和最终合并后的
   全局 SOP → 节点类别 Mermaid。映射确认后才进入目标 source。
5. 生成目标 source 时，切到 `../chatflow/graph-spec.md`、`../chatflow/node-selection.md` 和对应 `../chatflow/nodes/*.md`。
6. compile / validate / deploy 只使用 `../chatflow/workflow.md` 里的 CHAT_FLOW CLI。

迁移过程按 `migration/principles.md` 的“对话展示合同”输出。large 模式的 worker 只写 state，不与用户交互；
协调器合并并去重问题后才发起确认。state 文件路径只能作为复现依据放在末尾；除非用户明确要求下载或留档，
不把 Mermaid / plan / report 复制到 outputs。

## 状态文件

| 文件 | 用途 |
|------|------|
| `/workspace/state/agent-builder/multi-agent/read_<id>_raw.json` | 读取/解释旧 agent 原始对象 |
| `/workspace/state/agent-builder/multi-agent/update_<id>_payload.json` | 更新已有 MULTI_AGENT 的完整 payload |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/index.ai.json` | analyzer 裁剪后的 AI 输入 |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/overview.mmd` | 旧图 Mermaid 总览 |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/sop_mapping.mmd` | 经确认的 SOP → 节点映射 Mermaid |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/chunks.json` | 旧图 chunk 清单 |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/progress.json` | batch 检查点和可恢复进度 |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches/worker_manifest.json` | 当前并发 wave 的 worker 输入/输出清单 |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches/<batch>.context.json` | 单个 worker 的只读有界输入 |
| `/workspace/state/agent-builder/multi-agent/migrate_<id>_<name>/batches/<batch>.plan.json` | 单个 worker 的隔离输出；不含 Mermaid |

迁移生成 CHAT_FLOW source / graph 后，目标文件放 `/workspace/state/agent-builder/chatflow/`，不放回 `multi-agent/`。
