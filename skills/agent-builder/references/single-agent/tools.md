# SINGLE_AGENT Tools

SINGLE_AGENT 通过 `usedPlugins` 绑定可调用工具。对外叫“工具”，底层字段仍叫 `plugin`。

## 查询工具

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-plugins --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-plugin --id <tool_id> --pretty
```

`list-plugins` 只看精简列表；确认 requestParam / responseParam / actionStatuses 时使用 `get-plugin` 查看完整定义。

## 绑定格式

SINGLE_AGENT 通常使用工具 id 数组：

```json
{
  "usedPlugins": [2019, 2020]
}
```

不要写成对象数组，除非已确认该 Agent 类型和接口需要完整工具对象。

## 调试

`run-plugin` 会真实调用目标接口，只在用户明确要求或授权后执行；不能把它当作绑定工具或上线前的默认步骤。目标为写接口时，执行前还要额外确认请求体和影响范围。

`run_tool_config.json` 必须是包含 `externalHttpCallConfig` 和 `externalHttpCallRequestBody` 的 envelope，完整结构见 `../tools/http-tool.md`：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api run-plugin \
  --data-file /workspace/state/agent-builder/run_tool_config.json \
  --pretty
```
