# X-Token And Header Patch

订单、物流等外部数据工具通常通过 header 传鉴权信息。更新 header 是写入操作，执行前必须让用户确认。

## 获取当前租户 X-Token

底层接口：

```text
GET /api_v2/gpt/accounts/apikey
```

脚本会通过 `SolveaClient.get_api_key()` 获取。

## Patch 已复制 Agent 的工具

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/agent-builder/scripts/patch_agent_tools.py \
  --agent-id <agent_id> \
  --tool-name new_Order_information_product \
  --tool-name new_Order_information_FBA \
  --tool-name new_Order_information_ship \
  --patch-x-token \
  --dry-run
```

确认 dry-run 输出后去掉 `--dry-run`。

## 原则

- 不打印 token 明文到最终回复。
- 先查 Agent 工具列表，再按工具名匹配。
- 找不到目标工具时返回明确提示，不继续猜。
- 参数错误可以修正后重试；接口连续失败时停止并返回原始错误。
