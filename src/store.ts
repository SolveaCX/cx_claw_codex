import { AsyncEntry } from "@napi-rs/keyring";
import { mkdir, rmdir, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AuthSession, Session, SessionContext, TenantProfile } from "./types.js";

const options = process.platform === "linux" ? { linux: { store: "secret-service" as const } } : undefined;
const entry = (account: string) => new AsyncEntry("com.solvea.cxclaw", account, options);
const LEGACY_ACCOUNT = "session";
const AUTH_ACCOUNT = "auth";
const METADATA_ACCOUNT = "metadata";
export const LEGACY_CONTEXT_ID = "legacy-default";

interface StoreMetadata {
  contexts: string[];
  profiles: string[];
}

const unique = (values: string[]) => [...new Set(values)].sort();
async function readEntry<T>(account: string): Promise<T | undefined> {
  const raw = await entry(account).getPassword();
  return raw ? JSON.parse(raw) as T : undefined;
}
async function writeEntry(account: string, value: unknown): Promise<void> {
  await entry(account).setPassword(JSON.stringify(value));
}
async function removeEntry(account: string): Promise<void> {
  await entry(account).deleteCredential().catch(() => undefined);
}
async function loadMetadata(): Promise<StoreMetadata> {
  return await readEntry<StoreMetadata>(METADATA_ACCOUNT) ?? { contexts: [], profiles: [] };
}
let metadataUpdate = Promise.resolve();
const metadataLock = join(tmpdir(), "cxclaw-metadata.lock");
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
async function withMetadataLock(task: () => Promise<void>): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      await mkdir(metadataLock);
      try { await task(); return; } finally { await rmdir(metadataLock).catch(() => undefined); }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      const lockStat = await stat(metadataLock).catch(() => undefined);
      if (lockStat && Date.now() - lockStat.mtimeMs > 30_000) await rmdir(metadataLock).catch(() => undefined);
      await sleep(50);
    }
  }
  throw new Error("timed out waiting for CXClaw credential metadata lock");
}
async function updateMetadata(update: (value: StoreMetadata) => StoreMetadata): Promise<void> {
  const operation = metadataUpdate.then(() => withMetadataLock(async () => writeEntry(METADATA_ACCOUNT, update(await loadMetadata()))));
  metadataUpdate = operation.catch(() => undefined);
  await operation;
}

export class SessionNotFoundError extends Error {
  constructor() {
    super("未登录");
    this.name = "SessionNotFoundError";
  }
}

function authOnly(session: Session): AuthSession {
  const { accessToken, refreshToken, accessExpiry, employeeId, email, channel } = session;
  return { accessToken, refreshToken, accessExpiry, employeeId, email, channel };
}

export async function loadAuthSession(): Promise<AuthSession> {
  const current = await readEntry<AuthSession>(AUTH_ACCOUNT);
  if (current) return current;
  const legacy = await readEntry<Session>(LEGACY_ACCOUNT);
  if (!legacy) throw new SessionNotFoundError();
  const auth = authOnly(legacy);
  if (legacy.tenant?.accountId) {
    const now = Date.now();
    const profileId = `legacy-${legacy.tenant.environment}-${legacy.tenant.accountId}`;
    await saveProfile({ ...legacy.tenant, profileId, displayName: legacy.tenant.companyName ?? legacy.tenant.accountName ?? profileId, createdAt: now, updatedAt: now });
    await saveContext({ contextId: LEGACY_CONTEXT_ID, activeProfileId: profileId, createdAt: now, updatedAt: now });
  }
  await saveAuthSession(auth);
  await removeEntry(LEGACY_ACCOUNT);
  return auth;
}
export async function saveAuthSession(session: AuthSession): Promise<void> {
  if (!session.refreshToken) throw new Error("refusing to persist an empty session");
  await writeEntry(AUTH_ACCOUNT, session);
}
export async function deleteAuthSession(): Promise<void> { await removeEntry(AUTH_ACCOUNT); await removeEntry(LEGACY_ACCOUNT); }

export async function loadProfile(profileId: string): Promise<TenantProfile> {
  const profile = await readEntry<TenantProfile>(`profile:${profileId}`);
  if (!profile) throw new Error(`tenant profile not found: ${profileId}`);
  return profile;
}
export async function saveProfile(profile: TenantProfile): Promise<void> {
  await writeEntry(`profile:${profile.profileId}`, profile);
  await updateMetadata(value => ({ ...value, profiles: unique([...value.profiles, profile.profileId]) }));
}
export async function deleteProfile(profileId: string): Promise<void> {
  await removeEntry(`profile:${profileId}`);
  const metadata = await loadMetadata();
  for (const contextId of metadata.contexts) {
    const context = await readEntry<SessionContext>(`context:${contextId}`);
    if (context?.activeProfileId === profileId) await saveContext({ ...context, activeProfileId: undefined, updatedAt: Date.now() });
  }
  await updateMetadata(value => ({ ...value, profiles: value.profiles.filter(id => id !== profileId) }));
}
export async function listProfiles(): Promise<TenantProfile[]> {
  const metadata = await loadMetadata();
  const rows = await Promise.all(metadata.profiles.map(id => readEntry<TenantProfile>(`profile:${id}`)));
  return rows.filter((value): value is TenantProfile => Boolean(value));
}

export async function loadContext(contextId: string): Promise<SessionContext> {
  const context = await readEntry<SessionContext>(`context:${contextId}`);
  if (!context) throw new Error(`CXClaw context not found: ${contextId}`);
  return context;
}
export async function tryLoadContext(contextId: string): Promise<SessionContext | undefined> {
  return readEntry<SessionContext>(`context:${contextId}`);
}
export async function saveContext(context: SessionContext): Promise<void> {
  await writeEntry(`context:${context.contextId}`, context);
  await updateMetadata(value => ({ ...value, contexts: unique([...value.contexts, context.contextId]) }));
}
export async function listContexts(): Promise<SessionContext[]> {
  const metadata = await loadMetadata();
  const rows = await Promise.all(metadata.contexts.map(id => readEntry<SessionContext>(`context:${id}`)));
  return rows.filter((value): value is SessionContext => Boolean(value));
}
export async function deleteAllSessions(): Promise<void> {
  try {
    const metadata = await loadMetadata();
    await Promise.all([
      ...metadata.profiles.map(id => removeEntry(`profile:${id}`)),
      ...metadata.contexts.map(id => removeEntry(`context:${id}`)),
    ]);
    await removeEntry(METADATA_ACCOUNT);
  } finally {
    await deleteAuthSession();
  }
}
