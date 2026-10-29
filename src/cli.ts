import { readFile } from "node:fs/promises";
import { authenticated, login, logout, publicAuthStatus } from "./auth.js";
import { flag, option, positionals, stripOptions } from "./args.js";
import { runApi } from "./business.js";
import { isResourceCommand, resourceCommandForImplementation, resourceHelp, runResourceCommand } from "./commands/resources.js";
import { diagnose } from "./doctor.js";
import { query as slsQuery } from "./sls.js";
import { deleteProfile, LEGACY_CONTEXT_ID, loadAuthSession, loadContext, loadProfile } from "./store.js";
import { bindContext, clearContext, createContext, createOrRefreshProfile, publicContext, publicContexts, publicProfile, publicProfiles, resolveTenantSession, search } from "./tenant.js";
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
import { errorOutput } from "./cli-error.js";
import { isFlatAnalyticsCommand } from "./commands/analytics.js";

const print = (value: unknown) => console.log(JSON.stringify(value, null, 2));
const usage = () => [
  "cxclawctl <resource> <action> [options]",
  "cxclawctl auth|tenant|context|profile|sls|runtime|doctor|update|setup|version",
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
  if (action === "logout") { await logout(); return print({ ok: true, loggedOut: true }); }
  if (action === "status") {
    try {
      const session = await loadAuthSession();
      return print(publicAuthStatus(session));
    } catch { return print({ ok: true, loggedIn: false }); }
  }
  if (action === "refresh") { return print(publicAuthStatus(await authenticated())); }
  throw new Error("auth action must be login, logout, status, or refresh");
}

async function runTenant(action: string | undefined, args: string[]) {
  const auth = await authenticated();
  const contextId = option(args, "--context") ?? LEGACY_CONTEXT_ID;
  const profileId = option(args, "--profile");
  if (action === "current") {
    if (profileId) return print(publicProfile(await loadProfile(profileId)));
    return print(await publicContext(await loadContext(contextId)));
  }
  if (action === "clear") return print(await publicContext(await clearContext(contextId)));
  if (action === "search") return print(await search(auth, positionals(args)[0] ?? "", option(args, "--env")));
  if (action === "use") {
    const accountId = Number(positionals(args)[0]);
    const selectedProfileId = profileId ?? `legacy-${option(args, "--env") ?? "prod"}-${accountId}`;
    if (!profileId) console.error("未传 --profile，正在更新 legacy default context；新会话应显式使用 --profile 和 --context。");
    const profile = await createOrRefreshProfile(auth, {
      accountId,
      env: option(args, "--env"),
      purpose: option(args, "--purpose", true)!,
      profileId: selectedProfileId,
      displayName: option(args, "--display-name"),
    });
    let context = await (async () => {
      try { return await loadContext(contextId); }
      catch { return contextId === LEGACY_CONTEXT_ID ? createContext(LEGACY_CONTEXT_ID) : Promise.reject(new Error(`CXClaw context not found: ${contextId}; run context init first`)); }
    })();
    context = await bindContext(context.contextId, profile.profileId);
    return print({ ok: true, context: await publicContext(context) });
  }
  throw new Error("tenant action must be search, use, current, or clear");
}

async function runContext(action: string | undefined, args: string[]) {
  if (action === "init") return print({ ok: true, context: await publicContext(await createContext(option(args, "--id"))) });
  if (action === "list") return print(await publicContexts());
  const contextId = option(args, "--context", true)!;
  if (action === "current") return print(await publicContext(await loadContext(contextId)));
  if (action === "use") return print({ ok: true, context: await publicContext(await bindContext(contextId, positionals(args)[0] ?? "")) });
  if (action === "clear") return print({ ok: true, context: await publicContext(await clearContext(contextId)) });
  throw new Error("context action must be init, list, current, use, or clear");
}

