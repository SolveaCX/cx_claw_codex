import { afterEach, describe, expect, test } from "bun:test";
import type { Session } from "../types.js";
import { isNativeSolveaCommand, runSolveaCommand } from "./commands.js";

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

describe("native Solvea command registry", () => {
  test("keeps migrated API commands explicit", () => {
    expect(isNativeSolveaCommand("get-agent")).toBe(true);
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
      "--type", "QA", "--page", "2", "--page-size", "5", "--keyword", "充值",
    ]);

    const request = requests.at(-1);
    expect(request?.url).toEndWith("/sns_v1/project/302/getKnowledge");
    expect(request?.init?.method).toBe("POST");
    expect(JSON.parse(String(request?.init?.body))).toEqual({
      type: "QA", pageIndex: 2, pageSize: 5, keyword: "充值",
    });
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
      "--data", JSON.stringify({ type: "ALL", pageIndex: 9, pageSize: 99, keyword: "旧值", directoryId: 33727 }),
      "--type", "QA", "--page", "3", "--page-size", "10", "--keyword", "新值",
    ]);

    expect(requestBody).toEqual({
      type: "QA", pageIndex: 3, pageSize: 10, keyword: "新值", directoryId: 33727,
    });
  });

  test("routes resource detail reads using the required knowledge type", async () => {
    const requests: string[] = [];
    globalThis.fetch = (async input => {
      requests.push(String(input));
      const body = String(input).endsWith("/api_v2/gpt/bots") ? [{ projectId: 302 }] : { id: 8 };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;

    await runSolveaCommand(session, "get-knowledge", ["--id", "8", "--type", "WEBSITE"]);

    expect(requests.at(-1)).toEndWith("/sns_v1/project/302/document/8");
  });
});
