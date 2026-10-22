# 产品知识创建与更新

本 reference 只用于界面上的“产品”知识。对客户使用“产品 / Products”，不暴露内部实体名。

## 创建

创建计划写入 `/workspace/state/kb-builder/product_create.json`。至少包含：

- `title`：产品名称
- `spuUrl`：产品页地址，同一项目内不能重复

常用可选字段包括 `describe`、`image`、`price`、`compareAtPrice`、`currency`、`skuList`、`directoryId`、`metadata`、`specialTagMap`、`published`和 `isVisible`。CLI 默认补齐手工创建来源、已发布和已显示；如果用户要求其他状态，在计划中显式写出。

```bash
npx --yes cxclaw@latest api create-product-knowledge --data-file /workspace/state/kb-builder/product_create.json --pretty
```

## 更新

产品更新接口要求完整产品数据。使用下面的 CLI 时，它会先读取现有产品，再将变更字段合并到完整对象后提交，避免清空 SKU、图片、目录或状态。

只将要改的字段写入 `/workspace/state/kb-builder/product_update.json`，展示字段级 diff 并等待确认，然后执行：

```bash
npx --yes cxclaw@latest api update-product-knowledge --id 3057823 --data-file /workspace/state/kb-builder/product_update.json --pretty
```

如果现有产品缺少后端更新所必需的标题、描述、产品地址、图片、来源、发布状态或可见性，CLI 会拒绝提交并列出缺失字段；先让用户补齐，不自行编造。更新后用 `get-knowledge --type PRODUCT` 重新读取核对。

## 批量更新产品状态

当需要批量设置多个产品的状态（如批量设为主推、批量启用/停用）时，使用 `batch-update-products` 命令：

将批量计划写入 `/workspace/state/kb-builder/batch_products_update.json`：

```json
[
  { "id": 3057823, "mainPush": true },
  { "id": 3057824, "enable": false }
]
```

执行批量更新：

```bash
npx --yes cxclaw@latest api batch-update-products --data-file /workspace/state/kb-builder/batch_products_update.json --pretty
```

- 每条记录支持 `id`（或 `kuProductId`）、`mainPush`（主推）、`enable`（或 `published`）。
- **注意**：该批量接口仅用于更新商品的主推与启停状态；若需修改商品标题、描述、价格或 SKU 等内容，请使用单条 `update-product-knowledge`。

产品的删除、移动、发布/下架、显示/隐藏统一按 [`knowledge.md`](knowledge.md) 的 `operate-knowledge` 流程执行。
