import { readFile } from "node:fs/promises";
import { McpServer } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { OpenAIExtensions } from "@openai/mcp-extensions/server";
import type { OpenAIUiToolMetadata } from "@openai/mcp-extensions/server";
import { z } from "zod";
import { VERSION } from "../version.js";
import {
  LiveTestRunInputSchema,
  LiveTestSnapshotOutputSchema,
  LiveTestStartInputSchema,
  LiveTestStartOutputSchema,
  LiveTestStatusInputSchema,
  LiveTestTranscriptOutputSchema,
} from "./apps/live-test/contract.js";
import { LiveTestService } from "./apps/live-test/service.js";
import { loadTenantPanelStatus } from "./tenant-status.js";

const TENANT_PANEL_URI = "ui://cxclaw/tenant-status";
const LIVE_TEST_URI = "ui://cxclaw/live-test/v2.html";
const MCP_APP_MIME_TYPE = "text/html;profile=mcp-app";
const DEVELOPMENT_MODE = process.env.CXCLAW_PLUGIN_DEV === "1";

export const TENANT_PANEL_TOOL_META = {
  ui: { resourceUri: TENANT_PANEL_URI, visibility: ["model", "app"] },
  "openai/ui": { entrypoints: [{ type: "thread" }] } satisfies OpenAIUiToolMetadata,
};
export const LIVE_TEST_TOOL_META = {
  ui: { resourceUri: LIVE_TEST_URI, visibility: ["model", "app"] },
};
const LIVE_TEST_HELPER_META = { ui: { visibility: ["model", "app"] } };

type ViteManifestEntry = { file: string; css?: string[]; isEntry?: boolean };
export function resolveMcpAppCssFiles(
  manifest: Record<string, ViteManifestEntry>,
  entry: ViteManifestEntry,
): string[] {
  return [
    ...new Set([
      ...(entry.css ?? []),
      ...Object.values(manifest)
        .map((item) => item.file)
        .filter((file) => file.endsWith(".css")),
    ]),
  ];
}

export function createMcpAppHtml(script: string, styles = ""): string {
  const installStyles = styles
    ? `const cxclawStyle=document.createElement("style");cxclawStyle.textContent=${JSON.stringify(styles)};document.head.appendChild(cxclawStyle);`
    : "";
  const safeScript = `${installStyles}${script}`.replace(/<\/script/gi, "<\\/script");
  return `<div id="root"></div><script type="module">${safeScript}</script>`;
}

async function loadMcpAppHtml(appName: string) {
  const directory = new URL(`./mcp-apps/${appName}/`, import.meta.url);
  const manifest = JSON.parse(
    await readFile(new URL("manifest.json", directory), "utf8"),
  ) as Record<string, ViteManifestEntry>;
  const entry = Object.values(manifest).find((item) => item.isEntry);
  if (!entry) throw new Error(`Vite manifest has no entry for ${appName}`);
  const script = await readFile(new URL(entry.file, directory), "utf8");
  const cssFiles = resolveMcpAppCssFiles(manifest, entry);
  const styles = (
    await Promise.all(cssFiles.map((file) => readFile(new URL(file, directory), "utf8")))
  ).join("\n");
  return createMcpAppHtml(script, styles);
}

const result = (summary: string, structuredContent: Record<string, unknown>) => ({
  content: [{ type: "text" as const, text: summary }],
  structuredContent,
});

