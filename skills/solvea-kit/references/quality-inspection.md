# AI 质检管理

本模块管理系统的 AI 质检开关、系统规则、自定义规则和预警。质检结果运营分析仍由 `agent-analytics` 负责；这里仅在用户要调整配置或查看规则命中时使用。

## 查询与总开关

先读取现状。开启或关闭会影响项目后续 Agent 回复的质检行为，必须说明影响并在用户确认后写入：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-quality-status --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-quality-rules \
  --begin-ts <epoch_ms> --end-ts <epoch_ms> --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api set-quality-status --enable --pretty
```

关闭时使用 `--disable`。不要修改 GPT 的 Nacos `quality-inspection-gate`；它是平台灰度与消息过滤配置，不是租户可管理的质检开关。

## 系统规则

先读取规则清单与详情，再展示将要修改的范围、识别/拦截动作、启停状态和适用 Agent。系统规则只能更新，不能删除或更改为自定义规则：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-quality-rule \
  --inspection-key <rule_key> --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-quality-rule \
  --data-file /workspace/state/solvea-kit/quality_rule_update.json --pretty
```

## 自定义规则

自定义规则可包含以下配置：

- `name`：规则名称
- `customPrompt`：自然语言质检要求
- `words`：敏感词数组；可与 `customPrompt` 二选一或同时使用
- `scope`：`0` 客服回复、`1` 客户来信、`2` 全部消息
- `type`：`1` 仅识别、`2` 拦截；`scope=2` 时只能使用仅识别
- `checkAllAgent`、`agentIds`、`autoAddAgent`：适用 Agent 范围
- `filterAmazon`：是否过滤 Amazon 场景

先生成 JSON 并向用户展示，确认后再创建、更新或删除：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api create-custom-quality-rule \
  --data-file /workspace/state/solvea-kit/custom_quality_rule_create.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-custom-quality-rule \
  --inspection-key <rule_key> --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-custom-quality-rule \
  --data-file /workspace/state/solvea-kit/custom_quality_rule_update.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api delete-custom-quality-rule \
  --inspection-key <rule_key> --pretty
```

不要自行把规则设为拦截；用户没有明确要求时默认建议“仅识别”。删除规则前必须说明该规则将停止对后续消息生效。

## 预警

预警规则关联一个或多个质检规则，并可配置即时或每日汇总、邮箱或机器人 Webhook 通知。Webhook 和邮箱地址属于敏感配置：展示时脱敏，更新前必须确认。

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-quality-alert-rules --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-quality-alert-rule --id <alert_id> --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api create-quality-alert-rule \
  --data-file /workspace/state/solvea-kit/quality_alert_create.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-quality-alert-rule \
  --data-file /workspace/state/solvea-kit/quality_alert_update.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api delete-quality-alert-rule --id <alert_id> --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-quality-alert-messages \
  --data-file /workspace/state/solvea-kit/quality_alert_messages_query.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-quality-alert-message --id <message_id> --pretty
```

## 结果排查边界

规则命中趋势和汇总可通过 `report-inspection` / `report-inspection-history` 查询；要分析具体会话或质检判断原因，转 `agent-analytics`。Agent 回复后的运行质检由 GPT 调 Intelli 执行，字段配置由 Tars 管理，不要跨这两个边界猜测数据来源。
