import { afterEach, describe, expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import type { Session } from "../../../types.js";
import { LiveTestRunner } from "./runner.js";
import { LiveTestStore } from "./store.js";

const originalFetch = globalThis.fetch;
const stateRoot = `_tmp_/live-test-${process.pid}`;
afterEach(async () => {
  globalThis.fetch = originalFetch;
  delete process.env.CXCLAW_LIVE_TEST_STATE_DIR;
  await rm(stateRoot, { recursive: true, force: true });
});

const session: Session = {
  accessToken: "access",
  refreshToken: "refresh",
  accessExpiry: Math.floor(Date.now() / 1000) + 3600,
  employeeId: "employee",
  email: "employee@example.com",
  channel: "dev",
  runtimeContext: { contextId: "ctx_test", profileId: "profile-test" },
  tenant: {
    accountId: 12,
    accountCode: "test",
    accountName: "Test",
    environment: "staging",
    purpose: "test",
    businessUrl: "https://apps-staging.example",
    businessToken: "tenant-token",
    expiresAt: Math.floor(Date.now() / 1000) + 3600,
  },
};

describe("LiveTest runner", () => {
  test("runs END_TO_END without Agent overrides and evaluates the routed result", async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    const chatBodies: Record<string, unknown>[] = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      if (url.endsWith("/api_v2/gpt/ap/queryAgent"))
        throw new Error("END_TO_END must not resolve a fixed Agent");
      if (url.endsWith("/chat/stream")) {
        chatBodies.push(JSON.parse(String(init?.body)));
        return new Response(
          'data: {"content":"in transit"}\n\ndata: {"isEnd":true,"data":{"chatId":"chat-e2e","type":"MESSAGE","message":{"id":"ai-e2e","content":"in transit"},"contextComparison":{"chatContext":{"originIntent":"Track Shipment","intent":"Track Shipment","intents":[{"id":9750,"name":"Track Shipment"}],"strategyId":1001,"strategyName":"Logistics Routing","strategyAction":{"type":"AGENT","agentId":2584},"ext":{"invoke_agent_name":"Logistics Agent"}}}}}\n\n',
          { status: 200 },
        );
      }
      throw new Error(`unexpected request ${url}`);
    }) as typeof fetch;

    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        testScope: "END_TO_END",
      },
      [
        {
          message: "Where is my order?",
          expected: {
            intentId: 9750,
            intent: "Track Shipment",
            strategyName: "Logistics Routing",
            agentId: 2584,
            actionType: "AGENT",
          },
        },
      ],
    );
    const runner = new LiveTestRunner(store, async () => structuredClone(session));
    await runner.run(
      snapshot,
      {
        contextId: "ctx_test",
        testScope: "END_TO_END",
        touchPoint: "LIVE_CHAT",
        case: {
          turns: [
            {
              message: "Where is my order?",
              expected: {
                intentId: 9750,
                intent: "Track Shipment",
                strategyName: "Logistics Routing",
                agentId: 2584,
                actionType: "AGENT",
              },
            },
          ],
        },
        metadata: { specified_agent_id: 999, order_id: "A-1" },
        option: { debug: false },
      },
      new AbortController().signal,
    );

    const completed = await store.read("profile-test", snapshot.testRunId);
    expect(completed).toMatchObject({
      status: "succeeded",
      verdict: "PASS",
      testScope: "END_TO_END",
      chatId: "chat-e2e",
    });
    expect(completed.agentId).toBeUndefined();
    expect(completed.turns[0]?.routing).toMatchObject({
      intent: "Track Shipment",
      strategy: { name: "Logistics Routing", actionType: "AGENT" },
      agent: { id: 2584, name: "Logistics Agent" },
    });
    expect(completed.turns[0]?.evaluation?.verdict).toBe("PASS");
    expect(chatBodies[0]?.metadata).toEqual({ order_id: "A-1", show_chat_flow: true });
    expect(chatBodies[0]?.option).toEqual({ debug: true, verbose: true });
  });

  test("bounds persisted snapshots", async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        agentId: 9,
      },
      ["x".repeat(100_000)],
    );
    const persisted = await store.read("profile-test", snapshot.testRunId);
    expect(persisted.truncated).toBe(true);
    expect(Buffer.byteLength(JSON.stringify(persisted))).toBeLessThanOrEqual(32 * 1024);
  });

  test("resolves the target, protects routing fields, and completes multiple turns", async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    const chatBodies: Record<string, unknown>[] = [];
    let turn = 0;
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      if (url.endsWith("/api_v2/gpt/ap/queryAgent"))
        return new Response(
          JSON.stringify([{ id: 9, name: "Test Agent", type: "CHAT_FLOW", meta: {} }]),
          { status: 200 },
        );
      if (url.endsWith("/api_v2/gpt/chatflow/queryGraph/latest"))
        return new Response(JSON.stringify({ flowVersion: -101 }), { status: 200 });
      if (url.endsWith("/chat/stream")) {
        chatBodies.push(JSON.parse(String(init?.body)));
        turn += 1;
        return new Response(
          `data: {"content":"reply-${turn}"}\n\ndata: {"isEnd":true,"data":{"chatId":"chat-1","messageId":"m-${turn}","content":"reply-${turn}","actionType":"TO_AGENT","reasonDesc":"handoff"}}\n\n`,
          { status: 200 },
        );
      }
      throw new Error(`unexpected request ${url}`);
    }) as typeof fetch;

    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        agentId: 9,
      },
      ["one", "two"],
    );
    const runner = new LiveTestRunner(store, async () => structuredClone(session));
    await runner.run(
      snapshot,
      {
        contextId: "ctx_test",
        agentId: 9,
        touchPoint: "LIVE_CHAT",
        case: { turns: [{ message: "one" }, { message: "two" }] },
        metadata: { specified_agent_id: 999, custom: "ok" },
        option: { debug: false },
      },
      new AbortController().signal,
    );
    const completed = await store.read("profile-test", snapshot.testRunId);
    expect(completed.status).toBe("succeeded");
    expect(completed.chatId).toBe("chat-1");
    expect(completed.turns.map((item) => item.status)).toEqual(["succeeded", "succeeded"]);
    expect(completed.turns[0]?.outcome).toMatchObject({
      actionType: "TO_AGENT",
      handoff: true,
      reasonDesc: "handoff",
    });
    expect(chatBodies[0]?.metadata).toMatchObject({
      custom: "ok",
      specified_agent_id: 9,
      specified_flow_version: -101,
      show_chat_flow: true,
    });
    expect(chatBodies[0]?.option).toEqual({ debug: true, verbose: true });
    expect(chatBodies[1]?.chatId).toBe("chat-1");
  });

  test("runs SINGLE_AGENT without querying or injecting Chatflow fields", async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    const chatBodies: Record<string, unknown>[] = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      if (url.endsWith("/api_v2/gpt/ap/queryAgent"))
        return new Response(
          JSON.stringify([{ id: 2584, name: "Single Agent", type: "SINGLE_AGENT", meta: {} }]),
          { status: 200 },
        );
      if (url.endsWith("/api_v2/gpt/chatflow/queryGraph/latest"))
        throw new Error("SINGLE_AGENT must not query Chatflow versions");
      if (url.endsWith("/chat/stream")) {
        chatBodies.push(JSON.parse(String(init?.body)));
        return new Response(
          'data: {"content":"single answer"}\n\ndata: {"isEnd":true,"data":{"chatId":"chat-single","type":"AI_REPLY","message":{"id":"ai-single","content":"single answer"}}}\n\n',
          { status: 200 },
        );
      }
      throw new Error(`unexpected request ${url}`);
    }) as typeof fetch;

    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        agentId: 2584,
      },
      ["hello"],
    );
    const runner = new LiveTestRunner(store, async () => structuredClone(session));
    await runner.run(
      snapshot,
      {
        contextId: "ctx_test",
        agentId: 2584,
        botId: 723,
        touchPoint: "LIVE_CHAT",
        case: { turns: [{ message: "hello" }] },
        metadata: {
          order_id: "A-1",
          specified_flow_version: 17,
          show_chat_flow: true,
        },
        option: {},
      },
      new AbortController().signal,
    );

    const completed = await store.read("profile-test", snapshot.testRunId);
    expect(completed).toMatchObject({
      status: "succeeded",
      agentType: "SINGLE_AGENT",
      chatId: "chat-single",
    });
    expect(completed.flowVersion).toBeUndefined();
    expect(completed.turns[0]).toMatchObject({
      assistant: "single answer",
      messageId: "ai-single",
      outcome: { actionType: "AI_REPLY" },
    });
    expect(chatBodies[0]?.metadata).toEqual({ order_id: "A-1", specified_agent_id: 2584 });
  });

  test("rejects flowVersion for SINGLE_AGENT", async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    globalThis.fetch = (async (input) => {
      const url = String(input);
      if (url.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      if (url.endsWith("/api_v2/gpt/ap/queryAgent"))
        return new Response(
          JSON.stringify([{ id: 2584, name: "Single Agent", type: "SINGLE_AGENT", meta: {} }]),
          { status: 200 },
        );
      throw new Error(`unexpected request ${url}`);
    }) as typeof fetch;

    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        agentId: 2584,
      },
      ["hello"],
    );
    const runner = new LiveTestRunner(store, async () => structuredClone(session));
    await runner.run(
      snapshot,
      {
        contextId: "ctx_test",
        agentId: 2584,
        botId: 723,
        flowVersion: 17,
        touchPoint: "LIVE_CHAT",
        case: { turns: [{ message: "hello" }] },
        metadata: {},
        option: {},
      },
      new AbortController().signal,
    );

    const completed = await store.read("profile-test", snapshot.testRunId);
    expect(completed.status).toBe("failed");
    expect(completed.error).toBe(
      "SINGLE_AGENT does not support flowVersion; remove this parameter",
    );
  });

  test("marks a stopped SINGLE_AGENT action as failed", async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    globalThis.fetch = (async (input) => {
      const url = String(input);
      if (url.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      if (url.endsWith("/api_v2/gpt/ap/queryAgent"))
        return new Response(
          JSON.stringify([{ id: 2584, name: "Single Agent", type: "SINGLE_AGENT", meta: {} }]),
          { status: 200 },
        );
      if (url.endsWith("/chat/stream"))
        return new Response(
          'data: {"isEnd":true,"data":{"chatId":"chat-timeout","type":"STOPPED","reason":"AGENT_TIMEOUT","message":{"id":"ai-timeout","content":""}}}\n\n',
          { status: 200 },
        );
      throw new Error(`unexpected request ${url}`);
    }) as typeof fetch;

    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        agentId: 2584,
      },
      ["hello"],
    );
    const runner = new LiveTestRunner(store, async () => structuredClone(session));
    await runner.run(
      snapshot,
      {
        contextId: "ctx_test",
        agentId: 2584,
        botId: 723,
        touchPoint: "LIVE_CHAT",
        case: { turns: [{ message: "hello" }] },
        metadata: {},
        option: {},
      },
      new AbortController().signal,
    );

    const completed = await store.read("profile-test", snapshot.testRunId);
    expect(completed).toMatchObject({
      status: "failed",
      chatId: "chat-timeout",
      error: "AGENT_TIMEOUT",
    });
    expect(completed.turns[0]).toMatchObject({
      status: "failed",
      messageId: "ai-timeout",
      error: "AGENT_TIMEOUT",
      outcome: { actionType: "STOPPED", reason: "AGENT_TIMEOUT" },
    });
  });
});

