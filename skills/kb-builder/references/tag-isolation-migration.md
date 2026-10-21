# 标签迁移与隔离关键词映射

标签与隔离关键词是两个独立概念。标签绑定知识使用 `editTags`；隔离关键词绑定知识使用隔离关键词批量接口。两者之间不能直接按字段或 ID 推断关系。

## 中间态文件

先生成：

```text
/workspace/state/kb-builder/tag_isolation_keyword_mapping.json
```

格式：

```json
{
  "mappings": [
    {
      "tag": "kb-test",
      "isolationKeyword": "product-a",
      "isolationKeywordId": 11,
      "matchType": "semantic",
      "status": "candidate",
      "reason": "kb-test 与 product-a 都表示该知识内容属于 product-a 产品的测试知识范围"
    }
  ]
}
```

- 文本完全一致时，`matchType` 为 `exact`。
- 文本不一致但语义匹配时，`matchType` 为 `semantic`，`reason` 只说明二者为什么匹配。
- 无法匹配或有歧义时，`status` 为 `unmatched`，不生成绑定项。
- `isolationKeywordId` 必须来自隔离关键词接口返回的真实 ID。

## 一次性迁移流程

1. 批量读取知识及顶层 `tags`：

   ```bash
   ${PLUGIN_ROOT}/bin/cxclaw-launcher api list-knowledge \
     --directory-id <directory_id> --type QA --include-tags --page-size 500 --pretty
   ```

   测试环境使用 `--env staging`，生产环境使用 `--env prod`。根据总数继续分页。
2. 读取项目标签定义：

   ```bash
   ${PLUGIN_ROOT}/bin/cxclaw-launcher api list-knowledge-tags --pretty
   ```
3. 读取隔离关键词文本和真实 ID：

   ```bash
   ${PLUGIN_ROOT}/bin/cxclaw-launcher api \
     list-isolation-keywords --all --page-size 500 --pretty
   ```
4. CX 根据完全一致或语义关系生成中间态映射文件，并按映射生成知识到 `keywordIds` 的绑定计划。
5. 一次性展示映射文件、未匹配项、歧义项及全部新增绑定；用户只确认这一次。
6. 确认后调用隔离关键词批量绑定接口，整个迁移过程中不再逐条确认。
7. 回读知识，验证 `isolationKeywords`。

标签本身如需写入知识，另行使用 `editTags`；该动作也应纳入同一份迁移计划和同一次确认。
