# 语音链路 SLS 查询 Playbook

所有 SLS 查询都通过本机 `${PLUGIN_ROOT}/bin/cxclaw-launcher sls query` 使用 `shulex-cloud` 下发的短期只读 STS 直连阿里云，不经过业务服务查询代理。

## 基础模板

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher sls query \
  --from <epoch-seconds> \
  --to <epoch-seconds> \
  --query 'rest:"<keyword>"' \
  --line 50 \
  --offset 0
```

## 查询策略

| 标识 | 查询策略 |
|------|----------|
| `chatId` | `rest:"<chatId>" AND (rest:"callId" OR rest:"callSid" OR rest:"voice")` |
| `callId` | `rest:"<callId>"`，必要时加 `severity:"ERROR"` |
| `callSid` | `rest:"<callSid>"`，必要时加 `rest:"Twilio"` |
| `trace` | `trace:"<trace>"` |
| `armsTrace` | `armsTrace:"<armsTrace>"`，字段名首次使用需用实际日志验证 |

## 止损规则

- 单轮语音排查 SLS 查询最多 20 次。
- 连续 3 次 `count=0` 停止扩词。
- 查询不到时先检查时间窗、字段名、环境，不要直接下根因结论。
- 配置缺失时，降级为语音会话业务数据 + 已知输入排查。
