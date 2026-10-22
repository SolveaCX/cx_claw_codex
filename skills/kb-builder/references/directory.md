# 目录管理能力

默认目录最多三级（一级/二级/三级）。脚本会拒绝第四级及以上，不会静默截断；只有用户明确要求其他层级时，才使用 `--max-depth` 覆盖。

涵盖：探查网站/知识来源 → 设计目录树 → 用户确认 → 批量创建 / 临时补建。
本文档不规定调用顺序——SOP 可以全流程跑，也可以单独调用某一步（例如只补建某个型号目录）。

---

## §1 探查网站/知识来源

“网站”可以是品牌官网、产品站、帮助中心、FAQ 页面、文档站、支持站或用户给出的其他公开知识来源 URL；不要只按“官网首页”理解。

### 1.1 首轮爬取（必须读完全文）

调用 `web_crawl` 一次性发现 + 抽取页面，参数取较激进的设定（默认 max_depth=2/limit=50 经常不够）：

```
web_crawl(
    url="https://example.com",
    instructions="Product, category, policy, help center pages.",
    max_depth=3,
    limit=100,
)
```

⚠️ **instructions 必须简短**（建议 ≤80 字符），写"找什么主题的页面"，不写动作。实测 200+ 字符的长 instructions 会触发 tavily 服务端 "Try more concise instructions" 错误，返回空结果。

`web_crawl` 永远抓页面 + 完整内容（raw_content），instructions 只是引导爬虫挑哪类页面，不控制是否抓内容。每页返回完整 raw_content（含全站导航、分类、产品列表）；后续做 QA 再 `web_fetch` 单页深抓拿规格 / 政策原文。

**大文件必须读完，边读边记录**：100 页全文超过 20k tokens 时，运行时会自动把完整结果写到 `/large_tool_results/<tool_call_id>` 文件，工具回包改成 head + tail 预览。**无论后续是否找到其他来源、无论是否认为"已有足够信息"，大文件都必须读到底，不得提前停止**——中间段经常藏着整个品类：

1. `read_file(file_path=..., offset=0, limit=300)` 读第一段，**立即**从中提取产品/品类 URL 写入内部列表
2. 用返回的 `lines X-Y of N` 判断是否读完；若 Y < N，以 Y 为下一次 offset 继续读
3. 每段提取完即丢弃原文，只留 URL 列表，循环直到 Y ≥ N 才算读完
4. 读到页面标题或 URL 含 `all` / `shop-all` / `shop_all` / `all-products` / `products` / `collections` 等汇总页信号时，**必须单独 `web_fetch` 该 URL** 并解析其产品分区结构（不能只记标题/URL，需要拿到各品类下的产品列表和数量）

**全量产品页 / 汇总页不能漏**：很多站点把全部产品和真实品类结构放在 `/all`、`/products`、`/collections/all`、`/shop-all`、`/pages/all-products`、`/collections`、`/category/all` 这类页面里。发现这些链接时，即使 web_crawl 已经抓到一批产品页，也必须 fetch 汇总页并从中补全：
- 各品类名称
- 每个品类下的产品 URL
- 套装 / bundle / accessory 等容易被普通产品页抓取漏掉的条目
- 页面中出现但 sitemap / search 没出现的产品

**1.1 与 1.2 可以并行**：web_crawl 发出后，可以同步开始 robots.txt / site:search / 电商建站平台检测，不需要等 1.1 全部读完再启动兜底。

按内容关键词把每页归类成 `product` / `policy` / `help_center` / `other`。FAQ / Q&A 结构本身**不决定目录类型**：
- 产品详情页里的 FAQ 仍归 `product`
- 政策页里的 FAQ 仍归 `policy`
- 只有帮助中心 / 文档站 / 支持站页面，或路径/标题含 `help` / `support` / `docs` / `knowledge-base` 的 FAQ，才归 `help_center`

### 1.2 兜底补全（必须执行，与 1.1 并行）

