import { describe, expect, test } from "bun:test";
import {
  createMcpAppUri,
  createMcpAppHtml,
  LIVE_TEST_TOOL_META,
  mcpAppContentHash,
  resolveMcpAppCssFiles,
  TENANT_PANEL_TOOL_META,
} from "./server.js";

describe("tenant MCP App HTML", () => {
  test("embeds the bundled app without allowing a closing script tag", () => {
    const html = createMcpAppHtml('console.log("ok");</script><p>escaped</p>', "body{}");
    expect(html).toContain('<div id="root"></div>');
    expect(html).toContain('cxclawStyle.textContent="body{}"');
    expect(html).toContain("document.head.appendChild(cxclawStyle)");
    expect(html).toContain("<\\/script><p>escaped</p>");
    expect(html.match(/<\/script>/g)).toHaveLength(1);
  });

  test("includes standalone CSS manifest assets", () => {
    const entry = { file: "live-test.js", css: ["shared.css"], isEntry: true };
    expect(
      resolveMcpAppCssFiles(
        {
          "src/live-test/main.tsx": entry,
          "style.css": { file: "live-test.css" },
          "duplicate.css": { file: "shared.css" },
        },
        entry,
      ),
    ).toEqual(["shared.css", "live-test.css"]);
  });

  test("uses a stable content hash that changes with the final app HTML", () => {
    expect(mcpAppContentHash("same")).toBe(mcpAppContentHash("same"));
    expect(mcpAppContentHash("same")).not.toBe(mcpAppContentHash("changed"));
    expect(createMcpAppUri("live-test", "0123456789ab")).toBe(
      "ui://cxclaw/live-test/0123456789ab.html",
    );
  });
});

describe("tenant MCP App entrypoint", () => {
  test("registers the tenant panel in the conversation side panel", () => {
    expect(TENANT_PANEL_TOOL_META.ui.resourceUri).toMatch(
      /^ui:\/\/cxclaw\/tenant-status\/[a-f0-9]{12}\.html$/,
    );
    expect(TENANT_PANEL_TOOL_META.ui.visibility).toEqual(["model", "app"]);
    expect(TENANT_PANEL_TOOL_META["openai/ui"].entrypoints).toEqual([{ type: "thread" }]);
  });

  test("binds only the LiveTest entry tool to its card", () => {
    expect(LIVE_TEST_TOOL_META.ui.resourceUri).toMatch(
      /^ui:\/\/cxclaw\/live-test\/[a-f0-9]{12}\.html$/,
    );
  });
});
