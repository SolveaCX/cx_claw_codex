import { describe, expect, test } from "bun:test";
import { createTenantPanelHtml, TENANT_PANEL_TOOL_META } from "./server.js";

describe("tenant MCP App HTML", () => {
  test("embeds the bundled app without allowing a closing script tag", () => {
    const html = createTenantPanelHtml('console.log("ok");</script><p>escaped</p>');
    expect(html).toContain("CXClaw · 全局当前租户");
    expect(html).toContain("<\\/script><p>escaped</p>");
    expect(html.match(/<\/script>/g)).toHaveLength(1);
  });
});

describe("tenant MCP App entrypoint", () => {
  test("registers the tenant panel in the conversation side panel", () => {
    expect(TENANT_PANEL_TOOL_META.ui.visibility).toEqual(["model", "app"]);
    expect(TENANT_PANEL_TOOL_META["openai/ui"].entrypoints).toEqual([{ type: "thread" }]);
  });
});