`web_crawl` 是 BFS 链接跳转，受站点链接结构限制，单跑一次容易漏品类。下面三条**全部执行**，命中即合并进结果，**不互相替代**：

**A. 搜索引擎索引**（最普适）

```
web_search("site:{domain} product", allowed_domains=["{domain}"])
```

搜索引擎已做过站点索引，跨任何站点结构都有效。从结果里提取所有产品 URL。

同时补搜汇总页信号：

```
web_search("site:{domain} all products OR shop all OR collections all", allowed_domains=["{domain}"])
```

命中的汇总页必须 `web_fetch`，不能只把搜索结果里的 URL 记入列表。

**B. robots.txt → sitemap**（标准协议）

```
web_fetch("{baseUrl}/robots.txt")
```

读返回内容里的 `Sitemap: <url>` 行（可能多行）。robots.txt 是 RFC 标准，几乎所有站都有。对每个声明的 sitemap URL 再 `web_fetch`，从中提取所有产品路径。robots.txt 没声明 sitemap 时跳过，不要硬猜 `/sitemap.xml`。

**C. Shopify 专项补全**（检测到 Shopify 时，在 A/B 基础上额外执行）

判断是否 Shopify（满足其一即可）：
- robots.txt 内容含 `shopify` / `myshopify.com`
- web_crawl 结果中页面内容含 `cdn.shopify.com`

确认是 Shopify 后，**在 A/B 之外额外执行以下步骤**：

1. **`/products.json` 分页 API** — 返回完整产品列表，包括无 tag、未归入任何 collection 的产品（这类产品通过 web_crawl 和 sitemap 抓不到）：
   ```
   web_fetch("{baseUrl}/products.json?limit=250")
   # 若返回 products 数量 == 250，继续翻页直到某页数量 < 250
   web_fetch("{baseUrl}/products.json?limit=250&page=2")
   ```
   从 `products[].handle` 拼出 `/products/{handle}` URL 列表合并去重。

2. **sitemap 全量分片** — sitemap index 里每一条 `<loc>` 都要 `web_fetch`，不止第一片：
   ```
   # sitemap index 里可能有多行：
   # sitemap_products_1.xml?from=...&to=...
   # sitemap_products_2.xml?from=...&to=...   ← 不要漏
   ```

3. **从 sitemap_pages 找商家汇总页** — `/products.json` 只给产品 URL 的平铺列表，不告诉你商家把产品分成哪几个品类。商家常在 sitemap_pages 里维护一个汇总页（路径含 `shop`、`all`、`product` 等），能反映真实分类结构（包括无 tag 套餐的归属）：
   - 拿到 sitemap_pages 后，找路径匹配 `/pages/*shop*` 或 `/pages/*all*` 或 `/pages/*product*` 的条目
   - 逐条 `web_fetch`，若页面内容按品类分区列出产品，**以该页分区结构为准设计目录树**
   - 找不到则用 `/products.json` 的 `tags` 字段推断品类

**并行建议**：`/products.json` + sitemap 全量分片 + 汇总页访问可以同步发出，互不依赖。

**D. SHOPLINE 专项补全**（检测到 SHOPLINE 时，在 A/B 基础上额外执行）

判断是否 SHOPLINE（满足其一即可）：
- 输入域名或 sitemap / robots 里的链接包含 `myshopline.com`
- robots.txt / 页面源码 / web_crawl 原文包含 `SHOPLINE` / `shopline` / `shoplineapp`

确认是 SHOPLINE 后，**不要套 Shopify 的 `/products.json` 规则**。SHOPLINE 产品接口通常不是匿名公开抓取入口，优先走公开页面与 sitemap：

1. **robots.txt → sitemap 全量抓取**：
   - 先读 robots.txt 里的所有 `Sitemap:` 行
   - 对每个 sitemap URL 都 `web_fetch`
   - sitemap index 里出现多片 sitemap 时，每一片都要继续 fetch，不只读第一片
   - 从 `<loc>` 中提取疑似产品页、集合页、分类页、帮助中心页、政策页 URL

