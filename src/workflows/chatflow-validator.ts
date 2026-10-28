import type { JsonObject } from "./chatflow-compiler.js";

export type GraphValidation = {
  valid: boolean;
  errors: string[];
  warnings: string[];
  nodeCount: number;
  edgeCount: number;
  stats: { nodes: number; edges: number };
};

function record(value: unknown): JsonObject | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : undefined;
}
function category(node: JsonObject) { return String(record(node.data)?.category ?? ""); }
function title(node: JsonObject) { return String(record(node.data)?.title ?? node.id ?? ""); }
function config(node: JsonObject) { return record(record(node.data)?.config) ?? {}; }
function containsCycle(ids: Set<string>, edges: JsonObject[]) {
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) outgoing.set(String(edge.source), [...(outgoing.get(String(edge.source)) ?? []), String(edge.target)]);
  const visiting = new Set<string>(), visited = new Set<string>();
  const visit = (id: string): boolean => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    for (const next of outgoing.get(id) ?? []) if (ids.has(next) && visit(next)) return true;
    visiting.delete(id); visited.add(id); return false;
  };
  return [...ids].some(visit);
}
function selectors(value: unknown, path = "root", out: Array<{ selector: unknown[]; path: string }> = []) {
  if (Array.isArray(value)) {
    if (["SYSTEM", "TOOL", "NODE", "EXTRACT", "CODE", "LLM", "AGENT", "HUMAN_REVIEW", "SELF", "FLOW", "META"].includes(String(value[0]))) out.push({ selector: value, path });
    else value.forEach((item, index) => selectors(item, `${path}[${index}]`, out));
  } else if (value && typeof value === "object") for (const [key, child] of Object.entries(value)) selectors(child, `${path}.${key}`, out);
  return out;
}

