# 知识读取、更新与状态管理

## 列表与详情的类型边界

知识列表统一使用 `list-knowledge` / `getKnowledge`。后端返回同一套列表结构，但不同界面类型填充的字段不同：

- 问答 / AI自学习：主要是 `question`、`answer`
- 文档：主要是 `name`、`title`、`storageSize`
- 网页：主要是 `name`、`title`、`url`
- 产品：主要是 `productTitle`、`productId`、`sku`、`spuUrl` 等商品字段

每条列表记录都使用统一的 `knowledgeId`、`directoryId`、`type`、`knowledgeStatus`、`isolationKeywords`。必须保留并使用记录返回的类型，不能只拿 ID 猜实体。

详情接口按实体拆分：问答/AI自学习走 KU，文档/网页走 DOCUMENT，产品走 KU_PRODUCT。统一 CLI 用 `--type` 选择正确详情接口；这里的内部实体名只用于实现判断，不用于客户话术。

## 读取

已知知识 ID 时读取准确详情，不用关键词列表代替：

QA / AI自学习知识：

```bash
npx --yes @shulex/cxclawctl@latest api get-knowledge --id 3057821 --type QA --pretty
```

文档 / 网页知识使用同一个业务入口，但必须带对应类型；脚本会调用文档详情接口，而不是 QA 的详情接口：

```bash
npx --yes @shulex/cxclawctl@latest api get-knowledge --id 3057821 --type FILE --pretty
npx --yes @shulex/cxclawctl@latest api get-knowledge --id 3057821 --type WEBSITE --pretty
```

产品知识：

```bash
npx --yes @shulex/cxclawctl@latest api get-knowledge --id 3057821 --type PRODUCT --pretty
```

## 更新问答 / AI自学习知识

当前 `update-knowledge` 对应 KU 更新接口，不用于文档、网页或产品。文档/网页内容更新需要文档更新原子能力，不能拿本命令代替。

1. 先读取当前知识，确认 ID、标题、内容和目录。
2. 只把要修改的字段写入稳定文件 `/workspace/state/kb-builder/knowledge_update.json`。
3. 向用户展示字段级变更，等待明确确认。
4. 确认后执行：

```bash
npx --yes @shulex/cxclawctl@latest api update-knowledge --id 3057821 --data-file /workspace/state/kb-builder/knowledge_update.json --pretty
```

5. 再次读取同一 ID，核对实际结果。

更新文件支持 `title`、`content`、`published`、`directoryId`、`status`、`forceIndex`。仅写需要修改的字段；除非明确需要重建或删除索引，不要设置 `forceIndex`。

### 批量更新问答正文 / 标题

当需要修改多条问答知识时，严禁使用循环单条 `update-knowledge`，应使用批量更新命令 `batch-update-knowledge`。

将待修改列表写入 `/workspace/state/kb-builder/batch_knowledge_update.json`：

```json
[
  {
    "kuId": 3057821,
    "content": "修改后的答案正文",
    "directoryId": 145177
  },
  {
    "kuId": 3057822,
    "content": "修改后的答案正文",
    "directoryId": 145178
  }
]
```

执行批量更新：

```bash
npx --yes @shulex/cxclawctl@latest api batch-update-knowledge --data-file /workspace/state/kb-builder/batch_knowledge_update.json --pretty
```

- 每条记录支持 `kuId`（或 `id`）、`title`、`content`、`directoryId`、`published` 等字段。
- 建议优先带上扫描时已获取的 `directoryId`；若未带 `directoryId`，CLI 会自动向后兼容继承原目录。
- 批量更新建议单批 50~100 条。

## 更新文档 / 网页正文

文档和网页共用同一个正文更新入口。CLI 会先读取当前详情，保留目录、文件名和元数据，再合并本次变更；不要用 `update-knowledge` 更新这两类知识。

将新正文写入 `/workspace/state/kb-builder/document_update.json`：

```json
{
  "fileText": "更新后的 Markdown 或文本正文",
  "title": "可选的新标题"
}
```

展示变更摘要并获得确认后执行：

```bash
# 文档
npx --yes @shulex/cxclawctl@latest api update-document-content --id 3057821 --type FILE --data-file /workspace/state/kb-builder/document_update.json --pretty

# 网页
npx --yes @shulex/cxclawctl@latest api update-document-content --id 3057821 --type WEBSITE --data-file /workspace/state/kb-builder/document_update.json --pretty
```

更新后用原类型重新读取详情。`filePath` 仅用于已上传的新 Markdown 文件；普通正文修改使用 `fileText`。

## 删除、移动、发布状态与可见性

这些操作支持界面上的五类知识。对客户只说“问答 / AI自学习 / 文档 / 网页 / 产品”；下表字段仅用于脚本计划文件：

| 界面操作 | `operateType` |
|---|---|
| 删除 | `DELETE` |
| 移动到目录 | `MOVE`，同时传 `directoryId` |
| 发布 | `PUBLISH` |
| 下架 | `UNPUBLISH` |
| 显示 | `VISIBLE` |
| 隐藏 | `INVISIBLE` |

计划文件 `/workspace/state/kb-builder/knowledge_operations.json` 是 JSON 数组：

```json
[
  {"knowledgeType": "FILE", "knowledgeId": 3057821, "operateType": "MOVE", "directoryId": 32188},
  {"knowledgeType": "WEBSITE", "knowledgeId": 3057822, "operateType": "UNPUBLISH"},
  {"knowledgeType": "PRODUCT", "knowledgeId": 3057823, "operateType": "INVISIBLE"}
]
```

执行前必须：

1. 用 `get-knowledge --id ... --type ...` 读取每个目标，确认 ID 和界面类型一致。
2. 删除要列出具体标题和数量；移动要列出原目录和目标目录；状态变更要列出变更前后。
3. 等待用户明确确认。不得把“查看一下”视为删除或状态变更授权。

删除操作需要更强确认：展示影响后，要求用户明确回复“我已知晓删除影响并确认删除”或语义等价、同时包含“知晓影响”和“确认删除”的表达。英文用户可回复 `I understand the deletion impact and confirm deletion.`。只回复“确认”、`OK` 或“可以”不足以授权删除。

确认后执行：

```bash
# 非删除操作
npx --yes @shulex/cxclawctl@latest api operate-knowledge --data-file /workspace/state/kb-builder/knowledge_operations.json --pretty

# 计划中包含删除时，仅在收到上述强确认后增加
npx --yes @shulex/cxclawctl@latest api operate-knowledge --data-file /workspace/state/kb-builder/knowledge_operations.json --confirm-delete --pretty
```

CLI 会再次按类型读取每个目标，移动时还会确认目标目录存在，然后一次提交。提交后重新查询：删除要确认记录已不存在，其他操作要核对目录、发布状态或可见性。
