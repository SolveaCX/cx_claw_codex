import { readFile } from "node:fs/promises";
import { option, positionals, flag } from "../args.js";
import type { Session } from "../types.js";
import { SolveaClient } from "./client.js";
import { EXTENDED_COMMANDS, runExtendedCommand } from "./extended-commands.js";
import { REMAINING_COMMANDS, runRemainingCommand } from "./remaining-commands.js";

type JsonObject = Record<string, unknown>;

function requireFlag(args: string[], name: string, command: string) {
  if (!flag(args, name)) throw new Error(`${command} requires ${name} after explicit user acknowledgement`);
}

function enabled(args: string[], command: string) {
  const enable = flag(args, "--enable");
  const disable = flag(args, "--disable");
  if (enable === disable) throw new Error(`${command} requires exactly one of --enable or --disable`);
  return enable;
}

async function data(args: string[]): Promise<JsonObject> {
  const file = option(args, "--data-file");
  const raw = file ? await readFile(file, "utf8") : option(args, "--data");
  if (!raw) throw new Error("--data or --data-file is required");
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("request data must be a JSON object");
  return parsed as JsonObject;
}

async function transcriptFilters(args: string[]): Promise<JsonObject> {
  const filters: JsonObject = {
    pageIndex: Number(option(args, "--page") ?? 1),
    pageSize: Number(option(args, "--page-size") ?? 50),
    debug: flag(args, "--debug"),
    ...(await optionalData(args)),
  };
  const optional: Array<[string, string, (value: string) => unknown]> = [
    ["beginTimestamp", "--begin-ts", Number], ["endTimestamp", "--end-ts", Number],
    ["touchPoint", "--touch-point", String], ["botId", "--bot-id", Number],
    ["agentId", "--agent-id", Number], ["intentId", "--intent-id", Number],
    ["keyword", "--keyword", String], ["handoff", "--handoff", value => value === "true"],
  ];
  for (const [field, name, convert] of optional) {
    const value = option(args, name);
    if (value !== undefined) filters[field] = convert(value);
  }
  return filters;
}

