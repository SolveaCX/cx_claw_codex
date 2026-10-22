import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import { option, options } from "../args.js";
import type { Session } from "../types.js";

const safe = (value: string) => encodeURIComponent(value);
const docsMcpUrl = process.env.CXCLAW_DOCS_MCP_URL ?? "https://solvea-39f11a36.mintlify.app/mcp";
const publicDocsPrefix = "https://www.voc.ai/cn/docs/";
const previewDocsPrefix = "https://solvea-39f11a36.mintlify.app/";

async function docsTool(tool: string, arguments_: Record<string, unknown>) {
  const requestId = Date.now();
  const initialize = await fetch(docsMcpUrl, { method: "POST", headers: { accept: "application/json, text/event-stream", "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: requestId, method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "cxclawctl", version: "1" } } }), signal: AbortSignal.timeout(30_000) });
  const sessionId = initialize.headers.get("mcp-session-id"); const headers = { accept: "application/json, text/event-stream", "content-type": "application/json", ...(sessionId ? { "mcp-session-id": sessionId } : {}) };
  await fetch(docsMcpUrl, { method: "POST", headers, body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized", params: {} }), signal: AbortSignal.timeout(30_000) });
  const response = await fetch(docsMcpUrl, { method: "POST", headers, body: JSON.stringify({ jsonrpc: "2.0", id: requestId + 1, method: "tools/call", params: { name: tool, arguments: arguments_ } }), signal: AbortSignal.timeout(30_000) });
  const text = await response.text(); if (!response.ok) throw new Error(`product docs request failed: HTTP ${response.status}`);
  const dataLine = text.split(/\r?\n/).find(line => line.startsWith("data:")); try { const payload = JSON.parse(dataLine ? dataLine.slice(5).trim() : text) as Record<string, unknown>; if (payload.error) throw new Error(String((payload.error as Record<string, unknown>).message ?? "product docs request failed")); return payload.result ?? payload; } catch { return { content: [{ type: "text", text }] }; }
}

function normalizeDocUrl(value: string) { if (!value.startsWith(previewDocsPrefix)) return value; let path = value.slice(previewDocsPrefix.length); const hash = path.indexOf("#"); const fragment = hash >= 0 ? path.slice(hash) : ""; if (hash >= 0) path = path.slice(0, hash); if (path.startsWith("solvea/bot_cn/")) return `${publicDocsPrefix}bot/${path.split("/").pop()}${fragment}`; return `${publicDocsPrefix}${path}${fragment}`; }
function textBlocks(value: unknown): string[] { const content = value && typeof value === "object" ? (value as Record<string, unknown>).content : undefined; return Array.isArray(content) ? content.flatMap(item => item && typeof item === "object" && typeof (item as Record<string, unknown>).text === "string" ? [String((item as Record<string, unknown>).text)] : []) : []; }
function parseDocBlock(text: string) { const result: Record<string, unknown> = {}; const content: string[] = []; let inContent = false; for (const line of text.split(/\r?\n/)) { if (inContent) content.push(line); else if (line.startsWith("Title: ")) result.title = line.slice(7).trim(); else if (line.startsWith("Link: ")) result.url = normalizeDocUrl(line.slice(6).trim()); else if (line.startsWith("Page: ")) result.page = line.slice(6).trim(); else if (line.startsWith("Content:")) { inContent = true; if (line.slice(8).trim()) content.push(line.slice(8).trim()); } } if (content.length) result.content = content.join("\n").trim(); return Object.keys(result).length ? result : { content: text } ; }
async function request(session: Session, method: string, path: string, body?: unknown) {
  const tenant = session.tenant; const base = tenant?.businessUrl?.replace(/\/$/, ""); if (!tenant || !base || !tenant.businessToken) throw new Error("no tenant selected");
  const cookie = tenant.environment === "prod" ? "_token" : "_token_staging";
  const response = await fetch(`${base}/api_v2/gpt${path}`, { method, headers: { accept: "application/json", ...(body === undefined ? {} : { "content-type": "application/json" }), cookie: `${cookie}=${tenant.businessToken}` }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30_000) });
  const value = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok || (value.code !== undefined && ![0, 200, "0", "200", "OK", "SUCCESS"].includes(value.code as never))) throw new Error(`support API failed: HTTP ${response.status}`);
  return value.data ?? value;
}

function portal(session: Session) { return session.tenant?.environment === "prod" ? "https://ai.solvea.cx" : "https://ai-staging.solvea.cx"; }

export async function runSupport(session: Session, action: string | undefined, args: string[]) {
  if (action === "list-tickets") return request(session, "POST", "/support/tickets", { page: Number(option(args, "--page") ?? 1), pageSize: Number(option(args, "--page-size") ?? 20) });
  if (action === "get-ticket") return request(session, "GET", `/support/tickets/${safe(option(args, "--ticket-number", true)!)}`);
  if (action === "append-message") return request(session, "POST", `/support/tickets/${safe(option(args, "--ticket-number", true)!)}/messages`, { content: option(args, "--content", true) });
  if (action === "create-ticket") {
    const attachments: unknown[] = [];
    for (const file of options(args, "--attachment")) {
      const form = new FormData(); form.append("file", new Blob([await readFile(file)]), basename(file));
      const tenant = session.tenant; const base = tenant?.businessUrl?.replace(/\/$/, ""); if (!tenant || !base || !tenant.businessToken) throw new Error("no tenant selected"); const cookie = tenant.environment === "prod" ? "_token" : "_token_staging";
      const uploaded = await fetch(`${base}/api_v2/gpt/support/tickets/attachments/upload`, { method: "POST", headers: { cookie: `${cookie}=${tenant.businessToken}` }, body: form, signal: AbortSignal.timeout(30_000) }); const payload = await uploaded.json() as Record<string, unknown>; if (!uploaded.ok) throw new Error(`attachment upload failed: HTTP ${uploaded.status}`); attachments.push(payload.data ?? payload);
    }
    const sourceId = process.env.CHAT_ID ?? ""; if (!sourceId) throw new Error("CHAT_ID is not configured");
    const ticket = await request(session, "POST", "/support/tickets/create", { content: option(args, "--content", true), sourceType: "cxclaw", sourceId, brand: option(args, "--brand"), issueType: option(args, "--issue-type") ?? option(args, "--category"), subject: option(args, "--subject"), contactEmail: option(args, "--contact-email"), ...(option(args, "--ext") ? { extFields: JSON.parse(option(args, "--ext")!) } : {}), ...(attachments.length ? { attachments } : {}) }) as Record<string, unknown>;
    const number = ticket.ticketNumber;
    await request(session, "POST", "/support/skill-metrics", { chatId: sourceId, ticketNumber: number }).catch(() => undefined);
    return { ticketNumber: number, ticketDetailUrl: number ? `${portal(session)}/chatbot#/support/tickets/${number}` : undefined, status: ticket.status, subject: ticket.subject, issueType: ticket.issueType, createdAt: ticket.createdAt };
  }
  if (action === "search-docs") { const query = option(args, "--query", true)!; const result = await docsTool("search_solvea", { query }); return { query, results: textBlocks(result).map(parseDocBlock) }; }
  if (action === "query-docs-filesystem") { const command = option(args, "--command", true)!; const result = await docsTool("query_docs_filesystem_solvea", { command }); return { command, output: textBlocks(result) }; }
  throw new Error("support action must be search-docs, list-tickets, get-ticket, create-ticket, or append-message");
}
