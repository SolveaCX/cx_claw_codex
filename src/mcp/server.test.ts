import { describe, expect, test } from "bun:test";
import { createMcpAppHtml, LIVE_TEST_TOOL_META, TENANT_PANEL_TOOL_META } from "./server.js";

describe("tenant MCP App HTML", () => {
  test("embeds the bundled app without allowing a closing script tag", () => {
    const html = createMcpAppHtml('console.log("ok");</script><p>escaped</p>', "body{}");
    expect(html).toContain('<div id="root"></div>');
    expect(html).toContain("body{}");
    expect(html).toContain("<\\/script><p>escaped</p>");
    expect(html.match(/<\/script>/g)).toHaveLength(1);
  });
});

describe("tenant MCP App entrypoint", () => {
  test("registers the tenant panel in the conversation side panel", () => {
    expect(TENANT_PANEL_TOOL_META.ui.visibility).toEqual(["model", "app"]);
    expect(TENANT_PANEL_TOOL_META["openai/ui"].entrypoints).toEqual([{ type: "thread" }]);
  });

  test("binds only the LiveTest entry tool to its card", () => {
    expect(LIVE_TEST_TOOL_META.ui.resourceUri).toBe("ui://cxclaw/live-test");
  });
});
