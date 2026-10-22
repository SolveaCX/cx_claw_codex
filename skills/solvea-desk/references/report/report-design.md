# Shulex Desk HTML Design

This document defines the visual and structural standard for `solvea-desk` HTML deliverables.
The renderer uses the sibling files:

- `report.css`: fixed self-contained CSS for the report.
- `report-template.html`: fixed semantic HTML shell with renderer placeholders.

Agents should not copy these files into `analysis.py`. Generate structured `report_data.json`, then call `scripts/report/render_report.py` to build the HTML.

## Design Read

This is an operational report for support leads and business operators. It should feel calm, precise, and audit-friendly: closer to a finance packet or executive operations memo than a marketing page.

Use the taste/frontend principles only selectively: readable hierarchy, restrained palette, stable density, and no generic AI decoration. This is not a landing page, portfolio, or brand hero.

Design goals:

- Make the first screen useful: show report title, time range, data freshness, and 3-5 key metrics.
- Make numbers easy to audit: every KPI must have a nearby short basis/definition.
- Make dense tables readable without looking like raw exports.
- Use a restrained palette and stable layout that prints cleanly.
- Keep the report self-contained: no remote fonts, no external CSS, no external JavaScript.

Avoid:

- Hero/landing-page composition, decorative gradients, glassmorphism, large empty visual sections.
- Nested cards and card-heavy dashboards.
- Emoji, playful copy, marketing taglines.
- Low-contrast grey text, tiny table text, or saturated single-hue themes.

## Report Data Contract

`analysis.py` writes `STATE_TASK_DIR/report_data.json`. The renderer accepts this shape:

```json
{
  "report_slug": "assignee_group_weekly",
  "title": "客服组周报",
  "subtitle": "按客服组统计本周工单量、状态分布和 AI 解决情况。",
  "range": "2026-06-01 至 2026-06-08（北京时间）",
  "row_count": 55,
  "truncated": false,
  "generated_at": "2026-06-08T10:30:00+08:00",
  "kpis": [
    {"label": "工单总量", "value": "55", "basis": "按工单 ID 去重"}
  ],
  "sections": [
    {
      "title": "客服组工单量",
      "description": "按当前处理组汇总。",
      "chart": {
        "chartType": "bar",
        "xKey": "group",
        "yKey": "tickets",
        "label": "工单数"
      },
      "columns": [
        {"key": "group", "label": "客服组"},
        {"key": "tickets", "label": "工单数", "numeric": true}
      ],
      "rows": [
        {"group": "CxjOnly", "tickets": 23}
      ],
      "note": "未设置客服组的工单归入未分组。"
    }
  ],
  "footer": "本报告由 Shulex 基于当前账号授权范围内的工单快照生成，仅供运营分析使用。"
}
```

Rules:

- `report_slug` must be ASCII lowercase snake_case, for example `weekly_ticket_summary`.
- `report_data.json` must contain top-level `kpis` or `sections`; usually both. The renderer rejects free-form legacy shapes that only contain `overview`, `personal_performance`, `daily_trend`, or `status_distribution`.
- `row_count` means the raw snapshot row count from `fetch_sources.py`; `render_report.py` fills it from `manifest.json.row_counts` when omitted. Do not use filtered analysis sample size here.
- Visible labels should be Chinese business labels. Raw field names can appear only in short audit notes when necessary.
- Table columns should be ordered by business importance, not raw data order.
- Use `numeric: true` for numeric columns so the renderer can right-align and use tabular numbers.
- `sections[].chart` is optional. HTML reports support self-contained static `bar`、`line`、`pie`、`scatter` charts. Use the same chart type vocabulary as the `render_chart` tool.
- `bar`、`line`、`scatter` charts use `{"chartType": "bar|line|scatter", "xKey": "...", "yKey": "...", "label": "..."}`.
- `pie` charts use `{"chartType": "pie", "nameKey": "...", "valueKey": "...", "label": "..."}`. `xKey/yKey` can be used only when they clearly mean category/value.
- `chart_type` and `type` are accepted as aliases, but new `analysis.py` should write `chartType`.
- Chart sections always render a toggle: table is selected first, and the same `rows` can be viewed as the configured static chart.
- Agents must not generate chart HTML, CSS, JavaScript, or full ECharts options for HTML reports. The renderer builds the static chart from the same summary `rows`, so token cost stays close to a table plus a small chart config.
- Keep `sections[].rows` to report-sized summaries. Long raw detail belongs in `<report_slug>_detail.xlsx`.
- Do not put raw HTML in `report_data.json`; the renderer escapes values intentionally.

## Analysis Script Contract Template

`analysis.py` should define small local helpers before building `report_data`. This avoids the common failure where `columns` is written as `["日期", "工单数"]` instead of renderer-readable objects.

Copy this shape and fill it with the current report's metrics and summary rows:

```python
REPORT_SLUG = "weekly_ticket_summary"


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


daily_rows = [
    {"date": "03-01", "tickets": 12},
    {"date": "03-02", "tickets": 18},
]

report_data = {
    "report_slug": REPORT_SLUG,
    "title": "工单周报",
    "range": "2026-03-01 至 2026-03-07（北京时间）",
    "truncated": bool(manifest.get("truncated")),
    "kpis": [
        kpi("工单总量", total_tickets, "按工单 ID 去重"),
    ],
    "sections": [
        section(
            "每日工单趋势",
            [col("date", "日期"), col("tickets", "工单数", numeric=True)],
            daily_rows,
            chart={"chartType": "line", "xKey": "date", "yKey": "tickets", "label": "工单数"},
        )
    ],
}
```

Rules for the template:

- `columns` 必须是对象数组，每个对象至少有 `key` 和 `label`；不要写成字符串数组。
- Every `rows` item must use the same keys declared in `columns`.
- Chart data comes from the same `rows`; do not create separate `x` / `series` fields for HTML.
- Run `render_report.py --validate-only` immediately after writing `report_data.json`.

## Page Structure

The renderer outputs this structure:

1. Report masthead
   - Title
   - Subtitle
   - Meta strip: data range, row count, truncation status, generated time
2. KPI band
   - 3-5 compact KPI blocks
   - Each block has label, value, and one short basis line
3. Main sections
   - Each section starts with an `h2`
   - Optional static chart for compact trends or breakdowns; chart sections include a table/chart toggle by default
   - Tables for comparisons and breakdowns when no chart is configured
   - Short notes below tables for caveats
4. Calculation notes
   - Compact formula / range / definition from `calculation_notes.json`
5. Footer
   - Authorized snapshot statement and limitations

## Rendering

Use the renderer:

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher script skills/solvea-desk/scripts/report/render_report.py \
  --task-id "<task_id>" \
  --report-slug "assignee_group_weekly"
```

Default paths:

- Input: `workspace/state/solvea-desk/<task_id>/report_data.json`
- Input: `workspace/state/solvea-desk/<task_id>/calculation_notes.json`
- Output: `workspace/outputs/solvea-desk/<task_id>/<report_slug>.html`

Use `--report-data`, `--notes`, or `--output` only for local debugging or unusual internal workflows.

## File Naming

The report file name must match the analysis scenario:

- Weekly summary: `weekly_ticket_summary.html`
- Assignee group breakdown: `assignee_group_weekly.html`
- Channel trend: `channel_trend.html`
- CSAT analysis: `csat_analysis.html`

When the user refines the same report, overwrite the same file. When the user starts a clearly different report, choose a new slug.
