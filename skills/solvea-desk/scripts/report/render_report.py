#!/usr/bin/env python3
"""Render a solvea-desk HTML file from structured report data."""

import os
import sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import OUTPUTS_DIR, STATE_DIR  # noqa: E402

import argparse
import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
SUPPORTED_CHART_TYPES = {"bar", "line", "pie", "scatter"}
CHART_COLORS = ["#2563eb", "#0f766e", "#b54708", "#7c3aed", "#c026d3", "#475467", "#059669", "#dc2626"]


def _skill_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _html(value: Any) -> str:
    return escape(_text(value), quote=True)


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _display_number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 2)


def _validate_slug(slug: str) -> str:
    normalized = slug.strip()
    if not SLUG_RE.fullmatch(normalized):
        raise ValueError("report slug must be ASCII lowercase snake_case, for example assignee_group_weekly")
    return normalized


def _meta_items(report: dict[str, Any], notes: list[dict[str, Any]]) -> str:
    generated_at = report.get("generated_at") or datetime.now().astimezone().isoformat(timespec="seconds")
    range_text = report.get("range") or report.get("time_range") or (notes[0].get("range") if notes else "")
    row_count = report.get("row_count", "")
    truncated = report.get("truncated")
    if truncated is True:
        truncated_text = '<span class="badge warn">已截断</span>'
    elif truncated is False:
        truncated_text = '<span class="badge good">未截断</span>'
    else:
        truncated_text = "未说明"
    items = [
        ("统计范围", _html(range_text)),
        ("数据行数", _html(row_count)),
        ("截断状态", truncated_text),
        ("生成时间", _html(generated_at)),
    ]
    blocks = []
    for label, value in items:
        blocks.append(
            "\n".join(
                [
                    '          <div class="meta-item">',
                    f'            <div class="meta-label">{_html(label)}</div>',
                    f'            <div class="meta-value">{value}</div>',
                    "          </div>",
                ]
            )
        )
    return "\n".join(blocks)


def _kpi_blocks(report: dict[str, Any]) -> str:
    kpis = report.get("kpis") or []
    if not kpis:
        return '          <div class="empty">暂无核心指标。</div>'
    blocks = []
    for item in kpis[:5]:
        blocks.append(
            "\n".join(
                [
                    '          <div class="kpi">',
                    f'            <div class="kpi-label">{_html(item.get("label") or item.get("metric"))}</div>',
                    f'            <div class="kpi-value">{_html(item.get("value"))}</div>',
                    f'            <div class="kpi-note">{_html(item.get("basis") or item.get("note") or item.get("definition"))}</div>',
                    "          </div>",
                ]
            )
        )
    return "\n".join(blocks)


