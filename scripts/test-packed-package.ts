import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dirname, "..");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
  version: string;
};
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const tempRoot = join(root, "_tmp_");
mkdirSync(tempRoot, { recursive: true });
const temp = mkdtempSync(join(tempRoot, "packed-package-"));

try {
  const packed = JSON.parse(
    execFileSync(npm, ["pack", "--json", "--pack-destination", temp], {
      cwd: root,
      encoding: "utf8",
    }),
  ) as Array<{ filename: string }>;
  const archive = join(temp, packed[0].filename);
  const prefix = join(temp, "install");
  execFileSync(npm, ["install", "--prefix", prefix, archive], { stdio: "inherit" });

  const packageRoot = join(prefix, "node_modules", "@shulex", "cxclawctl");
  if (existsSync(join(packageRoot, "skills", "solvea-kit", "SKILL.md"))) {
    throw new Error("npm package must not contain Skill documentation");
  }
  if (!existsSync(join(packageRoot, "dist", "cli.js"))) throw new Error("missing compiled CLI");
  if (existsSync(join(packageRoot, "runtime"))) throw new Error("obsolete hook runtime was packaged");

  const bin =
    process.platform === "win32"
      ? join(prefix, "node_modules", ".bin", "cxclawctl.cmd")
      : join(prefix, "node_modules", ".bin", "cxclawctl");
  const env = { ...process.env, CXCLAW_PLUGIN_VERSION: pkg.version };
  const version = JSON.parse(
    execFileSync(bin, ["version", "--json"], { env, encoding: "utf8" }),
  ) as { cliVersion: string; pluginVersion: string };
  if (version.cliVersion !== pkg.version || version.pluginVersion !== pkg.version) {
    throw new Error(`packed version mismatch: ${JSON.stringify(version)}`);
  }
  execFileSync(bin, ["doctor"], { env, stdio: "inherit" });
} finally {
  rmSync(temp, { recursive: true, force: true });
}
