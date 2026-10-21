# 工具 Overview

工具是 Agent 可调用的外部能力，常见类型是 `EXTERNAL_HTTP_CALL`。底层 API 和字段名仍使用 `plugin` / `pluginId` / `queryPlugin`。

## 常用命令

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-plugins --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-plugin --id <tool_id> --pretty
python3 /skills/agent-builder/scripts/tools/validate_tool_config.py \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api create-plugin \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-plugin \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api run-plugin \
  --data-file /workspace/state/agent-builder/run_tool_config.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api replace-mock-data \
  --name <mock_type> --data-file /workspace/state/agent-builder/mock_records.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api query-mock-data \
  --name <mock_type> --pretty
```

`list-plugins` 只返回精简列表。排查或配置入参、出参、`actionStatuses` 时用 `get-plugin` 查看完整定义。Header 与其他工具字段一样通过 `headerParams` 配置。MockData 命令复用 `--name` 表示 `mock_type`，不是工具名。

## 创建流程

普通 HTTP 工具按以下顺序处理：

1. `list-plugins --pretty` 查重。
2. 将配置写入 `/workspace/state/agent-builder/tool_<name>.json`；跨轮配置不能写 `/workspace/tmp/`。
3. 运行 `validate_tool_config.py` 做静态验证。它不只检查 JSON 语法，还检查参数树、状态映射的精确字段路径、类型和关系。
4. 展示和配置摘要，请用户确认。
5. 执行 `create-plugin --data-file ...`。
6. 从创建结果取得 ID，再执行 `get-plugin --id <tool_id> --pretty`，确认服务端保存后的完整定义与预期一致。

Mock 工具必须先创建占位工具取得 ID，才能生成唯一的 `mock_type`；其完整顺序、安全确认和回查方式见 `mock-tool.md`。

`run-plugin` 会实际请求工具配置中的目标接口。其 data file 必须使用 `{"externalHttpCallConfig": {...}, "externalHttpCallRequestBody": {...}}` envelope，完整示例见 `http-tool.md`。只有用户明确要求或授权调试时才能运行；若目标是写接口，还要在执行前单独确认。它不是创建工具的默认步骤，也不能表述为“上线前必须运行”。

## 详细文档

- HTTP 工具结构：`http-tool.md`
- Mock / Excel / CSV 工具：`mock-tool.md`
- Agent 工具配置：`tool-config.md`
- X-Token / header patch：`x-token.md`
