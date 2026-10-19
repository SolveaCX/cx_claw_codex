# 从帮助中心 / FAQ / 文档站提取 QA

→ 通用质量规则见 `/skills/kb-builder/references/qa-quality.md`（必读）

帮助中心目录在 KB 里建好后，此处直接提取知识内容。这里也适用于用户直接提供的 FAQ 页面、文档站、支持站、知识库文章列表。

## 流程

1. **拿帮助中心页面 URL 列表**：
   - 优先从 `crawl_cache.json` 取出 `type == "help_center"` 的页面
   - cache 不存在或不全 → 用户给帮助中心根 URL → `web_crawl(url=root, max_depth=2, limit=80)` 单独深抓一次
2. **逐页 `web_fetch`** 拿完整 markdown（cache 里 snippet 只有 1200 字符不够）
3. **提取 Q&A**：
   - 页面本身已有明确的 FAQ / Q&A 结构（条目标题即问题、正文即答案）→ 按 `qa-quality.md` 的全局 FAQ 规则逐条提取
   - 页面无明确 FAQ 结构（如产品说明、政策说明等连续正文）→ 自行归纳整理成 Q&A
4. **归入 KB 中现有的 Help Center 子目录**（如 KB 已有「Getting Started > Setup Guide」），**不重新发明目录**
5. 一个帮助页面若包含多个独立话题，可拆分为多条 QA

## Help Center / 文档站 FAQ 条数规则

帮助中心 / 文档站 / 支持站里的 FAQ / Q&A 页面不受 `qa-from-web.md` 中“产品整体介绍 1 条 + 潜在问题 ≤5 条”的产品页规则限制。

- 有明确 FAQ 条目的页面：按页面上的有效条目逐条提取，原则上不压缩条数
- 只有连续正文、没有 FAQ 结构的页面：按独立主题归纳为 QA
- 真正的数量控制只在写文件和上传阶段：按 `upload.md` 每批 ≤4 KB 分片，避免截断

## 示例

```json
{
  "dir_path": ["Help Center", "Getting Started", "Setup Guide"],
  "question": "Kasa Smart Plugs — How do I set up my Kasa smart plug for the first time?",
  "answer": "1. Download the Kasa Smart app (iOS / Android)\n2. Open the app → tap '+' → select your device\n3. Follow the in-app setup wizard\n4. Connect to your 2.4GHz Wi-Fi network\n5. Name your device and assign it to a room\n\n![Kasa app setup](https://example.com/setup.png)"
}
```

## 目录前置自查

`list-directories` 看现有 Help Center 子目录树。提取过程中遇到帮助中心新栏目而 KB 还没建对应子目录时：
- 该栏目内容不多 → 临时 `create-folder` 补建（详见 directory.md §5）
- 实在难归类 → `["Pending Assignment"]`

## 产出文件（每批写到 tmp）

提取的 QA **不要**自己合并成 qa_plan，**也不要**一次 write_file 写完整数组。
每批 ≤ 4 KB 写到 `/workspace/tmp/kb-builder/qa_parts/qa_help_<topic>.json`（如 `qa_help_setup.json` / `qa_help_troubleshooting.json`），
最后由 `import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/` 自动合并 + 上传。

详见 `/skills/kb-builder/references/upload.md`。

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| 帮助中心目录建好了但没提取知识 | 帮助中心页面内容也要提取为 QA |
| 自己发明 Help Center 子目录而非照搬网站导航 | Help Center 子目录直接对齐网站真实导航 |
| 只看 cache snippet 就写 QA | 必须 web_fetch 全文 |
| FAQ 页面只抽 5 条 | FAQ 按有效条目逐条提取，不套产品页 ≤5 条潜在问题限制 |
