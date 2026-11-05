import { useEffect, useState } from "react";
import { callTool, useBridgeState } from "../shared/bridge.js";

type Status = Record<string, unknown>;
const value = (status: Status | undefined, key: string) => String(status?.[key] ?? "—");

export function TenantStatusApp() {
  const bridge = useBridgeState();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<Status>();
  useEffect(() => {
    if (bridge.output) setStatus(bridge.output);
  }, [bridge.output]);
  const contextId = String(bridge.input.contextId ?? status?.contextId ?? "");
  const refresh = async () => {
    setLoading(true);
    setError(undefined);
    try {
      if (!contextId) throw new Error("当前卡片缺少 contextId，请在登录并选择租户后重新打开");
      const output = await callTool("tenant.current", { contextId });
      if (output) setStatus(output);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  };
  return (
    <main className="bg-app-background text-app-foreground font-app-sans p-4 pt-8">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-app-muted mb-1 text-xs font-semibold tracking-wide uppercase">
            CXClaw · 当前会话租户
          </p>
          <h1 className="text-lg font-semibold">
            {status?.configured
              ? String(
                  status.companyName ??
                    status.accountName ??
                    status.accountCode ??
                    status.accountId ??
                    "—",
                )
              : "尚未选择租户"}
          </h1>
        </div>
        <button
          className="border-app-border bg-app-surface rounded-lg border px-3 py-2 text-sm disabled:opacity-50"
          disabled={loading || !bridge.connected || !contextId}
          onClick={refresh}
          type="button"
        >
          {loading ? "刷新中…" : "刷新"}
        </button>
      </header>
      {(error || bridge.error || !contextId) && (
        <p className="text-app-danger mt-3 text-sm">
          {error ??
            bridge.error ??
            "当前卡片未绑定 contextId，请在登录并选择租户后重新打开租户卡片"}
        </p>
      )}
      <dl className="border-app-border mt-5 grid grid-cols-[auto_1fr] border-t text-sm">
        {[
          ["环境", "environment"],
          ["Context", "contextId"],
          ["Profile", "profileId"],
          ["Account ID", "accountId"],
          ["Account Code", "accountCode"],
          ["公司名", "companyName"],
          ["用途", "purpose"],
          ["凭据到期", "expiresAt"],
        ].map(([label, key]) => (
          <div className="contents" key={key}>
            <dt className="text-app-muted border-app-border border-b py-3">{label}</dt>
            <dd className="border-app-border min-w-0 overflow-wrap-anywhere border-b py-3 text-right font-medium">
              {value(status, key)}
            </dd>
          </div>
        ))}
      </dl>
    </main>
  );
}
