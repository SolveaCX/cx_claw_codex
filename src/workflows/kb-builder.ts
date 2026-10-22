import { join } from "node:path";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { flag, option } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { asRows, ensureDir, intOption, outputRoot, readJson, stateRoot, writeJson } from "./common.js";

type JsonObject = Record<string, unknown>;
const clean = (value: unknown) => String(value ?? "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
const absolute = (href: string, base: string) => { try { return new URL(href, base).toString(); } catch { return undefined; } };

async function crawl(args: string[]) {
  const url = option(args, "--url", true)!;
  const maxPages = intOption(args, "--max-pages", 50), maxDepth = intOption(args, "--max-depth", 2), timeout = intOption(args, "--timeout", 20) * 1000;
  const origin = new URL(url).origin, queue: Array<{ url: string; depth: number }> = [{ url, depth: 0 }], seen = new Set<string>(), pages: JsonObject[] = [];
  while (queue.length && pages.length < maxPages) {
    const current = queue.shift()!; if (seen.has(current.url) || current.depth > maxDepth) continue; seen.add(current.url);
    try {
      const response = await fetch(current.url, { signal: AbortSignal.timeout(timeout), headers: { accept: "text/html,application/xhtml+xml" } });
      if (!response.ok) continue;
      const html = await response.text(); const title = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? "";
      const text = clean(html); pages.push({ url: current.url, depth: current.depth, title: clean(title), text: text.slice(0, 50_000), status: response.status });
      if (current.depth < maxDepth) for (const match of html.matchAll(/href\s*=\s*["']([^"']+)["']/gi)) {
        const next = absolute(match[1], current.url); if (next && next.startsWith(origin) && !seen.has(next)) queue.push({ url: next, depth: current.depth + 1 });
      }
    } catch (error) { pages.push({ url: current.url, depth: current.depth, error: error instanceof Error ? error.message : String(error) }); }
  }
  const result = { url, mode: option(args, "--mode") ?? "auto", pages, fetchedAt: new Date().toISOString(), total: pages.length };
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), "crawl_result.json"); await writeJson(output, result);
  return { ...result, output };
}

async function directoryPlan(args: string[]) {
  const source = await readJson<JsonObject>(option(args, "--crawl-result", true)!); const rows = asRows(source.pages ?? source);
  const groups = new Map<string, JsonObject[]>();
  for (const page of rows) { const title = String(page.title ?? page.url ?? "Untitled"); const key = title.split(/[:|/\\-]/)[0].trim() || "General"; groups.set(key, [...(groups.get(key) ?? []), page]); }
  const tree = [...groups.entries()].map(([name, pages]) => ({ name, children: pages.slice(0, 100).map(page => ({ name: String(page.title ?? page.url), sourceUrl: page.url })) }));
  const result = { source: option(args, "--crawl-result"), generatedAt: new Date().toISOString(), tree, confirmed: false };
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), "directory_plan.json"); await writeJson(output, result);
  if (flag(args, "--write-confirmed-tree")) await writeJson(join(stateRoot("kb-builder"), "confirmed_tree.json"), { ...result, confirmed: true });
  return { output, directories: tree.length, pages: rows.length, tree };
}

async function createDirectories(client: SolveaClient, args: string[]) {
  const file = option(args, "--tree-file") ?? join(stateRoot("kb-builder"), "confirmed_tree.json"); const value = await readJson<JsonObject>(file);
  const tree = Array.isArray(value.tree) ? value.tree as JsonObject[] : Array.isArray(value) ? value as unknown as JsonObject[] : [];
  if (!tree.length) throw new Error("confirmed directory tree is empty");
  const dryRun = flag(args, "--dry-run"), created: unknown[] = [];
  async function visit(nodes: JsonObject[], parentId = 0, depth = 0) {
    if (depth > intOption(args, "--max-depth", 3)) throw new Error("directory tree exceeds max depth");
    for (const node of nodes) {
      const name = String(node.name ?? "").trim(); if (!name) continue;
      const result = dryRun ? { name, parentId, dryRun: true } : await client.createFolder(name, parentId); created.push(result);
      const id = Number((result as JsonObject)?.id ?? (result as JsonObject)?.directoryId ?? 0); const children = Array.isArray(node.children) ? node.children as JsonObject[] : [];
      if (children.length && id) await visit(children, id, depth + 1);
    }
  }
  await visit(tree); return { file, dryRun, created, count: created.length };
}

