import { defineConfig } from "tsup";

export default defineConfig([
  {
    entry: { cli: "src/cli.ts" },
    format: ["esm"],
    target: "node22",
    platform: "node",
    clean: true,
    sourcemap: true,
    dts: false,
    splitting: false,
    banner: { js: "#!/usr/bin/env node" },
  },
  {
    entry: { "tenant-panel": "src/mcp/tenant-panel.ts" },
    format: ["iife"],
    target: "es2022",
    platform: "browser",
    clean: false,
    sourcemap: true,
    dts: false,
    splitting: false,
    minify: true,
    outExtension: () => ({ js: ".js" }),
  },
]);
