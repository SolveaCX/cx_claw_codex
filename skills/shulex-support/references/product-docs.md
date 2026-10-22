# 产品文档查询

产品使用、配置、排障、功能说明类问题，只使用产品文档查询命令，不再调用旧的 GPT 售后知识库查询链路。

### 搜索 query 写法

文档搜索同时看语义和关键词。调用 `search-docs` 时，query 要像用户真实问题，但保留核心产品词、功能词和对象名：

- 推荐：`我该怎么使用人机协同节点`、`Human in Loop 人机协同节点怎么配置`
- 不推荐：只堆叠 2-3 个短关键词，尤其包含“使用”“设置”“功能”等泛词时，容易带出无关结果

查看搜索结果时，优先采用标题、页面路径、内容片段都命中核心概念的结果；只因为泛词命中的结果不要引用。

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/shulex-support/scripts/support.py search-docs \
  --query "<用户问题>" \
  --pretty
```

`search-docs` 用于搜索产品文档，返回结构化结果：

```json
{
  "query": "<用户问题>",
  "results": [
    {
      "title": "<文档标题>",
      "url": "<文档链接>",
      "page": "<页面路径>",
      "content": "<相关片段>"
    }
  ]
}
```

当需要进一步定位或读取文档文件时，使用文件查询命令：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/shulex-support/scripts/support.py query-docs-filesystem \
  --command 'rg -il "<关键词>" / | head -10' \
  --pretty
```

常用只读命令示例：

```bash
# 找相关文件
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/shulex-support/scripts/support.py query-docs-filesystem \
  --command 'rg -il "变量" / | head -10' \
  --pretty

# 读取某个文档开头
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/shulex-support/scripts/support.py query-docs-filesystem \
  --command 'sed -n "1,160p" /solvea/bot_cn/function-manual/agents/variables/variable-definition.mdx' \
  --pretty
```

基于文档回答时：

- 只使用 `search-docs` / `query-docs-filesystem` 返回的内容，不要编造文档里没有的信息。
- 如果文档结果不足以回答，直接说明文档中没有找到确定依据，再引导用户补充信息或提交工单。
- 回复末尾必须列出「参考文档」，使用命令返回的 `title` 和 `url`；没有 `url` 时只列 `page`，不要自行拼链接。
- 有 `url` 时使用 Markdown 链接格式，避免写成 `标题：URL`。

参考文档格式：

```text
参考文档：
- [<title>](<url>)
```
