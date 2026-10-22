import type { Session } from "../types.js";
import { flag, option, options } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { ensureParent, htmlEscape, readJson, safeJson, writeHtml, writeJson } from "./common.js";

type JsonObject = Record<string, unknown>;

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
  const errors: string[] = [], warnings: string[] = [];
  if (!graph || typeof graph !== "object" || Array.isArray(graph)) errors.push("graph must be a JSON object");
  const nodes = graphNodes(graph), edges = graphEdges(graph);
  if (!nodes.length) warnings.push("graph contains no nodes");
  const ids = new Set<string>();
  for (const [index, node] of nodes.entries()) {
    const id = String(node.id ?? node.nodeId ?? node.key ?? "");
    if (!id) errors.push(`nodes[${index}] is missing id`);
    else if (ids.has(id)) errors.push(`duplicate node id: ${id}`);
    else ids.add(id);
    if (!node.type && !node.nodeType && !node.kind) warnings.push(`nodes[${index}] is missing type`);
  }
  for (const [index, edge] of edges.entries()) {
    const from = String(edge.source ?? edge.sourceId ?? edge.from ?? edge.start ?? "");
    const to = String(edge.target ?? edge.targetId ?? edge.to ?? edge.end ?? "");
    if (!from || !to) errors.push(`edges[${index}] must contain source and target`);
    else {
      if (!ids.has(from)) errors.push(`edge ${index} references unknown source ${from}`);
      if (!ids.has(to)) errors.push(`edge ${index} references unknown target ${to}`);
    }
  }
  return { valid: errors.length === 0, errors, warnings, nodeCount: nodes.length, edgeCount: edges.length };
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

async function chatflow(client: SolveaClient | undefined, action: string, args: string[]) {
  if (action === "inspect") return inspect(client, args);
  if (action === "validate") {
    const file = option(args, "--graph-file") ?? option(args, "--data-file", true)!;
    const graph = await readJson(file);
    return { ...(validateGraph(graph)), file };
  }
  if (action === "compile") {
    const source = await readJson(option(args, "--source-file", true)!);
    const graph = await readJson(option(args, "--graph-file", true)!);
    const result = mergeDeep(graph, source);
    const validation = validateGraph(result);
    if (!validation.valid) throw new Error(`compiled graph is invalid: ${validation.errors.join("; ")}`);
    await writeJson(option(args, "--graph-file", true)!, result);
    return { ...validation, graph: result };
  }
  if (action === "merge-source") {
    const integration = await readJson(option(args, "--integration-file", true)!);
    let result: unknown = integration;
    for (const fragment of options(args, "--fragment-file")) result = mergeDeep(result, await readJson(fragment));
    await writeJson(option(args, "--out-file", true)!, result);
    return { output: option(args, "--out-file"), ...(validateGraph(result)) };
  }
  if (["deploy", "update", "publish"].includes(action)) {
    const graph = await readJson(option(args, "--graph-file", true)!);
    const validation = validateGraph(graph);
    if (!validation.valid) throw new Error(`graph validation failed: ${validation.errors.join("; ")}`);
    if (!client) throw new Error("this chatflow action requires an authenticated tenant");
    if (action === "deploy") return client.createAgent({ name: option(args, "--agent-name", true), type: "CHAT_FLOW", meta: { chatFlowGraph: graph } });
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
  if (action === "chatflow") { const operation = options(args, "--operation")[0] ?? args.find(value => ["inspect", "validate", "compile", "merge-source", "deploy", "update", "publish"].includes(value)) ?? "inspect"; return chatflow(["validate", "compile", "merge-source"].includes(operation) ? undefined : session ? new SolveaClient(session) : undefined, operation, args); }
  if (["validate", "compile", "merge-source"].includes(action)) return chatflow(undefined, action, args);
  if (["inspect", "deploy", "update", "publish"].includes(action)) return chatflow(session ? new SolveaClient(session) : undefined, action, args);
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
