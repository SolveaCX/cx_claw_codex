import type { Session } from "../types.js";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, extname } from "node:path";
import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";

type JsonObject = Record<string, unknown>;

const KNOWLEDGE_TYPES = new Set(["QA", "LEARN_SELF", "FILE", "WEBSITE", "PRODUCT"]);
const asObject = (value: unknown, message: string): JsonObject => {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as JsonObject;
};
const asPositiveInt = (value: unknown, message: string) => {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number <= 0) throw new Error(message);
  return number;
};
const knowledgeType = (value: unknown) => {
  const normalized = String(value ?? "").toUpperCase();
  if (!KNOWLEDGE_TYPES.has(normalized)) throw new Error("knowledge type must be QA, LEARN_SELF, FILE, WEBSITE, or PRODUCT");
  return normalized;
};
const isolationKnowledgeType = (value: unknown) => ({ QA: "QA", LEARN_SELF: "QA", FILE: "DOCUMENT", WEBSITE: "DOCUMENT", PRODUCT: "PRODUCT" })[knowledgeType(value)]!;

/**
 * Typed transport for the tenant business API.
 * Authentication is deliberately request-local: a tenant token is never
 * copied into process.env or a module-level singleton.
 */
export class SolveaClient {
  private project?: string;
  private bot?: string;

  constructor(private readonly session: Session) {
    if (!session.tenant?.businessUrl || !session.tenant.businessToken) {
      throw new Error("no tenant selected; run tenant use before a business command");
    }
  }

  private get baseUrl() { return this.session.tenant!.businessUrl!.replace(/\/$/, ""); }
  private get env() { return this.session.tenant!.environment; }

