# Shulex Desk 报表工作流

根据用户维度使用历史回复/解决报表事实或当前工单列表快照，支持后端过滤下推、正文分类、趋势、时效、复杂过滤和 XLSX/报表交付。数据来自工单系统，与 Shulex 客服智能体（Agent）运营数据是两套独立产品，不要混用。

## 执行入口

每次使用本 skill，先按这个入口判断，不要等读到后文才决定：

1. 先读 `workspace/state/solvea-desk/latest_task.json`，判断是否复用已有 task。**该文件只在第一次 fetch 后才生成；读不到 / 文件不存在是首次使用的正常情况，不是错误**——此时直接按"没有可复用 task、需要新建 task"处理，继续后面的步骤，不要把它当成工具失败而中断。读到内容时：追问、改口径、补维度、换图表、生成/更新报表、导出明细，且时间窗和数据源范围没变时，复用同一 task；时间窗或数据源范围变了才新建 task。
   复用前还必须确认 `source_type` 一致：报表分析快照是 `ticket_report_snapshot`，原始工单明细快照是 `ticket_list_snapshot`，两者不能互相复用。
2. 先判断数据源语义：按时间窗内实际回复/解决行为分析时使用 `ticket_report_snapshot`；按工单当前状态、最后来信、当前负责人或正文分析时使用 `ticket_list_snapshot`。不要只根据“报表”“工单”字样选源。
3. 只有 `ticket_report_snapshot` 必须判断用户是否给了明确时间范围。明确时间范围包括绝对日期、月份/季度、今天/昨天、本周/上周、本月/上月，或“沿用刚才范围”。首轮新 task 且没有明确时间范围时，先面向用户确认时间范围，不要默认本月，不要 fetch。
4. 报表快照有明确时间范围时，把它换算成具体起止时间，用一句话告知，然后直接 fetch 或复用 task；不要让用户再确认一遍。**单次 fetch 最大 60 天**，超过 60 天要按 ≤60 天拆窗分别 fetch（见「数据源快照」规则），不要一次性拉。当前工单是当前状态快照；后端不支持的时间字段在 `analysis step` 中按响应字段处理。
5. 回复必须面向用户说话，不要把内部判断写成旁白。不要说“用户说 3 月”“用户要求查看...”“没有已有 task，需要新建”。应说“我按 2026 年 3 月理解，统计范围是 2026-03-01 00:00:00 至 2026-03-31 23:59:59（北京时间），现在拉取这段数据并分析回复率趋势。”
6. 只有缺少必要信息、需要用户选择口径或时间范围时才停下来提问；否则继续完成拉取、分析、对话内图表、Markdown 表格和报表生成。除非缺少必要信息、需要用户选择时间范围或口径，否则不要为了生成报表再停下来等确认。
7. 对用户只说“报表”，不要说“HTML”；内部文件扩展名和脚本参数可以照常使用 `.html`。

## 文件索引

```text
/skills/solvea-desk/
  SKILL.md                         # 主流程：task、拉数、分析、图表、最终回复规则
  CLI commands: `solvea-desk fetch-sources`, `solvea-desk fetch-tickets`, `solvea-desk render-report`
    report/
      solvea-desk fetch-sources             # 按时间范围拉取历史报表事实
      solvea-desk render-report             # 根据结构化分析结果渲染报表
    tickets/
      solvea-desk fetch-tickets             # 按视图和后端过滤条件拉当前工单快照
  references/
    report/
      fields.md                    # 历史报表事实字段
      report-design.md             # 报表结构和渲染契约
      report.css                   # 固定样式
      report-template.html         # 固定模板
    tickets/
      fields.md                    # ticket/list 请求参数和响应字段
```

按需读取：分析历史报表事实时读 `references/report/fields.md`；查询当前工单快照时读 `references/tickets/query.md`；生成报表前读 `references/report/report-design.md`；不要把 CSS / 模板复制进 `analysis step`。

本 skill 是“受控快照 + Agent 分析师 + 可复算口径账本”：

