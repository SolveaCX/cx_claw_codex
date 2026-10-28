import { randomUUID } from "node:crypto";
import { validateChatflowGraph } from "./chatflow-validator.js";

export type JsonObject = Record<string, unknown>;
type Point = { x: number; y: number };

const TYPE_ALIASES: Record<string, string> = {
  start: "START", finish: "FINISH", reply: "REPLY", llm: "LLM", model: "LLM", agent: "AGENT",
  if_else: "IF_ELSE", ifelse: "IF_ELSE", tool: "TOOL", question: "QUESTION",
  collect_order: "COLLECT_ORDER", collectorder: "COLLECT_ORDER", transfer: "TRANSFER_TO_HUMAN",
  transfer_to_human: "TRANSFER_TO_HUMAN", human_review: "HUMAN_REVIEW", humanreview: "HUMAN_REVIEW",
  intent: "INTENT", knowledge_reply: "KNOWLEDGE_REPLY", knowledge: "RAG_REPLY", rag_reply: "RAG_REPLY",
  rag: "RAG_REPLY", variable_extract: "VARIABLE_EXTRACT", variableextract: "VARIABLE_EXTRACT",
  variable_assignment: "VARIABLE_ASSIGNMENT", variableassignment: "VARIABLE_ASSIGNMENT",
  variable_process: "VARIABLE_PROCESS", variableprocess: "VARIABLE_PROCESS", code: "CODE",
  sub_graph: "SUB_GRAPH", subgraph: "SUB_GRAPH", business_track: "BUSINESS_TRACK", businesstrack: "BUSINESS_TRACK",
};
const SPECIAL_KEYS = new Set(["$start", "$finish", "$transfer"]);

function object(value: unknown, message: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as JsonObject;
}
function array(value: unknown, message: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(message);
  return value;
}
function text(value: unknown, message: string): string {
  const result = String(value ?? "").trim();
  if (!result) throw new Error(message);
  return result;
}
function sourceGet(source: JsonObject, ...names: string[]) {
  for (const name of names) if (source[name] !== undefined && source[name] !== null) return source[name];
  return undefined;
}
function cleanTitle(value: unknown) {
  const original = String(value ?? "");
  const cleaned = original.replace(/[^\p{L}\p{N}_-]/gu, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  return cleaned || `Node_${randomUUID().slice(0, 8)}`;
}
function integerIds(value: unknown, field: string): number[] {
  if (value === undefined || value === null) return [];
  return array(value, `${field} must be an array`).map((item, index) => {
    if (typeof item === "boolean" || !Number.isSafeInteger(Number(item))) throw new Error(`${field}[${index}] must be an integer id`);
    return Number(item);
  });
}
function nonEmptyString(value: unknown, message: string) {
  if (typeof value !== "string" || !value.trim()) throw new Error(message);
  return value;
}
function position(source: JsonObject, index: number): Point {
  const raw = source.position;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const p = raw as JsonObject; return { x: Number(p.x ?? 0), y: Number(p.y ?? 0) };
  }
  if (Array.isArray(raw) && raw.length >= 2) return { x: Number(raw[0]), y: Number(raw[1]) };
  return { x: (index % 5) * 320, y: Math.floor(index / 5) * 180 };
}
function graphNode(category: string, title: string | undefined, config: JsonObject | undefined, at: Point, extra: JsonObject = {}) {
  return { id: randomUUID(), type: "CUSTOM", data: { category, ...(title === undefined ? {} : { title: cleanTitle(title) }), ...(config === undefined ? {} : { config }), ...extra }, position: at } as JsonObject;
}
function deepMerge(target: JsonObject, patch: JsonObject) {
  for (const [key, value] of Object.entries(patch)) {
    if (value && typeof value === "object" && !Array.isArray(value) && target[key] && typeof target[key] === "object" && !Array.isArray(target[key])) deepMerge(target[key] as JsonObject, value as JsonObject);
    else target[key] = structuredClone(value);
  }
  return target;
}
function applyOverrides(compiled: JsonObject, source: JsonObject) {
  if (source.node_id !== undefined) compiled.id = String(source.node_id);
  if (source.id !== undefined && source.preserve_id) compiled.id = String(source.id);
  const data = compiled.data as JsonObject;
  if (source.data && typeof source.data === "object" && !Array.isArray(source.data)) deepMerge(data, source.data as JsonObject);
  if (source.config && typeof source.config === "object" && !Array.isArray(source.config)) deepMerge((data.config ??= {}) as JsonObject, source.config as JsonObject);
  if (source.extra && typeof source.extra === "object" && !Array.isArray(source.extra)) deepMerge(compiled, source.extra as JsonObject);
  return compiled;
}
function sourceType(source: JsonObject) {
  const raw = source.type ?? source.category;
  if (!raw) throw new Error(`source node missing type/category: ${JSON.stringify(source)}`);
  const key = String(raw).trim().toLowerCase().replace(/-/g, "_");
  return TYPE_ALIASES[key] ?? String(raw).trim().toUpperCase();
}
function sourceKey(source: JsonObject, index: number) { return String(source.key ?? source.name ?? source.title ?? `node_${index}`); }
function sourceTitle(source: JsonObject, key: string) { return String(source.title ?? source.name ?? key); }
function itemIdName(value: unknown, fallback: string): [string, string] {
  if (typeof value === "string") return [cleanTitle(value), value];
  const item = object(value, "branch item must be a string or object");
  const name = String(item.name ?? item.title ?? item.id ?? fallback);
  return [String(item.id ?? cleanTitle(name)), name];
}
function branchLookup(map: Map<string, string>, key: string, label: unknown, handle: unknown) {
  for (const candidate of new Set([String(label), String(handle), cleanTitle(label), cleanTitle(handle)])) map.set(`${key}\0${candidate}`, String(handle));
}
function normalizeReplies(value: unknown, branches: Map<string, string>, key: string) {
  return array(value ?? [], `${key}.replies must be an array`).map((raw, index) => {
    const [id, name] = itemIdName(raw, `reply_${index}`); branchLookup(branches, key, name, id); return { id, name: cleanTitle(name) };
  });
}
function normalizeIntents(value: unknown, branches: Map<string, string>, key: string) {
  return array(value ?? [], `${key}.intents must be an array`).map((raw, index) => {
    const [id, name] = itemIdName(raw, `intent_${index}`);
    const entry: JsonObject = typeof raw === "string" ? { id, name, desc: "" } : { ...object(raw, "intent must be an object"), id, name };
    if (entry.intentId === undefined && !String(entry.desc ?? "").trim()) throw new Error(`intent '${name}' in node '${key}' missing desc`);
    branchLookup(branches, key, name, id);
    return { id, name: cleanTitle(name), desc: entry.desc ?? "", intentId: entry.intentId ?? null, examples: entry.examples ?? [] };
  });
}
function normalizeCases(value: unknown, branches: Map<string, string>, key: string) {
  return array(value ?? [], `${key}.cases must be an array`).map((raw, index) => {
    const [id, name] = itemIdName(raw, `case_${index}`);
    const entry: JsonObject = typeof raw === "string" ? { id, name, conditions: [] } : { ...object(raw, "case must be an object"), id };
    branchLookup(branches, key, entry.name ?? id, id);
    const conditions = array(entry.conditions ?? [], `${key}.conditions must be an array`).map(rawCondition => {
      const condition: JsonObject = { varType: "string", ...object(rawCondition, "condition must be an object") }; condition.id ??= randomUUID(); return condition;
    });
    return { id, logicalOperator: entry.logicalOperator ?? "AND", conditions };
  });
}
function normalizeNextSteps(value: unknown, branches: Map<string, string>, key: string) {
  return array(value ?? [], `${key}.next_steps must be an array`).map(raw => {
    if (typeof raw === "string") throw new Error(`AGENT '${key}' next_steps item '${raw}' must be an object with id/title/prompt`);
    const item = object(raw, "next step must be an object"), stepTitle = String(item.title ?? item.name ?? item.id ?? "Step");
    const entry = { ...item, id: String(item.id ?? cleanTitle(stepTitle)), title: stepTitle }; branchLookup(branches, key, stepTitle, entry.id); return entry;
  });
}
function normalizeExtracts(value: unknown) {
  const aliases = new Map<string, string>();
  const items = array(value ?? [], "extracts must be an array").map(raw => {
    const entry = { ...object(raw, "extract must be an object") }, alias = entry.alias ?? entry.key ?? entry.id;
    entry.id = entry.graph_id ?? entry.graphId ?? randomUUID(); if (alias) aliases.set(String(alias), String(entry.id)); return entry;
  });
  return { items, aliases };
}
function normalizeAssignment(raw: unknown) {
  const item = object(raw, "assignment must be an object");
  return { id: item.id ?? randomUUID(), operation: item.operation ?? "OVER_WRITE", source: item.source ?? item.variableSelector ?? item.value, target: item.target ?? item.targets ?? [], forceOverride: item.forceOverride ?? item.force_override ?? false };
}

