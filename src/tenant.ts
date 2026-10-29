import { createHash, randomUUID } from "node:crypto";
import { mkdir, rmdir, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { post } from "./http.js";
import { SolveaClient } from "./solvea/client.js";
import { LEGACY_CONTEXT_ID, listContexts, listProfiles, loadContext, loadProfile, saveContext, saveProfile, tryLoadContext } from "./store.js";
import type { AuthSession, Session, SessionContext, Tenant, TenantProfile } from "./types.js";

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const profileLocks = new Map<string, Promise<TenantProfile>>();

export function environment(value?:string){const v=(value??"prod").toLowerCase();if(v==="test"||v==="staging")return "staging";if(v==="prod"||v==="production")return "prod";throw new Error(`unsupported environment ${value}; use test/staging or prod`)}
export async function search(session:AuthSession,query:string,env?:string){return (await post<{items:unknown[]}>(session,"/tenants/search",{query,environment:environment(env)})).items}

function identifier(value: string, name: string): string {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(normalized)) throw new Error(`${name} must contain only letters, numbers, dot, underscore, colon, or dash`);
  return normalized;
}

export function newContextId(): string { return `ctx_${randomUUID().replaceAll("-", "_")}`; }

export async function createContext(requestedId?: string): Promise<SessionContext> {
  const contextId = requestedId ? identifier(requestedId, "contextId") : newContextId();
  if (await tryLoadContext(contextId)) throw new Error(`CXClaw context already exists: ${contextId}`);
  const now = Date.now();
  const context = { contextId, createdAt: now, updatedAt: now };
  await saveContext(context);
  return context;
}

export async function bindContext(contextId: string, profileId: string): Promise<SessionContext> {
  const context = await loadContext(identifier(contextId, "contextId"));
  await loadProfile(identifier(profileId, "profileId"));
  const updated = { ...context, activeProfileId: profileId, updatedAt: Date.now() };
  await saveContext(updated);
  return updated;
}

export async function clearContext(contextId: string): Promise<SessionContext> {
  const context = await loadContext(identifier(contextId, "contextId"));
  const updated = { ...context, activeProfileId: undefined, updatedAt: Date.now() };
  await saveContext(updated);
  return updated;
}

function asTenant(profile: TenantProfile): Tenant {
  const { profileId: _profileId, displayName: _displayName, createdAt: _createdAt, updatedAt: _updatedAt, ...tenant } = profile;
  return structuredClone(tenant);
}

function requestSession(auth: AuthSession, profile: TenantProfile, contextId: string): Session {
  return { ...auth, tenant: asTenant(profile), runtimeContext: { contextId, profileId: profile.profileId } };
}

async function issueProfile(auth: AuthSession, accountId: number, env: string | undefined, purpose: string, profileId: string, displayName?: string, createdAt = Date.now()): Promise<TenantProfile> {
  if (!Number.isSafeInteger(accountId) || accountId <= 0) throw new Error("accountId must be a positive integer");
  if (!purpose?.trim()) throw new Error("purpose is required");
  const normalizedProfileId = identifier(profileId, "profileId");
  const response=await post<any>(auth,"/tenant-contexts",{accountId,environment:environment(env),purpose:purpose.trim()});
  if(!response.businessToken||!response.services?.businessUrl)throw new Error("authorization server did not return business credentials");
  const now = Date.now();
  const profile: TenantProfile = {
    ...response.tenant,
    profileId: normalizedProfileId,
    displayName: displayName?.trim() || response.tenant?.companyName || response.tenant?.accountName || normalizedProfileId,
    environment: response.environment,
    purpose: purpose.trim(),
    context: response.tenantContext,
    businessToken: response.businessToken,
    businessUrl: response.services.businessUrl.replace(/\/$/,""),
    slsUrl: response.services.slsUrl?.replace(/\/$/,""),
    expiresAt: response.businessTokenExpiresAt||Math.floor(Date.now()/1000)+response.expiresIn,
    createdAt,
    updatedAt: now,
  };
  await saveProfile(profile);
  try {
    const info = await new SolveaClient(requestSession(auth, profile, `profile-setup:${normalizedProfileId}`)).currentTenantInfo();
    const companyName = typeof info.companyName === "string" ? info.companyName.trim() : "";
    if (Number(info.accountId) === accountId && companyName) {
      profile.companyName = companyName;
      if (!displayName?.trim()) profile.displayName = companyName;
      profile.updatedAt = Date.now();
      await saveProfile(profile);
    }
  } catch {
    // Company metadata is optional; profile authorization must still succeed.
  }
  return profile;
}

