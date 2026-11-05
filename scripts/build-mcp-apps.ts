import { build } from "vite";
import { createMcpAppConfig } from "../mcp-apps/vite.config.js";

const watch = process.argv.includes("--watch");
const apps = [
  ["tenant-status", "src/tenant-status/main.tsx"],
  ["live-test", "src/live-test/main.tsx"],
] as const;

await Promise.all(
  apps.map(([name, entry]) =>
    build({ ...createMcpAppConfig(name, entry, watch), configFile: false }),
  ),
);
