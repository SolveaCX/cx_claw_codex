# SLS 日志查询

文本 badcase 的日志查询统一执行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query`。CLI 完成钉钉员工校验后，默认按生产环境从 `shulex-cloud` 获取 SLS AK/SK；只有用户明确要求测试环境时才传 `--env test`（或 `--env staging`），再由本机使用 `@alicloud/log` 直连 SLS；凭据只驻留当前进程内存，禁止写入文件、日志或普通命令输出。禁止从历史租户会话推断环境。

## 基础用法

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <epoch-seconds> \
  --to <epoch-seconds> \
  --query '<SLS 查询 DSL>' \
  --line 50 \
  --offset 0
```

返回 JSON：`{"count": N, "logs": [{...contents...}, ...]}`

字段说明：

| 字段 | 含义 |
|------|------|
| `fromTime` | 起始时间，epoch 秒 |
| `toTime` | 结束时间，epoch 秒 |
| `query` | SLS 查询 DSL，JSON 字符串内的双引号必须写成 `\"` |
| `line` | 返回条数，默认 50，最大 100 |
| `offset` | 分页偏移，默认 0 |
| `reverse` | 是否按时间倒序，默认 false |

## 时间窗口

会话记录顶层 `createdAt` 是 **epoch 毫秒**（例：`1775793526000`），不是 ISO 字符串。

**必须直接用 epoch 秒**做 `fromTime` / `toTime`（等于 `createdAt // 1000`），避免任何时区歧义：

```bash
# createdAt = 1775793526000 (ms) → 1775793526 (s)
# ±5/10min 窗口
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from 1775793226 \
  --to 1775794126 \
  --query 'rest:"HTTP_ASPECT"' \
  --line 5
```

推荐窗口：`createdAt_sec - 300` ~ `createdAt_sec + 600`（即 -5min ~ +10min）；漏查扩到 `±1800`（±30min）。

**不要用 ISO 字符串**：CLI 只接受 epoch 秒。会话记录没有 ISO 格式，人工转换容易踩时区坑（例如 `1775793526000` 转 UTC 是 03:58，而 SLS 控制台里你看到的是 CN 本地时间 11:58，差 8 小时），一旦转错就查不到日志。

## 定位 trace

chatId → trace 一对一。先查 HTTP 入口 aspect 拿到 trace：

> ⚠️ **禁止使用会话记录返回的 `traceId` 字段**——该值不可信，必须通过下面的 HTTP_ASPECT 查询重新定位 trace。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <createdAt_sec - 300> \
  --to <createdAt_sec + 600> \
  --query 'rest:"HTTP_ASPECT" AND rest:"<chatId>" AND (rest:"/bot/<botId>/chat " OR rest:"/bot/<botId>/chat/async" OR rest:"/bot/<botId>/chat/stream")' \
  --line 5
```

- chatId 在 `rest` 字段里（不是 `ext_2`）
- 结果中 `trace` 字段即后续所有查询的 trace 值
- 查询约束（次数上限、止损规则、DSL 规范）见 `/skills/shulex-support/references/badcase-analysis/text/log-query-rules.md`

## 跨服务 trace 拼接（qa-bot / ShulexService / chatflow / tars）

文本主链路以 `shulex-gpt` 为入口，qa-bot、ShulexService、chatflow、tars 都是 GPT 发起的下游调用。业务 `trace-id` 通过 HTTP header 透传时可能因异步 / 切线程而衰减，跨服务关联**优先以 `armsTrace` 为准**（SLS 自动注入字段）；目标服务没有 `armsTrace` 时，再用 `chatId` / `request_id` / `tenant_id` / 接口路径 / 时间窗兜底。

> ⚠️ **armsTrace 字段名首次使用时务必实测验证**：本文件中所有 `armsTrace` 字段名均按用户口述写入；如 SLS 控制台实际字段名不是 `armsTrace`（例如 `arms_trace` / `ARMS_Trace`），把本节及 `m9-knowledge-search.md` 中所有出现处一次性替换。

### 标准三步

```bash
# Step A：和同步路径一样，先用 chatId 拿 shulex-gpt 侧业务 trace
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <createdAt_sec - 300> \
  --to <createdAt_sec + 600> \
  --query 'rest:"HTTP_ASPECT" AND rest:"<chatId>" AND (rest:"/bot/<botId>/chat " OR rest:"/bot/<botId>/chat/async" OR rest:"/bot/<botId>/chat/stream")' \
  --line 5