async function extractWebQa(args: string[]) {
  const input = await readJson<JsonObject>(option(args, "--crawl-result", true)!); const pages = asRows(input.pages ?? input).slice(0, intOption(args, "--max-pages", 80));
  const outputDir = option(args, "--output-dir") ?? join(outputRoot("kb-builder"), "qa_parts"); await ensureDir(outputDir);
  const parts = pages.map((page, index) => ({ question: String(page.title ?? page.url), answer: String(page.text ?? "").slice(0, intOption(args, "--answer-limit", 3500)), sourceUrl: page.url, sourceTitle: page.title, index }));
  const files: string[] = []; for (const [index, part] of parts.entries()) { const file = join(outputDir, `part_${String(index + 1).padStart(4, "0")}.json`); await writeJson(file, { items: [part] }); files.push(file); }
  return { outputDir, files, count: files.length };
}

async function importQa(client: SolveaClient, args: string[]) {
  const qaFile = option(args, "--qa-file"); const fromDir = option(args, "--from-dir");
  if (!qaFile && !fromDir) throw new Error("--qa-file or --from-dir is required");
  const items: unknown[] = [];
  if (qaFile) { const value = await readJson<unknown>(qaFile); items.push(...(Array.isArray(value) ? value : (value as JsonObject).items && Array.isArray((value as JsonObject).items) ? (value as JsonObject).items as unknown[] : [value])); }
  if (fromDir) {
    const { readdir } = await import("node:fs/promises"); for (const file of (await readdir(fromDir)).filter(name => name.endsWith(".json"))) { const value = await readJson<unknown>(join(fromDir, file)); items.push(...(Array.isArray(value) ? value : (value as JsonObject).items && Array.isArray((value as JsonObject).items) ? (value as JsonObject).items as unknown[] : [value])); }
  }
  const plan = { items, count: items.length, createdAt: new Date().toISOString() }; const planFile = join(outputRoot("kb-builder"), `qa_import_plan_${Date.now()}.json`); await writeJson(planFile, plan);
  if (flag(args, "--dry-run")) return { dryRun: true, planFile, count: items.length };
  return { planFile, count: items.length, result: await client.uploadQa(items) };
}

async function importSources(client: SolveaClient, args: string[]) {
  const plan = await readJson<JsonObject>(option(args, "--plan-file", true)!); const documents = Array.isArray(plan.documents) ? plan.documents : Array.isArray(plan.items) ? plan.items : [];
  const payload = { documents, taskType: "WEB", published: true, isVisible: true, metadata: { tags: [] }, directoryId: String(plan.directoryId ?? "") };
  if (!flag(args, "--execute")) return { dryRun: true, payload };
  return client.rawCall("POST", `${client.qamPath}/project/${await client.projectId()}/documents`, payload);
}

async function importTemplates(client: SolveaClient, args: string[]) {
  const source = option(args, "--plan-file") ?? option(args, "--xlsx"); if (!source) throw new Error("--xlsx or --plan-file is required");
  const rows: JsonObject[] = [];
  if (source.endsWith(".json")) rows.push(...asRows(await readJson(source)));
  else { const workbook = new ExcelJS.Workbook(); await workbook.xlsx.readFile(source); const sheet = option(args, "--sheet") ? workbook.getWorksheet(option(args, "--sheet")!) : workbook.worksheets[0]; if (!sheet) throw new Error("workbook has no worksheet"); const headers = (sheet.getRow(1).values as unknown[]).slice(1).map(v => String(v ?? "")); sheet.eachRow((row, number) => { if (number === 1) return; const values = (row.values as unknown[]).slice(1); const item: JsonObject = {}; headers.forEach((header, index) => { if (header) item[header] = values[index] ?? ""; }); rows.push(item); }); }
  const items = rows.map(row => ({ name: String(row.name ?? row.Name ?? "").trim(), content: String(row.content ?? row.Content ?? row.template ?? ""), status: row.status ?? row.Status ?? "ENABLED", scene: row.scene ?? row.Scene })).filter(item => item.name && item.content);
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), `template_import_plan_${Date.now()}.json`); await writeJson(output, { items, count: items.length });
  if (flag(args, "--dry-run")) return { dryRun: true, output, count: items.length };
  const results = []; for (const item of items) results.push(await client.createTemplate(item)); return { output, count: results.length, results };
}

