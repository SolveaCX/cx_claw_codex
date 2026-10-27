import { execFileSync, spawn } from "node:child_process";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const devRoot = join(root, "_tmp_", "codex-plugin-dev");
const selector = "cxclaw-dev@cxclaw-dev";

type Manifest = {
  version: string;
  description: string;
  author?: unknown;
  repository?: unknown;
  extensions?: {
    "com.openai"?: Record<string, unknown> & {
      interface?: Record<string, unknown>;
    };
  };
};

function run(command: string, args: string[], options: { capture?: boolean } = {}): string {
  return execFileSync(command, args, {
    cwd: root,
    encoding: "utf8",
    stdio: options.capture ? ["ignore", "pipe", "pipe"] : "inherit",
  });
}

async function json<T>(path: string): Promise<T> {
  return JSON.parse(await readFile(path, "utf8")) as T;
}

function developerManifest(source: Manifest): Record<string, unknown> {
  const openai = source.extensions?.["com.openai"] ?? {};
  const interfaceConfig = openai.interface ?? {};
  return {
    $schema: "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    name: "cxclaw-dev",
    version: source.version,
    description: `${source.description} (local development)`,
    author: source.author,
    repository: source.repository,
    extensions: {
      "com.openai": {
        ...openai,
        onboardingSkill: "./skills/setup/SKILL.md",
        interface: {
          ...interfaceConfig,
          displayName: "CXClaw Dev",
          shortDescription: "CXClaw 本地开发调试版",
        },
      },
    },
  };
}

function compatibilityManifest(source: Manifest): Record<string, unknown> {
  const portable = developerManifest(source);
  const openai = (portable.extensions as { "com.openai": Record<string, unknown> })["com.openai"];
  return {
    $schema: portable.$schema,
    name: portable.name,
    version: portable.version,
    description: portable.description,
    author: portable.author,
    repository: portable.repository,
    skills: "./skills/",
    mcpServers: "./.mcp.json",
    ...openai,
  };
}

function mcpManifest(portable: boolean): Record<string, unknown> {
  const server = {
    ...(portable ? { type: "stdio" } : {}),
    command: "node",
    args: ["${PLUGIN_ROOT}/plugin-cli.dev.mjs", "mcp-server"],
  };
  return {
    ...(portable ? { $schema: "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json" } : {}),
    mcpServers: { "tenant-panel-dev": server },
  };
}

function launcherSource(version: string): string {
  const cli = join(root, "dist", "cli.js");
  return `#!/usr/bin/env node
import { spawn } from "node:child_process";
import { access } from "node:fs/promises";

const cli = ${JSON.stringify(cli)};
await access(cli).catch(() => {
  throw new Error("CXClaw development bundle is missing; run bun run dev:plugin");
});

const child = spawn(process.execPath, [cli, ...process.argv.slice(2)], {
  cwd: ${JSON.stringify(root)},
  stdio: "inherit",
  env: {
    ...process.env,
    CXCLAW_PLUGIN_ROOT: ${JSON.stringify(root)},
    CXCLAW_PLUGIN_VERSION: ${JSON.stringify(version)},
    CXCLAW_PLUGIN_DEV: "1",
  },
});

child.on("error", error => {
  console.error(\`cxclaw development launcher: \${error.message}\`);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exitCode = code ?? 1;
});
`;
}

