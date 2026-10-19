# RAG_REPLY

## 功能概述

单轮知识库检索并回复。新建知识库问答默认使用该节点。

RAG_REPLY 会先用配置的知识目录检索，再向用户发送答案。它的输出取决于知识是否命中：命中走
`TRUE`，未命中走 `LACK_KNOWLEDGE`。它不是普通固定话术节点，也不负责调用业务工具或执行开放式流程决策。

## 创建方式

```json
{
  "key": "product_knowledge",
  "type": "rag_reply",
  "prompt": "Answer based on the selected knowledge base.",
  "kb_dirs": [1001, 1002],
  "knowledge_keyword_ids": [11, 13],
  "knowledge_keyword_selector": ["SYSTEM", "Order", "isolation_keyword"],
  "customize_query": true,
  "query_selector": ["EXTRACT", "extract_question", "question_text"]
}
```

## 创建参数

| 字段 | 说明 |
|------|------|
| prompt | 知识回答要求；普通文本 |
| kb_dirs | knowledgeDirectoryIds；可选，未配置时节点不会检索知识并通常走 `LACK_KNOWLEDGE` |
| knowledge_keyword_ids | knowledgeKeywordIds；隔离关键词 ID 数组，限定检索范围/隔离条件 |
| knowledge_keyword_selector | knowledgeKeywordSelector；变量选择器，运行时值为隔离关键词名称或名称数组；由模型根据关键词来源自动选择 selector 类型 |
| customize_query | 是否用变量作为检索 query |
| query_selector | `customize_query=true` 时必填的上游变量选择器 |
| disable_prev_node_results | 是否不把前序节点结果注入知识回答上下文，默认 false |

## Edges

必须同时有 `TRUE` 和 `LACK_KNOWLEDGE`。运行时 `TRUE` 分支如果有出边，chatflow 后端会注入 `WAIT -> USER_INPUT -> 原 TRUE 下游`，也就是知识回复命中并回复用户后，等待下一轮用户输入再继续后续流程；`LACK_KNOWLEDGE` 直接走缺知识兜底分支。

如果命中知识后不需要继续流程，`TRUE` 可连 `$finish`；如果希望命中后继续处理下一轮用户输入，`TRUE` 连后续节点并接受上述等待语义。

## Resource Dependencies

先确认知识库目录 id。目录为空会导致总走 `LACK_KNOWLEDGE`。

## 限制

- 新建默认用 RAG_REPLY，不用 KNOWLEDGE_REPLY。
- `kb_dirs` / `knowledgeDirectoryIds` 是可选的；未配置或为空时，节点没有可检索目录，通常会走 `LACK_KNOWLEDGE`。只有用户明确要求空知识路径时才省略它。
- 使用固定隔离关键词时设置 `knowledgeKeywordIds`，值必须是通过 `kb-builder` 查询到的关键词数字 ID，不要把关键词文本直接填进去。
- 使用运行时变量决定隔离关键词时设置 `knowledgeKeywordSelector`，变量值必须是关键词名称或名称数组；需要先用 `kb-builder` 搜索/创建关键词，确认名称与知识中心一致。selector 类型按变量实际来源选择：系统字段用 `SYSTEM`，工具输出用 `TOOL`，提取/代码/LLM/AGENT/人工审核输出分别用对应类型。
- `knowledgeKeywordIds` 与 `knowledgeKeywordSelector` 默认互斥：固定关键词使用 ID，动态关键词使用 selector。后端尚未明确两者同时配置时的合并语义，因此 validator 会拒绝同时配置。
- `prompt` 不插变量；需要变量作为检索 query 时用 `customize_query=true` + `query_selector`。
- `query_selector` 支持 `SYSTEM`、`TOOL`、`EXTRACT`、`CODE`、`LLM`、`AGENT`、`HUMAN_REVIEW`。
- EXTRACT selector 第三段是 extract `id`，不是 `name`。
- 不使用工具状态 `ACTION_STATUS_NAME` 作为检索 query。
- `AGENT` selector 只能引用当前上游路径已连通 nextStep 的 `params[].name`。

## Common Mistakes

- 忘记 `LACK_KNOWLEDGE` 兜底。
- 知识目录为空还以为会命中知识。
- 把隔离关键词文本填入 `knowledgeKeywordIds`；该字段只接受关键词 ID。
- 未先查询/创建隔离关键词就配置 ID，导致节点引用不存在的关键词。
- 用户要求按变量切换隔离关键词，却误用 `querySelector`；前者使用 `knowledgeKeywordSelector`，后者只控制检索 query。
- `customize_query=true` 但没配置 `query_selector`。
- 把检索 query 写成 prompt 里的变量模板。
