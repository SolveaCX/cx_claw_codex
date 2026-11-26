import { join } from "node:path";
import { mkdir } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { option } from "../args.js";
import { stateRoot, outputRoot, readJson, writeJson } from "./common.js";
import { ReadClient, validateParameters, pathSegment } from "../commands/read-client.js";
import { ticketCommands } from "../commands/ticket.js";
import { renderTicketReport } from "./ticket-report.js";

type Row = Record<string, unknown>;
function integer(args: string[], name: string, fallback: number, max = Number.MAX_SAFE_INTEGER) {
  const value = Number(option(args, name) ?? fallback);
  if (!Number.isSafeInteger(value) || value < 1 || value > max)
    throw Error(`${name} must be between 1 and ${max}`);
  return value;
}
export function ticketTimeWindow(start: string, end: string, timezone = "Asia/Shanghai") {
  if (timezone !== "Asia/Shanghai")
    throw Error("ticket-analytics only supports timezone Asia/Shanghai");
  const normalize = (input: string) => {
    if (!/^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?$/.test(input))
      throw Error("invalid calendar date");
    const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(input);
    const zoned = /Z$|[+-]\d{2}:\d{2}$/.test(input);
    const calendar = input.slice(0, 10);
    if (new Date(calendar + "T00:00:00Z").toISOString().slice(0, 10) !== calendar)
      throw Error("invalid calendar date");
    const value = new Date(
      (dateOnly ? input + "T00:00:00" : input.replace(" ", "T")) + (zoned ? "" : "+08:00"),
    );
    if (!Number.isFinite(value.getTime())) throw Error("invalid calendar date");
    const local = new Date(value.getTime() + 8 * 3600_000).toISOString();
    if (local.slice(11, 23) !== "00:00:00.000")
      throw Error("only full calendar days are supported; start and end must be midnight");
    if (!zoned && local.slice(0, 10) !== input.slice(0, 10)) throw Error("invalid calendar date");
    return local.slice(0, 10);
  };
  const begin = normalize(start),
    finish = normalize(end);
  if (finish < begin) throw Error("end must not precede start");
  if ((Date.parse(finish) - Date.parse(begin)) / 86400000 >= 60)
    throw Error("historical snapshots support at most 60 calendar days; split the range");
  return { start: begin + "T00:00:00", end: finish + "T23:59:59", timezone };
}
export function ticketDatasets(data: unknown): Record<string, Row[]> {
  const rows = (value: unknown): Row[] =>
    Array.isArray(value)
      ? value.map((item) =>
          item && typeof item === "object" && !Array.isArray(item)
            ? (item as Row)
            : { value: item },
        )
      : [];
  if (Array.isArray(data)) return { data: rows(data) };
  if (!data || typeof data !== "object") throw Error("unexpected historical report response");
  const source = data as Row;
  for (const key of ["records", "list", "items", "rows"])
    if (Array.isArray(source[key])) return { data: rows(source[key]) };
  const datasets = Object.fromEntries(
    Object.entries(source)
      .filter(([, value]) => Array.isArray(value))
      .map(([key, value]) => [key, rows(value)]),
  );
  return Object.keys(datasets).length ? datasets : { data: [] };
}
async function snapshot(session: Session, action: string, args: string[]) {
  const historical = action === "fetch-sources";
  const taskId =
    option(args, "--task-id") ??
    new Date().toISOString().replace(/[^0-9]/g, "") + "_" + randomUUID().slice(0, 8);
  pathSegment(taskId);
  const dir = join(stateRoot("ticket-analytics"), taskId);
  const maxPages = integer(args, "--max-pages", historical ? 200 : 100, 1000),
    maxRows = integer(args, "--max-rows", historical ? 200000 : 10000),
    pageSize = integer(args, "--page-size", historical ? 200 : 50, historical ? 200 : 100);
  const window = historical
    ? ticketTimeWindow(
        option(args, "--start", true)!,
        option(args, "--end", true)!,
        option(args, "--timezone"),
      )
    : undefined;
  const rangeType = option(args, "--time-range-type");
  if (rangeType && rangeType !== "created_at")
    throw Error("time-range-type only accepts created_at");
  if (option(args, "--filters-file") && option(args, "--filters-json"))
    throw Error("use either filters-file or filters-json");
  const filters = option(args, "--filters-file")
    ? await readJson<Row>(option(args, "--filters-file")!)
    : JSON.parse(option(args, "--filters-json") ?? "{}");
  if (!filters || typeof filters !== "object" || Array.isArray(filters))
    throw Error("filters must be a JSON object");
  if (historical && Object.keys(filters).length)
    throw Error("historical report does not accept ticket-list filters");
  const client = new ReadClient(session);
  for (const key of ["page", "pageSize", "viewId", "sort", "order"])
    if (Object.hasOwn(filters, key)) throw Error(`${key} must use its dedicated CLI option`);
  if (!historical && option(args, "--order") && !["ASC", "DESC"].includes(option(args, "--order")!))
    throw Error("order must be ASC or DESC");
  const datasets: Record<string, Row[]> = {},
    seen = new Set<string>();
  let count = 0,
    truncated = false,
    pagesFetched = 0;
  for (let page = 1; page <= maxPages; page++) {
    let data: any, more: boolean;
    if (historical) {
      data = await client.request("POST", "/api_v2/tars/api/ticket/report/raw/page", {
        body: {
          startTime: window!.start,
          endTime: window!.end,
          page,
          pageSize,
          ...(rangeType ? { timeRangeType: rangeType } : {}),
        },
      });
      const explicit = data?.hasMore ?? data?.has_more;
      if (typeof explicit === "boolean") more = explicit;
      else if (Number.isInteger(data?.total))
        more = page * (data.pageSize ?? data.page_size ?? pageSize) < data.total;
      else throw Error("historical report lacks pagination metadata; cannot prove completeness");
    } else {
      const input = {
        viewId: 1,
        ...filters,
        ...(option(args, "--view-id") ? { viewId: Number(option(args, "--view-id")) } : {}),
        sort: option(args, "--sort") ?? filters.sort ?? "last_update_time",
        order: option(args, "--order") ?? filters.order ?? "DESC",
        page,
        pageSize,
      };
      data = await ticketCommands.list.run(client, validateParameters(ticketCommands.list, input));
      more = client.pagination!.truncated;
    }
    const pageDatasets = historical ? ticketDatasets(data) : { data: data.list as Row[] };
    const digest = createHash("sha256").update(JSON.stringify(pageDatasets)).digest("hex");
    if (seen.has(digest)) throw Error("pagination repeated a page; cannot prove completeness");
    seen.add(digest);
    let pageCount = 0;
    for (const [key, rows] of Object.entries(pageDatasets)) {
      pageCount += rows.length;
      const kept = rows.slice(0, Math.max(0, maxRows - count));
      (datasets[key] ??= []).push(...kept);
      count += kept.length;
      if (kept.length < rows.length) truncated = true;
    }
    pagesFetched = page;
    if (more && pageCount === 0) throw Error("pagination did not advance");
    if (!more) break;
    if (count >= maxRows || page === maxPages) {
      truncated = true;
      break;
    }
  }
  // 新任务目录独占创建，避免同名任务覆盖之前的快照。
  await mkdir(stateRoot("ticket-analytics"), { recursive: true });
  await mkdir(dir);
  const workbook = new ExcelJS.Workbook(),
    used = new Set<string>();
  for (const [name, rows] of Object.entries(datasets)) {
    const base =
      name
        .replace(/[\\/*?:\[\]]/g, "_")
        .replace(/^'+|'+$/g, "")
        .slice(0, 31) || "data";
    let sheetName = base,
      suffix = 1;
    while (used.has(sheetName.toLowerCase())) sheetName = base.slice(0, 26) + "_" + suffix++;
    used.add(sheetName.toLowerCase());
    const sheet = workbook.addWorksheet(sheetName);
    const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    sheet.addRow(keys);
    for (const row of rows)
      sheet.addRow(
        keys.map((key) =>
          row[key] && typeof row[key] === "object" ? JSON.stringify(row[key]) : (row[key] ?? ""),
        ),
      );
  }
  const output = join(dir, "datasource.xlsx");
  await workbook.xlsx.writeFile(output);
  const manifest = {
    task_id: taskId,
    tenant: { accountId: session.tenant!.accountId, environment: session.tenant!.environment },
    view_id: historical ? undefined : Number(option(args, "--view-id") ?? 1),
    sort: historical ? undefined : (option(args, "--sort") ?? "last_update_time"),
    order: historical ? undefined : (option(args, "--order") ?? "DESC"),
    status: "ready",
    source_type: historical ? "ticket_report_snapshot" : "ticket_list_snapshot",
    data_scope: "current_user",
    snapshot_semantics: historical ? "historical_facts" : "current_state",
    requested_window: window
      ? { start: option(args, "--start"), end: option(args, "--end"), timezone: window.timezone }
      : undefined,
    fetch_window: window,
    time_range_type: historical ? (rangeType ?? "report_activity_date") : undefined,
    filters: historical ? undefined : filters,
    source: client.source,
    pagesFetched,
    row_counts: Object.fromEntries(
      Object.entries(datasets).map(([key, rows]) => [key, rows.length]),
    ),
    truncated,
    generated_at: new Date().toISOString(),
  };
  await writeJson(join(dir, "manifest.json"), manifest);
  await writeJson(join(dir, "metadata.json"), manifest);
  await writeJson(join(stateRoot("ticket-analytics"), "latest_task.json"), {
    ...manifest,
    state_task_dir: dir,
    output_task_dir: join(outputRoot("ticket-analytics"), taskId),
  });
  return { taskId, output, count, truncated, pagesFetched, manifest: join(dir, "manifest.json") };
}
export async function runTicketAnalytics(
  session: Session | undefined,
  action: string | undefined,
  args: string[],
) {
  const options: Record<string, string[]> = {
    "fetch-tickets": [
      "--task-id",
      "--view-id",
      "--filters-json",
      "--filters-file",
      "--page-size",
      "--max-pages",
      "--max-rows",
      "--sort",
      "--order",
    ],
    "fetch-sources": [
      "--task-id",
      "--start",
      "--end",
      "--timezone",
      "--time-range-type",
      "--page-size",
      "--max-pages",
      "--max-rows",
    ],
    "render-report": [
      "--task-id",
      "--report-data",
      "--notes",
      "--report-slug",
      "--output",
      "--validate-only",
    ],
  };
  const allowed = options[action ?? ""] ?? [],
    seen = new Set<string>();
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (!allowed.includes(key) || seen.has(key)) throw Error(`unknown or duplicate option: ${key}`);
    seen.add(key);
    if (key !== "--validate-only" && (!args[++i] || args[i].startsWith("--")))
      throw Error(`missing value: ${key}`);
  }
  if (action === "render-report") return renderTicketReport(args);
  if (action !== "fetch-tickets" && action !== "fetch-sources")
    throw Error("ticket-analytics action must be fetch-tickets, fetch-sources, or render-report");
  if (!session) throw Error("select a tenant before fetching tickets");
  return snapshot(session, action, args);
}

export const ticketAnalyticsHelp = `cxclawctl ticket-analytics <action> [options]
fetch-tickets: --view-id --filters-json|--filters-file --page-size --max-pages --max-rows --sort --order --task-id
fetch-sources: --start YYYY-MM-DD --end YYYY-MM-DD [--timezone Asia/Shanghai] [--time-range-type created_at] --page-size --max-pages --max-rows --task-id
render-report: --task-id ID [--report-data FILE] [--notes FILE] [--report-slug SLUG] [--output FILE] [--validate-only]
`;