- **受控部分**：只能通过 skill 脚本调用场景对应的受控分页接口，账号范围 / 项目范围 / 鉴权由工程逻辑处理，Agent 不得直接 curl 工单接口。
- **数据边界**：Agent 只认受控 fetch 脚本写出的 `datasource.xlsx` 和内部快照元信息；报表字段以 `/skills/solvea-desk/references/report/fields.md` 为准，当前工单字段以 `/skills/solvea-desk/references/tickets/query.md` 为准。
- **开放部分**：拿到本地快照后，Agent 可按用户需求自写 `analysis step`，做复杂过滤、换维度、改口径和对比分析。
- **可信部分**：每个核心数字必须写入 `calculation_notes.json`，用业务语言说明算法、范围和口径。
- **展示部分**：对话内给核心结论、图表和表格，同时生成或更新报表；对话内图表只能通过 `render_chart` 工具展示；用户可下载交付物只写入 `workspace/outputs/solvea-desk/<task_id>/`。

## 任务生命周期

一个 task 表示一次已确认数据范围下的快照和围绕它持续迭代的分析产物。报表快照的数据范围是时间窗；当前工单快照的数据范围是当前用户权限、`viewId` 和后端过滤条件。用户几轮都在调整同一批数据、同一类分析时，复用同一个 task；不要每问一句都重新创建目录和拉快照。`task_id` 用 fetch 脚本输出的 ID。

```text
workspace/state/solvea-desk/<task_id>/
  datasource.xlsx          # 固定名，本轮数据源快照，多 sheet，来自 fetch 接口；工作文件，不作为下载物
  manifest.json            # 固定名，内部快照元信息：时间范围、分页、行数、截断状态、文件清单
  analysis step              # 固定名，本次最终分析脚本，保留用于复现
  report_data.json         # 固定名，报表结构化输入，由 analysis step 写入
  calculation_notes.json   # 固定名，核心指标口径账本，最终回复必须参考

workspace/outputs/solvea-desk/<task_id>/
  <report_slug>.html        # 用户可下载报表；文件名按本轮分析场景命名
  <report_slug>_detail.xlsx # 可选明细导出；和报表 slug 对齐

workspace/tmp/solvea-desk/<task_id>/
  raw_page_001.json        # 固定模式，接口原始分页响应，仅用于本轮排查 / 重放
  ...                      # 草稿脚本、临时 CSV、图表中间数据等

workspace/state/solvea-desk/
  latest_task.json         # 固定名，每次 fetch 覆盖，记录最近一次 task_id / 时间窗 / 状态
```

规则：

- `state/<task_id>/` 是本轮工作快照和可复算账本，路径带 task_id，每个新 task 不同；不要把它当用户下载物。
- `outputs/<task_id>/` 只放本轮用户可下载交付物，通常是 `<report_slug>.html` 和可选 `<report_slug>_detail.xlsx`；不要把 `datasource.xlsx` / `manifest.json` / `analysis step` / `calculation_notes.json` 放进 outputs。
- `tmp/<task_id>/` 是中间过程，可丢弃；不要把最终报表只放 tmp。
- `state/latest_task.json` 是跨轮 task 指针，每次新 fetch 覆盖；不要把用户可下载报表放 state。
- 开始处理前先读 `latest_task.json` 判断是否有可复用 task；该文件由对应 fetch 脚本首次拉数时创建，读不到或不存在就代表还没有任何 task，按新建 task 流程继续，不要当成错误。
- 同一 task 的判断：`source_type` 相同，用户在追问、改口径、补维度、换图表、生成/更新报表、导出明细，且没有改变时间窗、`viewId`、后端过滤条件或其他数据源范围。
- 新 task 的判断：`source_type` 改变，用户明确更换时间窗、`viewId`、后端过滤条件或明显不同的数据源范围，或上一次快照标记截断且用户接受缩小范围后重新拉取。
- 复用 task 时，读取同一 `state_task_dir` 下的 `datasource.xlsx` / `manifest.json`，修改并重跑 `analysis step`；不要重新调用 fetch。
- 新建 task 时才调用与 `source_type` 对应的 fetch 脚本拉快照。
- 报表文件名必须是 ASCII 小写语义化 slug，例如 `weekly_ticket_summary.html`、`assignee_group_weekly.html`、`channel_trend.html`。不要使用固定裸名 `report.html`。
- 同一 task 只维护一份主报表：首次分析确定 `REPORT_SLUG` 后，后续追问、改口径、补维度、换图表都覆盖同一个 `<report_slug>.html`，让下载入口始终指向这一份报表的最新版。
- 用户明确更换时间窗或数据源范围导致新 task 时，才重新确定新的 `REPORT_SLUG`。
- 生成报表前必须读取 `/skills/solvea-desk/references/report/report-design.md`，按其中的结构和 `report_data.json` 契约组织数据。
- 报表必须通过 `/skills/solvea-desk/`node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk render-report`` 生成；不要在 `analysis step` 里内联固定 CSS 或大段模板。