2. **平台默认 sitemap 兜底**：
   - 只有在已确认 SHOPLINE、且 robots.txt 没给 sitemap 时，才尝试一次 `{baseUrl}/sitemap.xml`
   - 若 404 / 空结果，立即停止这个分支，不继续硬猜路径

3. **站内结构补全**：
   - 用 `web_search("site:{domain} product OR products OR collection OR collections", allowed_domains=["{domain}"])`
   - 抓到集合 / 分类页后，再 `web_crawl(url=collection_url, max_depth=1, limit=50)` 提取其下产品页
   - 找到路径含 `shop` / `all` / `product` / `collection` 的汇总页时，必须 `web_fetch` 并解析品类分区结构

4. **分类依据**：
   - 页面含产品标题、价格、SKU、规格、Add to cart / Buy now、产品图片等信号 → `product`
   - 页面是集合、分类、全产品列表 → 作为目录树设计素材，并继续提取子产品 URL
   - 页面含 FAQ / Q&A 结构时，按 `qa-quality.md` 的 FAQ 规则逐条提取；产品页 FAQ 仍归对应产品目录

### 1.3 向用户汇报并等待确认完整性

汇报必须**结构化 + 主动确认**，不能只说"发现 N 个页面"：

```
✅ 已扫描 https://example.com（首轮 47 + 兜底补抓 32，去重后共 71 个）

按类型分桶：
- 产品页 35 个：/products/xxx, /products/yyy, ... (+33)
- 品类页 8 个：/category/aa, /category/bb, ...
- 政策页 4 个：/warranty, /returns, /shipping, /privacy
- 帮助中心 12 个：/help/setup-guide, ... (+9)
- 其他/已排除 12 个

兜底来源：
- 搜索引擎 site: 索引 ✅（解析出 35 个产品 URL）
- robots.txt → sitemap ⚠️（robots.txt 未声明 sitemap，已跳过）

⚠️ 可能未覆盖：（若有以下情况，如实列出）
- web_crawl 结果被截断，中间段未完整读取
- 某些品类页未发现（如网站导航里有但 crawl 没抓到的栏目名）
- 动态加载 / 登录后才可见的页面

请帮忙核对：
1. 上面产品列表是否覆盖了全部主力产品？
2. 有没有哪些品类或产品明显缺失？如果有，告诉我具体名称、或者直接把对应品类页 / 产品页的 URL 贴给我，我来补抓。
```

⚠️ 必须等用户明确"齐了 / 确认 / 没问题"才进入下一步。

**用户列出遗漏时的局部补抓**：

- 用户给具体 URL（品类页 / 产品页）→ 直接 `web_fetch` 那一页拿内容；如是品类页，再用 `web_crawl(url=cat_url, max_depth=1, limit=50)` 提其下产品
- 用户只给产品名（不给 URL）→ `web_search("site:{domain} {product_name}")` 找 URL；找到再 fetch；找不到让用户给品类页 URL
- 不要在主域名根目录硬猜路径（不通用）
- 补抓完再次走本步骤汇报，循环到用户说全为止

### 1.4 写入跨轮缓存（用 write_file 工具）

把整理好的 cache JSON 用 **write_file 工具**写到 `workspace/state/kb-builder/crawl_cache.json`（**固定名**，每轮覆盖）：

```json
{
  "baseUrl": "https://example.com",
  "crawledAt": "2026-05-06T10:00:00Z",
  "pages": [
    {"url": "https://example.com/products/kasa-ep25", "type": "product", "title": "Kasa EP25", "snippet": "..."},
    {"url": "https://example.com/warranty", "type": "policy", "title": "Warranty", "snippet": "..."}
  ]
}
```

后续提取 QA 时各来源直接复用此 cache，避免重复爬取。如需更新，重写整个文件。

