# 回复模板库管理

优先用 `/skill-lib/solvea-api/solvea_api.py` 管理模板；用户上传 Excel / CSV 批量导入时，用 `scripts/import_templates.py`。

## 能力清单

| 用户要做什么 | 使用方式 | 是否需要确认 | 输出 / 结果 |
|--------------|----------|--------------|-------------|
| 查模板 | `list-templates` | 否 | 返回 `id/name/content/status/scene` |
| 创建单条模板 | `create-template` | 是 | 返回新模板 `id` |
| 修改单条模板（改名 / 内容 / 状态） | `update-template --id ...` | 是 | 返回更新后的模板 |
| 批量导入模板 | `import_templates.py --dry-run` → 用户确认 → 正式导入 | 是 | dry-run 生成 `template_import_plan_*`；正式导入生成 `template_import_result_*` |
| 保留首条并跳过重复名 | `import_templates.py --skip-duplicates` | 是 | `skipped_duplicates` 记录被跳过的行 |
| 删除模板 | `delete-templates --ids ... --confirm-delete` | 是，必须确认模板名称和 id | 按 id 删除 |
| 单条发布 / 下架 | `update-template --id ... --status ENABLED/DISABLED` | 是 | 改单条模板状态 |
| 批量发布 / 下架 | 暂无批量 CLI | 是 | 单条走 `update-template`；批量走前端“批量更新” |

## 管理 CLI

所有命令都走：

```bash
cxclawctl api <command> [args]
```

### `list-templates`

查询模板库。只读，可直接执行。

| 参数 | 必填 | 说明 |
|------|------|------|
| `--keyword` | 否 | 按模板名 / 内容关键字查询；传数字时也可用于定位 id |
| `--status` | 否 | 状态过滤，如 `ENABLED` / `DISABLED` |
| `--scene` | 否 | 场景过滤；可重复传。普通模板一般不传，语音短信模板传 `voice_sms` |
| `--page` | 否 | 页码，默认 `1` |
| `--page-size` | 否 | 每页数量，默认 `50` |
| `--pretty` | 否 | 格式化输出，排查时建议加 |

```bash
cxclawctl api list-templates \
  --keyword "广告" --page-size 20 --pretty
```

### `create-template`

创建单条模板。执行前先向用户确认模板名称和内容。

| 参数 | 必填 | 说明 |
|------|------|------|
| `--name` | 是，除非用 `--data-file` | 模板名称，项目内必须唯一 |
| `--content` | 是，除非用 `--data-file` | 默认回复内容 |
| `--status` | 否 | 模板状态；不传时后端默认 `ENABLED` |
| `--scene` | 否 | 模板场景；普通模板不传，语音短信模板传 `voice_sms` |
| `--data` | 否 | JSON 字符串；适合传 `multiContent` 等复杂字段 |
| `--data-file` | 否 | JSON 文件路径；适合复杂模板 |
| `--pretty` | 否 | 格式化输出 |

```bash
cxclawctl api create-template \
  --name "广告关闭" \
  --content "您好，您可以在APP右下角“我的”里关闭广告。" \
  --status ENABLED \
  --pretty
```

复杂模板用 JSON：

```json
{
  "name": "广告关闭",
  "content": "您好，您可以在APP右下角“我的”里关闭广告。",
  "status": "ENABLED",
  "multiContent": {
    "AUTO": "您好，您可以在APP右下角“我的”里关闭广告。"
  }
}
```

### `update-template`

修改单条已有模板，**部分更新**：只传要改的字段，未传的保持不变。执行前先向用户确认改哪条、改成什么。

| 参数 | 必填 | 说明 |
|------|------|------|
| `--id` | 是 | 要修改的模板 id（templateId） |
| `--name` | 否 | 新模板名；项目内唯一，撞名会报 `template name is already existed` |
| `--content` | 否 | 新默认回复内容；后端会自动同步到 `multiContent.AUTO` |
| `--status` | 否 | `ENABLED` / `DISABLED` |
| `--data` / `--data-file` | 否 | JSON；传 `multiContent` 等多语种字段 |
| `--pretty` | 否 | 格式化输出 |

至少要传一个可改字段（`--name` / `--content` / `--status` / `multiContent`），否则报错。

```bash
# 下架
cxclawctl api update-template --id 12008 --status DISABLED

# 改名 + 内容
cxclawctl api update-template \
  --id 12008 --name "转人工" --content "<p>这是转人工的模版文案</p>" --pretty
```

多语种内容用 JSON（`--data` / `--data-file`）：

```json
{ "multiContent": { "AUTO": "<p>…</p>", "ENGLISH": "<p>…</p>" } }
```

### `delete-templates`

按 id 批量删除模板。删除前必须向用户展示模板名称和 id，并要求回复“我已知晓删除影响并确认删除”或等价强确认。

| 参数 | 必填 | 说明 |
|------|------|------|
| `--ids` | 是，除非用 `--data-file` | 要删除的模板 id 列表 |
| `--data` | 否 | JSON 字符串，格式为 `{"templateIds":[123,124]}` 或 `{"ids":[123,124]}` |
| `--data-file` | 否 | JSON 文件路径 |

```bash
cxclawctl api delete-templates --ids 123 124 125 --confirm-delete
```

