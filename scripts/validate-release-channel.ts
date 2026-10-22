import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

type ReleaseInput = {
  version: string;
  channel: string;
  eventName: string;
  prHeadRef: string;
  manifestVersions: string[];
};

export function validateReleaseChannel(input: ReleaseInput): void {
  const { version, channel, eventName, prHeadRef, manifestVersions } = input;
  if (manifestVersions.some((value) => value !== version)) {
    throw new Error(`release version ${version} does not match manifests: ${manifestVersions.join(", ")}`);
  }

  const prerelease = version.match(/^\d+\.\d+\.\d+-(canary|dev)\.\d+$/);
  const stable = /^\d+\.\d+\.\d+$/.test(version);

  if (eventName === "push") {
    if (!prerelease) throw new Error("tag pushes may publish only dev or canary prereleases");
    if (channel !== prerelease[1]) throw new Error(`version ${version} does not match channel ${channel}`);
    return;
  }

  if (eventName !== "pull_request") throw new Error(`unsupported release event ${eventName}`);
  if (!stable || channel !== "stable") throw new Error("release PRs may publish only stable versions");
  if (prHeadRef !== `release/v${version}`) {
    throw new Error(`release branch ${prHeadRef} must be release/v${version}`);
  }
}

function main(): void {
  const read = (path: string) => JSON.parse(readFileSync(path, "utf8")) as { version: string };
  const version = process.env.VERSION;
  const channel = process.env.CHANNEL;
  const eventName = process.env.EVENT_NAME;
  if (!version || !channel || !eventName) throw new Error("release environment is incomplete");

  validateReleaseChannel({
    version,
    channel,
    eventName,
    prHeadRef: process.env.PR_HEAD_REF ?? "",
    manifestVersions: [
      read("package.json").version,
      read("plugin.json").version,
      read(".codex-plugin/plugin.json").version,
    ],
  });
  console.log(`${version} -> ${channel}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