export async function createOrRefreshProfile(auth: AuthSession, options: { accountId: number; env?: string; purpose: string; profileId: string; displayName?: string }): Promise<TenantProfile> {
  let createdAt = Date.now();
  try { createdAt = (await loadProfile(options.profileId)).createdAt; } catch { /* new profile */ }
  return issueProfile(auth, options.accountId, options.env, options.purpose, options.profileId, options.displayName, createdAt);
}

async function withCrossProcessProfileLock(profileId: string, task: () => Promise<TenantProfile>): Promise<TenantProfile> {
  const digest = createHash("sha256").update(profileId).digest("hex").slice(0, 24);
  const lock = join(tmpdir(), `cxclaw-profile-${digest}.lock`);
  for (let attempt = 0; attempt < 2_400; attempt += 1) {
    try {
      await mkdir(lock);
      try { return await task(); } finally { await rmdir(lock).catch(() => undefined); }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      const lockStat = await stat(lock).catch(() => undefined);
      if (lockStat && Date.now() - lockStat.mtimeMs > 180_000) await rmdir(lock).catch(() => undefined);
      await sleep(50);
    }
  }
  throw new Error(`timed out waiting for tenant profile refresh: ${profileId}`);
}

async function ensureProfile(auth: AuthSession, profileId: string): Promise<TenantProfile> {
  const initial = await loadProfile(profileId);
  if (Date.now()/1000+30 < initial.expiresAt) return initial;
  const existing = profileLocks.get(profileId);
  if (existing) return existing;
  const refresh = withCrossProcessProfileLock(profileId, async () => {
    const latest = await loadProfile(profileId);
    if (Date.now()/1000+30 < latest.expiresAt) return latest;
    return issueProfile(auth, latest.accountId, latest.environment, latest.purpose, latest.profileId, latest.displayName, latest.createdAt);
  });
  profileLocks.set(profileId, refresh);
  try { return await refresh; } finally { profileLocks.delete(profileId); }
}

export async function resolveTenantSession(
  auth: AuthSession,
  options: { contextId?: string; profileId?: string; allowLegacy?: boolean } = {},
  dependencies: {
    loadContext?: (contextId: string) => Promise<SessionContext>;
    tryLoadContext?: (contextId: string) => Promise<SessionContext | undefined>;
    loadProfile?: (profileId: string) => Promise<TenantProfile>;
  } = {},
): Promise<Session> {
  const contextLoader = dependencies.loadContext ?? loadContext;
  const contextTryLoader = dependencies.tryLoadContext ?? tryLoadContext;
  const profileLoader = dependencies.loadProfile;
  let profileId = options.profileId ? identifier(options.profileId, "profileId") : undefined;
  let contextId = options.contextId ? identifier(options.contextId, "contextId") : undefined;
  if (!profileId && contextId) {
    const context = await contextLoader(contextId);
    profileId = context.activeProfileId;
    if (!profileId) throw new Error(`CXClaw context has no selected tenant profile: ${contextId}`);
  }
  if (!profileId && !contextId && options.allowLegacy !== false) {
    const legacy = await contextTryLoader(LEGACY_CONTEXT_ID);
    profileId = legacy?.activeProfileId;
    contextId = legacy ? LEGACY_CONTEXT_ID : undefined;
  }
  if (!profileId) throw new Error("no tenant context selected; pass --context <contextId> or --profile <profileId>");
  const profile = profileLoader ? await profileLoader(profileId) : await ensureProfile(auth, profileId);
  return requestSession(auth, profile, contextId ?? `profile-override:${profileId}`);
}

export function publicTenant(t?:Tenant){return t?{accountId:t.accountId,accountCode:t.accountCode,accountName:t.accountName,companyName:t.companyName,environment:t.environment,purpose:t.purpose,expiresAt:t.expiresAt,configured:Boolean(t.businessToken&&t.businessUrl)}:{configured:false}}
export function publicProfile(profile: TenantProfile) {
  return { profileId: profile.profileId, displayName: profile.displayName, ...publicTenant(profile), createdAt: profile.createdAt, updatedAt: profile.updatedAt };
}
export async function publicContext(context: SessionContext) {
  if (!context.activeProfileId) return { ...context, configured: false };
  try { return { ...context, configured: true, profile: publicProfile(await loadProfile(context.activeProfileId)) }; }
  catch { return { ...context, activeProfileId: undefined, configured: false }; }
}
export async function publicContexts() { return Promise.all((await listContexts()).map(publicContext)); }
export async function publicProfiles() { return Promise.all((await listProfiles()).map(publicProfile)); }

/** Backward-compatible helper for request-local sessions. */
export async function ensureTenant(session:Session){if(!session.tenant?.accountId)throw new Error("no tenant selected; pass --context <contextId> or --profile <profileId>");return session.tenant}
