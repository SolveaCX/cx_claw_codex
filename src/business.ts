import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Session } from "./types.js";
import { isNativeSolveaCommand, runSolveaCommand } from "./solvea/commands.js";

export const packageRoot=()=>resolve(dirname(fileURLToPath(import.meta.url)),"..");
export async function runApi(session:Session,command:string,args:string[]){
  if (isNativeSolveaCommand(command)) {
    console.log(JSON.stringify(await runSolveaCommand(session, command, args), null, 2));
    return;
  }
  throw new Error(`unknown TypeScript API command: ${command}`);
}