def _columns_for(section: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = section.get("columns")
    if isinstance(columns, list) and columns:
        result = []
        for column in columns:
            if isinstance(column, str):
                result.append({"key": column, "label": column})
            elif isinstance(column, dict) and column.get("key"):
                result.append(column)
        if result:
            return result
    if not rows:
        return []
    return [{"key": key, "label": key} for key in rows[0].keys()]


def _table(section: dict[str, Any]) -> str:
    rows = section.get("rows") or []
    if not rows:
        return '<p class="empty">暂无明细数据。</p>'
    columns = _columns_for(section, rows)
    header_cells = []
    for column in columns:
        key = column["key"]
        numeric = column.get("numeric")
        if numeric is None:
            numeric = any(_is_numeric(row.get(key)) for row in rows)
        cls = ' class="num"' if numeric else ""
        header_cells.append(f"<th{cls}>{_html(column.get('label') or key)}</th>")
    body_rows = []
    for row in rows:
        cells = []
        for column in columns:
            key = column["key"]
            numeric = column.get("numeric")
            if numeric is None:
                numeric = _is_numeric(row.get(key))
            cls = ' class="num"' if numeric else ""
            cells.append(f"<td{cls}>{_html(row.get(key))}</td>")
        body_rows.append(f"          <tr>{''.join(cells)}</tr>")
    return "\n".join(
        [
            '        <div class="table-wrap">',
            "          <table>",
            f"            <thead><tr>{''.join(header_cells)}</tr></thead>",
            "            <tbody>",
            "\n".join(body_rows),
            "            </tbody>",
            "          </table>",
            "        </div>",
        ]
    )


def _bar_chart(section: dict[str, Any], chart: dict[str, Any]) -> str:
    rows = section.get("rows") or []
    if not rows:
        return ""
    x_key = chart.get("xKey") or chart.get("x_key")
    y_key = chart.get("yKey") or chart.get("y_key")
    if not x_key or not y_key:
        return '<p class="note">图表配置缺少 xKey 或 yKey，已保留表格数据。</p>'

    points = []
    for row in rows:
        value = _number(row.get(y_key))
        if value is None:
            continue
        points.append((row.get(x_key), value))
    if not points:
        return '<p class="note">图表数值为空，已保留表格数据。</p>'

    max_items = chart.get("maxItems") or chart.get("max_items") or 24
    try:
        max_items = max(1, int(max_items))
    except (TypeError, ValueError):
        max_items = 24
    trimmed = points[:max_items]
    max_value = max(value for _, value in trimmed)
    if max_value <= 0:
        max_value = 1

    label = _text(chart.get("label") or y_key)
    title = _text(chart.get("title") or section.get("title") or "分析结果")
    bars = []
    for raw_name, value in trimmed:
        name = _text(raw_name)
        percent = max(2.0, min(100.0, value / max_value * 100))
        display_value = _display_number(value)
        bars.append(
            "\n".join(
                [
                    f'          <div class="chart-bar" aria-label="{_html(name)} {_html(label)} {_html(display_value)}">',
                    f'            <div class="chart-bar-value">{_html(display_value)}</div>',
                    '            <div class="chart-bar-track">',
                    f'              <div class="chart-bar-fill" style="height: {percent:.2f}%"></div>',
                    "            </div>",
                    f'            <div class="chart-bar-label">{_html(name)}</div>',
                    "          </div>",
                ]
            )
        )

    more_note = ""
    if len(points) > len(trimmed):
        more_note = f'        <p class="chart-note">图表展示前 {len(trimmed)} 项，其余数据保留在表格中。</p>'
    return "\n".join(
        [
            f'        <div class="report-chart report-chart-bar" role="img" aria-label="{_html(title)} 图表">',
            f'          <div class="chart-title">{_html(title)} 图表</div>',
            '          <div class="chart-bars">',
            "\n".join(bars),
            "          </div>",
            more_note,
            "        </div>",
        ]
    )


def _chart_type(chart: dict[str, Any]) -> str:
    return _text(chart.get("chartType") or chart.get("chart_type") or chart.get("type")).lower()


def _axis_keys(chart: dict[str, Any]) -> tuple[str | None, str | None]:
    return chart.get("xKey") or chart.get("x_key"), chart.get("yKey") or chart.get("y_key")


def _column_label(section: dict[str, Any], key: str | None, fallback: str) -> str:
    if key:
        for column in section.get("columns") or []:
            if isinstance(column, dict) and column.get("key") == key:
                return _text(column.get("label") or key)
    return fallback


def _xy_points(section: dict[str, Any], chart: dict[str, Any]) -> tuple[str, str, list[tuple[Any, float]]]:
    rows = section.get("rows") or []
    x_key, y_key = _axis_keys(chart)
    if not x_key or not y_key:
        return "", "", []
    points = []
    for row in rows:
        value = _number(row.get(y_key))
        if value is None:
            continue
        points.append((row.get(x_key), value))
    return x_key, y_key, points


def _max_items(chart: dict[str, Any], default: int = 24) -> int:
    max_items = chart.get("maxItems") or chart.get("max_items") or default
    try:
        return max(1, int(max_items))
    except (TypeError, ValueError):
        return default


def _line_chart(section: dict[str, Any], chart: dict[str, Any]) -> str:
    x_key, y_key, points = _xy_points(section, chart)
    if not x_key or not y_key:
        return '<p class="note">图表配置缺少 xKey 或 yKey，已保留表格数据。</p>'
    if not points:
        return '<p class="note">图表数值为空，已保留表格数据。</p>'

    trimmed = points[:_max_items(chart, 36)]
    values = [value for _, value in trimmed]
    min_value = min(values)
    max_value = max(values)
    if max_value == min_value:
        max_value = min_value + 1
    width = 720
    height = 260
    left = 46
    right = 18
    top = 22
    bottom = 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    step = plot_width / max(1, len(trimmed) - 1)
    label = _text(chart.get("label") or _column_label(section, y_key, y_key))
    title = _text(chart.get("title") or section.get("title") or "分析结果")

    coordinates = []
    point_nodes = []
    labels = []
    for idx, (raw_name, value) in enumerate(trimmed):
        x = left + idx * step
        y = top + (max_value - value) / (max_value - min_value) * plot_height
        coordinates.append(f"{x:.2f},{y:.2f}")
        name = _text(raw_name)
        display_value = _display_number(value)
        point_nodes.append(
            f'            <circle class="chart-point" cx="{x:.2f}" cy="{y:.2f}" r="4" '
            f'aria-label="{_html(name)} {_html(label)} {_html(display_value)}"></circle>'
        )
        labels.append(
            "\n".join(
                [
                    f'            <text class="chart-point-label" x="{x:.2f}" y="{max(12, y - 8):.2f}">{_html(display_value)}</text>',
                    f'            <text class="chart-axis-label" x="{x:.2f}" y="{height - 14}">{_html(name)}</text>',
                ]
            )
        )

    more_note = ""
    if len(points) > len(trimmed):
        more_note = f'        <p class="chart-note">图表展示前 {len(trimmed)} 项，其余数据保留在表格中。</p>'
    coordinate_text = " ".join(coordinates)
    return "\n".join(
        [
            f'        <div class="report-chart report-chart-line" role="img" aria-label="{_html(title)} 图表">',
            f'          <div class="chart-title">{_html(title)} 图表</div>',
            f'          <svg class="chart-svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none">',
            f'            <line class="chart-axis" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"></line>',
            f'            <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}"></line>',
            f'            <polyline class="chart-line" points="{coordinate_text}"></polyline>',
            "\n".join(point_nodes),
            "\n".join(labels),
            "          </svg>",
            more_note,
            "        </div>",
        ]
    )


def _pie_chart(section: dict[str, Any], chart: dict[str, Any]) -> str:
    rows = section.get("rows") or []
    name_key = chart.get("nameKey") or chart.get("name_key") or chart.get("xKey") or chart.get("x_key")
    value_key = chart.get("valueKey") or chart.get("value_key") or chart.get("yKey") or chart.get("y_key")
    if not name_key or not value_key:
        return '<p class="note">饼图配置缺少 nameKey 或 valueKey，已保留表格数据。</p>'

    points = []
    for row in rows:
        value = _number(row.get(value_key))
        if value is None or value <= 0:
            continue
        points.append((row.get(name_key), value))
    if not points:
        return '<p class="note">图表数值为空，已保留表格数据。</p>'

    trimmed = points[:_max_items(chart, 12)]
    total = sum(value for _, value in trimmed)
    if total <= 0:
        return '<p class="note">图表数值为空，已保留表格数据。</p>'
    label = _text(chart.get("label") or _column_label(section, value_key, value_key))
    title = _text(chart.get("title") or section.get("title") or "分析结果")
    offset = 0.0
    segments = []
    legend_items = []
    for idx, (raw_name, value) in enumerate(trimmed):
        name = _text(raw_name)
        display_value = _display_number(value)
        percent = value / total * 100
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        segments.append(
            f'              <circle class="pie-segment" cx="110" cy="110" r="72" pathLength="100" '
            f'fill="transparent" stroke="{color}" stroke-width="42" '
            f'stroke-dasharray="{percent:.2f} {100 - percent:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 110 110)" aria-label="{_html(name)} {_html(label)} {_html(display_value)}"></circle>'
        )
        legend_items.append(
            "\n".join(
                [
                    '              <li>',
                    f'                <span class="pie-swatch" style="background: {color}"></span>',
                    f'                <span>{_html(name)}</span>',
                    f'                <strong>{_html(display_value)}</strong>',
                    "              </li>",
                ]
            )
        )
        offset += percent

    more_note = ""
    if len(points) > len(trimmed):
        more_note = f'        <p class="chart-note">图表展示前 {len(trimmed)} 项，其余数据保留在表格中。</p>'
    return "\n".join(
        [
            f'        <div class="report-chart report-chart-pie" role="img" aria-label="{_html(title)} 图表">',
            f'          <div class="chart-title">{_html(title)} 图表</div>',
            '          <div class="pie-layout">',
            '            <svg class="chart-pie-svg" viewBox="0 0 220 220">',
            "\n".join(segments),
            '              <circle class="pie-hole" cx="110" cy="110" r="48"></circle>',
            "            </svg>",
            '            <ul class="pie-legend">',
            "\n".join(legend_items),
            "            </ul>",
            "          </div>",
            more_note,
            "        </div>",
        ]
    )


def _scatter_chart(section: dict[str, Any], chart: dict[str, Any]) -> str:
    rows = section.get("rows") or []
    x_key, y_key = _axis_keys(chart)
    if not x_key or not y_key:
        return '<p class="note">散点图配置缺少 xKey 或 yKey，已保留表格数据。</p>'

    points = []
    for row in rows:
        x_value = _number(row.get(x_key))
        y_value = _number(row.get(y_key))
        if x_value is None or y_value is None:
            continue
        points.append((x_value, y_value))
    if not points:
        return '<p class="note">图表数值为空，已保留表格数据。</p>'

    trimmed = points[:_max_items(chart, 80)]
    x_values = [x for x, _ in trimmed]
    y_values = [y for _, y in trimmed]
    min_x = min(x_values)
    max_x = max(x_values)
    min_y = min(y_values)
    max_y = max(y_values)
    if min_x == max_x:
        max_x = min_x + 1
    if min_y == max_y:
        max_y = min_y + 1
    width = 720
    height = 260
    left = 58
    right = 22
    top = 22
    bottom = 54
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_label = _text(chart.get("xLabel") or chart.get("x_label") or _column_label(section, x_key, x_key))
    y_label = _text(chart.get("yLabel") or chart.get("y_label") or _column_label(section, y_key, y_key))
    title = _text(chart.get("title") or section.get("title") or "分析结果")

    point_nodes = []
    for x_value, y_value in trimmed:
        x = left + (x_value - min_x) / (max_x - min_x) * plot_width
        y = top + (max_y - y_value) / (max_y - min_y) * plot_height
        point_nodes.append(
            f'            <circle class="chart-point" cx="{x:.2f}" cy="{y:.2f}" r="5" '
            f'aria-label="{_html(x_label)} {_html(_display_number(x_value))} {_html(y_label)} {_html(_display_number(y_value))}"></circle>'
        )

    more_note = ""
    if len(points) > len(trimmed):
        more_note = f'        <p class="chart-note">图表展示前 {len(trimmed)} 项，其余数据保留在表格中。</p>'
    return "\n".join(
        [
            f'        <div class="report-chart report-chart-scatter" role="img" aria-label="{_html(title)} 图表">',
            f'          <div class="chart-title">{_html(title)} 图表</div>',
            f'          <svg class="chart-svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none">',
            f'            <line class="chart-axis" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"></line>',
            f'            <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}"></line>',
            f'            <text class="chart-axis-title" x="{width / 2:.2f}" y="{height - 14}">{_html(x_label)}</text>',
            f'            <text class="chart-axis-title chart-axis-title-y" x="16" y="{height / 2:.2f}">{_html(y_label)}</text>',
            "\n".join(point_nodes),
            "          </svg>",
            more_note,
            "        </div>",
        ]
    )


def _chart(section: dict[str, Any]) -> str:
    chart = section.get("chart")
    if not isinstance(chart, dict):
        return ""
    chart_type = _chart_type(chart)
    if chart_type == "bar":
        return _bar_chart(section, chart)
    if chart_type == "line":
        return _line_chart(section, chart)
    if chart_type == "pie":
        return _pie_chart(section, chart)
    if chart_type == "scatter":
        return _scatter_chart(section, chart)
    if chart_type:
        return f'<p class="note">报表暂只支持 bar、line、pie、scatter 图表，{_html(chart_type)} 已以表格展示。</p>'
    return ""


def _chart_toggle(section: dict[str, Any], chart_html: str, section_index: int) -> str:
    toggle_id = f"chart-toggle-{section_index}"
    chart_input_id = f"{toggle_id}-chart"
    table_input_id = f"{toggle_id}-table"
    return "\n".join(
        [
            f'        <div class="chart-toggle" id="{toggle_id}">',
            '          <div class="chart-toggle-controls" role="tablist" aria-label="图表和表格切换">',
            f'            <input id="{table_input_id}" name="{toggle_id}" type="radio" value="table" checked>',
            f'            <label for="{table_input_id}">表格</label>',
            f'            <input id="{chart_input_id}" name="{toggle_id}" type="radio" value="chart">',
            f'            <label for="{chart_input_id}">图表</label>',
            "          </div>",
            '          <div class="chart-panel chart-panel-table">',
            _table(section),
            "          </div>",
            '          <div class="chart-panel chart-panel-chart">',
            chart_html,
            "          </div>",
            "        </div>",
        ]
    )


def _sections(report: dict[str, Any]) -> str:
    rendered = []
    for idx, section in enumerate(report.get("sections") or []):
        title = _html(section.get("title") or "分析结果")
        description = section.get("description")
        paragraphs = section.get("paragraphs") or []
        chart_html = _chart(section)
        if chart_html:
            body = [_chart_toggle(section, chart_html, idx)]
        else:
            body = [_table(section)]
        if paragraphs:
            body = [f"        <p>{_html(paragraph)}</p>" for paragraph in paragraphs] + body
        if section.get("note"):
            body.append(f'        <p class="note">{_html(section.get("note"))}</p>')
        rendered.append(
            "\n".join(
                [
                    '      <section class="section">',
                    f"        <h2>{title}</h2>",
                    f'        <p class="section-description">{_html(description)}</p>' if description else "",
                    "\n".join(line for line in body if line),
                    "      </section>",
                ]
            )
        )
    if rendered:
        return "\n\n".join(rendered)
    return "\n".join(
        [
            '      <section class="section">',
            "        <h2>分析结果</h2>",
            '        <p class="empty">暂无分析结果。</p>',
            "      </section>",
        ]
    )


def _formula_notes(notes: list[dict[str, Any]]) -> str:
    if not notes:
        return '          <p class="empty">暂无口径说明。</p>'
    blocks = []
    for note in notes[:12]:
        lines = [
            f"<strong>{_html(note.get('metric'))}：{_html(note.get('value'))}</strong>",
            f"算法：{_html(note.get('algorithm'))}",
            f"范围：{_html(note.get('range'))}",
            f"口径：{_html(note.get('definition'))}",
        ]
        limitations = note.get("limitations") or []
        if limitations:
            lines.append(f"限制：{_html('；'.join(_text(item) for item in limitations))}")
        blocks.append(
            '          <div class="formula">'
            + "".join(f'<div class="formula-line">{line}</div>' for line in lines)
            + "</div>"
        )
    return "\n".join(blocks)


def _validate_report_contract(report: dict[str, Any]) -> None:
    if not report.get("kpis") and not report.get("sections"):
        raise ValueError(
            "report_data.json must contain at least one of top-level 'kpis' or 'sections'. "
            "Do not use legacy/free-form fields such as 'overview', 'personal_performance', "
            "'daily_trend', or 'status_distribution' as renderer input."
        )
    kpis = report.get("kpis")
    if kpis is not None:
        if not isinstance(kpis, list):
            raise ValueError("report_data.json field 'kpis' must be a list")
        for idx, item in enumerate(kpis):
            if not isinstance(item, dict) or not item.get("label") or "value" not in item:
                raise ValueError(f"report_data.json kpis[{idx}] must contain 'label' and 'value'")
    sections = report.get("sections")
    if sections is not None:
        if not isinstance(sections, list):
            raise ValueError("report_data.json field 'sections' must be a list")
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                raise ValueError(f"report_data.json sections[{idx}] must be an object")
            rows = section.get("rows")
            if not isinstance(rows, list) or not rows:
                raise ValueError(f"report_data.json sections[{idx}].rows must be a non-empty list")
            columns = section.get("columns")
            if not isinstance(columns, list) or not columns:
                raise ValueError(f"report_data.json sections[{idx}].columns must be a non-empty list")
            for col_idx, column in enumerate(columns):
                if not isinstance(column, dict) or not column.get("key"):
                    raise ValueError(
                        f"report_data.json sections[{idx}].columns[{col_idx}] must contain 'key'"
                    )
            chart = section.get("chart")
            if chart is not None:
                if not isinstance(chart, dict):
                    raise ValueError(f"report_data.json sections[{idx}].chart must be an object")
                chart_type = _chart_type(chart)
                if chart_type not in SUPPORTED_CHART_TYPES:
                    raise ValueError(
                        f"report_data.json sections[{idx}].chart.chartType must be one of "
                        "bar, line, pie, scatter"
                    )
                if chart_type == "pie":
                    if not (chart.get("nameKey") or chart.get("name_key") or chart.get("xKey") or chart.get("x_key")):
                        raise ValueError(f"report_data.json sections[{idx}].chart.nameKey is required for pie")
                    if not (
                        chart.get("valueKey")
                        or chart.get("value_key")
                        or chart.get("yKey")
                        or chart.get("y_key")
                    ):
                        raise ValueError(f"report_data.json sections[{idx}].chart.valueKey is required for pie")
                else:
                    if not chart.get("xKey") and not chart.get("x_key"):
                        raise ValueError(f"report_data.json sections[{idx}].chart.xKey is required")
                    if not chart.get("yKey") and not chart.get("y_key"):
                        raise ValueError(f"report_data.json sections[{idx}].chart.yKey is required")


def _manifest_row_count(manifest: dict[str, Any]) -> int | None:
    row_counts = manifest.get("row_counts")
    if not isinstance(row_counts, dict) or not row_counts:
        return None
    data_count = row_counts.get("data")
    if isinstance(data_count, int) and not isinstance(data_count, bool):
        return data_count
    total = 0
    found = False
    for value in row_counts.values():
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
            found = True
    return total if found else None


def _apply_manifest_defaults(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    if report.get("row_count") in (None, ""):
        row_count = _manifest_row_count(manifest)
        if row_count is not None:
            report["row_count"] = row_count


def render_html(report: dict[str, Any], notes: list[dict[str, Any]]) -> str:
    _validate_report_contract(report)
    references_dir = _skill_dir() / "references" / "report"
    template = (references_dir / "report-template.html").read_text(encoding="utf-8")
    css = (references_dir / "report.css").read_text(encoding="utf-8")
    footer = report.get("footer") or "本报告由 Solvea Kit 基于当前账号授权范围内的工单快照生成，仅供运营分析使用。"
    replacements = {
        "{{REPORT_TITLE}}": _html(report.get("title") or "工单报表"),
        "{{REPORT_SUBTITLE}}": _html(report.get("subtitle") or "基于当前账号授权范围内的工单快照生成。"),
        "{{REPORT_CSS}}": css,
        "{{META_ITEMS}}": _meta_items(report, notes),
        "{{KPI_BLOCKS}}": _kpi_blocks(report),
        "{{SECTIONS}}": _sections(report),
        "{{FORMULA_NOTES}}": _formula_notes(notes),
        "{{FOOTER}}": _html(footer),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def main() -> int:
    parser = argparse.ArgumentParser(description="Render solvea-desk HTML from report_data.json")
    parser.add_argument("--task-id", required=True, help="Shulex Desk task id")
    parser.add_argument("--report-slug", default="", help="ASCII lowercase snake_case report slug")
    parser.add_argument("--report-data", default="", help="Path to report_data.json; defaults to state task dir")
    parser.add_argument("--notes", default="", help="Path to calculation_notes.json; defaults to state task dir")
    parser.add_argument("--output", default="", help="Output HTML path; defaults to output task dir")
    parser.add_argument("--validate-only", action="store_true", help="Validate inputs without writing HTML")
    args = parser.parse_args()

    state_task_dir = STATE_DIR / args.task_id
    output_task_dir = OUTPUTS_DIR / args.task_id
    report_data_path = Path(args.report_data) if args.report_data else state_task_dir / "report_data.json"
    notes_path = Path(args.notes) if args.notes else state_task_dir / "calculation_notes.json"
    manifest_path = state_task_dir / "manifest.json"
    report = _read_json(report_data_path, {})
    notes = _read_json(notes_path, [])
    manifest = _read_json(manifest_path, {})
    if not isinstance(report, dict):
        raise ValueError("report_data.json must contain a JSON object")
    if not isinstance(notes, list):
        raise ValueError("calculation_notes.json must contain a JSON array")
    if not isinstance(manifest, dict):
        manifest = {}
    _apply_manifest_defaults(report, manifest)

    slug = _validate_slug(args.report_slug or report.get("report_slug") or "desk_report")
    _validate_report_contract(report)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "ok": True,
                    "validated": True,
                    "task_id": args.task_id,
                    "report_slug": slug,
                    "report_data": str(report_data_path),
                    "notes": str(notes_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    output_path = Path(args.output) if args.output else output_task_dir / f"{slug}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(report, notes), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "task_id": args.task_id,
                "report_slug": slug,
                "report": str(output_path),
                "report_data": str(report_data_path),
                "notes": str(notes_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
