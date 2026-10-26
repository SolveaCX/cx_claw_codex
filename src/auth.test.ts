import { describe, expect, test } from "bun:test";
import { authorizeDevice, isAuthorizationPending, publicAuthStatus, resolveAuthenticated } from "./auth.js";
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

describe("device authorization wait", () => {
  const start = {
    deviceCode: "device-code",
    userCode: "user-code",
    verificationUriComplete: "https://example.test/authorize?code=user-code",
    expiresIn: 600,
    interval: 2,
  };
  const token = {
    accessToken: "new-access-token",
    refreshToken: "new-refresh-token",
    expiresIn: 900,
    employee: { id: "employee-2", email: "employee-2@example.com" },
  };

  test("recognizes pending authorization from HTTP status or response code", () => {
    expect(isAuthorizationPending(new HttpError(428, '{"message":"pending"}'))).toBe(true);
    expect(isAuthorizationPending(new HttpError(400, '{"code":428,"message":"authorization_pending"}'))).toBe(true);
    expect(isAuthorizationPending(new HttpError(400, '{"code":401,"message":"invalid"}'))).toBe(false);
  });

  test("keeps polling without printing the authorization URL when the browser opens", async () => {
    const logs: string[] = [];
    let polls = 0;
    const result = await authorizeDevice("stable", {
      start: async () => start,
      poll: async () => {
        polls += 1;
        if (polls === 1) throw new HttpError(400, '{"code":428,"message":"authorization_pending"}');
        return token;
      },
      openBrowser: async () => undefined,
      save: async () => undefined,
      sleep: async () => undefined,
      now: () => 0,
      log: message => logs.push(message),
    });

    expect(polls).toBe(2);
    expect(result.accessToken).toBe("new-access-token");
    expect(logs.join("\n")).not.toContain(start.verificationUriComplete);
    expect(logs).toContain("钉钉授权页已打开，当前命令会持续等待授权结果，无需回复 Codex。");
    expect(logs).toContain("钉钉授权成功，继续执行当前命令。");
  });

  test("prints the fallback URL only when the browser cannot be opened", async () => {
    const logs: string[] = [];
    await authorizeDevice("stable", {
      start: async () => start,
      poll: async () => token,
      openBrowser: async () => { throw new Error("cannot open browser"); },
      save: async () => undefined,
      sleep: async () => undefined,
      now: () => 0,
      log: message => logs.push(message),
    });

    expect(logs.join("\n")).toContain(start.verificationUriComplete);
    expect(logs.join("\n")).toContain(start.userCode);
  });
});
