import { join } from "node:path";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { flag, option } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { asRows, ensureParent, htmlEscape, intOption, outputRoot, readJson, stateRoot, writeHtml, writeJson } from "./common.js";

type JsonObject = Record<string, unknown>;
const taskId = (args: string[]) => option(args, "--task-id") ?? new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
const taskDir = (args: string[]) => join(stateRoot("solvea-desk"), taskId(args));

async function saveDatasource(dir: string, name: string, rows: JsonObject[]) {
  const file = join(dir, name); await ensureParent(file); const workbook = new ExcelJS.Workbook(); const sheet = workbook.addWorksheet("data"); const keys = [...new Set(rows.flatMap(row => Object.keys(row)))]; sheet.addRow(keys); for (const row of rows) sheet.addRow(keys.map(key => row[key] ?? "")); await workbook.xlsx.writeFile(file); return file;
}

async function fetchTickets(client: SolveaClient, args: string[]) {
  const dir = taskDir(args); const pageSize = Math.max(1, Math.min(intOption(args, "--page-size", 100), 500)); const maxPages = intOption(args, "--max-pages", 100); const maxRows = intOption(args, "--max-rows", 10_000); const rows: JsonObject[] = [];
  for (let page = 1; page <= maxPages && rows.length < maxRows; page += 1) {
    const value = await client.rawCall("POST", "/api_v2/tars/api/ticket/list", { viewId: option(args, "--view-id") ?? "1", page, pageSize, sort: option(args, "--sort") ?? "last_update_time", order: option(args, "--order") ?? "DESC", ...(option(args, "--filters-file") ? await readJson<JsonObject>(option(args, "--filters-file")!) : {}) }); const pageRows = asRows(value); rows.push(...pageRows.slice(0, maxRows - rows.length)); if (pageRows.length < pageSize) break;
  }
  const output = await saveDatasource(dir, "datasource.xlsx", rows); await writeJson(join(dir, "metadata.json"), { taskId: taskId(args), rows: rows.length, output }); return { taskId: taskId(args), output, count: rows.length };
}

async function fetchSources(client: SolveaClient, args: string[]) {
  const dir = taskDir(args); const begin = option(args, "--start", true)!, end = option(args, "--end", true)!; const sources: JsonObject = { begin, end, tickets: [] }; const value = await client.rawCall("POST", "/api_v2/tars/api/ticket/list", { startTime: begin, endTime: end, page: 1, pageSize: intOption(args, "--max-rows", 10_000) }); const rows = asRows(value).slice(0, intOption(args, "--max-rows", 10_000)); sources.tickets = rows; const output = await saveDatasource(dir, "datasource.xlsx", rows); await writeJson(join(dir, "sources.json"), sources); return { taskId: taskId(args), output, count: rows.length };
}

async function tags(client: SolveaClient, action: string, args: string[]) {
  if (action === "list-tags") return client.rawCall("GET", "/api_v2/tars/api/ticket/tag/tree");
  const ticket = option(args, "--ticket-number", true)!;
  if (action === "get-ticket-tags") return client.rawCall("GET", `/api_v2/tars/api/ticket/${encodeURIComponent(ticket)}/tags`);
  if (action === "search-tags") { const tree = await client.rawCall("GET", "/api_v2/tars/api/ticket/tag/tree"); const needle = option(args, "--name", true)!.toLowerCase(); const flatten = (value: unknown): JsonObject[] => Array.isArray(value) ? value.flatMap(flatten) : value && typeof value === "object" ? [value as JsonObject, ...flatten((value as JsonObject).children ?? (value as JsonObject).nodes ?? [])] : []; return flatten(tree).filter(row => String(row.name ?? row.label ?? "").toLowerCase().includes(needle)); }
  if (action === "batch-get-ticket-tags") { const ids = asRows(await readJson(option(args, "--ticket-ids-file", true)!)); const result = []; for (const row of ids) result.push({ ...row, tags: await client.rawCall("GET", `/api_v2/tars/api/ticket/${encodeURIComponent(String(row.ticketNumber ?? row.ticketId ?? row.id))}/tags`) }); return result; }
  if (action === "bind-tags" || action === "replace-tags") { if (!flag(args, "--confirm")) throw new Error(`${action} requires --confirm`); const tagsFile = option(args, "--tags-file", true)!; return client.rawCall("POST", `/api_v2/tars/api/ticket/${encodeURIComponent(ticket)}/tags`, { tags: await readJson(tagsFile) }); }
  throw new Error(`unknown tag action: ${action}`);
}

async function renderReport(args: string[]) {
  const dir = taskDir(args), dataFile = option(args, "--report-data") ?? join(dir, "report_data.json"), notesFile = option(args, "--notes") ?? join(dir, "calculation_notes.json"); const data = await readJson<JsonObject>(dataFile); if (flag(args, "--validate-only")) return { valid: true, dataFile }; const output = option(args, "--output") ?? join(outputRoot("solvea-desk"), taskId(args), `${option(args, "--report-slug") ?? "report"}.html`); const body = `<pre>${htmlEscape(JSON.stringify({ data, notes: await readJson(notesFile).catch(() => ({})) }, null, 2))}</pre>`; await writeHtml(output, option(args, "--report-slug") ?? "Solvea Desk report", body); return { output, valid: true };
}

export async function runDesk(session: Session, action: string | undefined, args: string[]) {
  if (!action) throw new Error("solvea-desk action is required"); const client = new SolveaClient(session);
  if (action === "fetch-tickets") return fetchTickets(client, args);
  if (action === "fetch-sources") return fetchSources(client, args);
  if (action === "render-report") return renderReport(args);
  if (action === "tags") return tags(client, option(args, "--operation") ?? args.find(value => ["list-tags", "get-ticket-tags", "batch-get-ticket-tags", "search-tags", "bind-tags", "replace-tags"].includes(value)) ?? "list-tags", args);
  if (["list-tags", "get-ticket-tags", "batch-get-ticket-tags", "search-tags", "bind-tags", "replace-tags"].includes(action)) return tags(client, action, args);
  throw new Error(`unknown solvea-desk action: ${action}`);
}
