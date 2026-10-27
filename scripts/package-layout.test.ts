import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const pkg = JSON.parse(readFileSync("package.json", "utf8")) as { files: string[] };
const launcher = readFileSync("plugin-cli.mjs", "utf8");

function files(root: string): string[] {
  return readdirSync(root).flatMap((name) => {
    const path = join(root, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

describe("release package layout", () => {
  test("keeps documentation in the plugin and runtime code in npm", () => {
    expect(pkg.files).not.toContain("skills");
    expect(pkg.files).not.toContain("skills/**/scripts/**");
    expect(pkg.files).not.toContain("skills/__lib__/**");
  });

  test("pins CLI execution to the plugin manifest version", () => {
    expect(launcher).toContain('.codex-plugin/plugin.json');
    expect(launcher).toContain("`@shulex/cxclawctl@${version}`");
    expect(launcher).toContain("CXCLAW_PLUGIN_VERSION: version");
  });

  test("all skills use the plugin launcher instead of npm latest", () => {
    const text = files("skills").map((path) => readFileSync(path, "utf8")).join("\n");
    expect(text).not.toContain("@shulex/cxclawctl@latest");
    expect(text).toContain('node "<PLUGIN_ROOT>/plugin-cli.mjs"');
  });

  test("both plugin archives include the launcher", () => {
    expect(readFileSync("scripts/package-agent-plugin.mjs", "utf8")).toContain(
      '"plugin-cli.mjs"',
    );
    expect(readFileSync("scripts/package-codex-plugin.mjs", "utf8")).toContain(
      '"plugin-cli.mjs"',
    );
  });

  test("packages the SLG branded plugin icon in both formats", () => {
    const portableManifest = JSON.parse(readFileSync("plugin.json", "utf8"));
    const codexManifest = JSON.parse(readFileSync(".codex-plugin/plugin.json", "utf8"));
    const portableInterface = portableManifest.extensions["com.openai"].interface;
    const icon = readFileSync("assets/cxclaw.svg", "utf8");

    for (const interfaceConfig of [portableInterface, codexManifest.interface]) {
      expect(interfaceConfig.brandColor).toBe("#1D65F5");
      expect(interfaceConfig.logo).toBe("./assets/cxclaw.svg");
      expect(interfaceConfig.composerIcon).toBe("./assets/cxclaw.svg");
    }
    expect(icon).toContain('viewBox="0 0 48 48"');
    expect(icon).toContain('fill="#1D65F5"');
    expect(readFileSync("scripts/package-agent-plugin.mjs", "utf8")).toContain('"assets"');
    expect(readFileSync("scripts/package-codex-plugin.mjs", "utf8")).toContain('"assets"');
  });

  test("both plugin formats include the tenant panel MCP server", () => {
    const portableManifest = readFileSync("mcp.json", "utf8");
    const compatibilityManifest = readFileSync(".mcp.json", "utf8");
    const codexManifest = readFileSync(".codex-plugin/plugin.json", "utf8");
    expect(portableManifest).toContain('"type": "stdio"');
    expect(portableManifest).toContain('"mcp-server"');
    expect(compatibilityManifest).toContain('"mcp-server"');
    expect(codexManifest).toContain('"mcpServers": "./.mcp.json"');
    expect(readFileSync("scripts/package-agent-plugin.mjs", "utf8")).toContain('"mcp.json"');
    expect(readFileSync("scripts/package-codex-plugin.mjs", "utf8")).toContain('".mcp.json"');
  });

  test("uses explicit CLI login and packages no authorization hooks", () => {
    const portableManifest = readFileSync("plugin.json", "utf8");
    const codexManifest = readFileSync(".codex-plugin/plugin.json", "utf8");
    expect(portableManifest).not.toContain('"hooks"');
    expect(codexManifest).not.toContain('"hooks"');
    expect(readFileSync("scripts/package-agent-plugin.mjs", "utf8")).not.toContain('"hooks"');
    expect(readFileSync("scripts/package-codex-plugin.mjs", "utf8")).not.toContain('"hooks"');
    expect(pkg.files).not.toContain("runtime");
  });

  test("refreshes the installed plugin after upgrading its marketplace", () => {
    const updater = readFileSync("src/update.ts", "utf8");
    const marketplaceUpgrade = updater.indexOf(
      '["plugin", "marketplace", "upgrade", "cxclaw"]',
    );
    const pluginInstall = updater.indexOf('["plugin", "add", "cxclaw@cxclaw"]');
    const pluginList = updater.indexOf('["plugin", "list", "--json"]');
    expect(marketplaceUpgrade).toBeGreaterThan(0);
    expect(pluginInstall).toBeGreaterThan(marketplaceUpgrade);
    expect(pluginList).toBeGreaterThan(pluginInstall);
  });

  test("does not package a Python runtime", () => {
    expect(pkg.files.some(path => path.includes("python") || path.includes("requirements"))).toBe(false);
  });

  test("keeps the native TypeScript API boundary separate from the legacy fallback", () => {
    const business = readFileSync("src/business.ts", "utf8");
    const commands = readFileSync("src/solvea/commands.ts", "utf8");
    expect(business).toContain("runSolveaCommand");
    expect(commands).toContain("TypeScript command not migrated yet");
    expect(commands).not.toContain("spawn(");
    expect(business).not.toContain("runPython");
  });
});
