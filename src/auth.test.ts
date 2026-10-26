import { describe, expect, test } from "bun:test";
import { publicAuthStatus, resolveAuthenticated } from "./auth.js";
import { HttpError } from "./http.js";
import { SessionNotFoundError } from "./store.js";
import type { Session } from "./types.js";

const session: Session = {
  accessToken: "secret-access-token",
  refreshToken: "secret-refresh-token",
  accessExpiry: 123456,
  employeeId: "employee-1",
  email: "employee@example.com",
  channel: "stable",
};

describe("public auth output", () => {
  test("never includes access or refresh credentials", () => {
    const output = publicAuthStatus(session);

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

describe("automatic authentication", () => {
  test("continues with the stored session when refresh succeeds", async () => {
    let authorized = false;
    const result = await resolveAuthenticated({
      load: async () => session,
      refresh: async value => value,
      remove: async () => undefined,
      authorize: async () => { authorized = true; return session; },
    });

    expect(result).toBe(session);
    expect(authorized).toBe(false);
  });

  test("starts and waits for authorization when no session exists", async () => {
    let authorized = false;
    const result = await resolveAuthenticated({
      load: async () => { throw new SessionNotFoundError(); },
      refresh: async value => value,
      remove: async () => undefined,
      authorize: async () => { authorized = true; return session; },
    });

    expect(result).toBe(session);
    expect(authorized).toBe(true);
  });

  test("removes an invalid session and authorizes again after 401", async () => {
    let removed = false;
    let authorized = false;
    const result = await resolveAuthenticated({
      load: async () => session,
      refresh: async () => { throw new HttpError(401, "expired"); },
      remove: async () => { removed = true; },
      authorize: async () => { authorized = true; return session; },
    });

    expect(result).toBe(session);
    expect(removed).toBe(true);
    expect(authorized).toBe(true);
  });

  test("does not turn server failures into a new authorization flow", async () => {
    let authorized = false;
    const failure = new HttpError(503, "unavailable");
    await expect(resolveAuthenticated({
      load: async () => session,
      refresh: async () => { throw failure; },
      remove: async () => undefined,
      authorize: async () => { authorized = true; return session; },
    })).rejects.toBe(failure);

    expect(authorized).toBe(false);
  });
});
