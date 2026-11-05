import { execFileSync, spawn } from "node:child_process";
import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
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

function run(
  command: string,
  args: string[],
  options: { capture?: boolean; cwd?: string } = {},
): string {
  return execFileSync(command, args, {
    cwd: options.cwd ?? root,
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
        onboardingSkill: "./skills/cxclawctl/SKILL.md",
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
    writeFile(
      join(pluginRoot, "plugin.json"),
      `${JSON.stringify(developerManifest(source), null, 2)}\n`,
    ),
    writeFile(
      join(pluginRoot, ".codex-plugin", "plugin.json"),
      `${JSON.stringify(compatibilityManifest(source), null, 2)}\n`,
    ),
    writeFile(join(pluginRoot, "mcp.json"), `${JSON.stringify(mcpManifest(true), null, 2)}\n`),
    writeFile(join(pluginRoot, ".mcp.json"), `${JSON.stringify(mcpManifest(false), null, 2)}\n`),
    writeFile(join(pluginRoot, "plugin-cli.dev.mjs"), launcherSource(source.version), {
      mode: 0o755,
    }),
    writeFile(
      marketplaceFile,
      `${JSON.stringify(
        {
          $schema: "https://agent-plugins.org/schemas/1.0.0/marketplace.schema.json",
          name: "cxclaw-dev",
          interface: { displayName: "CXClaw Local Development" },
          owner: { name: "SolveaCX" },
          plugins: [
            {
              name: "cxclaw-dev",
              source: { source: "local", path: "./plugins/cxclaw-dev" },
              description: "CXClaw local development plugin",
              policy: { installation: "AVAILABLE", authentication: "ON_USE" },
              category: "Developer Tools",
            },
          ],
        },
        null,
        2,
      )}\n`,
    ),
  ]);
}

async function playgroundRoots(workspaceRoot = root): Promise<string[]> {
  const entries = await readdir(workspaceRoot, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory() && entry.name === "playground")
    .map((entry) => join(workspaceRoot, entry.name));
}

function marketplaceDefinition(): Record<string, unknown> {
  return {
    $schema: "https://agent-plugins.org/schemas/1.0.0/marketplace.schema.json",
    name: "cxclaw-dev",
    interface: { displayName: "CXClaw Local Development" },
    owner: { name: "SolveaCX" },
    plugins: [
      {
        name: "cxclaw-dev",
        source: { source: "local", path: "./.codex/plugins/cxclaw-dev" },
        description: "CXClaw local development plugin",
        policy: { installation: "AVAILABLE", authentication: "ON_USE" },
        category: "Developer Tools",
      },
    ],
  };
}

async function enableForPlayground(playgroundRoot: string, outputRoot: string): Promise<void> {
  const codexRoot = join(playgroundRoot, ".codex");
  const pluginRoot = join(codexRoot, "plugins", "cxclaw-dev");
  const marketplaceFile = join(playgroundRoot, ".agents", "plugins", "marketplace.json");
  const configFile = join(codexRoot, "config.toml");
  const instructionsFile = join(playgroundRoot, "AGENTS.md");

  await rm(pluginRoot, { recursive: true, force: true });
  await mkdir(dirname(marketplaceFile), { recursive: true });
  await mkdir(codexRoot, { recursive: true });
  await cp(join(outputRoot, "plugins", "cxclaw-dev"), pluginRoot, { recursive: true });
  await writeFile(marketplaceFile, `${JSON.stringify(marketplaceDefinition(), null, 2)}\n`);
  const instructionsHeading = "## CXClaw 开发插件";
  const instructionsSection = [
    instructionsHeading,
    "",
    "- 本项目使用 `cxclaw-dev@cxclaw-dev` 开发版插件。",
    "- 用户没有明确要求时，不要在本地安装正式版 `cxclaw` 插件。",
  ].join("\n");
  let instructions = "# Playground 项目说明\n";
  try {
    instructions = await readFile(instructionsFile, "utf8");
  } catch {
    // A new playground does not have project instructions yet.
  }
  const sectionStart = instructions.indexOf(instructionsHeading);
  if (sectionStart >= 0) {
    const nextSection = instructions.indexOf("\n## ", sectionStart + instructionsHeading.length);
    instructions = [
      instructions.slice(0, sectionStart).trimEnd(),
      instructionsSection,
      nextSection >= 0 ? instructions.slice(nextSection).trimStart() : "",
    ]
      .filter(Boolean)
      .join("\n\n");
  } else {
    instructions = `${instructions.trimEnd()}\n\n${instructionsSection}`;
  }
  instructions = `${instructions.trimEnd()}\n`;
  await writeFile(instructionsFile, instructions);

  let config = "";
  try {
    config = await readFile(configFile, "utf8");
  } catch {
    // A new playground does not have project configuration yet.
  }
  const section = '[plugins."cxclaw-dev@cxclaw-dev"]';
  const enabled = /(\[plugins\."cxclaw-dev@cxclaw-dev"\]\s*\nenabled\s*=\s*)(?:true|false)/;
  config = enabled.test(config)
    ? config.replace(enabled, "$1true")
    : `${config.trimEnd()}${config.trim() ? "\n\n" : ""}${section}\nenabled = true\n`;
  await writeFile(configFile, config);
}

