import { join } from "node:path";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { flag, option } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { asRows, ensureDir, htmlEscape, intOption, outputRoot, readJson, stateRoot, writeHtml, writeJson } from "./common.js";

type JsonObject = Record<string, unknown>;
const KNOWN_INTENTS = ["Product Recommendation", "Discount Inquiry", "Price Inquiry", "Stock Availability", "Payment Issues", "Request Invoice", "Modify Order", "Check Order Status", "Cancel Order", "Track Shipment", "Shipping Exception", "Missing Items", "Wrong Items Received", "Damaged Package", "Product Usage", "Return and exchange"];

async function loadRows(file: string): Promise<JsonObject[]> {
  if (file.endsWith(".json")) { const value = await readJson<unknown>(file); return asRows(value); }
  const workbook = new ExcelJS.Workbook(); await workbook.xlsx.readFile(file); const sheet = workbook.worksheets[0]; if (!sheet) throw new Error("input workbook has no worksheet"); const headers = (sheet.getRow(1).values as unknown[]).slice(1).map(v => String(v ?? "")); const rows: JsonObject[] = []; sheet.eachRow((row, number) => { if (number === 1) return; const values = (row.values as unknown[]).slice(1), item: JsonObject = {}; headers.forEach((header, index) => { if (header) item[header] = values[index] ?? ""; }); rows.push(item); }); return rows;
}

async function writeRows(file: string, rows: JsonObject[]) {
  if (file.endsWith(".json")) { await writeJson(file, rows); return; }
  const workbook = new ExcelJS.Workbook(); const sheet = workbook.addWorksheet("results"); const keys = [...new Set(rows.flatMap(row => Object.keys(row)))]; sheet.addRow(keys); rows.forEach(row => sheet.addRow(keys.map(key => row[key] ?? ""))); await ensureDir(join(file, "..")); await workbook.xlsx.writeFile(file);
}

function classify(text: string) { const lower = text.toLowerCase(); return KNOWN_INTENTS.find(intent => lower.includes(intent.toLowerCase())) ?? (lower.includes("price") ? "Price Inquiry" : lower.includes("order") ? "Order Issues" : "New Intent"); }

async function classifyCases(args: string[], domain: "delivery" | "poc") {
  const input = option(args, "--xlsx") ?? option(args, "--input"); const noExcel = flag(args, "--no-excel"); if (!input && !noExcel) throw new Error("--xlsx/--input or --no-excel is required"); const rows = input ? await loadRows(input) : [];
  const grouped = new Map<string, JsonObject[]>(); for (const row of rows) { const text = Object.values(row).join(" "); const intent = classify(text); grouped.set(intent, [...(grouped.get(intent) ?? []), { ...row, intent }]); }
  const intents = [...grouped.entries()].map(([name, items]) => ({ name, definition: `Customer requests and issues related to ${name}.`, count: items.length, pct: rows.length ? items.length / rows.length : 0, samples: items.slice(0, 5), is_new: name === "New Intent" })); const runId = option(args, "--run-id") ?? Date.now().toString(); const result = { meta: { run_id: runId, total: rows.length, classified: rows.length, mode: noExcel ? "no-excel" : "structured", domain }, intents, new_intents: intents.filter(item => item.is_new) };
  const out = option(args, "--results") ?? join(outputRoot(domain), `results_${runId}.json`); await writeJson(out, result); await writeJson(join(stateRoot(domain), "progress.json"), { status: "classified", run_id: runId, results_path: out, updated_at: new Date().toISOString() }); return { ...result.meta, resultsPath: out };
}

async function plan(domain: "delivery" | "poc", args: string[]) {
  const file = join(stateRoot(domain), "progress.json"); let current: JsonObject = {}; try { current = await readJson<JsonObject>(file); } catch { /* initialize below */ }
  if (flag(args, "--init") || !Object.keys(current).length) current = { status: "initialized", tenant: option(args, "--tenant"), brandName: option(args, "--brand-name"), brandWebsite: option(args, "--brand-website"), updatedAt: new Date().toISOString() };
  const status = option(args, "--status"); if (status) current.status = status; const assignments: string[] = []; for (let index = 0; index < args.length; index += 1) { if (args[index] === "--set" && args[index + 1]) assignments.push(args[++index]); else if (args[index].startsWith("--set=")) assignments.push(args[index].slice(6)); } for (const assignment of assignments) { const [key, ...value] = assignment.split("="); if (key) current[key] = value.join("="); }
  await writeJson(file, current); return current;
}

async function runBatch(client: SolveaClient, args: string[], domain: "delivery" | "poc") {
  const input = option(args, "--input") ?? option(args, "--test-file", true)!; const rows = await loadRows(input); const output = option(args, "--output") ?? join(outputRoot(domain), `test_results_${Date.now()}.json`); const workers = Math.max(1, Math.min(intOption(args, "--workers", 4), 16)); const results: JsonObject[] = []; let cursor = 0;
  async function worker() { while (true) { const index = cursor++; if (index >= rows.length) return; const row = rows[index]; const message = String(row.message ?? row.question ?? row.input ?? Object.values(row).join(" ")); try { const response = await client.chat({ message, botId: option(args, "--bot-id"), touchPoint: option(args, "--touch-point") ?? "LIVE_CHAT", chatId: row.chatId }); results[index] = { ...row, index, ok: true, message, response }; } catch (error) { results[index] = { ...row, index, ok: false, message, error: error instanceof Error ? error.message : String(error) }; } } }
  await Promise.all(Array.from({ length: workers }, () => worker())); await writeJson(output, { meta: { total: rows.length, workers, domain, generatedAt: new Date().toISOString() }, results }); if (flag(args, "--report")) console.log(`completed ${results.filter(row => row.ok).length}/${results.length} cases`); return { output, total: results.length, succeeded: results.filter(row => row.ok).length, failed: results.filter(row => !row.ok).length };
}

