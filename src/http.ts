import type { Session } from "./types.js";
import { AUTH_SERVER_URL } from "./config.js";
import { VERSION } from "./version.js";

export class HttpError extends Error {
  constructor(public readonly status: number, public readonly responseBody: string) {
    super(`server returned ${status}: ${responseBody}`);
    this.name = "HttpError";
  }
}

export function unwrap<T>(value: unknown): T {
  if (value && typeof value === "object" && Object.keys(value).length === 1 && "data" in value) return (value as {data:T}).data;
  return value as T;
}
export async function request<T>(session: Session, path: string, init: RequestInit = {}, tenant = false): Promise<T> {
  const headers = new Headers(init.headers); headers.set("content-type", "application/json"); headers.set("x-cxclaw-client-version", VERSION);
  if (session.accessToken) headers.set("authorization", `Bearer ${session.accessToken}`);
  if (tenant) { if (!session.tenant?.context) throw new Error("no tenant selected; run npx --yes @shulex/cxclawctl@latest tenant use"); headers.set("x-cxclaw-tenant-context", session.tenant.context); }
  let last: unknown;
  for (let attempt=0; attempt<3; attempt++) {
    try {
      const response = await fetch(`${AUTH_SERVER_URL}${path}`, {...init, headers, signal: AbortSignal.timeout(30_000)});
      const text = await response.text(); const value = text ? JSON.parse(text) : undefined;
      if (!response.ok) throw new HttpError(response.status, text);
      return unwrap<T>(value);
    } catch (error) {
      last=error;
      // 4xx 是确定的业务结果（例如设备授权仍在等待），重复请求没有意义。
      if (error instanceof HttpError && error.status < 500) break;
      if (attempt<2) await new Promise(r=>setTimeout(r,200*2**attempt));
    }
  }
  throw last;
}
export const post = <T>(session:Session,path:string,body:unknown,tenant=false) => request<T>(session,path,{method:"POST",body:JSON.stringify(body)},tenant);
