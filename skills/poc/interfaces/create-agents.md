# POC Intent Onboarding

POC 专属能力：创建全部意图，优先克隆 3 个预置业务 agent，绑定 3 条业务策略；兜底 chatflow agent 由 POC 编排调用 `agent-builder` 创建后，再回填第 4 条兜底策略。

这份 SOP 属于 `poc` skill。POC 的意图创建、业务 agent 创建、兜底策略回填都从本 skill 的脚本入口执行。

## Commands

```bash
# POC 业务阶段：建全部意图 + 优先克隆 3 个业务 agent + 3 条业务策略
python3 /skills/poc/scripts/create_agents.py --mode poc

# POC 兜底阶段：fallback chatflow agent 创建完成后，绑定所有 pending intents
python3 /skills/poc/scripts/create_agents.py --mode poc --poc-fallback-agent-id <agent_id>

# POC 恢复阶段：预置 agent 不可用，用户确认从零新建或使用替代 agent 后，绑定业务策略
python3 /skills/poc/scripts/create_agents.py --mode poc \
  --custom-agent-map /workspace/state/poc/custom_agent_map.json
```

`custom_agent_map.json` 使用 POC binding 名作为 key：

```json
{
  "Package_Logistics": 2641,
  "PreSales": 2642,
  "Product": 2643
}
```

## SOP

1. 通过 `/skills/poc/interfaces/classify.md` 完成分类。
2. 展示分类结果，等用户确认。
3. 执行 `/skills/poc/scripts/create_agents.py --mode poc`。
4. 读取 `/workspace/state/poc/progress.json` 的 `created_log_path`。
5. 读取 created log，展示意图、agent、strategy 和 `fallback_pending`。
6. 如果 created log 或 state 出现 `preset_agent_errors` / `status=preset_agent_missing`，不要说“只能等开发修复”，也不要直接崩溃；应向用户说明缺失的预置 agent，并请用户选择：
   - 从零新建对应 CHAT_FLOW 业务 agent；
   - 或指定现有 agent 作为替代。
   用户确认后再调用 `agent-builder` 创建新 agent，或按用户给定替代 agent 继续绑定策略。
7. 如果用户选择从零新建或使用替代 agent，把已确认的 agent id 写入 `custom_agent_map.json`，执行 `--custom-agent-map` 绑定业务策略。
8. 调用 `/skills/agent-builder/interfaces/fallback-chatflow.md` 创建兜底 CHAT_FLOW agent。
9. 拿到 `agent_id` 后执行 `/skills/poc/scripts/create_agents.py --mode poc --poc-fallback-agent-id <agent_id>`。
10. 展示 fallback strategy 结果，等用户确认是否进入 KB 或测试阶段。

## POC Guarantees

- 创建全部标准意图和分类中新发现的 L1。
- 当前租户已有同名意图时复用现有意图 id，继续克隆 agent 和创建策略；不要因为 create intent 返回同名冲突而中断。
- 优先克隆 3 个固定业务 agent；如果预置 agent 不存在或复制失败，必须把它作为可恢复分支处理，询问用户从零新建还是使用替代 agent。
- 创建 3 条业务策略，其中 Package issues 与 Logistics Issues 共用一条策略。
- 兜底策略 priority=999，业务策略默认 priority=0。
- 不更新 X-Token。
- 不在 intent 脚本内创建兜底 chatflow agent。
- 新发现 L1 或不在 3 个业务 binding 内的意图自动进入 fallback pending。

## POC Fixed Bindings

| Binding | 意图 | 默认 squareAgent_id |
|---|---|---|
| `Package_Logistics` | Package issues, Logistics Issues | 38433 |
| `PreSales` | Pre-Sales Inquiry | 38429 |
| `Product` | Product issues | 38428 |
| `Fallback` | 不在上述 3 个 binding 里的所有意图 | 由 agent-builder 创建后传入 |

默认 `squareAgent_id` 只是首选来源，不是硬阻塞依赖。找不到时按上面的可恢复分支处理。

## Outputs

状态文件：`/workspace/state/poc/progress.json`。

POC 顶层只读取以下字段：

- `status`
- `mode`
- `created_log_path`
- `updated_at`

`created_log_path` 指向 JSON，POC 可读取：

- `intents[]`
- `intents[].intent_name`
- `intents[].intent_id`
- `intents[].agent_id`
- `intents[].strategy_id`
- `intents[].binding`
- `intents[].fallback_pending`
- `fallback_pending_intent_ids`
- `fallback_strategy`
- `custom_agent_strategies[]`
- `preset_agent_errors[]`
- `next_action`

## Fallback Chatflow Requirements

POC 只声明兜底 agent 的业务目的：

- 回复“当前问题不在本次 POC 测试范围内”或等价业务话术。
- 需要保持 CHAT_FLOW agent 类型。
- 需要输出可回填的 `agent_id`。

具体节点选择、graph 结构、变量、回复节点和结束节点由 agent-builder 在读取自身能力说明后创建。POC 不维护 chatflow graph 字段，也不复制 agent-builder 的构图规则。

## Non-Guarantees

- POC 不依赖策略 API payload、copyAgent payload 或 chatflow graph 内部结构。
- POC 不读取其他 skill 的完整业务流程，只调用公开 interface。
