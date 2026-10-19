# M12：回复后质检排查

M12 处理 Agent 生成回复之后的实时/后置质检：是否送检、命中什么标签、标签是否影响最终 AgentAction，以及质检服务是否调用失败。它不分析 ChatFlow 图或节点业务逻辑；图内执行异常先走 M10。

## 边界

- 质检可能记录标签，也可能根据命中结果改变回复、拦截回复或转人工；必须先确认实际影响，不能把“命中标签”等同于“回复被拦截”。
- `quality-inspection-gate` 是服务端过滤/灰度控制，不是租户的质检规则配置。badcase 排查只取运行证据，不修改它。
- 当前系统规则、自定义规则和开关只用于和历史结果对照，不是目标轮次的配置快照，也不能单独证明历史命中原因。

## 排查顺序

### 1. 对齐会话记录中的目标事实

先读取目标回复及其 `messages[].context`，检查：

| 证据 | 说明 |
|---|---|
| `context.metadata.real_time_inspection_tags` | 实时质检返回的标签，是优先证据 |
| `messages[].reason` / `reasonDesc` / `reasonList` | AgentAction 的原因及多原因列表 |
| `messages[].type` / `handoff` | 最终是否变为 `TO_AGENT`、`STOPPED` 或转人工 |
| `context.aiContent`、`filteredContent` 与最终 `content` | 候选回复是否被后处理改变或清空 |

先写清“生成了什么”和“最终展示了什么”。标签存在但最终 content、type 和 handoff 未受影响时，只能结论为“已记录命中，未证明拦截”。

### 2. 判断是否进入 M12

- 有 `real_time_inspection_tags`，或 reason 明确指向合规/质检：进入 M12。
- 回复被拦截、转人工或清空，但没有标签：先在 M12 确认是否送检；没有送检事实再回 M7/M8/M11。
- ChatFlow 节点本身失败：回 M10；不要把节点失败归为质检。
- 回复内容本身不符合业务预期、且最终未被质检改变：回 M7。

### 3. 对照当前质检配置

需要说明规则语义或复现建议时，可读取 solvea-kit 的质检管理说明和当前配置，核对总开关、系统规则、自定义规则及启用状态。

当前配置只能回答“现在什么规则会生效”。若会话记录没有保存当时规则版本或具体命中详情，报告必须写为“当前规则对照”，不能写成历史根因。

### 4. 最后才查日志

会话记录不能说明送检、标签来源、拦截原因或调用异常时，按 `sls-query.md` 的 M12 模板查日志：先查 GPT 的 `QualityCheckPostCheck`、`realTimeInspection`、`replyInspection`、`inspectionDataResponse`、豁免及 gate 线索；GPT 已确认外调失败时，再通过 `armsTrace` 查 Intelli。

日志查询次数和止损规则遵守 `log-query-rules.md`。没有日志证据时，不要从“没有标签”断言该轮一定未送检。

## 报告口径

只使用证据能支持的结论：

| 结论 | 最低证据 |
|---|---|
| 命中质检且影响 AgentAction | 标签/质检日志 + 最终 reason、type 或 handoff 的对应变化 |
| 命中质检但只记录、未拦截 | 有标签，且最终回复和动作未见质检影响 |
| 未送检 | 明确的豁免、过滤或未调用日志；不能只凭标签为空 |
| 质检调用失败 | GPT 或 Intelli 的实际异常日志 |
| 无法确认历史命中原因 | 仅能读取当前规则，缺少当时标签、规则快照或日志 |

不要把“质检命中”表述为原始 ChatFlow、意图、知识或 Agent 生成错误的根因；它是回复后的独立处理结果。建议修改规则时应保留原业务口径，并用原 badcase 回归验证。
