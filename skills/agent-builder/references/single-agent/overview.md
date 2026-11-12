# SINGLE_AGENT

SINGLE_AGENT 适合目标单一、分支少、一个 prompt 能说清职责的场景。超过 3 个稳定流程分支、需要条件路由或人工审批时，改用 CHAT_FLOW。

## 创建

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent create \
  --data-file /workspace/state/agent-builder/single_agent_payload.json \
  --pretty
```

最小结构：

```json
{
  "name": "FAQ_Bot",
  "type": "SINGLE_AGENT",
  "source": "MANUAL",
  "prompt": "...",
  "displayPrompt": "...",
  "usedPlugins": []
}
```

## 更新

更新前先读取当前对象，确认目标字段；提交时只传需要修改的字段：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent get --id <agent_id> --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent update \
  --id <agent_id> \
  --data-file /workspace/state/agent-builder/update_agent_<agent_id>.json \
  --pretty
```

约束：

- `agent update` 会读取完整对象并深度合并局部 patch，未传字段保持不变。
- patch 中出现 `id` / `agentId` 时必须与 `--id` 一致。
- 改 prompt 时同步改 `prompt` 和 `displayPrompt`。
- 工具只写真实工具 id；先用 `list-plugins` / `get-plugin` 确认。

## 相关文档

- prompt：`prompt.md`
- 工具绑定：`tools.md`
- 语音 Agent：`voice.md`
