# 隔离关键词管理

隔离关键词用于控制知识命中时的隔离条件。关键词资源和绑定关系分开管理；所有写入都必须先向用户展示变更并取得明确确认。

## 接口

接口前缀由 `SolveaClient` 根据环境自动选择：

```text
prod     /api_v2/qam
staging  /sns_v1
```

项目 ID 使用当前 `projectId`。

| 能力 | 方法与路径 | 请求/参数 |
|------|------------|-----------|
| 搜索/查询 | `GET /project/{projectId}/isolation_keywords` | `keyword`、`pageIndex`、`pageSize` |
| 创建 | `POST /project/{projectId}/isolation_keyword` | `{ "keyword": "hihi,oo" }`；逗号分隔输入会拆成多个关键词 |
| 修改 | `POST /project/{projectId}/isolation_keyword/{id}` | `{ "keyword": "new-value" }` |
| 删除 | `DELETE /project/{projectId}/isolation_keyword/{id}` | 无请求体 |
| 绑定/解绑 | `POST /project/{projectId}/knowledge/isolation_keywords/batch` | 见下文 |

对应公开 CLI：

```bash
cxclawctl api list-isolation-keywords --keyword "invoice" --pretty
cxclawctl api create-isolation-keyword --keyword "invoice,test" --pretty
cxclawctl api update-isolation-keyword --id 17 --keyword "0226" --pretty
cxclawctl api delete-isolation-keyword --id 16 --confirm-delete --pretty
cxclawctl api get-knowledge-isolation-keywords \
  --id 486955 --type FILE --pretty
cxclawctl api batch-update-isolation-keyword-bindings \
  --data-file /workspace/state/kb-builder/isolation_keyword_binding.json --pretty
```

批量绑定命令的 JSON 文件在接口结构 `items`、`directoryIds`、`keywordIds` 之外，使用 `operation` 声明业务操作：`append`（追加）、`remove`（移除）或 `replace`（替换）。知识级操作省略时默认为 `append`。

查询结果通常是数组，每项包含：

```text
id / keyword / bindCount / projectId / tenantId / createdAt / updatedAt
```

创建结果包含 `duplicate`、`failed`、`success`；成功项包含 `keyword` 和 `rowNo`。删除和批量绑定接口成功时通常返回 `ok`。

## 绑定请求

CLI 计划中的 `knowledgeType` 使用知识列表返回的界面类型：`QA`、`LEARN_SELF`、`FILE`、`WEBSITE` 或 `PRODUCT`。client 会按最新后端契约转换绑定类型：问答和 AI自学习 → `QA`，文档和网页 → `DOCUMENT`，产品 → `PRODUCT`。Agent 不要自行把列表类型改成后端类型，也不向客户暴露这些内部值。

具体知识级绑定：

```json
{
  "operation": "append",
  "items": [
    {
      "knowledgeType": "QA",
      "knowledgeId": 486955,
      "keywordIds": [11, 13]
    }
  ],
  "directoryIds": [],
  "keywordIds": [11, 13]
}
```

目录级绑定：

```json
{
  "operation": "replace",
  "confirmReplace": true,
  "items": [],
  "directoryIds": [32951],
  "keywordIds": [11, 13]
}
```

`directoryIds`、`items`、`keywordIds` 都可以省略；但三者同时为空时不得调用接口。一次请求只处理一种目标：`items` 或 `directoryIds` 二选一，避免目录级和知识级语义混淆。client 会拒绝空更新、校验 ID、并对数组去重。

后端绑定接口始终把提交的关键词 ID 当作最终集合，会先删除旧关系再写入新关系。CLI 对具体知识会自动读取现有绑定并按 `operation` 计算最终集合；读取失败时停止，不得猜测。目录级接口不能安全读取和合并目录内每条知识的现状，因此只允许显式 `replace`，并要求 `confirmReplace: true`。

## 绑定与解绑流程

1. 用 `list_isolation_keywords` 搜索关键词，确认目标关键词 ID；不存在时先创建。
2. 绑定目录前用 `list-directories` 获取真实 `directoryId`，不要根据目录名称猜 ID。
3. 绑定具体知识前用 `list-knowledge` 获取 `knowledgeId` 和类型，再用带 `--type` 的 `get-knowledge` 读取详情。
4. 追加使用 `operation: "append"`，移除使用 `operation: "remove"`；两者都由 CLI 读取当前关系并计算最终集合。只有用户明确要求覆盖全部绑定时才使用 `operation: "replace"` 和 `confirmReplace: true`。
5. 展示变更差异并取得用户明确确认后调用 `batch_update_isolation_keyword_bindings` 提交；没有现状快照不得提交。
6. 调用 `get-knowledge-isolation-keywords --id ... --type ...` 回读绑定结果；结果不符合预期时停止，不自动覆盖重试。

不要把关键词文本直接当作 `keywordIds`；绑定接口要求使用隔离关键词的数字 ID。目录绑定和知识绑定都必须保留目标对象的真实 ID。

## 创建关键词前的查重

用户要求新建关键词时，禁止直接调用创建接口。必须先执行：

1. 用 `list_isolation_keywords` 分页拉取当前项目的关键词（需要全量查重时按 `totalCount` / 分页结果继续查询）。
2. 将用户输入按逗号拆分、去除首尾空格并在本次输入内去重。
3. 与现有关键词按规范化后的精确文本匹配；把已存在的关键词单独列出并告知用户，不重复提交。
4. 只对不存在的关键词发起创建，并在写入前向用户展示待创建清单、重复清单和失败风险，取得明确确认。
5. 根据创建响应的 `success`、`duplicate`、`failed` 汇报结果；创建失败的项不得自动重试或改名。

如果所有输入都已存在，不调用创建接口，只告知用户现有关键词及其 ID，并继续询问是否需要绑定。

## 用户交互要求

- 用户说“建立隔离关键词 xxx”时，先解析并去重关键词，再展示将创建的列表。
- 新建前必须先查询当前关键词并查重；重复项要明确告知用户，只创建不存在的项。
- 创建完成后，询问是否绑定到某个知识目录；用户明确说不绑定时，仅创建关键词。
- 用户指定目录名时，先查询目录树并展示匹配目录，确认后再绑定。
- 删除关键词前检查 `bindCount`，提示可能影响的知识/目录；要求用户回复“我已知晓删除影响并确认删除”或等价强确认，然后才能使用 `--confirm-delete`。
