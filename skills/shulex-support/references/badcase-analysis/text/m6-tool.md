# M6：工具调用模块

**职责**：SINGLE_AGENT / CHAT_FLOW 中对 EXTERNAL_HTTP_CALL 工具的执行。

---

## 核心逻辑

### SINGLE_AGENT 路径（主要路径）

```
executeAgent() → function_call 消息 → callPluginId → 找 usedPlugins
  → plugin.type == EXTERNAL_HTTP_CALL:
      HttpParamUtils.updateArguments() → 更新参数（绑定 metadata 值）
      → 发起 HTTP 请求（带 headerParams 认证）
      → 解析 resultStr → 写入 toolResponse(metadata)
      → 下一循环继续
```

**参数来源（`source`）**：
- `LLM`：由 LLM 从对话上下文推断
- `CUSTOMIZE`：固定值（`value` 或 `ref`）
- `METADATA`：从 metadata（ai_fields）读取

### CHAT_FLOW 路径

```
ChatFlowService.callTool(request)
  → EXTERNAL_HTTP_CALL → callExternHttp()
  → KNOWLEDGE_AI_REPLY → callKnowledgeReply()
  → TEMPLATE_REPLY → callTemplateReply()
```

---

## 信号判断

从会话记录读取：

| 信号 | 含义 |
|------|------|
| `ai_fields.xxx = null` | `source=LLM` 参数无法填充 |
| SINGLE_AGENT 循环次数多但无结果 | 工具反复调用未成功 |
| CHAT_FLOW: chatflow_run_info 中 TOOL 节点 `status=failed` | 工具执行失败 |

---

## Config 层

```bash
# 查工具列表（精简信息）
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-plugins --pretty

# 查工具详情（request/response params、actionStatus）
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-plugin --id <tool_id> --pretty

# 查变量系统字段（LLM source 的参数需要对应变量系统字段）
$HOME/.codex/cxclaw/bin/cxclaw-launcher api list-ai-fields --pretty
```

检查点：
- `requestParam.items` 中 `required=true & source=LLM` 的参数：是否有对应变量系统字段？
- `responseParam.items`：映射路径是否与实际接口响应匹配？
- 接口地址、认证 header 是否正确？

---

## Log 层

### SINGLE_AGENT

```bash
# 工具调用结果（request + response）
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"call tool, currentLoopCount"' --line 10
# → pluginName, request（入参）, response（出参）
```

**精确日志字符串**：
```
executeAgent[<chatId>]: call tool, currentLoopCount={}, pluginName={}, request={}, response={}
executeAgent[<chatId>]: call plugin, currentLoopCount={}, arguments={}, headers={}, httpResult={}, plugin={}
```

### CHAT_FLOW

```bash
# callTool 入口和出口
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"chatflow callTool"' --line 15

# HTTP 工具详情
$BASE --from $BEGIN --to $END \
  --query 'trace:"<trace>" AND rest:"chatflow call http tool"' --line 15
```

**精确日志字符串**：
```
chatflow callTool request={}                      ← 完整入参
chatflow callTool chatId={} ...                   ← 完整出参
chatflow call http tool, toolId={}, chatId={}, url={}, method={}, params={}, inputs={}
chatflow call http tool, toolId={}, chatId={}, resultStr={}
chatflow callTool error chatId={}                 ← 异常
```

---

## 常见根因与建议

| 根因 | 建议 |
|------|------|
| `source=LLM` 参数提取失败（null） | 优化变量系统字段 prompt；或改为 `METADATA` source |
| HTTP 接口返回错误 | 检查接口鉴权、URL、参数格式 |
| responseParam 路径映射错误 | 对照实际 HTTP 响应修正路径 |
| SINGLE_AGENT 工具循环（参数反复错误） | 检查 arguments 是否每轮都相同，找循环根因 |
