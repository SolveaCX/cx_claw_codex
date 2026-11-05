import { AsyncEntry } from "@napi-rs/keyring";
import { mkdir, rmdir, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AuthSession, Session, SessionContext, TenantProfile } from "./types.js";

const options =
  process.platform === "linux" ? { linux: { store: "secret-service" as const } } : undefined;
const keyringEntry = (account: string) => new AsyncEntry("com.solvea.cxclaw", account, options);
const VAULT_ACCOUNT = "vault:v1";
const LEGACY_ACCOUNT = "session";
const AUTH_ACCOUNT = "auth";
const METADATA_ACCOUNT = "metadata";
export const LEGACY_CONTEXT_ID = "legacy-default";

interface StoreMetadata {
  contexts: string[];
  profiles: string[];
}

interface CredentialVault {
  version: 1;
  auth?: AuthSession;
  profiles: Record<string, TenantProfile>;
  contexts: Record<string, SessionContext>;
}

export interface CredentialBackend {
  get(account: string): Promise<string | null>;
  set(account: string, value: string): Promise<void>;
  remove(account: string): Promise<void>;
}

type StoreLock = <T>(task: () => Promise<T>) => Promise<T>;

const keyringBackend: CredentialBackend = {
  get: (account) => keyringEntry(account).getPassword(),
  set: (account, value) => keyringEntry(account).setPassword(value),
  remove: async (account) => {
    await keyringEntry(account)
      .deleteCredential()
      .catch(() => undefined);
  },
};

const vaultLock = join(tmpdir(), "cxclaw-credential-vault-v1.lock");
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function withVaultLock<T>(task: () => Promise<T>): Promise<T> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      await mkdir(vaultLock);
      try {
        return await task();
      } finally {
        await rmdir(vaultLock).catch(() => undefined);
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      const lockStat = await stat(vaultLock).catch(() => undefined);
      if (lockStat && Date.now() - lockStat.mtimeMs > 30_000)
        await rmdir(vaultLock).catch(() => undefined);
      await sleep(50);
    }
  }
  throw new Error("timed out waiting for CXClaw credential vault lock");
}

const emptyVault = (): CredentialVault => ({
  version: 1,
  profiles: {},
  contexts: {},
});

function authOnly(session: Session): AuthSession {
  const { accessToken, refreshToken, accessExpiry, employeeId, email, channel } = session;
  return { accessToken, refreshToken, accessExpiry, employeeId, email, channel };
}

export class SessionNotFoundError extends Error {
  constructor() {
    super("未登录");
    this.name = "SessionNotFoundError";
  }
}

export class SessionStore {
  constructor(
    private readonly backend: CredentialBackend = keyringBackend,
    private readonly lock: StoreLock = withVaultLock,
  ) {}

  private async readEntry<T>(account: string): Promise<T | undefined> {
    const raw = await this.backend.get(account);
    return raw ? (JSON.parse(raw) as T) : undefined;
  }

  private async writeEntry(account: string, value: unknown): Promise<void> {
    await this.backend.set(account, JSON.stringify(value));
  }

  private async legacyVault(): Promise<{ vault: CredentialVault; accounts: string[] } | undefined> {
    // Read legacy entries serially so macOS never stacks multiple Keychain dialogs.
    const storedAuth = await this.readEntry<AuthSession>(AUTH_ACCOUNT);
    const legacySession = await this.readEntry<Session>(LEGACY_ACCOUNT);
    const metadata = await this.readEntry<StoreMetadata>(METADATA_ACCOUNT);
    if (!storedAuth && !legacySession && !metadata) return undefined;

    const profileIds = new Set(metadata?.profiles ?? []);
    const contextIds = new Set(metadata?.contexts ?? []);
    const vault = emptyVault();
    vault.auth = storedAuth ?? (legacySession ? authOnly(legacySession) : undefined);

    if (legacySession?.tenant?.accountId) {
      const now = Date.now();
      const profileId = `legacy-${legacySession.tenant.environment}-${legacySession.tenant.accountId}`;
      vault.profiles[profileId] = {
        ...legacySession.tenant,
        profileId,
        displayName:
          legacySession.tenant.companyName ?? legacySession.tenant.accountName ?? profileId,
        createdAt: now,
        updatedAt: now,
      };
      vault.contexts[LEGACY_CONTEXT_ID] = {
        contextId: LEGACY_CONTEXT_ID,
        activeProfileId: profileId,
        createdAt: now,
        updatedAt: now,
      };
    }

    for (const id of profileIds) {
      const profile = await this.readEntry<TenantProfile>(`profile:${id}`);
      if (profile) vault.profiles[id] = profile;
    }
    for (const id of contextIds) {
      const context = await this.readEntry<SessionContext>(`context:${id}`);
      if (context) vault.contexts[id] = context;
    }

    return {
      vault,
      accounts: [
        AUTH_ACCOUNT,
        LEGACY_ACCOUNT,
        METADATA_ACCOUNT,
        ...[...profileIds].map((id) => `profile:${id}`),
        ...[...contextIds].map((id) => `context:${id}`),
      ],
    };
  }

