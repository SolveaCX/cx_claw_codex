import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { homedir, platform } from "node:os";
import { join } from "node:path";
import { compareVersions } from "compare-versions";
import { VERSION } from "./version.js";

const exec=(command:string,args:string[])=>new Promise<void>((done,reject)=>{const p=spawn(command,args,{stdio:"inherit"});p.on("error",reject);p.on("exit",c=>c===0?done():reject(new Error(`${command} exited with ${c}`)));});
export async function update(){const info=await fetch("https://registry.npmjs.org/cxclaw/latest",{signal:AbortSignal.timeout(30_000)}).then(r=>{if(!r.ok)throw new Error(`npm registry returned ${r.status}`);return r.json() as Promise<{version:string}>});if(compareVersions(info.version,VERSION)>0)console.log(`发现新版本 ${info.version}；npx 下次运行会自动使用最新版。`);await exec("codex",["plugin","marketplace","upgrade","cxclaw"]);return info.version;}
export async function installScheduler(){const command=process.platform==="win32"?"npx.cmd":"npx";const args=["--yes","cxclaw@latest","update","--scheduled"];
  if(platform()==="darwin"){const dir=join(homedir(),"Library/LaunchAgents");await mkdir(dir,{recursive:true});await writeFile(join(dir,"com.solvea.cxclaw.update.plist"),`<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key><string>com.solvea.cxclaw.update</string><key>ProgramArguments</key><array><string>${command}</string>${args.map(x=>`<string>${x}</string>`).join("")}</array><key>StartInterval</key><integer>21600</integer><key>RunAtLoad</key><true/></dict></plist>`);await exec("launchctl",["load",join(dir,"com.solvea.cxclaw.update.plist")]);}
  else if(platform()==="linux"){const dir=join(homedir(),".config/systemd/user");await mkdir(dir,{recursive:true});await writeFile(join(dir,"cxclaw-update.service"),`[Service]\nType=oneshot\nExecStart=${command} ${args.join(" ")}\n`);await writeFile(join(dir,"cxclaw-update.timer"),"[Timer]\nOnBootSec=5m\nOnUnitActiveSec=6h\nRandomizedDelaySec=30m\nPersistent=true\n[Install]\nWantedBy=timers.target\n");await exec("systemctl",["--user","daemon-reload"]);await exec("systemctl",["--user","enable","--now","cxclaw-update.timer"]);}
  else await exec("schtasks",["/Create","/F","/SC","HOURLY","/MO","6","/TN","Solvea CXClaw Update","/TR",`${command} ${args.join(" ")}`]);}
export async function installMarketplace(channel:string){if(!["stable","canary","dev"].includes(channel))throw new Error("invalid channel");await exec("codex",["plugin","marketplace","add","SolveaCX/cx_claw_codex","--ref",`marketplace/${channel}`]).catch(()=>exec("codex",["plugin","marketplace","upgrade","cxclaw"]));await exec("codex",["plugin","add","cxclaw@cxclaw"]).catch(()=>undefined)}
