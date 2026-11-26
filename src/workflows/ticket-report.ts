import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { readFileSync } from "node:fs";
import { flag, option } from "../args.js";
import { stateRoot, outputRoot, ensureParent, htmlEscape, readJson } from "./common.js";
import { pathSegment } from "../commands/read-client.js";

const template = readFileSync(new URL("./assets/ticket-report.html", import.meta.url), "utf8");
const css = readFileSync(new URL("./assets/ticket-report.css", import.meta.url), "utf8");

type Obj = Record<string, any>;
const escape = (value: unknown) =>
  htmlEscape(value && typeof value === "object" ? JSON.stringify(value) : value);
const object = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
function chartKeys(chart: Obj) {
  return {
    type: chart.chartType ?? chart.chart_type ?? chart.type,
    x: chart.nameKey ?? chart.name_key ?? chart.xKey ?? chart.x_key,
    y: chart.valueKey ?? chart.value_key ?? chart.yKey ?? chart.y_key,
  };
}
export function validateTicketReport(report: unknown): asserts report is Obj {
  if (!object(report)) throw Error("report data must be an object");
  if (!report.kpis?.length && !report.sections?.length)
    throw Error("report requires kpis or sections");
  if (
    report.kpis !== undefined &&
    (!Array.isArray(report.kpis) ||
      report.kpis.some((v: unknown) => !object(v) || !v.label || !("value" in v)))
  )
    throw Error("kpis must contain label and value");
  if (report.sections !== undefined && !Array.isArray(report.sections))
    throw Error("sections must be an array");
  for (const section of report.sections ?? []) {
    if (
      !object(section) ||
      !Array.isArray(section.rows) ||
      !section.rows.length ||
      section.rows.some((r: unknown) => !object(r))
    )
      throw Error("section rows must be a non-empty object array");
    if (
      !Array.isArray(section.columns) ||
      !section.columns.length ||
      section.columns.some((c: unknown) => !object(c) || typeof c.key !== "string" || !c.key)
    )
      throw Error("section columns require key");
    if (section.chart !== undefined) {
      if (!object(section.chart)) throw Error("chart must be an object");
      const { type, x, y } = chartKeys(section.chart);
      if (!["bar", "line", "pie", "scatter"].includes(type) || !x || !y)
        throw Error("chart requires supported chartType and axis keys");
    }
  }
}
const number = (v: unknown) =>
  typeof v === "number" && Number.isFinite(v)
    ? v
    : typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v.replace(/,/g, "")))
      ? Number(v.replace(/,/g, ""))
      : undefined;
