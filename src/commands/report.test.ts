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

  test("forwards page dimension filters for every legacy report action", async () => {
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
    globalThis.fetch = (async (input, init) => {
      requests.push({
        url: String(input),
        body: init?.body ? JSON.parse(String(init.body)) : {},
      });
      return new Response(JSON.stringify([]), { status: 200 });
    }) as typeof fetch;
    console.log = () => {};

    const actions = [
      "transcript",
      "message",
      "agent",
      "intent",
      "satisfaction",
      "satisfaction-list",
      "feedback",
      "knowledge",
      "knowledge-export",
      "satisfaction-export",
      "escalation",
      "escalation-drilldown",
      "agent-weekly-graph",
      "self-learning",
      "livechat",
      "livechat-table",
    ] as const;

    for (const action of actions) {
      await runReportAction(session, action, [
        "--begin-ts",
        "1792857600000",
        "--end-ts",
        "1793462399999",
        "--bot-id",
        "7",
        "--channel",
        "EMAIL",
        "--agent-id",
        "36623",
        "--intent-id",
        "88",
        "--date-unit",
        "WEEK",
        ...(action === "escalation-drilldown" ? ["--reason", "CALL_TOOL_MISSING_PARAM"] : []),
      ]);
    }

    const reportRequests = requests.filter((request) => !request.url.endsWith("/api_v2/gpt/bots"));
    expect(reportRequests).toHaveLength(actions.length);
    for (const request of reportRequests) {
      expect(request.body.botId).toBe(7);
      expect(request.body.touchPoint).toBe("EMAIL");
      expect(request.body.agentId).toBe(36623);
      expect(request.body.firstIntentId).toBe(88);
    }
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

  test("covers tag, knowledge export and inspection detail capabilities", async () => {
    const requests: Array<{ url: string; body: unknown }> = [];
    globalThis.fetch = (async (input, init) => {
      requests.push({
        url: String(input),
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      return new Response(JSON.stringify([]), { status: 200 });
    }) as typeof fetch;
    console.log = () => {};

    await runReportAction(session, "tag-distribution", [
      "--begin-ts",
      "1784736000000",
      "--end-ts",
      "1784822399999",
      "--tree-id",
      "33",
      "--level",
      "2",
      "--tag",
      "refund",
    ]);
    await runReportAction(session, "knowledge-export", [
      "--begin-ts",
      "1784736000000",
      "--end-ts",
      "1784822399999",
    ]);
    await runReportAction(session, "inspection-tags", [
      "--start-date",
      "2026-11-01",
      "--end-date",
      "2026-11-12",
    ]);
    await runReportAction(session, "inspection-tags-history", [
      "--start-date",
      "2026-11-01",
      "--end-date",
      "2026-11-12",
    ]);
    await runReportAction(session, "inspection-export", [
      "--start-date",
      "2026-11-01",
      "--end-date",
      "2026-11-12",
    ]);

    const apiRequests = requests.filter((request) => request.url.includes("/api_v2/"));
    expect(apiRequests.map((request) => request.url.split("/api_v2")[1])).toEqual([
      "/gpt/bots",
      "/qa_bot/label/project/950/report/distribution",
      "/gpt/bots",
      "/gpt/label/project/950/download/knowledge",
      "/intelli/inspection/ticket/tagsList",
      "/intelli/inspection/ticket/tagsHistory",
      "/gpt/bots",
      "/gpt/950/export/async",
    ]);
    expect(apiRequests[1]?.body).toEqual({
      beginTimestamp: 1784736000000,
      endTimestamp: 1784822399999,
      treeId: 33,
      level: 2,
      tag: "refund",
    });
  });
});
