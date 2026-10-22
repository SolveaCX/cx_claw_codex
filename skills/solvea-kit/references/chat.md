# 对话测试

> 已过时：POC 测试走 `poc`，交付回归走 `delivery`，原始会话与运营数据走 `agent-analytics`，badcase 上下文排查走 `shulex-support` 的 Agent 会话诊断场景，CHAT_FLOW 测试注意事项走 `agent-builder`。本文件仅保留历史兼容，不作为新任务入口。

## 单轮测试

### API

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 对话测试 | POST | `/api_v2/gpt/bot/{botId}/chat` | 单轮或多轮（传 chatId） |

### CLI

```bash
npx --yes cxclaw@latest api chat -m "你好" --pretty
```

---

## 多轮测试（Session）

多轮对话时，每轮请求必须传入上一轮返回的 `chatId`，否则每次开新会话、上下文断开。

### CLI

```bash
npx --yes cxclaw@latest api chat -m "你好" --pretty
# 从返回中取 chatId
npx --yes cxclaw@latest api chat -m "继续问" --chat-id <上轮chatId> --pretty
```

### Python 示例

```python
from client import SolveaClient
client = SolveaClient()

r1 = client.chat("你好")
chat_id = r1.get("chatId")
r2 = client.chat("继续问", chat_id=chat_id)
```

### 对话详情与 Badcase 溯源

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 收件箱列表 | POST | `/api_v2/gpt/project/{pid}/transcripts/filter` | 返回会话摘要，不含完整内容 |
| 对话详情（按 chatId） | GET | `/api_v2/gpt/project/{pid}/transcript/{chatId}?isCompare=true` | 获取单条完整对话 |
| Badcase 溯源（按轮次） | POST | `/api_v2/gpt/bot/{botId}/chat/context/compare` | 返回检索知识、tool call 详情、最终 answer |

```bash
npx --yes cxclaw@latest api list-transcripts --pretty
```

Badcase 分析标准流程：
1. `get-transcript --chat-id <chatId>` — 获取完整对话数据，定位问题轮次
2. `get_chat_context_compare(bot_id, turn_data)` — 传入该轮 context，返回检索知识、tool call 详情、最终 answer

---

## CHAT_FLOW Agent 测试注意事项

CHAT_FLOW Agent 不能用 `metadata.specified_agent_id`（或老版 `specified_agent_data`）这类强制 agent 路由直接测试，必须通过策略路由。

完整测试流程：
1. 创建意图（`create-intent`）
2. 创建策略（`create-strategy`），将意图路由到目标 CHAT_FLOW Agent
3. 启用策略（`toggle-strategy --enable`）
4. 编写测试用例 JSON
5. 运行当前业务 skill 指定的测试 runner
6. 根据失败项调整 Agent → 重跑测试直到通过率达标

---

## 批量测试

> POC 测试业务流程归属 `poc` skill，交付回归业务流程归属 `delivery` skill。
> 测试 runner 已归属到对应业务 skill。

### 用法

```bash
# POC 测试：先读 /skills/poc/interfaces/poc-test.md
# Delivery 回归：先读 /skills/delivery/interfaces/delivery-test.md

# 校验 chatflow 图结构（chatflow 能力在 agent-builder skill 下）
npx --yes cxclaw@latest script skills/agent-builder/scripts/chatflow/validate_graph.py --data-file graph.json
```

### 测试用例格式（JSON Schema）

```json
[
  {
    "name": "测试名称",
    "category": "分类",
    "messages": ["用户消息1", "用户消息2（多轮）"],
    "expected": {
      "intent": "期望意图名（模糊匹配）",
      "content_contains": ["回复须包含的关键词"],
      "content_not_contains": ["回复不应包含的关键词"],
      "handoff": false,
      "flow_status": "success",
      "nodes_executed": ["REPLY", "AGENT"]
    }
  }
]
```

### expected 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `intent` | string | 期望意图名，模糊匹配 |
| `content_contains` | string[] | 回复内容必须包含的关键词列表 |
| `content_not_contains` | string[] | 回复内容不应包含的关键词列表 |
| `handoff` | boolean | 是否期望转人工 |
| `flow_status` | string | 期望流程状态，如 `"success"` |
| `nodes_executed` | string[] | 期望执行的节点类型列表 |