for (const touchPoint of ["EMAIL", "LIVE_CHAT"]) {
  test(`persists and sends only current turn attachments over ${touchPoint}`, async () => {
    process.env.CXCLAW_LIVE_TEST_STATE_DIR = stateRoot;
    const bodies: Record<string, unknown>[] = [];
    globalThis.fetch = (async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api_v2/gpt/bots"))
        return new Response(JSON.stringify([{ projectId: 302, id: 723 }]), { status: 200 });
      if (url.endsWith(touchPoint === "EMAIL" ? "/chat" : "/chat/stream")) {
        bodies.push(JSON.parse(String(init?.body)));
        const action = { chatId: "attachment-chat", type: "MESSAGE", content: "received" };
        return new Response(
          touchPoint === "EMAIL"
            ? JSON.stringify(action)
            : `data: ${JSON.stringify({ isEnd: true, data: action })}\n\n`,
          { status: 200 },
        );
      }
      throw new Error(`unexpected request ${url}`);
    }) as typeof fetch;
    const turns = [
      { message: "", attachments: ["https://example.com/receipt.jpg"] },
      { message: "Please check it" },
      { message: "Manual", attachments: ["https://example.com/manual.pdf"] },
    ];
    const store = new LiveTestStore();
    const snapshot = await store.create(
      {
        contextId: "ctx_test",
        profileId: "profile-test",
        accountId: 12,
        environment: "staging",
        testScope: "END_TO_END",
      },
      turns,
    );
    expect(
      (await store.read(snapshot.profileId, snapshot.testRunId)).turns[0]?.attachments,
    ).toEqual(turns[0]!.attachments);
    await new LiveTestRunner(store, async () => structuredClone(session)).run(
      snapshot,
      {
        contextId: "ctx_test",
        testScope: "END_TO_END",
        botId: 723,
        touchPoint,
        case: { turns },
        metadata: {},
        option: {},
      },
      new AbortController().signal,
    );
    const saved = await store.read(snapshot.profileId, snapshot.testRunId);
    expect(saved.status).toBe("succeeded");
    expect(bodies).toHaveLength(3);
    expect(bodies[0]?.attachments).toEqual(turns[0]!.attachments);
    expect(bodies[0]?.message).toBe("");
    expect(bodies[1]?.attachments).toBeUndefined();
    expect(bodies[1]?.chatId).toBe("attachment-chat");
    expect(bodies[2]?.attachments).toEqual(turns[2]!.attachments);
    expect(saved.turns[2]?.attachments).toEqual(turns[2]!.attachments);
    expect(bodies[0]?.metadata).not.toHaveProperty("attachments");
  });
}
