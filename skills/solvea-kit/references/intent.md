# 意图管理

## 能力概览

创建、查询、更新、启用/禁用 Shulex 策略路由使用的系统意图。

意图（Intent）代表用户的问题类型，如"退款"、"查询订单"。策略路由依赖意图 id 将对话分派给正确的 Agent。

CHAT_FLOW 内的 INTENT 节点直接在节点配置里定义意图（填 name + desc），不需要调用系统意图接口创建。策略路由的意图才需要通过 API 创建。

## API

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 意图列表 | GET | `/api_v2/gpt/project/{pid}/intents` | |
| 创建意图 | POST | `/api_v2/gpt/project/{pid}/intent` | |
| 意图详情 | GET | `/api_v2/gpt/project/{pid}/intent/{id}` | |
| 更新意图 | PUT | `/api_v2/gpt/project/{pid}/intent/{id}` | |
| 启用/禁用意图 | PUT | `/api_v2/gpt/project/{pid}/intent/{id}/status` | |

## CLI

```bash
npx --yes cxclaw@latest api list-intents --pretty

npx --yes cxclaw@latest api get-intent --id <intent_id> --pretty

npx --yes cxclaw@latest api create-intent \
  --data '{"name":"退款","description":"用户要求退款","type":"Other","status":"ENABLED","category":"E_COMMERCE"}'

# 更新意图描述（PUT body 字段是 description，name 必传）
npx --yes cxclaw@latest api update-intent --id <intent_id> \
  --data-file /workspace/state/solvea-kit/intent_update.json

# 短描述可直接使用 --data；长描述先写入 JSON 文件，再通过 --data-file 提交

npx --yes cxclaw@latest api toggle-intent --id <intent_id> --disable
npx --yes cxclaw@latest api toggle-intent --id <intent_id> --enable
```

## update-intent 字段说明（GET / PUT 字段命名不一致，必看）

API 在 GET 和 PUT 之间字段名不对齐，照搬 GET 输出回写会失败：

| GET 返回 | PUT body | 用途 |
|---------|----------|------|
| `name` | `name` | 意图名（必传） |
| **`example`** | **`description`** | 意图描述。GET 返回的 `example` 字段对应 PUT 的 `description`，**不要照搬 GET 字段名** |
| `enableCollect` | `enableCollect` | 一致 |
| `collects` | `collects` | 一致 |
| 其它字段（`callCount` / `createdAt` / `source` 等只读） | 不传 | 服务端维护 |

仅更新描述时，body 最小必填：

```json
{
  "name": "Package issues",
  "description": "...",
  "enableCollect": false,
  "collects": []
}
```

## 原则

- 创建意图前先查 `list-intents`，避免重复创建同名意图
- 更新意图：先 `get-intent` 拿当前 `name`（必传），用 `description` 字段（不是 `example`）写新描述
- CHAT_FLOW 的 INTENT 节点内直接定义意图（`config.intents[]` 的 name + desc），`intents[].intentId` 留空，不要调用 `create-intent` 接口
- 意图 name 建议纯 ASCII，与 INTENT 节点 name 字段约定一致
