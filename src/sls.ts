import LogClient from "@alicloud/log";
import { post } from "./http.js";
import { environment } from "./tenant.js";
import type { Session } from "./types.js";

interface SlsSession{endpoint:string;project:string;logstore:string;credentials:{accessKeyId:string;accessKeySecret:string};limits:{maxTimeRangeSeconds:number;maxResults:number;maxConcurrency:number;maxMessageChars:number}}
function requireSlsSession(value:unknown):SlsSession{
  const response=value as Partial<SlsSession>&{message?:unknown};
  if(!response||typeof response!=="object")throw new Error("SLS credential request returned invalid data");
  if(typeof response.message==="string"&&response.message.trim())throw new Error(`SLS credential request failed: ${response.message}`);
  if(typeof response.endpoint!=="string"||typeof response.project!=="string"||typeof response.logstore!=="string"
    ||typeof response.credentials?.accessKeyId!=="string"||typeof response.credentials?.accessKeySecret!=="string"
    ||typeof response.limits?.maxTimeRangeSeconds!=="number"||typeof response.limits?.maxResults!=="number"
    ||typeof response.limits?.maxMessageChars!=="number")throw new Error("SLS credential request returned incomplete data");
  return response as SlsSession;
}
export async function query(session:Session,options:{environment?:string;from:number;to:number;query:string;line:number;offset:number;reverse:boolean}){
  if(!options.environment)throw new Error("SLS environment is required; use --env test or --env prod");
  const configured=requireSlsSession(await post<unknown>(session,"/sls/session",{environment:environment(options.environment)}));if(options.from<=0||options.to<options.from||options.to-options.from>configured.limits.maxTimeRangeSeconds)throw new Error("SLS time range exceeds the server limit");
  const client=new (LogClient as any)({endpoint:configured.endpoint,use_https:true,accessKeyId:configured.credentials.accessKeyId,accessKeySecret:configured.credentials.accessKeySecret});
  const response=await client.getLogs(configured.project,configured.logstore,new Date(options.from*1000),new Date(options.to*1000),{query:options.query,line:Math.min(options.line||50,configured.limits.maxResults),offset:options.offset||0,reverse:options.reverse});
  const logs=(response.body??response).map?.((row:Record<string,unknown>)=>Object.fromEntries(Object.entries(row).map(([k,v])=>[k,String(v).slice(0,configured.limits.maxMessageChars||undefined)])))??response.body??response;
  return {logs};
}