export async function prepareDeveloperPlugin(outputRoot = devRoot): Promise<void> {
  const pluginRoot = join(outputRoot, "plugins", "cxclaw-dev");
  const marketplaceFile = join(outputRoot, ".agents", "plugins", "marketplace.json");
  const source = await json<Manifest>(join(root, "plugin.json"));
  await rm(outputRoot, { recursive: true, force: true });
  await mkdir(join(pluginRoot, ".codex-plugin"), { recursive: true });
  await mkdir(dirname(marketplaceFile), { recursive: true });
  await cp(join(root, "assets"), join(pluginRoot, "assets"), { recursive: true });
  await cp(join(root, "skills"), join(pluginRoot, "skills"), { recursive: true });

  await Promise.all([
    writeFile(join(pluginRoot, "plugin.json"), `${JSON.stringify(developerManifest(source), null, 2)}\n`),
    writeFile(join(pluginRoot, ".codex-plugin", "plugin.json"), `${JSON.stringify(compatibilityManifest(source), null, 2)}\n`),
    writeFile(join(pluginRoot, "mcp.json"), `${JSON.stringify(mcpManifest(true), null, 2)}\n`),
    writeFile(join(pluginRoot, ".mcp.json"), `${JSON.stringify(mcpManifest(false), null, 2)}\n`),
    writeFile(join(pluginRoot, "plugin-cli.dev.mjs"), launcherSource(source.version), { mode: 0o755 }),
    writeFile(marketplaceFile, `${JSON.stringify({
      $schema: "https://agent-plugins.org/schemas/1.0.0/marketplace.schema.json",
      name: "cxclaw-dev",
      interface: { displayName: "CXClaw Local Development" },
      owner: { name: "SolveaCX" },
      plugins: [{
        name: "cxclaw-dev",
        source: { source: "local", path: "./plugins/cxclaw-dev" },
        description: "CXClaw local development plugin",
        policy: { installation: "AVAILABLE", authentication: "ON_USE" },
        category: "Developer Tools",
      }],
    }, null, 2)}\n`),
  ]);
}

function configuredMarketplaceRoot(): string | undefined {
  try {
    const line = run("codex", ["plugin", "marketplace", "list"], { capture: true })
      .split("\n")
      .find(value => value.trimStart().startsWith("cxclaw-dev "));
    return line?.trim().match(/^cxclaw-dev\s+(.+)$/)?.[1];
  } catch {
    return undefined;
  }
}

async function buildAndPrepare(skipBuild: boolean): Promise<void> {
  if (!skipBuild) run("bun", ["run", "build"]);
  await prepareDeveloperPlugin();
  console.log(`Prepared local development marketplace at ${devRoot}`);
}

async function sync(skipBuild: boolean): Promise<void> {
  await buildAndPrepare(skipBuild);
  const configuredRoot = configuredMarketplaceRoot();
  if (configuredRoot && configuredRoot !== devRoot) {
    run("codex", ["plugin", "marketplace", "remove", "cxclaw-dev"]);
  }
  if (configuredRoot !== devRoot) run("codex", ["plugin", "marketplace", "add", devRoot]);
  run("codex", ["plugin", "add", selector, "--json"]);
  console.log([
    "CXClaw Dev is installed from the local workspace.",
    "For the first install, restart the ChatGPT desktop app once.",
    "After tenant panel UI builds, invoke tenant.current again to reload the panel resource.",
    "After MCP server or tool metadata changes, restart the ChatGPT desktop app.",
  ].join("\n"));
}

async function watch(): Promise<void> {
  await sync(false);
  console.log([
    "Watching TypeScript bundles.",
    "Invoke tenant.current again after tenant panel UI builds.",
    "Restart the ChatGPT desktop app after MCP server or tool metadata changes.",
  ].join("\n"));
  const child = spawn("bun", ["x", "tsup", "--watch"], { cwd: root, stdio: "inherit" });
  process.on("SIGINT", () => child.kill("SIGINT"));
  process.on("SIGTERM", () => child.kill("SIGTERM"));
  await new Promise<void>((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", code => code === 0 || code === null ? resolve() : reject(new Error(`tsup watch exited with ${code}`)));
  });
}

function status(): void {
  run("codex", ["plugin", "marketplace", "list"]);
  run("codex", ["plugin", "list", "--json"]);
}

function remove(): void {
  try {
    run("codex", ["plugin", "remove", selector]);
  } catch {
    // Continue so a half-installed development marketplace can still be cleaned up.
  }
  try {
    run("codex", ["plugin", "marketplace", "remove", "cxclaw-dev"]);
  } catch {
    // The marketplace may already be absent.
  }
  console.log("Removed CXClaw Dev. The stable CXClaw plugin was not changed.");
}

async function main(): Promise<void> {
  const command = process.argv[2] ?? "sync";
  const skipBuild = process.argv.includes("--skip-build");
  if (command === "prepare") await buildAndPrepare(skipBuild);
  else if (command === "sync") await sync(skipBuild);
  else if (command === "watch") await watch();
  else if (command === "status") status();
  else if (command === "remove") remove();
  else throw new Error(`unknown dev-plugin command: ${command}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
