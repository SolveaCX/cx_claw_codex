export interface Tenant {
  accountId: number; accountCode: string; accountName: string; companyName?: string; environment: string;
  purpose: string; context?: string; businessToken?: string; businessUrl?: string;
  slsUrl?: string; expiresAt: number;
}
export interface Session {
  accessToken: string; refreshToken: string; accessExpiry: number;
  employeeId: string; email: string; channel: "stable" | "canary" | "dev"; tenant?: Tenant;
}
export interface DeviceStart { deviceCode: string; userCode: string; verificationUriComplete: string; expiresIn: number; interval: number }
export interface TokenResponse { accessToken: string; expiresIn: number; refreshToken: string; employee: { id: string; email: string } }
