import { describe, expect, test } from "bun:test";
import { AUTH_SERVER_URL } from "./config.js";
import { request } from "./http.js";

describe("production authorization server", () => {
  test("uses the fixed production control-plane URL", () => {
    expect(AUTH_SERVER_URL).toBe("https://ai.solvea.cx/api_v2/ticket");
  });

  test("ignores local session data when building control-plane requests", async () => {
    const originalFetch = globalThis.fetch;
    let requestedUrl = "";
    globalThis.fetch = (async (input: string | URL | Request) => {
      requestedUrl = String(input);
      return new Response(JSON.stringify({ data: { ok: true } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;

    try {
      await request({
        accessToken: "",
        refreshToken: "",
        accessExpiry: 0,
        employeeId: "",
        email: "",
        channel: "stable",
      }, "/plugin-config");
      expect(requestedUrl).toBe(`${AUTH_SERVER_URL}/plugin-config`);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
