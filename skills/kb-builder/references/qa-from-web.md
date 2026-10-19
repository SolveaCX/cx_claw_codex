# 从网站产品/政策页提取 QA

→ 通用质量规则见 `/skills/kb-builder/references/qa-quality.md`（必读）

## 数据来源优先级

**优先读取已有的爬取缓存**（`workspace/state/kb-builder/crawl_cache.json`），不重复爬取。

用 `read_file` 工具读取 cache，按 `pages` 中的 `type` 字段分类处理：
- `type == "product"` → Product Introduction
- `type == "policy"` → Brand Policy
- `type == "help_center"` → 走 `qa-from-help-center.md`
- `type == "other"` → 跳过

⚠️ cache 里的 `snippet` 只有 ≤1200 字符摘要，**做 QA 必须对每个目标 URL 单独调 `web_fetch(url=...)` 拿全文**（产品规格、政策原文、表格图片等只在全文里）。

如果 cache 不存在（用户跳过了网站探查阶段，直接给若干产品页 / 政策页 URL）→ 直接对每个 URL 用 `web_fetch` 拿全文，按下面规则提取。

## FAQ / Q&A 结构

任何网站页面只要正文里有明确 FAQ / Q&A 结构，先按 `qa-quality.md` 的 FAQ 规则逐条提取，再按页面上下文归类：

- 产品详情页里的产品 FAQ → `Product Introduction` 对应品类 / 型号目录
- 政策页里的政策 FAQ → `Brand Policy` 对应政策目录
- 帮助中心 / 文档站 / 支持站 FAQ → `Help Center` 对应真实导航目录

FAQ 条数**不受**“产品整体介绍 1 条 + 潜在问题 ≤5 条”限制；页面有多少有效 FAQ 条目就提取多少条，只受 `upload.md` 的分批大小限制。

## 1. 品牌政策知识（→ Brand Policy 目录）

从政策页提取：售后政策、退换货政策、物流政策、质保 / 保修政策。

每条政策生成 1 条 QA，归入对应 Brand Policy 二级目录：

```json
{
  "dir_path": ["Brand Policy", "Warranty Policy"],
  "question": "Kasa Smart Products — What is the warranty period and coverage?",
  "answer": "- 18-month limited warranty from date of purchase\n- Covers manufacturing defects and hardware failures\n- Does not cover physical damage, water damage, or misuse\n- Warranty valid for original purchaser only"
}
```

## 2. 产品落地页知识（→ Product Introduction 目录）

对每个产品详情页，生成**两类** QA：

**第一类：产品整体介绍**（每款产品 1 条）
- Q：`[型号] — Product Overview` 或 `What is the [型号] and what does it do?`
- A：详细产品描述、规格参数、尺寸、功能、卖点、产品对比、购买链接
- **必须保留**落地页上的图片（`![描述](图片URL)`）和表格

```json
{
  "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
  "question": "Kasa EP25 Smart Plug — What is the Kasa EP25 and what does it do?",
  "answer": "The Kasa EP25 is a dual-outlet smart plug with built-in energy monitoring.\n\n**Key Features:**\n- Two independently controlled outlets\n- Real-time energy monitoring\n- Compatible with Alexa, Google Home, and Apple Home\n- Max load: 15A / 1800W\n\n**Dimensions:** 2.1\" x 1.4\" x 1.4\"\n\n![Kasa EP25](https://example.com/ep25.jpg)\n\n| Feature | EP25 | EP10 |\n|---------|------|------|\n| Dual outlet | ✓ | ✗ |\n| Energy monitor | ✓ | ✗ |"
}
```

**第二类：产品潜在问题**（每款产品 ≤5 条）

参考落地页信息，生成消费者可能会问的具体问题（颜色规格、尺寸参数、功能差异等）。如果产品页本身已有 FAQ / Q&A 结构，FAQ 逐条提取，不占用这 ≤5 条“自行归纳潜在问题”的额度：

```json
[
  {
    "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
    "question": "Kasa EP25 Smart Plug — What colors does the EP25 come in?",
    "answer": "The Kasa EP25 is available in White only."
  },
  {
    "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
    "question": "Kasa EP25 Smart Plug — What is the maximum wattage the EP25 supports?",
    "answer": "The Kasa EP25 supports a maximum load of 15A / 1800W per outlet."
  }
]
```

## 目录前置自查

提取前先 `list-directories` 看现有目录是否覆盖本次产品的品类 / 型号，缺则用 `create-folder` 补建（详见 directory.md §5）。

## 产出文件（每批写到 tmp）

提取的 QA **不要**自己合并成 qa_plan，**也不要**一次 write_file 写完整数组。
每批 ≤ 4 KB 写到 `/workspace/tmp/kb-builder/qa_parts/qa_web_<topic>.json`（如 `qa_web_policy.json` / `qa_web_kasa-ep25.json`），
最后由 `import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/` 自动合并 + 上传。

详见 `/skills/kb-builder/references/upload.md`。

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| 只看 cache 里 1200 字 snippet 就生成 QA | 必须 web_fetch 全文 |
| 产品落地页只生成一类 QA | 两类必须都有：整体介绍 + ≤5 条潜在问题 |
| 产品页已有 FAQ 但只抽 5 条或放进 Help Center | FAQ 逐条提取，归 Product Introduction 对应产品目录 |
| 政策 QA 放进 Help Center 或 Product Introduction | 政策只进 Brand Policy 对应二级目录 |
