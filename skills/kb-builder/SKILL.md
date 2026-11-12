---
name: kb-builder
description: Shulex 知识库搭建与原子管理能力。用于目录管理，问答、文档、网页和产品知识的导入、查询、更新、状态管理与导出，以及标签、隔离关键词和回复模板管理。
requires:
  libs: [solvea-api]
---

# Shulex KB Builder

本 skill 提供知识库的原子管理能力、场景 reference 路由和通用执行规范。

详细格式、字段、确认步骤和异常处理都以对应 reference 为准；只在命中具体场景时读取相关 reference。

## 能力路由

| 用户意图 | 读取的 interface / reference | 主要执行入口 |
|---|---|---|
| 网页建知识库、探查网站、设计目录 | [`interfaces/web-kb.md`](interfaces/web-kb.md)、[`references/directory.md`](references/directory.md) | `kb-builder crawl`、`kb-builder directory-plan`、`kb-builder create-directories` |
| 网页/Word/PDF 导入 | 本文件“来源模式” | 按模式选择入口 |
| 网页/文件/工单整理成问答 | [`qa-quality.md`](references/qa-quality.md)、[`qa-from-web.md`](references/qa-from-web.md)、[`qa-from-help-center.md`](references/qa-from-help-center.md)、[`qa-from-pdf.md`](references/qa-from-pdf.md)、[`qa-from-tickets.md`](references/qa-from-tickets.md) | `kb-builder extract-web-qa`、`kb-builder batch-extract-ticket-qa`、`kb-builder import-qa` |
| Excel / CSV 整理成问答 | [`references/upload.md`](references/upload.md) | 先解析表格，再按 QA 导入流程执行 |
| 上传已有 QA 计划 | [`references/upload.md`](references/upload.md) | `kb-builder import-qa` |
| 回复模板库导入 | [`references/reply-template.md`](references/reply-template.md) | `kb-builder import-templates` |
| 查看、更新、移动、删除或改变知识状态 | [`references/knowledge.md`](references/knowledge.md) | 按 reference 提供的固定入口 |
| 创建或更新产品知识 | [`references/product.md`](references/product.md) | `create-product-knowledge`、`update-product-knowledge` |
| 导出知识 | [`references/export.md`](references/export.md) | `kb-builder export-knowledge` |
| 知识库目录管理 | [`references/directory.md`](references/directory.md) | 按 reference 提供的操作入口 |
| 标签管理 | [`references/tags.md`](references/tags.md) | 按 reference 提供的操作入口 |
| 隔离关键词及绑定 | [`references/isolation-keywords.md`](references/isolation-keywords.md)、[`references/tag-isolation-migration.md`](references/tag-isolation-migration.md) | 按 reference 提供的操作入口 |

## 来源模式

先根据用户意图区分模式，只读取选中路径的文档。用户只提供网址或文件时，提交前确认保存类型；已明确要求问答时不重复确认。

| 模式 | 后续路径 |
|---|---|
| 保存为网页/文档 | `kb-builder import-source-documents`，不进入问答提炼 |
| 原文转问答：每篇一条、完整保留正文 | 按下述原文规则生成计划 → `references/upload.md`；不读取 `qa-quality.md` 和 `qa-from-*` 提炼规则，不调用默认摘要脚本 `kb-builder extract-web-qa` |
| 提炼问答：提取 FAQ、归纳问题 | `references/qa-quality.md` + 对应来源的 `qa-from-*` → `references/upload.md` |

**保存为网页/文档**：计划格式为 `{"source": "URL 或本地文件路径", "dir_path": ["一级", "二级", "三级"]}`，多条记录组成 JSON 数组。先运行 `kb-builder import-source-documents --plan-file <plan>` 预览，用户明确确认后再加 `--execute`。脚本对本次计划内 URL 去重；历史重复由后端处理，执行结果保留后端响应。

**原文转问答**：

- 每篇文章/文件一条：原标题作 Question，完整正文作 Markdown Answer；按用户指定的前缀、分隔符和目录组织，不擅自摘要、拆条或生成潜在问题。
- 保留原文语言（除非明确要求翻译）、图片、表格、链接、步骤及客服办理条件；只清理正文之外的导航、页脚等噪声。订单、物流、退款等业务话题不排除。
- 获取完整正文，不用摘要或截断内容代替；生成计划后核对来源数量、标题及正文完整性，列明缺失项，再按 `upload.md` 预览、确认、上传。
- 实际客户个人信息须脱敏并告知用户；原始工单对话走提炼路径，不能直接作为公开知识。

