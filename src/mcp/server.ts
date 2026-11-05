import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { McpServer } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { OpenAIExtensions } from "@openai/mcp-extensions/server";
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

const MCP_APP_MIME_TYPE = "text/html;profile=mcp-app";
const DEVELOPMENT_MODE = process.env.CXCLAW_PLUGIN_DEV === "1";

export function mcpAppContentHash(content: string): string {
  return createHash("sha256").update(content).digest("hex").slice(0, 12);
}

export function createMcpAppUri(appName: string, contentHash: string): string {
  if (!/^[a-f0-9]{12}$/.test(contentHash)) throw new Error("invalid MCP App content hash");
  return `ui://cxclaw/${appName}/${contentHash}.html`;
}

function builtMcpAppDirectory(appName: string): URL | undefined {
  const candidates = [
    new URL(`./mcp-apps/${appName}/`, import.meta.url),
    new URL(`../../dist/mcp-apps/${appName}/`, import.meta.url),
  ];
  return candidates.find((directory) => {
    try {
      readFileSync(new URL("manifest.json", directory));
      return true;
    } catch {
      return false;
    }
  });
}

function resolveMcpAppContentHash(appName: string): string {
  const directory = builtMcpAppDirectory(appName);
  if (!directory) return mcpAppContentHash(`unbuilt:${appName}`);
  const manifest = JSON.parse(readFileSync(new URL("manifest.json", directory), "utf8")) as Record<
    string,
    ViteManifestEntry
  >;
  const entry = Object.values(manifest).find((item) => item.isEntry);
  if (!entry) throw new Error(`Vite manifest has no entry for ${appName}`);
  const script = readFileSync(new URL(entry.file, directory), "utf8");
  const styles = resolveMcpAppCssFiles(manifest, entry)
    .map((file) => readFileSync(new URL(file, directory), "utf8"))
    .join("\n");
  return mcpAppContentHash(createMcpAppHtml(script, styles));
}

const TENANT_PANEL_URI = createMcpAppUri(
  "tenant-status",
  resolveMcpAppContentHash("tenant-status"),
);
const LIVE_TEST_URI = createMcpAppUri("live-test", resolveMcpAppContentHash("live-test"));

export const TENANT_PANEL_TOOL_META = {
  ui: { resourceUri: TENANT_PANEL_URI, visibility: ["model", "app"] },
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
  const directory = builtMcpAppDirectory(appName);
  if (!directory) throw new Error(`MCP App build is missing for ${appName}`);
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

export const TenantCurrentInputSchema = z.object({ contextId: z.string().min(1) });

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
      inputSchema: TenantCurrentInputSchema,
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
        status.configured
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
      description:
        "在当前 CXClaw 租户中启动 CHAT_FLOW 或 SINGLE_AGENT 的单轮或多轮真实链路测试。CHAT_FLOW 自动解析版本，SINGLE_AGENT 不接受 flowVersion。",
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
