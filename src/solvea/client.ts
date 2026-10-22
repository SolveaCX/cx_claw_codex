import type { Session } from "../types.js";

type JsonObject = Record<string, unknown>;

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

  private async request<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | boolean>): Promise<T> {
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
  async updateAgent(data: JsonObject) { return this.post("/api_v2/gpt/ap/updateAgent", data); }

  async listPlugins() { return this.post("/api_v2/gpt/ap/queryPlugin", { projectId: Number(await this.projectId()), needRelation: false }); }
  async getPlugin(id: string) { return this.post("/api_v2/gpt/ap/queryPlugin", { projectId: Number(await this.projectId()), pluginId: Number(id), convertStrategyV5: true }); }
  async createPlugin(data: JsonObject) { return this.post("/api_v2/gpt/ap/createPlugin", { projectId: Number(await this.projectId()), ...data }); }
  async updatePlugin(data: JsonObject) { return this.post("/api_v2/gpt/ap/updatePlugin", { projectId: Number(await this.projectId()), ...data }); }
  async deletePlugin(id: string) { return this.post("/api_v2/gpt/ap/deletePlugin", { projectId: Number(await this.projectId()), pluginId: Number(id) }); }

  async chat(data: JsonObject) { const bot = String(data.botId ?? await this.botId()); return this.post(`/api_v2/gpt/bot/${bot}/chat`, { botId: Number(bot), projectId: Number(await this.projectId()), option: { debug: true }, ...data }); }
  async chatAsync(data: JsonObject) { const bot = String(data.botId ?? await this.botId()); return this.post(`/api_v2/gpt/bot/${bot}/chat/async`, { botId: Number(bot), projectId: Number(await this.projectId()), option: { debug: true }, ...data }); }
  async asyncResult(receipt: string, botId?: string) { const bot = botId ?? await this.botId(); return this.get(`/api_v2/gpt/bot/${bot}/chat/async/${encodeURIComponent(receipt)}`); }

  async listIntents(category = "E_COMMERCE") { return this.get(`/api_v2/gpt/project/${await this.projectId()}/intents`, category ? { category } : undefined); }
  async getIntent(id: string) { return this.get(`/api_v2/gpt/project/${await this.projectId()}/intent/${encodeURIComponent(id)}`); }
  async createIntent(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/intent`, data); }
  async updateIntent(id: string, data: JsonObject) { return this.put(`/api_v2/gpt/project/${await this.projectId()}/intent/${encodeURIComponent(id)}`, data); }
  async toggleIntent(id: string, enabled: boolean) { return this.put(`/api_v2/gpt/project/${await this.projectId()}/intent/${encodeURIComponent(id)}/status`, { status: enabled ? "ENABLED" : "DISABLED" }); }

  async listEntities() { return this.get(`/api_v2/gpt/project/${await this.projectId()}/entities`); }
  async listStrategies(pageSize = 100) { return this.get(`/api_v2/gpt/project/${await this.projectId()}/strategies`, { pageSize, pageNum: 1 }); }
  async createStrategy(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/strategy?v4=true`, data); }
  async updateStrategy(id: string, data: JsonObject) { return this.request("PUT", `/api_v2/gpt/project/${await this.projectId()}/strategy/${encodeURIComponent(id)}`, data); }
  async toggleStrategy(id: string, enabled: boolean) { return this.request("PUT", `/api_v2/gpt/project/${await this.projectId()}/strategy/${encodeURIComponent(id)}/status`, { status: enabled ? "ENABLED" : "DISABLED" }); }

  async transcript(chatId: string) { return this.get(`/api_v2/gpt/project/${await this.projectId()}/transcript/${encodeURIComponent(chatId)}`, { isCompare: true }); }
  async listTranscripts(data: JsonObject) { return this.post(`/api_v2/gpt/project/${await this.projectId()}/transcripts/filter`, data); }
  async chatContext(botId: string, data: JsonObject) { return this.post(`/api_v2/gpt/bot/${encodeURIComponent(botId)}/chat/context/compare`, data); }
}
