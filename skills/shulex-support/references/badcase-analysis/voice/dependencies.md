# 语音排查依赖与降级

## 运行依赖

- SLS：由本机 `cxclawctl sls query` 使用短期只读 STS 直连。
- VAPI/Twilio：由 `$SOLVEA_INTERNAL_PROXY_BASE_URL/voice/...` 提供。
- 沙箱不需要 VAPI CLI、Twilio CLI、aliyun CLI、本地 `.env` 或平台 token。

## 降级规则

| 缺失项 | 降级方式 |
|--------|----------|
| SLS 配置缺失 | 继续查 VAPI/Twilio 平台代理；结论中说明日志证据缺失 |
| VAPI 配置缺失 | 不查 VAPI；继续查 SLS/Twilio |
| Twilio 配置缺失 | 不查 Twilio；继续查 SLS/VAPI |
| callId 缺失 | 优先用 chatId 在 SLS 中定位 callId |
| callSid 缺失 | 优先用 callId/VAPI/SLS 定位 callSid |
| 时间窗缺失 | 向用户追问通话大致时间；不要按电话号码扫全量日志 |

不要让用户在对话中粘贴 token、AccessKey、Twilio Auth Token 或 VAPI API Key。
