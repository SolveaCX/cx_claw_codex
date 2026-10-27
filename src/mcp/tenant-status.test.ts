import { describe, expect, test } from "bun:test";
import { loadTenantPanelStatus, tenantPanelStatus } from "./tenant-status.js";
import type { Session } from "../types.js";

const session = (expiresAt: number): Session => ({
  accessToken: "access-secret",
  refreshToken: "refresh-secret",
  accessExpiry: expiresAt,
  employeeId: "employee-1",
  email: "employee@example.com",
  channel: "stable",
  tenant: {
    accountId: 5,
    accountCode: "V75400",
    accountName: "Test Tenant",
    companyName: "Test Company",
    environment: "staging",
    purpose: "badcase 排查",
    context: "tenant-context-secret",
    businessToken: "business-secret",
    businessUrl: "https://business.example.com",
    expiresAt,
  },
});

describe("tenant panel status", () => {
  test("returns only public fields for the selected tenant", () => {
    const status = tenantPanelStatus(session(2_000), 1_000_000);
    expect(status).toEqual({
      checkedAt: 1_000,
      loggedIn: true,
      configured: true,
      credentialStatus: "active",
      accountId: 5,
      accountCode: "V75400",
      accountName: "Test Tenant",
      companyName: "Test Company",
      environment: "staging",
      purpose: "badcase 排查",
      expiresAt: 2_000,
    });
    expect(JSON.stringify(status)).not.toContain("secret");
    expect(JSON.stringify(status)).not.toContain("business.example.com");
  });

  test("marks expired tenant credentials", () => {
    expect(tenantPanelStatus(session(999), 1_000_000).credentialStatus).toBe("expired");
  });

  test("distinguishes login without a tenant from no login", () => {
    expect(tenantPanelStatus({ ...session(2_000), tenant: undefined }, 1_000_000).credentialStatus).toBe("not_selected");
    expect(tenantPanelStatus(undefined, 1_000_000).credentialStatus).toBe("not_logged_in");
  });

  test("does not expose credential-store failures", async () => {
    const status = await loadTenantPanelStatus(async () => { throw new Error("keychain details"); }, 1_000_000);
    expect(status.credentialStatus).toBe("unavailable");
    expect(JSON.stringify(status)).not.toContain("keychain details");
  });
});
