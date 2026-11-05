import { describe, expect, test } from "bun:test";
import { SessionNotFoundError, SessionStore, type CredentialBackend } from "./store.js";
import type { AuthSession, Session, SessionContext, TenantProfile } from "./types.js";

class MemoryBackend implements CredentialBackend {
  readonly values = new Map<string, string>();
  readonly removed: string[] = [];
  failSet = false;

  async get(account: string) {
    return this.values.get(account) ?? null;
  }

  async set(account: string, value: string) {
    if (this.failSet) throw new Error("keychain write failed");
    this.values.set(account, value);
  }

  async remove(account: string) {
    this.removed.push(account);
    this.values.delete(account);
  }

  put(account: string, value: unknown) {
    this.values.set(account, JSON.stringify(value));
  }
}

const unlocked = async <T>(task: () => Promise<T>) => task();

const auth: AuthSession = {
  accessToken: "access",
  refreshToken: "refresh",
  accessExpiry: 1,
  employeeId: "employee",
  email: "employee@example.com",
  channel: "stable",
};

const profile: TenantProfile = {
  profileId: "production",
  displayName: "Production",
  accountId: 12,
  accountCode: "account",
  accountName: "Account",
  environment: "product",
  purpose: "support",
  businessToken: "business-token",
  expiresAt: 2,
  createdAt: 1,
  updatedAt: 1,
};

const context: SessionContext = {
  contextId: "workspace",
  activeProfileId: profile.profileId,
  createdAt: 1,
  updatedAt: 1,
};

describe("credential vault", () => {
  test("stores all current state in one keychain entry", async () => {
    const backend = new MemoryBackend();
    const store = new SessionStore(backend, unlocked);

    await store.saveAuthSession(auth);
    await store.saveProfile(profile);
    await store.saveContext(context);

    expect([...backend.values.keys()]).toEqual(["vault:v1"]);
    expect(await store.loadAuthSession()).toEqual(auth);
    expect(await store.listProfiles()).toEqual([profile]);
    expect(await store.listContexts()).toEqual([context]);
  });

  test("migrates legacy entries before deleting them", async () => {
    const backend = new MemoryBackend();
    backend.put("auth", auth);
    backend.put("metadata", { profiles: [profile.profileId], contexts: [context.contextId] });
    backend.put(`profile:${profile.profileId}`, profile);
    backend.put(`context:${context.contextId}`, context);
    const store = new SessionStore(backend, unlocked);

    expect(await store.loadProfile(profile.profileId)).toEqual(profile);
    expect([...backend.values.keys()]).toEqual(["vault:v1"]);
    expect(backend.removed).toEqual([
      "auth",
      "session",
      "metadata",
      `profile:${profile.profileId}`,
      `context:${context.contextId}`,
    ]);
  });

  test("converts the original combined session during migration", async () => {
    const backend = new MemoryBackend();
    const legacy: Session = { ...auth, tenant: profile };
    backend.put("session", legacy);
    const store = new SessionStore(backend, unlocked);

    expect(await store.loadAuthSession()).toEqual(auth);
    expect(await store.loadProfile("legacy-product-12")).toMatchObject({
      accountId: 12,
      businessToken: "business-token",
    });
    expect(await store.loadContext("legacy-default")).toMatchObject({
      activeProfileId: "legacy-product-12",
    });
  });

  test("preserves legacy entries when the vault write fails", async () => {
    const backend = new MemoryBackend();
    backend.put("auth", auth);
    backend.put("metadata", { profiles: [profile.profileId], contexts: [] });
    backend.put(`profile:${profile.profileId}`, profile);
    backend.failSet = true;
    const store = new SessionStore(backend, unlocked);

    await expect(store.loadAuthSession()).rejects.toThrow("keychain write failed");
    expect(backend.values.has("auth")).toBe(true);
    expect(backend.values.has(`profile:${profile.profileId}`)).toBe(true);
    expect(backend.removed).toEqual([]);
  });

  test("updates profile references atomically when deleting a profile", async () => {
    const backend = new MemoryBackend();
    const store = new SessionStore(backend, unlocked);
    await store.saveProfile(profile);
    await store.saveContext(context);

    await store.deleteProfile(profile.profileId);

    expect(await store.listProfiles()).toEqual([]);
    const updatedContext = await store.loadContext(context.contextId);
    expect(updatedContext.contextId).toBe(context.contextId);
    expect(updatedContext.activeProfileId).toBeUndefined();
    expect(updatedContext.updatedAt).toBeGreaterThan(context.updatedAt);
  });

  test("reports a missing login without creating a keychain entry", async () => {
    const backend = new MemoryBackend();
    const store = new SessionStore(backend, unlocked);

    await expect(store.loadAuthSession()).rejects.toBeInstanceOf(SessionNotFoundError);
    await store.deleteAuthSession();
    expect(backend.values.size).toBe(0);
  });
});