## 数据源快照

Shulex Desk 有两种不能混用的数据源：

| 数据源 | `source_type` | 入口 | 适用场景 |
|---|---|---|---|
| 历史报表事实 | `ticket_report_snapshot` | ``node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-sources`` | 时间范围内实际发生的回复/解决行为、实际回复人/解决人、趋势和时效 |
| 当前工单快照 | `ticket_list_snapshot` | ``node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-tickets`` | 当前负责人、当前状态、最后来信、语言、标题正文、标签和视图内核对 |

- 用户问“某段时间实际由谁回复/解决”、回复趋势、解决趋势、实际回复人、实际解决人或后端报表时效时，使用 ``node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-sources``。
- 用户问当前负责人、当前状态、最后来信、语言、标题正文、标签，或明确用 `lastResponseTime` 等当前列表字段筛选时，使用 ``node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-tickets``。
- 用户口中的“处理人”含义不清时，根据其他维度判断：与回复/解决动作绑定的是历史事实；与当前队列、状态或最后来信绑定的是当前工单。仍会改变结果时再追问。
- 同时需要正文分类和实际回复人/报表时效时，分别拉两种快照，以 `ticketNumber` / `ticketId` 关联；必须说明两个接口的时间语义和快照时点，不能用当前 `agent` 替代历史 `responder`。
- `shulex-support` 的 `list-tickets` 查询的是 Shulex 产品售后工单，不属于 Desk 客服台数据。

新建 task 时必须通过 fetch 脚本拉取数据源；复用 task 时不要重新 fetch。报表分析快照按时间范围调用：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-sources \
  --start "2026-06-01T00:00:00+08:00" \
  --end "2026-06-01T00:00:00+08:00" \
  --timezone Asia/Shanghai \
  --page-size 200 \
  --max-pages 200 \
  --max-rows 200000
```

查询当前用户权限与指定工单视图内的原始工单明细：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-tickets \
  --view-id 1 \
  --page-size 100 \
  --max-pages 120 \
  --max-rows 200000 \
  --sort last_update_time \
  --order DESC
```

`solvea-desk fetch-tickets` 调用 `/api_v2/tars/api/ticket/list`，输出固定标记 `source_type=ticket_list_snapshot`、`data_scope=current_user`、`snapshot_semantics=current_state`。请求过滤参数和响应字段见 `references/tickets/query.md`。

当前工单查询必须遵守：

- 把后端已经支持、且值已明确的条件写入 `--filters-json`，例如渠道、负责人 ID、状态、店铺、标签、工单号；不要先拉全量再做这些过滤。
- `--filters-json` 的字段名必须与 `TicketListPageDTO` 一致。不要放入 `page`、`pageSize`、`viewId`、`sort`、`order`；这些使用独立参数。
- `agentIdList` 只接受 ID。用户只给姓名且没有可靠 ID 映射时，不要猜 ID；先使用其他可下推条件缩小数据，再按返回的 `agent` 精确过滤，并在口径中说明它是当前负责人。
- `ticket/list` 不支持的筛选维度不要伪装成请求参数；拉取后在 `analysis step` 中按响应字段过滤，并在口径中说明。
- 脚本持续分页直到接口无下一页或命中安全上限；命中安全上限按截断处理。

