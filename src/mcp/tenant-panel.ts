import {
  App,
  applyDocumentTheme,
  applyHostStyleVariables,
} from "@modelcontextprotocol/ext-apps";

type TenantStatus = {
  checkedAt: number;
  loggedIn: boolean;
  configured: boolean;
  credentialStatus: "active" | "expired" | "not_selected" | "not_logged_in" | "unavailable";
  accountId?: number;
  accountCode?: string;
  accountName?: string;
  companyName?: string;
  environment?: string;
  purpose?: string;
  expiresAt?: number;
};

const app = new App({ name: "CXClaw Tenant", version: "1.0.0" });
const refreshButton = document.querySelector<HTMLButtonElement>("#refresh");
document.body.style.paddingTop = "32px";

function text(id: string, value: string): void {
  const element = document.querySelector<HTMLElement>(`#${id}`);
  if (element) element.textContent = value;
}

function formatTime(value?: number): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(value * 1_000) : "—";
}

function render(value: unknown): void {
  if (!value || typeof value !== "object") return renderError("暂时无法读取租户状态");
  const status = value as TenantStatus;
  const environment = status.environment?.toLowerCase();
  const badge = document.querySelector<HTMLElement>("#environment");
  document.body.dataset.state = status.credentialStatus;
  if (badge) badge.dataset.environment = environment ?? "none";

  if (status.credentialStatus === "not_logged_in") {
    text("headline", "尚未登录 CXClaw");
    text("summary", "完成登录并选择租户后，这里会自动显示当前租户。");
  } else if (status.credentialStatus === "not_selected") {
    text("headline", "尚未选择租户");
    text("summary", "运行 tenant use 后，这里会自动刷新。");
  } else if (status.credentialStatus === "unavailable") {
    text("headline", "无法读取租户状态");
    text("summary", "请检查系统凭据库和 CXClaw 登录状态。");
  } else {
    text("headline", status.companyName || status.accountName || `租户 ${status.accountId ?? "—"}`);
    text("summary", status.credentialStatus === "expired" ? "租户凭据已过期，下次业务操作会尝试刷新。" : "当前业务命令将访问这个租户。");
  }

  text("environment", environment === "prod" ? "PRODUCTION" : environment === "staging" ? "STAGING" : "未选择");
  text("account-id", status.accountId == null ? "—" : String(status.accountId));
  text("account-code", status.accountCode || "—");
  text("company-name", status.companyName || "—");
  text("purpose", status.purpose || "—");
  text("expires-at", formatTime(status.expiresAt));
  text("checked-at", `更新于 ${formatTime(status.checkedAt)}`);
}

function renderError(message: string): void {
  document.body.dataset.state = "unavailable";
  text("headline", message);
  text("summary", "稍后重试，或检查 CXClaw MCP server 是否正常运行。");
}

async function refresh(): Promise<void> {
  if (refreshButton) refreshButton.disabled = true;
  try {
    const result = await app.callServerTool({ name: "tenant.current", arguments: {} });
    if (result.isError) renderError("刷新租户状态失败");
    else render(result.structuredContent);
  } catch {
    renderError("刷新租户状态失败");
  } finally {
    if (refreshButton) refreshButton.disabled = false;
  }
}

function applyHostContext(): void {
  const context = app.getHostContext();
  if (context?.theme) applyDocumentTheme(context.theme);
  if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
}

app.ontoolresult = result => render(result.structuredContent);
app.addEventListener("hostcontextchanged", applyHostContext);
refreshButton?.addEventListener("click", () => void refresh());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void refresh();
});
window.addEventListener("focus", () => void refresh());

async function start(): Promise<void> {
  await app.connect();
  applyHostContext();
  window.setInterval(() => {
    if (document.visibilityState === "visible") void refresh();
  }, 10_000);
}

void start().catch(() => renderError("租户面板启动失败"));
