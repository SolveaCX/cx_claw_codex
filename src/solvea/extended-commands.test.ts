import { afterEach, describe, expect, test } from "bun:test";
import type { Session } from "../types.js";
import { SolveaClient } from "./client.js";
import { runExtendedCommand } from "./extended-commands.js";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const session: Session = {
  accessToken: "access", refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000, employeeId: "employee", email: "employee@example.com", channel: "dev",
  tenant: {
    accountId: 1, accountCode: "test", accountName: "Test", environment: "staging",
    purpose: "test", businessUrl: "https://apps-staging.example", businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

describe("extended TypeScript business commands", () => {
  test("calls the managed AI Field paging endpoint", async () => {
    let request: { url: string; init?: RequestInit } | undefined;
    globalThis.fetch = (async (input, init) => {
      request = { url: String(input), init };
      return new Response(JSON.stringify({ code: 0, data: [] }), { status: 200 });
    }) as typeof fetch;

    await runExtendedCommand(new SolveaClient(session), "list-managed-ai-fields", ["--page", "2", "--page-size", "20", "--keyword", "order"]);

    expect(request?.url).toEndWith("/api_v2/tars/api/field/manage/page");
    expect(request?.init?.method).toBe("POST");
    expect(JSON.parse(String(request?.init?.body))).toEqual({ pageIndex: 2, pageSize: 20, name: "order" });
  });

  test("blocks destructive template deletion without confirmation", async () => {
    await expect(runExtendedCommand(new SolveaClient(session), "delete-templates", ["--ids", "1", "2"]))
      .rejects.toThrow("--confirm-delete");
  });

  test("rejects unsafe mock data path segments before a request", async () => {
    await expect(runExtendedCommand(new SolveaClient(session), "query-mock-data", ["--name", "../secret"]))
      .rejects.toThrow("safe non-empty path segment");
  });
});
