# START

## 功能概述

CHAT_FLOW 唯一入口节点。source JSON 通常不显式创建 START，由顶层 `entry` 自动生成。

## 创建方式

```json
{"entry": "first_business_node"}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| entry | 首个业务节点 key |

## Edges

START 自动连到 `entry`，handle 为 `SOURCE`。

## Resource Dependencies

无。

## 限制

- 平台要求 START 必须且只能有一个。
- START 必须有出边。

## Common Mistakes

- 手写多个 START。
- 已写 `entry` 又额外手写一个重复 START。
