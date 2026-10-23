import { describe, expect, test } from "bun:test";
import { publicAuthStatus } from "./auth.js";

describe("public auth output", () => {
  test("never includes access or refresh credentials", () => {
    const output = publicAuthStatus({
      accessToken: "secret-access-token",
      refreshToken: "secret-refresh-token",
      accessExpiry: 123456,
      employeeId: "employee-1",
      email: "employee@example.com",
      channel: "stable",
    });

    expect(output).toEqual({
      ok: true,
      loggedIn: true,
      email: "employee@example.com",
      channel: "stable",
      accessExpiresAt: 123456,
    });
    expect(JSON.stringify(output)).not.toContain("secret-access-token");
    expect(JSON.stringify(output)).not.toContain("secret-refresh-token");
  });
});
