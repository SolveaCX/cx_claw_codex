#!/usr/bin/env tsx

import { execFileSync, spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compareVersions } from "compare-versions";

const ROOT = resolve(import.meta.dirname, "..");
const STABLE_VERSION = /^\d+\.\d+\.\d+$/;
const RELEASE_FILES = [
  ".codex-plugin/plugin.json",
  "capabilities.lock.json",
  "package.json",
  "plugin.json",
];

export type VersionInput = "major" | "minor" | "patch" | string;

export function resolveReleaseVersion(current: string, input: VersionInput): string {
  if (!STABLE_VERSION.test(current)) throw new Error(`main has invalid stable version: ${current}`);
  const [major, minor, patch] = current.split(".").map(Number) as [number, number, number];
  const version = input === "major"
    ? `${major + 1}.0.0`
    : input === "minor"
      ? `${major}.${minor + 1}.0`
      : input === "patch"
        ? `${major}.${minor}.${patch + 1}`
        : input;

  if (!STABLE_VERSION.test(version)) {
    throw new Error("release version must be major, minor, patch, or X.Y.Z");
  }
  if (compareVersions(version, current) <= 0) {
    throw new Error(`release version ${version} must be greater than ${current}`);
  }
  return version;
}

export function releaseBranch(version: string) {
  return `release/v${version}`;
}

export function releasePullRequestBody(version: string) {
  return `## 发布内容

- 发布 CXClaw \`${version}\`
- 同步 npm CLI、Codex 插件和能力清单版本

## 发布前检查

- TypeScript 类型检查
- 单元测试
- CLI 构建与安装包测试
- 能力清单与版本一致性检查
- Agent Plugin、Codex Plugin 和 npm 包生成

合并后 Publish workflow 将发布 \`@shulex/cxclawctl@${version}\`、GitHub Release \`v${version}\`，并推进 \`marketplace/stable\`。`;
}

function capture(command: string, args: string[]) {
  return execFileSync(command, args, { cwd: ROOT, encoding: "utf8" }).trim();
}

function run(command: string, args: string[]) {
  execFileSync(command, args, { cwd: ROOT, stdio: "inherit" });
}

function succeeds(command: string, args: string[]) {
  return spawnSync(command, args, { cwd: ROOT, stdio: "ignore" }).status === 0;
}

function assertCleanWorkingTree() {
  if (capture("git", ["status", "--porcelain"])) {
    throw new Error("working tree must be clean before creating a release");
  }
}

function changedPaths() {
  const tracked = capture("git", ["diff", "--name-only", "HEAD"]);
  const untracked = capture("git", ["ls-files", "--others", "--exclude-standard"]);
  return [...new Set(`${tracked}\n${untracked}`.split("\n").filter(Boolean))].sort();
}

function main() {
  const input = process.argv[2];
  if (!input) throw new Error("usage: bun run release:create <major|minor|patch|X.Y.Z>");

  assertCleanWorkingTree();
  run("git", ["fetch", "origin", "main", "--tags", "--prune"]);
  run("gh", ["auth", "status"]);

  const mainPackage = JSON.parse(capture("git", ["show", "origin/main:package.json"])) as { version?: string };
  const current = mainPackage.version;
  if (!current) throw new Error("origin/main package.json has no version");

  const version = resolveReleaseVersion(current, input);
  const branch = releaseBranch(version);
  if (succeeds("git", ["show-ref", "--verify", "--quiet", `refs/heads/${branch}`])) {
    throw new Error(`local branch already exists: ${branch}`);
  }
  if (succeeds("git", ["ls-remote", "--exit-code", "--heads", "origin", branch])) {
    throw new Error(`remote branch already exists: ${branch}`);
  }

  console.log(`Creating CXClaw ${version} from origin/main (${current})`);
  run("git", ["switch", "-c", branch, "origin/main"]);
  run("bun", ["install", "--frozen-lockfile"]);
  run("bun", ["run", "release:prepare", version]);

  for (const [command, args] of [
    ["bun", ["run", "typecheck"]],
    ["bun", ["test"]],
    ["bun", ["run", "build"]],
    ["bun", ["run", "test:package"]],
    ["bun", ["run", "check:capabilities"]],
    ["bun", ["run", "check:release"]],
    ["bun", ["run", "package:agent-plugin"]],
    ["bun", ["run", "package:codex-plugin"]],
    ["npm", ["pack", "--dry-run"]],
  ] as const) run(command, [...args]);
  run("git", ["diff", "--check"]);

  const changed = changedPaths();
  if (JSON.stringify(changed) !== JSON.stringify(RELEASE_FILES)) {
    throw new Error(`unexpected release files: ${changed.join(", ") || "none"}`);
  }

  run("git", ["add", ...RELEASE_FILES]);
  run("git", ["commit", "-m", `chore(release): 发布${version}`]);
  run("git", ["push", "-u", "origin", branch]);
  const url = capture("gh", [
    "pr", "create",
    "--base", "main",
    "--head", branch,
    "--title", `chore(release): 发布${version}`,
    "--body", releasePullRequestBody(version),
  ]);
  console.log(`Release PR created: ${url}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
