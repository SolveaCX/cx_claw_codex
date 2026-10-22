import type { Session } from "./types.js";
import { VERSION } from "./version.js";

export function unwrap<T>(value: unknown): T {
  if (value && typeof value === "object" && Object.keys(value).length === 1 && "data" in value) return (value as {data:T}).data;
  return value as T;
}
export async function request<T>(session: Session, path: string, init: RequestInit = {}, tenant = false): Promise<T> {
  const headers = new Headers(init.headers); headers.set("content-type", "application/json"); headers.set("x-cxclaw-client-version", VERSION);
  if (session.accessToken) headers.set("authorization", `Bearer ${session.accessToken}`);
  if (tenant) { if (!session.tenant?.context) throw new Error("no tenant selected; run npx cxclaw tenant use"); headers.set("x-cxclaw-tenant-context", session.tenant.context); }
  let last: unknown;
  for (let attempt=0; attempt<3; attempt++) {
    try {
      const response = await fetch(`${session.serverUrl.replace(/\/$/,"")}${path}`, {...init, headers, signal: AbortSignal.timeout(30_000)});
      const text = await response.text(); const value = text ? JSON.parse(text) : undefined;
      if (!response.ok) throw new Error(`server returned ${response.status}: ${text}`);
      return unwrap<T>(value);
    } catch (error) { last=error; if (attempt<2) await new Promise(r=>setTimeout(r,200*2**attempt)); }
  }
  throw last;
}
export const post = <T>(session:Session,path:string,body:unknown,tenant=false) => request<T>(session,path,{method:"POST",body:JSON.stringify(body)},tenant);
