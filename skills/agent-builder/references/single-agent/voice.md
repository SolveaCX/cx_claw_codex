# Voice Agent

Voice Agent 是 `SINGLE_AGENT` 的语音特化：`type` 仍为 `SINGLE_AGENT`，通过 `meta.category = "voice"` 进入语音链路。

## 创建结构

```json
{
  "name": "Voice_Support",
  "type": "SINGLE_AGENT",
  "source": "MANUAL",
  "prompt": "Use short, spoken sentences.",
  "displayPrompt": "Use short, spoken sentences.",
  "meta": {
    "category": "voice",
    "version": "v1",
    "assistant": {
      "callType": "INBOUND_PHONE_CALL",
      "firstMessage": "Hello, how can I help?",
      "language": "en-US"
    }
  }
}
```

## 关键字段

| 字段 | 说明 |
|---|---|
| `type` | 固定 `SINGLE_AGENT` |
| `meta.category` | 固定 `voice`，必须在 `meta` 内 |
| `meta.assistant` | 必填，不能为 null |
| `meta.assistant.callType` | `INBOUND_PHONE_CALL` / `OUTBOUND_PHONE_CALL` / `WEB_CALL` |
| `meta.assistant.language` | 语音识别和合成语言 |
| `meta.assistant.firstMessage` | 接通后第一句话 |

## CLI

```bash
npx --yes @shulex/cxclawctl@latest api list-voice-agents --pretty
npx --yes @shulex/cxclawctl@latest api create-agent \
  --data-file /workspace/state/agent-builder/voice_agent_payload.json \
  --pretty
```

更新语音 Agent 前仍然先 `get-agent`，再提交完整对象。
