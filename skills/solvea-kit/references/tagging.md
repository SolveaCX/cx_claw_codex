# 标签树管理

这里对接的是 `tagSetting` 页面使用的标签树，用于维护标签组、标签节点，以及通过 Excel 批量初始化或更新标签。

注意：当前页面使用的是 `/api_v2/gpt/label/project/...` 这组接口；`/ai-tag/*` 是另一套标签能力，不在本流程内。

## API

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 标签组列表 | GET | `/api_v2/gpt/label/project/{pid}/getTreeInfo` | 获取标签组，返回 `id/treeName/treeDescribe/condition` |
| 创建/更新/删除标签组 | POST | `/api_v2/gpt/label/project/{pid}/updateTreeInfo` | body 用 `operateType=CREATE/UPDATE/DELETE` |
| 标签树 | GET | `/api_v2/gpt/label/project/{pid}/getTagTree` | 参数 `treeId` 必填，`name` 可选 |
| 标签详情 | POST | `/api_v2/gpt/label/project/{pid}/getDetailTree` | 支持 `nodeIds/nodeNames/parentIds` |
| 创建/更新/删除标签节点 | POST | `/api_v2/gpt/label/project/{pid}/updateNode` | body 用 `operateType=CREATE/UPDATE/DELETE` |
| 下载导入模板 | GET | `/api_v2/gpt/label/project/{pid}/downloadLabelTemplate` | 排查或人工编辑时使用，普通流程不用 |
| 下载当前标签 | GET | `/api_v2/gpt/label/project/{pid}/downloadLabel` | 用于导出现有标签，更新后再导入 |
| 批量导入标签 | POST | `/api_v2/gpt/label/project/{pid}/uploadLabel` | body 传 `treeId/file/uploadWay`；`file` 是上传到临时 S3 后的 key |

## CLI

### 标签组

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-label-groups --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-label-groups --name "Default" --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api create-label-group \
  --name "售后问题" --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api update-label-group --id <group_id> \
  --data-file /workspace/state/solvea-kit/label_group_update.json --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api delete-label-group --id <group_id> --pretty
```

`update-label-group` 的 data-file 示例：

```json
{
  "treeName": "售后问题",
  "treeDescribe": "",
  "condition": null,
  "isMultiTag": true
}
```

### 标签节点

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api get-label-tree \
  --tree-id <tree_id> --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api get-label-tree \
  --tree-id <tree_id> --name "退款" --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api get-label-detail-tree \
  --tree-id <tree_id> --node-ids <node_id> --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api create-label-node \
  --tree-id <tree_id> --name "退货退款" --content "用户咨询退货、退款、取消订单等售后问题" --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api update-label-node \
  --tree-id <tree_id> --id <node_id> \
  --data-file /workspace/state/solvea-kit/label_node_update.json --pretty

node "<PLUGIN_ROOT>/plugin-cli.mjs" api delete-label-node \
  --tree-id <tree_id> --id <node_id> --pretty
```

`create-label-node` / `update-label-node` 的 data-file 示例：

```json
{
  "nodeName": "退货退款",
  "describe": "用户咨询退货、退款、取消订单等售后问题",
  "parentId": 0,
  "isTag": true,
  "exampleList": [
    "How can I return my order?",
    "I want a refund."
  ]
}
```

`parentId=0` 表示一级标签。`isTag=false` 表示该节点不参与打标；关闭父节点时后端会影响子节点。

## 批量导入

主流程不是让用户下载模板手填。用户描述标签需求后，agent 应先整理标签树结构，写成 JSON，生成符合导入接口模板的 xlsx，再上传导入。

推荐流程：

1. 先 `list-label-groups` / `get-label-tree` 确认目标标签组是否为空、现有节点是什么。
2. 根据用户描述整理标签层级、描述、样例，写入 `/workspace/state/solvea-kit/labels.json`。
3. 用 `workflow label-import` 生成 xlsx。
4. 给用户展示将导入的层级摘要，确认后执行 `upload-labels`。

### 生成导入文件

空标签组初始化用 `--init`，JSON 示例：

