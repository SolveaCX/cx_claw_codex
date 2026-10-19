# NOTE

## 功能概述

画布注释节点，只用于给搭建者留下说明，不参与 CHAT_FLOW 运行。

前端创建 NOTE 时使用 `type: CUSTOM_NOTE`、`data.category: NOTE`、`data.config.noteText`；后端 `GraphJSONLoader` 解析节点时会跳过 `CUSTOM_NOTE`。

## 创建方式

通常不要在 source JSON 中新建 NOTE。只有在增量维护已有图并需要保留画布备注时，才保留已有 NOTE。

## 创建参数

| 字段 | 说明 |
|------|------|
| type | 完整 graph 中为 `CUSTOM_NOTE` |
| data.category | `NOTE` |
| data.config.noteText | 注释文本 |

## Edges

无运行边。NOTE 不需要从 START 可达，也不要求入边或出边。

## Resource Dependencies

无。

## 限制

- NOTE 不参与运行、变量、工具、模板、路由或发布后的执行逻辑。
- 不要连接 NOTE 节点；连线不会表达业务路径。
- 校验运行图时不要把孤立 NOTE 当作异常。

## Common Mistakes

- 把 NOTE 未连接 START 当作图异常提醒用户。
- 用 NOTE 表达业务流程中的条件、回复或人工说明。
