import { describe, expect, test } from "bun:test";
import { environment, newContextId, resolveTenantSession } from "./tenant.js";
import type { AuthSession, SessionContext, TenantProfile } from "./types.js";

test("tenant environment defaults to production", () => {
  expect(environment()).toBe("prod");
  expect(environment("test")).toBe("staging");
  expect(environment("prod")).toBe("prod");
});

const auth: AuthSession = { accessToken: "access", refreshToken: "refresh", accessExpiry: 9999999999, employeeId: "e1", email: "e@example.com", channel: "stable" };
const profile = (profileId: string, accountId: number, context: string): TenantProfile => ({
  profileId, displayName: profileId, accountId, accountCode: `A${accountId}`, accountName: profileId,
  environment: "prod", purpose: "test", context, businessToken: `token-${profileId}`,
  businessUrl: `https://${profileId}.example.com`, expiresAt: 9999999999, createdAt: 1, updatedAt: 1,
});

describe("tenant context isolation", () => {
  test("generates opaque unique context ids", () => {
    const first = newContextId(), second = newContextId();
    expect(first).toMatch(/^ctx_[0-9a-f_]+$/);
    expect(second).not.toBe(first);
  });

  test("resolves two contexts to independent request-local tenant snapshots", async () => {
    const contexts: Record<string, SessionContext> = {
      a: { contextId: "a", activeProfileId: "profile-a", createdAt: 1, updatedAt: 1 },
      b: { contextId: "b", activeProfileId: "profile-b", createdAt: 1, updatedAt: 1 },
    };
    const profiles: Record<string, TenantProfile> = {
      "profile-a": profile("profile-a", 10, "tenant-context-a"),
      "profile-b": profile("profile-b", 20, "tenant-context-b"),
    };
    const dependencies = {
      loadContext: async (id: string) => contexts[id],
      tryLoadContext: async (id: string) => contexts[id],
      loadProfile: async (id: string) => profiles[id],
    };

    const [a, b] = await Promise.all([
      resolveTenantSession(auth, { contextId: "a" }, dependencies),
      resolveTenantSession(auth, { contextId: "b" }, dependencies),
    ]);
    expect(a.runtimeContext).toEqual({ contextId: "a", profileId: "profile-a" });
    expect(a.tenant?.context).toBe("tenant-context-a");
    expect(b.runtimeContext).toEqual({ contextId: "b", profileId: "profile-b" });
    expect(b.tenant?.context).toBe("tenant-context-b");

    contexts.a = { ...contexts.a, activeProfileId: "profile-b" };
    const switched = await resolveTenantSession(auth, { contextId: "a" }, dependencies);
    expect(switched.tenant?.accountId).toBe(20);
    expect(b.tenant?.accountId).toBe(20);
    expect(b.runtimeContext?.contextId).toBe("b");
  });

  test("explicit profile overrides context and no implicit global tenant is accepted", async () => {
    const selected = await resolveTenantSession(auth, { contextId: "a", profileId: "profile-b" }, {
      loadProfile: async id => profile(id, 20, "tenant-context-b"),
    });
    expect(selected.runtimeContext).toEqual({ contextId: "a", profileId: "profile-b" });
    await expect(resolveTenantSession(auth, { allowLegacy: false }, { tryLoadContext: async () => undefined })).rejects.toThrow("pass --context");
  });
});
