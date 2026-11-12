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
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : undefined;
}
function category(node: JsonObject) {
  return String(record(node.data)?.category ?? "");
}
function title(node: JsonObject) {
  return String(record(node.data)?.title ?? node.id ?? "");
}
function config(node: JsonObject) {
  return record(record(node.data)?.config) ?? {};
}
function isNoteNode(node: JsonObject) {
  return category(node) === "NOTE" || String(node.type ?? "") === "CUSTOM_NOTE";
}

function toolParamItems(plugin: JsonObject): JsonObject[] {
  const meta = record(plugin.meta) ?? plugin;
  const config = record(meta.externalHttpCallConfig) ?? meta;
  return flattenParamItems(record(config.requestParam)?.items);
}

function toolActionStatusNames(plugin: JsonObject): string[] {
  const meta = record(plugin.meta) ?? plugin;
  const configs = [meta, ...Object.values(meta).map(record).filter(Boolean)];
  for (const config of configs) {
    const statuses = config && Array.isArray(config.actionStatuses) ? config.actionStatuses : [];
    const names = statuses
      .map((status) => String(record(status)?.name ?? "").trim())
      .filter(Boolean);
    if (names.length) return names;
  }
  return [];
}

function flattenParamItems(value: unknown): JsonObject[] {
  return Array.isArray(value) ? (value.filter(record) as JsonObject[]) : [];
}

function configuredParam(value: JsonObject): boolean {
  return (
    (value.text !== undefined && value.text !== null) ||
    (value.value !== undefined && value.value !== null) ||
    (value.variableSelector !== undefined && value.variableSelector !== null) ||
    (value.selector !== undefined && value.selector !== null) ||
    (Array.isArray(value.children) && value.children.length > 0)
  );
}

/** Validate required TOOL inputs against the complete plugin request contract. */
export function validateToolParameters(graph: unknown, plugins: JsonObject[]): string[] {
  const root = record(graph);
  if (!root) return [];
  const byId = new Map(plugins.map((plugin) => [String(plugin.id ?? plugin.pluginId), plugin]));
  const errors: string[] = [];
  const nodes = Array.isArray(root.nodes) ? (root.nodes.filter(record) as JsonObject[]) : [];
  for (const node of nodes) {
    if (category(node) !== "TOOL") continue;
    const nodeConfig = config(node),
      tool = record(nodeConfig.tool) ?? {};
    const plugin = byId.get(String(tool.id ?? ""));
    if (!plugin) continue;
    const rawInputParams = Array.isArray(tool.inputParams)
      ? tool.inputParams
      : Array.isArray(nodeConfig.inputParams)
        ? nodeConfig.inputParams
        : [];
    const inputParams = rawInputParams.filter(record) as JsonObject[];
    const check = (definition: JsonObject, path: string, bindings: JsonObject[]) => {
      if (definition.required === false) return;
      const binding = bindings.find(
        (item) => String(item.name ?? "") === String(definition.name ?? ""),
      );
      const source = String(definition.source ?? "").toUpperCase();
      if (source === "CUSTOMIZE" && definition.value !== undefined && definition.value !== null)
        return;
      if (!binding || !configuredParam(binding)) {
        errors.push(`TOOL '${title(node)}' required tool param '${path}' is not configured`);
        return;
      }
      if (String(definition.type ?? "").toLowerCase() === "object") {
        const children = Array.isArray(definition.objectItems)
          ? (definition.objectItems.filter(record) as JsonObject[])
          : [];
        const boundChildren = Array.isArray(binding.children)
          ? (binding.children.filter(record) as JsonObject[])
          : [];
        children.forEach((child) =>
          check(child, `${path}.${String(child.name ?? "")}`, boundChildren),
        );
      }
    };
    toolParamItems(plugin).forEach((definition) =>
      check(definition, String(definition.name ?? ""), inputParams),
    );
  }
  return errors;
}

