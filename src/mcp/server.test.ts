import { describe, expect, test } from "bun:test";
import { createTenantPanelHtml } from "./server.js";

describe("tenant MCP App HTML", () => {
  test("embeds the bundled app without allowing a closing script tag", () => {
    const html = createTenantPanelHtml('console.log("ok");</script><p>escaped</p>');
    expect(html).toContain("CXClaw · 全局当前租户");
    expect(html).toContain("<\\/script><p>escaped</p>");
    expect(html.match(/<\/script>/g)).toHaveLength(1);
  });
});
