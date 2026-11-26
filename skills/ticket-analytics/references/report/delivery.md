# 交付分析报告与文件

仅在用户要下载文件、完整报告或更新已有报告时进入。先确定要交付指标表、明细表还是带解释的完整报告；已明确格式时直接做，不再询问。

## 沿用合适的数据来源

- 产品报表接口已回答问题：复用其返回数据、筛选条件、来源和采集时间。生成文件不要求重新拉全部工单或换成快照口径。
- 用户需要复杂分类或标准接口未提供的明细口径：读取 `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/workflow.md`，按历史事实或当前状态选择快照。
- 更新已有报告：核对数据来源、时间范围、时区、过滤条件和完整性；这些不变可复用，但用户要求“最新”或当前状态已过期时需重查。不能仅因目录存在就沿用旧数据。

## 只要明细或指标文件

分页取完需要的数据；截断时明确范围，不能交付为全量。将业务字段、单位、日期、筛选口径和来源写入 XLSX。只要数据表时无需生成 HTML 报告或图表。输出到 `<WORKSPACE>/outputs/ticket-analytics/<唯一任务名>/`。

## 完整报告

1. 快照任务沿用已有 task_id；直接统计接口取数使用新的唯一任务名，将请求范围和响应保存在 `<WORKSPACE>/state/ticket-analytics/<唯一任务名>/`。直接统计任务不覆盖 latest_task.json，不伪装成 ticket_report_snapshot 或 ticket_list_snapshot。
2. 读取 `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/report-design.md`。在分析脚本中生成 report_data.json 与 calculation_notes.json；快照数据处理规则见 `<PLUGIN_ROOT>/skills/ticket-analytics/references/report/workflow.md`，直接统计用原始指标及其口径，不重算为另一套定义。
3. 完整性信息按实际来源填写：统计接口无明细行数时row_count 可写“不适用（聚合统计）”，不伪造明细行数，不用零代替未知；不同来源分别注明时间语义。
4. 使用统一 renderer 校验再输出，失败时修正分析脚本及输入，不重写 CSS/模板。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics render-report --task-id <唯一任务名> --report-slug <英文报告名> --validate-only
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket-analytics render-report --task-id <唯一任务名> --report-slug <英文报告名>
```

结束时给核心结论、范围、限制和交付物；无需向用户讲内部 task 机制。未取得可信数据时交代缺口，不为了完成报告生成虚构数字。