async function runProfile(action: string | undefined, args: string[]) {
  if (action === "list") return print(await publicProfiles());
  const profileId = positionals(args)[0] ?? "";
  if (action === "inspect") return print(publicProfile(await loadProfile(profileId)));
  if (action === "delete") { await deleteProfile(profileId); return print({ ok: true, deleted: true, profileId }); }
  if (action === "create") {
    const profile = await createOrRefreshProfile(await authenticated(), {
      profileId,
      accountId: Number(option(args, "--account-id", true)),
      env: option(args, "--env"),
      purpose: option(args, "--purpose", true)!,
      displayName: option(args, "--display-name"),
    });
    return print({ ok: true, profile: publicProfile(profile) });
  }
  throw new Error("profile action must be list, create, inspect, or delete");
}

const runtimeOptions = ["--context", "--profile"];
async function tenantSession(args: string[]) {
  const session = await resolveTenantSession(await authenticated(), { contextId: option(args, "--context"), profileId: option(args, "--profile") });
  console.error(JSON.stringify({ cxclawContext: {
    contextId: session.runtimeContext?.contextId,
    profileId: session.runtimeContext?.profileId,
    accountId: session.tenant?.accountId,
    environment: session.tenant?.environment,
    purpose: session.tenant?.purpose,
  } }));
  return session;
}
const businessArgs = (args: string[]) => stripOptions(args, runtimeOptions);

async function main(args = process.argv.slice(2)) {
  const [command, action, ...rest] = args;
  if (!command || command === "help" || flag(args, "--help")) {
    console.log(command && isResourceCommand(command) ? resourceHelp(command, action && !["help", "--help"].includes(action) ? action : undefined) : usage());
    return;
  }
  if (isResourceCommand(command)) {
    await runResourceCommand(await tenantSession(rest), command, action, businessArgs(rest));
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
  if (command === "mcp-server") {
    const { serveTenantMcp } = await import("./mcp/server.js");
    serveTenantMcp();
    return;
  }
  if (command === "auth") return runAuth(action, rest);
  if (command === "login" || command === "logout") return runAuth(command, args.slice(1));
  if (command === "tenant") return runTenant(action, rest);
  if (command === "context") return runContext(action, rest);
  if (command === "profile") return runProfile(action, rest);
  if (command === "runtime") return print(await runRuntime(action, rest));
  if (command === "workflow") return print(await runSolveaKitWorkflow(action, rest));
  if (command === "support") return print(await runSupport(await tenantSession(rest), action, businessArgs(rest)));
  if (command === "agent-builder") return print(await runAgentBuilder(["validate", "compile", "merge-source", "validate-tool", "migration", "replay"].includes(action ?? "") ? undefined : await tenantSession(rest), action, businessArgs(rest)));
  if (command === "agent-tester") return print(await runAgentTester(action === "create-sheet" ? undefined : await tenantSession(rest), action, businessArgs(rest)));
  if (command === "delivery") return print(await runDelivery(["classify", "plan", "report", "render", "render-report", "excel", "gen-excel", "render-summary"].includes(action ?? "") ? undefined : await tenantSession(rest), action, businessArgs(rest)));
  if (command === "poc") return print(await runPoc(["classify", "plan", "report", "render", "render-report", "excel", "gen-excel", "manual", "render-summary"].includes(action ?? "") ? undefined : await tenantSession(rest), action, businessArgs(rest)));
  if (command === "kb-builder") return print(await runKbBuilder(["crawl", "directory-plan", "extract-web-qa", "extract-ticket-qa", "batch-extract-ticket-qa"].includes(action ?? "") ? undefined : await tenantSession(rest), action, businessArgs(rest)));
  if (command === "solvea-desk") return print(await runDesk(await tenantSession(rest), action, businessArgs(rest)));
  if (command === "api") {
    if (!action) throw new Error("api command is required");
    if (isFlatAnalyticsCommand(action)) throw new Error("flat analytics commands are not supported; use cxclawctl analytics <action>");
    const publicCommand = resourceCommandForImplementation(action);
    if (publicCommand) throw new Error(`use the resource command instead: cxclawctl ${publicCommand}`);
    await runApi(await tenantSession(rest), action, businessArgs(rest)); return;
  }
  if (command === "sls" && action === "query") {
    return print(await slsQuery(await authenticated(), {
      environment: option(rest, "--env"),
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
  const output = errorOutput(error);
  console.error(JSON.stringify(output));
  process.exitCode = output.error.code;
});