---

## §2 目录树设计

目录 schema 优先级：

1. 用户当前消息明确指定的目录层级。
2. SOP（poc/delivery）传入的目录规范。
3. kb-builder 默认标准模板。

如果用户或上游给出目录 schema，必须按该规范创建和上传。schema 定义了根节点和层级时，不得因为默认标准模板存在而额外增加默认根目录，也不得擅自重排或补充层级。

### 默认标准模板

仅当用户没有指定目录 schema、SOP 也没有传入目录规范时，才使用下面的标准模板。使用该模板时，不得自由发明一级目录名称。

### 一级目录详细语义

**1. Product Introduction（产品介绍）**
- 二级：产品品类（如 Smart Plugs / Robot Vacuums / Air Purifiers）
- 三级：该品类下的具体产品名称（如 Kasa EP25 / Roomba j7+）
- 规则：二级必须是品类，**不能直接把产品名放到二级**
- 来源：产品列表页、品类页、单品详情页
- 始终创建

**2. Brand Policy（品牌政策）**
- 二级：细分政策类型（如 Warranty Policy / Return Policy / Shipping Policy / Privacy Policy）
- **不创建三级目录**
- 来源：条款页、政策页、FAQ 中的政策类内容
- 始终创建

**3. Help Center（帮助中心）**
- ⚠️ **条件创建**：仅当爬取内容中发现 support / help / faq 路径的页面时才创建
- 二级 & 三级：直接参考网站帮助中心 / FAQ / 文档站的**真实导航结构**，不自行发明
- 如未发现帮助中心页面 → **跳过此目录，不创建**

**4. Pending Assignment（待分配）**
- 所有无法明确归入以上三个目录的内容，统一放入此目录
- **始终创建**，作为正式兜底目录
- 不预设子目录（运行时动态归入即可）

### 示例目录树

```
Brand Knowledge Base
├── Product Introduction
│   ├── Smart Plugs
│   │   ├── Kasa EP25
│   │   └── Kasa EP40
│   └── Cameras
│       ├── Kasa EC70
│       └── Kasa KC400
├── Brand Policy
│   ├── Warranty Policy
│   ├── Return Policy
│   └── Shipping Policy
├── Help Center
│   ├── Getting Started
│   │   ├── Setup Guide
│   │   └── App Configuration
│   └── Troubleshooting
│       └── Connectivity Issues
└── Pending Assignment
```

### 内部维护 JSON（唯一数据来源）

```json
[
  {"name": "Product Introduction", "children": [
    {"name": "Smart Plugs", "children": [
      {"name": "Kasa EP25"}, {"name": "Kasa EP40"}
    ]}
  ]},
  {"name": "Brand Policy", "children": [
    {"name": "Warranty Policy"}, {"name": "Return Policy"}
  ]},
  {"name": "Help Center", "children": [
    {"name": "Getting Started", "children": [{"name": "Setup Guide"}]}
  ]},
  {"name": "Pending Assignment"}
]
```

命名规则：使用默认标准模板时，4 个一级目录保持英文稳定标识；新建的二级、三级目录使用目标业务语言，品牌名、型号和其他专有名词保留原文。使用用户/SOP schema 时，各层目录名按该 schema 原样保留，只清理接口不支持的非法字符。

---

## §3 交互式确认循环

展示目录树后等待用户反馈，支持以下操作：

| 用户说 | 操作 |
|--------|------|
| "在 [Y] 下面加 [X]" | 在指定父节点下插入 |
| "删掉 [X]" | 删除该节点及其子节点 |
| "把 [X] 改名为 [Y]" | 更新名称 |
| "把 [X] 移到 [Y] 下面" | 重新挂载节点 |
| 「确认」/「没问题」/「开始创建」/「可以创建」 | 进入 §4 |

⚠️ 仅「确认」「没问题」「开始创建」「可以创建」触发创建，「可以」「好」「嗯」不触发。

