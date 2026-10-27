import { loadSession, SessionNotFoundError } from "../store.js";
import { publicTenant } from "../tenant.js";
import type { Session } from "../types.js";

export type TenantCredentialStatus = "active" | "expired" | "not_selected" | "not_logged_in" | "unavailable";

export interface TenantPanelStatus {
  checkedAt: number;
  loggedIn: boolean;
  configured: boolean;
  credentialStatus: TenantCredentialStatus;
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
  if (!session) {
    return { checkedAt, loggedIn: false, configured: false, credentialStatus: "not_logged_in" };
  }

  const tenant = publicTenant(session.tenant);
  if (!tenant.configured || !("accountId" in tenant)) {
    return { checkedAt, loggedIn: true, configured: false, credentialStatus: "not_selected" };
  }

  const expiresAt = tenant.expiresAt ?? 0;
  return {
    checkedAt,
    loggedIn: true,
    ...tenant,
    expiresAt,
    credentialStatus: expiresAt <= checkedAt ? "expired" : "active",
  };
}

export async function loadTenantPanelStatus(
  load: () => Promise<Session> = loadSession,
  now = Date.now(),
): Promise<TenantPanelStatus> {
  try {
    return tenantPanelStatus(await load(), now);
  } catch (error) {
    if (error instanceof SessionNotFoundError) return tenantPanelStatus(undefined, now);
    return {
      checkedAt: Math.floor(now / 1000),
      loggedIn: false,
      configured: false,
      credentialStatus: "unavailable",
    };
  }
}