例如，按当前负责人 ID 和 eBay 渠道查询：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk fetch-tickets \
  --view-id 1 \
  --filters-json '{"channelList":["ebay"],"agentIdList":[474501]}' \
  --page-size 100 \
  --max-pages 120
```

以下规则仅适用于 `solvea-desk fetch-sources` 的报表分析快照：

规则：

- Agent 只调用场景对应的受控 fetch 脚本，不要直接调用工单接口。
- 数据源只支持按自然日拉取，start 和 end 都包含。查询 2026-07-10 至 2026-07-16，应传 `--start "2026-07-10T00:00:00+08:00" --end "2026-07-16T00:00:00+08:00"`。
- 所有时间统一按北京时间 `Asia/Shanghai` 解释，`start` 和 `end` 必须对齐北京时间 00:00:00。脚本发给 Tars 的是北京时间本地无 offset 时间，不转 UTC，也不支持其他业务时区。
- 默认不传 `timeRangeType`，由 Tars 使用默认的 `report_activity_date`，按回复日期或解决日期筛选。
- 只有用户明确要求按工单创建时间维度筛选时，才增加 `--time-range-type created_at`。Kit 对 `created_at` 同样只开放北京时间自然日，不允许用户指定时分秒。
- 不要拆成半天或小时窗口。接口会丢弃时分秒，只保留日期，因此同一天内继续缩小时段不会减少查询范围。超时降级只能按完整自然日拆窗。
- page-size 最大值为 200，推荐固定使用 `--page-size 200`。不要传 500、1000 等更大值；脚本会直接拒绝，Tars 服务端也只会按 200 处理。
- **数据源单次最大时间范围 60 天**（硬上限）。用户要求的范围超过 60 天时，不要一次性 fetch——接口会直接报错（5xx）。必须按 ≤60 天拆成多个时间窗分别 fetch，或先和用户确认收窄范围；分段拉取后合并分析时，在 `calculation_notes.json` 和最终回复里说明数据是分窗拼接的。
- 字段说明固定维护在 `/skills/solvea-desk/references/report/fields.md`；`solvea-desk fetch-sources` 不生成 `schema.md`。
- 原始接口通常落为 `data` sheet；如果接口临时返回多个 list dataset，脚本仍会分别落为 sheet，但分析时优先使用 `data` sheet。
- 用户 / Agent 传入的时间统一按北京时间 `Asia/Shanghai` 解释；如果时间字符串自带 `Z` / 其他 offset，则先转换到北京时间，再校验是否为自然日边界。
- 内部快照元信息会记录用户业务时间窗口、实际拉取窗口、分页、行数和截断状态。
- fetch 脚本返回的 `task_id`、`state_task_dir` / `output_task_dir` / `tmp_task_dir` 是后续读写路径来源。读取快照用 `state_task_dir`，写用户下载物用 `output_task_dir`，写草稿用 `tmp_task_dir`。
- 如果脚本返回 `truncated=true` 或退出码 `3`，说明命中分页 / 行数上限；必须提示用户缩小时间范围或降低分析粒度，不能把结果说成全量精确。
- 只按时间拉快照，因此首响、解决时长、解决率等生命周期指标可能受窗口边界影响；有风险时必须在 `calculation_notes.json` 和最终回复里说明。

## 字段说明

`datasource.xlsx` 默认读取 `data` sheet。根据 source type 读取 `/skills/solvea-desk/references/report/fields.md` 或 `/skills/solvea-desk/references/tickets/query.md` 确认字段含义。

## 分析脚本

Agent 读取 `manifest.json` 和 `datasource.xlsx` 后，自写最终脚本：

```text
workspace/state/solvea-desk/<task_id>/analysis step
```

分析脚本必须使用下面的路径模板，不要在 Python 代码里硬编码 `/workspace/...`：

```python
import os
from pathlib import Path

