import { defineConfig } from "tsup";
import { cp } from "node:fs/promises";

export default defineConfig({
  entry: { cli: "src/cli.ts" },
  format: ["esm"],
  target: "node22",
  platform: "node",
  clean: true,
  onSuccess: async () => {
    await cp("src/workflows/assets", "dist/assets", { recursive: true });
  },
  sourcemap: true,
  dts: false,
  splitting: false,
  banner: { js: "#!/usr/bin/env node" },
});
