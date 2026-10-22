import LogClient from "@alicloud/log";
import { post } from "./http.js";
import type { Session } from "./types.js";

interface SlsSession{endpoint:string;project:string;logstore:string;credentials:{accessKeyId:string;accessKeySecret:string;securityToken:string};limits:{maxTimeRangeSeconds:number;maxResults:number;maxConcurrency:number;maxMessageChars:number}}
export async function query(session:Session,options:{from:number;to:number;query:string;line:number;offset:number;reverse:boolean}){
  const temporary=await post<SlsSession>(session,"/sls/session",{},true);if(options.from<=0||options.to<options.from||options.to-options.from>temporary.limits.maxTimeRangeSeconds)throw new Error("SLS time range exceeds the server limit");
  const client=new (LogClient as any)({endpoint:temporary.endpoint,use_https:true,accessKeyId:temporary.credentials.accessKeyId,accessKeySecret:temporary.credentials.accessKeySecret,securityToken:temporary.credentials.securityToken});
  const response=await client.getLogs(temporary.project,temporary.logstore,new Date(options.from*1000),new Date(options.to*1000),{query:options.query,line:Math.min(options.line||50,temporary.limits.maxResults),offset:options.offset||0,reverse:options.reverse});
  const logs=(response.body??response).map?.((row:Record<string,unknown>)=>Object.fromEntries(Object.entries(row).map(([k,v])=>[k,String(v).slice(0,temporary.limits.maxMessageChars||undefined)])))??response.body??response;
  return {logs};
}
