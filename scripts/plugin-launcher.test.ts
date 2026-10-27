import { expect, test } from "bun:test";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { delimiter, join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const launcherTest = process.platform === "win32" ? test.skip : test;
const pluginVersion = JSON.parse(
  readFileSync(join(root, ".codex-plugin", "plugin.json"), "utf8"),
) as { version: string };

function runLauncher(command: string) {
  mkdirSync(join(root, "_tmp_"), { recursive: true });
  const fixture = mkdtempSync(join(root, "_tmp_", "plugin-launcher-"));
  const binDir = join(fixture, "bin");
  const mcpCwd = join(fixture, "mcp-cwd");
  const capturePath = join(fixture, "capture.json");
  mkdirSync(binDir);
  mkdirSync(mcpCwd);

  const fakeNpx = join(binDir, "npx");
  writeFileSync(
    fakeNpx,
    `#!/usr/bin/env node
import { writeFileSync } from "node:fs";
writeFileSync(process.env.CAPTURE_PATH, JSON.stringify({ cwd: process.cwd(), args: process.argv.slice(2) }));
`,
  );
  chmodSync(fakeNpx, 0o755);

  try {
    const result = Bun.spawnSync([process.execPath, join(root, "plugin-cli.mjs"), command], {
      cwd: root,
      env: {
        ...process.env,
        PATH: `${binDir}${delimiter}${process.env.PATH ?? ""}`,
        TMPDIR: mcpCwd,
        CAPTURE_PATH: capturePath,
      },
      stdout: "pipe",
      stderr: "pipe",
    });
    if (result.exitCode !== 0) {
      throw new Error(new TextDecoder().decode(result.stderr));
    }
    return JSON.parse(readFileSync(capturePath, "utf8")) as { cwd: string; args: string[] };
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
}

launcherTest("runs the MCP server outside the plugin package root", () => {
  const invocation = runLauncher("mcp-server");
  expect(invocation.cwd).not.toBe(root);
  expect(invocation.args).toEqual([
    "--yes",
    `@shulex/cxclawctl@${pluginVersion.version}`,
    "mcp-server",
  ]);
});

launcherTest("keeps the caller cwd for regular CLI commands", () => {
  const invocation = runLauncher("version");
  expect(invocation.cwd).toBe(root);
});
