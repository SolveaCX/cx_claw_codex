import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";
import type { UserConfig } from "vite";

export function createMcpAppConfig(appName: string, entry: string, watch = false): UserConfig {
  return {
    root: resolve(import.meta.dirname),
    plugins: [react(), tailwindcss()],
    build: {
      outDir: resolve(import.meta.dirname, `../dist/mcp-apps/${appName}`),
      emptyOutDir: true,
      manifest: "manifest.json",
      cssCodeSplit: false,
      watch: watch ? {} : null,
      rollupOptions: {
        input: resolve(import.meta.dirname, entry),
        output: {
          format: "es",
          inlineDynamicImports: true,
          entryFileNames: `${appName}.js`,
          assetFileNames: `${appName}[extname]`,
        },
      },
    },
  };
}
