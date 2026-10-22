# POC Test

POC 专属测试能力：为 POC 业务 agent 设计并执行测试，生成 POC 测试手册。

这份 interface 属于 `poc` skill。POC 测试 runner 和手册资产都在本 skill 内。

## Commands

```bash
npx --yes cxclaw@latest script skills/poc/scripts/inspect_chatflow.py --agent-id <id> [--agent-id <id>] --pretty

npx --yes cxclaw@latest script skills/poc/scripts/poc_test.py \
  --test-file /workspace/outputs/poc/poc_test_cases_<ts>.json \
  --max-turns 3 \
  --output /workspace/outputs/poc/results_<ts>.json \
  --report

npx --yes cxclaw@latest script skills/poc/scripts/gen_poc_manual.py \
  --results /workspace/outputs/poc/results_<ts>.json \
  --output /workspace/outputs/poc/poc_test_manual_<ts>.html \
  --title "Shulex POC 测试手册 - <brand>" \
  --brand-name "<brand>" \
  --brand-website "<url>" \
  --account-email "<email>"
```

## Agent Scope

- 只测试 3 个业务 agent。
- 跳过 Fallback agent。
- 如果刚跑完 POC 意图创建，从 `/workspace/state/poc/progress.json` 或 `intent.created_log_path` 展开业务 agent。
- 如果用户显式给了 agent ID，以用户输入为准。

## Case Design

- 每个业务 agent 默认 5 个 case。
- 单 case 1 到 3 轮，`--max-turns 3` 是 POC 硬上限。
- 覆盖不同分支，优先覆盖步骤多、链路长的路径。
- KB 节点要设计能触发 KB 检索的问题。
- 订单号必须向用户索取真实订单号集，不要编造。
- 至少保留 1 个故意触发转人工的 case。
- 展示结构化 case 清单，用户确认后再执行。

## cases.json

主字段是 `case_name`，不是 `name`。

```json
[
  {
    "case_name": "P1_Shipping_Inquiry",
    "agent_name": "Pre-Sales Inquiry",
    "agent_id": 38059,
    "scenario": "Customer asks about shipping to Canada",
    "messages": ["Do you ship to Canada?"],
    "expected": {
      "intent": "Pre-Sales Inquiry",
      "content_contains": ["Canada"]
    }
  }
]
```

## Behavior Guarantees

- 触发 `handoff=True` 或 `TRANSFER_TO_HUMANS` 成功节点时停止当前 case。
- 结果 JSON 包含 `stopped_reason`。
- 结果 JSON 包含 chatflow 执行链路摘要。
- 手册生成前必须确认 `brand_name`、`brand_website`、`account_email`。
- 用户只要求重新出报告时，复用已有 `results_path`，不要重跑测试。

## State

POC 顶层状态写 `/workspace/state/poc/progress.json`：

- `test.agents`
- `test.cases_json_path`
- `test.results_path`
- `test.manual_path`

不读取其他测试 skill 的状态作为 POC 顶层状态源。

## User-Facing Message

面向业务人员，只突出手册：

```text
## 交付物

- POC 测试手册：`poc_test_manual_<ts>.html`
- 测试结果原始数据：`results_<ts>.json`

共 N 个测试案例，覆盖 M 个场景。
```
