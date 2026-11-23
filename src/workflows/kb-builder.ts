import { join } from "node:path";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { flag, option, options } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import {
  asRows,
  ensureDir,
  intOption,
  outputRoot,
  readJson,
  stateRoot,
  writeJson,
} from "./common.js";

type JsonObject = Record<string, unknown>;
const templateHeaderAliases: Record<string, string[]> = {
  name: [
    "name",
    "title",
    "topic",
    "template",
    "template_name",
    "template name",
    "template title",
    "模板名称",
    "模板名",
    "模版名称",
    "模版名",
    "名称",
    "标题",
    "主题",
  ],
  content: [
    "content",
    "message",
    "body",
    "reply",
    "answer",
    "response",
    "template_content",
    "template content",
    "reply text",
    "模板内容",
    "模板回复",
    "模版内容",
    "模版回复",
    "回复内容",
    "回复话术",
    "话术",
    "答案",
    "内容",
  ],
  status: ["status", "state", "状态", "发布状态"],
  scene: ["scene", "usage", "scenario", "场景", "适用场景"],
};
const templateLanguages = new Set([
  "AUTO",
  "ENGLISH",
  "CHINESE",
  "JAPANESE",
  "FRENCH",
  "GERMAN",
  "SPANISH",
  "ARABIC",
  "RUSSIAN",
  "PORTUGUESE",
  "ITALIAN",
  "KOREAN",
  "DUTCH",
  "INDONESIAN",
  "TURKISH",
  "ROMANIAN",
  "POLISH",
  "PHILIPPINES",
]);
const normalizedTemplateHeader = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("-", "_");
const canonicalTemplateHeader = (value: unknown) => {
  const raw = String(value ?? "").trim();
  const normalized = normalizedTemplateHeader(raw);
  for (const [canonical, aliases] of Object.entries(templateHeaderAliases))
    if (aliases.some((alias) => normalizedTemplateHeader(alias) === normalized)) return canonical;
  return templateLanguages.has(raw.toUpperCase()) ? raw.toUpperCase() : normalized;
};
const clean = (value: unknown) =>
  String(value ?? "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
const absolute = (href: string, base: string) => {
  try {
    return new URL(href, base).toString();
  } catch {
    return undefined;
  }
};

async function crawl(args: string[]) {
  const url = option(args, "--url", true)!;
  const maxPages = intOption(args, "--max-pages", 50),
    maxDepth = intOption(args, "--max-depth", 2),
    timeout = intOption(args, "--timeout", 20) * 1000;
  const origin = new URL(url).origin,
    queue: Array<{ url: string; depth: number }> = [{ url, depth: 0 }],
    seen = new Set<string>(),
    pages: JsonObject[] = [];
  while (queue.length && pages.length < maxPages) {
    const current = queue.shift()!;
    if (seen.has(current.url) || current.depth > maxDepth) continue;
    seen.add(current.url);
    try {
      const response = await fetch(current.url, {
        signal: AbortSignal.timeout(timeout),
        headers: { accept: "text/html,application/xhtml+xml" },
      });
      if (!response.ok) continue;
      const html = await response.text();
      const title = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? "";
      const text = clean(html);
      pages.push({
        url: current.url,
        depth: current.depth,
        title: clean(title),
        text: text.slice(0, 50_000),
        status: response.status,
      });
      if (current.depth < maxDepth)
        for (const match of html.matchAll(/href\s*=\s*["']([^"']+)["']/gi)) {
          const next = absolute(match[1], current.url);
          if (next && next.startsWith(origin) && !seen.has(next))
            queue.push({ url: next, depth: current.depth + 1 });
        }
    } catch (error) {
      pages.push({
        url: current.url,
        depth: current.depth,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  const result = {
    url,
    mode: option(args, "--mode") ?? "auto",
    pages,
    fetchedAt: new Date().toISOString(),
    total: pages.length,
  };
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), "crawl_result.json");
  await writeJson(output, result);
  return { ...result, output };
}

async function directoryPlan(args: string[]) {
  const source = await readJson<JsonObject>(option(args, "--crawl-result", true)!);
  const rows = asRows(source.pages ?? source);
  const groups = new Map<string, JsonObject[]>();
  for (const page of rows) {
    const title = String(page.title ?? page.url ?? "Untitled");
    const key = title.split(/[:|/\\-]/)[0].trim() || "General";
    groups.set(key, [...(groups.get(key) ?? []), page]);
  }
  const tree = [...groups.entries()].map(([name, pages]) => ({
    name,
    children: pages
      .slice(0, 100)
      .map((page) => ({ name: String(page.title ?? page.url), sourceUrl: page.url })),
  }));
  const result = {
    source: option(args, "--crawl-result"),
    generatedAt: new Date().toISOString(),
    tree,
    confirmed: false,
  };
  const output = option(args, "--output") ?? join(outputRoot("kb-builder"), "directory_plan.json");
  await writeJson(output, result);
  if (flag(args, "--write-confirmed-tree"))
    await writeJson(join(stateRoot("kb-builder"), "confirmed_tree.json"), {
      ...result,
      confirmed: true,
    });
  return { output, directories: tree.length, pages: rows.length, tree };
}

async function createDirectories(client: SolveaClient, args: string[]) {
  const file = option(args, "--tree-file") ?? join(stateRoot("kb-builder"), "confirmed_tree.json");
  const value = await readJson<JsonObject>(file);
  const tree = Array.isArray(value.tree)
    ? (value.tree as JsonObject[])
    : Array.isArray(value)
      ? (value as unknown as JsonObject[])
      : [];
  if (!tree.length) throw new Error("confirmed directory tree is empty");
  const dryRun = flag(args, "--dry-run"),
    created: unknown[] = [];
  async function visit(nodes: JsonObject[], parentId = 0, depth = 0) {
    if (depth > intOption(args, "--max-depth", 3))
      throw new Error("directory tree exceeds max depth");
    for (const node of nodes) {
      const name = String(node.name ?? "").trim();
      if (!name) continue;
      const result = dryRun
        ? { name, parentId, dryRun: true }
        : await client.createFolder(name, parentId);
      created.push(result);
      const id = Number((result as JsonObject)?.id ?? (result as JsonObject)?.directoryId ?? 0);
      const children = Array.isArray(node.children) ? (node.children as JsonObject[]) : [];
      if (children.length && id) await visit(children, id, depth + 1);
    }
  }
  await visit(tree);
  return { file, dryRun, created, count: created.length };
}

async function extractWebQa(args: string[]) {
  const input = await readJson<JsonObject>(option(args, "--crawl-result", true)!);
  const pages = asRows(input.pages ?? input).slice(0, intOption(args, "--max-pages", 80));
  const outputDir = option(args, "--output-dir") ?? join(outputRoot("kb-builder"), "qa_parts");
  await ensureDir(outputDir);
  const parts = pages.map((page, index) => ({
    question: String(page.title ?? page.url),
    answer: String(page.text ?? "").slice(0, intOption(args, "--answer-limit", 3500)),
    sourceUrl: page.url,
    sourceTitle: page.title,
    index,
  }));
  const files: string[] = [];
  for (const [index, part] of parts.entries()) {
    const file = join(outputDir, `part_${String(index + 1).padStart(4, "0")}.json`);
    await writeJson(file, { items: [part] });
    files.push(file);
  }
  return { outputDir, files, count: files.length };
}

type QaPlanItem = {
  dirPath: string[];
  title: string;
  content: string;
  similarQuestions?: string[];
};
const flattenDirectories = (nodes: JsonObject[], result: JsonObject[] = []) => {
  for (const node of nodes) {
    result.push(node);
    if (Array.isArray(node.children))
      flattenDirectories(
        node.children.filter((child) => child && typeof child === "object") as JsonObject[],
        result,
      );
  }
  return result;
};

function validateQaItems(values: unknown[], maxDepth: number): QaPlanItem[] {
  if (!values.length) throw new Error("QA plan must contain at least one item");
  return values.map((value, index) => {
    if (!value || typeof value !== "object" || Array.isArray(value))
      throw new Error(`QA item #${index + 1} must be an object`);
    const item = value as JsonObject;
    if (!Array.isArray(item.dir_path) || !item.dir_path.length)
      throw new Error(`QA item #${index + 1} dir_path must be a non-empty array`);
    if (item.dir_path.length > maxDepth)
      throw new Error(`QA item #${index + 1} dir_path exceeds maximum depth ${maxDepth}`);
    const dirPath = item.dir_path.map((name, depth) => {
      if (typeof name !== "string" || !name.trim() || /[\\/]/.test(name))
        throw new Error(`QA item #${index + 1} dir_path[${depth}] must be a folder name`);
      return name.trim();
    });
    const title = typeof item.question === "string" ? item.question.trim() : "";
    const content = typeof item.answer === "string" ? item.answer.trim() : "";
    if (!title) throw new Error(`QA item #${index + 1} question must be a non-empty string`);
    if (!content)
      throw new Error(`QA item #${index + 1} answer must be a non-empty markdown string`);
    let similarQuestions: string[] | undefined;
    if (item.similar_questions !== undefined) {
      if (!Array.isArray(item.similar_questions))
        throw new Error(`QA item #${index + 1} similar_questions must be an array`);
      if (item.similar_questions.length > 10)
        throw new Error(`QA item #${index + 1} similar_questions has more than 10 entries`);
      similarQuestions = [];
      for (const value of item.similar_questions) {
        if (typeof value !== "string" || !value.trim())
          throw new Error(
            `QA item #${index + 1} similar_questions entries must be non-empty strings`,
          );
        const normalized = value.trim();
        if (normalized === title)
          throw new Error(
            `QA item #${index + 1} similar_questions must not repeat the primary question`,
          );
        if (similarQuestions.includes(normalized))
          throw new Error(`QA item #${index + 1} similar_questions must not contain duplicates`);
        similarQuestions.push(normalized);
      }
    }
    return { dirPath, title, content, similarQuestions };
  });
}

async function resolveDirectory(
  client: SolveaClient,
  path: string[],
  directories: JsonObject[],
  cache: Map<string, number>,
) {
  let parentId = 0;
  const prefix: string[] = [];
  for (const name of path) {
    prefix.push(name);
    const key = prefix.join("/");
    const cached = cache.get(key);
    if (cached !== undefined) {
      parentId = cached;
      continue;
    }
    const match = directories.find(
      (directory) =>
        String(directory.name ?? "") === name && Number(directory.parentId ?? 0) === parentId,
    );
    if (match) parentId = Number(match.id ?? match.directoryId);
    else {
      const createdParentId = parentId;
      const created = (await client.createFolder(name, parentId)) as JsonObject;
      const id = Number(created?.id ?? created?.directoryId);
      if (!Number.isSafeInteger(id) || id <= 0)
        throw new Error(`could not create directory ${key}: response has no directory id`);
      parentId = id;
      directories.push({ id, name, parentId: Number(created?.parentId ?? createdParentId) });
    }
    cache.set(key, parentId);
  }
  return parentId;
}

async function importQa(client: SolveaClient, args: string[]) {
  const qaFile = option(args, "--qa-file");
  const fromDir = option(args, "--from-dir");
  if (!qaFile && !fromDir) throw new Error("--qa-file or --from-dir is required");
  const items: unknown[] = [];
  if (qaFile) {
    const value = await readJson<unknown>(qaFile);
    items.push(
      ...(Array.isArray(value)
        ? value
        : (value as JsonObject).items && Array.isArray((value as JsonObject).items)
          ? ((value as JsonObject).items as unknown[])
          : [value]),
    );
  }
  if (fromDir) {
    const { readdir } = await import("node:fs/promises");
    for (const file of (await readdir(fromDir)).filter((name) => name.endsWith(".json")).sort()) {
      const value = await readJson<unknown>(join(fromDir, file));
      items.push(
        ...(Array.isArray(value)
          ? value
          : (value as JsonObject).items && Array.isArray((value as JsonObject).items)
            ? ((value as JsonObject).items as unknown[])
            : [value]),
      );
    }
  }
  const maxDepth = intOption(args, "--max-depth", 3);
  if (!Number.isSafeInteger(maxDepth) || maxDepth <= 0)
    throw new Error("--max-depth must be a positive integer");
  const normalized = validateQaItems(items, maxDepth);
  const plan = { items, count: items.length, createdAt: new Date().toISOString() };
  const planFile = join(outputRoot("kb-builder"), `qa_import_plan_${Date.now()}.json`);
  await writeJson(planFile, plan);
  if (flag(args, "--dry-run")) return { dryRun: true, planFile, count: items.length };
  const directories = flattenDirectories(asRows(await client.listDirectories()));
  const cache = new Map<string, number>();
  const payload = [];
  for (const item of normalized)
    payload.push({
      title: item.title,
      content: item.content,
      directoryId: await resolveDirectory(client, item.dirPath, directories, cache),
      ...(item.similarQuestions === undefined ? {} : { similarQuestions: item.similarQuestions }),
    });
  return { planFile, count: payload.length, result: await client.uploadQa(payload) };
}

async function importSources(client: SolveaClient, args: string[]) {
  const value = await readJson<unknown>(option(args, "--plan-file", true)!);
  const source = Array.isArray(value)
    ? value
    : value && typeof value === "object" && Array.isArray((value as JsonObject).items)
      ? ((value as JsonObject).items as unknown[])
      : [];
  if (!source.length) throw new Error("source document plan must be a non-empty array");
  const maxDepth = intOption(args, "--max-depth", 3);
  if (!Number.isSafeInteger(maxDepth) || maxDepth <= 0)
    throw new Error("--max-depth must be a positive integer");
  const { stat } = await import("node:fs/promises");
  const normalized: Array<{
    source: string;
    dirPath: string[];
    isUrl: boolean;
    skippedDuplicate: boolean;
  }> = [];
  const seenUrls = new Set<string>();
  for (const [index, raw] of source.entries()) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw))
      throw new Error(`source document #${index + 1} must be an object`);
    const item = raw as JsonObject;
    const itemSource = typeof item.source === "string" ? item.source.trim() : "";
    if (!itemSource) throw new Error(`source document #${index + 1} needs a non-empty source`);
    const path = item.dir_path ?? [];
    if (
      !Array.isArray(path) ||
      path.some((name) => typeof name !== "string" || !name.trim() || /[\\/]/.test(name))
    )
      throw new Error(`source document #${index + 1} dir_path must contain folder names`);
    if (path.length > maxDepth)
      throw new Error(`source document #${index + 1} dir_path exceeds maximum depth ${maxDepth}`);
    const isUrl = /^https?:\/\//i.test(itemSource);
    if (!isUrl) {
      if (
        ![".doc", ".docx", ".pdf"].some((extension) => itemSource.toLowerCase().endsWith(extension))
      )
        throw new Error(`source document #${index + 1} supports .doc, .docx, or .pdf`);
      const info = await stat(itemSource).catch(() => undefined);
      if (!info?.isFile())
        throw new Error(`source document #${index + 1} file not found: ${itemSource}`);
    }
    const skippedDuplicate = isUrl && seenUrls.has(itemSource);
    if (isUrl) seenUrls.add(itemSource);
    normalized.push({
      source: itemSource,
      dirPath: path.map(String).map((name) => name.trim()),
      isUrl,
      skippedDuplicate,
    });
  }
  if (!flag(args, "--execute"))
    return {
      dryRun: true,
      count: normalized.length,
      items: normalized.map((item) => ({
        source: item.source,
        dir_path: item.dirPath,
        status: item.skippedDuplicate ? "skipped_duplicate" : "pending",
      })),
    };

  const directories = flattenDirectories(asRows(await client.listDirectories()));
  const cache = new Map<string, number>();
  const results = [];
  for (const item of normalized) {
    if (item.skippedDuplicate) {
      results.push({ source: item.source, status: "skipped_duplicate" });
      continue;
    }
    const directoryId = await resolveDirectory(client, item.dirPath, directories, cache);
    const filePath = item.isUrl ? item.source : await client.uploadKnowledgeFile(item.source);
    const documents = [{ filePath, docType: "TC", ...(item.isUrl ? { fileType: "website" } : {}) }];
    const result = await client.createDocuments(
      documents,
      directoryId,
      item.isUrl ? "WEB" : "FILE",
    );
    results.push({ source: item.source, directoryId, status: "submitted", result });
  }
  return { count: normalized.length, results };
}

