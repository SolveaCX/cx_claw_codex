# VAPI / Twilio 内部代理接口

沙箱不直接调用 VAPI/Twilio CLI，不持有平台 token。所有平台查询都调用主服务内部代理。

| 平台 | 用途 | 命令 | 使用时机 |
|------|------|------|----------|
| VAPI | call 详情 | `GET /voice/vapi/calls/<callId>` | 已有 VAPI callId 时 |
| VAPI | call 日志 | `GET /voice/vapi/calls/<callId>/logs` | 需要平台原始事件/错误时 |
| Twilio | call 详情 | `GET /voice/twilio/calls/<callSid>` | 已有 Twilio callSid 时 |
| Twilio | 录音列表 | `GET /voice/twilio/calls/<callSid>/recordings` | 需要确认录音/时长时 |
| Twilio | 事件列表 | `GET /voice/twilio/calls/<callSid>/events` | 需要确认平台事件/错误码时 |

## 调用示例

```bash
curl -sS "$SOLVEA_INTERNAL_PROXY_BASE_URL/voice/vapi/calls/<callId>"
curl -sS "$SOLVEA_INTERNAL_PROXY_BASE_URL/voice/vapi/calls/<callId>/logs"
curl -sS "$SOLVEA_INTERNAL_PROXY_BASE_URL/voice/twilio/calls/<callSid>"
curl -sS "$SOLVEA_INTERNAL_PROXY_BASE_URL/voice/twilio/calls/<callSid>/recordings"
curl -sS "$SOLVEA_INTERNAL_PROXY_BASE_URL/voice/twilio/calls/<callSid>/events"
```

## 错误处理

- `{"error":"voice proxy config missing"}`：主服务缺平台配置，降级为 SLS + 已知输入排查，不要求用户提供 token。
- `{"error":"voice upstream request failed"}`：平台接口失败，记录 status/detail，继续用其它证据排查。

不要猜表外接口；遇到 404/502 时停止该平台分支，改查 SLS 或向用户要更多标识。
