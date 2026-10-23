import { describe, expect, test } from "bun:test";
import { mkdir, writeFile } from "node:fs/promises";
import { validateGraph } from "./agent-builder.js";
import { runDelivery, runPoc } from "./delivery.js";
import { runKbBuilder } from "./kb-builder.js";

describe("TypeScript workflow migrations", () => {
  test("validates graph structure without a tenant session", () => {
    expect(validateGraph({ nodes: [{ id: "start", type: "START" }], edges: [] }).valid).toBe(true);
    expect(validateGraph({ nodes: [{ id: "a" }, { id: "a" }], edges: [] }).valid).toBe(false);
  });

  test("keeps delivery and POC state workflows local", async () => {
    const delivery = await runDelivery(undefined, "plan", ["--init"]);
    const poc = await runPoc(undefined, "classify", ["--no-excel"]);
    expect(delivery).toHaveProperty("status");
    expect(poc).toMatchObject({ domain: "poc", total: 0 });
  });

  test("builds a directory plan without Python or a tenant", async () => {
    await mkdir("_tmp_", { recursive: true });
    const input = `_tmp_/migrated-kb-${Date.now()}.json`;
    await writeFile(input, JSON.stringify({ pages: [{ title: "Help Center / Orders", url: "https://example.test/orders" }] }));
    const result = await runKbBuilder(undefined, "directory-plan", ["--crawl-result", input, "--output", `${input}.plan.json`]);
    expect(result).toMatchObject({ directories: 1, pages: 1 });
  });
});
