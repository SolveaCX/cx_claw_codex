# KNOWLEDGE_REPLY

## 功能概述

兼容多轮知识回复节点。仅用于用户明确要求保留，或已有图中原样维护。

## 创建方式

```json
{
  "key": "compat_knowledge",
  "type": "knowledge_reply",
  "prompt": "Answer based on the knowledge base.",
  "kb_dirs": [1001]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| prompt | 知识回答要求 |
| kb_dirs | knowledgeDirectoryIds |
| max_rounds | 多轮最大轮数 |
| disable_prev_node_results | 是否不把前序节点结果注入知识回答上下文，默认 false |

## Edges

必须同时有 `RESOLVED` 和 `UNRESOLVED`。

## Resource Dependencies

先确认知识库目录 id。

## 限制

- 新建默认不要用。
- 保留时必须补齐双出边。

## Common Mistakes

- 新图误用 KNOWLEDGE_REPLY。
- 缺少 `UNRESOLVED` 转人工路径。