  async request<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | boolean>): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [key, value] of Object.entries(query ?? {})) url.searchParams.set(key, String(value));
    const cookie = this.env === "prod" ? "_token" : "_token_staging";
    const headers = new Headers({
      accept: "application/json, text/plain, */*",
      origin: this.baseUrl,
      referer: `${this.baseUrl}/chatbot`,
      cookie: `${cookie}=${this.session.tenant!.businessToken}`,
      "x-cxclaw-client-version": process.env.CXCLAW_PLUGIN_VERSION ?? "unknown",
    });
    if (body !== undefined) headers.set("content-type", "application/json");
    let last: unknown;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const response = await fetch(url, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: AbortSignal.timeout(30_000),
        });
        const text = await response.text();
        let value: unknown;
        try { value = text ? JSON.parse(text) : undefined; } catch { value = { raw: text }; }
        if (!response.ok) throw new Error(`HTTP ${response.status} ${method} ${path}: ${text}`);
        if (value && typeof value === "object" && !Array.isArray(value)) {
          const object = value as JsonObject;
          const code = object.code ?? object.errno;
          if (code !== undefined && ![0, "0", 200, "200", "OK", "SUCCESS"].includes(code as never)) {
            throw new Error(`API error ${method} ${path}: ${String(object.msg ?? object.message ?? object.error ?? code)}`);
          }
          if (object.success === false) throw new Error(`API error ${method} ${path}: ${String(object.msg ?? object.message ?? object.error ?? "request failed")}`);
        }
        return value as T;
      } catch (error) {
        last = error;
        if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 200 * 2 ** attempt));
      }
    }
    throw last;
  }

  private async post<T>(path: string, body: unknown) { return this.request<T>("POST", path, body); }
  private async get<T>(path: string, query?: Record<string, string | number | boolean>) { return this.request<T>("GET", path, undefined, query); }
  private async put<T>(path: string, body: unknown) { return this.request<T>("PUT", path, body); }

  async rawCall<T = unknown>(method: string, path: string, body?: unknown, query?: Record<string, string | number | boolean>) {
    return this.request<T>(method, path, body, query);
  }

  private safePathSegment(value: string, name: string) {
    if (!value || value === "." || value === ".." || /[\\/?#%\u0000-\u001f\u007f]/.test(value)) {
      throw new Error(`${name} must be a safe non-empty path segment`);
    }
    return encodeURIComponent(value);
  }

  async projectInfo() { return this.get<unknown[]>("/api_v2/gpt/bots"); }
  async projectId() {
    if (!this.project) {
      const rows = await this.projectInfo();
      const first = Array.isArray(rows) ? rows[0] as JsonObject | undefined : undefined;
      this.project = String(first?.projectId ?? 950);
      this.bot = String(first?.id ?? "");
    }
    return this.project;
  }
  async botId() { if (!this.bot) await this.projectId(); return this.bot || "723"; }

  async listAgents(category = "text") { return this.post("/api_v2/gpt/ap/queryAgent", { projectId: Number(await this.projectId()), needRelation: true, noMeta: true, category }); }
  async getAgent(id: string) { return this.post("/api_v2/gpt/ap/queryAgent", { projectId: Number(await this.projectId()), agentId: Number(id), needRelation: true, squareAgent: false }); }
  async getChatflowGraph(id: string) { return this.post("/api_v2/gpt/chatflow/queryGraph/latest", { agentId: Number(id) }); }
  async createAgent(data: JsonObject) { return this.post("/api_v2/gpt/ap/createAgent", { projectId: Number(await this.projectId()), ...data }); }
  async updateAgent(data: JsonObject) {
    const payload: JsonObject = { ...data, projectId: Number(await this.projectId()) };
    if (payload.agentId === undefined && payload.id !== undefined) payload.agentId = payload.id;
    return this.post("/api_v2/gpt/ap/updateAgent", payload);
  }
  async updateChatflow(agentId: string, graph: JsonObject, publish = false) {
    const current = await this.getAgent(agentId);
    const agent = Array.isArray(current) ? current[0] as JsonObject : current as JsonObject;
    if (!agent || agent.type !== "CHAT_FLOW") throw new Error(`Agent ${agentId} is not CHAT_FLOW`);
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error("chatFlowGraph must be an object with nodes and edges");
    const payload: JsonObject = { ...agent, agentId: agent.id ?? Number(agentId), meta: { ...(agent.meta as JsonObject ?? {}), chatFlowGraph: graph } };
    if (publish) {
      delete payload.backupType;
      delete (payload.meta as JsonObject).backupType;
      delete (payload.meta as JsonObject).draft_flow_updatetime;
    } else {
      payload.backupType = "DRAFT";
      (payload.meta as JsonObject).draft_flow_updatetime = Date.now();
    }
    return this.updateAgent(payload);
  }

  async listPlugins() { return this.post("/api_v2/gpt/ap/queryPlugin", { projectId: Number(await this.projectId()), needRelation: false }); }
  async getPlugin(id: string) { return this.post("/api_v2/gpt/ap/queryPlugin", { projectId: Number(await this.projectId()), pluginId: Number(id), convertStrategyV5: true }); }
  async createPlugin(data: JsonObject) { return this.post("/api_v2/gpt/ap/createPlugin", { projectId: Number(await this.projectId()), ...data }); }
  async updatePlugin(data: JsonObject) {
    const payload: JsonObject = { projectId: Number(await this.projectId()), ...data };
    if (payload.pluginId === undefined && payload.id !== undefined) payload.pluginId = payload.id;
    return this.post("/api_v2/gpt/ap/updatePlugin", payload);
  }
  async deletePlugin(id: string) { return this.post("/api_v2/gpt/ap/deletePlugin", { projectId: Number(await this.projectId()), pluginId: Number(id) }); }
  async runPlugin(config: unknown, requestBody?: JsonObject) {
    return this.post("/api_v2/gpt/ap/runHttpPlugin", {
      projectId: Number(await this.projectId()), botId: Number(await this.botId()),
      externalHttpCallConfig: config,
      ...(requestBody === undefined ? {} : { externalHttpCallRequestBody: requestBody }),
    });
  }
  async replaceMockData(type: string, records: unknown[]) {
    if (records.length > 10_000) throw new Error("records must contain at most 10000 items");
    return this.post(`/api_v2/gpt/mockdata/reAddMockData/${this.safePathSegment(type, "mock type")}`, records);
  }
  async queryMockData(type: string) { return this.get("/api_v2/gpt/mockdata/queryMockData", { type: this.safePathSegment(type, "mock type"), globalData: false }); }

  async listAiFields() { return this.post("/api_v2/gpt/chatflow/queryAiFields", {}); }
  async listAgentAiFields() { return this.post("/api_v2/gpt/field/list/range", { fieldRange: ["all", "agent", "agent_preload_visible"] }); }
  async aiFieldGuide() { return this.post("/api_v2/tars/api/field/manage/guide/record", {}); }
  async initializeAiFields() { return this.get("/api_v2/tars/api/field/manage/pre/install"); }
  async listManagedAiFields(pageIndex: number, pageSize: number, name: string) {
    return this.post("/api_v2/tars/api/field/manage/page", { pageIndex, pageSize, name });
  }
  async getManagedAiField(id: string) { return this.get(`/api_v2/tars/api/field/manage/detail/${encodeURIComponent(id)}`); }
  async createManagedAiField(data: JsonObject) { return this.post("/api_v2/tars/api/field/manage/create", data); }
  async updateManagedAiField(data: JsonObject) { return this.post("/api_v2/tars/api/field/manage/update", data); }
  async deleteManagedAiField(id: string) { return this.get(`/api_v2/tars/api/field/manage/delete/${encodeURIComponent(id)}`); }
  async toggleManagedAiField(id: string) { return this.get(`/api_v2/tars/api/field/manage/switch/${encodeURIComponent(id)}`); }

  async chat(data: JsonObject) { const bot = String(data.botId ?? await this.botId()); return this.post(`/api_v2/gpt/bot/${bot}/chat`, { ...data, botId: Number(bot), projectId: Number(await this.projectId()), option: data.option ?? { debug: true } }); }
  async chatStream(data: JsonObject) {
    const bot = String(data.botId ?? await this.botId());
    const body = { ...data, botId: Number(bot), projectId: Number(await this.projectId()), option: data.option ?? { debug: true } };
    const cookie = this.env === "prod" ? "_token" : "_token_staging";
    const response = await fetch(`${this.baseUrl}/api_v2/gpt/bot/${encodeURIComponent(bot)}/chat/stream`, {
      method: "POST",
      headers: {
        accept: "text/event-stream", "content-type": "application/json", origin: this.baseUrl,
        referer: `${this.baseUrl}/chatbot`, cookie: `${cookie}=${this.session.tenant!.businessToken}`,
        "x-cxclaw-client-version": process.env.CXCLAW_PLUGIN_VERSION ?? "unknown",
      },
      body: JSON.stringify(body), signal: AbortSignal.timeout(30_000),
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`HTTP ${response.status} POST /api_v2/gpt/bot/${bot}/chat/stream: ${text}`);
    let finalAction: JsonObject | undefined;
    const content: string[] = [];
    for (const line of text.split(/\r?\n/)) {
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (!raw) continue;
      let event: JsonObject;
      try { event = asObject(JSON.parse(raw), "stream event must be an object"); } catch { continue; }
      if (event.errno !== undefined && ![0, "0"].includes(event.errno as never)) throw new Error(`API error POST /api_v2/gpt/bot/${bot}/chat/stream: ${String(event.errmsg ?? event.message ?? event.errno)}`);
      if (event.content) content.push(String(event.content));
      if (event.isEnd) finalAction = event.data && typeof event.data === "object" && !Array.isArray(event.data) ? event.data as JsonObject : event;
    }
    return finalAction ?? { content: content.join(""), isEnd: true };
  }
  async chatAsync(data: JsonObject) { const bot = String(data.botId ?? await this.botId()); return this.post(`/api_v2/gpt/bot/${bot}/chat/async`, { ...data, botId: Number(bot), projectId: Number(await this.projectId()), option: data.option ?? { debug: true } }); }
  async asyncResult(receipt: string, botId?: string) { const bot = botId ?? await this.botId(); return this.get(`/api_v2/gpt/bot/${bot}/chat/async/${encodeURIComponent(receipt)}`); }

  async listIntents(category = "E_COMMERCE") { return this.get(`/api_v2/gpt/project/${await this.projectId()}/intents`, category ? { category } : undefined); }
  async getIntent(id: string) { return this.get(`/api_v2/gpt/project/${await this.projectId()}/intent/${encodeURIComponent(id)}`); }
  async createIntent(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/intent`, data); }
  async updateIntent(id: string, data: JsonObject) { return this.put(`/api_v2/gpt/project/${await this.projectId()}/intent/${encodeURIComponent(id)}`, data); }
  async toggleIntent(id: string, enabled: boolean) { return this.put(`/api_v2/gpt/project/${await this.projectId()}/intent/${encodeURIComponent(id)}/status`, { status: enabled ? "ENABLED" : "DISABLED" }); }

  async listEntities() { return this.get(`/api_v2/gpt/project/${await this.projectId()}/entities`); }
  async listStrategies(pageSize = 100) { return this.get(`/api_v2/gpt/project/${await this.projectId()}/strategies`, { pageSize, pageNum: 1 }); }
  async createStrategy(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/strategy?v4=true`, data); }
  async updateStrategy(id: string, data: JsonObject) { return this.request("PUT", `/api_v2/gpt/project/${await this.projectId()}/strategy/${encodeURIComponent(id)}`, data, { v4: "true" }); }
  async toggleStrategy(id: string, enabled: boolean) { return this.request("PUT", `/api_v2/gpt/project/${await this.projectId()}/strategy/${encodeURIComponent(id)}`, { status: enabled ? "ENABLED" : "DISABLED" }, { v4: "true" }); }

  async qualityStatus() { return this.get("/api_v2/intelli/inspection/ticket/status"); }
  async setQualityStatus(enabled: boolean) { return this.post("/api_v2/intelli/inspection/ticket/open", { open: enabled, projectId: Number(await this.projectId()) }); }
  async qualityRules(beginTimestamp?: number, endTimestamp?: number) { return this.get("/api_v2/intelli/inspection/ticket/rules", { ...(beginTimestamp === undefined ? {} : { beginTimestamp }), ...(endTimestamp === undefined ? {} : { endTimestamp }) }); }
  async qualityRule(key: string) { return this.get("/api_v2/intelli/inspection/ticket/rules/detail", { inspectionKey: key }); }
  async updateQualityRule(data: JsonObject) { return this.post("/api_v2/intelli/inspection/ticket/rules", data); }
  async customQualityRule(key: string) { return this.post("/api_v2/intelli/inspection/ticket/customRules/detail", { inspectionKey: key }); }
  async createCustomQualityRule(data: JsonObject) { return this.post("/api_v2/intelli/inspection/ticket/customRules/create", data); }
  async updateCustomQualityRule(data: JsonObject) { return this.post("/api_v2/intelli/inspection/ticket/customRules/update", data); }
  async deleteCustomQualityRule(key: string) { return this.post("/api_v2/intelli/inspection/ticket/customRules/delete", { inspectionKey: key }); }
  async listQualityAlertRules() { return this.get("/api_v2/intelli/inspection/alert/list"); }
  async getQualityAlertRule(id: string) { return this.get("/api_v2/intelli/inspection/alert/detail", { id }); }
  async createQualityAlertRule(data: JsonObject) { return this.post("/api_v2/intelli/inspection/alert/create", data); }
  async updateQualityAlertRule(data: JsonObject) { return this.post("/api_v2/intelli/inspection/alert/update", data); }
  async deleteQualityAlertRule(id: string) { return this.get("/api_v2/intelli/inspection/alert/delete", { id }); }
  async listQualityAlertMessages(data: JsonObject) { return this.post("/api_v2/intelli/inspection/alert/message/list", data); }
  async getQualityAlertMessage(id: string) { return this.get("/api_v2/intelli/inspection/alert/message/detail", { id }); }

  async listTemplates(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/templates/filter`, data); }
  async createTemplate(data: JsonObject) {
    const content = String(data.content ?? "");
    return this.post(`/api_v2/gpt/project/${await this.projectId()}/template`, {
      name: data.name, content, status: data.status ?? "ENABLED",
      multiContent: data.multiContent ?? { AUTO: content },
      ...(data.scene ? { scene: data.scene } : {}),
    });
  }
  async updateTemplate(id: string, data: JsonObject) {
    return this.put(`/api_v2/gpt/project/${await this.projectId()}/template/${encodeURIComponent(id)}`, data);
  }
  async deleteTemplates(ids: number[]) {
    return this.request("DELETE", `/api_v2/gpt/project/${await this.projectId()}/templates`, { templateIds: ids });
  }

  private get qamPrefix() { return this.env === "prod" ? "/api_v2/qam" : "/sns_v1"; }
  get qamPath() { return this.qamPrefix; }
  async listKnowledge(data: JsonObject) { return this.post(`${this.qamPrefix}/project/${await this.projectId()}/getKnowledge`, { type: "ALL", pageIndex: 1, pageSize: 50, keyword: "", ...data }); }
  async getKnowledge(id: string) { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/ku/${encodeURIComponent(id)}`); }
  async getDocument(id: string) { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/document/${encodeURIComponent(id)}`); }
  async getProductKnowledge(id: string) { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/ku_product/${encodeURIComponent(id)}`); }
  async getKnowledgeByType(id: string, type: string) {
    const normalized = knowledgeType(type);
    if (normalized === "FILE" || normalized === "WEBSITE") return this.getDocument(id);
    if (normalized === "PRODUCT") return this.getProductKnowledge(id);
    return this.getKnowledge(id);
  }
  async updateKnowledge(id: string, data: JsonObject) {
    const payload = { ...data };
    if (payload.directoryId === undefined) {
      const current = asObject(await this.getKnowledge(id), `could not read knowledge ${id} before update`);
      if (current.directoryId !== undefined) payload.directoryId = current.directoryId;
    }
    return this.request("PUT", `${this.qamPrefix}/project/${await this.projectId()}/ku`, { ...payload, kuId: asPositiveInt(id, "knowledge id must be a positive integer") });
  }
  async uploadQa(items: unknown[]) {
    if (!Array.isArray(items) || !items.length) throw new Error("QA items must be a non-empty array");
    const payload = items.map((value, index) => {
      const item = asObject(value, `QA item #${index + 1} must be an object`);
      const title = String(item.title ?? "").trim();
      const content = String(item.content ?? "").trim();
      if (!title) throw new Error(`QA item #${index + 1} requires title`);
      if (!content) throw new Error(`QA item #${index + 1} requires content`);
      return {
        title, content, forceIndex: item.forceIndex ?? true, type: "QA",
        published: item.published ?? true, taskType: item.taskType ?? "MANUAL",
        metadata: item.metadata ?? { tags: [] }, directoryId: item.directoryId ?? "",
        isVisible: item.isVisible ?? true,
      };
    });
    return this.post(`${this.qamPrefix}/project/${await this.projectId()}/kus`, payload);
  }
  async createDocuments(documents: JsonObject[], directoryId: number | string, taskType: "FILE" | "WEB") {
    if (!documents.length) throw new Error("documents must be a non-empty array");
    return this.post(`${this.qamPrefix}/project/${await this.projectId()}/documents`, {
      documents, published: true, taskType, taskUrl: "MANUAL", isFullSiteCrawl: false,
      metadata: { tags: [] }, directoryId, isVisible: true,
    });
  }
  async uploadTempFile(filePath: string, forKnowledge = false) {
    const credentialPath = forKnowledge
      ? `${this.qamPrefix}/project/${await this.projectId()}/sts_credentials`
      : `/api_v2/gpt/project/${await this.projectId()}/sts_credentials`;
    const credentials = asObject(
      await this.get(credentialPath),
      "STS credentials must be an object",
    );
    const required = ["accessKeyId", "secretAccessKey", "sessionToken", "region", "bucketName", "path"];
    const missing = required.filter(key => !credentials[key]);
    if (missing.length) throw new Error(`knowledge STS credentials missing fields: ${missing.join(", ")}`);
    const key = `${String(credentials.path)}${basename(filePath)}`;
    const client = new S3Client({
      region: String(credentials.region),
      credentials: {
        accessKeyId: String(credentials.accessKeyId),
        secretAccessKey: String(credentials.secretAccessKey),
        sessionToken: String(credentials.sessionToken),
      },
    });
    const contentTypes: Record<string, string> = {
      ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".pdf": "application/pdf",
    };
    await client.send(new PutObjectCommand({
      Bucket: String(credentials.bucketName), Key: key, Body: await readFile(filePath),
      ContentType: contentTypes[extname(filePath).toLowerCase()] ?? "application/octet-stream",
    }));
    return key;
  }
  async uploadKnowledgeFile(filePath: string) { return this.uploadTempFile(filePath, true); }
  async downloadFile(path: string, target: string, query?: Record<string, string | number | boolean>) {
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [key, value] of Object.entries(query ?? {})) url.searchParams.set(key, String(value));
    const cookie = this.env === "prod" ? "_token" : "_token_staging";
    const response = await fetch(url, {
      headers: { accept: "*/*", origin: this.baseUrl, referer: `${this.baseUrl}/chatbot`, cookie: `${cookie}=${this.session.tenant!.businessToken}` },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status} GET ${path}: ${await response.text()}`);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, new Uint8Array(await response.arrayBuffer()));
    return target;
  }
  async downloadLabelTemplate(templateType: string, target: string) {
    if (!["VOC_LABEL", "VOC_LABEL_INIT"].includes(templateType)) throw new Error("template type must be VOC_LABEL or VOC_LABEL_INIT");
    return this.downloadFile(`/api_v2/gpt/label/project/${await this.projectId()}/downloadLabelTemplate`, target, { type: templateType });
  }
  async downloadLabels(treeId: string, target: string) {
    return this.downloadFile(`/api_v2/gpt/label/project/${await this.projectId()}/downloadLabel`, target, { treeId: asPositiveInt(treeId, "tree id must be a positive integer") });
  }
  async uploadLabelFile(treeId: string, filePath: string, init = false) {
    const fileKey = await this.uploadTempFile(filePath);
    const result = await this.post(`/api_v2/gpt/label/project/${await this.projectId()}/uploadLabel`, {
      treeId: asPositiveInt(treeId, "tree id must be a positive integer"), file: fileKey, ...(init ? { uploadWay: "INIT" } : {}),
    });
    return { fileKey, result };
  }
  async updateKus(value: unknown) {
    const source = Array.isArray(value) ? value : asObject(value, "batch knowledge update must be an array or object with list").list;
    if (!Array.isArray(source) || !source.length) throw new Error("batch knowledge update requires a non-empty array");
    const list = [];
    for (const [index, value] of source.entries()) {
      const row = { ...asObject(value, `batch knowledge item #${index + 1} must be an object`) };
      row.kuId = asPositiveInt(row.kuId ?? row.id, `batch knowledge item #${index + 1} requires kuId or id`);
      delete row.id;
      if (row.directoryId === undefined) {
        const current = asObject(await this.getKnowledge(String(row.kuId)), `could not read knowledge ${row.kuId} before update`);
        if (current.directoryId !== undefined) row.directoryId = current.directoryId;
      }
      list.push(row);
    }
    return this.request("PUT", `${this.qamPrefix}/project/${await this.projectId()}/kus`, { list });
  }
  async updateDocumentContent(id: string, type: string, changes: JsonObject) {
    const normalized = knowledgeType(type);
    if (normalized !== "FILE" && normalized !== "WEBSITE") throw new Error("document type must be FILE or WEBSITE");
    const unknown = Object.keys(changes).filter(key => !["fileText", "filePath", "title"].includes(key));
    if (unknown.length) throw new Error(`unsupported document content fields: ${unknown.sort().join(", ")}`);
    if (changes.fileText === undefined && changes.filePath === undefined) throw new Error("document update requires fileText or filePath");
    const documentId = asPositiveInt(id, "document id must be a positive integer");
    const current = asObject(await this.getDocument(id), `could not read document ${id} before update`);
    const payload = {
      type: normalized, directoryId: current.directoryId,
      fileName: current.fileName ?? current.name ?? current.title,
      title: current.title ?? current.fileName ?? current.name,
      metadata: current.metadata && typeof current.metadata === "object" && !Array.isArray(current.metadata) ? current.metadata : {},
      ...changes, knowledgeIds: [documentId],
    };
    return this.request("PUT", `${this.qamPrefix}/project/${await this.projectId()}/document/${documentId}/contentV2`, payload);
  }
  async createProductKnowledge(data: JsonObject) {
    if (!data.title || !data.spuUrl) throw new Error("product knowledge requires title and spuUrl");
    return this.post(`${this.qamPrefix}/project/${await this.projectId()}/ku_product`, {
      source: "MANUAL", published: true, isVisible: true, metadata: { tags: [] }, ...data,
    });
  }
  async updateProductKnowledge(id: string, changes: JsonObject) {
    const allowed = new Set(["productId", "tags", "documentId", "title", "handle", "vendor", "category", "brand", "productStatus", "country", "spuUrl", "image", "platform", "currency", "price", "compareAtPrice", "describe", "source", "skuList", "directoryId", "published", "metadata", "specialTagMap", "isVisible", "optionName"]);
    const unknown = Object.keys(changes).filter(key => !allowed.has(key) && key !== "id" && key !== "kuProductId");
    if (unknown.length) throw new Error(`unsupported product fields: ${unknown.sort().join(", ")}`);
    const current = asObject(await this.getProductKnowledge(id), `could not read product knowledge ${id} before update`);
    const payload: JsonObject = {};
    for (const key of allowed) if (current[key] !== undefined) payload[key] = current[key];
    for (const key of allowed) if (changes[key] !== undefined) payload[key] = changes[key];
    const missing = ["title", "describe", "spuUrl", "image", "source", "published", "isVisible"].filter(key => payload[key] === undefined || payload[key] === "");
    if (missing.length) throw new Error(`product detail is incomplete: ${missing.join(", ")}`);
    return this.request("PUT", `${this.qamPrefix}/project/${await this.projectId()}/ku_product`, { ...payload, kuProductId: asPositiveInt(id, "product id must be a positive integer") });
  }
  async updateKuProducts(value: unknown) {
    const source = Array.isArray(value) ? value : asObject(value, "batch product update must be an array or object with list").list;
    if (!Array.isArray(source) || !source.length) throw new Error("batch product update requires a non-empty array");
    const list = source.map((value, index) => {
      const row = asObject(value, `batch product item #${index + 1} must be an object`);
      const entry: JsonObject = { id: asPositiveInt(row.id ?? row.kuProductId, `batch product item #${index + 1} requires id or kuProductId`) };
      if (row.mainPush !== undefined) entry.mainPush = Boolean(row.mainPush);
      if (row.enable !== undefined) entry.enable = Boolean(row.enable);
      else if (row.published !== undefined) entry.enable = Boolean(row.published);
      return entry;
    });
    return this.request("PUT", `${this.qamPrefix}/project/${await this.projectId()}/ku_products`, { list });
  }
  async operateKnowledge(value: unknown, confirmDelete = false) {
    const source = Array.isArray(value) ? value : asObject(value, "knowledge operation must be an array or object with requestList").requestList;
    if (!Array.isArray(source) || !source.length) throw new Error("knowledge operation requires a non-empty array");
    const supportedOperations = new Set(["DELETE", "MOVE", "PUBLISH", "UNPUBLISH", "VISIBLE", "INVISIBLE"]);
    const requestList = [];
    for (const [index, value] of source.entries()) {
      const row = asObject(value, `knowledge operation #${index + 1} must be an object`);
      const type = knowledgeType(row.knowledgeType);
      const operateType = String(row.operateType ?? "").toUpperCase();
      if (!supportedOperations.has(operateType)) throw new Error(`unsupported knowledge operation: ${operateType}`);
      const knowledgeId = asPositiveInt(row.knowledgeId, `knowledge operation #${index + 1} requires knowledgeId`);
      await this.getKnowledgeByType(String(knowledgeId), type);
      const normalized: JsonObject = { knowledgeType: type, knowledgeId, operateType };
      if (operateType === "MOVE") normalized.directoryId = asPositiveInt(row.directoryId, "MOVE requires directoryId");
      requestList.push(normalized);
    }
    if (requestList.some(item => item.operateType === "DELETE") && !confirmDelete) throw new Error("DELETE requires --confirm-delete after explicit user acknowledgement");
    return this.post(`${this.qamPrefix}/project/${await this.projectId()}/updateKnowledge`, { requestList });
  }
  async listDirectories() { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/directories`, { keyword: "", kuPublished: "" }); }
  async createFolder(name: string, parentId = 0) { return this.post(`${this.qamPrefix}/project/${await this.projectId()}/directory`, { name, parentId, type: "GENERIC" }); }
  async updateDirectory(id: string, data: JsonObject) { return this.request("PUT", `${this.qamPrefix}/project/${await this.projectId()}/directory/${encodeURIComponent(id)}`, data); }
  async deleteDirectory(id: string) { return this.request("DELETE", `${this.qamPrefix}/project/${await this.projectId()}/directory/${encodeURIComponent(id)}`); }
  async knowledgeTags(keyword = "") { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/searchKeywordAndIntents`, { keyword }); }
  async moveDirectory(id: string, parentId: string) { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/directory/move`, { currentId: asPositiveInt(id, "directory id must be a positive integer"), parentId: Number(parentId) }); }
  async getKnowledgeIsolationKeywords(id: string, type: string) { return this.get(`${this.qamPrefix}/project/${await this.projectId()}/knowledge/isolation_keywords`, { knowledgeType: isolationKnowledgeType(type), knowledgeId: asPositiveInt(id, "knowledge id must be a positive integer") }); }
  async batchUpdateIsolationKeywordBindings(data: JsonObject) {
    const items = data.items ?? [], directoryIds = data.directoryIds ?? [], keywordIds = data.keywordIds ?? [];
    if (!Array.isArray(items) || !Array.isArray(directoryIds) || !Array.isArray(keywordIds)) throw new Error("items, directoryIds and keywordIds must be arrays");
    if (!items.length && !directoryIds.length && !keywordIds.length) throw new Error("isolation keyword binding update has no targets or keyword IDs");
    if (items.length && directoryIds.length) throw new Error("submit knowledge items and directory IDs in separate binding updates");
    const normalizedItems = items.map((value, index) => {
      const row = asObject(value, `isolation binding item #${index + 1} must be an object`);
      if (!Array.isArray(row.keywordIds)) throw new Error("items[].keywordIds must be an array");
      return {
        knowledgeType: isolationKnowledgeType(row.knowledgeType ?? "QA"),
        knowledgeId: asPositiveInt(row.knowledgeId, "items[].knowledgeId must be a positive integer"),
        keywordIds: [...new Set(row.keywordIds.map(value => asPositiveInt(value, "items[].keywordIds must contain positive integer IDs")))],
      };
    });
    return this.post(`${this.qamPrefix}/project/${await this.projectId()}/knowledge/isolation_keywords/batch`, {
      items: normalizedItems,
      directoryIds: [...new Set(directoryIds.map(value => asPositiveInt(value, "directoryIds must contain positive integer IDs")))],
      keywordIds: [...new Set(keywordIds.map(value => asPositiveInt(value, "keywordIds must contain positive integer IDs")))],
    });
  }
  async applyIsolationKeywordBindings(data: JsonObject) {
    const operation = String(data.operation ?? "append").toLowerCase();
    if (!["append", "remove", "replace"].includes(operation)) throw new Error("operation must be append, remove, or replace");
    const items = data.items ?? [], directoryIds = data.directoryIds ?? [];
    if (!Array.isArray(items) || !Array.isArray(directoryIds) || (!items.length && !directoryIds.length)) throw new Error("binding update requires knowledge items or directory IDs");
    if (items.length && directoryIds.length) throw new Error("submit knowledge items and directory IDs in separate binding updates");
    if (directoryIds.length && operation !== "replace") throw new Error("directory bindings require operation=replace");
    if ((directoryIds.length || operation === "replace") && data.confirmReplace !== true) throw new Error("binding replacement requires confirmReplace=true after explicit user confirmation");
    const resolvedItems = [];
    for (const [index, value] of items.entries()) {
      const row = asObject(value, `isolation binding item #${index + 1} must be an object`);
      const id = asPositiveInt(row.knowledgeId, "items[].knowledgeId must be a positive integer");
      const type = knowledgeType(row.knowledgeType);
      if (!Array.isArray(row.keywordIds)) throw new Error("items[].keywordIds must be an array");
      const requestedIds = row.keywordIds.map(value => asPositiveInt(value, "items[].keywordIds must contain positive integer IDs"));
      await this.getKnowledgeByType(String(id), type);
      const existingResponse = await this.getKnowledgeIsolationKeywords(String(id), type);
      const existingRows = Array.isArray(existingResponse) ? existingResponse
        : existingResponse && typeof existingResponse === "object" && Array.isArray((existingResponse as JsonObject).list) ? (existingResponse as JsonObject).list as unknown[] : [];
      const existingIds = existingRows.map(value => asPositiveInt(asObject(value, "existing isolation keyword binding must be an object").id, "existing isolation keyword binding has an invalid ID"));
      const finalIds = operation === "append" ? [...new Set([...existingIds, ...requestedIds])]
        : operation === "remove" ? existingIds.filter(id => !requestedIds.includes(id)) : [...new Set(requestedIds)];
      resolvedItems.push({ knowledgeType: type, knowledgeId: id, keywordIds: finalIds });
    }
    for (const value of directoryIds) await this.listKnowledge({ directoryId: asPositiveInt(value, "directoryIds must contain positive integer IDs"), pageIndex: 1, pageSize: 1 });
    return this.batchUpdateIsolationKeywordBindings({ items: resolvedItems, directoryIds, keywordIds: data.keywordIds ?? [] });
  }
  async editKnowledgeTags(data: JsonObject) {
    const knowledgeIds = data.knowledgeIds, requestedTags = data.tagList;
    if (!Array.isArray(knowledgeIds) || !knowledgeIds.length) throw new Error("edit knowledge tags requires non-empty knowledgeIds");
    if (!Array.isArray(requestedTags) || requestedTags.some(value => typeof value !== "string" || !value.trim())) throw new Error("tagList must contain non-empty strings");
    const operation = String(data.operation ?? "append");
    if (!["append", "replace", "remove"].includes(operation)) throw new Error("tag operation must be append, replace, or remove");
    const type = knowledgeType(data.type ?? "QA");
    const results = [];
    for (const value of knowledgeIds) {
      const id = asPositiveInt(value, "knowledgeIds must contain positive integer IDs");
      const current = asObject(await this.getKnowledgeByType(String(id), type), `could not read knowledge ${id} before tag update`);
      const metadata = current.metadata && typeof current.metadata === "object" && !Array.isArray(current.metadata) ? current.metadata as JsonObject : {};
      const existing = Array.isArray(current.tags) ? current.tags : Array.isArray(metadata.tags) ? metadata.tags : [];
      const requested = requestedTags.map(String);
      const tagList = operation === "append" ? [...new Set([...existing.map(String), ...requested])]
        : operation === "remove" ? existing.map(String).filter(tag => !requested.includes(tag)) : [...new Set(requested)];
      results.push(await this.post(`${this.qamPrefix}/project/${await this.projectId()}/editTags`, { type, knowledgeIds: [id], tagList }));
    }
    return { success: true, results };
  }

  async transcript(chatId: string) { return this.get(`/api_v2/gpt/project/${await this.projectId()}/transcript/${encodeURIComponent(chatId)}`, { isCompare: true }); }
  async listTranscripts(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/transcripts/filter`, data); }
  async getConversationsByIntent(intent: string, limit = 50) {
    const intentResponse = await this.listIntents("");
    const intents = Array.isArray(intentResponse) ? intentResponse
      : intentResponse && typeof intentResponse === "object" && Array.isArray((intentResponse as JsonObject).data) ? (intentResponse as JsonObject).data as unknown[]
        : intentResponse && typeof intentResponse === "object" && Array.isArray((intentResponse as JsonObject).list) ? (intentResponse as JsonObject).list as unknown[] : [];
    const matched = intents.find(value => value && typeof value === "object" && String((value as JsonObject).name ?? "") === intent) as JsonObject | undefined;
    if (!matched?.id) return [];
    const response = await this.listTranscripts({ pageSize: limit, pageIndex: 1, intentId: Number(matched.id) });
    const rows = Array.isArray(response) ? response
      : response && typeof response === "object" && Array.isArray((response as JsonObject).list) ? (response as JsonObject).list as unknown[] : [];
    const result = [];
    for (const value of rows) {
      if (!value || typeof value !== "object") continue;
      const row = value as JsonObject, chatId = row.chatId ?? row.id;
      if (!chatId) continue;
      try {
        const detail = asObject(await this.transcript(String(chatId)), `transcript ${chatId} must be an object`);
        const turns = Array.isArray(detail.turns) ? detail.turns : Array.isArray(detail.messages) ? detail.messages : [];
        const messages: unknown[] = []; let metadata: JsonObject = {};
        for (const turnValue of turns) {
          if (!turnValue || typeof turnValue !== "object") continue;
          const turn = turnValue as JsonObject, role = turn.role ?? turn.type, content = turn.content ?? turn.message;
          if (role === "USER" && content) messages.push(content);
          if (!Object.keys(metadata).length && turn.metadata && typeof turn.metadata === "object" && !Array.isArray(turn.metadata)) metadata = turn.metadata as JsonObject;
        }
        if (messages.length) result.push({ source_chat_id: chatId, intent, messages, metadata });
      } catch { /* One unreadable transcript must not abort the batch. */ }
    }
    return result;
  }
  async resolveTranscriptChatId(externalId: string, pageSize = 10) {
    const result = await this.listTranscripts({ pageSize, pageIndex: 1, debug: false, keyword: externalId });
    const rows = Array.isArray(result) ? result : (result as JsonObject)?.list;
    const items = Array.isArray(rows) ? rows.filter(row => row && typeof row === "object") as JsonObject[] : [];
    const exact = items.filter(row => String(row.externId ?? row.externalId ?? row.external_id ?? "") === externalId);
    const matches = (exact.length ? exact : items).map(row => ({ chatId: row.chatId ?? row.id, externalId: row.externId ?? row.externalId ?? row.external_id, agentName: row.agentName ?? "", touchPoint: row.touchPoint ?? row.touchpoint ?? "", createdAt: row.createdAt ?? "" }));
    return { externalId, chatId: exact.length || matches.length === 1 ? matches[0]?.chatId ?? null : null, matchedBy: exact.length ? "exactExternalId" : "keyword", matches };
  }
  async chatContext(botId: string, data: JsonObject) { return this.post(`/api_v2/gpt/bot/${encodeURIComponent(botId)}/chat/context/compare`, data); }
}
