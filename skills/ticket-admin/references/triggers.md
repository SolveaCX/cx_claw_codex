# 触发器与 Webhook

设置 → 效率 → 触发器（`/settings/trigger`）和 Webhook（`/settings/trigger-webhooks`）是两个独立菜单。
所有命令入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket`，参数通过 `--params-json` 或 `--params-file` 传入。

## 查看触发器与排查执行结果

先读规则、适用渠道和意图选项，再按 ticketId 读执行记录。静态 preview 的 eventContextRequired 表示缺少事件上下文，不能断言历史执行结果。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-triggers` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-trigger-categories` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-trigger-channel-options` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-trigger-executions` | before:integer, limit:integer, **ticketId**:string | 支持 `--all`；检查截断 |
| `ticket admin-trigger-preview` | **ticketNumber**:string, **id**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-trigger-intent-options` | **projectId**:integer | 单次响应；保留服务端分页字段 |

先用 `ticket admin-triggers` 取得规则列表，再按 ID 或准确名称定位目标。列表已包含规则状态、分类、顺序、版本、重复策略，以及 conditionsJson/actionsJson 和可用的展示字段；前端也从该列表打开规则编辑器，不需要猜一个详情接口。

解释时分别说清：何时触发、哪些条件须满足、配置了哪些动作、是否启用、是否限制每张工单只执行一次。动作配置可以读取和解释，但不能执行这些动作。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-triggers
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-trigger-preview --params-json '{"id":"123","ticketNumber":"ST-123"}'
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-trigger-executions --params-json '{"ticketId":"456","limit":20}' --all --max-pages 20
```

ticketNumber 是对外工单号，ticketId 是从详情取得的内部 ID。预览不能替代执行记录；执行记录分页截断时说明已读范围。规则、分类的新增/修改/删除/排序和启停接口本期不接。

## Webhook 菜单的当前缺口

Webhook 页面读取 legacy-endpoints，触发器动作选择器读取 endpoints；它们不能互相替代。当前 CLI 尚未覆盖这两项读取，不能声称已查到 Webhook 配置或订阅事件；请客户在产品对应页面核对。这里不推断 Webhook 没配置，也不执行测试发送。