/** Native TypeScript business commands. Keep this table explicit so every command has a reviewable contract. */
export async function runSolveaCommand(session: Session, command: string, args: string[]): Promise<unknown> {
  const client = new SolveaClient(session);
  if (EXTENDED_COMMANDS.has(command)) return runExtendedCommand(client, command, args);
  if (REMAINING_COMMANDS.has(command)) return runRemainingCommand(client, command, args);
  const id = () => option(args, "--id", true)!;
  switch (command) {
    case "get-project": return client.projectInfo();
    case "list-agents": return client.listAgents(option(args, "--category") ?? "text");
    case "get-agent": return client.getAgent(id());
    case "get-chatflow-graph": return client.getChatflowGraph(option(args, "--agent-id", true)!);
    case "create-agent": return client.createAgent(await data(args));
    case "update-agent": return client.updateAgent(await data(args));
    case "list-plugins": return client.listPlugins();
    case "get-plugin": return client.getPlugin(id());
    case "create-plugin": return client.createPlugin(await data(args));
    case "update-plugin": return client.updatePlugin(await data(args));
    case "delete-plugin": requireFlag(args, "--confirm-delete", command); return client.deletePlugin(id());
    case "chat": return client.chat({ message: option(args, "--message") ?? option(args, "-m", true), botId: option(args, "--bot-id"), chatId: option(args, "--chat-id"), touchPoint: option(args, "--touch-point") ?? "LIVE_CHAT", ...(await optionalData(args)) });
    case "chat-async": return client.chatAsync({ message: option(args, "--message") ?? option(args, "-m", true), botId: option(args, "--bot-id"), chatId: option(args, "--chat-id"), touchPoint: option(args, "--touch-point") ?? "LIVE_CHAT", ...(await optionalData(args)) });
    case "get-async-result": return client.asyncResult(option(args, "--receipt", true)!, option(args, "--bot-id"));
    case "list-intents": return client.listIntents(option(args, "--category") ?? "E_COMMERCE");
    case "get-intent": return client.getIntent(id());
    case "create-intent": return client.createIntent(await data(args));
    case "update-intent": return client.updateIntent(id(), await data(args));
    case "toggle-intent": return client.toggleIntent(id(), !flag(args, "--disable"));
    case "list-entities": return client.listEntities();
    case "list-strategies": return client.listStrategies(Number(option(args, "--page-size") ?? 100));
    case "create-strategy": return client.createStrategy(await data(args));
    case "update-strategy": return client.updateStrategy(id(), await data(args));
    case "toggle-strategy": return client.toggleStrategy(id(), !flag(args, "--disable"));
    case "get-quality-status": return client.qualityStatus();
    case "set-quality-status": return client.setQualityStatus(enabled(args, command));
    case "list-quality-rules": return client.qualityRules(Number(option(args, "--begin-ts") ?? 0) || undefined, Number(option(args, "--end-ts") ?? 0) || undefined);
    case "get-quality-rule": return client.qualityRule(option(args, "--inspection-key", true)!);
    case "update-quality-rule": return client.updateQualityRule(await data(args));
    case "get-custom-quality-rule": return client.customQualityRule(option(args, "--inspection-key", true)!);
    case "create-custom-quality-rule": return client.createCustomQualityRule(await data(args));
    case "update-custom-quality-rule": return client.updateCustomQualityRule(await data(args));
    case "delete-custom-quality-rule": return client.deleteCustomQualityRule(option(args, "--inspection-key", true)!);
    case "list-knowledge": return client.listKnowledge(await optionalData(args));
    case "get-knowledge": return client.getKnowledge(id());
    case "update-knowledge": return client.updateKnowledge(id(), await data(args));
    case "upload-qa": return client.uploadQa((await data(args)).items as unknown[]);
    case "list-directories": return client.listDirectories();
    case "create-folder": return client.createFolder(option(args, "--name", true)!, Number(option(args, "--parent-id") ?? 0));
    case "update-directory": return client.updateDirectory(id(), option(args, "--name") ? { name: option(args, "--name") } : await data(args));
    case "delete-directory": requireFlag(args, "--confirm-delete", command); return client.deleteDirectory(id());
    case "list-knowledge-tags": return client.knowledgeTags(option(args, "--keyword") ?? "");
    case "get-transcript": return client.transcript(option(args, "--chat-id", true)!);
    case "list-transcripts": return client.listTranscripts(await transcriptFilters(args));
    case "get-chat-context": return client.chatContext(option(args, "--bot-id", true)!, await data(args));
    default: throw new Error(`TypeScript command not migrated yet: ${command}`);
  }
}

async function optionalData(args: string[]) {
  if (!option(args, "--data") && !option(args, "--data-file")) return {};
  return data(args);
}

export function isNativeSolveaCommand(command: string) {
  return EXTENDED_COMMANDS.has(command) || REMAINING_COMMANDS.has(command) || new Set([
    "get-project", "list-agents", "get-agent", "get-chatflow-graph", "create-agent", "update-agent",
    "list-plugins", "get-plugin", "create-plugin", "update-plugin", "delete-plugin", "chat", "chat-async",
    "get-async-result", "list-intents", "get-intent", "create-intent", "update-intent", "toggle-intent",
    "list-entities", "list-strategies", "create-strategy", "update-strategy", "toggle-strategy",
    "get-transcript", "list-transcripts", "get-chat-context", "get-quality-status", "set-quality-status",
    "list-quality-rules", "get-quality-rule", "update-quality-rule", "get-custom-quality-rule",
    "create-custom-quality-rule", "update-custom-quality-rule", "delete-custom-quality-rule",
    "list-knowledge", "get-knowledge", "update-knowledge", "upload-qa", "list-directories",
    "create-folder", "update-directory", "delete-directory", "list-knowledge-tags",
  ]).has(command);
}
