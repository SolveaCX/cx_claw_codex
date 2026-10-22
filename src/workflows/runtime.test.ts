import { afterEach, describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import { join } from "node:path";
import { runRuntime } from "./runtime.js";

const workspace = join(process.cwd(), "_tmp_", "runtime-workflow");
afterEach(async () => { await fs.rm(workspace, { recursive: true, force: true }); });

describe("runtime workflow", () => {
  test("prepares, processes, and verifies state without Python", async () => {
    process.env.WORKSPACE_DIR = workspace;
    const prepared = await runRuntime("prepare", ["--batch-size", "7"]) as { totalBatches: number };
    expect(prepared.totalBatches).toBe(5);
    const processed = await runRuntime("process", []) as { total: number };
    expect(processed.total).toBe(30);
    const verified = await runRuntime("verify", []) as { ok: boolean };
    expect(verified.ok).toBe(true);
  });

  test("returns a bounded model truncation instruction", async () => {
    process.env.WORKSPACE_DIR = workspace;
    const result = await runRuntime("model", ["--scenario", "truncation"]) as { scenario: string; target: string };
    expect(result.scenario).toBe("truncation");
    expect(result.target).toContain("runtime-inspector");
  });
});
