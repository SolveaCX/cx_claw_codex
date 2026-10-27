import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, readFile } from "node:fs/promises";
import type { Session } from "../types.js";
import { SolveaClient } from "./client.js";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const session: Session = {
  accessToken: "access", refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000, employeeId: "employee", email: "employee@example.com", channel: "dev",
  tenant: {
    accountId: 5, accountCode: "test", accountName: "Test", environment: "staging",
    purpose: "test", businessUrl: "https://apps-staging.example", businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

type Request = { url: string; method: string; body?: Record<string, unknown> };
function capture(responder: (request: Request) => unknown = () => ({ success: true })) {
  const requests: Request[] = [];
  globalThis.fetch = (async (input, init) => {
    const request = { url: String(input), method: String(init?.method ?? "GET"), body: init?.body ? JSON.parse(String(init.body)) : undefined };
    requests.push(request);
    const response = request.url.endsWith("/api_v2/gpt/bots") ? [{ projectId: 302, id: 723 }] : responder(request);
    return new Response(JSON.stringify(response), { status: 200 });
  }) as typeof fetch;
  return requests;
}

describe("cross-module API migration contracts", () => {
  test("reads the current tenant company name from the business API", async () => {
    const requests = capture(() => ({ data: { accountId: 5, accountCode: "test", companyName: "Test Company" } }));
    const info = await new SolveaClient(session).currentTenantInfo();
    expect(requests.at(-1)?.url).toEndWith("/api_v2/ticket/agent/plg-user/v2/user-info");
    expect(info).toMatchObject({ accountId: 5, accountCode: "test", companyName: "Test Company" });
  });

  test("normalizes legacy agent and tool ID fields", async () => {
    const requests = capture();
    const client = new SolveaClient(session);
    await client.updateAgent({ id: 7, name: "Agent" });
    expect(requests.at(-1)?.body).toMatchObject({ id: 7, agentId: 7, projectId: 302 });
    await client.updatePlugin({ id: 8, name: "Tool" });
    expect(requests.at(-1)?.body).toMatchObject({ id: 8, pluginId: 8, projectId: 302 });
  });

  test("preserves chatflow draft semantics from the legacy implementation", async () => {
    const requests = capture(request => request.url.endsWith("/queryAgent")
      ? [{ id: 7, type: "CHAT_FLOW", meta: { backupType: "OLD" } }] : { success: true });
    await new SolveaClient(session).updateChatflow("7", { nodes: [], edges: [] });
    expect(requests.at(-1)?.body).toMatchObject({
      agentId: 7, projectId: 302, backupType: "DRAFT",
      meta: { chatFlowGraph: { nodes: [], edges: [] } },
    });
    expect((requests.at(-1)?.body?.meta as Record<string, unknown>).draft_flow_updatetime).toBeNumber();
  });

  test("uses the v4 strategy update endpoint for updates and toggles", async () => {
    const requests = capture();
    const client = new SolveaClient(session);
    await client.updateStrategy("9", { name: "Strategy" });
    expect(requests.at(-1)?.url).toEndWith("/api_v2/gpt/project/302/strategy/9?v4=true");
    await client.toggleStrategy("9", false);
    expect(requests.at(-1)?.url).toEndWith("/api_v2/gpt/project/302/strategy/9?v4=true");
    expect(requests.at(-1)?.body).toEqual({ status: "DISABLED" });
  });

  test("does not allow extra chat data to override tenant routing fields", async () => {
    const requests = capture();
    await new SolveaClient(session).chat({ message: "hello", botId: 723, projectId: 999 });
    expect(requests.at(-1)?.body).toMatchObject({ message: "hello", botId: 723, projectId: 302, option: { debug: true } });
  });

  test("uses the streaming endpoint and returns the final AgentAction", async () => {
    const requests: Request[] = [];
    globalThis.fetch = (async (input, init) => {
      const request = { url: String(input), method: String(init?.method ?? "GET"), body: init?.body ? JSON.parse(String(init.body)) : undefined };
      requests.push(request);
      if (request.url.endsWith("/api_v2/gpt/bots")) return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      return new Response('data: {"content":"partial"}\n\ndata: {"isEnd":true,"data":{"chatId":"c1","content":"done"}}\n\n', { status: 200 });
    }) as typeof fetch;

    const result = await new SolveaClient(session).chatStream({ message: "hello" });

    expect(requests.at(-1)?.url).toEndWith("/api_v2/gpt/bot/723/chat/stream");
    expect(result).toEqual({ chatId: "c1", content: "done" });
  });

  test("downloads label workbooks as binary files", async () => {
    await mkdir("_tmp_/cross-module-contracts", { recursive: true });
    const target = `_tmp_/cross-module-contracts/labels-${Date.now()}.xlsx`;
    const requests: string[] = [];
    globalThis.fetch = (async input => {
      requests.push(String(input));
      if (String(input).endsWith("/api_v2/gpt/bots")) return new Response(JSON.stringify([{ projectId: 302 }]));
      return new Response(new Uint8Array([80, 75, 3, 4]), { status: 200 });
    }) as typeof fetch;

    await new SolveaClient(session).downloadLabels("7", target);

    expect(requests.at(-1)).toEndWith("/api_v2/gpt/label/project/302/downloadLabel?treeId=7");
    expect([...await readFile(target)]).toEqual([80, 75, 3, 4]);
  });
});
