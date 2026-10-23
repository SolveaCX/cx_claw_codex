import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, writeFile } from "node:fs/promises";
import type { Session } from "../types.js";
import { runKbBuilder } from "./kb-builder.js";

const originalFetch = globalThis.fetch;
const originalOutputDir = process.env.CXCLAW_OUTPUT_DIR;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalOutputDir === undefined) delete process.env.CXCLAW_OUTPUT_DIR;
  else process.env.CXCLAW_OUTPUT_DIR = originalOutputDir;
});

const session: Session = {
  accessToken: "access", refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000, employeeId: "employee", email: "employee@example.com", channel: "dev",
  tenant: {
    accountId: 5, accountCode: "test", accountName: "Test", environment: "staging",
    purpose: "test", businessUrl: "https://apps-staging.example", businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

describe("kb-builder migration contracts", () => {
  test("resolves dir_path and converts QA plan fields before upload", async () => {
    await mkdir("_tmp_/kb-builder-contracts", { recursive: true });
    const plan = `_tmp_/kb-builder-contracts/qa-${Date.now()}.json`;
    await writeFile(plan, JSON.stringify([{ dir_path: ["test-hw"], question: "Q", answer: "A" }]));
    process.env.CXCLAW_OUTPUT_DIR = "_tmp_/kb-builder-contracts/output";
    const requests: Array<{ url: string; method: string; body?: unknown }> = [];
    globalThis.fetch = (async (input, init) => {
      const request = { url: String(input), method: String(init?.method ?? "GET"), body: init?.body ? JSON.parse(String(init.body)) : undefined };
      requests.push(request);
      const response = request.url.endsWith("/api_v2/gpt/bots") ? [{ projectId: 302 }]
        : request.url.includes("/directories?") ? { list: [{ id: 31577, parentId: 0, name: "test-hw", children: [] }] }
          : { success: true };
      return new Response(JSON.stringify(response), { status: 200 });
    }) as typeof fetch;

    const result = await runKbBuilder(session, "import-qa", ["--qa-file", plan]);

    expect(result).toMatchObject({ count: 1 });
    expect(requests.at(-1)?.url).toEndWith("/sns_v1/project/302/kus");
    expect(requests.at(-1)?.body).toEqual([{
      title: "Q", content: "A", directoryId: 31577, type: "QA", forceIndex: true,
      published: true, taskType: "MANUAL", metadata: { tags: [] }, isVisible: true,
    }]);
  });

  test("dry-run validates QA fields before reporting success", async () => {
    await mkdir("_tmp_/kb-builder-contracts", { recursive: true });
    const plan = `_tmp_/kb-builder-contracts/invalid-${Date.now()}.json`;
    await writeFile(plan, JSON.stringify([{ dir_path: ["test-hw"], question: "", answer: "A" }]));
    await expect(runKbBuilder(session, "import-qa", ["--qa-file", plan, "--dry-run"]))
      .rejects.toThrow("question must be a non-empty string");
  });

  test("converts source document plans into the documents API contract", async () => {
    await mkdir("_tmp_/kb-builder-contracts", { recursive: true });
    const plan = `_tmp_/kb-builder-contracts/sources-${Date.now()}.json`;
    await writeFile(plan, JSON.stringify([{ source: "https://example.test/help", dir_path: ["test-hw"] }]));
    const requests: Array<{ url: string; body?: unknown }> = [];
    globalThis.fetch = (async (input, init) => {
      const request = { url: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined };
      requests.push(request);
      const response = request.url.endsWith("/api_v2/gpt/bots") ? [{ projectId: 302 }]
        : request.url.includes("/directories?") ? { list: [{ id: 31577, parentId: 0, name: "test-hw", children: [] }] }
          : { success: true };
      return new Response(JSON.stringify(response), { status: 200 });
    }) as typeof fetch;

    await runKbBuilder(session, "import-source-documents", ["--plan-file", plan, "--execute"]);

    expect(requests.at(-1)?.url).toEndWith("/sns_v1/project/302/documents");
    expect(requests.at(-1)?.body).toEqual({
      documents: [{ filePath: "https://example.test/help", docType: "TC", fileType: "website" }],
      published: true, taskType: "WEB", taskUrl: "MANUAL", isFullSiteCrawl: false,
      metadata: { tags: [] }, directoryId: 31577, isVisible: true,
    });
  });
});
