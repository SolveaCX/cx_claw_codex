# 客服工单明细与快照分析

标准指标、趋势和队列问题先用 `../product-reports.md` 中的统计查询。只有复杂正文分类、标准接口未覆盖的维度、明细分析或文件交付需要快照。客服工单与 Inbox 是不同的数据源，不能混算。

## 选择数据源与范围

| 业务问题 | CLI action | source_type | 时间语义 |
|---|---|---|---|
| 时间范围内实际回复/解决行为、回复人/解决人和时效 | `ticket-analytics fetch-sources` | `ticket_report_snapshot` | 历史事实 |
| 当前状态、负责人、最后来信、标题正文、标签、视图筛选 | `ticket-analytics fetch-tickets` | `ticket_list_snapshot` | 当前状态 |

已有范围直接沿用。历史分析缺少必要日期且上下文无法确定时才询问，不默认本月。不要为已明确的范围再要求确认。当前负责人不能当作历史回复人或解决人。

CLI 调用遵循 `cxclawctl` Skill：使用插件入口，每条租户命令带本对话 `--context <contextId>`。`<WORKSPACE>` 为本地工作区；状态和输出路径以 CLI 返回值为准，不能假设线上沙箱路径存在。

## 任务复用

只在快照分析路径读取 `state/ticket-analytics/latest_task.json`。不存在代表尚未取数，直接创建新任务；普通统计查询不读取它。

复用前核对 source_type、租户、时间窗、视图、过滤条件和采集时点。追问、改图表、改分析维度可复用同一快照；用户要最新数据、来源/范围变化或快照已过期时重新取数。不要读取旧 Skill 状态目录。

CLI 返回 taskId、output（XLSX）、manifest、row count、truncated 和 pagesFetched。同名 task 不能覆盖取数目录；新任务用默认唯一 ID 或自行生成唯一 ID。

## 历史事实快照

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics fetch-sources \
  --start 2026-07-10 --end 2026-07-16 \
  --timezone Asia/Shanghai --page-size 200 \
  --max-pages 200 --max-rows 200000 --context <contextId>
```

- 起止日期均包含；日期字符串或对齐北京时间午夜的 ISO 时间均可。只支持 Asia/Shanghai 自然日，结束日实际查询到 23:59:59。
- 单次最多 60 天。超过时分成 ≤60 天窗口，合并分析注明分窗；不能按半天/小时拆分，因为接口按日期查询。
- 默认按 report_activity_date（回复/解决日期）查询，不传 timeRangeType。只有用户明确要求创建日期时加 `--time-range-type created_at`。
- page-size 为 1～200。到达 max-pages/max-rows 时保留 `truncated=true`，不得声称全量。缺少可信分页信息时失败，不把未知完整性当作完整。
- 历史事实调用 `/api_v2/tars/api/ticket/report/raw/page`，不能用当前列表替代。
- 历史字段见 `fields.md`。生命周期指标可能受窗口边界影响，必须在口径中说明。

## 当前工单快照

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics fetch-tickets \
  --view-id 1 --page-size 100 --max-pages 120 --max-rows 200000 \
  --filters-json '{"channelList":["ebay"],"agentIdList":[474501],"ticketStatusList":["open","pending"]}' \
  --sort last_update_time --order DESC --context <contextId>
```

- 调用 `/api_v2/tars/api/ticket/list`，受当前用户权限和视图共同限制。默认 viewId=1、sort=last_update_time、order=DESC；page-size 为 1～100。
- 支持的过滤字段见 `../tickets/query.md`。将已知条件下推；参数多时使用 `--filters-file`，与 `--filters-json` 二选一。
- page、pageSize、viewId、sort、order 使用独立参数，不能混入 filters。未知字段直接报错；不能自行拼接 API。
- 名称先解析到准确 ID，重名不猜。后端不支持的过滤在本地快照处理，并记录口径。

## 文件和分析

```text
state/ticket-analytics/<task_id>/
  datasource.xlsx          # 原始数据，通常 data sheet；多个 dataset 分 sheet
  manifest.json            # 来源、租户、范围、分页、行数、截断信息
  metadata.json            # 快照元信息
  analysis.ts              # 本地可复算的分析脚本
  report_data.json         # 报告结构化输入
  calculation_notes.json   # 算法、范围、定义、限制
outputs/ticket-analytics/<task_id>/
  <report_slug>.html
  <report_slug>_detail.xlsx # 按需
```

不要手工覆盖 datasource.xlsx，不把原始快照、凭据或内部状态作为用户交付物。分析脚本仅处理 CLI 已取回的数据；不要从脚本绕过 CLI 请求业务接口。本地脚本可以使用环境中可用的表格处理库，先确认依赖可用，不假定插件依赖能从任意目录 import。

每个核心指标写一条 calculation_notes.json 记录：metric、value、algorithm、range、definition、limitations（数组）。比例由分子分母复算；多窗口的比例不能直接求平均；缺失值不能补零。完整性与过滤条件一起保留。数据量大时分批处理，不因输出大小限制改为抽样后声称全量。

## 输出与报告

直接回答问题时给核心结论、可核对的数据、范围和限制，按需要展示图表；不强制生成文件。

完整报告先读 `report-design.md`，由分析脚本生成 report_data.json 和 calculation_notes.json。通过统一 renderer 校验并输出：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics render-report \
  --task-id <taskId> --report-slug weekly_ticket_summary --validate-only
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics render-report \
  --task-id <taskId> --report-slug weekly_ticket_summary
```

render-report 只读本地输入，不要求登录。可用 `--report-data`、`--notes`、`--output` 指定实际路径。renderer 内置模板和样式，支持表格与 bar/line/pie/scatter 切换，默认表格；不要自写模板。输入校验失败要修正并重跑分析脚本。

同一 task 保持同一语义化 ASCII snake_case 报告名，更新同一报告；新范围使用新 task。直接统计接口生成报告不必创建快照，用新的任务名保存原始指标和请求范围，不覆盖 latest_task；无明细行数时写“不适用（聚合统计）”。

交付时说明结论和口径，给出实际报告与明细文件的绝对路径链接。不要依赖线上 finished 事件自动生成下载入口，也不要只给内部文件名。
