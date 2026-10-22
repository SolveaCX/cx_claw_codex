# SINGLE_AGENT

SINGLE_AGENT 适合目标单一、分支少、一个 prompt 能说清职责的场景。超过 3 个稳定流程分支、需要条件路由或人工审批时，改用 CHAT_FLOW。

## 创建

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api create-agent \
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

更新前先查完整对象：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-agent --id <agent_id> --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher api update-agent \
  --data-file /workspace/state/agent-builder/update_agent_<agent_id>.json \
  --pretty
```

约束：

- `update-agent` 必须提交完整对象。
- `agentId` 必须等于 `id`。
- 改 prompt 时同步改 `prompt` 和 `displayPrompt`。
- 工具只写真实工具 id；先用 `list-plugins` / `get-plugin` 确认。

## 相关文档

- prompt：`prompt.md`
- 工具绑定：`tools.md`
- 语音 Agent：`voice.md`