# → trace = trace_GPT；同时记录该日志的 armsTrace 字段值

# Step B：用 trace_GPT 拉一条 shulex-gpt 业务日志，取其 armsTrace
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <createdAt_sec - 300> \
  --to <createdAt_sec + 600> \
  --query 'trace:"<trace_GPT>" AND rest:"aiReply["' \
  --line 3
# → 取返回 JSON 第一条的 armsTrace 字段值，记为 armsTrace_X
# → 如 aiReply 不存在（未走知识召回），换 shulex-gpt 侧任意业务日志关键字（如 rest:"BOT_REPLY" 或 rest:"chat["），目的只是拿到 armsTrace

# Step C：用 armsTrace_X 查目标下游服务日志
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <createdAt_sec - 300> \
  --to <createdAt_sec + 600> \
  --query 'armsTrace:"<armsTrace_X>" AND rest:"searchKnowledge["' \
  --line 5
# → 命中即说明跨服务拼接成功，后续下游模块查询都优先用此 armsTrace
```

### qa-bot（M2 意图 / M9 知识）

```bash
# qa-bot 知识召回
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"searchKnowledge[" OR rest:"rerankKnowledge[" OR rest:"embeddingSearchAsync[")' \
  --line 20

# qa-bot 意图识别
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"intentParse" OR rest:"checkIntent" OR rest:"intentIdentify[")' \
  --line 20

# qa-bot 兜底：armsTrace 不可用
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'rest:"<chatId>" AND (rest:"searchKnowledge[" OR rest:"intentIdentify[" OR rest:"checkIntent")' \
  --line 20
```

### ShulexService（M2 / M4 / M11）

```bash
# ShulexService 通用 request_start / request_end / ERROR
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"request_start" OR rest:"request_end" OR rest:"ERROR" OR rest:"http_cost_time")' \
  --line 20

# ShulexService 按能力缩小
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"intent_identify" OR rest:"intent_pure" OR rest:"general_ner" OR rest:"batch_classify" OR rest:"query_rewrite" OR rest:"ai_reply")' \
  --line 20

# ShulexService 兜底：request_id / chatId
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query '(rest:"<request_id>" OR rest:"<chatId>") AND (rest:"request_start" OR rest:"request_end" OR rest:"ERROR")' \
  --line 20
```

### chatflow（M10）

```bash
# chatflow graph / node / condition
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"graph_exec" OR rest:"node_enter" OR rest:"evaluate_condition" OR rest:"case_matched" OR rest:"no_case_matched")' \
  --line 20

# chatflow RAG / KB / tool / variable
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"rag_reply retrieve" OR rest:"kb_reply retrieve" OR rest:"tool_node" OR rest:"selected variable not found")' \
  --line 20

# chatflow 兜底：chatId + 节点关键字
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'rest:"<chatId>" AND (rest:"graph_exec" OR rest:"node_enter" OR rest:"tool_node")' \
  --line 20
```

### 质检（M12）

先在 GPT 侧确认该轮是否进入后置质检；只有会话记录不足以判断送检、命中或调用失败时才查。`quality-inspection-gate` 是服务端灰度/过滤开关，只能作为“是否可能送检”的运行线索，不能据此改动或推断租户规则。

```bash
# GPT 回复后质检：实时送检、回复送检、结果与豁免
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'trace:"<trace_GPT>" AND (rest:"QualityCheckPostCheck" OR rest:"realTimeInspection" OR rest:"replyInspection" OR rest:"inspectionDataResponse" OR rest:"quality-inspection-gate" OR rest:"exempt_request" OR rest:"exempt_ai_reply")' \
  --line 20

