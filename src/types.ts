export interface Tenant {
  accountId: number; accountCode: string; accountName: string; companyName?: string; environment: string;
  purpose: string; context?: string; businessToken?: string; businessUrl?: string;
  slsUrl?: string; expiresAt: number;
}
export interface AuthSession {
  accessToken: string; refreshToken: string; accessExpiry: number;
  employeeId: string; email: string; channel: "stable" | "canary" | "dev";
}
export interface TenantProfile extends Tenant {
  profileId: string; displayName: string; createdAt: number; updatedAt: number;
}
export interface SessionContext {
  contextId: string; activeProfileId?: string; createdAt: number; updatedAt: number;
}
/** Request-local compatibility shape used by existing business handlers. */
export interface Session extends AuthSession {
  tenant?: Tenant;
  runtimeContext?: { contextId: string; profileId: string };
}
export interface DeviceStart { deviceCode: string; userCode: string; verificationUriComplete: string; expiresIn: number; interval: number }
export interface TokenResponse { accessToken: string; expiresIn: number; refreshToken: string; employee: { id: string; email: string } }
