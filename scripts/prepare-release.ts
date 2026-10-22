import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { compareVersions } from "compare-versions";

const version = process.argv[2];
const pattern = /^\d+\.\d+\.\d+(?:-(?:canary|dev)\.\d+)?$/;
if (!version || !pattern.test(version)) {
  throw new Error("usage: bun run release:prepare <X.Y.Z|X.Y.Z-canary.N|X.Y.Z-dev.N>");
}

const status = execFileSync("git", ["status", "--porcelain"], { encoding: "utf8" }).trim();
if (status) throw new Error("working tree must be clean before preparing a release");

const packageJson = JSON.parse(readFileSync("package.json", "utf8")) as { version: string };
if (compareVersions(version, packageJson.version) <= 0) {
  throw new Error(`new version ${version} must be greater than ${packageJson.version}`);
}

for (const path of ["package.json", "plugin.json", ".codex-plugin/plugin.json"]) {
  const source = readFileSync(path, "utf8");
  const updated = source.replace(/("version"\s*:\s*)"[^"]+"/, `$1"${version}"`);
  if (updated === source) throw new Error(`version field not found in ${path}`);
  writeFileSync(path, updated);
}

execFileSync("python3", ["scripts/check_capabilities.py", "--write"], { stdio: "inherit" });
console.log(`Prepared CXClaw ${version}`);
if (version.includes("-")) {
  console.log(`Commit the changes, then push tag v${version} to publish the prerelease.`);
} else {
  console.log(`Commit the changes on release/v${version}, open a PR to main, and merge it to publish.`);
}
