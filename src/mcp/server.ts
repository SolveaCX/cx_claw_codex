import { readFile } from "node:fs/promises";
import { McpServer } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { OpenAIExtensions } from "@openai/mcp-extensions/server";
import type { OpenAIUiToolMetadata } from "@openai/mcp-extensions/server";
import { VERSION } from "../version.js";
import { loadTenantPanelStatus } from "./tenant-status.js";

const TENANT_PANEL_URI = "ui://cxclaw/tenant-status";
const MCP_APP_MIME_TYPE = "text/html;profile=mcp-app";
const DEVELOPMENT_MODE = process.env.CXCLAW_PLUGIN_DEV === "1";
export const TENANT_PANEL_TOOL_META = {
  ui: { resourceUri: TENANT_PANEL_URI, visibility: ["model", "app"] },
  "openai/ui": { entrypoints: [{ type: "thread" }] } satisfies OpenAIUiToolMetadata,
};

export function createTenantPanelHtml(script: string): string {
  const safeScript = script.replace(/<\/script/gi, "<\\/script");
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { color-scheme: light dark; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px 16px 16px; color: var(--color-text-primary, CanvasText); background: transparent; }
    .header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
    .eyebrow { margin: 0 0 6px; color: var(--color-text-secondary, GrayText); font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
    h1 { margin: 0; font-size: 18px; line-height: 1.35; }
    .summary { min-height: 40px; margin: 8px 0 18px; color: var(--color-text-secondary, GrayText); font-size: 13px; line-height: 1.5; }
    button { border: 1px solid var(--color-border-secondary, ButtonBorder); border-radius: 8px; padding: 7px 10px; color: inherit; background: var(--color-background-secondary, ButtonFace); cursor: pointer; }
    button:disabled { cursor: wait; opacity: .55; }
    .environment { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 8px; font-size: 11px; font-weight: 700; }
    .environment[data-environment="prod"] { color: #b42318; background: #fee4e2; }
    .environment[data-environment="staging"] { color: #93370d; background: #fef0c7; }
    .environment[data-environment="none"] { color: var(--color-text-secondary, GrayText); background: var(--color-background-secondary, ButtonFace); }
    dl { display: grid; grid-template-columns: minmax(88px, auto) 1fr; gap: 0; margin: 0; border-top: 1px solid var(--color-border-secondary, rgba(127,127,127,.25)); }
    dt, dd { margin: 0; padding: 11px 0; border-bottom: 1px solid var(--color-border-secondary, rgba(127,127,127,.25)); font-size: 13px; }
    dt { color: var(--color-text-secondary, GrayText); }
    dd { min-width: 0; text-align: right; overflow-wrap: anywhere; font-weight: 550; }
    .footer { margin: 12px 0 0; color: var(--color-text-secondary, GrayText); font-size: 11px; text-align: right; }
    body[data-state="expired"] h1, body[data-state="unavailable"] h1 { color: #b42318; }
  </style>
</head>
<body data-state="loading">
  <div class="header">
    <div>
      <p class="eyebrow">CXClaw${DEVELOPMENT_MODE ? " Dev" : ""} · 全局当前租户</p>
      <h1 id="headline">正在读取租户信息…</h1>
    </div>
    <button id="refresh" class="cursor-interaction" type="button">刷新</button>
  </div>
  <p id="summary" class="summary">租户切换后，面板会自动更新。</p>
  <dl>
    <dt>环境</dt><dd><span id="environment" class="environment" data-environment="none">未选择</span></dd>
    <dt>Account ID</dt><dd id="account-id">—</dd>
    <dt>Account Code</dt><dd id="account-code">—</dd>
    <dt>用途</dt><dd id="purpose">—</dd>
    <dt>凭据到期</dt><dd id="expires-at">—</dd>
  </dl>
  <p id="checked-at" class="footer">尚未更新</p>
  <script>${safeScript}</script>
</body>
</html>`;
}

async function tenantPanelHtml(): Promise<string> {
  const script = await readFile(new URL("./tenant-panel.js", import.meta.url), "utf8");
  return createTenantPanelHtml(script);
}

export function createTenantMcpServer(): McpServer {
  const name = DEVELOPMENT_MODE ? "cxclaw-dev" : "cxclaw";
  const title = DEVELOPMENT_MODE ? "CXClaw Dev 当前租户" : "CXClaw 当前租户";
  const server = new McpServer({ name, version: VERSION });
  new OpenAIExtensions(server);

  server.registerResource(
    "CXClaw current tenant panel",
    TENANT_PANEL_URI,
    { title, mimeType: MCP_APP_MIME_TYPE },
    async () => ({
      contents: [{
        uri: TENANT_PANEL_URI,
        mimeType: MCP_APP_MIME_TYPE,
        text: await tenantPanelHtml(),
      }],
    }),
  );

  server.registerTool(
    "tenant.current",
    {
      title,
      description: "读取本机 CXClaw 当前选择的全局租户，仅返回非敏感展示字段。",
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
      _meta: TENANT_PANEL_TOOL_META,
    },
    async () => {
      const status = await loadTenantPanelStatus();
      return {
        content: [{ type: "text", text: status.configured ? `当前租户：${status.accountName ?? status.accountId}` : "当前未选择租户" }],
        structuredContent: status,
      };
    },
  );

  return server;
}

export function serveTenantMcp(): void {
  serveStdio(createTenantMcpServer);
}
