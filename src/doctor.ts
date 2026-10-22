import { access } from "node:fs/promises";
import { join } from "node:path";
import { packageRoot } from "./business.js";
import { VERSION } from "./version.js";

export async function diagnose() {
  const root = packageRoot();
  const requiredFiles = [
    "package.json",
  ];
  await Promise.all(requiredFiles.map((path) => access(join(root, path))));

  const expectedPluginVersion = process.env.CXCLAW_PLUGIN_VERSION || null;
  if (expectedPluginVersion && expectedPluginVersion !== VERSION) {
    throw new Error(
      `plugin version ${expectedPluginVersion} does not match CLI ${VERSION}`,
    );
  }

  return {
    ok: true,
    cliVersion: VERSION,
    pluginVersion: expectedPluginVersion,
    versionsMatch: expectedPluginVersion ? expectedPluginVersion === VERSION : null,
    nodeVersion: process.versions.node,
    runtimeFiles: requiredFiles,
  };
}
