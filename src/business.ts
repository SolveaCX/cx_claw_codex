import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import { dirname, join, normalize, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Session } from "./types.js";
import { isNativeSolveaCommand, runSolveaCommand } from "./solvea/commands.js";

export const packageRoot=()=>resolve(dirname(fileURLToPath(import.meta.url)),"..");
export async function findPython(){for(const name of ["python3.12","python3"]){const ok=await new Promise<boolean>(r=>{const p=spawn(name,["-c","import sys;raise SystemExit(sys.version_info[:2]!=(3,12))"],{stdio:"ignore"});p.on("error",()=>r(false));p.on("exit",c=>r(c===0));});if(ok)return name;}throw new Error("Python 3.12 is required for CXClaw business scripts");}
export async function runPython(script:string,args:string[],session?:Session):Promise<number>{
  const root=packageRoot(), target=resolve(root,normalize(script.replace(/^[/\\]+/,"")));if(!relative(join(root,"skills"),target)||relative(join(root,"skills"),target).startsWith(".."))throw new Error("script path must be inside skills/");await access(target);
  const command=await findPython();const env={...process.env,PYTHONPATH:join(root,"skills","__lib__")};if(session?.tenant)Object.assign(env,{SOLVEA_ENV:session.tenant.environment,SOLVEA_BASE_URL:session.tenant.businessUrl,SOLVEA_PROD_URL:session.tenant.businessUrl,SOLVEA_TOKEN:session.tenant.businessToken,SOLVEA_PROD_TOKEN:session.tenant.businessToken});
  return await new Promise((done,reject)=>{const child=spawn(command,[target,...args],{stdio:"inherit",env});child.on("error",reject);child.on("exit",code=>done(code??1));});
}
export async function runApi(session:Session,command:string,args:string[]){
  if (isNativeSolveaCommand(command)) {
    console.log(JSON.stringify(await runSolveaCommand(session, command, args), null, 2));
    return;
  }
  const code=await runPython("skills/__lib__/solvea-api/solvea_api.py",[command,...args],session);if(code)throw new Error(`business command ${command} failed with exit code ${code}`)
}
