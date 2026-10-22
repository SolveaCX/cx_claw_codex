# M9：知识召回排查

M9 负责判断知识在 query、范围、候选召回、排序、过滤和上下文组装中的问题。知识已经正确进入上下文但回复仍错误时，转 M7 分析 Prompt、LLM 生成和后处理。

ChatFlow 场景先按 M10 读取 graph，确认实际节点配置和知识目录，再进入本模块判断知识链路。

## 诊断顺序

### 1. 对齐问题和目标轮次

先写清用户原问题、实际回复和预期回复。知识排查必须回答具体差异，不能只罗列召回 ID 和分数。

从目标回复的 `messages[].context` 读取：

- `mixedQuery.originTitle/originContent`：原始用户问题。
- `mixedQuery.userQuery/userEnQuery`：召回和 rerank 使用的用户 query。
- `mixedQuery.knowledgeQuery/knowledgeEnQuery`：知识检索改写结果。
- `intents`、变量系统字段和前置轮次：判断 query 是否被错误上下文带偏。

原问题与知识 query 语义不一致时，优先定位 query rewrite / 多轮上下文问题，不直接修改知识。

### 2. 确认调用路径和检索范围

检查：

- `touchPoint`：livechat 与非 livechat 的相关性判断配置可能不同。
- `directoryIds`：Agent、策略或 ChatFlow 节点限定的目录。
- `metadata.ai_fields`：pn、pdt 等变量系统字段可能影响 query、目录和字段加权。
- `useQa/useDoc/useProduct`：是否启用 QA、文档和商品召回。
- ChatFlow：按 M10 从 graph 读取知识节点的真实目录和参数；会话记录只说明实际执行过哪些节点。

目录过宽会引入噪音，目录过窄会漏召回。不能只看到某条无关知识就断言 rerank 失败。

### 3. 区分候选、排序和实际使用结果

QA 主要看 `retrievedKus`。其中 `retrievedKus[].title/content` 是历史运行时保存的知识内容，先用它还原当时模型实际看到的证据：

| 字段 | 含义 |
|------|------|
| `score` | ES / 混合召回阶段分数，不能跨模式直接比较 |
| `rerankScore` | rerank 分数 |
| `relevantScore` | 可选的相关性判断分数 |
| `rank` | rerank 后排名 |
| `effect` | 是否最终进入知识上下文；受相关性、TopN 和 token 预算影响 |
| `title/content` | 真实进入判断的知识内容 |
| `directoryId/tags/conditionTags` | 目录和标签线索 |

文档看 `documentQaContext` 中的 used chunks、chunk 内容和 `usedDocuments`；商品看 `recommendProductContext.usedProducts`。只出现文件名不代表整份文件都进入 Prompt，应尽量确认实际 chunk。

需要判断知识当前是否仍有问题，或准备给出修改方案时，再按知识 ID 读取当前知识详情：

```bash
npx --yes cxclaw@latest api get-knowledge --id <knowledge_id> --pretty
```

报告中明确区分“历史运行时内容”和“当前知识详情”。`list-knowledge --keyword` 可用于找候选，但不能代替按 ID 读取详情；不要为核对单条知识扫描整个知识库。

诊断时分别回答：

1. 正确知识是否进入候选。
2. 候选排名是否合理。
3. 正确知识是否 `effect=true` 并进入最终上下文。
4. 是否同时混入足以误导模型的无关或冲突知识。

### 4. 区分召回问题和生成问题

对比实际使用的知识、`aiContent` 和最终 `content`：

| 现象 | 判断方向 |
|------|----------|
| 正确知识未进入候选 | query、目录、过滤条件、索引或混合召回问题 |
| 正确知识在候选中但排名过低 | rerank、query 或知识标题/内容区分度问题 |
| 排名合理但 `effect=false` | 相关性判断、TopN 或 token 预算问题 |
| 无关 QA、文档或商品 `effect=true` | 检索范围、排序、相关性或上下文污染 |
| 使用知识本身矛盾、过时或缺少目标场景 | 知识内容问题 |
| 使用知识正确，但 `aiContent` 结论错误 | 召回正确但生成错误，转 M7 |
| `aiContent` 正确，最终 `content` 错误 | 格式化、检查或后处理问题，转 M7/M11 |

