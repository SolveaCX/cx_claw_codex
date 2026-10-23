import { afterEach, describe, expect, test } from "bun:test";
import type { Session } from "../types.js";
import { SolveaClient } from "./client.js";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const session: Session = {
  serverUrl: "https://auth.example", accessToken: "access", refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000, employeeId: "employee", email: "employee@example.com", channel: "dev",
  tenant: {
    accountId: 5, accountCode: "test", accountName: "Test", environment: "staging",
    purpose: "test", businessUrl: "https://apps-staging.example", businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

type CapturedRequest = { url: string; method: string; body?: unknown };
function capture(responder: (request: CapturedRequest) => unknown = () => ({ success: true })) {
  const requests: CapturedRequest[] = [];
  globalThis.fetch = (async (input, init) => {
    const request = {
      url: String(input), method: String(init?.method ?? "GET"),
      body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
    };
    requests.push(request);
    const result = request.url.endsWith("/api_v2/gpt/bots") ? [{ projectId: 302 }] : responder(request);
    return new Response(JSON.stringify(result), { status: 200 });
  }) as typeof fetch;
  return requests;
}

describe("knowledge API migration contracts", () => {
  test("normalizes QA uploads instead of forwarding plan fields", async () => {
    const requests = capture();
    await new SolveaClient(session).uploadQa([{ title: "Q", content: "A", directoryId: 31577 }]);
    expect(requests.at(-1)).toMatchObject({
      method: "POST", body: [{
        title: "Q", content: "A", directoryId: 31577, type: "QA", forceIndex: true,
        published: true, taskType: "MANUAL", metadata: { tags: [] }, isVisible: true,
      }],
    });
    expect(requests.at(-1)?.url).toEndWith("/sns_v1/project/302/kus");
  });

  test("routes detail reads by UI knowledge type", async () => {
    const requests = capture();
    const client = new SolveaClient(session);
    await client.getKnowledgeByType("11", "FILE");
    await client.getKnowledgeByType("12", "PRODUCT");
    expect(requests.at(-2)?.url).toEndWith("/sns_v1/project/302/document/11");
    expect(requests.at(-1)?.url).toEndWith("/sns_v1/project/302/ku_product/12");
  });

  test("wraps batch knowledge updates and inherits directoryId", async () => {
    const requests = capture(request => request.url.endsWith("/ku/7") ? { id: 7, directoryId: 99 } : { success: true });
    await new SolveaClient(session).updateKus([{ id: 7, content: "updated" }]);
    expect(requests.at(-1)).toMatchObject({ method: "PUT", body: { list: [{ kuId: 7, content: "updated", directoryId: 99 }] } });
  });

  test("updates document content through contentV2 with preserved metadata", async () => {
    const requests = capture(request => request.url.endsWith("/document/8")
      ? { id: 8, directoryId: 3, fileName: "manual.pdf", title: "Manual", metadata: { tags: ["x"] } }
      : { success: true });
    await new SolveaClient(session).updateDocumentContent("8", "FILE", { fileText: "new" });
    expect(requests.at(-1)).toMatchObject({
      method: "PUT", body: {
        type: "FILE", directoryId: 3, fileName: "manual.pdf", title: "Manual",
        metadata: { tags: ["x"] }, fileText: "new", knowledgeIds: [8],
      },
    });
    expect(requests.at(-1)?.url).toEndWith("/sns_v1/project/302/document/8/contentV2");
  });

  test("normalizes batch product status fields", async () => {
    const requests = capture();
    await new SolveaClient(session).updateKuProducts([{ kuProductId: 9, published: false, mainPush: true }]);
    expect(requests.at(-1)).toMatchObject({ method: "PUT", body: { list: [{ id: 9, enable: false, mainPush: true }] } });
  });

  test("adds product creation defaults", async () => {
    const requests = capture();
    await new SolveaClient(session).createProductKnowledge({ title: "Product", spuUrl: "https://example.test/product" });
    expect(requests.at(-1)).toMatchObject({
      method: "POST", body: {
        title: "Product", spuUrl: "https://example.test/product", source: "MANUAL",
        published: true, isVisible: true, metadata: { tags: [] },
      },
    });
  });

  test("merges product updates with the complete current record", async () => {
    const current = {
      title: "Old", describe: "Description", spuUrl: "https://example.test/product", image: "https://example.test/image.png",
      source: "MANUAL", published: true, isVisible: true, directoryId: 3,
    };
    const requests = capture(request => request.url.endsWith("/ku_product/9") ? current : { success: true });
    await new SolveaClient(session).updateProductKnowledge("9", { title: "New" });
    expect(requests.at(-1)).toMatchObject({ method: "PUT", body: { ...current, title: "New", kuProductId: 9 } });
  });

  test("wraps operations and requires explicit delete confirmation", async () => {
    const client = new SolveaClient(session);
    capture(() => ({ id: 10, type: "QA" }));
    await expect(client.operateKnowledge([{ knowledgeType: "QA", knowledgeId: 10, operateType: "DELETE" }]))
      .rejects.toThrow("--confirm-delete");

    const requests = capture(() => ({ id: 10, type: "QA" }));
    await new SolveaClient(session).operateKnowledge([{ knowledgeType: "QA", knowledgeId: 10, operateType: "DELETE" }], true);
    expect(requests.at(-1)).toMatchObject({ body: { requestList: [{ knowledgeType: "QA", knowledgeId: 10, operateType: "DELETE" }] } });
  });

  test("maps UI types for isolation keyword APIs", async () => {
    const requests = capture();
    const client = new SolveaClient(session);
    await client.getKnowledgeIsolationKeywords("13", "WEBSITE");
    expect(requests.at(-1)?.url).toContain("knowledgeType=DOCUMENT");
    await client.batchUpdateIsolationKeywordBindings({ items: [{ knowledgeType: "LEARN_SELF", knowledgeId: 13, keywordIds: [2, 2] }] });
    expect(requests.at(-1)).toMatchObject({ body: { items: [{ knowledgeType: "QA", knowledgeId: 13, keywordIds: [2] }], directoryIds: [], keywordIds: [] } });
  });

  test("computes final isolation keyword bindings for append operations", async () => {
    const requests = capture(request => request.url.includes("/knowledge/isolation_keywords?") ? [{ id: 1 }] : { id: 13, type: "QA" });
    await new SolveaClient(session).applyIsolationKeywordBindings({
      operation: "append", items: [{ knowledgeType: "QA", knowledgeId: 13, keywordIds: [2] }],
    });
    expect(requests.at(-1)).toMatchObject({
      body: { items: [{ knowledgeType: "QA", knowledgeId: 13, keywordIds: [1, 2] }], directoryIds: [], keywordIds: [] },
    });
  });

  test("computes final tag sets before calling editTags", async () => {
    const requests = capture(request => request.url.endsWith("/ku/14") ? { id: 14, metadata: { tags: ["old"] } } : { success: true });
    await new SolveaClient(session).editKnowledgeTags({ knowledgeIds: [14], tagList: ["new"], operation: "append", type: "QA" });
    expect(requests.at(-1)).toMatchObject({ body: { type: "QA", knowledgeIds: [14], tagList: ["old", "new"] } });
  });
});
