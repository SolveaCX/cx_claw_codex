# Web KB Interface

公开能力：从网站、产品站、帮助中心或文档站构建知识库目录与 QA，也支持在确认“保留网页原文”后创建网页资料。

网页地址先做模式确认：保留原始网页时使用
`../scripts/import_source_documents.py --plan-file <plan> --execute`；选择整理问答时才进入下面的 crawl → extract → import_qa 流程。

## Modes

```text
auto    # 默认；适合网页整理的任务使用 crawl pipeline，其他任务走 legacy
crawl   # 新脚本化网页 pipeline，可使用 Crawl4AI
legacy  # 旧 reference + Tavily 工具路径，兼容历史行为
```

## Provider

```text
auto | crawl4ai | tavily
```

原则：

- Crawl4AI 只用于适合网页抓取/整理的任务。
- PDF / xlsx / qa_plan.json / 回复模板 / 导出 / 单条知识更新不使用 Crawl4AI。
- Crawl4AI 作为 Python 依赖运行在 sandbox 内的 skill 脚本中，不接入主服务全局工具。
- 默认 `provider=auto` 保持轻量兼容路径；需要 JS/动态页面抓取时显式使用 `provider=crawl4ai`。

## Stable commands

首版脚本化 pipeline 目标入口：

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/crawl_site.py \
  --url <source_url> \
  --mode auto \
  --provider auto \
  --max-depth 3 \
  --max-pages 100 \
  --output /workspace/outputs/kb-builder/crawl_result_<ts>.json

$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/build_directory_plan.py \
  --crawl-result /workspace/outputs/kb-builder/crawl_result_<ts>.json \
  --output /workspace/outputs/kb-builder/directory_plan_<ts>.json

# 展示 directory_plan_<ts>.json，等待用户明确确认后写入 confirmed_tree
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/build_directory_plan.py \
  --crawl-result /workspace/outputs/kb-builder/crawl_result_<ts>.json \
  --output /workspace/outputs/kb-builder/directory_plan_<ts>.json \
  --write-confirmed-tree

$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/create_dirs.py

$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/kb-builder/scripts/extract_web_qa.py \
  --crawl-result /workspace/outputs/kb-builder/crawl_result_<ts>.json \
  --output-dir /workspace/tmp/kb-builder/qa_parts
```

兼容路径：

- `mode=legacy` 或 `provider=tavily` 时，按 `kb-builder/SKILL.md` 和对应 reference 走 legacy。
- `provider=crawl4ai` 只在 sandbox 依赖可用时执行；失败时输出显式错误，不把调用方切到其他 skill 内部实现。

## Outputs

- `crawl_result_<ts>.json`
- `directory_plan_<ts>.json`
- `/workspace/state/kb-builder/confirmed_tree.json`
- `/workspace/tmp/kb-builder/qa_parts/*.json`

## Guarantees

- 用户或上游 SOP 明确给出目录 schema 时，按输入 schema 生成目录树，不额外增加 Product Introduction 等默认根目录。
- 未给出目录 schema 时，使用 kb-builder 默认标准模板：Product Introduction / Brand Policy / Help Center / Pending Assignment。
- `Help Center` 仅在发现帮助中心/FAQ/文档站时创建。
- QA parts 兼容 `import_qa.py --from-dir`。
- `create_dirs.py` 前必须已经存在 `/workspace/state/kb-builder/confirmed_tree.json`；没有用户确认时不得写入或创建目录。
- 调用方不需要知道 crawl provider 内部策略。

## Non-guarantees

- 页面顺序不保证稳定。
- Markdown 具体格式不保证完全一致。
- Crawl provider 的具体实现不对调用方暴露。
