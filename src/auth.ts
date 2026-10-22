import open from "open";
import { post } from "./http.js";
import { deleteSession, loadSession, saveSession } from "./store.js";
import type { DeviceStart, Session, TokenResponse } from "./types.js";
import { VERSION } from "./version.js";

const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
export async function login(serverUrl:string, channel:Session["channel"]):Promise<Session>{
  const session:Session={serverUrl:serverUrl.replace(/\/$/,""),channel,accessToken:"",refreshToken:"",accessExpiry:0,employeeId:"",email:""};
  const start=await post<DeviceStart>(session,"/auth/device/start",{clientVersion:VERSION});
  console.error(`请在浏览器打开以下地址完成钉钉授权：\n${start.verificationUriComplete}\n设备码：${start.userCode}`);
  await open(start.verificationUriComplete).catch(()=>undefined);
  const deadline=Date.now()+start.expiresIn*1000;
  while(Date.now()<deadline){ await sleep(Math.max(2,start.interval)*1000); try {
    const token=await post<TokenResponse>(session,"/auth/device/token",{deviceCode:start.deviceCode,clientVersion:VERSION});
    Object.assign(session,{accessToken:token.accessToken,refreshToken:token.refreshToken,accessExpiry:Math.floor(Date.now()/1000)+token.expiresIn,employeeId:token.employee.id,email:token.employee.email}); await saveSession(session); return session;
  } catch(error){ if(!String(error).includes("428")) throw error; } }
  throw new Error("device authorization expired");
}
export async function ensureAccess(session:Session):Promise<Session>{
  if(session.accessToken && Date.now()/1000+30<session.accessExpiry)return session;
  const token=await post<TokenResponse>(session,"/auth/refresh",{refreshToken:session.refreshToken,clientVersion:VERSION});
  Object.assign(session,{accessToken:token.accessToken,refreshToken:token.refreshToken,accessExpiry:Math.floor(Date.now()/1000)+token.expiresIn}); await saveSession(session); return session;
}
export async function authenticated(){return ensureAccess(await loadSession())}
export async function logout(){let session:Session|undefined;try{session=await loadSession()}catch{};if(session?.refreshToken)await post(session,"/auth/logout",{refreshToken:session.refreshToken}).catch(()=>undefined);await deleteSession()}