# trace 缺失时用 chatId 在 GPT 侧兜底；命中调用异常后再按 armsTrace 查 Intelli
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'rest:"<chatId>" AND (rest:"realTimeInspection" OR rest:"replyInspection" OR rest:"inspectionDataResponse" OR rest:"QualityCheckPostCheck")' \
  --line 20
```

从 GPT 日志取得 `armsTrace` 后，再以该值和 `realTimeInspection` / `replyInspection` / `ERROR` 查询 Intelli 侧 HTTP 调用与异常。不要在没有会话或日志事实时，根据当前质检规则倒推历史是否命中。

### tars（M4 变量系统）

```bash
# tars 变量系统字段抽取
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace_X>" AND (rest:"/service/field/internal/extract" OR rest:"AiFieldExtractService #")' \
  --line 20

# tars 兜底：chatId + 变量系统日志
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'rest:"<chatId>" AND (rest:"AiFieldExtractService #" OR rest:"extract aiFieldExtractDTO" OR rest:"extract result aiFieldDbDTOList")' \
  --line 20
```

### 失败兜底

- Step C 或服务模板命中为 0：
  1. 检查字段名是否真为 `armsTrace`（注意大小写 / 真实字段名）
  2. 时间窗是否覆盖下游调用时刻（±30s 通常足够，最大放宽到 ±30min）
  3. 该会话是否真正走到了目标服务（参考会话记录的 `reason` / `type` / `chatflow_run_info` / GPT 侧调用日志）
- 上述均无果 → 退回 GPT 侧结论，按 `log-query-rules.md` 的「连续 3 次空止损」执行，**不再继续追深下游服务**

### 配额

- Step A / B / C 均算入单轮 20 次硬上限
- 每个跨服务模块自身的日志查询同样计入；**建议每个模块 ≤ 6 次查询**

## 异步路径（/chat/async）

Kafka 生产端和消费端是**两条独立的 trace**，不能跨 Kafka 传播。但 SLS 日志里有 `span` 字段可以把两段串起来。

分三步：

```bash
# 1a 定位入口请求，拿到 span
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <createdAt_sec - 300> \
  --to <createdAt_sec + 600> \
  --query 'rest:"HTTP_ASPECT" AND rest:"<chatId>" AND rest:"/bot/<botId>/chat/async"' \
  --line 2
# → 记录返回字段 span

# 1b 用 span 找消费端 trace
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <createdAt_sec - 300> \
  --to <createdAt_sec + 1800> \
  --query 'span:"<span>"' \
  --line 5
# → 消费端日志的 trace 字段就是后续 M2~M8 查询用的 trace

# Step 2 起：跟同步完全一样，trace 用消费端那条
```

- `trace_A`（入口）仅用于检查「请求到了 / 生产 Kafka 成功没」，不做 M2~M8 查询
- `trace_B`（消费端）是 M2~M8 日志真正落在的 trace
- `trace_A.timestamp` 与 `trace_B.timestamp` 差值 ≈ 消息在 Kafka 里的排队时间
- 1b 查不到 → 消费端没触达（积压 / consumer group 故障 / 反序列化异常），回到 1a 时间窗附近查 `severity:"ERROR"`

## 通用模板（按 trace 查）

```bash
# 模块相关日志
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'trace:"<trace>" AND rest:"<关键字>"' \
  --line <N>

# 所有 ERROR（M8 系统异常排查用）
node "<PLUGIN_ROOT>/plugin-cli.mjs" sls query \
  --from <begin> \
  --to <end> \
  --query 'trace:"<trace>" AND severity:"ERROR"' \
  --line 20
```

## 配置缺失处理

认证错误统一按 `cxclawctl` skill 的登录流程处理，不在本流程重复定义。查询默认使用生产环境，测试环境查询才显式传 `--env test`；需要单独诊断登录状态时运行
`node "<PLUGIN_ROOT>/plugin-cli.mjs" auth status`。若返回 SLS 配置缺失，检查目标环境的 Nacos 配置。SLS 长期 AK/SK 由 `shulex-cloud`
按环境读取，并在钉钉员工校验通过后下发；凭据只驻留 CLI 当前进程内存。