WORKSPACE_DIR = Path(os.environ["WORKSPACE_DIR"])
TASK_ID = "<对应 fetch 脚本返回的 task_id>"
STATE_TASK_DIR = WORKSPACE_DIR / "state" / "solvea-desk" / TASK_ID
OUTPUT_TASK_DIR = WORKSPACE_DIR / "outputs" / "solvea-desk" / TASK_ID
TMP_TASK_DIR = WORKSPACE_DIR / "tmp" / "solvea-desk" / TASK_ID

OUTPUT_TASK_DIR.mkdir(parents=True, exist_ok=True)
TMP_TASK_DIR.mkdir(parents=True, exist_ok=True)
```

`analysis step` 构造 `report_data.json` 时必须先定义下面这些 helper，再用 helper 组装数据，减少结构写错：

```python
REPORT_SLUG = "<semantic_slug>"


def kpi(label, value, basis):
    return {"label": label, "value": str(value), "basis": basis}


def col(key, label, numeric=False):
    item = {"key": key, "label": label}
    if numeric:
        item["numeric"] = True
    return item


def section(title, columns, rows, chart=None, description="", note=""):
    return {
        "title": title,
        "description": description,
        "columns": columns,
        "rows": rows,
        **({"chart": chart} if chart else {}),
        **({"note": note} if note else {}),
    }
```

要求：

- 只读取同一 `STATE_TASK_DIR` 下的 `datasource.xlsx` / `manifest.json`。
- 字段含义只参考对应 source type 的字段文档，不要要求或生成 `schema.md`。
- 用 pandas / openpyxl 处理 XLSX。
- 不调用外部接口，不访问当前授权范围之外的数据。
- 必须输出 `STATE_TASK_DIR/calculation_notes.json` 和 `STATE_TASK_DIR/report_data.json`。
- `analysis step` 里显式定义 `REPORT_SLUG = "<semantic_slug>"`，并写入 `report_data.json.report_slug`；同一报表迭代复用同一个 slug，新场景换新 slug。
- `report_data.json` 必须按 `references/report/report-design.md` 契约写顶层 `kpis` 和 `sections`；不要把 `overview`、`personal_performance`、`daily_trend`、`status_distribution` 这类分析中间结果直接当作 renderer 输入。
- columns 必须是对象数组，也就是 `sections[].columns` 每列至少包含 `key` 和 `label`，例如 `col("date", "日期")`；不要写成字符串数组。
- 有图表的 section 仍然必须提供同一份 `rows`；报表默认先展示表格，并提供表格 / 图表切换。报表静态图支持 `line`、`bar`、`pie`、`scatter`，与 `render_chart` 工具支持类型一致。
- 报表图表配置只写小型结构：`bar` / `line` / `scatter` 用 `{"chartType": "...", "xKey": "...", "yKey": "...", "label": "..."}`；`pie` 用 `{"chartType": "pie", "nameKey": "...", "valueKey": "...", "label": "..."}`。不要写 ECharts option、`x`、`series` 或图表模板。
- `analysis step` 只负责计算和写结构化数据，不要拼接固定模板/CSS。
- 每次运行 `analysis step` 写完 `report_data.json` 后，必须立刻执行 `solvea-desk render-report --validate-only` 校验结构；校验失败时修改并重跑 `analysis step`，不要在生成报表阶段临时重写 `report_data.json`。
- 生成或更新报表时调用：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk render-report \
  --task-id "<task_id>" \
  --report-slug "<semantic_slug>"
```

- 校验命令：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk render-report \
  --task-id "<task_id>" \
  --report-slug "<semantic_slug>" \
  --validate-only
