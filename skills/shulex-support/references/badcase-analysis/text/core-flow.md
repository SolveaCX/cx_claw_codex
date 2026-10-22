# 文本 badcase 核心流程

本文件只负责编排。字段解释、配置检查和日志查询由会话记录说明及对应模块文档负责。

## 1. 理解问题并获取会话记录

始终围绕用户的问题描述排查。先明确用户指出的异常、实际结果、预期结果和可能的目标轮次；信息已经给出时不要重复询问。

所有用户提供的会话标识都先按内部 `chatId` 查询，包括看起来像外部系统 ID 的值：

```bash
npx --yes @shulex/cxclawctl@latest api get-transcript --chat-id <用户提供的会话标识> --pretty
```

只有 `get-transcript --chat-id` 查不到、返回空或 404 时，才把同一个值作为外部会话 ID 走 Inbox 同源搜索解析内部 chatId，再拉详情：

```bash
npx --yes @shulex/cxclawctl@latest api resolve-transcript-chat-id --external-id <用户提供的会话标识> --page-size 10 --pretty
npx --yes @shulex/cxclawctl@latest api get-transcript --chat-id <resolvedChatId> --pretty
```

解析返回多个候选时，优先使用 `matchedBy=exactExternalId` 的结果；没有精确匹配时，先向用户说明候选并确认目标会话，不要随意拿 keyword 首条继续诊断。

命令默认携带 `isCompare=true`。返回的是会话记录详情，`Transcript` 只是后端对象和命令中的技术名称。

## 2. 定位目标事实

读取 `/skills/shulex-support/references/badcase-analysis/text/conversation-record.md`，定位目标消息及必要的前置轮次，先回答：

- 用户实际说了什么，系统实际回复或执行了什么。
- 目标轮次经过了哪些与问题相关的模块。
- 会话记录直接证明了什么，哪些只是当前状态或推断。

不要脱离用户描述遍历全部字段，也不要因为看到某个异常信号就擅自改变排查目标。

## 3. 进入对应模块排查

根据目标事实按需读取模块文档。配置、图和日志的检查规则由模块文档决定，不在本文件重复。

| 主要信号 | 模块 |
|----------|------|
| 请求入口、HumanReview 旁路 | M1 入口：`m1-entry.md` |
| 意图识别或改写错误 | M2 意图识别：`m2-intent.md` |
| 策略未命中或命中错误 | M3 策略匹配：`m3-strategy.md` |
| 变量系统字段缺失或值错误 | M4 变量系统：`m4-aifield.md` |
| Agent 类型选择、调用次数或 SINGLE_AGENT / MULTI_AGENT 执行异常 | M5 Agent 执行：`m5-agent.md` |
| 外部工具请求、响应或状态异常 | M6 工具调用：`m6-tool.md` |
| 召回正确但回复生成、Prompt 或后处理异常 | M7 回复生成：`m7-reply.md` |
| 系统错误、超时、空回复 | M8 系统异常：`m8-error.md` |
| 回复后被质检标记、拦截或因合规原因转人工 | M12 质检：`m12-quality-inspection.md` |
| query、检索范围、召回、排序、过滤或知识内容异常 | M9 知识召回：`m9-knowledge-search.md` |
| ChatFlow 图、节点、边、变量或节点内知识/工具异常 | M10 ChatFlow 服务：`m10-chatflow-service.md` |
| ShulexService 的 intent / NER / classify / rewrite / reply / check 异常 | M11 算法服务：`m11-algorithm-service.md` |

一个 badcase 可以涉及多个模块，但报告要指出主根因和上游诱因。现有证据不足以确认根因时，按模块文档查询当前配置或聚焦日志；不要无差别拉取所有资源和日志。

## 4. 输出结论和建议

先写发生了什么，再写为什么。明确区分：

- **已确认**：会话记录、配置或日志直接证明。
- **当前状态**：读取时的当前配置或知识状态，不一定是历史运行快照。
- **待确认**：证据不足的推断及缺失证据。

建议必须对应已确认根因，保持用户给出的业务口径，不得把“可能”“不建议”等表述擅自加强为确定承诺或禁止规则。

### 排查不清或用户无法理解时

- 完成必要的会话、配置或日志检查后根因仍不清晰，必须如实说明缺少什么证据，不要用推测填满结论。
- 用户表示不理解当前结论、不知道如何处理，或希望由售后继续跟进时，切换到本 skill 的售后工单流程。
- 转入售后前先整理 ChatId、问题现象、已确认事实、待确认项、失败节点以及 trace / armsTrace（如有），减少用户重复描述。
- 这里只整理提单信息并征得用户确认，不得直接创建工单；创建、查询或追加工单必须读取 `/skills/shulex-support/references/tickets.md`，并遵守“先确认后提交”。

```markdown
## 会话诊断：chatId=<chatId>

### 结论
<发生了什么，主根因是什么>

### 实际执行链路
<只列与目标问题相关的关键步骤>

### 根因与证据
<区分已确认、当前状态、待确认>

### 建议
1. [可自行调整] <准确的配置或内容建议>
2. [需联系研发] <代码、服务或运行时问题>
```
