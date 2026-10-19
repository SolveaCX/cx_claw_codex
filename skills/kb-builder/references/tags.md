# 知识库标签管理

知识库标签是知识条目上的字符串标签，不是 `tagSetting` 标签树。读取问答时使用 QA 详情接口；读取文档/网页时使用 DOCUMENT 详情接口；写入统一使用 `editTags`，并把对应的 `type` 一并传给接口。

## 接口

```text
POST /sns_v1/project/{projectId}/editTags
```

请求体：

```json
{
  "type": "QA",
  "knowledgeIds": [488523],
  "tagList": ["123", "kb-test"]
}
```

`tagList` 是最终标签列表。调用前必须先读取目标知识的顶层 `tags`，再按用户意图计算最终列表：默认追加；明确要求替换时覆盖；删除时计算差集。调用后重新读取知识核对 `tags`。

示例状态文件：

```json
{
  "type": "QA",
  "knowledgeIds": [488523],
  "tagList": ["kb-test"],
  "operation": "append"
}
```

`operation` 支持 `append`、`replace`、`remove`，默认是 `append`。`metadata.tags` 暂不作为标签写入字段；返回对象中的顶层 `tags` 是本能力的事实来源。

文档和网页分别传列表返回的 `FILE`、`WEBSITE`；不要因为二者底层都属于 DOCUMENT 就把 `type` 写成 `DOCUMENT`。

## 标签配置到知识

标签绑定知识只使用 `editTags`，不使用隔离关键词接口：

```text
测试环境：POST /sns_v1/project/{projectId}/editTags
生产环境：POST /api_v2/qam/project/{projectId}/editTags
```
