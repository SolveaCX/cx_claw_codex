# 语音排查依赖与降级

## 运行依赖

- SLS：由本机 `node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query` 使用短期只读 STS 直连。
- 语音会话：由 `node "<PLUGIN_ROOT>/plugin-cli.mjs" api list-voice-transcripts` / `get-voice-transcript` 查询现有业务 API。
- 沙箱不需要 VAPI CLI、Twilio CLI、aliyun CLI、本地 `.env` 或平台 token。

## 降级规则

| 缺失项 | 降级方式 |
|--------|----------|
| SLS 配置缺失 | 继续查语音会话业务数据；结论中说明日志证据缺失 |
| 语音会话查不到 | 继续查 SLS；不直接访问 VAPI/Twilio 私有 API |
| callId 缺失 | 优先用 chatId 在 SLS 中定位 callId |
| callSid 缺失 | 优先用 callId/VAPI/SLS 定位 callSid |
| 时间窗缺失 | 向用户追问通话大致时间；不要按电话号码扫全量日志 |

不要让用户在对话中粘贴 token、AccessKey、Twilio Auth Token 或 VAPI API Key。
