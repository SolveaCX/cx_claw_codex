# 知识导出

把 Shulex 知识库导出成带目录路径的 Excel。核心原则：优先调用 `scripts/export_knowledge.py` 完成目录读取、分页拉取、目录 join 和 Excel 写入；不要让模型临时手写分页脚本或 Excel 生成逻辑。

脚本内部会读取 `list-directories` 的完整目录树，并用每条知识的 `directoryId` 精确 join 目录路径。禁止用 question 前缀、关键词、型号名等方式猜目录。

## 适用入口

用户提到以下诉求时使用本 reference：

- 导出知识 / 导出知识库
- 带目录导出
- 按目录导出一部分知识
- 导出当前 KB 供客户审阅 / 迁移 / 备份

## 数据来源

### 1. 目录树

先读取完整目录树：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-directories --pretty
```

`list-directories` 对应前端接口：

```text
GET /api_v2/qam/project/{projectId}/directories?keyword=&kuPublished=
```

响应里的 `list` 已经是完整树，不需要逐级再查。需要保留所有节点，包括 `kuCount=0` 的目录，因为它可能是父目录或暂时为空的目录。

把目录树 flatten 成两张索引：

- `directory_id -> node`
- `directory_id -> path_names`

例如：

```text
100327 -> ["Product Category", "Calendar Machine", "A1"]
82769  -> ["Product Category", "Tablet", "Tablet General"]
```

### 2. 知识列表

查询知识：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-knowledge \
  --type ALL \
  --page-size 1000 \
  --page 1 \
  --pretty
```

指定目录查询：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-knowledge \
  --type ALL \
  --directory-id 105809 \
  --page-size 1000 \
  --page 1 \
  --pretty
```

`list-knowledge` 对应前端接口：

```text
POST /api_v2/qam/project/{projectId}/getKnowledge
```

请求体示例：

```json
{
  "type": "ALL",
  "pageIndex": 1,
  "pageSize": 50,
  "directoryId": 105809,
  "keyword": ""
}
```

每条知识必须使用返回的 `directoryId` 去目录索引里查路径。不要从 `question` / `answer` / `title` 里推断目录。

## 脚本调用

⚠️ 默认不要直接导出。`导出知识库`、`导出知识`、`帮我导出 KB` 这类说法只表示用户要进入导出流程，不表示导出全部。

### 全量导出

只有用户明确说了“全部 / 全量 / 所有 / 整个知识库 / 当前知识库全部 / all / everything”时，才直接执行全量导出：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py --all
```

### 指定目录导出

用户指定一个目录时：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py --directory-id 105809
```

默认会包含该目录及其所有子孙目录。

只导出目录自身、不包含子目录时：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py --directory-id 105809 --no-children
```

### 多目录导出

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py \
  --directory-id 105809 \
  --directory-id 82764
```

脚本会按 KU ID 去重。

### keyword 过滤

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py \
  --directory-id 105809 \
  --keyword battery
```

### 指定知识类型

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py --all --type QA
```

`--type` 默认为 `ALL`，可按接口支持传 `QA / FILE / WEBSITE / PRODUCT / LEARN_SELF / ALL`。

## 和用户确认导出范围

默认先用 `list-directories` 拉目录树，向用户展示可选目录，至少包含：

- 目录 id
- 完整路径
- `kuCount`

询问用户导出范围：

```text
我看到了当前目录树。你希望导出哪一部分？
- 全部知识库
- 某个目录及其子目录，例如 Product Category / Tablet
- 多个目录
- 按 keyword 过滤后导出
```

只有用户已经明确“全部 / 全量 / 所有 / 整个知识库 / 当前知识库全部 / all / everything”时，不需要再问，直接运行：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/export_knowledge.py --all
```

反例：用户只说“导出知识库”或“导出知识”，必须先列目录并询问范围，不能直接按全量处理。

## 拉取策略

### 全量导出

脚本内部不会遍历所有目录。它直接不传 `directoryId`，按页拉全量知识：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-knowledge --type ALL --page-size 1000 --page 1 --pretty
```

第一页读取 `total`，继续翻页直到拉完。

### 指定单个父目录导出

脚本内部会先从目录树展开该目录的所有子孙目录 id，包含父目录自身。然后按目录逐个分页拉取：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-knowledge \
  --type ALL \
  --directory-id <dir_id> \
  --page-size 1000 \
  --page 1 \
  --pretty
```

父目录导出时，目录树里的 `kuCount` 通常是子树汇总。若选中目录子孙很多，或者 `kuCount` 接近全量，可以提示用户“这个范围接近全量，是否直接导出全量”。

### 多目录导出

脚本内部会对每个选中目录重复“展开子孙目录 id + 分页拉取”。同一条知识如果被多个父目录覆盖，按 `id` 去重。

### keyword 导出

把 `--keyword` 和可选 `--directory-id` 组合使用。脚本仍然用返回的 `directoryId` join 目录路径，不会用 keyword 推断目录。

## Excel 结构

默认生成一个 Sheet，名字建议 `Knowledge Base`。目录已经由 Level 列清晰表达，不要默认按一级目录拆多个 Sheet。

表头的目录层级列必须动态生成，不能硬编码 `Level 1/2/3`。先根据本次导出范围内实际出现的目录路径计算最大深度 `N`，然后生成：

```text
Level 1, Level 2, ..., Level N, Question, Answer, KU ID, Type, Status
```

如果某条知识路径短于 `N`，后面的 Level 列留空。

示例：

```text
Product Category / Tablet / C107 / Firmware
```

对应：

```text
Level 1 = Product Category
Level 2 = Tablet
Level 3 = C107
Level 4 = Firmware
```

建议额外保留这些列：

- `KU ID`
- `Type`
- `Status`
- `Directory ID`（排查用，建议放在最后）

如果用户明确要求“按一级目录拆 Sheet”或“每个目录一个 Sheet”，才拆 Sheet；拆 Sheet 时也必须保留完整 Level 列。

## 输出路径

最终 Excel 写到：

```text
/workspace/outputs/kb-builder/kb_export_<timestamp>.xlsx
```

中间 JSON、目录索引、分页结果写到：

```text
/workspace/tmp/kb-builder/export/
```

不要把中间分页数据写到 outputs，避免输出给用户。

## 汇报格式

导出完成后向用户说明：

```text
已导出 X 条知识到 /workspace/outputs/kb-builder/kb_export_<timestamp>.xlsx

范围：
- 全部知识库 / 指定目录 ...

目录统计：
- Product Category / Tablet: N 条
- Product Category / Frame: N 条
- Uncategorized: N 条

说明：
- 目录来自 directoryId 精确匹配
- 没有 directoryId 或目录已不存在的知识会放到 Unknown Directory
```

## 禁止事项

- 禁止用 question 前缀、型号名、关键词匹配目录。
- 禁止固定只输出 `Level 1/2/3`。
- 禁止默认拆多个 Sheet。
- 禁止把 `list-directories` 里的 `kuCount=0` 目录删除后再建索引。
- 禁止只导出 KU ID 而丢掉 question / answer / directoryId。