export function validateChatflowGraph(graph: unknown): GraphValidation {
  const errors: string[] = [], warnings: string[] = [], root = record(graph);
  if (!root) errors.push("graph must be a JSON object");
  const nodes = Array.isArray(root?.nodes) ? root.nodes.filter(record) as JsonObject[] : [];
  const edges = Array.isArray(root?.edges) ? root.edges.filter(record) as JsonObject[] : [];
  if (!Array.isArray(root?.nodes)) errors.push("graph.nodes must be an array");
  if (!Array.isArray(root?.edges)) errors.push("graph.edges must be an array");
  if (root && !Array.isArray(root.variables)) errors.push("graph.variables must be an array");
  if (!nodes.length) errors.push("Graph has no nodes");

  const ids = new Set<string>(), nodeById = new Map<string, JsonObject>();
  nodes.forEach((node, index) => {
    const id = typeof node.id === "string" ? node.id.trim() : "";
    if (!id) errors.push(`nodes[${index}] is missing id`);
    else if (ids.has(id)) errors.push(`duplicate node id: ${id}`);
    else { ids.add(id); nodeById.set(id, node); }
    if (!category(node)) errors.push(`nodes[${index}] is missing data.category`);
  });

  const edgeIds = new Set<string>(), outgoing = new Map<string, JsonObject[]>(), incoming = new Map<string, JsonObject[]>();
  const required = ["id", "source", "sourceHandle", "target", "targetHandle", "type"];
  edges.forEach((edge, index) => {
    for (const field of required) if (edge[field] === undefined || edge[field] === null || (typeof edge[field] === "string" && !edge[field].trim())) errors.push(`edge[${index}] missing ${field}`);
    const id = String(edge.id ?? ""); if (id && edgeIds.has(id)) errors.push(`duplicate edge id '${id}'`); else if (id) edgeIds.add(id);
    if (edge.type !== undefined && edge.type !== "default") errors.push(`edge[${index}] unsupported type '${String(edge.type)}'; expected 'default'`);
    const from = String(edge.source ?? ""), to = String(edge.target ?? "");
    if (from && !ids.has(from)) errors.push(`Edge ${id || `edge[${index}]`}: source '${from}' not in nodes`);
    if (to && !ids.has(to)) errors.push(`Edge ${id || `edge[${index}]`}: target '${to}' not in nodes`);
    if (from && to) { outgoing.set(from, [...(outgoing.get(from) ?? []), edge]); incoming.set(to, [...(incoming.get(to) ?? []), edge]); }
  });

  const starts = nodes.filter(node => category(node) === "START");
  if (!starts.length) errors.push("Missing START node");
  else if (starts.length > 1) errors.push(`Multiple START nodes found: ${starts.map(node => node.id).join(", ")}`);
  if (starts.length === 1 && !(outgoing.get(String(starts[0].id))?.length)) errors.push(`START node '${String(starts[0].id)}' has no outgoing edge`);

  if (starts.length === 1) {
    const reachable = new Set<string>(), queue = [String(starts[0].id)];
    while (queue.length) { const id = queue.shift()!; if (reachable.has(id)) continue; reachable.add(id); for (const edge of outgoing.get(id) ?? []) queue.push(String(edge.target)); }
    const orphan = [...ids].filter(id => !reachable.has(id));
    if (orphan.length) errors.push(`Orphan nodes not reachable from START: ${orphan.map(id => `${id}(${category(nodeById.get(id)!)})`).join(", ")}`);
  }
  if (containsCycle(ids, edges)) errors.push("Graph contains a cycle");

  const seenTitles = new Set<string>();
  for (const node of nodes) {
    const cat = category(node), id = String(node.id), nodeTitle = title(node), cfg = config(node), handles = new Set((outgoing.get(id) ?? []).map(edge => String(edge.sourceHandle)));
    if (cat !== "START") {
      if (!nodeTitle.trim()) errors.push(`Node '${id}' (${cat}) has empty title`);
      else if (seenTitles.has(nodeTitle)) errors.push(`Duplicate node title: '${nodeTitle}'`); else seenTitles.add(nodeTitle);
      if (!(incoming.get(id)?.length)) warnings.push(`Node '${id}' (${cat}) has no incoming edge`);
    }
    const requireOutgoing = !["FINISH", "SUB_GRAPH", "TRANSFER_TO_HUMAN"].includes(cat);
    if (requireOutgoing && !(outgoing.get(id)?.length)) errors.push(`${cat} '${nodeTitle}' has no outgoing edge`);
    if (["FINISH", "SUB_GRAPH"].includes(cat) && (outgoing.get(id)?.length)) errors.push(`${cat} '${nodeTitle}' must not have outgoing edges`);
    const requireHandles = (expected: string[]) => expected.forEach(handle => { if (!handles.has(handle)) errors.push(`${cat} '${nodeTitle}' missing ${handle} edge`); });
    if (cat === "QUESTION") {
      const info = record(cfg.collectInfo) ?? {};
      if (info.type === "USER_REPLY") requireHandles([...(Array.isArray(info.replies) ? info.replies.map(item => String(record(item)?.id ?? "")) : []), "OTHER"]);
      else requireHandles(["SOURCE"]);
    } else if (cat === "INTENT") requireHandles([...(Array.isArray(cfg.intents) ? cfg.intents.map(item => String(record(item)?.id ?? "")) : []), "OTHER"]);
    else if (cat === "IF_ELSE") requireHandles([...(Array.isArray(cfg.cases) ? cfg.cases.map(item => String(record(item)?.id ?? "")) : []), "FALSE"]);
    else if (cat === "RAG_REPLY") requireHandles(["TRUE", "LACK_KNOWLEDGE"]);
    else if (cat === "KNOWLEDGE_REPLY") requireHandles(["RESOLVED", "UNRESOLVED"]);
    else if (cat === "HUMAN_REVIEW" && record(cfg.humanReview)?.method === "approval") requireHandles(["AGREE", "REJECT"]);
    else if (cat === "AGENT") {
      const data = record(cfg.agentData) ?? {};
      if (!String(data.prompt ?? "").trim()) errors.push(`AGENT node '${id}' has empty prompt`);
      if (!String(data.displayPrompt ?? "").trim()) errors.push(`AGENT node '${id}' has empty displayPrompt`);
      const steps = Array.isArray(cfg.nextStep) ? cfg.nextStep : [];
      requireHandles(steps.length ? steps.map(step => String(record(step)?.id ?? "")) : ["SOURCE"]);
      if (!Array.isArray(data.usedPlugins) || data.usedPlugins.some(item => !Number.isInteger(item) || typeof item === "boolean")) errors.push(`AGENT '${nodeTitle}' usedPlugins must contain integer ids`);
      if (data.enableKnowledgeBase && !(data.usedPlugins as unknown[]).includes(-3)) errors.push(`AGENT '${nodeTitle}' enables knowledge base but is missing KNOWLEDGE_AI_REPLY plugin -3`);
    } else if (requireOutgoing) requireHandles(["SOURCE"]);

    if (cat === "CODE") {
      const code = record(cfg.code) ?? {}, outputs = code.outputs;
      if (!Array.isArray(outputs) || !outputs.length) errors.push(`CODE '${nodeTitle}' must declare at least one output`);
      const source = String(code.sourceCode ?? "");
      if (/\b(import|from)\s+(os|sys|subprocess|socket|pathlib|shutil|requests)\b/.test(source) || /\b(eval|exec|compile|__import__|open)\s*\(/.test(source) || /__(class|mro|bases|subclasses|globals|dict|builtins|import)__/.test(source)) errors.push(`CODE '${nodeTitle}' contains forbidden Python operations`);
    }
    if (cat === "HUMAN_REVIEW" && !String(record(cfg.humanReview)?.description ?? "").trim()) errors.push(`HUMAN_REVIEW '${nodeTitle}' requires description`);
  }

  for (const node of nodes) for (const { selector, path } of selectors(node)) {
    const kind = String(selector[0]);
    if (kind === "SYSTEM" && selector.length < 3) errors.push(`${title(node)} ${path} SYSTEM selector must include category and field path`);
    if (["TOOL", "LLM", "CODE", "EXTRACT", "AGENT", "HUMAN_REVIEW", "NODE"].includes(kind)) {
      const sourceId = String(selector[1] ?? "");
      if (!nodeById.has(sourceId)) errors.push(`${title(node)} ${path} references missing ${kind} node '${sourceId}'`);
      else if (sourceId === String(node.id)) errors.push(`${title(node)} ${path} references itself`);
    }
    if (kind === "TOOL" && selector.slice(2).some(item => typeof item === "string" && item.includes("."))) errors.push(`${title(node)} ${path} nested TOOL fields must use separate path segments`);
  }

  return { valid: errors.length === 0, errors, warnings, nodeCount: nodes.length, edgeCount: edges.length, stats: { nodes: nodes.length, edges: edges.length } };
}
