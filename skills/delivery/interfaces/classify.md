# Delivery Intent Classification

Delivery 专属分类入口。入口和状态归属 Delivery skill；分类实现调用 `delivery classify`，状态写入 `/workspace/state/delivery/progress.json`。

## Commands

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" delivery classify --xlsx <xlsx> --messages-col <col> [--title-col <col>]
node "<PLUGIN_ROOT>/plugin-cli.mjs" delivery classify --no-excel
node "<PLUGIN_ROOT>/plugin-cli.mjs" delivery report --brand <brand>
node "<PLUGIN_ROOT>/plugin-cli.mjs" delivery excel --brand <brand>
```

## Inputs

- `xlsx`：用户上传的客诉表，可选。
- `--messages-col`：xlsx 模式必填，由 Delivery 先读样例推断。
- `--title-col`：可选。
- `--no-excel`：使用固定 taxonomy。

## Guarantees

- xlsx 模式不会自动降级到 `--no-excel`。
- 模型选择由 Solvea Kit 的 service-managed LLM 通道决定，Delivery 不维护具体模型名。
- 分类结果通过 `results_path` 落盘。
- 报告和 Excel 路径通过 Delivery state 暴露。

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
