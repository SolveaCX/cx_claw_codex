#!/usr/bin/env node
import { hasActiveAuthWait } from "../runtime/auth-wait-state.mjs";

let input = {};
try {
  input = JSON.parse(await new Promise((resolve, reject) => {
    let value = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => { value += chunk; });
    process.stdin.on("end", () => resolve(value || "{}"));
    process.stdin.on("error", reject);
  }));
} catch {
  process.stdout.write("{}\n");
  process.exit(0);
}

if (await hasActiveAuthWait(input.session_id)) {
  process.stdout.write(JSON.stringify({
    decision: "block",
    reason: "CXClaw 钉钉授权仍在进行。继续读取刚才启动的命令 session，直到该命令成功或明确失败；不要结束当前轮次，也不要要求用户回复已授权。",
  }) + "\n");
} else {
  process.stdout.write("{}\n");
}
