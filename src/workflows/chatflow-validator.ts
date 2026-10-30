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
function isNote(node: JsonObject) { const data = record(node.data) ?? {}; return node.type === "CUSTOM_NOTE" || data.category === "NOTE"; }
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

const META_VARIABLE_NAMES = new Set([
  "current_user_message", "current_message_summary", "subject", "chat_id", "extern_id",
  "touch_point", "current_round", "current_request_start_time", "current_time", "bot_id",
  "flow_version", "is_test", "conversation_attachments",
]);
function flowVariableNames(root: JsonObject): Set<string> {
  const vars = Array.isArray(root.variables) ? root.variables : [];
  return new Set(vars.flatMap(item => {
    const value = record(item); const name = value?.name ?? value?.variableName;
    return typeof name === "string" ? [name] : [];
  }));
}

export function validateChatflowGraph(graph: unknown): GraphValidation {
  const errors: string[] = [], warnings: string[] = [], root = record(graph);
  if (!root) errors.push("graph must be a JSON object");
  const allNodes = Array.isArray(root?.nodes) ? root.nodes.filter(record) as JsonObject[] : [];
  const nodes = allNodes.filter(node => !isNote(node));
  const edges = Array.isArray(root?.edges) ? root.edges.filter(record) as JsonObject[] : [];
  if (!Array.isArray(root?.nodes)) errors.push("graph.nodes must be an array");
  if (!Array.isArray(root?.edges)) errors.push("graph.edges must be an array");
  // `variables` is optional in current frontend graphs; when present it must be an array.
  if (root && root.variables !== undefined && !Array.isArray(root.variables)) errors.push("graph.variables must be an array");
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
  const flowNames = root ? flowVariableNames(root) : new Set<string>();
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
    if (cat === "SUB_GRAPH") {
      const subGraph = record(cfg.subGraph) ?? {};
      const limit = subGraph.contextTurnLimit ?? 5;
      if (typeof limit !== "number" || !Number.isInteger(limit) || limit < 0 || limit > 10) errors.push(`SUB_GRAPH '${nodeTitle}' contextTurnLimit must be between 0 and 10`);
      if (!subGraph.targetAgentId) errors.push(`SUB_GRAPH '${nodeTitle}' missing targetAgentId`);
    }
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
    if (cat === "AGENT") {
      const data = record(cfg.agentData) ?? {};
      if (data.transferToHumans && Array.isArray(data.transferToHumans) && data.transferToHumans.length) warnings.push(`AGENT '${nodeTitle}' contains legacy transferToHumans; current frontend/runtime ignores it, use a TRANSFER_TO_HUMAN node`);
      const action = record(cfg.maxRoundsExceededAction)?.type;
      if (action && !["FORCE_NEXT_STEP", "TRANSFER_TO_HUMAN"].includes(String(action))) errors.push(`AGENT '${nodeTitle}' has unsupported maxRoundsExceededAction '${String(action)}'`);
      if (Array.isArray(data.usedPlugins)) {
        const seen = new Set<number>();
        for (const plugin of data.usedPlugins) if (Number.isInteger(plugin) && !Number.isNaN(plugin)) { if (seen.has(plugin)) warnings.push(`AGENT '${nodeTitle}' usedPlugins contains duplicate id ${plugin}`); seen.add(plugin); }
      }
    }
    if (cat === "REPLY" || cat === "TRANSFER_TO_HUMAN") {
      const content = cat === "REPLY" ? record(cfg.replyContent) ?? {} : record(cfg.transferToHuman) ?? {};
      const type = String(content.type ?? "").toUpperCase();
      if (type && type !== "PROMPT" && Array.isArray(content.aiFieldIds) && content.aiFieldIds.length) warnings.push(`${cat} '${nodeTitle}' ${type} ignores legacy aiFieldIds; resave it without aiFieldIds`);
    }
    if (cat === "HUMAN_REVIEW" && !String(record(cfg.humanReview)?.description ?? "").trim()) errors.push(`HUMAN_REVIEW '${nodeTitle}' requires description`);
  }

  for (const node of nodes) for (const { selector, path } of selectors(node)) {
    const kind = String(selector[0]);
    if (kind === "SYSTEM" && selector.length < 3) errors.push(`${title(node)} ${path} SYSTEM selector must include category and field path`);
    if (kind === "META" && (selector.length !== 2 || !META_VARIABLE_NAMES.has(String(selector[1])))) errors.push(`${title(node)} ${path} references unknown META variable '${String(selector[1])}'`);
    if (kind === "FLOW" && (selector.length !== 2 || !flowNames.has(String(selector[1])))) errors.push(`${title(node)} ${path} references unknown FLOW variable '${String(selector[1])}'`);
    if (["TOOL", "LLM", "CODE", "EXTRACT", "AGENT", "HUMAN_REVIEW", "NODE"].includes(kind)) {
      const sourceId = String(selector[1] ?? "");
      if (!nodeById.has(sourceId)) errors.push(`${title(node)} ${path} references missing ${kind} node '${sourceId}'`);
      else if (sourceId === String(node.id)) errors.push(`${title(node)} ${path} references itself`);
    }
    if (kind === "TOOL" && selector.slice(2).some(item => typeof item === "string" && item.includes("."))) errors.push(`${title(node)} ${path} nested TOOL fields must use separate path segments`);
  }

  // Assignment targets are writes: only SYSTEM and FLOW are valid destinations.
  for (const node of nodes) {
    const cfg = config(node), cat = category(node), assignments = cat === "VARIABLE_PROCESS" ? record(cfg.variableProcess)?.assignments : cat === "VARIABLE_ASSIGNMENT" ? cfg.variableAssignment : undefined;
    if (!Array.isArray(assignments)) continue;
    assignments.forEach((assignment, ai) => {
      const item = record(assignment); const targets = item?.target;
      if (!Array.isArray(targets)) return;
      targets.forEach((target, ti) => {
        if (!Array.isArray(target) || !["SYSTEM", "FLOW"].includes(String(target[0]))) errors.push(`${title(node)} assignments[${ai}].target[${ti}] must target SYSTEM or FLOW variable`);
        else if (target[0] === "FLOW" && (target.length !== 2 || !flowNames.has(String(target[1])))) errors.push(`${title(node)} assignments[${ai}].target[${ti}] references unknown FLOW variable '${String(target[1])}'`);
      });
    });
  }

  return { valid: errors.length === 0, errors, warnings, nodeCount: nodes.length, edgeCount: edges.length, stats: { nodes: nodes.length, edges: edges.length } };
}