不要把所有“回答不准”都归为召回不准。

## 当前实现事实

- 检索范围按租户走默认 flat 或 `STRICT_ISOLATION` 目录模式。
- 当前核心路径中 QA / Doc / Product 三路并行召回，再统一 rerank、可选相关性判断、TopN/token 选择和上下文组装。
- QA 同时使用原始问题与知识 query，对标题和内容进行向量 + BM25 混合召回。
- rerank 失败会退化为 ES 分数排序，需用日志确认，不能只凭最终排名猜测。
- livechat 与非 livechat 是否启用相关性判断由租户配置决定。
- `AiReplyOption` 类型默认值不是运行时事实；普通主路径和 ChatFlow 当前都显式传入 `retrieve_min_score=0.01`。
- 当前默认 `qaUsedSize/docUsedSize/productUsedSize` 为 `6/4/4`，仍可能被租户配置覆盖。
- 最终还受 `knowledgeMaxToken` 和单文档 chunk 上限约束。

报告引用阈值或模式前，必须先用请求日志或租户配置确认实际值。

## 何时查配置和日志

会话记录已经能证明“用了哪些知识、内容为何冲突”时，可以直接给出内容层建议。以下情况需要继续查知识检索服务日志：

- 正确知识存在但候选为空。
- query 看起来正确但排序明显异常。
- 怀疑目录过滤、变量系统字段加权、embedding、BM25、rerank 或相关性服务异常。
- 需要确认实际检索模式、阈值、候选漏失阶段或 rerank fallback。

### 服务边界

只有定位代码或查询 SLS 时才需要区分服务：

| 环节 | 主要服务 | 查什么 |
|------|----------|--------|
| 原问题、上下文和知识请求组装 | `shulex-gpt` | 实际 query、目录、变量系统字段、调用参数 |
| query rewrite、相关性算法、部分非 LiveChat 回复生成 | `ShulexService` | 改写是否偏离、相关性判断输入输出 |
| QA / Doc / Product 召回、rerank、过滤和上下文组装 | `qa-bot` | 候选漏失、排序、过滤、fallback、最终使用知识 |
| ChatFlow 知识节点参数和结果消费 | ChatFlow 服务 | 先按 M10 对照 graph、节点输入、节点输出和运行路径 |
| LiveChat 最终生成与后处理 | `shulex-gpt` | 召回正确但模型回复或格式化结果错误时转 M7 |

不要因为最终回复错误就直接查询 `qa-bot`。先用会话记录判断问题发生在 query、召回、上下文还是生成阶段，再选择服务。

先按 `sls-query.md` 获取目标服务可用的关联标识，再聚焦查询：

```text
searchKnowledge[<chatId>]: req=
searchKnowledgeFlat[<chatId>]
searchKnowledgeStrictDirs[<chatId>]
retrieveQaV2[<chatId>]
retrieveDocV2[<chatId>]
retrieveProductV2[<chatId>]
hybridSearch[<chatId>]
rerankKnowledgeAdaptive[<chatId>]
cohere rerank error[<chatId>]
相关性判断过滤掉
相关性判断通过
```

一次只验证一个假设，并遵守 `log-query-rules.md` 的预算和止损规则。

## 根因与建议边界

| 已确认根因 | 建议方向 |
|------------|----------|
| query rewrite 偏离原问题 | 修正 rewrite / 多轮上下文，不用堆同义知识掩盖 |
| 目录范围错误 | 调整 Agent、策略或 ChatFlow 知识目录 |
| 正确知识缺失 | 新增覆盖该业务场景的知识 |
| 知识内容冲突或留有推断空白 | 统一相关知识口径，明确场景边界 |
| 知识区分度不足导致排序差 | 优化问题标题、答案关键词和场景限定；必要时评估 rerank |
| rerank / relevance 服务异常 | 提供日志证据并交研发处理 |
| 召回正确但生成错误 | 转 M7 检查运行时 Prompt、知识上下文和 LLM 输出 |

知识建议必须保持用户确认的政策强度。例如原规则是“不建议，可能影响”，不得改写成“禁止”或确定会失效。未确认运行时 Prompt 时，也不能仅凭当前配置断言 PE 已生效。
