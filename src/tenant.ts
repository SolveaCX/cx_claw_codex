import { post } from "./http.js";
import { saveSession } from "./store.js";
import type { Session, Tenant } from "./types.js";

export function environment(value:string){const v=value.toLowerCase();if(v==="test"||v==="staging")return "staging";if(v==="prod"||v==="production")return "prod";throw new Error(`unsupported environment ${value}; use test/staging or prod`)}
export async function search(session:Session,query:string,env:string){return (await post<{items:unknown[]}>(session,"/tenants/search",{query,environment:environment(env)})).items}
export async function useTenant(session:Session,accountId:number,env:string,purpose:string){
  if(!purpose)throw new Error("purpose is required");
  const response=await post<any>(session,"/tenant-contexts",{accountId,environment:environment(env),purpose});
  if(!response.businessToken||!response.services?.businessUrl)throw new Error("authorization server did not return business credentials");
  session.tenant={...response.tenant,environment:response.environment,purpose,context:response.tenantContext,businessToken:response.businessToken,businessUrl:response.services.businessUrl.replace(/\/$/,""),slsUrl:response.services.slsUrl?.replace(/\/$/,""),expiresAt:response.businessTokenExpiresAt||Math.floor(Date.now()/1000)+response.expiresIn} as Tenant;
  await saveSession(session);return publicTenant(session.tenant);
}
export function publicTenant(t?:Tenant){return t?{accountId:t.accountId,accountCode:t.accountCode,accountName:t.accountName,environment:t.environment,purpose:t.purpose,expiresAt:t.expiresAt,configured:Boolean(t.businessToken&&t.businessUrl)}:{configured:false}}
export async function ensureTenant(session:Session){if(!session.tenant?.accountId)throw new Error("no tenant selected; run npx --yes @shulex/cxclawctl@latest tenant use");if(Date.now()/1000+30>=session.tenant.expiresAt)await useTenant(session,session.tenant.accountId,session.tenant.environment,session.tenant.purpose);return session.tenant}
