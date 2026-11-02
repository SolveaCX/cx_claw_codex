#!/usr/bin/env tsx

import { execFileSync, spawnSync } from "node:child_process";

const env = (name: string) => {
  const value = process.env[name];
  if (!value) throw new Error(`missing required environment variable: ${name}`);
  return value;
};

const headRef = env("PR_HEAD_REF");
const baseRef = env("PR_BASE_REF");
const title = env("PR_TITLE");

if (baseRef !== "main") {
  throw new Error(`pull requests must target main, got ${baseRef}`);
}

const releaseMatch = /^release\/v(\d+\.\d+\.\d+)$/.exec(headRef);
const developmentMatch = /^cxj\/\d{6}\/[a-z0-9][a-z0-9-]*$/.test(headRef);

if (releaseMatch) {
  const version = releaseMatch[1];
  const expectedTitle = `chore(release): 发布${version}`;
  if (title !== expectedTitle) {
    throw new Error(`release branch ${headRef} requires PR title: ${expectedTitle}`);
  }

  const tagExists = spawnSync(
    "git",
    ["ls-remote", "--exit-code", "origin", `refs/tags/v${version}`],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    },
  );
  if (tagExists.status === 0 && tagExists.stdout.trim()) {
    throw new Error(`release tag v${version} already exists; create a new release branch`);
  }

  const baseSha = env("PR_BASE_SHA");
  const headSha = env("PR_HEAD_SHA");
  const changed = execFileSync("git", ["diff", "--name-only", `${baseSha}...${headSha}`], {
    encoding: "utf8",
  })
    .trim()
    .split("\n")
    .filter(Boolean)
    .sort();
  const allowed = [".codex-plugin/plugin.json", "package.json", "plugin.json"];
  if (JSON.stringify(changed) !== JSON.stringify(allowed)) {
    throw new Error(
      `release PR may only change ${allowed.join(", ")}; got ${changed.join(", ") || "none"}`,
    );
  }
} else if (!developmentMatch) {
  throw new Error(`branch ${headRef} must match cxj/YYMMDD/topic or release/vX.Y.Z`);
} else if (/^chore\(release\): 发布/.test(title)) {
  throw new Error("release PR title is only allowed on release/vX.Y.Z branches");
}

console.log(`PR policy passed: ${headRef}`);
