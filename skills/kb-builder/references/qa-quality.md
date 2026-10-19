# QA 通用质量规则

无论 QA 来源（网站 / 帮助中心 / FAQ / PDF / 工单），所有生成的 QA 都必须遵守本文规则。

## 格式

**Answer 全部用 markdown**——Shulex 知识库后台和客服回复链路均按 markdown 渲染。
保留图片 `![alt](url)`、表格、列表 `-`、加粗 `**...**`、有序步骤 `1. ...`，不要写 HTML 标签。
抓取阶段（`web_fetch` / `web_crawl` / `read_file` PDF）返回的就是 markdown，可直接保留结构、按需精简。

**语言：** 用户明确指定的产物语言 > 会话上下文中的用户界面语言偏好 > 用户当前消息语言。Question、Answer 与新建的业务目录名使用目标语言；品牌名、产品型号和其他专有名词保留原文。网页、附件、PDF 或工单原文只是知识来源，不能单独改变目标语言。不得因为本文示例是英文而默认生成英文。

目录路径必须跟随当前任务的目录 schema。用户或 SOP 明确给出目录层级时，按该 schema 原样归类；未给出 schema 时才使用默认标准模板，默认一级目录 `Product Introduction` / `Brand Policy` / `Help Center` / `Pending Assignment` 保持英文。

## Question 格式

- 品类通用问题（多款产品共有）→ 用品类名：`[品类名] — [问题]`
- 特定型号专有问题 → 用型号名：`[型号名] — [问题]`

✅ `Smart Security Cameras — How do I reset my camera to factory settings?`（品类通用）
✅ `Kasa EP25 Smart Plug — What is the maximum wattage this plug supports?`（型号专有）
❌ `How do I reset it?` ← 无产品信息
❌ `Reset steps?` ← 不是完整问句

## FAQ / Q&A 结构提取规则

任何页面只要有明确 FAQ / Q&A 结构（条目标题是问题、正文是答案），都按下面规则处理：

- 逐条提取原页面的有效 FAQ；问题加品牌 / 品类 / 型号前缀，答案保留原文 markdown 内容
- 不受产品页“整体介绍 1 条 + 潜在问题 ≤5 条”限制；FAQ 有多少有效条目就提取多少条
- 目录归类仍按页面上下文决定：产品页里的产品 FAQ 归产品对应品类/型号目录；政策页里的政策 FAQ 归政策目录；帮助中心 / 文档站 FAQ 才归帮助中心目录。使用默认标准模板时，这些目录分别对应 Product Introduction、Brand Policy、Help Center。
- 真正的数量控制只在写文件和上传阶段：按 `upload.md` 每批 ≤4 KB 分片，避免截断

## Answer 强制过滤

- 删除所有向客户索要信息的话术（订单号、收据、产品照片、序列号等）
- 删除所有引导联系客服 / 提交工单 / 发邮件的话术
- 删除营销语言、品牌故事、公司介绍
- 格式清晰有条理：分点用 `-`，保留图片 `![描述](URL)`，保留表格

## 全局排除话题（不生成 QA、不建目录）

- 物流 / 快递 / 配送时效 / 包裹追踪
- 订单查询 / 修改 / 取消
- 退货 / 退款 / 换货
- 账号管理
- 支付 / 账单

## 目录归类规则

每条 QA 归入最精确匹配的目录：

1. 能匹配三级目录 → 归入三级
2. 能匹配二级目录 → 归入二级
3. 无法判断 → 归入 `["Pending Assignment"]`

提取过程中发现品类/型号目录在 KB 里不存在时，**用 `create-folder` CLI 临时补建**，
不要直接归到 Pending Assignment（兜底是给真的无法分类的内容）。

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| Question 不区分品类 / 型号 | 通用问题用品类名，型号专有问题用型号名 |
| Answer 里向客户索要信息（订单号 / 照片 / 序列号） | 整句删除 |
| Answer 里引导联系客服 / 提交工单 | 整句删除 |
| 用户已指定目录 schema 时仍套默认 Product Introduction | 用户 schema 优先，严格按指定层级归类 |
| 默认标准模板下自由发明一级目录名称 | 一级目录只有四个固定名称（见 directory.md） |
| Product Introduction 二级是产品名 | 二级必须是品类，三级才是产品名 |
| Brand Policy 下建了三级目录 | Brand Policy 只到二级 |
| 无法归类的内容随意放置 | 统一放入 Pending Assignment |
| 产品页 FAQ 被放进 Help Center | 产品页 FAQ 归 Product Introduction 对应产品目录 |
| FAQ 页面只抽 5 条 | FAQ 按有效条目逐条提取，不套产品页潜在问题 ≤5 条限制 |
