# Delivery Test

Delivery 专属回归能力：正式交付前按上传用例或历史抽样执行批量回归，输出 KPI HTML + MD。

这份 interface 属于 `delivery` skill。Delivery 回归 runner 和报告渲染器都在本 skill 内。

## Commands

```bash
# 历史抽样
npx --yes cxclaw@latest script skills/delivery/scripts/sample_history_cases.py \
  --total 100 \
  --intents "Order Issues" \
  --output /workspace/outputs/delivery/cases_<ts>.json

# 批量回归
npx --yes cxclaw@latest script skills/delivery/scripts/batch_test.py \
  --input /workspace/outputs/delivery/cases_<ts>.json \
  --output /workspace/outputs/delivery/results_<ts>.json \
  --touch-point LIVE_CHAT \
  --workers 10 \
  --partial /workspace/state/delivery/partial_results.json \
  --report
```

## Inputs

- 用户上传的 xlsx/csv/json，调用前必须物化文件。
- 或历史抽样生成的 `cases.json`。
- `touch-point`：默认 `LIVE_CHAT`，按用户要求可用 `EMAIL`。

## Flow

1. 确认数据来源：用户上传，或按意图从历史会话抽样。
2. 确认 touch-point。
3. 执行 `batch_test.py`。
4. 如中断，基于 partial 续跑未完成 case。
5. 读取结果并展示核心 KPI。
6. 更新 `/workspace/state/delivery/progress.json`。

## Outputs

- `results_<ts>.json`
- `results_<ts>.json.html`
- `results_<ts>.json.md`
- partial：`/workspace/state/delivery/partial_results.json`

## State

Delivery 顶层状态写 `/workspace/state/delivery/progress.json`：

- `regression.input_path`
- `regression.touch_point`
- `regression.results_path`
- `regression.report_html`
- `regression.report_md`

## Behavior Guarantees

- Delivery 回归支持 partial 续跑。
- `--report` 输出 HTML + MD。
- EMAIL 模式内部处理异步轮询，调用方不要额外加 sleep。

## Non-Guarantees

- 报告 HTML 模板结构不保证稳定。
- batch runner 并发实现不对 Delivery 暴露。
