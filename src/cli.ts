import { readFile } from "node:fs/promises";
import { authenticated, login, logout } from "./auth.js";
import { flag, option, positionals } from "./args.js";
import { runApi, runPython } from "./business.js";
import { isResourceCommand, resourceHelp, runResourceCommand } from "./commands/resources.js";
import { diagnose } from "./doctor.js";
import { query as slsQuery } from "./sls.js";
import { loadSession, saveSession } from "./store.js";
import { publicTenant, search, useTenant } from "./tenant.js";
import { installMarketplace, installScheduler, update } from "./update.js";
import { SERVER_API_VERSION, TOOL_SCHEMA_VERSION, VERSION } from "./version.js";
import { runRuntime } from "./workflows/runtime.js";
import { runSolveaKitWorkflow } from "./workflows/solvea-kit.js";

const print = (value: unknown) => console.log(JSON.stringify(value, null, 2));
const usage = () => [
  "cxclawctl <resource> <action> [options]",
  "cxclawctl auth|tenant|sls|runtime|doctor|update|setup|version",
  resourceHelp(),
  "Example: cxclawctl intent create --data-file intent.json",
].join("\n\n");

async function runAuth(action: string | undefined, args: string[]) {
  if (action === "login") return print(await login(option(args, "--server", true)!, (option(args, "--channel") ?? "stable") as "stable" | "canary" | "dev"));
  if (action === "logout") { await logout(); return print({ ok: true, loggedOut: true }); }
  if (action === "status") {
    try {
      const session = await loadSession();
      return print({ ok: true, loggedIn: true, email: session.email, channel: session.channel, accessExpiresAt: session.accessExpiry });
    } catch { return print({ ok: true, loggedIn: false }); }
  }
  if (action === "refresh") { const session = await authenticated(); return print({ ok: true, accessExpiresAt: session.accessExpiry }); }
  throw new Error("auth action must be login, logout, status, or refresh");
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
    const channel = (option(args, "--channel") ?? "stable") as "stable" | "canary" | "dev";
    await installMarketplace(channel); await login(option(args, "--server", true)!, channel); await installScheduler(); return;
  }
  if (command === "auth") return runAuth(action, rest);
  if (command === "login" || command === "logout") return runAuth(command, args.slice(1));
  if (command === "tenant" || command === "context") return runTenant(action, rest);
  if (command === "runtime") return print(await runRuntime(action, rest));
  if (command === "workflow") return print(await runSolveaKitWorkflow(action, rest));
  if (command === "api") { if (!action) throw new Error("api command is required"); await runApi(await authenticated(), action, rest); return; }
  if (command === "script") { if (!action) throw new Error("script path is required"); process.exitCode = await runPython(action, rest); return; }
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
