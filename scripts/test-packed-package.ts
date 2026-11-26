import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
  for (const app of ["tenant-status", "live-test"])
    if (!existsSync(join(packageRoot, "dist", "mcp-apps", app, "manifest.json")))
      throw new Error(`missing ${app} MCP App bundle`);
  if (existsSync(join(packageRoot, "runtime")))
    throw new Error("obsolete hook runtime was packaged");

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
  const help = execFileSync(bin, ["ticket", "get", "--help"], { env, encoding: "utf8" });
  if (!help.includes("ticketNumber")) throw new Error("packed ticket CLI is missing");
  const reportData = join(temp, "report.json");
  writeFileSync(reportData, JSON.stringify({ kpis: [{ label: "Tickets", value: 2 }] }));
  const output = join(temp, "ticket-report.html");
  execFileSync(
    bin,
    [
      "ticket-analytics",
      "render-report",
      "--task-id",
      "package-check",
      "--report-data",
      reportData,
      "--output",
      output,
    ],
    { env },
  );
  if (!readFileSync(output, "utf8").includes("Tickets"))
    throw new Error("packed report renderer or assets are missing");
} finally {
  rmSync(temp, { recursive: true, force: true });
}