## 基础查询入口

以下是本 skill 约定的只读查询入口，按需直接使用；涉及写入、查重、迁移、导出或结果校验时，再读取对应 reference。不要自行猜测其他 CLI 命令。

| 查询内容 | 固定命令 |
|---|---|
| 目录树 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" directory list --pretty` |
| 知识列表 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" knowledge list --type ALL --page-size 50 --page 1 --pretty` |
| 按关键词查知识 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" knowledge list --keyword "关键词" --page-size 50 --pretty` |
| 单条知识 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" knowledge get --id <knowledge_id> --type {QA,LEARN_SELF,FILE,WEBSITE,PRODUCT} --pretty` |
| 知识标签定义 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" knowledge tags --pretty` |
| 隔离关键词 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-isolation-keywords --page-size 50 --page 1 --pretty` |
| 单条知识已绑定的隔离关键词 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" api get-knowledge-isolation-keywords --id <knowledge_id> --type {QA,LEARN_SELF,FILE,WEBSITE,PRODUCT} --pretty` |
| 回复模板 | `node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-templates --page-size 50 --pretty` |

`list-knowledge` 分页时先看返回的 `total`，再按需增加 `--page`；接口最大 `--page-size` 为 1000，不要用不断增大页大小的方式探测总量。

## 写入入口索引

以下能力仍由本 skill 提供，但必须先读对应 reference、展示变更计划并取得明确确认，再使用其中规定的参数：

| 写入能力 | 固定入口 | 必读 reference |
|---|---|---|
| 更新问答 / AI自学习 / 文档 / 网页 | `update-knowledge` / `batch-update-knowledge` / `update-document-content` | [`knowledge.md`](references/knowledge.md) |
| 创建或更新产品知识 | `create-product-knowledge` / `update-product-knowledge` / `batch-update-products` | [`product.md`](references/product.md) |
| 删除、移动、发布/下架、显示/隐藏各类知识 | `operate-knowledge` | [`knowledge.md`](references/knowledge.md) |
| 创建、重命名、移动或删除目录 | `create-folder` / `kb-builder create-directories` / `update-directory` / `move-directory` / `delete-directory` | [`directory.md`](references/directory.md) |
| 导入问答 | `kb-builder import-qa` | [`upload.md`](references/upload.md) |
| 导入文档或网页 | `kb-builder import-source-documents` | 本文件“来源模式” |
| 修改知识标签 | `edit-knowledge-tags` | [`tags.md`](references/tags.md) |
| 创建、修改、删除或绑定隔离关键词 | `create-isolation-keyword` / `update-isolation-keyword` / `delete-isolation-keyword` / `batch-update-isolation-keyword-bindings` | [`isolation-keywords.md`](references/isolation-keywords.md) |
| 创建、修改或删除回复模板 | `create-template` / `update-template` / `delete-templates` | [`reply-template.md`](references/reply-template.md) |

## 统一规则

- 客户侧始终使用产品界面术语，并跟随用户的界面语言：中文使用“AI自学习 / 问答 / 文档 / 网页 / 产品”，英文使用“AI Self-learning / Q&A / Documents / Websites / Products”；不要向客户暴露 `QA`、`KU`、`FILE`、`DOCUMENT`、`WEBSITE` 等内部字段。
- 网页和 Word/PDF 在执行前确认“保留原文”还是“整理成问答”；用户明确要求 FAQ/问答时才直接走 QA 流程。
- 未明确指定时，目录默认最多三级；超过三级只能在用户明确要求后通过 `--max-depth` 覆盖。
- 业务产物语言遵循：用户明确指定的产物语言 > 会话上下文中的用户界面语言偏好 > 用户当前消息语言。
- 所有线上写入（创建目录、上传知识、修改知识、关键词变更）都必须先展示计划并等待明确确认。
- 删除前必须展示影响范围，并获得同时表达“已知晓影响”和“确认删除”的强确认；简单的“确认 / OK / 可以”不足以授权删除。
- 具体格式、目录规则、查重、结果校验和 API 参数以对应 reference 为准；不要把这些细节复制到本文件。
- 不把内容整理建议说成平台限制。只有接口文档、格式校验或实际错误提供依据时，才报告对应的技术限制，并说明具体证据；不能因文章涉及订单、退款或联系客服就声称需要研发支持。

根据用户明确意图读取上表对应 reference，再执行相应的原子能力。
