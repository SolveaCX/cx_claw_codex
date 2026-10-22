# Delivery Intent And Agent Creation

Delivery 专属能力：创建正式交付意图，优先复制固定广场 agent，绑定策略，并默认更新订单工具 X-Token。

## Commands

```bash
npx --yes @shulex/cxclawctl@latest script skills/delivery/scripts/create_agents.py --mode delivery

# Delivery 恢复阶段：预置 agent 不可用，用户确认从零新建或使用替代 agent 后，绑定业务策略
npx --yes @shulex/cxclawctl@latest script skills/delivery/scripts/create_agents.py --mode delivery \
  --custom-agent-map /workspace/state/delivery/custom_agent_map.json

# 创建后禁用多余 SYSTEM 意图
npx --yes @shulex/cxclawctl@latest script skills/delivery/scripts/create_agents.py --disable-system
```

`custom_agent_map.json` 使用 Delivery intent 名作为 key：

```json
{
  "Pre-Sales Inquiry": 2642,
  "Product issues": 2643
}
```

## Flow

1. 通过 `/skills/delivery/interfaces/classify.md` 完成分类。
2. 展示分类结果，等用户确认。
3. 执行 `/skills/delivery/scripts/create_agents.py --mode delivery`。
4. 读取 `/workspace/state/delivery/progress.json` 的 `created_log_path`。
5. 读取 created log，展示意图、agent、strategy。
6. 说明 skipped 项：
   - 新 L1：已创建意图，但没有固定广场 agent 映射，需要人工配置 agent 或复用已有 agent。
   - 标准 L1 的 `preset_agent_errors`：默认 squareAgent 不可用，不要直接崩溃或要求开发修复；询问客户是从零新建 CHAT_FLOW agent，还是使用其他现有 agent 替代。
7. 用户确认新建或替代后，把已确认的 agent id 写入 `custom_agent_map.json`，执行 `--custom-agent-map` 绑定业务策略；没有确认前不要盲目绑定策略。
8. 询问是否需要 `--disable-system` 关闭多余 SYSTEM 意图。

## Guarantees

- 创建 7 个标准意图和分类中新发现的 L1。
- 当前租户已有同名意图时复用现有意图 id，继续创建 agent 和策略；不要因为 create intent 返回同名冲突而中断。
- 7 个标准意图优先按固定 binding 克隆 agent。
- 固定 squareAgent 不可用时，记录为可恢复 skipped 项，询问从零新建或使用替代 agent。
- 预置或替代 agent 可用后，1 个意图绑定 1 条策略。
- 默认更新订单工具 X-Token。

## Delivery Fixed Bindings

| L1 Intent | L2 子意图（预定义） | 默认 squareAgent_id |
|---|---|---|
| Pre-Sales Inquiry | Product Recommendation, Discount Inquiry, Price Inquiry, Stock Availability, Payment Issues | 37625 |
| Invoices | Request Invoice, Modify Invoice Information | 37627 |
| Order Issues | Modify Order, Check Order Status, Cancel Order | 37631 |
| Logistics Issues | Track Shipment, Shipping Exception | 37633 |
| Package issues | Missing Items, Wrong Items Received, Damaged Package | 37623 |
| Product issues | Product Usage, Physical Damage, Non-Physical Issues | 38114 |
| Return and exchange | 从数据中推断，无 xlsx 时为空 | 37626 |

默认 `squareAgent_id` 只是首选来源，不是硬阻塞依赖。找不到时按可恢复 skipped 项处理。

## Outputs

状态文件：`/workspace/state/delivery/progress.json`。

可读取：

- `status`
- `mode`
- `created_log_path`
- `updated_at`

`created_log_path` 指向 JSON，可读取：

- `intents[]`
- `intents[].intent_name`
- `intents[].intent_id`
- `intents[].agent_id`
- `intents[].strategy_id`
- `intents[].skipped`
- `intents[].skip_reason`
- `preset_agent_errors[]`
- `next_action`
- `custom_agent_strategies[]`

## Non-Guarantees

- 策略 API payload、copyAgent payload 不对上层流程暴露。