function chart(section: Obj) {
  const settings = section.chart,
    { type, x, y } = chartKeys(settings);
  const max = settings.maxItems ?? settings.max_items ?? (type === "scatter" ? 80 : 20);
  if (!Number.isInteger(max) || max < 1 || max > 500)
    throw Error("chart maxItems must be between 1 and 500");
  const validRows = section.rows.filter(
    (r: Obj) => number(r[y]) !== undefined && (type !== "scatter" || number(r[x]) !== undefined),
  ) as Obj[];
  const rows = validRows.slice(0, max);
  if (!rows.length) return '<p class="note">图表数值为空，已保留表格数据。</p>';
  const colors = ["#4472c4", "#14a38b", "#ed9a45", "#9873ba", "#df6488", "#68a3b8"];
  let shapes = "";
  if (type === "pie") {
    const allPositive = validRows.filter((r) => number(r[y])! > 0);
    const positive = allPositive.slice(0, max);
    const remainder = allPositive.slice(max).reduce((sum, r) => sum + number(r[y])!, 0);
    if (remainder) positive.push({ [x]: "其他", [y]: remainder });
    const total = allPositive.reduce((sum, r) => sum + number(r[y])!, 0);
    let angle = -Math.PI / 2;
    if (!total) return '<p class="note">没有正数数据，已保留表格。</p>';
    shapes = positive
      .map((row, i) => {
        const value = number(row[y])!,
          next = angle + (value / total) * 2 * Math.PI;
        const title = `${escape(row[x])}: ${escape(value)}`;
        const d = `M 180 130 L ${180 + 100 * Math.cos(angle)} ${130 + 100 * Math.sin(angle)} A 100 100 0 ${next - angle > Math.PI ? 1 : 0} 1 ${180 + 100 * Math.cos(next)} ${130 + 100 * Math.sin(next)} Z`;
        angle = next;
        return (
          (value === total
            ? `<circle cx="180" cy="130" r="100" fill="${colors[i % 6]}"><title>${title}</title></circle>`
            : `<path d="${d}" fill="${colors[i % 6]}"><title>${title}</title></path>`) +
          `<text x="320" y="${30 + i * 20}">${title} (${((value / total) * 100).toFixed(1)}%)</text>`
        );
      })
      .join("");
  } else {
    const values = rows.map((r) => number(r[y])!),
      low = Math.min(0, ...values),
      high = Math.max(0, ...values),
      span = high - low || 1;
    const Y = (v: number) => 220 - ((v - low) / span) * 190;
    const xs = rows.map((r, i) => (type === "scatter" ? number(r[x])! : i)),
      minX = Math.min(...xs),
      xSpan = Math.max(...xs) - minX || 1;
    const X = (v: number) => 60 + ((v - minX) / xSpan) * 600;
    shapes = `<line class="chart-axis" x1="50" y1="${Y(0)}" x2="690" y2="${Y(0)}"/><line class="chart-axis" x1="50" y1="20" x2="50" y2="220"/><text x="5" y="30">${escape(high)}</text><text x="5" y="220">${escape(low)}</text>`;
    const xLabel =
      settings.xLabel ??
      settings.x_label ??
      section.columns.find((c: Obj) => c.key === x)?.label ??
      x;
    const yLabel =
      settings.yLabel ??
      settings.y_label ??
      section.columns.find((c: Obj) => c.key === y)?.label ??
      y;
    shapes += `<text x="360" y="268" text-anchor="middle">${escape(xLabel)}</text><text x="55" y="15">${escape(yLabel)}</text>`;
    if (type === "scatter")
      shapes += `<text x="60" y="242">${escape(minX)}</text><text x="660" y="242" text-anchor="end">${escape(Math.max(...xs))}</text>`;
    if (type === "line")
      shapes += `<polyline class="chart-line" fill="none" stroke="#4472c4" points="${values.map((v, i) => `${X(xs[i])},${Y(v)}`).join(" ")}"/>`;
    shapes += rows
      .map((row, i) => {
        const v = values[i],
          title = `${escape(row[x])}: ${escape(v)}`,
          label = `<title>${title}</title>`;
        if (type === "bar") {
          const width = 600 / rows.length;
          return `<rect fill="#4472c4" x="${55 + i * width}" y="${Math.min(Y(v), Y(0))}" width="${width * 0.7}" height="${Math.abs(Y(v) - Y(0))}">${label}</rect><text x="${55 + i * width}" y="245">${escape(row[x])}</text>`;
        }
        return (
          `<circle fill="#4472c4" cx="${X(xs[i])}" cy="${Y(v)}" r="4">${label}</circle>` +
          (type === "line"
            ? `<text x="${X(xs[i])}" y="245" text-anchor="middle">${escape(row[x])}</text>`
            : "")
        );
      })
      .join("");
  }
  return `<div class="report-chart report-chart-${type}" role="img" aria-label="${escape(section.title)}"><div class="chart-title">${escape(settings.title ?? section.title)}</div><svg class="chart-svg" viewBox="0 0 720 ${type === "pie" ? Math.max(280, (rows.length + 1) * 20 + 40) : 270}" xmlns="http://www.w3.org/2000/svg">${shapes}</svg>${section.rows.length > rows.length ? `<p class="chart-note">图表展示 ${rows.length} 项有效数据，完整数据见表格。</p>` : ""}</div>`;
}
export function ticketReportHtml(report: unknown, notes: unknown[] = []) {
  validateTicketReport(report);
  if (!Array.isArray(notes) || notes.some((n) => !object(n)))
    throw Error("notes must be an object array");
  const table = (s: Obj) =>
    `<div class="table-wrap"><table><thead><tr>${s.columns.map((c: Obj) => `<th>${escape(c.label ?? c.key)}</th>`).join("")}</tr></thead><tbody>${s.rows.map((r: Obj) => `<tr>${s.columns.map((c: Obj) => `<td${c.numeric ? ' class="num"' : ""}>${escape(r[c.key])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const sections = (report.sections ?? [])
    .map((s: Obj, i: number) => {
      let body = table(s);
      if (s.chart)
        body = `<div class="chart-toggle"><div class="chart-toggle-controls" role="group" aria-label="图表和表格切换"><input id="table-${i}" name="view-${i}" type="radio" value="table" checked><label for="table-${i}">表格</label><input id="chart-${i}" name="view-${i}" type="radio" value="chart"><label for="chart-${i}">图表</label></div><div class="chart-panel chart-panel-table">${body}</div><div class="chart-panel chart-panel-chart">${chart(s)}</div></div>`;
      return `<section class="section"><h2>${escape(s.title ?? "分析结果")}</h2>${s.description ? `<p>${escape(s.description)}</p>` : ""}${(s.paragraphs ?? []).map((p: unknown) => `<p>${escape(p)}</p>`).join("")}${body}${s.note ? `<p class="note">${escape(s.note)}</p>` : ""}</section>`;
    })
    .join("\n");
  const meta = {
    范围: report.range ?? report.time_range ?? (notes[0] as Obj | undefined)?.range ?? "见指标口径",
    数据行数: report.row_count ?? "不适用（聚合统计）",
    完整性: report.truncated ? "已截断，请按样本范围解读" : "按数据来源口径",
    生成时间: report.generated_at ?? new Date().toISOString(),
  };
  const replacements: Record<string, string> = {
    REPORT_TITLE: escape(report.title ?? "客服工单分析"),
    REPORT_SUBTITLE: escape(report.subtitle ?? "基于当前账号授权范围内的数据生成。"),
    REPORT_CSS: css,
    META_ITEMS: Object.entries(meta)
      .map(
        ([k, v]) =>
          `<div class="meta-item"><span>${escape(k)}</span><strong>${escape(v)}</strong></div>`,
      )
      .join(""),
    KPI_BLOCKS: (report.kpis ?? [])
      .map(
        (k: Obj) =>
          `<div class="kpi"><div class="kpi-label">${escape(k.label)}</div><div class="kpi-value">${escape(k.value)}</div><div class="kpi-note">${escape(k.basis)}</div></div>`,
      )
      .join(""),
    SECTIONS: sections,
    FORMULA_NOTES: notes
      .map((n) => {
        const v = n as Obj;
        return `<div class="formula"><strong>${escape(v.metric)}：${escape(v.value)}</strong>${["algorithm", "range", "definition", "limitations"].map((key, i) => `<div class="formula-line">${["算法", "范围", "口径", "限制"][i]}：${escape(Array.isArray(v[key]) ? v[key].join("；") : v[key])}</div>`).join("")}</div>`;
      })
      .join(""),
    FOOTER: escape(report.footer ?? "本报告基于当前账号授权范围内的数据生成，仅供运营分析使用。"),
  };
  return template.replace(/\{\{([A-Z_]+)\}\}/g, (match, key) => replacements[key] ?? match);
}
async function optionalJson(path: string, fallback: unknown) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return fallback;
    throw error;
  }
}
export async function renderTicketReport(args: string[]) {
  const taskId = option(args, "--task-id", true)!;
  pathSegment(taskId);
  const dir = join(stateRoot("ticket-analytics"), taskId);
  const reportFile = option(args, "--report-data") ?? join(dir, "report_data.json"),
    notesFile = option(args, "--notes") ?? join(dir, "calculation_notes.json");
  const report = await readJson<Obj>(reportFile),
    notes = await optionalJson(notesFile, []),
    manifest = await optionalJson(join(dir, "manifest.json"), {});
  validateTicketReport(report);
  if (report.row_count == null || report.row_count === "") {
    const counts = object(manifest?.row_counts) ? manifest.row_counts : undefined;
    if (counts) {
      const values = Object.values(counts).filter((v): v is number => Number.isInteger(v));
      if (values.length)
        report.row_count = Number.isInteger(counts.data)
          ? counts.data
          : values.reduce((a, b) => a + b, 0);
    }
  }
  // 截断事实来自取数清单，报告输入不能把截断快照描述为完整。
  if (manifest?.truncated) report.truncated = true;
  const slug = option(args, "--report-slug") ?? report.report_slug ?? "ticket_report";
  if (typeof slug !== "string" || !/^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/.test(slug))
    throw Error("report-slug must be ASCII lowercase snake_case");
  const html = ticketReportHtml(report, notes);
  if (flag(args, "--validate-only"))
    return { ok: true, validated: true, task_id: taskId, report_slug: slug };
  const output =
    option(args, "--output") ?? join(outputRoot("ticket-analytics"), taskId, `${slug}.html`);
  await ensureParent(output);
  await writeFile(output, html, "utf8");
  return {
    ok: true,
    task_id: taskId,
    report_slug: slug,
    report: output,
    report_data: reportFile,
    notes: notesFile,
  };
}
