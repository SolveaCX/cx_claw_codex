# Agent 管理

> 已过时：Agent 构建、修改、复制、语音 Agent、CHAT_FLOW 和工具绑定已迁入 `agent-builder`。本文件仅保留历史兼容，不作为新任务入口。

## 能力概览

| 类型 | 适用场景 | 何时选用 |
|------|---------|---------|
| SINGLE_AGENT | 单一目标：FAQ问答、查询、生成 | 任务目标明确、不超过3个流程分支、一个 Prompt 能说清职责边界 |
| CHAT_FLOW | 多分支流程：意图分类、条件路由、多步骤处理 | 需要条件分支、人工审批、超过3个流程节点，Prompt 无法涵盖 |
| Voice Agent | 语音对话 | 同上，但 category=voice |

CHAT_FLOW 图构建、修改、校验和发布由 `chatflow` skill 维护，本文件不展开节点规则。

---

## SINGLE_AGENT

### 能力

用户输入 → [Prompt + Tools] → LLM 自主推理（可多轮工具调用） → 输出

适用条件：
- 任务目标单一明确（问答、查询、生成）
- 不需要条件分支或人工审批
- 一个 Prompt 能说清职责边界
- 客服FAQ问答、预约助手、数据查询
- 流程不超过3个分支；超过时改用 CHAT_FLOW，太长的 prompt 难以维护

### API

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 列表/详情 | POST | `/api_v2/gpt/ap/queryAgent` | 不返回 chatFlowGraph |
| 创建 | POST | `/api_v2/gpt/ap/createAgent` | |
| 更新 | POST | `/api_v2/gpt/ap/updateAgent` | 必须提交完整对象 |

### CLI

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-agents --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-agent --id <agent_id> --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher api create-agent \
  --data '{"name":"FAQ_Bot","type":"SINGLE_AGENT","prompt":"...","displayPrompt":"..."}' --pretty
```

### 原则

- 更新前必须先 `get-agent` 获取完整对象，`update-agent` 不支持 partial patch
- `prompt` 和 `displayPrompt` 必须同步更新，两者不一致导致执行与展示不符
- `agentId` 字段必须等于 `id`，否则更新失败

## Voice Agent

语音 Agent 与文本 Agent **共用** `POST /api_v2/gpt/ap/createAgent` / `updateAgent` 接口。后端按 `meta.category == "voice"` 分流到语音处理逻辑。语音对话记录走独立 internal API。

### 创建示例

```json
{
  "projectId": 103,
  "name": "Voice_Support",
  "description": "客服语音助手",
  "type": "SINGLE_AGENT",
  "source": "MANUAL",
  "prompt": "你是一个语音客服助手。用简短的口语化句子回答，避免列表和 markdown。涉及专业术语时附上通俗解释。",
  "displayPrompt": "你是一个语音客服助手。用简短的口语化句子回答，避免列表和 markdown。涉及专业术语时附上通俗解释。",
  "meta": {
    "category": "voice",
    "version": "v1",
    "assistant": {
      "callType": "INBOUND_PHONE_CALL",
      "firstMessage": "您好，请问有什么可以帮您？",
      "language": "zh-CN"
    },
    "knowledgeAiReplyPlugin": {
      "type": "KNOWLEDGE_AI_REPLY",
      "meta": {
        "knowledgeAiReplyConfig": {
          "enable": true,
          "directoryIds": [32254, 32255],
          "useAgentPrompt": true
        }
      }
    }
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `projectId` | ✅ | 当前租户 project ID |
| `name` | ✅ | 长度 ≤ 40 |
| `type` | ✅ | 固定 `SINGLE_AGENT`（MULTI_AGENT 后端会拒） |
| `source` | 推荐 | `MANUAL` 区分手动创建；`SYSTEM` 系统自动生成 |
| `prompt` | 可选 | agent 角色/语气/策略。**和 `displayPrompt` 文本必须一致**（不一致执行与展示分裂） |
| `displayPrompt` | 可选 | 同 `prompt`；不传则后端按 `meta.version` 自动用默认模板 |
| `description` | 可选 | agent 描述 |
| `meta.category` | ✅ | 固定 `"voice"`。**必须放 `meta` 里**，顶层不走语音分流 |
| `meta.version` | 推荐 | `"v1"` 走新版默认 prompt（KB_Reply + Transfer_To_Agent 工具引用） |
| `meta.assistant` | ✅ | 整个对象不能为 null，否则 400 `"Assistant config cannot be empty"` |
| `meta.assistant.callType` | ✅ | 枚举：`INBOUND_PHONE_CALL`（入呼）/ `OUTBOUND_PHONE_CALL`（出呼）/ `WEB_CALL`（网页语音） |
| `meta.assistant.firstMessage` | 可选 | 接通后第一句话 |
| `meta.assistant.language` | 可选 | 语言代码，如 `zh-CN` / `ja-JP` / `en-US`，决定语音识别和合成 |
| `meta.assistant.specials[]` | 可选 | 绑定真实电话号码：`[{phoneNumberId, language}]`。`phoneNumberId` 必须存在且未被其它 agent 绑定 |
| `meta.assistant.voiceTone` | 看场景 | 音色配置。**create 不传**（后端不强制）；**update 必传**（含 `voiceId` / `voiceProvider`） |
| `meta.knowledgeAiReplyPlugin` | 可选 | 覆盖后端默认注入的 KB_Reply 内置工具，绑到指定知识库目录 |
| `...knowledgeAiReplyConfig.directoryIds` | 绑 KB 时必填 | 知识库目录 ID 数组（用 `list-directories` 查） |
| `...knowledgeAiReplyConfig.enable` | 绑 KB 时必填 | `true` 启用 KB 检索 |
| `...knowledgeAiReplyConfig.useAgentPrompt` | 推荐 | `true` 让 KB 检索结果用 agent 的 prompt 改写（语气一致） |

> ⚠️ **上表是完整 schema，没列的字段一律不要发明**。出现 400 优先回看上表，**不要靠改字段组合反复试**（见 rules.md §4 调试预算）。

### API 端点

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 列表 | POST | `/api_v2/gpt/ap/queryAgent` | `category=voice` 作为顶层过滤参数 |
| 创建 / 更新 | POST | `/api_v2/gpt/ap/createAgent` 或 `updateAgent` | |
| 对话记录分页 | POST | `/api_v2/as_bot/voice-report/transcript-page` | internal.shulex.com |
| 对话详情 | GET | `/api_v2/gpt/voice/transcript/projectId/{pid}/history/{hid}` | internal.shulex.com |

### CLI

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-voice-agents --pretty

# 创建：payload 存成 json 文件，避免 shell 转义出问题（多语言 prompt 尤其推荐）
$HOME/.codex/cxclaw/bin/cxclaw-launcher api create-agent \
  --data-file /workspace/tmp/voice_agent_payload.json --pretty

$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-voice-transcripts --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-voice-transcript \
  --history-id 019d4dac-aa36-744d-8c5d-d54bc3f7e528 --pretty
```

### 注意事项

- **接口说明**：对话记录接口由 CLI 内部处理域名与鉴权
- **额外 header**：`x-language: cn` + `x-token-domain: .shulex.com`
- **时间戳**：`beginTimestamp` / `endTimestamp` 毫秒级
- 音色 ID 从 `/api_v2/gpt/ap/voiceConfig` 查询，可选条件 gender / language / provider
- `list-voice-agents` 等价于 `list-agents --category voice`
