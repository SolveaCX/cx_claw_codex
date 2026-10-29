import { afterEach, describe, expect, test } from "bun:test";
import type { Session } from "../types.js";
import { isFlatAnalyticsCommand, runAnalyticsAction } from "./analytics.js";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
afterEach(() => { globalThis.fetch = originalFetch; console.log = originalLog; });

const session: Session = {
  accessToken: "access", refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000, employeeId: "employee", email: "employee@example.com", channel: "dev",
  tenant: {
    accountId: 5, accountCode: "test", accountName: "Test", environment: "staging",
    purpose: "test", businessUrl: "https://apps-staging.example", businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

describe("analytics resource commands", () => {
  test("route actions directly to formal Agent report endpoints", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (input, init) => {
      requests.push({ url: String(input), init });
      return new Response(JSON.stringify([]), { status: 200 });
    }) as typeof fetch;
    console.log = () => {};

    const actions = {
      tickets: "tickets",
      messages: "messages",
      intents: "intents",
      agents: "agents",
      satisfaction: "satisfaction",
      "first-response": "first-response",
      "return-retention": "return-retention",
      "inspection-results": "inspection-results",
    };
    for (const [action, endpoint] of Object.entries(actions)) {
      requests.length = 0;
      await runAnalyticsAction(session, action, [
        "--start-date", "2026-10-01", "--end-date", "2026-10-20",
        "--bot-id", "723", "--channel", "EMAIL",
      ]);
      const request = requests.at(-1);
      expect(request?.url).toEndWith(`/api_v2/as_bot/chat-report/${endpoint}`);
      expect(request?.init?.method).toBe("POST");
      expect(JSON.parse(String(request?.init?.body))).toEqual({
        startDate: "2026-10-01", endDate: "2026-10-20", botId: 723, touchPoint: "EMAIL",
      });
    }
  });

  test("uses GET for inbox scripts", async () => {
    let request: { url: string; init?: RequestInit } | undefined;
    globalThis.fetch = (async (input, init) => {
      request = { url: String(input), init };
      return new Response(JSON.stringify({}), { status: 200 });
    }) as typeof fetch;
    console.log = () => {};

    await runAnalyticsAction(session, "inbox-scripts", []);
    expect(request?.url).toEndWith("/api_v2/as_bot/chat-report/inbox-scripts");
    expect(request?.init?.method).toBe("GET");
    expect(request?.init?.body).toBeUndefined();
  });

  test("rejects flat and unknown actions", async () => {
    expect(isFlatAnalyticsCommand("analytics-messages")).toBe(true);
    expect(isFlatAnalyticsCommand("chat-report-messages")).toBe(true);
    expect(isFlatAnalyticsCommand("analytics")).toBe(false);
    await expect(runAnalyticsAction(session, "analytics-messages", [])).rejects.toThrow("unknown analytics action");
    await expect(runAnalyticsAction(session, "unknown", [])).rejects.toThrow("unknown analytics action");
  });
});