/** Compare TOOL status edges with current metadata without rejecting compatible old graphs. */
export function validateToolEdgeCompatibility(
  graph: unknown,
  plugins: JsonObject[],
): { errors: string[]; warnings: string[] } {
  const root = record(graph);
  if (!root) return { errors: [], warnings: [] };
  const byId = new Map(plugins.map((plugin) => [String(plugin.id ?? plugin.pluginId), plugin]));
  const nodes = Array.isArray(root.nodes) ? (root.nodes.filter(record) as JsonObject[]) : [];
  const edges = Array.isArray(root.edges) ? (root.edges.filter(record) as JsonObject[]) : [];
  const warnings: string[] = [];

  for (const node of nodes) {
    if (category(node) !== "TOOL") continue;
    const tool = record(config(node).tool) ?? {};
    if (tool.enableActionStatus !== true) continue;
    const plugin = byId.get(String(tool.id ?? ""));
    if (!plugin) continue;
    const expected = toolActionStatusNames(plugin);
    if (!expected.length) continue;
    const actual = new Set(
      edges
        .filter((edge) => String(edge.source ?? "") === String(node.id ?? ""))
        .map((edge) => String(edge.sourceHandle ?? "SOURCE")),
    );
    const missing = expected.filter((name) => !actual.has(name));
    const unknown = [...actual].filter(
      (handle) => handle !== "SOURCE" && !expected.includes(handle),
    );
    if (missing.length)
      warnings.push(
        `TOOL '${title(node)}' has no edge for current action status(es): ${missing.join(", ")}`,
      );
    if (unknown.length)
      warnings.push(
        `TOOL '${title(node)}' keeps legacy or unknown action status edge(s): ${unknown.join(", ")}`,
      );
  }

  return { errors: [], warnings };
}
function containsCycle(ids: Set<string>, edges: JsonObject[]) {
  const outgoing = new Map<string, string[]>();
  for (const edge of edges)
    outgoing.set(String(edge.source), [
      ...(outgoing.get(String(edge.source)) ?? []),
      String(edge.target),
    ]);
  const visiting = new Set<string>(),
    visited = new Set<string>();
  const visit = (id: string): boolean => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    for (const next of outgoing.get(id) ?? []) if (ids.has(next) && visit(next)) return true;
    visiting.delete(id);
    visited.add(id);
    return false;
  };
  return [...ids].some(visit);
}
function selectors(
  value: unknown,
  path = "root",
  out: Array<{ selector: unknown[]; path: string }> = [],
) {
  if (Array.isArray(value)) {
    if (
      [
        "SYSTEM",
        "TOOL",
        "NODE",
        "EXTRACT",
        "CODE",
        "LLM",
        "AGENT",
        "HUMAN_REVIEW",
        "SELF",
        "FLOW",
        "META",
      ].includes(String(value[0]))
    )
      out.push({ selector: value, path });
    else value.forEach((item, index) => selectors(item, `${path}[${index}]`, out));
  } else if (value && typeof value === "object")
    for (const [key, child] of Object.entries(value)) selectors(child, `${path}.${key}`, out);
  return out;
}

