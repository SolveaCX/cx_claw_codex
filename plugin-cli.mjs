#!/usr/bin/env node
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const manifest = JSON.parse(
  await readFile(new URL(".codex-plugin/plugin.json", import.meta.url), "utf8"),
);
const version = manifest.version;

if (!/^\d+\.\d+\.\d+(?:-(?:canary|dev)\.\d+)?$/.test(version)) {
  throw new Error(`invalid CXClaw plugin version: ${version}`);
}

const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const child = spawn(
  npx,
  ["--yes", `@shulex/cxclawctl@${version}`, ...process.argv.slice(2)],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      CXCLAW_PLUGIN_ROOT: root,
      CXCLAW_PLUGIN_VERSION: version,
    },
  },
);

child.on("error", (error) => {
  console.error(`cxclaw plugin launcher: ${error.message}`);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});
