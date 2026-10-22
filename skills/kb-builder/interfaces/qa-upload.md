# QA Upload Interface

公开能力：合并 QA parts 或现成 qa_plan，并上传到 Shulex 知识库。

## Stable commands

```bash
# QA parts 合并 + dry-run
npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py \
  --from-dir /workspace/tmp/kb-builder/qa_parts/ \
  --dry-run

# 使用 dry-run 已落盘的 qa_plan 正式上传
npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py \
  --qa-file /workspace/outputs/kb-builder/qa_plan_<ts>.json

# 或直接从 parts 合并并上传
npx --yes cxclaw@latest script skills/kb-builder/scripts/import_qa.py \
  --from-dir /workspace/tmp/kb-builder/qa_parts/
```

## Input qa item

```json
{
  "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
  "question": "Kasa EP25 — What is the product overview?",
  "answer": "Markdown answer"
}
```

`dir_path` 必须是目录名数组，每一段都是一个实际文件夹名称。禁止写成字符串路径，例如
`"/kb/B0117-03018-BK"` 或 `"Product Introduction/Speakers/B0117-03018-BK"`；这类输入会在
dry-run 阶段失败。上传到已有目录前先用 `list-directories` 确认真实目录层级，并按该层级写数组。

如果 `answer` 包含图片，必须保留 markdown 图片语法：

```markdown
![](https://example.com/image.png)
```

处理 DOCX / PDF / 网页来源时，优先使用能保留 markdown 图片的读取结果。不要把含图文档重新降级为
纯段落文本后再生成 QA，否则会丢失图片但上传仍可能成功。

## Guarantees

- `--from-dir` 会合并多个 QA part 并输出 `qa_plan_<ts>.json`。
- 正式上传前必须先 dry-run 并获得用户明确确认。
- `dir_path` schema 错误会在 dry-run 和正式上传前失败，不会创建目录。
- `answer` 使用 markdown；上传脚本透传 answer 内容，不会替调用方补图片。

## Non-guarantees

- 上传 API payload 结构不对调用方暴露。
- 去重和目录匹配细节归 kb-builder 内部维护。