async function exportKnowledge(client: SolveaClient, args: string[]) {
  const directories = asRows(await client.listDirectories()); const ids = option(args, "--directory-id") ? [Number(option(args, "--directory-id"))] : directories.map(row => Number(row.id ?? row.directoryId)).filter(Number.isFinite);
  const rows: JsonObject[] = []; for (const id of ids) { const value = await client.listKnowledge({ directoryId: id, keyword: option(args, "--keyword") ?? "", type: option(args, "--type") ?? "ALL", pageSize: intOption(args, "--page-size", 1000) }); rows.push(...asRows(value).map(row => ({ ...row, directoryId: id, directoryName: directories.find(dir => Number(dir.id ?? dir.directoryId) === id)?.name ?? "" }))); }
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), `knowledge_${Date.now()}.xlsx`); const workbook = new ExcelJS.Workbook(); const sheet = workbook.addWorksheet("knowledge"); const keys = [...new Set(rows.flatMap(row => Object.keys(row)))]; sheet.addRow(keys); for (const row of rows) sheet.addRow(keys.map(key => row[key] ?? "")); await ensureDir(join(output, "..")); await workbook.xlsx.writeFile(output); return { output, count: rows.length };
}

export async function runKbBuilder(session: Session | undefined, action: string | undefined, args: string[]) {
  if (!action) throw new Error("kb-builder action is required");
  if (action === "crawl") return crawl(args);
  if (action === "directory-plan") return directoryPlan(args);
  if (!session) throw new Error(`${action} requires an authenticated tenant`);
  const client = new SolveaClient(session);
  if (action === "create-directories") return createDirectories(client, args);
  if (action === "extract-web-qa") return extractWebQa(args);
  if (action === "import-qa") return importQa(client, args);
  if (action === "import-source-documents") return importSources(client, args);
  if (action === "import-templates") return importTemplates(client, args);
  if (action === "export-knowledge") return exportKnowledge(client, args);
  if (action === "extract-ticket-qa" || action === "batch-extract-ticket-qa") return extractTicketQa(args);
  throw new Error(`unknown kb-builder action: ${action}`);
}

async function extractTicketQa(args: string[]) {
  const file = option(args, "--xlsx", true)!; const workbook = new ExcelJS.Workbook(); await workbook.xlsx.readFile(file); const sheet = workbook.worksheets[0]; if (!sheet) throw new Error("workbook has no worksheet");
  const headers = (sheet.getRow(1).values as unknown[]).slice(1).map(v => String(v ?? "")); const messageCol = option(args, "--messages-col") ?? headers.find(header => /message|conversation|content|描述/i.test(header)) ?? headers[0]; const titleCol = option(args, "--title-col"); const replyCol = option(args, "--reply-col"); const brand = option(args, "--brand", true)!; const items: JsonObject[] = [];
  sheet.eachRow((row, number) => { if (number === 1) return; const values = (row.values as unknown[]).slice(1), record: JsonObject = {}; headers.forEach((header, index) => { record[header] = values[index] ?? ""; }); const question = `${brand}: ${String(record[titleCol!] ?? "").trim()} ${String(record[messageCol!] ?? "").trim()}`.trim(); const answer = String(record[replyCol!] ?? "").trim(); if (question && question !== `${brand}:`) items.push({ question, answer, sourceRow: number }); });
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), `ticket_qa_${Date.now()}.json`); const result = { brand, count: items.length, items }; await writeJson(output, result); if (flag(args, "--dry-run")) return { dryRun: true, output, count: items.length }; return { output, count: items.length, items };
}
