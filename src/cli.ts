import { readFile } from "node:fs/promises";
import { authenticated, login, logout } from "./auth.js";
import { flag, option, positionals } from "./args.js";
import { packageRoot, runApi, runPython } from "./business.js";
import { loadSession, saveSession } from "./store.js";
import { query as slsQuery } from "./sls.js";
import { publicTenant, search, useTenant } from "./tenant.js";
import { installMarketplace, installScheduler, update } from "./update.js";
import { SERVER_API_VERSION, TOOL_SCHEMA_VERSION, VERSION } from "./version.js";

const print=(value:unknown)=>console.log(JSON.stringify(value,null,2));
async function main(args=process.argv.slice(2)){
  const [command,sub,...rest]=args;if(!command){console.log("cxclaw auth|tenant|api|sls|script|doctor|update|setup|version");return;}
  if(command==="version")return print({pluginVersion:VERSION,cliVersion:VERSION,toolSchemaVersion:TOOL_SCHEMA_VERSION,serverApiVersion:SERVER_API_VERSION});
  if(command==="setup"){const server=option(args,"--server",true)!;const channel=(option(args,"--channel")??"stable") as any;await installMarketplace(channel);await login(server,channel);await installScheduler();return;}
  if(command==="auth"||command==="login"||command==="logout"){
    const action=command==="auth"?sub:command;if(action==="login"){const channel=(option(rest,"--channel")??"stable") as any;return print(await login(option(rest,"--server",true)!,channel));}if(action==="logout"){await logout();return print({ok:true,loggedOut:true});}if(action==="status"){try{const s=await loadSession();return print({ok:true,loggedIn:true,email:s.email,channel:s.channel,accessExpiresAt:s.accessExpiry});}catch{return print({ok:true,loggedIn:false});}}if(action==="refresh"){const s=await authenticated();return print({ok:true,accessExpiresAt:s.accessExpiry});}}
  if(command==="tenant"||command==="context"){const session=await authenticated();if(sub==="current")return print(publicTenant(session.tenant));if(sub==="clear"){delete session.tenant;await saveSession(session);return print({ok:true,cleared:true});}if(sub==="search")return print(await search(session,positionals(rest)[0]??"",option(rest,"--env",true)!));if(sub==="use")return print(await useTenant(session,Number(positionals(rest)[0]),option(rest,"--env",true)!,option(rest,"--purpose",true)!));}
  if(command==="api"){const session=await authenticated();if(!sub)throw new Error("api command is required");await runApi(session,sub,rest);return;}
  if(command==="script"){if(!sub)throw new Error("script path is required");process.exitCode=await runPython(sub,rest);return;}
  if(command==="sls"&&sub==="query"){const session=await authenticated();return print(await slsQuery(session,{from:Number(option(rest,"--from",true)),to:Number(option(rest,"--to",true)),query:option(rest,"--query",true)!,line:Number(option(rest,"--line")??50),offset:Number(option(rest,"--offset")??0),reverse:flag(rest,"--reverse")}));}
  if(command==="doctor"){const manifest=JSON.parse(await readFile(new URL("../plugin.json",import.meta.url),"utf8"));if(manifest.version!==VERSION)throw new Error(`plugin version ${manifest.version} does not match CLI ${VERSION}`);return print({ok:true,node:process.versions.node,cliVersion:VERSION,root:packageRoot()});}
  if(command==="update"){if(flag(args,"--install-scheduler")){await installScheduler();return;}if(flag(args,"--scheduled"))await new Promise(r=>setTimeout(r,Math.random()*1_800_000));return print({version:await update()});}
  if(command==="commands"||command==="capabilities")return console.log(await readFile(new URL("../capabilities.lock.json",import.meta.url),"utf8"));
  throw new Error(`unknown command: ${command}`);
}
main().catch(error=>{console.error(`cxclaw: ${error instanceof Error?error.message:String(error)}`);process.exitCode=1});