### 含节点执行检查的测试用例示例

```json
{
  "name": "修改地址-完整流程",
  "messages": ["I want to change my address for order 12345"],
  "expected": {
    "intent": "Modify Order",
    "flow_status": "success",
    "nodes_executed": ["REPLY", "AGENT"],
    "content_contains": ["address"]
  }
}
```

### 自动判定为失败的条件

以下情况无论回复内容如何，测试工具自动判定为失败：
- 回复内容为 `INTERNAL_ERROR`
- `response.type` 为 `STOPPED` 或 `CONFUSED`

## 自动化测试闭环

用真实对话数据验证 Agent 配置效果，替代人工编写测试用例。

```
Step 1: 拉取真实对话数据
  client.export_transcripts() → 轮询 → 下载 xlsx
  （可选）client.list_intents/list_agents/list_plugins

Step 2: 转化为测试用例
  从 inbox 提取每条对话的用户消息序列（按提问顺序）
  单轮对话 → messages: [首条消息]
  多轮对话 → messages: [消息1, 消息2, ...]（保持原始顺序）

Step 3: 批量测试
  POC 按 /skills/poc/interfaces/poc-test.md
  Delivery 按 /skills/delivery/interfaces/delivery-test.md
  检查：意图识别、节点执行链路、INTERNAL_ERROR、回复质量

Step 4: 分析结果 → 生成优化方案
  - 意图误识别 → 调整意图 description
  - 节点执行失败 → 修复 CHAT_FLOW 图
  - 回复不准确 → 调整 Agent prompt
  - 策略未命中 → 修复策略条件
  列出待修改清单，和用户确认后自动执行

Step 5: 自动执行修改
  用户确认后，调 API 更新意图/策略/Agent

Step 6: 重新测试
  再次运行 batch test，对比前后通过率
  循环 Step 4-6 直到达标
```

### 从线上导出 inbox 数据

```python
from client import SolveaClient
import time

client = SolveaClient()

# 1. 提交导出任务（默认近 1 个月）
result = client.export_transcripts(page_size=1000, time_offset=8)
task_id = result.get("taskId")

# 2. 轮询任务状态
while True:
    tasks = client.get_export_tasks()
    task = next((t for t in tasks if str(t["id"]) == str(task_id)), None)
    if task and task["status"] == "SUCCESS":
        file_url = task["file"]
        break
    time.sleep(5)

# 3. 下载 xlsx 并读取
# curl -o /tmp/inbox_export.xlsx '<file_url>'
```

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 提交导出任务 | POST | `/api_v2/gpt/project/{pid}/transcripts/export/async` | |
| 轮询导出状态 | POST | `/api_v2/gpt/label/project/{pid}/getLabelTask` | status=SUCCESS 时取 file URL |

```bash
npx --yes cxclaw@latest api export-transcripts --pretty
npx --yes cxclaw@latest api get-export-tasks --pretty
```

### 转化真实数据为测试用例

```python
test_cases = []
for conversation in inbox_data:
    user_messages = [msg["content"] for msg in conversation["messages"]
                     if msg["role"] == "user"]
    if user_messages:
        test_cases.append({
            "name": f"real_{conversation['id']}",
            "category": "production_data",
            "messages": user_messages,
            "expected": {}
        })
```

### 优化调整规则

1. 意图误识别率 > 10% → 修改意图 description，扩展或收窄匹配范围
2. 策略未命中 → 检查条件规则，修复 apiName/relation/values
3. INTERNAL_ERROR → 检查 CHAT_FLOW 图结构（validate_graph）
4. 回复不准确 → 调整 prompt，增加业务规则说明
5. 多轮断开 → 检查 maxRounds 配置

---

## 原则

- 多轮对话必须传 chatId，否则每次开新会话、上下文断开
- 测试驱动配置：配置 Agent 后必须通过批量测试验证，不能只配置不测试
- 测试用例必须覆盖 CHAT_FLOW 的每一个流程节点和分支，包括负面用例（不应匹配的意图）
- 仅检查回复内容不够，CHAT_FLOW 测试必须同时检查 `nodes_executed` 和 `flow_status`
- 每次调整后必须重跑测试，对比通过率变化