export function validateChatflowGraph(graph: unknown): GraphValidation {
  const errors: string[] = [],
    warnings: string[] = [],
    root = record(graph);
  if (!root) errors.push("graph must be a JSON object");
  const nodes = Array.isArray(root?.nodes) ? (root.nodes.filter(record) as JsonObject[]) : [];
  const edges = Array.isArray(root?.edges) ? (root.edges.filter(record) as JsonObject[]) : [];
  if (!Array.isArray(root?.nodes)) errors.push("graph.nodes must be an array");
  if (!Array.isArray(root?.edges)) errors.push("graph.edges must be an array");
  if (root && root.variables !== undefined && !Array.isArray(root.variables))
    errors.push("graph.variables must be an array");
  if (!nodes.length) errors.push("Graph has no nodes");

  const ids = new Set<string>(),
    nodeById = new Map<string, JsonObject>();
  nodes.forEach((node, index) => {
    const id = typeof node.id === "string" ? node.id.trim() : "";
    if (!id) errors.push(`nodes[${index}] is missing id`);
    else if (ids.has(id)) errors.push(`duplicate node id: ${id}`);
    else {
      ids.add(id);
      nodeById.set(id, node);
    }
    if (!category(node)) errors.push(`nodes[${index}] is missing data.category`);
  });

  const edgeIds = new Set<string>();
  const required = ["id", "source", "sourceHandle", "target", "targetHandle", "type"];
  edges.forEach((edge, index) => {
    for (const field of required)
      if (
        edge[field] === undefined ||
        edge[field] === null ||
        (typeof edge[field] === "string" && !edge[field].trim())
      )
        if (
          field !== "sourceHandle" ||
          category(nodeById.get(String(edge.source ?? "")) ?? {}) !== "TOOL"
        )
          errors.push(`edge[${index}] missing ${field}`);
    const id = String(edge.id ?? "");
    if (id && edgeIds.has(id)) errors.push(`duplicate edge id '${id}'`);
    else if (id) edgeIds.add(id);
    if (edge.type !== undefined && edge.type !== "default")
      errors.push(`edge[${index}] unsupported type '${String(edge.type)}'; expected 'default'`);
    const from = String(edge.source ?? ""),
      to = String(edge.target ?? "");
    if (from && !ids.has(from))
      errors.push(`Edge ${id || `edge[${index}]`}: source '${from}' not in nodes`);
    if (to && !ids.has(to))
      errors.push(`Edge ${id || `edge[${index}]`}: target '${to}' not in nodes`);
  });

  const runtimeNodes = nodes.filter((node) => !isNoteNode(node));
  const runtimeIds = new Set(runtimeNodes.map((node) => String(node.id)));
  const runtimeEdges = edges.filter(
    (edge) => runtimeIds.has(String(edge.source)) && runtimeIds.has(String(edge.target)),
  );
  const runtimeOutgoing = new Map<string, JsonObject[]>(),
    runtimeIncoming = new Map<string, JsonObject[]>();
  for (const edge of runtimeEdges) {
    const from = String(edge.source),
      to = String(edge.target);
    runtimeOutgoing.set(from, [...(runtimeOutgoing.get(from) ?? []), edge]);
    runtimeIncoming.set(to, [...(runtimeIncoming.get(to) ?? []), edge]);
  }

  const starts = runtimeNodes.filter((node) => category(node) === "START");
  if (!starts.length) errors.push("Missing START node");
  else if (starts.length > 1)
    errors.push(`Multiple START nodes found: ${starts.map((node) => node.id).join(", ")}`);
  if (starts.length === 1 && !runtimeOutgoing.get(String(starts[0].id))?.length)
    errors.push(`START node '${String(starts[0].id)}' has no outgoing edge`);

  if (starts.length === 1) {
    const reachable = new Set<string>(),
      queue = [String(starts[0].id)];
    while (queue.length) {
      const id = queue.shift()!;
      if (reachable.has(id)) continue;
      reachable.add(id);
      for (const edge of runtimeOutgoing.get(id) ?? []) queue.push(String(edge.target));
    }
    const orphan = [...runtimeIds].filter((id) => !reachable.has(id));
    if (orphan.length)
      errors.push(
        `Orphan nodes not reachable from START: ${orphan.map((id) => `${id}(${category(nodeById.get(id)!)})`).join(", ")}`,
      );
  }
  if (containsCycle(runtimeIds, runtimeEdges)) errors.push("Graph contains a cycle");

  const seenTitles = new Set<string>();
  for (const node of runtimeNodes) {
    const cat = category(node),
      id = String(node.id),
      nodeTitle = title(node),
      cfg = config(node),
      handles = new Set(
        (runtimeOutgoing.get(id) ?? []).map((edge) => String(edge.sourceHandle ?? "SOURCE")),
      );
    if (cat !== "START") {
      if (!nodeTitle.trim()) errors.push(`Node '${id}' (${cat}) has empty title`);
      else if (seenTitles.has(nodeTitle)) errors.push(`Duplicate node title: '${nodeTitle}'`);
      else seenTitles.add(nodeTitle);
      if (!runtimeIncoming.get(id)?.length)
        warnings.push(`Node '${id}' (${cat}) has no incoming edge`);
    }
    const requireOutgoing = ![
      "AGENT",
      "FINISH",
      "REPLY",
      "SUB_GRAPH",
      "TRANSFER_TO_HUMAN",
    ].includes(cat);
    if (requireOutgoing && !runtimeOutgoing.get(id)?.length)
      errors.push(`${cat} '${nodeTitle}' has no outgoing edge`);
    if (
      ["FINISH", "SUB_GRAPH", "TRANSFER_TO_HUMAN"].includes(cat) &&
      runtimeOutgoing.get(id)?.length
    )
      errors.push(`${cat} '${nodeTitle}' must not have outgoing edges`);
    const requireHandles = (expected: string[]) =>
      expected.forEach((handle) => {
        if (!handles.has(handle)) errors.push(`${cat} '${nodeTitle}' missing ${handle} edge`);
      });
    if (cat === "REPLY") {
      const replyEdges = runtimeOutgoing.get(id) ?? [];
      if (replyEdges.length > 1)
        errors.push(`REPLY '${nodeTitle}' must have at most one outgoing edge`);
      if (replyEdges.length) requireHandles(["SOURCE"]);
    } else if (cat === "QUESTION") {
      const info = record(cfg.collectInfo) ?? {};
      if (info.type === "USER_REPLY")
        requireHandles([
          ...(Array.isArray(info.replies)
            ? info.replies.map((item) => String(record(item)?.id ?? ""))
            : []),
          "OTHER",
        ]);
      else requireHandles(["SOURCE"]);
    } else if (cat === "INTENT")
      requireHandles([
        ...(Array.isArray(cfg.intents)
          ? cfg.intents.map((item) => String(record(item)?.id ?? ""))
          : []),
        "OTHER",
      ]);
    else if (cat === "IF_ELSE")
      requireHandles([
        ...(Array.isArray(cfg.cases)
          ? cfg.cases.map((item) => String(record(item)?.id ?? ""))
          : []),
        "FALSE",
      ]);
    else if (cat === "RAG_REPLY") requireHandles(["TRUE", "LACK_KNOWLEDGE"]);
    else if (cat === "KNOWLEDGE_REPLY") requireHandles(["RESOLVED", "UNRESOLVED"]);
    else if (cat === "HUMAN_REVIEW") {
      const review = record(cfg.humanReview) ?? record(cfg.humanInLoop) ?? {};
      const required = review.method === "fill" ? ["SOURCE"] : ["AGREE", "REJECT"];
      if (review.midwayMessageStrategy === "handle") required.push("MESSAGE");
      requireHandles(required);
    } else if (cat === "TOOL") {
      const tool = record(cfg.tool) ?? {};
      if (tool.enableActionStatus === true) {
        if (![...handles].some((handle) => handle !== "SOURCE"))
          errors.push(`TOOL '${nodeTitle}' has no action-status outbound edge`);
      } else if (!handles.has("SOURCE")) errors.push(`TOOL '${nodeTitle}' missing SOURCE edge`);
    } else if (cat === "AGENT") {
      const data = record(cfg.agentData) ?? {};
      if (!String(data.prompt ?? "").trim()) errors.push(`AGENT node '${id}' has empty prompt`);
      if (!String(data.displayPrompt ?? "").trim())
        errors.push(`AGENT node '${id}' has empty displayPrompt`);
      const steps = Array.isArray(cfg.nextStep) ? cfg.nextStep : [];
      const stepIds = new Set(
        steps.map((step) => String(record(step)?.id ?? "").trim()).filter(Boolean),
      );
      if (steps.length) requireHandles(steps.map((step) => String(record(step)?.id ?? "")));
      else if (!handles.has("SOURCE"))
        warnings.push(
          `AGENT '${nodeTitle}' has no SOURCE outbound edge — confirm it's a terminal node`,
        );
      for (const edge of runtimeOutgoing.get(id) ?? []) {
        const target = nodeById.get(String(edge.target));
        if (
          target &&
          category(target) === "TRANSFER_TO_HUMAN" &&
          !stepIds.has(String(edge.sourceHandle))
        )
          errors.push(
            `AGENT '${nodeTitle}' must reach TRANSFER_TO_HUMAN through a declared handoff nextStep`,
          );
      }
      if (
        data.usedPlugins !== undefined &&
        (!Array.isArray(data.usedPlugins) ||
          data.usedPlugins.some((item) => !Number.isInteger(item) || typeof item === "boolean"))
      )
        errors.push(`AGENT '${nodeTitle}' usedPlugins must contain integer ids`);
      if (
        data.enableKnowledgeBase &&
        !(Array.isArray(data.usedPlugins) ? data.usedPlugins : []).includes(-3)
      )
        errors.push(
          `AGENT '${nodeTitle}' enables knowledge base but is missing KNOWLEDGE_AI_REPLY plugin -3`,
        );
    } else if (requireOutgoing) requireHandles(["SOURCE"]);

    if (cat === "CODE") {
      const code = record(cfg.code) ?? {},
        outputs = code.outputs;
      if (!Array.isArray(outputs) || !outputs.length)
        errors.push(`CODE '${nodeTitle}' must declare at least one output`);
      const source = String(code.sourceCode ?? "");
      if (
        /\b(import|from)\s+(os|sys|subprocess|socket|pathlib|shutil|requests)\b/.test(source) ||
        /\b(eval|exec|compile|__import__|open)\s*\(/.test(source) ||
        /__(class|mro|bases|subclasses|globals|dict|builtins|import)__/.test(source)
      )
        errors.push(`CODE '${nodeTitle}' contains forbidden Python operations`);
    }
    if (
      cat === "HUMAN_REVIEW" &&
      !String((record(cfg.humanReview) ?? record(cfg.humanInLoop))?.description ?? "").trim()
    )
      errors.push(`HUMAN_REVIEW '${nodeTitle}' requires description`);
  }

  for (const node of nodes)
    for (const { selector, path } of selectors(node)) {
      const kind = String(selector[0]);
      if (kind === "SYSTEM" && selector.length < 3)
        errors.push(`${title(node)} ${path} SYSTEM selector must include category and field path`);
      if (["TOOL", "LLM", "CODE", "EXTRACT", "AGENT", "HUMAN_REVIEW", "NODE"].includes(kind)) {
        const sourceId = String(selector[1] ?? "");
        if (!nodeById.has(sourceId))
          errors.push(`${title(node)} ${path} references missing ${kind} node '${sourceId}'`);
        else if (sourceId === String(node.id))
          errors.push(`${title(node)} ${path} references itself`);
      }
      if (
        kind === "TOOL" &&
        selector.slice(2).some((item) => typeof item === "string" && item.includes("."))
      )
        errors.push(`${title(node)} ${path} nested TOOL fields must use separate path segments`);
    }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    nodeCount: nodes.length,
    edgeCount: edges.length,
    stats: { nodes: nodes.length, edges: edges.length },
  };
}