每次修改后重新渲染完整树并等待确认。未收到明确「确认」前不得继续。

收到明确确认后，用 **write_file 工具** 把当前树写到 `workspace/state/kb-builder/confirmed_tree.json`（固定名）。

---

## §4 批量创建目录

调用 `scripts/create_dirs.py`：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/kb-builder/scripts/create_dirs.py
```

脚本行为：
1. 读 `STATE_DIR/confirmed_tree.json`
2. 深度优先递归创建（先父后子）
3. 同名同 parent 的目录已存在则跳过（幂等）

验证：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-directories --pretty
```

---

## §5 临时补建单个目录

提取 QA 时（PDF / 工单 / 网站产品页）发现品类 / 型号目录在 KB 里缺失，
**不要回头跑全流程目录搭建**，直接用 CLI 补建：

```bash
# 查现有目录拿 parent-id
node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-directories --pretty

# 默认标准模板：在 Product Introduction 下建新品类（parent-id 是 Product Introduction 的 id）
node "<PLUGIN_ROOT>/plugin-cli.mjs" api create-folder --name "Diagnostic Scanners" --parent-id 32188 --pretty

# 在新品类下建型号（parent-id 是上一步返回的 id）
node "<PLUGIN_ROOT>/plugin-cli.mjs" api create-folder --name "AV-D600" --parent-id <new_id> --pretty
```

使用默认标准模板且实在归不进去（罕见）→ 归入 `["Pending Assignment"]`。使用用户/SOP schema 时，按其兜底目录规则处理；没有兜底规则时先向用户确认，不自行添加默认兜底目录。

---

## §6 重命名、移动与删除目录

这三类操作都要先用 `list-directories` 确认目标 ID 和完整路径，展示变更计划并等待用户明确确认。

```bash
# 重命名
node "<PLUGIN_ROOT>/plugin-cli.mjs" api update-directory --id 32188 --name "New name" --pretty

# 移动到另一目录下；移到根层使用 --parent-id 0
node "<PLUGIN_ROOT>/plugin-cli.mjs" api move-directory --id 32188 --parent-id 32000 --pretty

# 递归删除（收到强确认后才能带上 --confirm-delete）
node "<PLUGIN_ROOT>/plugin-cli.mjs" api delete-directory --id 32188 --confirm-delete --pretty
```

移动时默认检查移动后的整棵子树不超过三级，也不允许移到自身或自身子目录下。仅用户明确要求其他层级时使用 `--max-depth`。

**删除目录是级联删除**：后端会递归删除该目录、所有子目录和其中的各类知识。确认前必须展示完整子树、影响的知识数量和代表性标题；不提供“只删目录保留知识”的虚假选项。

展示影响后，必须要求用户回复“我已知晓删除影响并确认删除”或同时表达知晓影响与确认删除的等价语句；英文用户可回复 `I understand the deletion impact and confirm deletion.`。简单的“确认”、`OK` 或“可以”不够。收到强确认后才能在命令中加 `--confirm-delete`。执行后重新查询目录树和知识列表。

---

## §7 常见错误

| 错误 | 正确做法 |
|------|----------|
| 用户已指定 A/B/C 列目录，却额外增加 Product Introduction | 用户 schema 优先，严格按 A/B/C 创建 |
| 默认标准模板下自由发明一级目录名字 | 默认模板一级目录只有四个固定名称 |
| Product Introduction 二级是产品名 | 二级必须是品类，三级才是产品名 |
| Brand Policy 下建了三级目录 | Brand Policy 只到二级 |
| 网站没有帮助中心 / FAQ 却创建了 Help Center | 未发现 support / help / faq / docs 页面时跳过 |
| 跳过用户确认直接 create_dirs | 必须收到明确「确认」才创建 |
| 提取 QA 时品类目录缺失就直接归 Pending Assignment | 优先用 create-folder CLI 补建一级下的子目录 |
