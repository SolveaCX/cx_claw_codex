import { afterEach, describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import { join } from "node:path";
import { runSolveaKitWorkflow } from "./solvea-kit.js";

const workspace = join(process.cwd(), "_tmp_", "solvea-kit-workflow");
afterEach(async () => { await fs.rm(workspace, { recursive: true, force: true }); });

describe("solvea-kit workflows", () => {
  test("creates the no-excel intent classification result", async () => {
    process.env.WORKSPACE_DIR = workspace;
    const result = await runSolveaKitWorkflow("intent-classify", ["--owner", "poc", "--no-excel"]) as { mode: string; resultsPath: string };
    expect(result.mode).toBe("no-excel");
    expect(await fs.stat(result.resultsPath)).toBeTruthy();
  });

  test("generates a label import workbook", async () => {
    process.env.WORKSPACE_DIR = workspace;
    const input = join(workspace, "labels.json"); await fs.mkdir(workspace, { recursive: true });
    await fs.writeFile(input, JSON.stringify({ labels: [{ path: ["Orders", "Cancel"], describe: "Cancel order", examples: ["cancel it"] }] }));
    const result = await runSolveaKitWorkflow("label-import", ["--input", input, "--init"]) as { file: string; rows: number };
    expect(result.rows).toBe(1);
    expect((await fs.stat(result.file)).size).toBeGreaterThan(0);
  });
});
