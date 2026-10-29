import open from "open";
import { HttpError, post } from "./http.js";
import { deleteAllSessions, deleteAuthSession, loadAuthSession, saveAuthSession, SessionNotFoundError } from "./store.js";
import type { AuthSession, DeviceStart, TokenResponse } from "./types.js";
import { VERSION } from "./version.js";
import { notAuthenticated } from "./cli-error.js";

const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));

interface DeviceAuthorizationRuntime {
  start: (session: AuthSession) => Promise<DeviceStart>;
  poll: (session: AuthSession, deviceCode: string) => Promise<TokenResponse>;
  openBrowser: (url: string) => Promise<void>;
  save: (session: AuthSession) => Promise<void>;
  sleep: (ms: number) => Promise<unknown>;
  now: () => number;
  log: (message: string) => void;
}

export function publicAuthStatus(session: AuthSession) {
  return { ok: true, loggedIn: true, email: session.email, channel: session.channel, accessExpiresAt: session.accessExpiry };
}

export function isAuthorizationPending(error: unknown): boolean {
  return error instanceof HttpError && (error.status === 428 || error.responseCode === 428);
}

export async function authorizeDevice(channel:AuthSession["channel"], runtime:DeviceAuthorizationRuntime):Promise<AuthSession>{
  const session:AuthSession={channel,accessToken:"",refreshToken:"",accessExpiry:0,employeeId:"",email:""};
  const start=await runtime.start(session);
  try {
    await runtime.openBrowser(start.verificationUriComplete);
    runtime.log("钉钉授权页已打开，当前命令会持续等待授权结果，无需回复 Codex。");
  } catch {
    runtime.log(`未能自动打开浏览器，请打开以下地址完成钉钉授权：\n${start.verificationUriComplete}\n设备码：${start.userCode}`);
  }
  const deadline=runtime.now()+start.expiresIn*1000;
  let nextProgressAt=runtime.now()+15_000;
  while(runtime.now()<deadline){ await runtime.sleep(Math.max(2,start.interval)*1000); try {
    const token=await runtime.poll(session,start.deviceCode);
    Object.assign(session,{accessToken:token.accessToken,refreshToken:token.refreshToken,accessExpiry:Math.floor(runtime.now()/1000)+token.expiresIn,employeeId:token.employee.id,email:token.employee.email});
    await runtime.save(session);
    runtime.log("钉钉授权成功。");
    return session;
  } catch(error){
    if(!isAuthorizationPending(error)) throw error;
    if(runtime.now()>=nextProgressAt){runtime.log("仍在等待钉钉授权……");nextProgressAt=runtime.now()+15_000;}
  } }
  throw new Error("device authorization expired");
}

async function runLogin(channel:AuthSession["channel"]):Promise<AuthSession>{
  return authorizeDevice(channel,{
    start: session=>post<DeviceStart>(session,"/auth/device/start",{clientVersion:VERSION}),
    poll: (session,deviceCode)=>post<TokenResponse>(session,"/auth/device/token",{deviceCode,clientVersion:VERSION}),
    openBrowser: async url=>{await open(url);},
    save: saveAuthSession,
    sleep,
    now: Date.now,
    log: message=>console.error(message),
  });
}

export function login(channel:AuthSession["channel"]):Promise<AuthSession>{
  return runLogin(channel);
}

export async function ensureAccess(session:AuthSession):Promise<AuthSession>{
  if(session.accessToken && Date.now()/1000+30<session.accessExpiry)return session;
  const token=await post<TokenResponse>(session,"/auth/refresh",{refreshToken:session.refreshToken,clientVersion:VERSION});
  Object.assign(session,{accessToken:token.accessToken,refreshToken:token.refreshToken,accessExpiry:Math.floor(Date.now()/1000)+token.expiresIn}); await saveAuthSession(session); return session;
}

interface AuthenticationRuntime {
  load: () => Promise<AuthSession>;
  refresh: (session: AuthSession) => Promise<AuthSession>;
  remove: () => Promise<void>;
}

export async function resolveAuthenticated(runtime: AuthenticationRuntime):Promise<AuthSession>{
  try {
    return await runtime.refresh(await runtime.load());
  } catch(error) {
    if (error instanceof SessionNotFoundError) {
      throw notAuthenticated();
    }
    if (error instanceof HttpError && error.status===401) {
      await runtime.remove().catch(()=>undefined);
      throw notAuthenticated("CXClaw 登录已失效");
    }
    throw error;
  }
}

export function authenticated():Promise<AuthSession>{
  return resolveAuthenticated({load:loadAuthSession,refresh:ensureAccess,remove:deleteAuthSession});
}
export async function logout(){let session:AuthSession|undefined;try{session=await loadAuthSession()}catch{};if(session?.refreshToken)await post(session,"/auth/logout",{refreshToken:session.refreshToken}).catch(()=>undefined);await deleteAllSessions()}
