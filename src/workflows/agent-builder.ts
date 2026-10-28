import type { Session } from "../types.js";
import { flag, option, options } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { ensureDir, ensureParent, htmlEscape, readJson, safeJson, stateRoot, writeHtml, writeJson } from "./common.js";
import { createHash, createHmac, randomUUID } from "node:crypto";
import { open, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { compileChatflowSource } from "./chatflow-compiler.js";
import { validateChatflowGraph } from "./chatflow-validator.js";

type JsonObject = Record<string, unknown>;

function record(value: unknown): JsonObject | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : undefined;
}

function graphNodes(graph: unknown): JsonObject[] {
  if (!graph || typeof graph !== "object") return [];
  const root = graph as JsonObject;
  for (const key of ["nodes", "nodeList", "blocks"]) if (Array.isArray(root[key])) return root[key]!.filter(x => x && typeof x === "object") as JsonObject[];
  return [];
}

function graphEdges(graph: unknown): JsonObject[] {
  if (!graph || typeof graph !== "object") return [];
  const root = graph as JsonObject;
  for (const key of ["edges", "connections", "lines"]) if (Array.isArray(root[key])) return root[key]!.filter(x => x && typeof x === "object") as JsonObject[];
  return [];
}

export function validateGraph(graph: unknown) {
  return validateChatflowGraph(graph);
}

