#!/usr/bin/env node

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

const command = String(input.tool_input?.command ?? "");
const response = JSON.stringify(input.tool_response ?? "").replaceAll("\\", "");
const checkedCxclawStatus = command.includes("plugin-cli.mjs") && /\bauth\s+status\b/.test(command);
const isLoggedOut = /"loggedIn"\s*:\s*false/.test(response);

if (checkedCxclawStatus && isLoggedOut) {
  process.stdout.write(JSON.stringify({
    decision: "block",
    reason: "CXClaw 尚未登录。立即执行同一插件的 `auth ensure`，或直接执行原计划中的租户/业务命令；等待 CLI 完成授权，不要结束当前轮次。",
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: "CXClaw 登录状态检查发现未登录；继续执行 CLI 并等待钉钉授权完成。",
    },
  }) + "\n");
} else {
  process.stdout.write("{}\n");
}
