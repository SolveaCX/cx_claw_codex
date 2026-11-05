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
        return new Response(JSON.stringify([{ id: 9, name: "Test Agent", meta: {} }]), {
          status: 200,
        });
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
});
