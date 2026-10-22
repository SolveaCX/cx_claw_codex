# VAPI / Twilio 平台数据

本地插件不持有 VAPI/Twilio 长期凭据。优先通过现有语音会话业务 API 和 SLS 取证。

| 平台 | 用途 | 命令 | 使用时机 |
|------|------|------|----------|
| 业务平台 | 会话列表 | `npx --yes @shulex/cxclawctl@latest api list-voice-transcripts` | 按时间、状态缩小范围 |
| 业务平台 | 会话详情 | `npx --yes @shulex/cxclawctl@latest api get-voice-transcript --history-id <historyId>` | 查看 transcript 和已落库平台字段 |
| SLS | provider 日志 | `npx --yes @shulex/cxclawctl@latest sls query ...` | 按 callId/callSid 补齐原始错误 |

## 调用示例

```bash
npx --yes @shulex/cxclawctl@latest api list-voice-transcripts --begin-ts <ms> --end-ts <ms> --pretty
npx --yes @shulex/cxclawctl@latest api get-voice-transcript --history-id <historyId> --pretty
```

## 错误处理

- 业务接口为空：校验环境和时间窗，再按 callId/callSid 查 SLS。
- SLS 也无结果：记录当前证据边界，结论标为“未确认”。

不要猜测未公开 provider 接口，也不要要求用户提供 VAPI/Twilio token。