type LibraryBlock = { raw: string; type: string; fields: Record<string, string> };
function libraryBlocks(prompt: unknown): LibraryBlock[] {
  if (!prompt) return [];
  if (typeof prompt !== "string") throw new Error("AGENT prompt must be a string");
  const blocks: LibraryBlock[] = [], pattern = /\{#LibraryBlock\s+(.+?)\s*#\}/g;
  for (const match of prompt.matchAll(pattern)) {
    const fields: Record<string, string> = {};
    const attrs = [...match[1].matchAll(/(?:^|\s+)([A-Za-z_]\w*)=/g)];
    if (!attrs.length || match[1].slice(0, attrs[0].index).trim()) throw new Error("invalid LibraryBlock attributes; expected key=value");
    attrs.forEach((attr, index) => {
      const key = attr[1];
      if (fields[key] !== undefined) throw new Error(`invalid or duplicate LibraryBlock attribute '${key}'`);
      let value = match[1].slice((attr.index ?? 0) + attr[0].length, index + 1 < attrs.length ? attrs[index + 1].index : undefined).trim();
      if (value.startsWith('"') || value.endsWith('"')) {
        if (value.length < 2 || !value.startsWith('"') || !value.endsWith('"')) throw new Error(`invalid quoted LibraryBlock attribute '${key}'`);
        value = value.slice(1, -1);
      }
      fields[key] = value;
    });
    const type = fields.type;
    if (type === "variable") {
      if (!fields.id || !fields.name || !/^\d+$/.test(fields.id) || Number(fields.id) <= 0 || !blockName(fields)) throw new Error("variable LibraryBlock requires a positive field id and non-empty name");
    } else if (["flowVariable", "systemVariable"].includes(type)) {
      if (!fields.name || !blockName(fields)) throw new Error(`${type} LibraryBlock requires a decodable non-empty name`);
    } else if (type === "contextVariable") {
      if (!fields.selector || !fields.name || !blockName(fields)) throw new Error("contextVariable LibraryBlock requires selector/name");
      try { canonicalContextVariable(JSON.parse(decodeURIComponent(fields.selector))); } catch { throw new Error("contextVariable LibraryBlock has invalid selector"); }
    } else if (type === "tool") {
      if (!fields.id || !fields.name || !fields.tool || !/^-?\d+$/.test(fields.id) || Number(fields.id) === 0) throw new Error("tool LibraryBlock requires id/type/name/tool with a non-zero integer id");
      if (fields.tool === "template_reply" && Number(fields.id) < 0) throw new Error("template_reply LibraryBlock requires a positive template content id");
    } else if (type === "transferHuman") {
      if (!fields.tool_id || !fields.name || !/^\d+$/.test(fields.tool_id) || Number(fields.tool_id) <= 0) throw new Error("transferHuman LibraryBlock requires a positive numeric tool_id and non-empty name");
      if (fields.action && !["NOT_REPLY", "CUSTOM_REPLY", "TEMPLATE_REPLY"].includes(fields.action)) throw new Error("transferHuman LibraryBlock has an unsupported action");
      if (fields.templateId && (!/^\d+$/.test(fields.templateId) || Number(fields.templateId) <= 0)) throw new Error("transferHuman LibraryBlock templateId must be a positive integer");
    } else throw new Error(`unsupported LibraryBlock type '${type}'`);
    blocks.push({ raw: match[0], type, fields });
  }
  if ((prompt.match(/\{#LibraryBlock/g) ?? []).length !== blocks.length) throw new Error("AGENT prompt contains an incomplete LibraryBlock");
  const transferIds = blocks.filter(block => block.type === "transferHuman").map(block => block.fields.tool_id);
  if (new Set(transferIds).size !== transferIds.length) throw new Error("transferHuman LibraryBlock tool_id must be unique within one AGENT prompt");
  return blocks;
}
function blockName(fields: Record<string, string>) { try { return fields.nameEncoded === "true" ? decodeURIComponent(fields.name ?? "") : fields.name; } catch { return undefined; } }
function canonicalContextVariable(value: unknown): unknown[] {
  const selector = array(value, "context variable must be a non-empty selector array");
  if (!selector.length || selector.some(item => typeof item !== "string" && (!Number.isInteger(item) || typeof item === "boolean"))) throw new Error("context variable selector items must be strings or integers");
  if (selector[0] === "SYSTEM") {
    if (![3, 4].includes(selector.length) || selector.slice(2).some(item => !Number.isInteger(item) || typeof item === "boolean")) throw new Error("SYSTEM context variable must contain one or two numeric field ids");
    return ["SYSTEM", "Custom", ...selector.slice(2)];
  }
  if (selector.length < 2) throw new Error("context variable selector must contain at least two items");
  return [...selector];
}
function blockSelector(block: LibraryBlock): unknown[] | undefined {
  const f = block.fields;
  if (block.type === "variable") return ["SYSTEM", "Custom", Number(f.id)];
  if (block.type === "flowVariable") return ["FLOW", blockName(f)];
  if (block.type === "systemVariable") return ["META", blockName(f)];
  if (block.type === "contextVariable") return canonicalContextVariable(JSON.parse(decodeURIComponent(f.selector)));
  return undefined;
}
function formatAgentPrompt(prompt: string) {
  let result = prompt;
  for (const block of libraryBlocks(prompt)) {
    const f = block.fields;
    const replacement = ["variable", "flowVariable", "systemVariable", "contextVariable"].includes(block.type) ? ` ${blockName(f) ?? ""} `
      : block.type === "tool" ? (f.tool === "template_reply" ? ` template_reply tool (template id: ${f.id ?? ""})` : `${f.name ?? ""} tool `)
      : block.type === "transferHuman" ? ` Transfer_To_Agent (reason: ${f.name ?? ""}) ` : "";
    result = result.replace(block.raw, replacement);
  }
  return result;
}

function compileNode(source: JsonObject, index: number, key: string, branches: Map<string, string>) {
  const at = position(source, index);
  if (source.node && typeof source.node === "object" && !Array.isArray(source.node)) {
    const raw = structuredClone(source.node) as JsonObject; raw.id ??= randomUUID(); raw.type ??= "CUSTOM"; raw.position ??= at; return applyOverrides(raw, source);
  }
  const kind = sourceType(source), name = sourceTitle(source, key);
  let compiled: JsonObject;
  if (kind === "START") compiled = graphNode("START", undefined, undefined, at);
  else if (kind === "FINISH") compiled = graphNode("FINISH", name, {}, at);
  else if (kind === "REPLY") {
    const replyType = String(sourceGet(source, "reply_type", "replyType", "type_value") ?? "PROMPT").toUpperCase();
    const prompt = sourceGet(source, "prompt", "text", "message") ?? "", templateId = sourceGet(source, "template_id", "templateId"), templateContent = sourceGet(source, "template_content", "templateContent");
    if (!new Set(["PROMPT", "TEMPLATE", "DYNAMIC_TEMPLATE"]).has(replyType)) throw new Error(`unsupported REPLY type: ${replyType}`);
    if (replyType === "TEMPLATE" && !templateId) throw new Error("REPLY type TEMPLATE requires template_id");
    if (replyType === "DYNAMIC_TEMPLATE" && !String(templateContent ?? "").trim()) throw new Error("REPLY type DYNAMIC_TEMPLATE requires non-empty template_content");
    if (replyType !== "PROMPT" && integerIds(sourceGet(source, "ai_field_ids", "aiFieldIds"), "ai_field_ids").length) throw new Error(`REPLY type ${replyType} does not use ai_field_ids`);
    compiled = graphNode("REPLY", name, { replyContent: { type: replyType, prompt: replyType === "PROMPT" ? prompt : null, templateId: replyType === "TEMPLATE" ? templateId : null, templateContent: replyType === "DYNAMIC_TEMPLATE" ? templateContent : null, aiFieldIds: replyType === "PROMPT" ? integerIds(sourceGet(source, "ai_field_ids", "aiFieldIds"), "ai_field_ids") : null }, useLongMemory: Boolean(sourceGet(source, "use_long_memory", "useLongMemory") ?? false), disablePrevNodeResult: Boolean(sourceGet(source, "disable_prev_node_results", "disablePrevNodeResult") ?? false) }, at);
  } else if (kind === "AGENT") {
    const prompt = String(source.prompt ?? ""), blocks = libraryBlocks(prompt), plugins = [...new Set(integerIds(sourceGet(source, "plugins", "usedPlugins"), "plugins"))];
    for (const block of blocks) if (block.type === "tool" && block.fields.tool !== "template_reply") { const id = Number(block.fields.id); if (!plugins.includes(id)) plugins.push(id); }
    let contextVariables = sourceGet(source, "context_variables", "contextVariables") as unknown[] | undefined;
    if (!contextVariables) contextVariables = integerIds(sourceGet(source, "ai_field_ids", "aiFieldIds"), "ai_field_ids").map(id => ["SYSTEM", "Custom", id]);
    else contextVariables = array(contextVariables, "context_variables must be an array").map(canonicalContextVariable);
    for (const block of blocks) { const selector = blockSelector(block); if (selector && !contextVariables.some(value => JSON.stringify(value) === JSON.stringify(selector))) contextVariables.push(selector); }
    const enableKnowledgeBase = Boolean(sourceGet(source, "enable_kb", "enableKnowledgeBase") ?? false) || blocks.some(block => block.type === "tool" && block.fields.tool !== "template_reply" && Number(block.fields.id) === -3);
    if (enableKnowledgeBase && !plugins.includes(-3)) plugins.push(-3);
    const actionRaw = sourceGet(source, "max_rounds_exceeded_action", "maxRoundsExceededAction") ?? "TRANSFER_TO_HUMAN";
    const action = String(typeof actionRaw === "object" ? (actionRaw as JsonObject).type : actionRaw).toUpperCase();
    if (!new Set(["FORCE_NEXT_STEP", "TRANSFER_TO_HUMAN"]).has(action)) throw new Error("AGENT max_rounds_exceeded_action must be FORCE_NEXT_STEP or TRANSFER_TO_HUMAN");
    const nextStep = normalizeNextSteps(sourceGet(source, "next_steps", "nextStep"), branches, key);
    const agentData: JsonObject = { prompt: formatAgentPrompt(prompt), displayPrompt: prompt, usedPlugins: plugins, contextVariables, enableKnowledgeBase, knowledgeDirectoryIds: sourceGet(source, "kb_dirs", "knowledgeDirectoryIds") ?? [], transferToHumans: [] };
    if (sourceGet(source, "knowledge_keyword_ids", "knowledgeKeywordIds") !== undefined) agentData.knowledgeKeywordIds = sourceGet(source, "knowledge_keyword_ids", "knowledgeKeywordIds");
    if (sourceGet(source, "knowledge_keyword_selector", "knowledgeKeywordSelector") !== undefined) agentData.knowledgeKeywordSelector = sourceGet(source, "knowledge_keyword_selector", "knowledgeKeywordSelector");
    compiled = graphNode("AGENT", name, { maxRounds: sourceGet(source, "max_rounds", "maxRounds") ?? 10, maxRoundsExceededAction: { type: action }, useLongMemory: Boolean(sourceGet(source, "use_long_memory", "useLongMemory") ?? false), disablePrevNodeResult: Boolean(sourceGet(source, "disable_prev_node_results", "disablePrevNodeResult") ?? false), agentData, ...(nextStep.length ? { nextStep } : {}) }, at, { version: 2 });
  } else if (kind === "LLM") {
    const unsupported = ["ai_field_ids", "aiFieldIds", "model_id", "modelId", "outputs", "output_variables", "outputVariables"].filter(field => field in source);
    if (unsupported.length) throw new Error(`LLM source fields are no longer supported by the current ChatFlow runtime: ${unsupported.join(", ")}`);
    const vision = object(source.vision ?? {}, "LLM vision must be an object"), structured = object(sourceGet(source, "structured_output", "structuredOutput") ?? {}, "LLM structured_output must be an object");
    const historyRoundLimit = Number(sourceGet(source, "history_round_limit", "historyRoundLimit") ?? 0);
    if (!Number.isInteger(historyRoundLimit) || historyRoundLimit < -1) throw new Error("LLM history_round_limit must be -1, 0, or a positive integer");
    const visionDetail = vision.detail ?? "auto", mediaSelectors = vision.media_selectors ?? vision.mediaSelectors ?? [];
    if (!["auto", "low", "high"].includes(String(visionDetail))) throw new Error("LLM vision.detail must be auto, low, or high");
    if (!Array.isArray(mediaSelectors)) throw new Error("LLM vision.media_selectors must be a list");
    if (vision.enabled && !mediaSelectors.length) throw new Error("LLM vision.enabled requires media_selectors");
    const structuredSchema = structured.schema ?? {};
    if (!structuredSchema || typeof structuredSchema !== "object" || Array.isArray(structuredSchema)) throw new Error("LLM structured_output.schema must be an object");
    if (structured.enabled && ((structuredSchema as JsonObject).type !== "object" || !(structuredSchema as JsonObject).properties || typeof (structuredSchema as JsonObject).properties !== "object" || Array.isArray((structuredSchema as JsonObject).properties))) throw new Error("LLM structured_output.enabled requires an object-rooted JSON Schema with properties");
    if (structured.enabled && "required" in (structuredSchema as JsonObject) && !Array.isArray((structuredSchema as JsonObject).required)) throw new Error("LLM structured_output.schema.required must be a list");
    compiled = graphNode("LLM", name, { historyRoundLimit, useLongMemory: Boolean(sourceGet(source, "use_long_memory", "useLongMemory") ?? false), llm: { promptTemplate: source.prompt ?? "", vision: { enabled: Boolean(vision.enabled ?? false), detail: visionDetail, mediaSelectors }, structuredOutput: { enabled: Boolean(structured.enabled ?? false), schema: structuredSchema } } }, at);
  } else if (kind === "IF_ELSE") compiled = graphNode("IF_ELSE", name, { cases: normalizeCases(source.cases, branches, key) }, at);
  else if (kind === "TOOL") {
    const tool = source.tool && typeof source.tool === "object" && !Array.isArray(source.tool) ? source.tool as JsonObject : {};
    const id = sourceGet(source, "tool_id", "toolId") ?? tool.id; if (id === undefined) throw new Error(`TOOL node '${key}' missing tool_id`);
    const toolType = sourceGet(source, "tool_type", "toolType") ?? tool.type ?? "EXTERNAL_HTTP_CALL"; nonEmptyString(toolType, "TOOL tool_type must be a non-empty plugin type");
    compiled = graphNode("TOOL", name, { tool: { id, type: toolType, enableActionStatus: Boolean(sourceGet(source, "enable_action_status", "enableActionStatus") ?? false), inputParams: sourceGet(source, "input_params", "inputParams") ?? [] } }, at);
  } else if (kind === "QUESTION") {
    const replies = normalizeReplies(source.replies ?? [], branches, key), mode = String(sourceGet(source, "mode", "collect_type") ?? (replies.length ? "USER_REPLY" : "VARIABLE")).toUpperCase(), questionType = String(sourceGet(source, "question_type", "questionType") ?? "PROMPT").toUpperCase();
    if (!["VARIABLE", "USER_REPLY"].includes(mode)) throw new Error(`unsupported QUESTION mode: ${mode}`);
    if (!["PROMPT", "TEMPLATE"].includes(questionType)) throw new Error(`unsupported QUESTION question_type: ${questionType}`);
    if (questionType === "TEMPLATE" && !sourceGet(source, "question_template_id", "questionTemplateId")) throw new Error(`QUESTION node '${name}' type TEMPLATE requires question_template_id`);
    const question = sourceGet(source, "question", "prompt") ?? ""; if (questionType === "PROMPT" && !question) throw new Error(`QUESTION node '${name}' type PROMPT requires question`);
    const condition = String(source.condition ?? "AND").toUpperCase(); if (!["AND", "OR"].includes(condition)) throw new Error(`QUESTION node '${name}' condition must be AND or OR`);
    compiled = graphNode("QUESTION", name, { maxRounds: sourceGet(source, "max_rounds", "maxRounds") ?? 5, useChatHistory: Boolean(sourceGet(source, "use_chat_history", "useChatHistory") ?? true), collectInfo: { type: mode, questionType, question: questionType === "PROMPT" ? question : null, questionTemplateId: questionType === "TEMPLATE" ? sourceGet(source, "question_template_id", "questionTemplateId") : null, condition, ...(mode === "VARIABLE" ? { variables: source.variables ?? [], replies: [] } : { replies }) } }, at);
  } else if (kind === "COLLECT_ORDER") {
    const exceptions = array(sourceGet(source, "collect_order_exception", "collectOrderException") ?? [], "collectOrderException must be an array").map((raw, index) => { const item = object(raw, "exception must be an object"), type = String(item.type ?? "REPLY").toUpperCase(), templateId = item.template_id ?? item.templateId; if (type === "TEMPLATE" && !templateId) throw new Error(`COLLECT_ORDER exception[${index}] type TEMPLATE requires template_id`); if (type !== "TEMPLATE" && typeof item.reply !== "string") throw new Error(`COLLECT_ORDER exception[${index}] type REPLY requires reply`); return { key: item.key ?? "ORDER_NUMBER_NOT_PROVIDED", type, reply: item.reply, templateId }; });
    compiled = graphNode("COLLECT_ORDER", name, { maxRounds: sourceGet(source, "max_rounds", "maxRounds") ?? 5, collectOrderException: exceptions }, at);
  } else if (kind === "TRANSFER_TO_HUMAN") {
    const transferType = String(sourceGet(source, "transfer_type", "type_value", "transferType") ?? "NO_REPLY").toUpperCase(), templateId = sourceGet(source, "template_id", "templateId");
    if (!["NO_REPLY", "PROMPT", "TEMPLATE"].includes(transferType)) throw new Error(`unsupported TRANSFER_TO_HUMAN type: ${transferType}`);
    if (transferType === "TEMPLATE" && !templateId) throw new Error(`TRANSFER_TO_HUMAN node '${name}' type TEMPLATE requires template_id`);
    if (transferType === "PROMPT" && !source.prompt) throw new Error(`TRANSFER_TO_HUMAN node '${name}' type PROMPT requires prompt`);
    if (transferType !== "PROMPT" && integerIds(sourceGet(source, "ai_field_ids", "aiFieldIds"), "ai_field_ids").length) throw new Error(`TRANSFER_TO_HUMAN type ${transferType} does not use ai_field_ids`);
    compiled = graphNode("TRANSFER_TO_HUMAN", name, { transferToHuman: { type: transferType, prompt: source.prompt ?? "", explain: source.explain ?? cleanTitle(name), aiFieldIds: transferType === "PROMPT" ? integerIds(sourceGet(source, "ai_field_ids", "aiFieldIds"), "ai_field_ids") : null, ...(transferType === "TEMPLATE" ? { templateId } : {}) }, disablePrevNodeResult: Boolean(sourceGet(source, "disable_prev_node_results", "disablePrevNodeResult") ?? false) }, at);
  } else if (kind === "HUMAN_REVIEW") {
    const method = String(source.method ?? "approval").toLowerCase(), midwayMessageStrategy = String(sourceGet(source, "midway_message_strategy", "midwayMessageStrategy") ?? "ignore").toLowerCase();
    if (!["approval", "fill"].includes(method)) throw new Error("HUMAN_REVIEW method must be approval or fill");
    if (!["ignore", "handle"].includes(midwayMessageStrategy)) throw new Error("HUMAN_REVIEW midway_message_strategy must be ignore or handle");
    const humanReview: JsonObject = { method, description: source.description ?? "", midwayMessageStrategy };
    if (method === "fill" && source.fields) humanReview.fields = source.fields;
    compiled = graphNode("HUMAN_REVIEW", name, { humanReview }, at, { desc: "Routes task to a human operator for review, approval, or manual input" }); branchLookup(branches, key, "AGREE", "AGREE"); branchLookup(branches, key, "REJECT", "REJECT");
  } else if (kind === "INTENT") {
    compiled = graphNode("INTENT", name, { useChatHistory: Boolean(sourceGet(source, "use_chat_history", "useChatHistory") ?? true), historyRoundLimit: sourceGet(source, "history_round_limit", "historyRoundLimit") ?? null, prompt: source.prompt ?? null, intents: normalizeIntents(source.intents, branches, key) }, at); branchLookup(branches, key, "OTHER", "OTHER");
  } else if (kind === "KNOWLEDGE_REPLY") {
    compiled = graphNode("KNOWLEDGE_REPLY", name, { maxRounds: sourceGet(source, "max_rounds", "maxRounds") ?? 10, knowledgeReply: { prompt: source.prompt ?? "", knowledgeDirectoryIds: sourceGet(source, "kb_dirs", "knowledgeDirectoryIds") ?? null }, nextStep: [{ id: "RESOLVED", title: "Resolved", prompt: null }, { id: "UNRESOLVED", title: "Unresolved", prompt: null }], disablePrevNodeResult: Boolean(sourceGet(source, "disable_prev_node_results", "disablePrevNodeResult") ?? false) }, at); branchLookup(branches, key, "RESOLVED", "RESOLVED"); branchLookup(branches, key, "UNRESOLVED", "UNRESOLVED");
  } else if (kind === "RAG_REPLY") {
    const ragReply: JsonObject = { prompt: source.prompt ?? "", knowledgeDirectoryIds: sourceGet(source, "kb_dirs", "knowledgeDirectoryIds") ?? [] };
    for (const [snake, camel] of [["kb_dirs", "knowledgeDirectoryIds"], ["knowledge_keyword_ids", "knowledgeKeywordIds"], ["knowledge_keyword_selector", "knowledgeKeywordSelector"]]) { const v = sourceGet(source, snake, camel); if (v !== undefined) ragReply[camel] = v; }
    if (sourceGet(source, "customize_query", "customizeQuery")) { ragReply.customizeQuery = true; ragReply.querySelector = sourceGet(source, "query_selector", "querySelector"); }
    compiled = graphNode("RAG_REPLY", name, { ragReply, disablePrevNodeResult: Boolean(sourceGet(source, "disable_prev_node_results", "disablePrevNodeResult") ?? false) }, at); branchLookup(branches, key, "TRUE", "TRUE"); branchLookup(branches, key, "LACK_KNOWLEDGE", "LACK_KNOWLEDGE");
  } else if (["VARIABLE_EXTRACT", "VARIABLE_PROCESS"].includes(kind)) {
    const normalized = normalizeExtracts(source.variables ?? source.extracts ?? []);
    const extracts = normalized.items.map(item => ({ id: item.id, name: cleanTitle(item.name), describe: item.describe ?? item.description ?? "", type: item.type ?? "string" }));
    const common = { additionalData: sourceGet(source, "additional_data", "additionalData") ?? [], extracts };
    if (kind === "VARIABLE_EXTRACT") compiled = graphNode(kind, name, { useChatHistory: Boolean(sourceGet(source, "use_chat_history", "useChatHistory") ?? false), variableExtract: common }, at);
    else compiled = graphNode(kind, name, { useChatHistory: Boolean(sourceGet(source, "use_chat_history", "useChatHistory") ?? false), variableProcess: { ...common, assignments: array(source.assignments ?? [], "assignments must be an array").map(normalizeAssignment) } }, at);
    compiled._sourceExtractAliases = Object.fromEntries(normalized.aliases);
  } else if (kind === "VARIABLE_ASSIGNMENT") compiled = graphNode(kind, name, { variableAssignment: array(source.assignments ?? [], "assignments must be an array").map(normalizeAssignment) }, at);
  else if (kind === "CODE") {
    const inputs = array(source.inputs ?? [], "CODE inputs must be an array").map(raw => { const item = object(raw, "CODE input must be an object"), fieldName = sourceGet(item, "fieldName", "field_name"); if (!fieldName) throw new Error(`CODE node '${name}' input missing field_name`); const variableSelector = sourceGet(item, "variableSelector", "variable_selector"); if (variableSelector === undefined) throw new Error(`CODE node '${name}' input '${String(fieldName)}' missing variable_selector`); return { id: item.id ?? randomUUID(), fieldName, variableSelector }; });
    const outputs = array(source.outputs ?? [], "CODE outputs must be an array").map(raw => { const item = object(raw, "CODE output must be an object"), fieldName = sourceGet(item, "fieldName", "field_name"); if (!fieldName) throw new Error(`CODE node '${name}' output missing field_name`); return { id: item.id ?? randomUUID(), fieldName, fieldType: sourceGet(item, "fieldType", "field_type") ?? "String" }; });
    compiled = graphNode("CODE", name, { code: { inputs, sourceCode: sourceGet(source, "source_code", "sourceCode", "code") ?? "", outputs } }, at);
  } else if (kind === "SUB_GRAPH") {
    const targetAgentId = sourceGet(source, "target_agent_id", "targetAgentId", "agent_id", "agentId"); if (!targetAgentId) throw new Error(`SUB_GRAPH node '${name}' missing target_agent_id`);
    compiled = graphNode("SUB_GRAPH", name, { subGraph: { targetAgentId: Number(targetAgentId), contextTurnLimit: Number(sourceGet(source, "context_turn_limit", "contextTurnLimit") ?? 5) } }, at);
  } else if (kind === "BUSINESS_TRACK") {
    const events = array(sourceGet(source, "trace_events", "traceEvents"), "BUSINESS_TRACK trace_events must be a non-empty list").map((event, i) => text(event, `trace_events[${i}] must be non-empty`)); if (!events.length) throw new Error("BUSINESS_TRACK trace_events must be a non-empty list");
    compiled = graphNode("BUSINESS_TRACK", name, { businessTrack: { traceEvents: events } }, at);
  } else throw new Error(`unsupported source node type '${kind}' for key '${key}'`);
  return applyOverrides(compiled, source);
}

function specialNode(key: string, index: number) {
  const at = { x: (index % 5) * 320, y: Math.floor(index / 5) * 180 };
  if (key === "$start") return graphNode("START", undefined, undefined, at);
  if (key === "$finish") return graphNode("FINISH", "Finish", {}, at);
  if (key === "$transfer") return graphNode("TRANSFER_TO_HUMAN", "Transfer_To_Human", { transferToHuman: { type: "NO_REPLY", prompt: "", explain: "Transfer_To_Human", aiFieldIds: null }, disablePrevNodeResult: false }, at);
  throw new Error(`unknown special node key: ${key}`);
}
function extractAlias(aliases: Map<string, Map<string, string>>, key: string, id: unknown) { return id === undefined ? id : aliases.get(key)?.get(String(id)) ?? id; }
function normalizeSelector(value: unknown, nodes: Map<string, JsonObject>, aliases: Map<string, Map<string, string>>): unknown {
  const node = (key: unknown) => { const result = nodes.get(String(key)); if (!result) throw new Error(`selector node key not found: ${String(key)}`); return result; };
  if (Array.isArray(value)) {
    if (value[0] === "TOOL_KEY") return ["TOOL", node(value[1]).id, ...value.slice(2)];
    if (value[0] === "NODE_KEY") return ["NODE", node(value[1]).id];
    if (value[0] === "EXTRACT_KEY") return ["EXTRACT", node(value[1]).id, extractAlias(aliases, String(value[1]), value[2])];
    return value;
  }
  if (!value || typeof value !== "object") return value;
  const selector = value as JsonObject;
  if (typeof selector.tool === "string") { let path = selector.path ?? selector.field ?? []; if (typeof path === "string") { if (path.includes(".")) throw new Error(`nested TOOL output '${path}' must use path segments`); path = [path]; } return ["TOOL", node(selector.tool).id, ...(path as unknown[])]; }
  if (typeof selector.tool_status === "string") return ["TOOL", node(selector.tool_status).id, "ACTION_STATUS_NAME"];
  if (typeof selector.node === "string") return ["NODE", node(selector.node).id];
  if (typeof selector.llm === "string") { let path = selector.path ?? selector.field ?? []; if (typeof path === "string") path = [path]; if (!(path as unknown[]).length) path = ["text"]; const llm = node(selector.llm), first = (path as unknown[])[0]; if (first !== "text" && first !== "structured_output") { const structured = (((llm.data as JsonObject).config as JsonObject).llm as JsonObject).structuredOutput as JsonObject; if (structured.enabled) path = ["structured_output", ...(path as unknown[])]; else throw new Error(`LLM selector for '${selector.llm}' must use field='text', or enable structured_output before selecting structured fields`); } return ["LLM", llm.id, ...(path as unknown[])]; }
  if (typeof selector.code === "string") { const field = selector.field ?? selector.field_name ?? selector.output; if (typeof field !== "string" || !field) throw new Error(`CODE selector for '${selector.code}' missing field`); return ["CODE", node(selector.code).id, field]; }
  if (typeof selector.extract === "string") return ["EXTRACT", node(selector.extract).id, extractAlias(aliases, selector.extract, selector.alias ?? selector.id ?? selector.extract_id ?? selector.variable_id ?? selector.variable)];
  if (selector.system && typeof selector.system === "object") {
    if (Array.isArray(selector.system)) { const system = selector.system; if (system.length < 2) return selector; const path = system.length === 2 && Array.isArray(system[1]) ? system[1] : system.slice(1); return ["SYSTEM", system[0], ...(path as unknown[])]; }
    const system = selector.system as JsonObject; let path = system.path ?? system.field_id ?? system.id; if (!Array.isArray(path)) path = [path]; return ["SYSTEM", system.category ?? "Custom", ...(path as unknown[])];
  }
  return selector;
}
function isShortcut(value: unknown) {
  return Boolean(value && typeof value === "object" && (Array.isArray(value)
    ? ["TOOL_KEY", "NODE_KEY", "EXTRACT_KEY"].includes(String(value[0]))
    : typeof (value as JsonObject).tool === "string"
      || typeof (value as JsonObject).tool_status === "string"
      || typeof (value as JsonObject).node === "string"
      || typeof (value as JsonObject).llm === "string"
      || typeof (value as JsonObject).code === "string"
      || typeof (value as JsonObject).extract === "string"
      || (value as JsonObject).system !== undefined));
}
function resolveSelectors(value: unknown, nodes: Map<string, JsonObject>, aliases: Map<string, Map<string, string>>, currentKey?: string): unknown {
  if (typeof value === "string" && value.includes("[[var:")) return value.replace(/\[\[var:(\{.*?\}|\[.*?\])\]\]/g, (raw, json) => { try { const parsed = JSON.parse(json); return isShortcut(parsed) ? `[[var:${JSON.stringify(normalizeSelector(parsed, nodes, aliases))}]]` : raw; } catch { return raw; } });
  if (isShortcut(value)) return normalizeSelector(value, nodes, aliases);
  if (Array.isArray(value)) {
    if (value[0] === "SELF" && value.length === 2 && currentKey) return ["SELF", extractAlias(aliases, currentKey, value[1])];
    return value.map(item => resolveSelectors(item, nodes, aliases, currentKey));
  }
  if (value && typeof value === "object") {
    const result = value as JsonObject;
    if ("variableSelector" in result) result.variableSelector = normalizeSelector(result.variableSelector, nodes, aliases);
    for (const [key, child] of Object.entries(result)) result[key] = resolveSelectors(child, nodes, aliases, currentKey);
  }
  return value;
}

function autoLayout(nodes: JsonObject[], edges: JsonObject[], locked: Set<string>) {
  const order = new Map(nodes.map((item, index) => [String(item.id), index])), indegree = new Map(nodes.map(item => [String(item.id), 0])), outgoing = new Map<string, string[]>();
  for (const edge of edges) { const from = String(edge.source), to = String(edge.target); outgoing.set(from, [...(outgoing.get(from) ?? []), to]); indegree.set(to, (indegree.get(to) ?? 0) + 1); }
  const roots = nodes.filter(item => (item.data as JsonObject).category === "START").map(item => String(item.id));
  if (!roots.length) for (const [id, count] of indegree) if (count === 0) roots.push(id);
  const depth = new Map(roots.map(id => [id, 0])), queue = [...roots], remaining = new Map(indegree); for (const root of roots) remaining.set(root, 0);
  while (queue.length) { const from = queue.shift()!; for (const to of outgoing.get(from) ?? []) { depth.set(to, Math.max(depth.get(to) ?? 0, (depth.get(from) ?? 0) + 1)); remaining.set(to, (remaining.get(to) ?? 0) - 1); if (remaining.get(to) === 0) queue.push(to); } }
  const columns = new Map<number, JsonObject[]>(); for (const item of nodes) { const d = depth.get(String(item.id)) ?? 0; columns.set(d, [...(columns.get(d) ?? []), item]); }
  for (const [column, items] of columns) { items.sort((a, b) => (order.get(String(a.id)) ?? 0) - (order.get(String(b.id)) ?? 0)); items.forEach((item, row) => { if (!locked.has(String(item.id))) item.position = { x: column * 360, y: row * 220 }; }); }
}

export function compileChatflowSource(value: unknown) {
  const source = object(value, "source must be a JSON object"), rawNodes = array(source.nodes, "source.nodes must be a non-empty list");
  if (!rawNodes.length) throw new Error("source.nodes must be a non-empty list");
  const nodes: JsonObject[] = [], byKey = new Map<string, JsonObject>(), keyById = new Map<string, string>(), branches = new Map<string, string>(), aliases = new Map<string, Map<string, string>>(), locked = new Set<string>();
  rawNodes.forEach((raw, index) => {
    const spec = object(raw, `source node at index ${index} must be an object`), key = sourceKey(spec, index); if (byKey.has(key)) throw new Error(`duplicate source node key: ${key}`);
    const compiled = compileNode(spec, index, key, branches), sourceAliases = compiled._sourceExtractAliases;
    delete compiled._sourceExtractAliases; if (sourceAliases) aliases.set(key, new Map(Object.entries(sourceAliases as JsonObject).map(([k, v]) => [k, String(v)])));
    nodes.push(compiled); byKey.set(key, compiled); keyById.set(String(compiled.id), key); if (spec.position !== undefined) locked.add(String(compiled.id));
  });
  const rawEdges = [...array(source.edges ?? [], "source.edges must be an array")] as JsonObject[];
  if (source.entry && !nodes.some(item => (item.data as JsonObject).category === "START")) { const start = specialNode("$start", nodes.length); nodes.push(start); byKey.set("$start", start); rawEdges.unshift({ from: "$start", to: source.entry }); }
  for (const item of nodes) resolveSelectors(item, byKey, aliases, keyById.get(String(item.id)));
  const ensureSpecial = (key: string) => { if (SPECIAL_KEYS.has(key) && !byKey.has(key)) { const item = specialNode(key, nodes.length); nodes.push(item); byKey.set(key, item); } };
  const edges = rawEdges.map((raw, index) => {
    const spec = object(raw, `source edge at index ${index} must be an object`), from = String(sourceGet(spec, "from", "source") ?? ""), to = String(sourceGet(spec, "to", "target") ?? "");
    ensureSpecial(from); ensureSpecial(to); if (!byKey.has(from)) throw new Error(`edge source key not found: ${from}`); if (!byKey.has(to)) throw new Error(`edge target key not found: ${to}`);
    let handle: unknown = sourceGet(spec, "source_handle", "sourceHandle", "handle"); if (handle === undefined && "on" in spec) handle = branches.get(`${from}\0${String(spec.on)}`) ?? branches.get(`${from}\0${cleanTitle(spec.on)}`) ?? spec.on; handle ??= "SOURCE";
    const sourceId = String(byKey.get(from)!.id), targetId = String(byKey.get(to)!.id), sourceHandle = String(handle);
    return { id: `e-${sourceId.slice(0, 8)}-${sourceHandle}-${targetId.slice(0, 8)}`, source: sourceId, sourceHandle, target: targetId, targetHandle: "TARGET", type: "default" };
  });
  autoLayout(nodes, edges, locked);
  const graph = { nodes, edges, viewport: { x: 0, y: 0, zoom: 0.8 }, variables: source.variables ?? [] };
  const validation = validateChatflowGraph(graph);
  if (!validation.valid) throw new Error(`Graph validation failed:\n${validation.errors.map(error => `  ERROR: ${error}`).join("\n")}`);
  return graph;
}
