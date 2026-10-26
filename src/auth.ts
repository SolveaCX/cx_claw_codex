import open from "open";
import { HttpError, post } from "./http.js";
import { deleteSession, loadSession, saveSession, SessionNotFoundError } from "./store.js";
import type { DeviceStart, Session, TokenResponse } from "./types.js";
import { VERSION } from "./version.js";
import { withAuthWaitMarker } from "../runtime/auth-wait-state.mjs";

const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
let loginInFlight: Promise<Session> | undefined;

interface DeviceAuthorizationRuntime {
  start: (session: Session) => Promise<DeviceStart>;
  poll: (session: Session, deviceCode: string) => Promise<TokenResponse>;
  openBrowser: (url: string) => Promise<void>;
  save: (session: Session) => Promise<void>;
  sleep: (ms: number) => Promise<unknown>;
  now: () => number;
  log: (message: string) => void;
}

export function publicAuthStatus(session: Session) {
  return { ok: true, loggedIn: true, email: session.email, channel: session.channel, accessExpiresAt: session.accessExpiry };
}

export async function authorizeDevice(channel:Session["channel"], runtime:DeviceAuthorizationRuntime):Promise<Session>{
  const session:Session={channel,accessToken:"",refreshToken:"",accessExpiry:0,employeeId:"",email:""};
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
    runtime.log("钉钉授权成功，继续执行当前命令。");
    return session;
  } catch(error){
    if(!(error instanceof HttpError) || error.status!==428) throw error;
    if(runtime.now()>=nextProgressAt){runtime.log("仍在等待钉钉授权……");nextProgressAt=runtime.now()+15_000;}
  } }
  throw new Error("device authorization expired");
}

async function runLogin(channel:Session["channel"]):Promise<Session>{
  return withAuthWaitMarker(()=>authorizeDevice(channel,{
    start: session=>post<DeviceStart>(session,"/auth/device/start",{clientVersion:VERSION}),
    poll: (session,deviceCode)=>post<TokenResponse>(session,"/auth/device/token",{deviceCode,clientVersion:VERSION}),
    openBrowser: async url=>{await open(url);},
    save: saveSession,
    sleep,
    now: Date.now,
    log: message=>console.error(message),
  }));
}

export function login(channel:Session["channel"]):Promise<Session>{
  if (!loginInFlight) loginInFlight=runLogin(channel).finally(()=>{loginInFlight=undefined;});
  return loginInFlight;
}

export async function ensureAccess(session:Session):Promise<Session>{
  if(session.accessToken && Date.now()/1000+30<session.accessExpiry)return session;
  const token=await post<TokenResponse>(session,"/auth/refresh",{refreshToken:session.refreshToken,clientVersion:VERSION});
  Object.assign(session,{accessToken:token.accessToken,refreshToken:token.refreshToken,accessExpiry:Math.floor(Date.now()/1000)+token.expiresIn}); await saveSession(session); return session;
}

interface AuthenticationRuntime {
  load: () => Promise<Session>;
  refresh: (session: Session) => Promise<Session>;
  remove: () => Promise<void>;
  authorize: () => Promise<Session>;
}

export async function resolveAuthenticated(runtime: AuthenticationRuntime):Promise<Session>{
  try {
    return await runtime.refresh(await runtime.load());
  } catch(error) {
    if (error instanceof SessionNotFoundError) {
      console.error("CXClaw 尚未授权，正在自动发起钉钉授权。");
      return runtime.authorize();
    }
    if (error instanceof HttpError && error.status===401) {
      console.error("CXClaw 登录已失效，正在重新发起钉钉授权。");
      await runtime.remove().catch(()=>undefined);
      return runtime.authorize();
    }
    throw error;
  }
}

export function authenticated():Promise<Session>{
  return resolveAuthenticated({load:loadSession,refresh:ensureAccess,remove:deleteSession,authorize:()=>login("stable")});
}
export async function logout(){let session:Session|undefined;try{session=await loadSession()}catch{};if(session?.refreshToken)await post(session,"/auth/logout",{refreshToken:session.refreshToken}).catch(()=>undefined);await deleteSession()}