async function importTemplates(client: SolveaClient, args: string[]) {
  const planFile = option(args, "--plan-file");
  const inputFile = option(args, "--xlsx");
  if (Boolean(planFile) === Boolean(inputFile))
    throw new Error("exactly one of --xlsx or --plan-file is required");
  const source = planFile ?? inputFile!;
  const directoryId = option(args, "--directory-id");
  if (
    directoryId !== undefined &&
    (!Number.isSafeInteger(Number(directoryId)) || Number(directoryId) < 0)
  )
    throw new Error("--directory-id must be a non-negative integer");
  const rows: JsonObject[] = [];
  const skippedDuplicates: JsonObject[] = [];
  if (planFile) rows.push(...asRows(await readJson(source)));
  else {
    const workbook = new ExcelJS.Workbook();
    if (source.toLowerCase().endsWith(".csv")) await workbook.csv.readFile(source);
    else if (/\.xls(?:x|m)$/i.test(source)) await workbook.xlsx.readFile(source);
    else throw new Error("only .xlsx, .xlsm, and .csv files are supported");
    const sheet = option(args, "--sheet")
      ? workbook.getWorksheet(option(args, "--sheet")!)
      : workbook.worksheets[0];
    if (!sheet) throw new Error("workbook has no worksheet");
    const rawHeaders = (sheet.getRow(1).values as unknown[])
      .slice(1)
      .map((value) => String(value ?? "").trim());
    const headers = rawHeaders.map(canonicalTemplateHeader);
    for (const [canonical, argument] of [
      ["name", "--name-col"],
      ["content", "--content-col"],
      ["status", "--status-col"],
      ["scene", "--scene-col"],
    ] as const) {
      const requested = option(args, argument);
      if (!requested) continue;
      const index = rawHeaders.findIndex(
        (header) => normalizedTemplateHeader(header) === normalizedTemplateHeader(requested),
      );
      if (index < 0)
        throw new Error(`${argument} '${requested}' not found; available columns: ${rawHeaders}`);
      headers[index] = canonical;
    }
    for (const mapping of options(args, "--lang-col")) {
      const separator = mapping.indexOf("=");
      if (separator <= 0 || separator === mapping.length - 1)
        throw new Error(`--lang-col must use LANGUAGE=COLUMN format, got: ${mapping}`);
      const language = mapping.slice(0, separator).trim().toUpperCase();
      const requested = mapping.slice(separator + 1).trim();
      if (!templateLanguages.has(language))
        throw new Error(`unsupported template language: ${language}`);
      const index = rawHeaders.findIndex(
        (header) => normalizedTemplateHeader(header) === normalizedTemplateHeader(requested),
      );
      if (index < 0)
        throw new Error(
          `--lang-col ${language} '${requested}' not found; available columns: ${rawHeaders}`,
        );
      headers[index] = language;
    }
    if (!headers.includes("name") || !headers.includes("content"))
      throw new Error(
        `cannot detect template name/content columns; use --name-col and --content-col; available columns: ${rawHeaders}`,
      );
    sheet.eachRow((row, number) => {
      if (number === 1) return;
      const values = (row.values as unknown[]).slice(1);
      const item: JsonObject = {};
      headers.forEach((header, index) => {
        if (header) item[header] = String(values[index] ?? "").trim();
      });
      rows.push(item);
    });
  }
  const seenNames = new Set<string>();
  const items: JsonObject[] = [];
  rows.forEach((row, index) => {
    const name = String(row.name ?? row.Name ?? "").trim();
    const content = String(row.content ?? row.Content ?? row.template ?? "").trim();
    if (!name && !content) return;
    if (!name || !content) throw new Error(`row ${index + 2}: name and content are required`);
    if (seenNames.has(name)) {
      if (!flag(args, "--skip-duplicates"))
        throw new Error(`row ${index + 2}: duplicate template name in file: ${name}`);
      skippedDuplicates.push({ row: index + 2, name });
      return;
    }
    seenNames.add(name);
    const multiContent: JsonObject = { AUTO: row.AUTO || content };
    for (const language of templateLanguages)
      if (language !== "AUTO" && row[language]) multiContent[language] = row[language];
    const item: JsonObject = {
      name,
      content,
      status: row.status ?? row.Status ?? "ENABLED",
      scene: row.scene ?? row.Scene,
      multiContent: row.multiContent ?? multiContent,
    };
    if (directoryId !== undefined) item.directoryId = Number(directoryId);
    else if (row.directoryId !== undefined) item.directoryId = Number(row.directoryId);
    items.push(item);
  });
  const output =
    option(args, "--output") ??
    join(
      outputRoot("kb-builder"),
      `template_import_${flag(args, "--dry-run") ? "plan" : "result"}_${Date.now()}.json`,
    );
  const plan = { items, count: items.length, skipped_duplicates: skippedDuplicates };
  if (flag(args, "--dry-run")) {
    await writeJson(output, plan);
    return { dryRun: true, output, count: items.length, skipped_duplicates: skippedDuplicates };
  }
  const createdItems: JsonObject[] = [];
  const errors: JsonObject[] = [];
  for (const item of items) {
    try {
      const response = await client.createTemplate(item);
      const result = response && typeof response === "object" ? (response as JsonObject) : {};
      const data =
        result.data && typeof result.data === "object" ? (result.data as JsonObject) : {};
      createdItems.push({ id: result.id ?? data.id, name: item.name });
    } catch (error) {
      errors.push({
        name: item.name,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  const result = {
    input: items.length,
    created: createdItems.length,
    failed: errors.length,
    output,
    created_items: createdItems,
    skipped_duplicates: skippedDuplicates,
    errors,
  };
  await writeJson(output, result);
  return result;
}

async function exportKnowledge(client: SolveaClient, args: string[]) {
  const directories = asRows(await client.listDirectories());
  const ids = option(args, "--directory-id")
    ? [Number(option(args, "--directory-id"))]
    : directories.map((row) => Number(row.id ?? row.directoryId)).filter(Number.isFinite);
  const rows: JsonObject[] = [];
  for (const id of ids) {
    const value = await client.listKnowledge({
      directoryId: id,
      keyword: option(args, "--keyword") ?? "",
      type: option(args, "--type") ?? "ALL",
      pageSize: intOption(args, "--page-size", 1000),
    });
    rows.push(
      ...asRows(value).map((row) => ({
        ...row,
        directoryId: id,
        directoryName:
          directories.find((dir) => Number(dir.id ?? dir.directoryId) === id)?.name ?? "",
      })),
    );
  }
  const output =
    option(args, "--output") ?? join(outputRoot("kb-builder"), `knowledge_${Date.now()}.xlsx`);
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("knowledge");
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  sheet.addRow(keys);
  for (const row of rows) sheet.addRow(keys.map((key) => row[key] ?? ""));
  await ensureDir(join(output, ".."));
  await workbook.xlsx.writeFile(output);
  return { output, count: rows.length };
}

export async function runKbBuilder(
  session: Session | undefined,
  action: string | undefined,
  args: string[],
) {
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
  if (action === "extract-ticket-qa" || action === "batch-extract-ticket-qa")
    return extractTicketQa(args);
  throw new Error(`unknown kb-builder action: ${action}`);
}

async function extractTicketQa(args: string[]) {
  const file = option(args, "--xlsx", true)!;
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(file);
  const sheet = workbook.worksheets[0];
  if (!sheet) throw new Error("workbook has no worksheet");
  const headers = (sheet.getRow(1).values as unknown[]).slice(1).map((v) => String(v ?? ""));
  const messageCol =
    option(args, "--messages-col") ??
    headers.find((header) => /message|conversation|content|描述/i.test(header)) ??
    headers[0];
  const titleCol = option(args, "--title-col");
  const replyCol = option(args, "--reply-col");
  const brand = option(args, "--brand", true)!;
  const items: JsonObject[] = [];
  sheet.eachRow((row, number) => {
    if (number === 1) return;
    const values = (row.values as unknown[]).slice(1),
      record: JsonObject = {};
    headers.forEach((header, index) => {
      record[header] = values[index] ?? "";
    });
    const question =
      `${brand}: ${String(record[titleCol!] ?? "").trim()} ${String(record[messageCol!] ?? "").trim()}`.trim();
    const answer = String(record[replyCol!] ?? "").trim();
    if (question && question !== `${brand}:`) items.push({ question, answer, sourceRow: number });
  });
  const output =
    option(args, "--output") ?? join(outputRoot("kb-builder"), `ticket_qa_${Date.now()}.json`);
  const result = { brand, count: items.length, items };
  await writeJson(output, result);
  if (flag(args, "--dry-run")) return { dryRun: true, output, count: items.length };
  return { output, count: items.length, items };
}
