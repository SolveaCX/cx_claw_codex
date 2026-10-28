import { afterEach, expect, test } from "bun:test";
import LogClient from "@alicloud/log";
import { query } from "./sls.js";
import type { Session } from "./types.js";

const originalFetch = globalThis.fetch;
const originalGetLogs = (LogClient as any).prototype.getLogs;

afterEach(() => {
  globalThis.fetch = originalFetch;
  (LogClient as any).prototype.getLogs = originalGetLogs;
});

test("SLS query uses employee access and explicit environment without tenant context", async () => {
  let requestBody: unknown;
  let requestHeaders: Headers | undefined;
  globalThis.fetch = (async (_input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
    requestBody = JSON.parse(String(init?.body));
    requestHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({ data: {
      endpoint: "test.log.aliyuncs.com",
      project: "project",
      logstore: "logstore",
      credentials: { accessKeyId: "ak", accessKeySecret: "sk" },
      limits: { maxTimeRangeSeconds: 7200, maxResults: 200, maxConcurrency: 2, maxMessageChars: 20000 },
    } }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;
  (LogClient as any).prototype.getLogs = async () => ({ body: [] });
  const session: Session = {
    accessToken: "employee-access",
    refreshToken: "refresh",
    accessExpiry: 2_000_000_000,
    employeeId: "1",
    email: "employee@example.test",
    channel: "stable",
  };

  await query(session, { environment: "test", from: 100, to: 200, query: "*", line: 1, offset: 0, reverse: false });

  expect(requestBody).toEqual({ environment: "staging" });
  expect(requestHeaders?.get("authorization")).toBe("Bearer employee-access");
  expect(requestHeaders?.has("x-cxclaw-tenant-context")).toBe(false);
});

test("SLS query never inherits the environment from a previous tenant", async () => {
  let requested = false;
  globalThis.fetch = (async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) => {
    requested = true;
    throw new Error("unexpected request");
  }) as unknown as typeof fetch;
  const session: Session = {
    accessToken: "employee-access",
    refreshToken: "refresh",
    accessExpiry: 2_000_000_000,
    employeeId: "1",
    email: "employee@example.test",
    channel: "stable",
    tenant: { accountId: 1, accountCode: "V1", accountName: "Tenant", environment: "prod", purpose: "old", expiresAt: 2_000_000_000 },
  };

  await expect(query(session, { from: 100, to: 200, query: "*", line: 1, offset: 0, reverse: false }))
    .rejects.toThrow("SLS environment is required; use --env test or --env prod");
  expect(requested).toBe(false);
});

test("SLS query surfaces the authorization service business error", async () => {
  globalThis.fetch = (async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) => new Response(
    JSON.stringify({ code: 200, message: "SLS session is not configured" }),
    { status: 200, headers: { "content-type": "application/json" } },
  )) as unknown as typeof fetch;
  const session: Session = {
    accessToken: "employee-access",
    refreshToken: "refresh",
    accessExpiry: 2_000_000_000,
    employeeId: "1",
    email: "employee@example.test",
    channel: "stable",
  };

  await expect(query(session, { environment: "test", from: 100, to: 200, query: "*", line: 1, offset: 0, reverse: false }))
    .rejects.toThrow("SLS credential request failed: SLS session is not configured");
});