export async function syncDeveloperPluginToPlaygrounds(
  outputRoot = devRoot,
  workspaceRoot = root,
): Promise<string[]> {
  const playgrounds = await playgroundRoots(workspaceRoot);
  if (playgrounds.length === 0) {
    throw new Error(`No ./playground directory found under ${workspaceRoot}`);
  }
  await Promise.all(playgrounds.map((playground) => enableForPlayground(playground, outputRoot)));
  return playgrounds;
}

function removeGlobalRegistration(): void {
  const marketplace = run("codex", ["plugin", "marketplace", "list"], { capture: true });
  if (!marketplace.split("\n").some((line) => line.trimStart().startsWith("cxclaw-dev "))) {
    return;
  }
  try {
    run("codex", ["plugin", "remove", selector]);
  } catch {
    // Continue so a half-installed global marketplace can still be cleaned up.
  }
  try {
    run("codex", ["plugin", "marketplace", "remove", "cxclaw-dev"]);
  } catch {
    // The global marketplace may already be absent.
  }
}

async function buildAndPrepare(skipBuild: boolean): Promise<void> {
  if (!skipBuild) run("bun", ["run", "build"]);
  await prepareDeveloperPlugin();
  console.log(`Prepared local development marketplace at ${devRoot}`);
}

async function sync(skipBuild: boolean): Promise<void> {
  await buildAndPrepare(skipBuild);
  removeGlobalRegistration();
  const playgrounds = await syncDeveloperPluginToPlaygrounds();
  console.log(
    [
      `CXClaw Dev is enabled in: ${playgrounds.join(", ")}`,
      "For the first install, restart the ChatGPT desktop app once.",
      "After MCP App, MCP server, or tool metadata changes, restart the ChatGPT desktop app so content-hashed resource URIs are registered.",
    ].join("\n"),
  );
}

async function watch(): Promise<void> {
  await sync(false);
  console.log(
    [
      "Watching TypeScript bundles.",
      "After login and tenant selection, invoke tenant.current with the current contextId.",
      "Restart the ChatGPT desktop app after MCP server or tool metadata changes.",
    ].join("\n"),
  );
  const children = [
    spawn("bun", ["x", "tsup", "--watch"], { cwd: root, stdio: "inherit" }),
    spawn("bun", ["run", "dev:mcp-apps"], { cwd: root, stdio: "inherit" }),
  ];
  process.on("SIGINT", () => children.forEach((child) => child.kill("SIGINT")));
  process.on("SIGTERM", () => children.forEach((child) => child.kill("SIGTERM")));
  await new Promise<void>((resolve, reject) => {
    for (const child of children) {
      child.on("error", reject);
      child.on("exit", (code) => {
        children
          .filter((candidate) => candidate !== child)
          .forEach((candidate) => candidate.kill());
        code === 0 || code === null
          ? resolve()
          : reject(new Error(`development watcher exited with ${code}`));
      });
    }
  });
}

async function status(): Promise<void> {
  run("codex", ["plugin", "marketplace", "list"]);
  const playgrounds = await playgroundRoots();
  console.log(`CXClaw Dev playgrounds: ${playgrounds.join(", ") || "none"}`);
}

async function remove(): Promise<void> {
  removeGlobalRegistration();
  const playgrounds = await playgroundRoots();
  await Promise.all(
    playgrounds.map(async (playground) => {
      await rm(join(playground, ".codex", "plugins", "cxclaw-dev"), {
        recursive: true,
        force: true,
      });
      await rm(join(playground, ".agents", "plugins", "marketplace.json"), { force: true });

      const configFile = join(playground, ".codex", "config.toml");
      try {
        const config = await readFile(configFile, "utf8");
        const section =
          /\n?\[plugins\."cxclaw-dev@cxclaw-dev"\]\s*\nenabled\s*=\s*(?:true|false)\s*\n?/;
        await writeFile(configFile, config.replace(section, "").trimStart());
      } catch {
        // The playground may already be clean.
      }
    }),
  );
  console.log("Removed CXClaw Dev. The stable CXClaw plugin was not changed.");
}

async function main(): Promise<void> {
  const command = process.argv[2] ?? "sync";
  const skipBuild = process.argv.includes("--skip-build");
  if (command === "prepare") await buildAndPrepare(skipBuild);
  else if (command === "sync") await sync(skipBuild);
  else if (command === "watch") await watch();
  else if (command === "status") await status();
  else if (command === "remove") await remove();
  else throw new Error(`unknown dev-plugin command: ${command}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
