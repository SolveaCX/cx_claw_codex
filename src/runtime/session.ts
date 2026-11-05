import { authenticated } from "../auth.js";
import { resolveTenantSession } from "../tenant.js";
import type { Session } from "../types.js";

export async function resolveRuntimeSession(
  contextId: string,
  options: { forceProfileRefresh?: boolean; minValiditySeconds?: number } = {},
): Promise<Session> {
  if (!contextId.trim()) throw new Error("contextId is required");
  return resolveTenantSession(await authenticated(), {
    contextId,
    allowLegacy: false,
    ...options,
  });
}
