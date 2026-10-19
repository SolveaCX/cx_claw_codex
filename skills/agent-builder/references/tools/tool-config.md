# Agent 工具配置

## SINGLE_AGENT

SINGLE_AGENT 通过 `usedPlugins` 绑定工具。优先使用工具 id 数组：

```json
{
  "usedPlugins": [2019, 2020]
}
```

配置前必须确认：

- 工具 id 存在。
- requestParam 必填项能由 LLM、metadata、固定值或上下文提供。
- prompt 里提到的工具都在 `usedPlugins` 中。

## CHAT_FLOW

CHAT_FLOW 有两种用法：

- `TOOL` 节点：直接调用单个工具，适合结构化结果和 actionStatus 分支。
- `AGENT` 节点 `usedPlugins`：让 LLM 调工具并解释结果，适合非结构化判断。

构图细节读：

- `../chatflow/nodes/tool.md`
- `../chatflow/nodes/agent.md`
- `../chatflow/node-selection.md`

## 查看详情

```bash
cxclawctl api get-plugin --id <tool_id> --pretty
```

重点看：

- `meta.externalHttpCallConfig.requestParam.items`
- `meta.externalHttpCallConfig.responseParam.items`
- `meta.externalHttpCallConfig.actionStatuses`
- `headerParams`
