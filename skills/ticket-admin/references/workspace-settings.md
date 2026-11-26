# 成员权限与工单基础配置

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-admin/<唯一文件名>.json` 保存。

## 成员和角色

按姓名/已知 ID 定位成员，再查其角色和权限；要解释当前用户可见范围时查 my-permissions。角色权限能解释部分菜单限制，但菜单还可能受灰度或产品域影响，权限齐全不等于证明所有入口都可见。只回答查询目标涉及的权限，不读取无关成员详情。

分别读取成员、角色定义、角色成员和当前权限；缺少配置权限时如实说明。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-members` | content:string | 单次响应；保留服务端分页字段 |
| `ticket admin-member` | **id**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-roles` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-role` | **id**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-role-members` | **id**:string | 单次响应；保留服务端分页字段 |
| `ticket admin-permissions` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-my-permissions` | 无 | 单次响应；保留服务端分页字段 |

## 字段与表单

用户问字段是否存在，先查定义；问“为什么不显示”，再查布局分组、顺序及返回的展示条件。字段有定义、页面可见、具体工单有值是三个不同事实；具体值由 ticket-helper 查询。确认缺口后给配置建议即可，不保存布局。

先用 `ticket admin-fields` 读字段定义，再查询 `custom_field_section_order` 获取展示分组及顺序；仅有字段列表不足以解释表单布局。AI 字段定义复用 `<PLUGIN_ROOT>/skills/ticket-admin/SKILL.md` 中的 Agent 域 CLI 命令。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket admin-fields` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-ai-tag-policy` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-inactivity` | 无 | 单次响应；保留服务端分页字段 |
| `ticket admin-settings-list` | **types**:array | 单次响应；保留服务端分页字段 |
| `ticket admin-toolbar-configs` | 无 | 单次响应；保留服务端分页字段 |

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-fields
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-settings-list --params-json '{"types":["custom_field_section_order"]}'
```

## AI 打标

设置 → AI → AI 打标使用 `ticket admin-ai-tag-policy` 读取策略现值。单张工单已打上的人工/AI 标签查询归 ticket-helper，不拿策略设置当成工单标签结果。

## 工具栏扩展

用 `ticket admin-toolbar-configs` 查询配置。第三方 iframe、外部 API 的 runtime/data 和测试调用未接，不能凭配置宣称扩展运行正常。

系统设置的旧页面当前仅有说明内容，不在当前设置菜单中；`ticket admin-settings-list` 是多个实际页面共用的查询，按上面的已知类型使用，不猜类型。
