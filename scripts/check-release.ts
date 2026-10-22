import { readFileSync } from "node:fs";
const read=(path:string)=>JSON.parse(readFileSync(path,"utf8"));
const versions=[read("package.json").version,read("plugin.json").version,read(".codex-plugin/plugin.json").version];
if(new Set(versions).size!==1)throw new Error(`release versions differ: ${versions.join(", ")}`);
if(!/^\d+\.\d+\.\d+(?:-(?:canary|dev)\.\d+)?$/.test(versions[0]))throw new Error(`invalid version ${versions[0]}`);
console.log(versions[0]);
