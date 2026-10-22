# 工具管理（Legacy 兼容入口）

> 本文件不再维护工具 schema。工具查看、创建、更新、调试、MockData 和 X-Token 配置统一由 `agent-builder` 负责。

权威文档：

- 总入口：`../../agent-builder/references/tools/overview.md`
- HTTP 参数、状态映射、relation/value 契约：`../../agent-builder/references/tools/http-tool.md`
- Mock / Excel / CSV：`../../agent-builder/references/tools/mock-tool.md`
- X-Token：`../../agent-builder/references/tools/x-token.md`

底层兼容命名仍是 `plugin` / `pluginId` / `queryPlugin`，常见工具类型仍是 `EXTERNAL_HTTP_CALL`。旧任务进入本页后，应立即转到上述 agent-builder 文档，不在这里复制或推导另一套 payload。

## 核心命令入口

统一使用 `/workspace/state/agent-builder/` 保存跨轮配置：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-plugins --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-plugin --id <tool_id> --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/agent-builder/scripts/tools/validate_tool_config.py \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api create-plugin \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api update-plugin \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api replace-mock-data \
  --name <mock_type> \
  --data-file /workspace/state/agent-builder/mock_records.json --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api query-mock-data \
  --name <mock_type> --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api run-plugin \
  --data-file /workspace/state/agent-builder/run_tool_config.json --pretty
```

`run_tool_config.json` 必须使用 `externalHttpCallConfig` + `externalHttpCallRequestBody` envelope；具体结构只看 agent-builder 的 `http-tool.md`。

## 兼容与安全边界

- 创建前先查重并运行静态 validator；写入前确认环境和影响范围；创建后使用 `get-plugin` 回查完整定义。
- Authorization、X-Token 等鉴权 Header 按普通 `headerParams` 配置。
- `run-plugin` 会真实调用目标接口，只在用户明确要求或授权后执行。目标为写接口时，执行前还要额外确认请求体和影响范围；它不是创建或上线的默认步骤。
- MockData 的 `replace-mock-data` 是全量替换写操作，执行前必须确认；`--name` 在 MockData 命令中表示 `mock_type`。
- BOOLEAN 状态规则兼容 JSON boolean `true` / `false` 和前端保存的字符串 `"true"` / `"false"`；手写 JSON 推荐 boolean。完整类型与 relation 约束以 agent-builder 的 `http-tool.md` 为准。
- `actionStatuses` 默认分支兼容 `"condition": {}` 和 `"condition": {"or": []}`；新建配置推荐 canonical `{}`，但 `or: []` 同样合法。
- 工具绑定格式和节点边界按具体 Agent 形态的 agent-builder 文档处理，不沿用本 legacy 文件的历史示例。
