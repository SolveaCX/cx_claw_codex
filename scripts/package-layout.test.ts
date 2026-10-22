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
    expect(pkg.files).toContain("skills/**/scripts/**");
    expect(pkg.files).toContain("skills/__lib__/**");
    expect(pkg.files).toContain("skills/**/assets/**");
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

  test("locks the direct Python runtime dependencies", () => {
    const requirements = readFileSync("requirements-cli.txt", "utf8");
    for (const name of [
      "httpx",
      "boto3",
      "openpyxl",
      "beautifulsoup4",
      "openai",
      "pandas",
      "markdownify",
      "markdown",
      "jinja2",
    ]) {
      expect(requirements).toMatch(new RegExp(`^${name}==`, "m"));
    }
  });
});
