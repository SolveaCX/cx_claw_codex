import { afterEach, describe, expect, test } from "bun:test";
import type { Session } from "../types.js";
import { runReportAction } from "./report.js";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
afterEach(() => {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
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

describe("legacy report resource commands", () => {
  test("uses the report command group and legacy statement endpoint", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (input, init) => {
      requests.push({ url: String(input), init });
      return new Response(JSON.stringify([]), { status: 200 });
    }) as typeof fetch;
    console.log = () => {};

    await runReportAction(session, "message", [
      "--begin-ts",
      "1784736000000",
      "--end-ts",
      "1784822399999",
      "--bot-id",
      "2584",
      "--channel",
      "LIVE_CHAT",
      "--date-unit",
      "TOTAL",
    ]);

    const request = requests.at(-1);
    expect(request?.url).toEndWith("/api_v2/as_bot/statement/message");
    expect(request?.init?.method).toBe("POST");
    expect(JSON.parse(String(request?.init?.body))).toEqual({
      projectId: 950,
      beginTimestamp: 1784736000000,
      endTimestamp: 1784822399999,
      timeOffset: 8,
      botId: 2584,
      touchPoint: "LIVE_CHAT",
      dateUnit: "TOTAL",
    });
  });

  test("supports solvea-kit report endpoints missing from the old CLI", async () => {
    const requests: string[] = [];
    globalThis.fetch = (async (input) => {
      requests.push(String(input));
      return new Response(JSON.stringify([]), { status: 200 });
    }) as typeof fetch;
    console.log = () => {};

    for (const action of ["feedback", "escalation-drilldown", "agent-weekly-graph"] as const) {
      await runReportAction(session, action, [
        "--begin-ts",
        "1784736000000",
        "--end-ts",
        "1784822399999",
        ...(action === "escalation-drilldown" ? ["--reason", "pricing"] : []),
      ]);
    }
    await runReportAction(session, "inspection-history", [
      "--start-date",
      "2026-08-01",
      "--end-date",
      "2026-08-31",
    ]);

    expect(requests.map((url) => url.split("/api_v2")[1])).toEqual([
      "/gpt/bots",
      "/as_bot/statement/feedback",
      "/gpt/bots",
      "/as_bot/statement/transcript/reason/three/level",
      "/gpt/bots",
      "/as_bot/statement/graph/agent",
      "/intelli/inspection/ticket/history",
    ]);
  });
});
