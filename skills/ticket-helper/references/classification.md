# 工单筛选目录

入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" <resource> <action>`，参数用 `--params-json` 或 `--params-file`。粗体为必填参数；`<命令> --help` 查看参数类型与默认值。

支持分页的查询可加 `--all --max-pages 20`，必须检查 `pagination.truncated`；`pageMetadata` 保留列名与总量。JSON 快照用 `--output <WORKSPACE>/outputs/ticket-helper/<唯一文件名>.json` 保存。

## 解析筛选条件

仅查询本次筛选实际用到的目录。名字唯一匹配后把 ID 写入对应过滤字段；存在多个候选时展示区分信息，未匹配到时请用户修正条件，不把未找到的标签当成“无标签”。目录只是筛选依据，具体客服工单结果仍需查询列表。

先将客服、渠道、品牌、标签等名称解析到目录 ID；重名时不要猜测。

| 业务查询命令 | JSON 参数 | 分页/交付 |
|---|---|---|
| `ticket catalog-users` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-assignable-users` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-channels` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-stores` | channel:string | 单次响应；保留服务端分页字段 |
| `ticket catalog-emails` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-phones` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-platforms` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-markets` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-brands` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-categories` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-skus` | 无 | 单次响应；保留服务端分页字段 |
| `ticket catalog-tags` | name:string | 单次响应；保留服务端分页字段 |
| `ticket catalog-tag-search` | **tagName**:string | 单次响应；保留服务端分页字段 |
| `ticket catalog-fields` | 无 | 单次响应；保留服务端分页字段 |

工单人工标签、AI 标签、完整标签路径和批量标签查询见 `<PLUGIN_ROOT>/skills/ticket-helper/references/tags.md`。
