import { afterAll, describe, expect, test } from "bun:test";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { prepareDeveloperPlugin, syncDeveloperPluginToPlaygrounds } from "./dev-plugin.js";

const output = join(import.meta.dirname, "..", "_tmp_", "codex-plugin-dev-test");
const plugin = join(output, "plugins", "cxclaw-dev");
const workspace = join(import.meta.dirname, "..", "_tmp_", "codex-plugin-workspace-test");

afterAll(() => {
  rmSync(output, { recursive: true, force: true });
  rmSync(workspace, { recursive: true, force: true });
});

describe("local development plugin", () => {
  test("uses separate identities and runs the workspace bundle", async () => {
    await prepareDeveloperPlugin(output);

    const marketplace = JSON.parse(
      readFileSync(join(output, ".agents", "plugins", "marketplace.json"), "utf8"),
    );
    const manifest = JSON.parse(readFileSync(join(plugin, "plugin.json"), "utf8"));
    const mcp = JSON.parse(readFileSync(join(plugin, "mcp.json"), "utf8"));
    const launcher = readFileSync(join(plugin, "plugin-cli.dev.mjs"), "utf8");

    expect(marketplace.name).toBe("cxclaw-dev");
    expect(marketplace.plugins[0].source.path).toBe("./plugins/cxclaw-dev");
    expect(manifest.name).toBe("cxclaw-dev");
    expect(manifest.extensions["com.openai"].interface.displayName).toBe("CXClaw Dev");
    expect(manifest.extensions["com.openai"].interface.logo).toBe("./assets/cxclaw.svg");
    expect(readFileSync(join(plugin, "assets", "cxclaw.svg"), "utf8")).toContain("#1D65F5");
    expect(mcp.mcpServers["tenant-panel-dev"].args[0]).toBe("${PLUGIN_ROOT}/plugin-cli.dev.mjs");
    expect(launcher).toContain(join(import.meta.dirname, "..", "dist", "cli.js"));
    expect(launcher).not.toContain("npx");
  });

  test("enables the plugin only in the exact top-level playground directory", async () => {
    await prepareDeveloperPlugin(output);
    const playground = join(workspace, "playground");
    const fuzzyMatch = join(workspace, "local-playground");
    mkdirSync(playground, { recursive: true });
    mkdirSync(join(fuzzyMatch, ".codex"), { recursive: true });
    writeFileSync(
      join(playground, ".codex-placeholder"),
      "project content must remain untouched\n",
    );
    writeFileSync(join(playground, "AGENTS.md"), "# Existing instructions\n\nKeep this rule.\n");

    const synced = await syncDeveloperPluginToPlaygrounds(output, workspace);

    expect(synced).toEqual([playground]);
    expect(
      JSON.parse(readFileSync(join(playground, ".agents", "plugins", "marketplace.json"), "utf8"))
        .plugins[0].source.path,
    ).toBe("./.codex/plugins/cxclaw-dev");
    expect(readFileSync(join(playground, ".codex", "config.toml"), "utf8")).toContain(
      'plugins."cxclaw-dev@cxclaw-dev"',
    );
    expect(readFileSync(join(playground, ".codex-placeholder"), "utf8")).toContain(
      "project content",
    );
    expect(readFileSync(join(playground, "AGENTS.md"), "utf8")).toContain("用户没有明确要求时");
    expect(readFileSync(join(playground, "AGENTS.md"), "utf8")).toContain("Keep this rule.");
    expect(() => readFileSync(join(fuzzyMatch, ".codex", "config.toml"), "utf8")).toThrow();
  });
});