async function createAgents(client: SolveaClient, args: string[], domain: "delivery" | "poc") {
  const state = await readJson<JsonObject>(join(stateRoot(domain), "progress.json")).catch(() => ({} as JsonObject)); const resultsPath = option(args, "--results") ?? (typeof state.results_path === "string" ? state.results_path : undefined); if (!resultsPath) throw new Error("classification results are required"); const result = await readJson<JsonObject>(resultsPath); const intents = Array.isArray(result.intents) ? result.intents as JsonObject[] : []; if (flag(args, "--dry-run")) return { dryRun: true, intents: intents.map(item => item.name) }; const created = []; for (const intent of intents.filter(item => Number(item.count ?? 0) > 0)) created.push(await client.createAgent({ name: `${String(intent.name)} ${domain === "poc" ? "POC" : "Delivery"}`, type: "CHAT_FLOW", meta: { intent: intent.name } })); return { created, count: created.length };
}

async function renderReport(args: string[], domain: "delivery" | "poc") {
  const progress = await readJson<JsonObject>(join(stateRoot(domain), "progress.json")).catch(() => ({} as JsonObject)); const resultsFile = option(args, "--results") ?? option(args, "--input") ?? (typeof progress.results_path === "string" ? progress.results_path : undefined); if (!resultsFile) throw new Error("--results/--input is required, or run classify first"); const value = await readJson<JsonObject>(resultsFile); const rows = asRows(value.results ?? value.items ?? value); const output = option(args, "--html") ?? option(args, "--output") ?? join(outputRoot(domain), `${domain}_report.html`); const body = `<p>Total: ${rows.length}</p>${rows.map((row, index) => `<div class="card"><h2>${index + 1}. ${htmlEscape(row.intent ?? row.question ?? row.message ?? "Case")}</h2><pre>${htmlEscape(JSON.stringify(row, null, 2))}</pre></div>`).join("")}`; await writeHtml(output, option(args, "--title") ?? `${domain} report`, body); const md = option(args, "--md"); if (md) await import("node:fs/promises").then(fs => fs.writeFile(md, `# ${domain} report\n\nTotal: ${rows.length}\n`, "utf8")); return { output, count: rows.length };
}

async function genExcel(args: string[], domain: "delivery" | "poc") { const progress = await readJson<JsonObject>(join(stateRoot(domain), "progress.json")).catch(() => ({} as JsonObject)); const input = option(args, "--results") ?? option(args, "--items") ?? (typeof progress.results_path === "string" ? progress.results_path : undefined); if (!input) throw new Error("--results or --items is required, or run classify first"); const value = await readJson<unknown>(input); const rows = asRows(value); const output = option(args, "--output") ?? join(outputRoot(domain), `${domain}_results.xlsx`); await writeRows(output, rows); return { output, count: rows.length }; }

async function sampleHistory(client: SolveaClient, args: string[]) { const output = option(args, "--output", true)!; const result = await client.listTranscripts({ pageIndex: 1, pageSize: intOption(args, "--max-conversations", 50), debug: false }); const rows = asRows(result).slice(0, intOption(args, "--total", 100)); await writeJson(output, rows.map((row, index) => ({ id: row.chatId ?? row.id ?? String(index), message: row.message ?? row.lastMessage ?? "", metadata: flag(args, "--with-metadata") ? row : undefined }))); return { output, count: rows.length }; }

async function inspectChatflow(client: SolveaClient, args: string[]) { const ids = args.flatMap((value, index) => value === "--agent-id" ? [args[index + 1]] : []).filter(Boolean); const results = []; for (const id of ids) results.push({ agentId: id, graph: await client.getChatflowGraph(id!) }); return results; }

export async function runDelivery(session: Session | undefined, action: string | undefined, args: string[]) { return runDomain(session, "delivery", action, args); }
export async function runPoc(session: Session | undefined, action: string | undefined, args: string[]) { return runDomain(session, "poc", action, args); }

async function runDomain(session: Session | undefined, domain: "delivery" | "poc", action: string | undefined, args: string[]) {
  if (!action) throw new Error(`${domain} action is required`);
  if (action === "classify") return classifyCases(args, domain);
  if (action === "plan") return plan(domain, args);
  if (action === "report" || action === "render" || action === "render-report" || action === "manual") return renderReport(args, domain);
  if (action === "excel" || action === "gen-excel") return genExcel(args, domain);
  if (!session) throw new Error(`${domain} ${action} requires an authenticated tenant`);
  const client = new SolveaClient(session);
  if (action === "batch-test" || action === "test") return runBatch(client, args, domain);
  if (action === "create-agents") return createAgents(client, args, domain);
  if (action === "sample-history") return sampleHistory(client, args);
  if (action === "inspect-chatflow") return inspectChatflow(client, args);
  if (action === "render-summary") return plan(domain, args);
  throw new Error(`unknown ${domain} action: ${action}`);
}
