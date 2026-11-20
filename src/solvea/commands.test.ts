import { afterEach, describe, expect, test } from "bun:test";
import type { Session } from "../types.js";
import { isNativeSolveaCommand, runSolveaCommand } from "./commands.js";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

const session: Session = {
  accessToken: "access",
  refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000,
  employeeId: "employee",
  email: "employee@example.com",
  channel: "dev",
  tenant: {
    accountId: 5,
    accountCode: "test",
    accountName: "Test",
    environment: "staging",
    purpose: "test",
    businessUrl: "https://apps-staging.example",
    businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

describe("native Solvea command registry", () => {
  test("keeps migrated API commands explicit", () => {
    expect(isNativeSolveaCommand("get-agent")).toBe(true);
    expect(isNativeSolveaCommand("delete-agent")).toBe(true);
    expect(isNativeSolveaCommand("update-intent")).toBe(true);
    expect(isNativeSolveaCommand("list-managed-ai-fields")).toBe(true);
    expect(isNativeSolveaCommand("create-quality-alert-rule")).toBe(true);
    expect(isNativeSolveaCommand("delete-templates")).toBe(true);
    expect(isNativeSolveaCommand("list-voice-agents")).toBe(true);
    expect(isNativeSolveaCommand("analytics-messages")).toBe(false);
    expect(isNativeSolveaCommand("analytics-inbox-scripts")).toBe(false);
    expect(isNativeSolveaCommand("chat-report-messages")).toBe(false);
    expect(isNativeSolveaCommand("unknown-command")).toBe(false);
  });

  test("passes direct knowledge list filters to the API", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (input, init) => {
      requests.push({ url: String(input), init });
      const body = String(input).endsWith("/api_v2/gpt/bots")
        ? [{ projectId: 302 }]
        : { list: [], totalCount: 0 };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;

    await runSolveaCommand(session, "list-knowledge", [
      "--type",
      "QA",
      "--page",
      "2",
      "--page-size",
      "5",
      "--keyword",
      "充值",
    ]);

    const request = requests.at(-1);
    expect(request?.url).toEndWith("/sns_v1/project/302/getKnowledge");
    expect(request?.init?.method).toBe("POST");
    expect(JSON.parse(String(request?.init?.body))).toEqual({
      type: "QA",
      pageIndex: 2,
      pageSize: 5,
      keyword: "充值",
    });
  });

  test("uses the paged isolation keyword endpoint", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      requests.push({ url, init });
      const body = url.endsWith("/api_v2/gpt/bots")
        ? [{ projectId: 302 }]
        : { list: [{ id: 11, keyword: "pump" }], pageIndex: 2, pageSize: 5, totalPage: 3 };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;

    const result = await runSolveaCommand(session, "list-isolation-keywords", [
      "--keyword",
      "pump",
      "--page",
      "2",
      "--page-size",
      "5",
    ]);

    const request = requests.at(-1);
    const url = new URL(request?.url ?? "https://invalid.example");
    expect(url.pathname).toBe("/sns_v1/project/302/isolation_keywords/page");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      keyword: "pump",
      pageIndex: "2",
      pageSize: "5",
    });
    expect(request?.init?.method).toBe("GET");
    expect(result).toEqual([{ id: 11, keyword: "pump" }]);
  });

  test("preserves the raw isolation keyword page response", async () => {
    globalThis.fetch = (async (input) => {
      const url = String(input);
      const body = url.endsWith("/api_v2/gpt/bots")
        ? [{ projectId: 302 }]
        : { list: [{ id: 11, keyword: "pump" }], pageIndex: 1, pageSize: 50, totalPage: 1 };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;

    const result = await runSolveaCommand(session, "list-isolation-keywords", ["--raw"]);

    expect(result).toEqual({
      list: [{ id: 11, keyword: "pump" }],
      pageIndex: 1,
      pageSize: 50,
      totalPage: 1,
    });
  });

  test("collects all isolation keyword pages using totalPage", async () => {
    const requestedPages: number[] = [];
    globalThis.fetch = (async (input) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302 }]), { status: 200 });

      const pageIndex = Number(url.searchParams.get("pageIndex"));
      requestedPages.push(pageIndex);
      return new Response(
        JSON.stringify({
          list: [{ id: pageIndex, keyword: `keyword-${pageIndex}` }],
          pageIndex,
          pageSize: 1,
          totalPage: 2,
          totalCount: 2,
        }),
        { status: 200 },
      );
    }) as typeof fetch;

    const result = await runSolveaCommand(session, "list-isolation-keywords", [
      "--all",
      "--page-size",
      "1",
    ]);

    expect(result).toEqual([
      { id: 1, keyword: "keyword-1" },
      { id: 2, keyword: "keyword-2" },
    ]);
    expect(requestedPages).toEqual([1, 2]);
  });

  test("rejects repeated isolation keyword pages", async () => {
    globalThis.fetch = (async (input) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302 }]), { status: 200 });
      return new Response(
        JSON.stringify({ list: [{ id: 11, keyword: "duplicate" }], pageSize: 1 }),
        { status: 200 },
      );
    }) as typeof fetch;

    await expect(
      runSolveaCommand(session, "list-isolation-keywords", ["--all", "--page-size", "1"]),
    ).rejects.toThrow("repeated page data at pageIndex=2");
  });

  test("attaches Agent labels and filters the list by label name", async () => {
    const requests: Array<{ url: string; body?: Record<string, unknown> }> = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ url, body });
      const response = url.endsWith("/api_v2/gpt/bots")
        ? [{ projectId: 302 }]
        : url.endsWith("/api_v2/gpt/ap/queryAgent")
          ? [
              { id: 7, name: "Returns", type: "CHAT_FLOW" },
              { id: 8, name: "Shipping", type: "CHAT_FLOW" },
            ]
          : url.endsWith("/api_v2/gpt/agent/tag/queryAllBindings")
            ? [{ agentId: 7, tags: [{ id: 11, name: "aaa", color: "#fff" }] }]
            : { success: true };
      return new Response(JSON.stringify(response), { status: 200 });
    }) as typeof fetch;

    const result = await runSolveaCommand(session, "list-agents", ["--tag", "AAA"]);

    expect(result).toEqual([
      {
        id: 7,
        name: "Returns",
        type: "CHAT_FLOW",
        tags: [{ id: 11, name: "aaa", color: "#fff" }],
      },
    ]);
    expect(
      requests.some((request) => request.url.endsWith("/api_v2/gpt/agent/tag/queryAllBindings")),
    ).toBe(true);
  });

  test("applies partial updates through the generic Agent command", async () => {
    const requests: Array<{ url: string; body?: Record<string, unknown> }> = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ url, body });
      const response = url.endsWith("/api_v2/gpt/bots")
        ? [{ projectId: 302 }]
        : url.endsWith("/queryAgent")
          ? [
              {
                id: 7,
                type: "CHAT_FLOW",
                name: "Support flow",
                meta: { chatFlowGlobalPrompt: "Old role", maxInvokeCount: 30 },
              },
            ]
          : { success: true };
      return new Response(JSON.stringify(response), { status: 200 });
    }) as typeof fetch;

    await runSolveaCommand(session, "update-agent", [
      "--id",
      "7",
      "--data",
      JSON.stringify({ meta: { chatFlowGlobalPrompt: "New role" } }),
    ]);

    expect(requests.at(-1)?.url).toEndWith("/api_v2/gpt/ap/updateAgent");
    expect(requests.at(-1)?.body).toMatchObject({
      id: 7,
      agentId: 7,
      projectId: 302,
      name: "Support flow",
      meta: { chatFlowGlobalPrompt: "New role", maxInvokeCount: 30 },
    });
  });

  test("requires explicit confirmation before deleting an Agent", async () => {
    let requestCount = 0;
    globalThis.fetch = (async () => {
      requestCount += 1;
      return new Response(JSON.stringify({ success: true }), { status: 200 });
    }) as unknown as typeof fetch;

    await expect(runSolveaCommand(session, "delete-agent", ["--id", "7"])).rejects.toThrow(
      "requires --confirm-delete after explicit user acknowledgement",
    );
    expect(requestCount).toBe(0);
  });

  test("deletes an Agent after explicit confirmation", async () => {
    const requests: Array<{ url: string; body?: Record<string, unknown> }> = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ url, body });
      const response = url.endsWith("/api_v2/gpt/bots") ? [{ projectId: 302 }] : { success: true };
      return new Response(JSON.stringify(response), { status: 200 });
    }) as typeof fetch;

    const result = await runSolveaCommand(session, "delete-agent", [
      "--id",
      "7",
      "--confirm-delete",
    ]);

    expect(result).toEqual({ agentId: 7, deleted: true });
    expect(requests.at(-1)?.url).toEndWith("/api_v2/gpt/ap/deleteAgent");
    expect(requests.at(-1)?.body).toEqual({ projectId: 302, agentId: 7 });
  });

  test("keeps data filters and lets direct knowledge options override them", async () => {
    let requestBody: unknown;
    globalThis.fetch = (async (input, init) => {
      if (String(input).endsWith("/api_v2/gpt/bots")) {
        return new Response(JSON.stringify([{ projectId: 302 }]), { status: 200 });
      }
      requestBody = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ list: [], totalCount: 0 }), { status: 200 });
    }) as typeof fetch;

    await runSolveaCommand(session, "list-knowledge", [
      "--data",
      JSON.stringify({
        type: "ALL",
        pageIndex: 9,
        pageSize: 99,
        keyword: "旧值",
        directoryId: 33727,
      }),
      "--type",
      "QA",
      "--page",
      "3",
      "--page-size",
      "10",
      "--keyword",
      "新值",
    ]);

    expect(requestBody).toEqual({
      type: "QA",
      pageIndex: 3,
      pageSize: 10,
      keyword: "新值",
      directoryId: 33727,
    });
  });

  test("routes resource detail reads using the required knowledge type", async () => {
    const requests: string[] = [];
    globalThis.fetch = (async (input) => {
      requests.push(String(input));
      const body = String(input).endsWith("/api_v2/gpt/bots") ? [{ projectId: 302 }] : { id: 8 };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;

    await runSolveaCommand(session, "get-knowledge", ["--id", "8", "--type", "WEBSITE"]);

    expect(requests.at(-1)).toEndWith("/sns_v1/project/302/document/8");
  });

  test("forwards report drill-down scripts and exact chat IDs", async () => {
    let requestBody: unknown;
    globalThis.fetch = (async (input, init) => {
      if (String(input).endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302 }]), { status: 200 });
      requestBody = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ list: [] }), { status: 200 });
    }) as typeof fetch;

    await runSolveaCommand(session, "list-transcripts", [
      "--script",
      '{"term":{"handoff":true}}',
      "--chat-ids",
      "c1,c2",
    ]);

    expect(requestBody).toEqual({
      pageIndex: 1,
      pageSize: 50,
      debug: false,
      script: '{"term":{"handoff":true}}',
      chatIds: ["c1", "c2"],
    });
  });
});