## 批量导入脚本

脚本路径：

```bash
python3 /skills/kb-builder/scripts/import_templates.py [args]
```

### Excel / CSV 列

| 列 | 必填 | 说明 | 兼容表头 |
|----|------|------|----------|
| `name` | 是 | 模板名称，必须唯一 | `模板名称` / `模板名` / `模版名称` / `模版名` / `名称` / `标题` / `主题` |
| `content` | 是 | 默认回复内容 | `模板内容` / `模版内容` / `回复内容` / `回复话术` / `话术` / `答案` / `内容` |
| `status` | 否 | 模板状态，默认 `ENABLED` | `状态` / `发布状态` |
| `scene` | 否 | 普通模板留空；语音短信模板填 `voice_sms` | `场景` / `适用场景` |
| `AUTO` | 否 | 默认语言内容；为空时自动使用 `content` | `AUTO` |
| 其他语言列 | 否 | 多语言内容，如 `ENGLISH` / `CHINESE` / `JAPANESE` | 需使用脚本支持的语言枚举 |

### 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--xlsx` | 二选一 | Excel / CSV 文件路径，支持 `.xlsx` / `.xlsm` / `.csv` |
| `--plan-file` | 二选一 | 已确认的 `template_import_plan_*.json` 路径；正式导入优先用它，避免跨轮依赖临时 Excel |
| `--sheet` | 否 | Excel sheet 名；不传用第一个 sheet |
| `--name-col` | 否 | 指定模板名称列；表头不标准时必传 |
| `--content-col` | 否 | 指定模板内容列；表头不标准时必传 |
| `--status-col` | 否 | 指定状态列 |
| `--scene-col` | 否 | 指定场景列 |
| `--lang-col` | 否 | 指定多语言列，可重复传，格式 `LANGUAGE=列名`，如 `CHINESE=中文话术` |
| `--skip-duplicates` | 否 | 文件内模板名重复时保留第一条，跳过后续同名行；结果写入 `skipped_duplicates` |
| `--dry-run` | 否 | 只解析并生成导入计划，不创建模板 |

`--xlsx` 和 `--plan-file` 二选一。dry-run 阶段通常用 `--xlsx`；正式导入阶段优先用 `--plan-file`。

## 标准流程

1. 先读用户文件表头和样例：

   ```text
   read_file(file_path="/mounted/chat-files/user/templates.xlsx", limit=20)
   ```

2. 先 dry-run：

   ```bash
   python3 /skills/kb-builder/scripts/import_templates.py \
     --xlsx /mounted/chat-files/user/templates.xlsx \
     --dry-run
   ```

   表头不标准时显式传列名：

   ```bash
   python3 /skills/kb-builder/scripts/import_templates.py \
     --xlsx /mounted/chat-files/user/templates.xlsx \
     --name-col "Topic" \
     --content-col "Message" \
     --scene-col "Usage" \
     --lang-col "CHINESE=中文话术" \
     --dry-run
   ```

   如果确实需要临时处理用户文件，例如手工去重、改列、清洗内容：可以把处理后的文件写到 `/workspace/tmp` 供本轮 dry-run 使用，但用户确认后不能再依赖这个 tmp 文件。跨轮稳定输入是 dry-run 生成的 `template_import_plan_*`。

   用户要求跳过重复模板名时，可以用脚本参数生成最终 plan：

   ```bash
   python3 /skills/kb-builder/scripts/import_templates.py \
     --xlsx /mounted/chat-files/user/templates.xlsx \
     --name-col "快捷词" \
     --content-col "回复内容" \
     --skip-duplicates \
     --dry-run
   ```

3. 向用户汇报解析数量和计划文件，等待明确确认：

   ```text
   已解析 X 条模板，计划文件：
   /workspace/outputs/kb-builder/template_import_plan_<ts>.json

   确认上传到模板库吗？
   ```

4. 用户明确回复“确认 / 上传吧 / 没问题”后，用已确认的 plan 正式导入：

   ```bash
   python3 /skills/kb-builder/scripts/import_templates.py \
     --plan-file /workspace/outputs/kb-builder/template_import_plan_<ts>.json
   ```

   正式导入输出：

   ```text
   /workspace/outputs/kb-builder/template_import_result_<ts>.json
   ```

   结果文件包含 `created_items`：

   ```json
   [{"id": 123, "name": "Warranty reply"}]
   ```

## 规则

- 查询模板可直接执行；创建、修改、正式批量导入、删除前必须等用户明确确认。
- `update-template` 是部分更新：只改传入字段，未传字段不变；改名同样受“名称唯一”校验；改单条状态（上架 / 下架）用 `update-template --status`，无需依赖前端。
- 删除模板前必须展示并确认模板名称和 id。
- 后端校验模板名唯一；脚本不会覆盖已有模板。
- Excel 导入没有后端批量创建接口，脚本会逐行调用单条创建接口。
- 正式导入不会生成新的 import plan，只生成 import result。
- 跨轮不要依赖 `/workspace/tmp` 临时文件；正式导入应使用 dry-run 生成的 `template_import_plan_*`。
- plan 是用户确认的导入内容快照；正式导入不要重新解析 Excel，避免文件消失、表头参数不一致或临时处理丢失。
