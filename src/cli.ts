import { readFile } from "node:fs/promises";
import { authenticated, login, logout, publicAuthStatus } from "./auth.js";
import { flag, option, positionals } from "./args.js";
import { runApi } from "./business.js";
import { isResourceCommand, resourceHelp, runResourceCommand } from "./commands/resources.js";
import { diagnose } from "./doctor.js";
import { query as slsQuery } from "./sls.js";
import { loadSession, saveSession } from "./store.js";
import { publicTenant, search, useTenant } from "./tenant.js";
import { installMarketplace, installScheduler, update } from "./update.js";
import { SERVER_API_VERSION, TOOL_SCHEMA_VERSION, VERSION } from "./version.js";
import { runRuntime } from "./workflows/runtime.js";
import { runSolveaKitWorkflow } from "./workflows/solvea-kit.js";
import { runSupport } from "./workflows/support.js";
import { runAgentBuilder } from "./workflows/agent-builder.js";
import { runAgentTester } from "./workflows/tester.js";
import { runDelivery, runPoc } from "./workflows/delivery.js";
import { runKbBuilder } from "./workflows/kb-builder.js";
import { runDesk } from "./workflows/desk.js";

const print = (value: unknown) => console.log(JSON.stringify(value, null, 2));
const usage = () => [
  "cxclawctl <resource> <action> [options]",
  "cxclawctl auth|tenant|sls|runtime|doctor|update|setup|version",
  "cxclawctl agent-builder|agent-tester|delivery|poc|kb-builder|solvea-desk <action>",
  resourceHelp(),
  "Example: cxclawctl intent create --data-file intent.json",
].join("\n\n");

async function runAuth(action: string | undefined, args: string[]) {
  if (action === "login") {
    if (flag(args, "--server") || flag(args, "--env")) throw new Error("auth login 固定使用生产授权服务，不支持 --server 或 --env");
    const session = await login((option(args, "--channel") ?? "stable") as "stable" | "canary" | "dev");
    return print(publicAuthStatus(session));
  }
  if (action === "ensure") return print(publicAuthStatus(await authenticated()));
  if (action === "logout") { await logout(); return print({ ok: true, loggedOut: true }); }
  if (action === "status") {
    try {
      const session = await loadSession();
      return print(publicAuthStatus(session));
    } catch { return print({ ok: true, loggedIn: false }); }
  }
  if (action === "refresh") { return print(publicAuthStatus(await authenticated())); }
  throw new Error("auth action must be login, ensure, logout, status, or refresh");
}

async function runTenant(action: string | undefined, args: string[]) {
  const session = await authenticated();
  if (action === "current") return print(publicTenant(session.tenant));
  if (action === "clear") { delete session.tenant; await saveSession(session); return print({ ok: true, cleared: true }); }
  if (action === "search") return print(await search(session, positionals(args)[0] ?? "", option(args, "--env", true)!));
  if (action === "use") return print(await useTenant(session, Number(positionals(args)[0]), option(args, "--env", true)!, option(args, "--purpose", true)!));
  throw new Error("tenant action must be search, use, current, or clear");
}

async function main(args = process.argv.slice(2)) {
  const [command, action, ...rest] = args;
  if (!command || command === "help" || flag(args, "--help")) {
    console.log(command && isResourceCommand(command) ? resourceHelp(command, action && !["help", "--help"].includes(action) ? action : undefined) : usage());
    return;
  }
  if (isResourceCommand(command)) {
    await runResourceCommand(await authenticated(), command, action, rest);
    return;
  }
  if (command === "version") {
    if (flag(args, "--json")) return print({ pluginVersion: process.env.CXCLAW_PLUGIN_VERSION ?? null, cliVersion: VERSION, toolSchemaVersion: TOOL_SCHEMA_VERSION, serverApiVersion: SERVER_API_VERSION });
    console.log(`cxclawctl ${VERSION}`); return;
  }
  if (command === "setup") {
    if (flag(args, "--server") || flag(args, "--env")) throw new Error("setup 固定使用生产授权服务，不支持 --server 或 --env");
    const channel = (option(args, "--channel") ?? "stable") as "stable" | "canary" | "dev";
    await installMarketplace(channel); await login(channel); await installScheduler(); return;
  }
  if (command === "auth") return runAuth(action, rest);
  if (command === "login" || command === "logout") return runAuth(command, args.slice(1));
  if (command === "tenant" || command === "context") return runTenant(action, rest);
  if (command === "runtime") return print(await runRuntime(action, rest));
  if (command === "workflow") return print(await runSolveaKitWorkflow(action, rest));
  if (command === "support") return print(await runSupport(await authenticated(), action, rest));
  if (command === "agent-builder") return print(await runAgentBuilder(["validate", "compile", "merge-source", "validate-tool", "migration", "replay"].includes(action ?? "") ? undefined : await authenticated(), action, rest));
  if (command === "agent-tester") return print(await runAgentTester(action === "create-sheet" ? undefined : await authenticated(), action, rest));
  if (command === "delivery") return print(await runDelivery(["classify", "plan", "report", "render", "render-report", "excel", "gen-excel", "render-summary"].includes(action ?? "") ? undefined : await authenticated(), action, rest));
  if (command === "poc") return print(await runPoc(["classify", "plan", "report", "render", "render-report", "excel", "gen-excel", "manual", "render-summary"].includes(action ?? "") ? undefined : await authenticated(), action, rest));
  if (command === "kb-builder") return print(await runKbBuilder(["crawl", "directory-plan", "extract-web-qa", "extract-ticket-qa", "batch-extract-ticket-qa"].includes(action ?? "") ? undefined : await authenticated(), action, rest));
  if (command === "solvea-desk") return print(await runDesk(await authenticated(), action, rest));
  if (command === "api") { if (!action) throw new Error("api command is required"); await runApi(await authenticated(), action, rest); return; }
  if (command === "sls" && action === "query") {
    return print(await slsQuery(await authenticated(), {
      from: Number(option(rest, "--from", true)), to: Number(option(rest, "--to", true)),
      query: option(rest, "--query", true)!, line: Number(option(rest, "--line") ?? 50),
      offset: Number(option(rest, "--offset") ?? 0), reverse: flag(rest, "--reverse"),
    }));
  }
  if (command === "doctor") return print(await diagnose());
  if (command === "update") {
    if (flag(args, "--install-scheduler")) { await installScheduler(); return print({ ok: true, schedulerInstalled: true }); }
    if (flag(args, "--scheduled")) await new Promise(resolve => setTimeout(resolve, Math.random() * 1_800_000));
    return print(await update());
  }
  if (command === "commands" || command === "capabilities") console.log(await readFile(new URL("../capabilities.lock.json", import.meta.url), "utf8"));
  else throw new Error(`unknown command: ${command}`);
}

main().catch(error => {
  console.error(`cxclawctl: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
