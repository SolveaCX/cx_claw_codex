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
    entry: { "tenant-app": "src/mcp/tenant-app.ts" },
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
