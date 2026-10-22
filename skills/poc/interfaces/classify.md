# POC Intent Classification

POC 专属分类入口。入口和状态归属 POC skill；通用意图分类实现调用 `solvea-kit/scripts/intent_classify.py`，状态写入 `/workspace/state/poc/progress.json`。

## Commands

```bash
npx --yes cxclaw@latest script skills/poc/scripts/classify.py --xlsx <xlsx> --messages-col <col> [--title-col <col>]
npx --yes cxclaw@latest script skills/poc/scripts/classify.py --no-excel
npx --yes cxclaw@latest script skills/poc/scripts/gen_report.py --brand <brand>
npx --yes cxclaw@latest script skills/poc/scripts/gen_excel.py --brand <brand>
```

## Inputs

- `xlsx`：用户上传的客诉表，可选。
- `--messages-col`：xlsx 模式必填，由 POC 先读样例推断。
- `--title-col`：可选。
- `--no-excel`：使用固定 taxonomy。

## Guarantees

- xlsx 模式不会自动降级到 `--no-excel`。
- 模型选择由 Solvea Kit 的 service-managed LLM 通道决定，POC 不维护具体模型名。
- 分类结果通过 `results_path` 落盘。
- 报告和 Excel 路径通过 POC state 暴露。

## State Fields

- `status`
- `tenant`
- `run_id`
- `results_path`
- `items_path`
- `report_path`
- `excel_path`
- `mode`
- `updated_at`