```

- renderer 默认读取 `STATE_TASK_DIR/report_data.json` 和 `STATE_TASK_DIR/calculation_notes.json`，输出 `OUTPUT_TASK_DIR/<report_slug>.html`。生成报表阶段只允许调用 `solvea-desk render-report`；如果发现 `report_data.json` 不符合契约，回到 `analysis step` 修改并重跑 `analysis step`，不要用一次性脚本临时改 `report_data.json`。
- 用户要求明细或脚本判断需要明细时，输出 `OUTPUT_TASK_DIR/<report_slug>_detail.xlsx`。
- 临时草稿、调试 CSV、图表中间数据写 `TMP_TASK_DIR`。
- 无法判断口径时，在 `calculation_notes.json` 里写明假设或限制，不要假装精确。

轻量查询流程：

- 用户说“看看本周工单”“看一下今天工单”“本月情况”这类轻量业务问题时，也必须完成：拉快照或复用 task、写/更新分析脚本、写 `calculation_notes.json`、写/更新 `report_data.json`、调用至少一次 `render_chart`、生成或更新报表，最终正文给核心数字说明和 Markdown 表格。
- 轻量查询默认输出 3-5 个核心数字，例如工单总量、每日趋势、渠道分布、状态分布、AI 回复相关指标；具体字段以对应 source type 的字段文档为准，字段缺失就说明不能算。
- 图表优先给每日趋势 + 渠道 / 状态分布，放在一次 `render_chart` 调用的 `charts` 数组中；不要只生成下载文件后结束。

报表生成规则：

- 用户要求业务指标、趋势、对比、可视化、明细或报表时，默认生成或更新报表。
- 只要时间范围、数据源范围和必要口径足够明确，就直接调用 `solvea-desk render-report` 生成或更新报表；不要额外询问“是否生成报表”。
- 除非缺少必要信息、需要用户选择时间范围或口径，否则不要为了生成报表再停下来等确认。
- 用户要求换图表、改口径、补维度时，基于同一 task 重算，更新对话内图表/表格，并覆盖同一份主报表。
- 对用户只说“报表”，不要说“HTML”；正文里可以写实际文件名，但不要解释文件格式技术细节。

输出收敛原则：

- 按用户问题的复杂度收敛动作和正文。用户只是确认数据结构、字段、行数、某个中间结果时，直接回答确认结果即可，不要强行生成完整报表、图表和交付物。
- 用户要求业务指标、趋势、对比、可视化、明细或报表时，默认生成或更新报表，并给对话内图表、表格和口径说明。用户只是确认数据结构、字段、行数、某个中间结果时，可以不生成报表。

## 业务分析规则

MVP 目标是辅助分析，不是权威财务 / 税务 / 对外汇报数据源。

优先支持：

- **复杂过滤**：渠道、店铺 / 邮箱、客服 / 客服组、品牌、品类、关键词、工作日 / 周末、AI / 人工、满意度评分 / 是否有满意度反馈等；具体字段以对应 source type 的字段文档为准。
- **换维度**：按渠道、店铺、邮箱、客服、客服组、品牌、品类、日期桶、满意度评分档等分组；字段不存在时说明无法直接计算。
- **改口径**：用户明确说“不要剔除广告”“只算人工”“分子只算客户回复谢谢”等时，以用户口径优先。
- **满意度（CSAT）分析**：用户要看满意度时，用 `satisfactionScore` 算平均满意度 / 评分分布 / 好评差评占比，用 `satisfactionFeedback` 摘录差评原声做归因。分母只算有评分的工单，并同时给出满意度回收率（有评分工单 / 工单总数）；样本过小或回收率低时必须在口径里说明，不要拿少量评分代表整体。

默认规则：

- 报表快照的新 task 用户没说时间时先确认时间范围，不要默认本月；同一 task 的追问沿用当前 task 时间范围。原始工单明细快照不要求时间范围。
- 用户明确说“本周”时，按当前日期所在 ISO 周计算：周一 00:00:00 到当前时刻；如需整周报表可以到周日 23:59:59，但必须在范围里说清楚。不要把周二误写成周一。
- 用户没说口径，沿用工单报表默认业务口径；如果当前快照字段无法支撑默认口径，必须说明替代口径。
- 用户要求对比时，优先用等长上一周期；同比 / 环比必须写清楚对比时间窗。
- 不要凭字段名猜业务含义。字段说明缺失时，可以在最终回复中标为“按字段名推断”，并降低结论确定性。

## 口径账本

`calculation_notes.json` 是最终回复和报表的可信来源。每个核心指标都应有一条记录：

```json
[
  {
    "metric": "解决率",
    "value": "14.29%",
    "algorithm": "1 个已解决工单 / 共 7 个工单",
    "range": "2026-05-01 至 2026-05-17",
    "filters": ["Email 渠道", "排除 AI 关单"],
    "definition": "已解决 = 在统计范围内标记为已解决的工单",
    "limitations": []
  }
]
```

输出要求：

- 每个核心数字必须能生成下面 4 行说明，全部用业务语言，不出现字段名、SQL、接口内部名。
- 对话最终回复中的口径说明必须使用 Markdown 列表：每个指标一条一级列表，算法 / 范围 / 口径用二级列表。不要把口径说明写成普通段落里的单换行，因为标准 Markdown 会把段落内单换行折叠成空格。

```markdown
- **解决率：14.29%**
  - 算法：1 个已解决工单 / 共 7 个工单
  - 范围：2026-05-01 至 2026-05-17，剔除广告/通知工单
  - 口径：已解决 = 标记已解决时间在范围内的工单
