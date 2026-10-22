# 合并 qa_plan 并上传

→ 通用质量规则见 `/skills/kb-builder/references/qa-quality.md`（必读）

各来源（网站 / 帮助中心 / FAQ / PDF / 工单）独立提取出 QA 后，按下面流程上传。

## 工作流：分批写 tmp，脚本自动合并

**核心思路**：agent 把每批 QA 写到 `/workspace/tmp/kb-builder/qa_parts/` 的多个小文件，
`import_qa.py --from-dir` 自动按文件名排序合并、写一份带时间戳的成品到 outputs，再做 dry-run / 上传。

### 为什么这样做

直接 `write_file` 一份完整 qa_plan 大概率被 endpoint max_tokens 截断（一份典型计划 50~200 条 QA、30~100 KB）。
任何 string 字段（write_file/edit_file 的 content/new_string）都是 LLM 一次性输出，**全部受 max_tokens 限制**。
不要用占位 sentinel + edit_file 多次替换的老办法——edit_file 的 new_string 同样会被截。

### 步骤

1. **先 mkdir 干净的 tmp 目录**（避免上轮残留污染本轮）：

   ```bash
   mkdir -p /workspace/tmp/kb-builder/qa_parts && rm -f /workspace/tmp/kb-builder/qa_parts/*.json
   ```

2. **每批 ≤ 4 KB 写一个 json 文件**到 `/workspace/tmp/kb-builder/qa_parts/`。
   命名约定（任意，按文件名字母序合并）：

   | 文件名样例 | 来源 |
   |-----------|------|
   | `qa_web_policy.json` | 网站政策 QA |
   | `qa_web_kasa-ep25.json` | 网站某产品 QA |
   | `qa_help_setup.json` | 帮助中心某子目录 QA |
   | `qa_pdf_av-d600_part1.json` `qa_pdf_av-d600_part2.json` | PDF 拆出来的 QA（分批） |
   | `qa_tickets_camera.json` | 工单提炼出某品类 QA |

   每个文件的 JSON 结构都是 **QA 数组**：

   ```json
   [
     {
       "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
       "question": "Kasa EP25 Smart Plug — What is the maximum wattage?",
       "answer": "..."
     }
   ]
   ```

   `dir_path` 必须是目录名数组，不是字符串路径。不要写 `"/kb/Kasa EP25"`、
   `"Product Introduction/Smart Plugs/Kasa EP25"` 或其他带 `/` 的单个字符串；脚本会在
   dry-run 阶段报错。上传到现有 SKU / 产品目录时，先 `list-directories` 确认真实父目录，
   再写完整数组，例如 `["Product Introduction", "Speakers", "B0117-03018-BK"]`。

   含图片的答案必须在 `answer` 中保留 markdown 图片语法 `![](url)`。如果来源是 DOCX / PDF / 网页，
   优先使用能保留图片 markdown 的读取结果；不要用只读段落文本的解析方式生成最终 QA。

3. **每批 size 控制**（防止单次 write_file 被截）：
   - 普通 QA 每条 200~500 字符 → 每批 8~10 条
   - 长 answer（含图表 / 多步骤 / 规格表 / 说明书全文 QA）每条 1~3 KB → 每批 2~3 条
   - **每批 new_string ≤ 4 KB**（≈ 1K output tokens，留足余量）
   - 估不准就保守一点，少塞几条没关系

4. **被截的兜底**：如果某次 `write_file` 报 `content: Field required` 或日志出现
   `output truncated by max_tokens`，**立刻把这批数量减半重写**。这是 max_tokens 截断信号。

5. **合并 + dry-run**（脚本会把合并结果写到 `/workspace/outputs/kb-builder/qa_plan_{ts}.json` 留档）：

   ```bash
   npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/ --dry-run
   ```

6. **向用户汇报数量**，等待明确确认：

   ```
   即将上传 X 条 QA：
   - Product Introduction: N1 条
   - Brand Policy: N2 条
   - Help Center: N3 条
   - Pending Assignment: N4 条

   合并产物：/workspace/outputs/kb-builder/qa_plan_{ts}.json
   确认上传吗？
   ```

   ⚠️ 等用户回「确认」「上传吧」「没问题」后再正式上传。「可以」「好」「嗯」**不算**。

7. **正式上传**：

   ```bash
   npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/
   ```

   或者用 dry-run 阶段已落盘的 qa_plan 文件（避免重新合并）：

   ```bash
   npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py --qa-file /workspace/outputs/kb-builder/qa_plan_<ts>.json
   ```

## 上传后验证

```bash
# 按 keyword 检索确认上传成功
npx --yes cxclaw@latest api list-knowledge --keyword "Kasa EP25" --page-size 50 --pretty

# 看目录的 kuCount 是否增加
npx --yes cxclaw@latest api list-directories --pretty
```

## 已经有合并好的 qa_plan.json 时

直接传文件路径，不走 tmp：

```bash
npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py --qa-file /path/to/qa_plan.json --dry-run
npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py --qa-file /path/to/qa_plan.json
```

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| 一次 `write_file` 写整份 qa_plan | 分批写到 `/workspace/tmp/kb-builder/qa_parts/`，由 `import_qa.py --from-dir` 合并 |
| 用占位 sentinel + 多次 `edit_file` 追加 | 已废弃。`edit_file` 的 `new_string` 同样受 max_tokens 限制，会被截 |
| 单批塞太多导致截断 | 每批 ≤ 4 KB；长 answer 每批 2~3 条；截断信号出现立刻减半重试 |
| 直接上传不先 dry-run | 必须先 dry-run 并向用户汇报数量 |
| 用「可以」「好」「嗯」当确认 | 必须收到明确「确认 / 上传吧 / 没问题」|
| `--qa-file` / `--from-dir` 路径用相对形式 | 用绝对路径 `/workspace/...` |
| 上传后知识无效果 | 检查 `published: true` 和 `forceIndex: true` 是否已设置 |
| `dir_path` 写成 `/kb/SKU` 字符串 | 改成目录名数组，例如 `["Product Introduction", "Speakers", "SKU"]` |
| 回复说保留图片但知识里没有图片 | 检查 QA plan 的 `answer` 是否真的包含 `![](url)`，上传脚本不会自动从原文补图 |
