# FINISH

## 功能概述

结束流程，不发送回复、不转人工。

## 创建方式

```json
{"from": "final_reply", "to": "$finish"}
```

## 创建参数

通常只通过 `$finish` 引用，不需要手写节点字段。

## Edges

- 必须有入边。
- 无出边。

## Resource Dependencies

无。

## 限制

- 平台不强制 FINISH 唯一。
- 默认使用单个共享 `$finish`，让终端路径汇聚，减少无意义终端节点。

## Common Mistakes

- 把需要先回复的终止路径直接连 `$finish`，导致用户收不到结束话术。
- 误以为平台要求只能有一个 FINISH；这是推荐约定，不是硬校验。
