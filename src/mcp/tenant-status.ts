import { loadAuthSession, loadContext, loadProfile, SessionNotFoundError } from "../store.js";
import { publicTenant } from "../tenant.js";
import type { AuthSession, Session, SessionContext, TenantProfile } from "../types.js";

export type TenantCredentialStatus = "active" | "expired" | "not_selected" | "not_logged_in" | "unavailable";

export interface TenantPanelStatus {
  checkedAt: number;
  loggedIn: boolean;
  configured: boolean;
  contextRequired?: boolean;
  credentialStatus: TenantCredentialStatus;
  contextId?: string;
  profileId?: string;
  accountId?: number;
  accountCode?: string;
  accountName?: string;
  companyName?: string;
  environment?: string;
  purpose?: string;
  expiresAt?: number;
}

export function tenantPanelStatus(session: Session | undefined, now = Date.now()): TenantPanelStatus {
  const checkedAt = Math.floor(now / 1000);
  if (!session) return { checkedAt, loggedIn: false, configured: false, credentialStatus: "not_logged_in" };
  const tenant = publicTenant(session.tenant);
  if (!tenant.configured || !("accountId" in tenant)) return { checkedAt, loggedIn: true, configured: false, credentialStatus: "not_selected" };
  const expiresAt = tenant.expiresAt ?? 0;
  return {
    checkedAt,
    loggedIn: true,
    ...tenant,
    contextId: session.runtimeContext?.contextId,
    profileId: session.runtimeContext?.profileId,
    expiresAt,
    credentialStatus: expiresAt <= checkedAt ? "expired" : "active",
  };
}

function contextStatus(auth: AuthSession, context: SessionContext, profile: TenantProfile | undefined, now: number): TenantPanelStatus {
  if (!profile) return { checkedAt: Math.floor(now / 1000), loggedIn: true, configured: false, contextId: context.contextId, credentialStatus: "not_selected" };
  return tenantPanelStatus({ ...auth, tenant: profile, runtimeContext: { contextId: context.contextId, profileId: profile.profileId } }, now);
}

export async function loadTenantPanelStatus(
  contextId?: string,
  dependencies: {
    loadAuth?: () => Promise<AuthSession>;
    loadContext?: (id: string) => Promise<SessionContext>;
    loadProfile?: (id: string) => Promise<TenantProfile>;
  } = {},
  now = Date.now(),
): Promise<TenantPanelStatus> {
  try {
    const auth = await (dependencies.loadAuth ?? loadAuthSession)();
    if (!contextId) return { checkedAt: Math.floor(now / 1000), loggedIn: true, configured: false, contextRequired: true, credentialStatus: "not_selected" };
    const context = await (dependencies.loadContext ?? loadContext)(contextId);
    if (!context.activeProfileId) return contextStatus(auth, context, undefined, now);
    const profile = await (dependencies.loadProfile ?? loadProfile)(context.activeProfileId);
    return contextStatus(auth, context, profile, now);
  } catch (error) {
    if (error instanceof SessionNotFoundError) return tenantPanelStatus(undefined, now);
    return { checkedAt: Math.floor(now / 1000), loggedIn: false, configured: false, credentialStatus: "unavailable" };
  }
}