```json
{
  "labels": [
    {
      "path": ["售后问题", "物流问题", "配送延迟"],
      "describe": "用户反馈包裹未按预计时间送达、配送时效过慢或物流长时间未更新。",
      "examples": [
        "My package is delayed.",
        "Tracking has not updated for several days."
      ]
    }
  ]
}
```

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" workflow label-import \
  --init \
  --input /workspace/state/solvea-kit/labels.json \
  --output /workspace/state/solvea-kit/labels_init.xlsx --pretty
```

已有标签更新或追加时，优先先 `download-labels` 导出现有标签，或 `get-label-tree` 查询节点 ID，再生成更新格式。JSON 示例：

```json
{
  "labels": [
    {
      "id": "",
      "name": "配送延迟",
      "describe": "用户反馈包裹未按预计时间送达、配送时效过慢或物流长时间未更新。",
      "parentId": 123456,
      "isTag": true,
      "examples": [
        "My package is delayed.",
        "Tracking has not updated for several days."
      ],
      "path": "售后问题/物流问题/配送延迟"
    }
  ]
}
```

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" workflow label-import \
  --input /workspace/state/solvea-kit/labels.json \
  --output /workspace/state/solvea-kit/labels_update.xlsx --pretty
```

### 上传导入

空标签组初始化：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api upload-labels \
  --tree-id <tree_id> \
  --file /workspace/state/solvea-kit/labels_init.xlsx \
  --init --pretty
```

已有标签更新：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api upload-labels \
  --tree-id <tree_id> \
  --file /workspace/state/solvea-kit/labels_update.xlsx --pretty
```

### 模板下载（排查用）

一般不需要让用户下载模板。只有在核对线上模板变化、排查导入失败，或需要人工离线编辑时才下载。普通场景直接用上面的生成脚本。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api download-label-template \
  --template-type update \
  --output /workspace/state/solvea-kit/label_template.xlsx --pretty
```

更新已有标签时，优先先导出现有标签，在导出的 xlsx 上修改：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api download-labels \
  --tree-id <tree_id> \
  --output /workspace/state/solvea-kit/current_labels.xlsx --pretty
```

## Excel 模板口径

当前标签导出 / 更新格式：

| 列 | 含义 |
|---|---|
| `id` | 已有节点 ID；为空表示新增标签 |
| `name` | 标签名称，不能为空；同一 parent 下不能重复 |
| `describe` | 标签描述，供模型理解标签含义 |
| `example1` ~ `example5` | 样例表达 |
| `is_tag` | `1` 参与打标，`0` 不参与打标；为空按 `1` |
| `level` | 展示字段，更新时主要依赖 `parent_id` |
| `parent_id` | 父节点 ID；一级标签填 `0` 或空 |
| `path` | 展示字段，便于人工核对路径 |

初始化格式：

| 列 | 含义 |
|---|---|
| `first_level` | 一级标签，不能为空 |
| `second_level` | 二级标签，可空 |
| `third_level` | 三级标签，可空 |
| `fourth_level` | 四级标签，可空 |
| `describe` | 叶子标签描述 |
| `example1` ~ `example5` | 样例表达 |

后端限制：

- Excel 空数据会失败。
- 最多支持 2000 个标签，超过会失败。
- `id` / `parent_id` 必须是数字或空。
- `id` 必须属于当前租户项目已有节点；`parent_id` 必须存在。
- 同一父节点下的 `name` 不能重复。
- 普通更新模板要求至少 12 列。

## 操作原则

- 新增或更新前，先 `list-label-groups` / `get-label-tree` 确认现状。
- 删除标签组或标签节点前，先展示将删除的对象，并得到用户明确确认。
- 批量导入前先基于用户描述整理结构化 JSON，再生成 xlsx；不要让用户手填模板。
- 更新已有标签时，先查现有树或导出现有标签，避免 parentId / id 写错。
- 批量导入文件放 `/workspace/state/solvea-kit/`，先说明影响范围，再执行 `upload-labels`。
- 标签分析、分布报表、AI 测试不属于本页基础管理能力；需要时走分析类能力单独处理。
