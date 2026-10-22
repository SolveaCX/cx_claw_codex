# 从历史工单 xlsx 提取 QA

→ 通用质量规则见 `/skills/kb-builder/references/qa-quality.md`（必读）

工单原始对话含有噪声（情绪语言、订单号、客服套话），不能直接粘贴进知识库。流程：读表头样例 → 判断数据源列 → dry-run → 分页/并发提炼到 state → 汇总去重到 outputs → 用户确认后再 dry-run 上传。

## 步骤一：检测 xlsx 格式

**直接 `read_file` 读 xlsx**，不要 inline `python3 -c "import pandas..."`。read_file 工具内部用 markitdown 把 xlsx 转成 markdown 表格：

- 每个 sheet 输出一段 `## SheetName` + 列名表头 + 数据行
- 直接看到列名、行数（看返回的 `lines X-Y of N`）、前几行内容样例
- 同一份 xlsx 同轮内缓存到 `workspace/tmp/parsed/`，重复读不会重新解析
- 单 cell 超过 500 字符会被截断（middleware 层 `_MAX_LINE_CHARS`），看格式 / 列名足够；长对话原文走 `extract_ticket_qa.py` 全量提炼时再处理

```
read_file(file_path="/mounted/chat-files/user/tickets.xlsx", limit=20)
```

返回示例：

```
File: tickets.xlsx (lines 1-20 of 532)

## Sheet1
| conversation_id | customer_message | agent_reply |
| --- | --- | --- |
| T001 | my charger broke | please send photos of the damaged item |
| T002 | battery drains fast | check motion sensitivity in app settings |
...
```

⚠️ 同样有 ~32K chars 上限。检测列名只读前 20 行就够，不要全文加载。

| 格式 | 特征 | 处理方式 |
|------|------|----------|
| **Shulex 导出** | 有 `conversations` 列 | 直接解析对话序列 |
| **自定义系统导出** | 列名不固定 | 自动检测问题列 / 回复列 |

## 步骤二：判断数据源列

先根据表头和前几行判断真实客诉对话列，像 POC / Delivery 分类脚本一样显式传给脚本：

| 参数 | 用途 | 常见列名 |
|------|------|----------|
| `--messages-col` | 完整对话列；或客户问题列 | `conversations` / `messages` / `comments_json` / `conversation` / `聊天记录` / `对话内容` / `customer_message` |
| `--title-col` | 工单标题 / 主题（可选） | `subject` / `title` / `主题` / `工单标题` |
| `--reply-col` | 客服回复列（仅问答分列时传） | `agent_reply` / `reply` / `answer` / `客服回复` |

如果无法判断哪列是真实客诉对话，不要直接跑提取；先问用户确认列名。

脚本保留自动检测兜底，但 agent 应优先显式传列名。

## 步骤三：dry-run 确认提取逻辑

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/extract_ticket_qa.py \
  --xlsx /mounted/chat-files/user/tickets.xlsx --brand "{品牌名称}" \
  --messages-col conversations --title-col subject \
  --page 1 --page-size 100 --batch-size 5 --workers 3 --dry-run
```

dry-run 必须检查：

- `[detect]` 里的 `messages_col` / `reply_col` / `title_col` 是否符合表头判断
- sample thread 是否是真实客诉对话
- `Would call model=<模型> X times` 是否合理

## 步骤四：批量分页运行提炼（OpenAI-compatible 模型）

历史工单必须分页处理，避免单轮超过 20 分钟 SSE 上限。`page` 从 1 开始，`page-size` 最大 100。

推荐优先用批处理 wrapper，一次处理完整 xlsx，但内部仍按页跑：

```bash
# 全表分页提取：每页 100 行，页内每 5 条对话一次模型调用，并发 3 个 batch
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/batch_extract_ticket_qa.py \
  --xlsx /mounted/chat-files/user/tickets.xlsx --brand "{品牌名称}" \
  --messages-col conversations --title-col subject \
  --page-size 100 --batch-size 5 --workers 3 --resume
