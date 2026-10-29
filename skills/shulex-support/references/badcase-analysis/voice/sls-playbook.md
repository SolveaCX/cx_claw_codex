# 语音链路 SLS 查询 Playbook

所有 SLS 查询都通过本机 `node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query`，完成钉钉员工校验后按环境获取 `shulex-cloud` 下发的 SLS AK/SK 并直连阿里云，不经过业务服务查询代理。默认查询生产环境；只有测试环境查询才显式传 `--env test`。

## 基础模板

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
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
