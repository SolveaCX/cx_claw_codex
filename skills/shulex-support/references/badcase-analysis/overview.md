# Agent 会话诊断入口

**原则**：本文件只做信息收集和文本/语音Agent会话分流。不要在入口文件里展开完整分析流程，不要预加载全部 references。

## 启动时必须收集信息

先从当前消息和会话上下文提取会话标识与问题描述。用户已经给出 ChatId、会话 ID 或外部会话 ID 时直接开始，不要重复询问；缺少会话标识时只补问缺失信息。

用户只提供一个 ID、或明确说这是 chatId / 会话 ID 时，默认进入本流程。只有 `ST...` 开头的 ID，或用户明确提到售后工单、查询工单、追加工单时，才切到售后工单流程。

```text
需要以下信息来帮你诊断这条会话：

1. **chatId / 会话 ID / 外部会话 ID**（必填）：请提供要诊断的会话标识
2. **问题描述**（选填）：这条会话哪里有问题？如果是语音/电话问题，请说明是否有 callId、callSid、VAPI/Twilio 信息。

请提供以上信息后我开始分析。
```

收到会话标识后才执行后续诊断流程。若用户未提供会话标识，不得开始任何数据拉取。

## 分流规则

1. 用户明确提到语音、电话、VAPI、Twilio、callId、callSid、断音、延迟、STT、TTS、录音、webhook：读取 `/skills/shulex-support/references/badcase-analysis/voice/core-flow.md`。
2. 用户描述普通 AI 客服文本回复问题：读取 `/skills/shulex-support/references/badcase-analysis/text/core-flow.md`。
3. 不确定时先按文本流程走：读取 `/skills/shulex-support/references/badcase-analysis/text/core-flow.md`。
4. 文本流程中 `get-transcript --chat-id` 查不到、返回空或 404：停止文本流程，读取 `/skills/shulex-support/references/badcase-analysis/voice/core-flow.md` 做语音兜底排查。

## 读取规则

- 只先读取对应的 `core-flow.md`。
- 其它 references 由 core-flow 指引按需读取。
- 不要使用 `cat` 读取 `/workspace` 或 `/skills` 路径；单纯读文件统一用 read_file 工具。
- 语音排查不生成独立报告模板，最终仍按 badcase 风格说明发生了什么、为什么、关键证据和建议。