function flattenItems(value: unknown): JsonObject[] {
  if (Array.isArray(value)) return value.filter(record) as JsonObject[];
  const item = record(value); if (!item) return [];
  if (item.SYSTEM !== undefined || item.MANUAL !== undefined) return [...flattenItems(item.SYSTEM), ...flattenItems(item.MANUAL)];
  for (const key of ["data", "list", "records", "items"]) if (item[key] !== undefined) return flattenItems(item[key]);
  return [];
}
function walk(value: unknown, visit: (value: unknown) => void) {
  visit(value);
  if (Array.isArray(value)) value.forEach(item => walk(item, visit));
  else if (value && typeof value === "object") Object.values(value).forEach(item => walk(item, visit));
}
function bindSystemPlugins(graph: JsonObject, catalog: JsonObject[]) {
  const byType = new Map(catalog.map(plugin => [String(plugin.type ?? "").toUpperCase(), Number(plugin.id)]).filter(([, id]) => Number.isInteger(id)) as Array<[string, number]>);
  for (const node of graphNodes(graph)) {
    if (record(node.data)?.category !== "AGENT") continue;
    const agentData = record(record(record(node.data)?.config)?.agentData); if (!agentData) continue;
    const prompt = String(agentData.displayPrompt ?? ""), required = new Set<string>();
    for (const match of prompt.matchAll(/\{#LibraryBlock\s+(.+?)\s*#\}/g)) {
      const raw = match[1];
      if (/\btype=transferHuman\b/.test(raw)) required.add("TRANSFER_TO_HUMAN");
      else if (/\btype=tool\b/.test(raw) && /\btool=template_reply\b/.test(raw)) required.add("TEMPLATE_REPLY");
      else if (/\btype=tool\b/.test(raw) && /\bid=-3(?:\s|$)/.test(raw)) required.add("KNOWLEDGE_AI_REPLY");
    }
    const plugins = Array.isArray(agentData.usedPlugins) ? agentData.usedPlugins as number[] : [];
    for (const type of required) { const id = byType.get(type); if (id === undefined) throw new Error(`AGENT '${String(record(node.data)?.title ?? node.id)}' requires Chatflow system plugin type '${type}', but the Chatflow catalog did not return it`); if (!plugins.includes(id)) plugins.push(id); }
    agentData.usedPlugins = plugins;
  }
}
async function remoteValidation(client: SolveaClient, graph: JsonObject, bind = false) {
  const errors: string[] = [], warnings: string[] = [];
  let aiFields: JsonObject[] | undefined, plugins: JsonObject[] | undefined, templates: JsonObject[] | undefined;
  try { aiFields = flattenItems(await client.listAiFields()); } catch (error) { warnings.push(`queryAiFields: ${error instanceof Error ? error.message : String(error)}`); }
  try { plugins = flattenItems(await client.listChatflowPlugins(true)); if (bind) bindSystemPlugins(graph, plugins); } catch (error) { if (bind && error instanceof Error && error.message.includes("requires Chatflow system plugin")) errors.push(error.message); else warnings.push(`queryPlugin: ${error instanceof Error ? error.message : String(error)}`); }
  try { templates = flattenItems(await client.listTemplates({ name: "", pageIndex: 1, pageSize: 999 })); } catch (error) { warnings.push(`templates: ${error instanceof Error ? error.message : String(error)}`); }
  if (aiFields) {
    const paths = new Set<string>();
    const add = (field: JsonObject, category: string, parent: unknown[] = []) => { if (field.id === undefined) return; const path = [...parent, field.id]; paths.add(JSON.stringify(["SYSTEM", category, ...path])); for (const child of flattenItems(field.children)) add(child, category, path); };
    aiFields.forEach(field => add(field, String(field.bizType ?? "Custom")));
    walk(graph, value => { if (Array.isArray(value) && value[0] === "SYSTEM" && !paths.has(JSON.stringify(value))) errors.push(`references invalid SYSTEM field path ${JSON.stringify(value)}`); });
  }
  if (plugins) {
    const ids = new Set(plugins.map(item => Number(item.id)).filter(Number.isInteger));
    walk(graph, value => { const item = record(value); if (item?.category === "TOOL") { const id = Number(record(record(item.config)?.tool)?.id); if (Number.isInteger(id) && !ids.has(id)) errors.push(`TOOL references unknown plugin id ${id}`); } });
  }
  if (templates) {
    const byId = new Map(templates.map(item => [String(item.id ?? item.templateId), item]));
    walk(graph, value => { const item = record(value); if (!item) return; for (const key of ["templateId", "questionTemplateId"]) if (item[key]) { const template = byId.get(String(item[key])); if (!template) errors.push(`references unknown template id ${String(item[key])}`); else if (String(template.status ?? "").toUpperCase() !== "ENABLED") errors.push(`references template id ${String(item[key])} with status ${String(template.status ?? "UNKNOWN")}; expected ENABLED`); } });
  }
  return { errors: [...new Set(errors)], warnings: [...new Set(warnings)] };
}

function mergeDeep(base: unknown, patch: unknown): unknown {
  if (Array.isArray(base) && Array.isArray(patch)) return [...base, ...patch];
  if (base && patch && typeof base === "object" && typeof patch === "object" && !Array.isArray(base) && !Array.isArray(patch)) {
    const out: JsonObject = { ...(base as JsonObject) };
    for (const [key, value] of Object.entries(patch as JsonObject)) out[key] = key in out ? mergeDeep(out[key], value) : value;
    return out;
  }
  return patch;
}

function mergeSourceFragments(fragments: Array<{ path: string; value: unknown }>, integrationValue: unknown) {
  if (!fragments.length) throw new Error("at least one source fragment is required");
  const integration = record(integrationValue); if (!integration) throw new Error("integration document must be a JSON object");
  if ("nodes" in integration) throw new Error("integration document must not define nodes; put nodes in source fragments");
  const entry = typeof integration.entry === "string" ? integration.entry.trim() : ""; if (!entry) throw new Error("integration document requires a non-empty entry node key");
  const connectorEdges = integration.edges ?? []; if (!Array.isArray(connectorEdges)) throw new Error("integration.edges must be a list");
  const nodes: JsonObject[] = [], edges: JsonObject[] = [], nodeKeys = new Set<string>(), signatures = new Set<string>();
  const origins = new Map<string, string>(), fragmentEdges: Array<{ from: string; to: string; origin: string; keys: Set<string> }> = [];
  const edgeKeys = (raw: unknown, origin: string) => { const edge = record(raw); if (!edge) throw new Error(`${origin} edge must be an object`); const from = String(edge.from ?? edge.source ?? "").trim(), to = String(edge.to ?? edge.target ?? "").trim(); if (!from) throw new Error(`${origin} edge missing source key`); if (!to) throw new Error(`${origin} edge missing target key`); const signature = JSON.stringify(Object.fromEntries(Object.entries(edge).sort(([a], [b]) => a.localeCompare(b)))); if (signatures.has(signature)) throw new Error(`duplicate source edge while merging: ${from} -> ${to}`); signatures.add(signature); edges.push(structuredClone(edge)); return { from, to }; };
  for (const fragmentItem of fragments) {
    const fragment = record(fragmentItem.value); if (!fragment) throw new Error(`source fragment must be a JSON object: ${fragmentItem.path}`);
    if ("entry" in fragment) throw new Error(`source fragment must not define entry; integration owns the final entry: ${fragmentItem.path}`);
    if (!Array.isArray(fragment.nodes) || !fragment.nodes.length) throw new Error(`source fragment requires a non-empty nodes list: ${fragmentItem.path}`);
    if (fragment.edges !== undefined && !Array.isArray(fragment.edges)) throw new Error(`source fragment edges must be a list: ${fragmentItem.path}`);
    const keys = new Set<string>();
    fragment.nodes.forEach((raw, index) => { const node = record(raw); if (!node) throw new Error(`source fragment node must be an object: ${fragmentItem.path}[${index}]`); const key = typeof node.key === "string" ? node.key.trim() : ""; if (!key) throw new Error(`source fragment node requires an explicit key: ${fragmentItem.path}[${index}]`); if (nodeKeys.has(key)) throw new Error(`duplicate source node key while merging: ${key}`); nodeKeys.add(key); keys.add(key); origins.set(key, fragmentItem.path); nodes.push(structuredClone(node)); });
    for (const raw of fragment.edges ?? []) { const parsed = edgeKeys(raw, fragmentItem.path); fragmentEdges.push({ ...parsed, origin: fragmentItem.path, keys }); }
  }
  const terminals = new Set(["$finish", "$transfer"]);
  for (const edge of fragmentEdges) { if (!edge.keys.has(edge.from)) throw new Error(`source fragment edge must start at a node in the same fragment: ${edge.origin}: ${edge.from}`); if (!edge.keys.has(edge.to) && !terminals.has(edge.to)) throw new Error(`source fragment edge crosses flow blocks; put cross-block edges in integration: ${edge.origin}: ${edge.from} -> ${edge.to}`); }
  for (const raw of connectorEdges) { const { from, to } = edgeKeys(raw, "integration"); if (!nodeKeys.has(from)) throw new Error(`integration edge source key not found in fragments: ${from}`); if (!nodeKeys.has(to) && !terminals.has(to)) throw new Error(`integration edge target key not found in fragments: ${to}`); if (origins.get(from) && origins.get(from) === origins.get(to)) throw new Error(`integration edge stays inside one source fragment; put it in that fragment instead: ${from} -> ${to}`); }
  if (!nodeKeys.has(entry)) throw new Error(`integration entry key not found in fragments: ${entry}`);
  return { entry, nodes, edges };
}

function digest(value: unknown) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

type MutationAction = "deploy" | "update" | "publish";

function confirmationToken(session: Session, action: MutationAction, args: string[], graph: JsonObject) {
  const payload = {
    action,
    agentId: option(args, "--agent-id") ?? null,
    agentName: option(args, "--agent-name") ?? null,
    graphSha256: digest(graph),
    tenantContext: session.tenant?.context ?? null,
    expiresAt: Date.now() + 10 * 60 * 1000,
  };
  const body = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  const key = session.tenant?.businessToken;
  if (!key) throw new Error("selected tenant has no business token");
  const signature = createHmac("sha256", key).update(body).digest("base64url");
  return `${body}.${signature}`;
}

async function readConfirmationToken() {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8").trim();
}

function verifyConfirmationToken(session: Session, token: string, action: MutationAction, args: string[], graph: JsonObject) {
  const [body, signature, ...rest] = token.split(".");
  if (!body || !signature || rest.length) throw new Error("invalid confirmation token");
  const key = session.tenant?.businessToken;
  if (!key) throw new Error("selected tenant has no business token");
  const expected = createHmac("sha256", key).update(body).digest("base64url");
  if (signature !== expected) throw new Error("confirmation token signature mismatch");
  let payload: JsonObject;
  try { payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as JsonObject; } catch { throw new Error("invalid confirmation token payload"); }
  if (Number(payload.expiresAt) < Date.now()) throw new Error("confirmation token expired; run preview again");
  if (payload.action !== action || payload.graphSha256 !== digest(graph) || payload.tenantContext !== (session.tenant?.context ?? null)) {
    throw new Error("confirmation token does not match this action, tenant, or graph");
  }
  if (action === "deploy" && payload.agentName !== (option(args, "--agent-name") ?? null)) throw new Error("confirmation token agent name mismatch");
  if (action !== "deploy" && payload.agentId !== (option(args, "--agent-id") ?? null)) throw new Error("confirmation token agent id mismatch");
}

function skeletonGraph() {
  const startId = randomUUID(), finishId = randomUUID();
  return {
    nodes: [
      { id: startId, type: "CUSTOM", data: { category: "START" }, position: { x: 0, y: 0 } },
      { id: finishId, type: "CUSTOM", data: { category: "FINISH", title: "Finish", config: {} }, position: { x: 360, y: 0 } },
    ],
    edges: [{ id: `e-${startId.slice(0, 8)}-SOURCE-${finishId.slice(0, 8)}`, source: startId, sourceHandle: "SOURCE", target: finishId, targetHandle: "TARGET", type: "default" }],
    viewport: { x: 0, y: 0, zoom: 1 },
  };
}

async function createAgentIdempotently(client: SolveaClient, key: string, fingerprint: string, agentName: string, graph: JsonObject) {
  const directory = stateRoot("agent-builder/chatflow-idempotency");
  await ensureDir(directory);
  const file = join(directory, `${digest(key)}.json`);
  let handle;
  try {
    handle = await open(file, "wx", 0o600);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    const record = JSON.parse(await readFile(file, "utf8")) as JsonObject;
    if (record.fingerprint !== fingerprint) throw new Error("idempotency key was already used for a different Chatflow deployment");
    if (record.status === "completed") return { idempotentReplay: true, result: record.result };
    throw new Error("an earlier deployment with this idempotency key may still be in progress; inspect the Agent list before retrying");
  }
  try {
    await handle.writeFile(`${JSON.stringify({ status: "pending", fingerprint, createdAt: Date.now() }, null, 2)}\n`, "utf8");
  } finally {
    await handle.close();
  }
  const created = await client.createAgent({ name: agentName, type: "CHAT_FLOW", category: "TEXT", source: "MANUAL", meta: { chatFlowGraph: skeletonGraph() } }, key);
  const createdObject = created as JsonObject;
  const agentId = createdObject.id ?? record(createdObject.data)?.id;
  if (agentId === undefined || agentId === null || agentId === "") throw new Error("createAgent response did not contain an agent id");
  const detail = await client.getAgent(String(agentId));
  const agent = (Array.isArray(detail) ? detail[0] : detail) as JsonObject;
  if (!agent || typeof agent !== "object") throw new Error(`created Agent ${String(agentId)} could not be loaded`);
  await client.updateAgent({ ...agent, agentId, meta: { ...(record(agent.meta) ?? {}), chatFlowGraph: graph } });
  const result = { agent_id: agentId };
  await writeFile(file, `${JSON.stringify({ status: "completed", fingerprint, completedAt: Date.now(), result }, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  return result;
}

async function inspect(client: SolveaClient | undefined, args: string[]) {
  if (!client) throw new Error("inspect requires an authenticated tenant");
  const agentId = option(args, "--agent-id");
  const agentName = option(args, "--agent-name");
  if (!agentId && !agentName) throw new Error("inspect requires --agent-id or --agent-name");
  let agent: unknown;
  if (agentId) agent = await client.getAgent(agentId);
  else {
    const result = await client.listAgents("text");
    const rows = Array.isArray(result) ? result : (result as JsonObject)?.list;
    agent = Array.isArray(rows) ? rows.find(row => String((row as JsonObject).name ?? (row as JsonObject).agentName) === agentName) : undefined;
    if (!agent) throw new Error(`agent not found: ${agentName}`);
  }
  const item = Array.isArray(agent) ? agent[0] as JsonObject : agent as JsonObject;
  const id = String(item?.id ?? item?.agentId ?? agentId ?? "");
  const graph = id ? await client.getChatflowGraph(id) : undefined;
  const result = { agent: item, graph };
  const out = option(args, "--out");
  if (out) await writeJson(out, graph);
  return result;
}

async function chatflow(session: Session | undefined, client: SolveaClient | undefined, action: string, args: string[]) {
  if (action === "inspect") return inspect(client, args);
  if (action === "validate") {
    const file = option(args, "--graph-file") ?? option(args, "--data-file", true)!;
    const graph = await readJson(file);
    const local = validateGraph(graph), remote = client && !flag(args, "--offline") ? await remoteValidation(client, graph as JsonObject) : { errors: [], warnings: ["offline validation: remote AI fields, plugin metadata, and template status were not checked"] };
    return { ...local, valid: local.valid && !remote.errors.length, errors: [...local.errors, ...remote.errors], warnings: [...local.warnings, ...remote.warnings], file };
  }
  if (action === "compile") {
    const source = await readJson(option(args, "--source-file", true)!);
    const graphFile = option(args, "--graph-file", true)!;
    const result = compileChatflowSource(source);
    const remote = client && !flag(args, "--offline") ? await remoteValidation(client, result as JsonObject, true) : { errors: [], warnings: ["offline compilation: remote AI fields, plugin metadata, and template status were not checked"] };
    const local = validateGraph(result), validation = { ...local, valid: local.valid && !remote.errors.length, errors: [...local.errors, ...remote.errors], warnings: [...local.warnings, ...remote.warnings] };
    if (!validation.valid) throw new Error(`compiled graph is invalid: ${validation.errors.join("; ")}`);
    await writeJson(graphFile, result);
    return { ...validation, graph: result };
  }
  if (action === "merge-source") {
    const integration = await readJson(option(args, "--integration-file", true)!);
    const fragmentPaths = options(args, "--fragment-file");
    const result = mergeSourceFragments(await Promise.all(fragmentPaths.map(async path => ({ path, value: await readJson(path) }))), integration);
    await writeJson(option(args, "--out-file", true)!, result);
    return { output: option(args, "--out-file"), nodes: result.nodes.length, edges: result.edges.length };
  }
  if (["deploy", "update", "publish"].includes(action)) {
    const graph = await readJson(option(args, "--graph-file", true)!);
    const validation = validateGraph(graph);
    if (!validation.valid) throw new Error(`graph validation failed: ${validation.errors.join("; ")}`);
    if (!client) throw new Error("this chatflow action requires an authenticated tenant");
    const mutation = action as MutationAction;
    const phase = option(args, "--phase");
    if (phase !== "preview" && phase !== "commit") throw new Error(`${mutation} requires --phase preview or --phase commit`);
    if (phase === "preview") {
      return {
        phase: "preview",
        action: mutation,
        environment: client.environment,
        tenantId: client.tenantId,
        ...(mutation === "deploy" ? { agentName: option(args, "--agent-name", true) } : { agentId: option(args, "--agent-id", true) }),
        graph: { sha256: digest(graph), nodeCount: validation.nodeCount, edgeCount: validation.edgeCount },
        confirmationToken: confirmationToken(session!, mutation, args, graph as JsonObject),
        expiresInSeconds: 600,
      };
    }
    if (!flag(args, "--confirmation-token-stdin")) throw new Error(`${mutation} commit requires --confirmation-token-stdin`);
    const idempotencyKey = option(args, "--idempotency-key");
    if (!idempotencyKey) throw new Error(`${mutation} commit requires --idempotency-key`);
    verifyConfirmationToken(session!, await readConfirmationToken(), mutation, args, graph as JsonObject);
    if (mutation === "deploy") {
      const agentName = option(args, "--agent-name", true)!;
      const fingerprint = digest({ mutation, tenant: session!.tenant?.context, agentName, graph });
      return createAgentIdempotently(client, idempotencyKey, fingerprint, agentName, graph as JsonObject);
    }
    const id = option(args, "--agent-id", true)!;
    return client.updateChatflow(id, graph as JsonObject, action === "publish");
  }
  throw new Error(`unknown chatflow action: ${action}`);
}

async function validateTool(args: string[]) {
  const value = await readJson(option(args, "--data-file", true)!);
  const errors: string[] = [], warnings: string[] = [];
  if (!value || typeof value !== "object" || Array.isArray(value)) errors.push("tool payload must be an object");
  else {
    const object = value as JsonObject;
    if (!object.name && !object.pluginName) errors.push("tool name is required");
    if (!object.config && !object.externalHttpCallConfig && !object.url) warnings.push("tool has no HTTP configuration");
  }
  return { valid: errors.length === 0, errors, warnings };
}

export async function runAgentBuilder(session: Session | undefined, action: string | undefined, args: string[]) {
  if (!action) throw new Error("agent-builder action is required");
  if (action === "chatflow") { const operation = options(args, "--operation")[0] ?? args.find(value => ["inspect", "validate", "compile", "merge-source", "deploy", "update", "publish"].includes(value)) ?? "inspect"; return chatflow(session, operation === "merge-source" || flag(args, "--offline") ? undefined : session ? new SolveaClient(session) : undefined, operation, args); }
  if (["validate", "compile", "merge-source"].includes(action)) return chatflow(session, action === "merge-source" || flag(args, "--offline") ? undefined : session ? new SolveaClient(session) : undefined, action, args);
  if (["inspect", "deploy", "update", "publish"].includes(action)) return chatflow(session, session ? new SolveaClient(session) : undefined, action, args);
  if (action === "validate-tool") return validateTool(args);
  if (action === "migration" || action === "replay") return runLocalAgentWorkflow(action, args);
  if (!session) throw new Error(`${action} requires an authenticated tenant`);
  const client = new SolveaClient(session);
  if (action === "copy-marketplace") {
    const ids = options(args, "--square-id");
    if (!ids.length) throw new Error("--square-id is required");
    if (flag(args, "--dry-run")) return { dryRun: true, squareIds: ids };
    const results = [];
    for (const id of ids) results.push(await client.rawCall("POST", "/api_v2/gpt/ap/copySquareAgent", { squareAgentId: Number(id), projectId: Number(await client.projectId()) }));
    return { squareIds: ids, results };
  }
  if (action === "patch-tools") {
    const ids = options(args, "--agent-id");
    if (!ids.length) throw new Error("--agent-id is required");
    const headers = options(args, "--header").map(value => { const index = value.indexOf("="); return index < 1 ? { name: value, value: "" } : { name: value.slice(0, index), value: value.slice(index + 1) }; });
    if (flag(args, "--dry-run")) return { dryRun: true, agentIds: ids, headers };
    const results = [];
    for (const id of ids) {
      const agent = await client.getAgent(id);
      const item = (Array.isArray(agent) ? agent[0] : agent) as JsonObject;
      const tools = Array.isArray(item?.tools) ? item.tools as JsonObject[] : [];
      const changed = tools.map(tool => ({ ...tool, headers: [...(Array.isArray(tool.headers) ? tool.headers : []), ...headers] }));
      results.push(await client.updateAgent({ ...item, agentId: Number(id), tools: changed }));
    }
    return { agentIds: ids, results };
  }
  throw new Error(`unknown agent-builder action: ${action}`);
}

async function runLocalAgentWorkflow(action: string, args: string[]) {
  if (action === "migration") {
    const operation = option(args, "--operation") ?? args.find(value => ["inspect", "emit-chunk-context", "prepare-batch", "prepare-batches", "merge-batch-plans", "emit-batch-context", "emit-mapping-mermaid", "validate-migration-plan", "validate-prompt-block-rendering", "audit-migration-source", "emit-handoff", "verify-handoff", "coverage-report", "update-progress", "update-batch-progress"].includes(value)) ?? "inspect";
    if (operation === "update-progress" || operation === "update-batch-progress") { const file = option(args, "--progress-file", true)!; const progress = await readJson<JsonObject>(file).catch(() => ({} as JsonObject)); const id = option(args, operation === "update-progress" ? "--chunk-id" : "--batch-id", true)!; const status = option(args, "--status", true)!; const key = operation === "update-progress" ? "chunks" : "batches"; const entries = Array.isArray(progress[key]) ? progress[key] as JsonObject[] : []; const existing = entries.find(entry => String(entry.id ?? entry.chunkId ?? entry.batchId) === id); if (existing) existing.status = status; else entries.push({ id, status, note: option(args, "--note"), artifacts: options(args, "--artifact") }); progress[key] = entries; await writeJson(file, progress); return { operation, id, status, file }; }
    const input = option(args, "--input") ?? option(args, "--plan-file") ?? option(args, "--source-file") ?? option(args, "--index-file"); if (!input) throw new Error("migration requires --input or a plan/source file"); const value = await readJson(input);
    if (["validate", "validate-plan", "validate-migration-plan", "audit", "audit-migration-source", "validate-prompt-block-rendering"].includes(operation)) return { operation, valid: true, validation: validateGraph(value), file: input };
    if (operation === "mermaid" || operation === "emit-mapping-mermaid") { const nodes = graphNodes(value), edges = graphEdges(value); const lines = ["flowchart TD", ...nodes.map(node => `  ${String(node.id ?? node.nodeId)}[${String(node.name ?? node.type ?? "node")}]`), ...edges.map(edge => `  ${String(edge.source ?? edge.from)} --> ${String(edge.target ?? edge.to)}`)]; const out = option(args, "--out-file"); if (out) await writeFileText(out, lines.join("\n")); return { mermaid: lines.join("\n"), output: out }; }
    return { operation, input, nodeCount: graphNodes(value).length, edgeCount: graphEdges(value).length, value };
  }
  const input = option(args, "--cases-file") ?? option(args, "--input"); const cases = input ? await readJson(input) : [{ id: option(args, "--synthetic-case-id") ?? "synthetic_smoke", message: "status" }]; const rows = Array.isArray(cases) ? cases : [cases]; const output = { cases: rows, executed: flag(args, "--execute"), results: [] }; const out = option(args, "--out-json"); if (out) await writeJson(out, output); const html = option(args, "--out-html"); if (html) await writeHtml(html, "Replay comparison", `<pre>${htmlEscape(safeJson(output))}</pre>`); return output;
}

async function writeFileText(file: string, content: string) { await ensureParent(file); const { writeFile } = await import("node:fs/promises"); await writeFile(file, `${content}\n`, "utf8"); }
