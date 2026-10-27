import { afterAll, describe, expect, test } from "bun:test";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { prepareDeveloperPlugin } from "./dev-plugin.js";

const output = join(import.meta.dirname, "..", "_tmp_", "codex-plugin-dev-test");
const plugin = join(output, "plugins", "cxclaw-dev");

afterAll(() => rmSync(output, { recursive: true, force: true }));

describe("local development plugin", () => {
  test("uses separate identities and runs the workspace bundle", async () => {
    await prepareDeveloperPlugin(output);

    const marketplace = JSON.parse(readFileSync(join(output, ".agents", "plugins", "marketplace.json"), "utf8"));
    const manifest = JSON.parse(readFileSync(join(plugin, "plugin.json"), "utf8"));
    const compatibility = JSON.parse(readFileSync(join(plugin, ".codex-plugin", "plugin.json"), "utf8"));
    const launcher = readFileSync(join(plugin, "plugin-cli.dev.mjs"), "utf8");

    expect(marketplace.name).toBe("cxclaw-dev");
    expect(marketplace.plugins[0].source.path).toBe("./plugins/cxclaw-dev");
    expect(manifest.name).toBe("cxclaw-dev");
    expect(manifest.extensions["com.openai"].interface.displayName).toBe("CXClaw Dev");
    expect(compatibility.mcpServers).toBeUndefined();
    expect(existsSync(join(plugin, "mcp.json"))).toBeFalse();
    expect(existsSync(join(plugin, ".mcp.json"))).toBeFalse();
    expect(launcher).toContain(join(import.meta.dirname, "..", "dist", "cli.js"));
    expect(launcher).not.toContain("npx");
  });
});
