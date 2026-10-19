# M11：算法服务通用排查

**职责代码**：ShulexService 的 intent、NER、classification、query rewrite、AI reply、input check、response check 等算法接口。

**服务路径**：`/Users/jianghao/PycharmProjects/ShulexService`

---

## 职责与边界

M11 是算法服务公共兜底手册，用于确认 ShulexService 是否收到请求、入参上下文是否正确、是否发生 fallback / 超时 / ERROR。

优先级：
- 意图识别问题先看 M2，只有确认落到 ShulexService 算法接口时才进入 M11。
- 变量系统 / NER / 分类问题先看 M4，算法侧通用日志再用 M11。
- 知识召回内部逻辑先看 M9；只有 embedding / rerank / LLM fallback 明确落到算法服务时才进入 M11。
- ChatFlow 内部节点问题先看 M10，节点调用算法接口失败时再进入 M11。

不要把所有下游异常都归到 M11；M11 只回答“算法服务这一层是否正常”。

---

## 关键入口

关键 router：

- `app/router/intent_identify.py`
- `app/router/ner.py`
- `app/router/query.py`
- `app/router/reply.py`
- `app/router/check.py`
- `app/router/agent.py`

常见接口 / 能力：

| 能力 | 典型接口或路径 | 常见上游 |
|------|----------------|---------|
| 意图识别 | `/v2/intent_identify`、`/intent_pure` | qa-bot / GPT |
| NER / 实体抽取 | `ner_api/general_ner`、`/ner/text_extract_x` | GPT / tars / chatflow |
| 分类 | `classification_api/batch_classify` | GPT / 变量系统 |
| query rewrite | `/query_rewrite` | GPT / qa-bot / chatflow |
| AI reply | `/ai_reply` | GPT / chatflow |
| 输入检查 | check router | GPT / chatflow |
| 输出检查 | check router | GPT / chatflow |

---

## Trace / 上下文

ShulexService 的上下文由中间件从 body/header 提取：

- `app/middleware/tenant_context.py`
  - `tenant_id`
  - `request_id`
  - `chat_id`
  - `armtrack`
- `app/infra/trace_middleware.py`
  - `traceparent`
  - B3 multi header
  - B3 single header
- `app/infra/http_logging.py`
  - `METHOD path || http_cost_time || ...`

排查时要确认：
- `tenant_id` 是否和 GPT / qa-bot 一致。
- `chat_id` 是否是当前 badcase 的 chatId。
- `request_id` 是否能串起一次算法调用。
- `armtrack` / `armsTrace` 是否能和 GPT 主链路关联。

---

## Log 层

通用日志：

```text
{chat_id} || {request_id} || {api} || request_start
{chat_id} || {request_id} || {api} || request_end
{chat_id} || {request_id} || {api} || ERROR
METHOD path || http_cost_time || ...
llm_call_with_fallbacks
```

查询模板：

```bash
# 按 armsTrace 查算法服务目标接口
cxclawctl sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND (rest:"request_start" OR rest:"request_end" OR rest:"ERROR")' \
  --line 20

# 按 chatId / request_id 兜底
cxclawctl sls query \
  --from <begin> \
  --to <end> \
  --query '(rest:"<chatId>" OR rest:"<request_id>") AND (rest:"request_start" OR rest:"request_end" OR rest:"ERROR")' \
  --line 20

# HTTP 耗时
cxclawctl sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND rest:"http_cost_time"' \
  --line 20

# LLM fallback
cxclawctl sls query \
  --from <begin> \
  --to <end> \
  --query 'armsTrace:"<armsTrace>" AND rest:"llm_call_with_fallbacks"' \
  --line 20
```

按能力缩小查询：

```bash
# 意图识别
--query 'armsTrace:"<armsTrace>" AND (rest:"intent_identify" OR rest:"intent_pure")'

# NER / 实体
--query 'armsTrace:"<armsTrace>" AND (rest:"general_ner" OR rest:"text_extract_x" OR rest:"ner")'

# 分类
--query 'armsTrace:"<armsTrace>" AND (rest:"batch_classify" OR rest:"classification")'

# query rewrite
--query 'armsTrace:"<armsTrace>" AND rest:"query_rewrite"'

# AI reply
--query 'armsTrace:"<armsTrace>" AND rest:"ai_reply"'
```

---

## 常见根因与建议

| 根因 | 建议 |
|------|------|
| 没有 `request_start` | `[需联系研发]` 上游可能未发起调用、trace 未串上，回对应模块确认 GPT / qa-bot / chatflow 调用点 |
| 有 `request_start` 无 `request_end` | `[需联系研发]` 算法接口超时或中途异常，提供 `request_id` 给算法侧 |
| 有 `ERROR` | `[需联系研发]` 提供 ERROR 日志、接口名、request_id、chat_id |
| 入参 tenant / chatId 不一致 | `[需联系研发]` 检查上游透传和 ShulexService tenant_context |
| `llm_call_with_fallbacks` 频繁 fallback | `[需联系研发]` 检查模型供应商、限流、超时和 fallback 配置 |
| `http_cost_time` 明显过高 | `[需联系研发]` 判断算法服务慢、下游模型慢，或上游等待超时 |
| 算法返回空但无 ERROR | `[需联系研发]` 提供入参与输出，交算法侧判断模型效果或阈值 |
| 算法结果正确但 GPT 侧未使用 | 回到对应业务模块：意图回 M2，变量系统回 M4，回复回 M7，ChatFlow 回 M10 |