```

wrapper 行为：

- 每页产物写入 `/workspace/state/kb-builder/ticket_extract/pages/page_001.json`
- 进度写入 `/workspace/state/kb-builder/ticket_extract/progress.json`
- 失败后可用同一命令 `--resume` 续跑，已完成 page 会跳过
- 最终合并、过滤、去重后输出 `/workspace/outputs/kb-builder/ticket_qa_merged_<ts>.json`
- **不会上传知识**

必要时也可以只跑单页 worker（调试或补页）：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/extract_ticket_qa.py \
  --xlsx /mounted/chat-files/user/tickets.xlsx --brand "{品牌名称}" \
  --messages-col conversations --title-col subject \
  --page 2 --page-size 100 --batch-size 5 --workers 3
```

## 步骤五：用户确认后再上传

批处理完成后，先向用户展示：

- 总行数 / 完成页 / 失败页
- 模型调用数 / 提取数 / 过滤数 / 去重数
- merged 输出文件路径
- 3-5 条样例 QA

用户确认后，再按 upload.md 进入 `import_qa.py --dry-run`。dry-run 通过后，用户再次确认才正式上传。

## 工单来源特有过滤规则

| 场景 | 处理方式 |
|------|---------|
| 与产品无关（发票 / 物流 / 订单流程） | 整条工单跳过，不提炼 |
| 产品物理破损（摔坏 / 撞坏 / 外壳损坏） | 整条工单直接忽略 |
| 向客户索要订单号 / 收据 / 照片 | 删除该句 |
| 引导联系客服 / 提交工单 | 删除该句 |

## 同一问题多种表达合并（重要）

如果多个消费者表达了同一个产品问题但措辞不同，将多种表达**合并**进同一条 QA 的 Question 里：

```json
{
  "question": "Kasa EC70 Camera — Why is my camera battery draining fast / discharging quickly / running out of charge quickly?",
  "answer": "- Check motion sensitivity settings — high sensitivity triggers more recordings\n- Reduce clip length in app settings\n- Enable scheduled recording only during active hours\n- Ensure firmware is up to date"
}
```

## 目录归类

工单提炼出的知识**统一归入 Product Introduction** 目录下的对应产品文件夹：

- 能识别产品型号 → `["Product Introduction", "<品类>", "<产品名>"]`
- 只能识别品类 → `["Product Introduction", "<品类>"]`
- 无法识别产品 → `["Pending Assignment"]`

提取前用 `list-directories` 自查目录是否齐全；缺则 `create-folder` 补建（详见 directory.md §5）。

## 产出文件（接入 tmp 合并流程）

批处理 wrapper 的分页中间产物在 `/workspace/state/kb-builder/ticket_extract/pages/`，最终汇总产物在：

```
/workspace/outputs/kb-builder/ticket_qa_merged_<ts>.json
```

要把最终汇总产物接入合并上传流程时，**复制一份**到 tmp 目录（保留产物原文件）：

```bash
cp /workspace/outputs/kb-builder/ticket_qa_merged_<ts>.json /workspace/tmp/kb-builder/qa_parts/qa_tickets_<brand>.json
```

然后由 `import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/` 与其他来源一起合并上传。

详见 `/skills/kb-builder/references/upload.md`。

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| 直接把工单原文粘贴进知识库 | 必须经过 `extract_ticket_qa.py` 提炼 |
| 工单里有物理破损场景也提炼了 | 物理破损整条工单直接忽略 |
| 无关工单（发票 / 物流 / 订单）也提炼 | 整条工单跳过 |
| 同一产品问题多种表达各自成条 | 合并到同一条 QA 的 Question 里 |
| 工单 QA 放进 Help Center | 工单知识统一归 Product Introduction 对应产品目录 |
| 续跑时重复处理前 600 行 | 用 `--page 6 --page-size 100` 只跑第 501-600 行 |
