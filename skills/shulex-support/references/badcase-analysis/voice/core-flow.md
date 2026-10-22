# 语音 badcase 核心分析流程

## 进入条件

以下任一情况进入语音流程：

1. 用户明确描述语音、电话、VAPI、Twilio、callId、callSid、断音、延迟、STT、TTS、录音、webhook 问题。
2. 文本流程执行 `get-transcript --chat-id <chatId>` 查不到、返回空或 404。

## 核心原则

1. 先确认排查对象：默认沿用当前 badcase 上下文；用户显式指定范围时以用户为准。
2. 先用稳定标识缩小范围：`chatId`、`callId`、`callSid`、`traceId`、电话号码 + 时间段。
3. SLS 通过本机 `npx --yes @shulex/cxclawctl@latest sls query` 直查；语音会话通过 `npx --yes @shulex/cxclawctl@latest api list-voice-transcripts`
   和 `npx --yes @shulex/cxclawctl@latest api get-voice-transcript` 查询，客户端不持有 VAPI/Twilio 长期密钥。
4. 不生成独立语音报告模板；最终按 badcase 回复风格输出。
5. 不要只凭单一数据源下结论，缺失证据必须说明。

## 1. 识别入口

| 输入 | 优先动作 |
|------|----------|
| `chatId` | 查 SLS 定位 callId/callSid/voice trace |
| VAPI `callId` | 查语音会话详情 + SLS callId 相关日志 |
| Twilio `callSid` | 查语音会话详情 + SLS callSid 相关日志 |
| `traceId` / `armsTrace` | 查 SLS 链路日志 |
| 电话号码 + 时间段 | 先要求用户补充时间窗，再查 SLS/VAPI/Twilio |

不确定字段含义时只问一个澄清问题。

## 2. 查询 SLS

读取 `/skills/shulex-support/references/badcase-analysis/voice/sls-playbook.md`。

优先用 chatId/callId/callSid 做最小时间窗查询。连续 3 次空结果停止扩词，避免无节制查询。

## 3. 查询语音平台数据

读取 `/skills/shulex-support/references/badcase-analysis/voice/platform-api.md`。

- 先用 `npx --yes @shulex/cxclawctl@latest api list-voice-transcripts` 缩小范围，再用
  `npx --yes @shulex/cxclawctl@latest api get-voice-transcript --history-id <historyId>` 读取详情。
- 有 `callId` / `callSid` 时同时查 SLS，补齐 provider 原始错误和时间线。
- 当前本地插件不下发 VAPI/Twilio 长期密钥，也不直接请求 provider 私有 API；产品接口和
  SLS 都缺少证据时，明确标为“未确认”，不要要求用户粘贴 token。

## 4. 依赖或配置缺失

读取 `/skills/shulex-support/references/badcase-analysis/voice/dependencies.md`。

## 5. 输出方式

按 badcase 风格回复：

```markdown
## 会话诊断：chatId=<xxx>

### 发生了什么
<一句话描述语音/通话现象>

### 根因
<基于 SLS/VAPI/Twilio 证据解释原因；证据不足时说明未确认>

- **问题层级**：客户端 / Twilio / VAPI / 应用服务 / STT / LLM / TTS / 未确认
- **Log 层**：<关键发现 / 未查询 / 配置缺失>
- **Platform 层**：<VAPI/Twilio 关键发现 / 未查询 / 配置缺失>

### 关键证据
<只列最少必要字段；不要粘贴 token、完整客户号码>

### 建议
1. [可自行调整] <后台配置类建议，如有>
2. [需联系研发] <代码/平台链路问题，如有>

---
以上分析是否符合你的预期？需要更深入排查吗？
```
