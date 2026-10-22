import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { homedir, platform } from "node:os";
import { isAbsolute, join } from "node:path";

type ExecOptions = { capture?: boolean; allowFailure?: boolean };

const exec = (command: string, args: string[], options: ExecOptions = {}) =>
  new Promise<string>((resolve, reject) => {
    const chunks: Buffer[] = [];
    const child = spawn(command, args, {
      stdio: options.capture ? ["ignore", "pipe", "inherit"] : "inherit",
    });
    if (options.capture) child.stdout?.on("data", (chunk) => chunks.push(chunk));
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0 || options.allowFailure) {
        resolve(Buffer.concat(chunks).toString("utf8"));
        return;
      }
      reject(new Error(`${command} exited with ${code}`));
    });
  });

const xml = (value: string) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");

const systemdArg = (value: string) =>
  `"${value.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;

const windowsArg = (value: string) =>
  /[\s"]/.test(value) ? `"${value.replaceAll('"', '\\"')}"` : value;

export function schedulerInvocation(
  environment: NodeJS.ProcessEnv = process.env,
  nodeExecutable = process.execPath,
) {
  const npmExecutable = environment.npm_execpath;
  if (!npmExecutable || !isAbsolute(npmExecutable)) {
    throw new Error(
      "cannot register updater: run this command through npm or npx so npm_execpath is available",
    );
  }
  return {
    command: nodeExecutable,
    args: [
      npmExecutable,
      "exec",
      "--yes",
      "--package=@shulex/cxclawctl@latest",
      "--",
      "cxclawctl",
      "update",
      "--scheduled",
    ],
  };
}

export async function update() {
  await exec("codex", ["plugin", "marketplace", "upgrade", "cxclaw"]);
  await exec("codex", ["plugin", "add", "cxclaw@cxclaw"]);
  const raw = await exec("codex", ["plugin", "list", "--json"], { capture: true });
  const list = JSON.parse(raw) as {
    installed?: Array<{ pluginId?: string; version?: string; enabled?: boolean }>;
  };
  const plugin = list.installed?.find((item) => item.pluginId === "cxclaw@cxclaw");
  if (!plugin?.version || plugin.enabled === false) {
    throw new Error("CXClaw plugin is not installed and enabled");
  }

  const response = await fetch(
    `https://registry.npmjs.org/@shulex%2Fcxclawctl/${encodeURIComponent(plugin.version)}`,
    { signal: AbortSignal.timeout(30_000) },
  );
  if (!response.ok) {
    throw new Error(
      `npm package @shulex/cxclawctl@${plugin.version} is unavailable (${response.status})`,
    );
  }
  const metadata = (await response.json()) as { version?: string };
  if (metadata.version !== plugin.version) {
    throw new Error(
      `npm returned ${metadata.version ?? "no version"}, expected ${plugin.version}`,
    );
  }
  return {
    pluginVersion: plugin.version,
    cliPackageVersion: metadata.version,
    restartRequired: true,
  };
}

export async function installScheduler() {
  const invocation = schedulerInvocation();
  if (platform() === "darwin") {
    const dir = join(homedir(), "Library/LaunchAgents");
    const path = join(dir, "com.solvea.cxclaw.update.plist");
    const programArguments = [invocation.command, ...invocation.args]
      .map((value) => `<string>${xml(value)}</string>`)
      .join("");
    await mkdir(dir, { recursive: true });
    await writeFile(
      path,
      `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>Label</key><string>com.solvea.cxclaw.update</string><key>ProgramArguments</key><array>${programArguments}</array><key>StartInterval</key><integer>21600</integer><key>RunAtLoad</key><true/></dict></plist>\n`,
    );
    await exec("launchctl", ["unload", path], { allowFailure: true });
    await exec("launchctl", ["load", path]);
    return;
  }

  if (platform() === "linux") {
    const dir = join(homedir(), ".config/systemd/user");
    const command = [invocation.command, ...invocation.args].map(systemdArg).join(" ");
    await mkdir(dir, { recursive: true });
    await writeFile(
      join(dir, "cxclaw-update.service"),
      `[Service]\nType=oneshot\nExecStart=${command}\n`,
    );
    await writeFile(
      join(dir, "cxclaw-update.timer"),
      "[Timer]\nOnBootSec=5m\nOnUnitActiveSec=6h\nPersistent=true\n[Install]\nWantedBy=timers.target\n",
    );
    await exec("systemctl", ["--user", "daemon-reload"]);
    await exec("systemctl", ["--user", "enable", "--now", "cxclaw-update.timer"]);
    return;
  }

  const task = [invocation.command, ...invocation.args].map(windowsArg).join(" ");
  await exec("schtasks", [
    "/Create",
    "/F",
    "/SC",
    "HOURLY",
    "/MO",
    "6",
    "/TN",
    "Solvea CXClaw Update",
    "/TR",
    task,
  ]);
}

export async function installMarketplace(channel: string) {
  if (!["stable", "canary", "dev"].includes(channel)) {
    throw new Error("invalid channel");
  }
  await exec("codex", [
    "plugin",
    "marketplace",
    "add",
    "SolveaCX/cx_claw_codex",
    "--ref",
    `marketplace/${channel}`,
  ]).catch(() => exec("codex", ["plugin", "marketplace", "upgrade", "cxclaw"]));
  await exec("codex", ["plugin", "add", "cxclaw@cxclaw"]);
}