```

- `calculation_notes.json` 每条记录至少包含 `metric`、`value`、`algorithm`、`range`、`definition`、`filters`、`limitations`。旧字段名 `formula` 不要再新增。
- 主视图用业务语言，不直接展示 SQL、内部字段名或 `manifest.json` 这类内部文件名；面对用户说“数据范围、数据行数、是否截断、快照生成时间”。
- 有窗口边界、截断、字段缺失、样本过小等风险时，`limitations` 不能为空。
- 用户质疑口径时，基于同一快照修改 `analysis step` 重算；不要只改文案。

## 图表展示

对话内图表不使用 Markdown code fence，不新增 SSE 自定义事件。需要图表时必须调用内置工具：

```json
{
  "charts": [
    {
      "title": "Ticket Trend",
      "description": "Daily ticket count in the selected range.",
      "chartType": "line",
      "option": {
        "xAxis": {"type": "category", "data": ["Mon", "Tue"]},
        "yAxis": {"type": "value"},
        "series": [{"name": "Tickets", "type": "line", "data": [12, 18]}]
      }
    },
    {
      "title": "Channel Share",
      "description": "Ticket share by source.",
      "chartType": "pie",
      "option": {
        "series": [
          {
            "name": "Source",
            "type": "pie",
            "data": [{"name": "Email", "value": 12}, {"name": "Chat", "value": 18}]
          }
        ]
      }
    }
  ]
}
```

约束：

- 调用 `render_chart` 前必须先用一句简洁自然语言说明本次要渲染的统计维度和指标，例如：“下面渲染每日工单量、渠道分布和状态分布三张概览图。”不要突然甩出图表工具调用。
- `render_chart` 工具内部会校验 ECharts option；校验失败会作为 tool error 返回，必须修正后再继续。
- 不要在 ECharts option 里使用函数、字符串模板或高风险配置；例如 `tooltip.formatter` 会被工具安全校验拒绝，直接使用 `tooltip.trigger` 即可。
- 一次调用最多传 4 张图。报表预览有多个图时优先放在同一个 `charts` 数组里，让前端自适应网格展示；超过 4 张时拆成多次 `render_chart` 调用，不要为了“测试上限”故意传 5 张触发失败。
- 成功结果唯一协议为 `{"type":"chart","version":1,"charts":[...]}`，Agent 不要手写这段 result。
- 支持图表类型：`line`、`bar`、`pie`、`scatter`。
- 如果用户指定的图表类型不在 line、bar、pie、scatter 中，例如漏斗图、雷达图、热力图、桑基图、地图，必须先说明当前 `render_chart` 暂不支持该图表类型，并给出最接近的支持方案；不要调用 render_chart 去试错。
- 图表数据要控制体量，长明细放明细文件或报表，不要塞进工具入参。
- 不要在普通 assistant 文本里输出 ECharts JSON 或 Markdown code fence。

ECharts option 安全兜底：

- 只使用纯 JSON option，不使用 JS 函数、回调、URL 或字符串模板。
- 禁止任何层级的 `formatter` 和 `renderItem`，包括 `tooltip.formatter`、`label.formatter`、`axisLabel.formatter`。这些在 ECharts 中可用，但当前工具会递归拒绝。
- 需要显示数据值时，用 `series[].label.show = true`，并按图表类型补 `position`：柱状图用 `top`，折线 / 散点用 `top`，饼图用 `outside`。
- 需要 tooltip 时，只写 `tooltip: {"trigger": "axis"}` 或 `tooltip: {"trigger": "item"}`。
- 需要图例时，只写 `legend` 的基础布局，例如 `{"top": 0}` 或 `{"left": "left", "orient": "vertical"}`。
- 需要控制边距时，只写 `grid: {"left": 48, "right": 24, "top": 48, "bottom": 48, "containLabel": true}`。
- 类目轴标签包含客服组、店铺、渠道等名称时，默认加 `xAxis.axisLabel.interval = 0`，保证所有类目都显示；如果名称较长，再加 `xAxis.axisLabel.rotate = 20` 到 `35`，并把 `grid.bottom` 提到 72 以上。
- 类目名称特别长时，xAxis 可使用短显示名，完整名称放在图表 `description` 或最终回复表格里；不要让长标签把坐标轴挤没。
- 字段名、单位、百分比等说明放在图表 `title` / `description` / 轴 `name` / 最终回复口径说明里，不靠 formatter 拼接。

优先套用这些安全模板：

```json
{
  "line_or_bar": {
    "tooltip": {"trigger": "axis"},
    "legend": {"top": 0},
    "grid": {"left": 48, "right": 24, "top": 48, "bottom": 72, "containLabel": true},
    "xAxis": {
      "type": "category",
      "data": ["06-01", "06-02"],
      "axisLabel": {"interval": 0, "rotate": 20}
    },
    "yAxis": {"type": "value", "name": "工单数"},
    "series": [
      {
        "name": "工单数",
        "type": "bar",
        "data": [12, 18],
        "label": {"show": true, "position": "top"}
      }
    ]
  },
  "pie": {
    "tooltip": {"trigger": "item"},
    "legend": {"left": "left", "orient": "vertical"},
    "series": [
      {
        "name": "渠道",
        "type": "pie",
        "radius": "60%",
        "data": [{"name": "Email", "value": 12}, {"name": "Chat", "value": 18}],
        "label": {"show": true, "position": "outside"}
      }
    ]
  },
  "scatter": {
    "tooltip": {"trigger": "item"},
    "grid": {"left": 48, "right": 24, "top": 48, "bottom": 48, "containLabel": true},
    "xAxis": {"type": "value", "name": "响应时长"},
    "yAxis": {"type": "value", "name": "满意度"},
    "series": [
      {
        "name": "样本",
        "type": "scatter",
        "data": [[3, 4.9], [8, 4.7]],
        "label": {"show": true, "position": "top"}
      }
    ]
  }
}
```

## 最终回复格式

回复用户时：

1. 用普通文本说明核心结论。
2. 用一句话说明即将渲染的图表维度和指标，然后调用 `render_chart` 工具生成图表块；轻量查询也至少调用一次。
3. 输出用于核对的 Markdown 表格数据，例如每日趋势、渠道分布、状态分布或用户指定维度；不要只给图不列数据。
4. 每个核心数字按 Markdown 列表格式输出，内容来自 `calculation_notes.json`。每个指标一条一级列表，算法 / 范围 / 口径用二级列表；不要写成普通段落里的单换行。
5. 如果本次生成或更新了报表 / 明细文件，再补一个简短“交付物”小节：

```markdown
## 交付物

- 报表：`<report_slug>.html`
- 明细文件：`<report_slug>_detail.xlsx`（如有）
```

前端 finished 事件会展示 outputs 下载链接；正文里只写本轮实际文件名，例如 `assignee_group_weekly.html`，不要写占位名。
6. 最后用一句话主动引导下一步。已生成报表时，提示可改维度、补明细或换口径；未生成报表时，只说明缺少哪些必要信息。