function buildCxclawMcpServer(service: LiveTestService): McpServer {
  const name = DEVELOPMENT_MODE ? "cxclaw-dev" : "cxclaw";
  const tenantTitle = DEVELOPMENT_MODE ? "CXClaw Dev 当前租户" : "CXClaw 当前租户";
  const server = new McpServer({ name, version: VERSION });
  new OpenAIExtensions(server);

  server.registerResource(
    "CXClaw current tenant panel",
    TENANT_PANEL_URI,
    { title: tenantTitle, mimeType: MCP_APP_MIME_TYPE },
    async () => ({
      contents: [
        {
          uri: TENANT_PANEL_URI,
          mimeType: MCP_APP_MIME_TYPE,
          text: await loadMcpAppHtml("tenant-status"),
        },
      ],
    }),
  );
  server.registerResource(
    "CXClaw LiveTest",
    LIVE_TEST_URI,
    { title: "Agent LiveTest", mimeType: MCP_APP_MIME_TYPE },
    async () => ({
      contents: [
        {
          uri: LIVE_TEST_URI,
          mimeType: MCP_APP_MIME_TYPE,
          text: await loadMcpAppHtml("live-test"),
        },
      ],
    }),
  );

  server.registerTool(
    "tenant.current",
    {
      title: tenantTitle,
      description: "读取指定 CXClaw context 当前选择的租户，仅返回非敏感展示字段。",
      inputSchema: z.object({ contextId: z.string().optional() }),
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
      _meta: TENANT_PANEL_TOOL_META,
    },
    async ({ contextId }) => {
      const status = await loadTenantPanelStatus(contextId);
      return result(
        status.contextRequired
          ? "需要传入 contextId"
          : status.configured
            ? `当前租户：${status.companyName ?? status.accountName ?? status.accountId}`
            : "当前 context 未选择租户",
        status as unknown as Record<string, unknown>,
      );
    },
  );

  server.registerTool(
    "live_test.start",
    {
      title: "开始 Agent LiveTest",
      description: "在当前 CXClaw 租户中启动指定 Agent 的单轮或多轮真实链路测试。",
      inputSchema: LiveTestStartInputSchema,
      outputSchema: LiveTestStartOutputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: false,
      },
      _meta: LIVE_TEST_TOOL_META,
    },
    async (input) => {
      const output = await service.start(input);
      return result(`LiveTest ${output.testRunId} 已启动`, output);
    },
  );
  server.registerTool(
    "live_test.status",
    {
      title: "读取 Agent LiveTest 状态",
      description: "读取 LiveTest 当前快照，可等待 revision 变化。",
      inputSchema: LiveTestStatusInputSchema,
      outputSchema: LiveTestSnapshotOutputSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
      _meta: LIVE_TEST_HELPER_META,
    },
    async ({ contextId, testRunId, afterRevision, waitMs }) => {
      const output = await service.status(contextId, testRunId, afterRevision, waitMs);
      return result(`LiveTest 状态：${output.snapshot.status}`, output);
    },
  );
  server.registerTool(
    "live_test.cancel",
    {
      title: "取消 Agent LiveTest",
      description: "取消当前租户上下文中的 LiveTest。",
      inputSchema: LiveTestRunInputSchema,
      outputSchema: LiveTestSnapshotOutputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
      _meta: LIVE_TEST_HELPER_META,
    },
    async ({ contextId, testRunId }) => {
      const output = await service.cancel(contextId, testRunId);
      return result(`LiveTest 状态：${output.snapshot.status}`, output);
    },
  );
  server.registerTool(
    "live_test.transcript",
    {
      title: "读取 Agent LiveTest 执行详情",
      description: "读取属于当前租户 LiveTest 的完整 transcript。",
      inputSchema: LiveTestRunInputSchema,
      outputSchema: LiveTestTranscriptOutputSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
      _meta: LIVE_TEST_HELPER_META,
    },
    async ({ contextId, testRunId }) => {
      const output = await service.transcript(contextId, testRunId);
      return result(`已读取 LiveTest ${testRunId} 的执行详情`, output);
    },
  );
  return server;
}

export function createCxclawMcpServer(): McpServer {
  return buildCxclawMcpServer(new LiveTestService());
}
export const createTenantMcpServer = createCxclawMcpServer;
export function serveTenantMcp(): void {
  serveStdio(createCxclawMcpServer);
}