  private async readVaultUnlocked(): Promise<CredentialVault | undefined> {
    const current = await this.readEntry<CredentialVault>(VAULT_ACCOUNT);
    if (current) {
      if (current.version !== 1) throw new Error("unsupported CXClaw credential vault version");
      return current;
    }

    const legacy = await this.legacyVault();
    if (!legacy) return undefined;

    await this.writeEntry(VAULT_ACCOUNT, legacy.vault);
    for (const account of legacy.accounts) await this.backend.remove(account);
    return legacy.vault;
  }

  private async readVault(): Promise<CredentialVault | undefined> {
    return this.lock(() => this.readVaultUnlocked());
  }

  private async updateVault(
    update: (vault: CredentialVault) => void,
    createIfMissing = true,
  ): Promise<void> {
    await this.lock(async () => {
      const current = await this.readVaultUnlocked();
      if (!current && !createIfMissing) return;
      const vault = current ?? emptyVault();
      update(vault);
      await this.writeEntry(VAULT_ACCOUNT, vault);
    });
  }

  async loadAuthSession(): Promise<AuthSession> {
    const auth = (await this.readVault())?.auth;
    if (!auth) throw new SessionNotFoundError();
    return auth;
  }

  async saveAuthSession(session: AuthSession): Promise<void> {
    if (!session.refreshToken) throw new Error("refusing to persist an empty session");
    await this.updateVault((vault) => {
      vault.auth = session;
    });
  }

  async deleteAuthSession(): Promise<void> {
    await this.updateVault((vault) => {
      delete vault.auth;
    }, false);
  }

  async loadProfile(profileId: string): Promise<TenantProfile> {
    const profile = (await this.readVault())?.profiles[profileId];
    if (!profile) throw new Error(`tenant profile not found: ${profileId}`);
    return profile;
  }

  async saveProfile(profile: TenantProfile): Promise<void> {
    await this.updateVault((vault) => {
      vault.profiles[profile.profileId] = profile;
    });
  }

  async deleteProfile(profileId: string): Promise<void> {
    await this.updateVault((vault) => {
      delete vault.profiles[profileId];
      for (const context of Object.values(vault.contexts)) {
        if (context.activeProfileId === profileId) {
          context.activeProfileId = undefined;
          context.updatedAt = Date.now();
        }
      }
    }, false);
  }

  async listProfiles(): Promise<TenantProfile[]> {
    const profiles = Object.values((await this.readVault())?.profiles ?? {});
    return profiles.sort((a, b) => a.profileId.localeCompare(b.profileId));
  }

  async loadContext(contextId: string): Promise<SessionContext> {
    const context = (await this.readVault())?.contexts[contextId];
    if (!context) throw new Error(`CXClaw context not found: ${contextId}`);
    return context;
  }

  async tryLoadContext(contextId: string): Promise<SessionContext | undefined> {
    return (await this.readVault())?.contexts[contextId];
  }

  async saveContext(context: SessionContext): Promise<void> {
    await this.updateVault((vault) => {
      vault.contexts[context.contextId] = context;
    });
  }

  async listContexts(): Promise<SessionContext[]> {
    const contexts = Object.values((await this.readVault())?.contexts ?? {});
    return contexts.sort((a, b) => a.contextId.localeCompare(b.contextId));
  }

  async deleteAllSessions(): Promise<void> {
    await this.lock(async () => {
      const vault = await this.readVaultUnlocked();
      await this.backend.remove(VAULT_ACCOUNT);
      await Promise.all([
        this.backend.remove(AUTH_ACCOUNT),
        this.backend.remove(LEGACY_ACCOUNT),
        this.backend.remove(METADATA_ACCOUNT),
        ...Object.keys(vault?.profiles ?? {}).map((id) => this.backend.remove(`profile:${id}`)),
        ...Object.keys(vault?.contexts ?? {}).map((id) => this.backend.remove(`context:${id}`)),
      ]);
    });
  }
}

const store = new SessionStore();

export const loadAuthSession = () => store.loadAuthSession();
export const saveAuthSession = (session: AuthSession) => store.saveAuthSession(session);
export const deleteAuthSession = () => store.deleteAuthSession();
export const loadProfile = (profileId: string) => store.loadProfile(profileId);
export const saveProfile = (profile: TenantProfile) => store.saveProfile(profile);
export const deleteProfile = (profileId: string) => store.deleteProfile(profileId);
export const listProfiles = () => store.listProfiles();
export const loadContext = (contextId: string) => store.loadContext(contextId);
export const tryLoadContext = (contextId: string) => store.tryLoadContext(contextId);
export const saveContext = (context: SessionContext) => store.saveContext(context);
export const listContexts = () => store.listContexts();
export const deleteAllSessions = () => store.deleteAllSessions();
