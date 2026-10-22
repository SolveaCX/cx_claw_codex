import { spawn } from "node:child_process";
import { access, readFile } from "node:fs/promises";
import { join } from "node:path";
import { findPython, packageRoot } from "./business.js";
import { VERSION } from "./version.js";

const run = (command: string, args: string[]) =>
  new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, { stdio: "ignore" });
    child.on("error", reject);
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${command} exited with ${code}`)),
    );
  });

export async function diagnose() {
  const root = packageRoot();
  const requiredFiles = [
    "capabilities.lock.json",
    "requirements-cli.txt",
    "skills/__lib__/solvea-api/solvea_api.py",
  ];
  await Promise.all(requiredFiles.map((path) => access(join(root, path))));

  const expectedPluginVersion = process.env.CXCLAW_PLUGIN_VERSION || null;
  if (expectedPluginVersion && expectedPluginVersion !== VERSION) {
    throw new Error(
      `plugin version ${expectedPluginVersion} does not match CLI ${VERSION}`,
    );
  }

  const python = await findPython();
  const requirements = await readFile(join(root, "requirements-cli.txt"), "utf8");
  const importNames: Record<string, string> = { beautifulsoup4: "bs4" };
  const modules = requirements
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split(/[<>=!~\[]/, 1)[0])
    .map((name) => importNames[name] ?? name.replaceAll("-", "_"));
  try {
    await run(python, ["-c", modules.map((name) => `import ${name}`).join(";")]);
  } catch {
    throw new Error(
      `Python dependencies are missing; run ${python} -m pip install -r "${join(root, "requirements-cli.txt")}"`,
    );
  }

  return {
    ok: true,
    cliVersion: VERSION,
    pluginVersion: expectedPluginVersion,
    versionsMatch: expectedPluginVersion ? expectedPluginVersion === VERSION : null,
    nodeVersion: process.versions.node,
    python,
    runtimeFiles: requiredFiles,
  };
}
