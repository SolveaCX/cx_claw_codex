#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
const root=join(import.meta.dirname,"..");const output=join(root,"dist","cxclaw-codex-plugin.zip");const paths=[".codex-plugin","plugin-cli.mjs","skills"];
for(const path of paths)execFileSync("git",["cat-file","-e",`HEAD:${path}`],{cwd:root});mkdirSync(join(root,"dist"),{recursive:true});execFileSync("git",["archive","--format=zip","--prefix=cxclaw/","--output",output,"HEAD","--",...paths],{cwd:root});
if(statSync(output).size>100_000_000)throw new Error("Codex plugin archive exceeds 100 MB");console.log(output);
