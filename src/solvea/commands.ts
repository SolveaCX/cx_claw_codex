import { readFile } from "node:fs/promises";
import { option, positionals, flag } from "../args.js";
import type { Session } from "../types.js";
import { SolveaClient } from "./client.js";

type JsonObject = Record<string, unknown>;
async function data(args: string[]): Promise<JsonObject> {
  const file = option(args, "--data-file");
  const raw = file ? await readFile(file, "utf8") : option(args, "--data");
  if (!raw) throw new Error("--data or --data-file is required");
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("request data must be a JSON object");
  return parsed as JsonObject;
}

/** Native TypeScript business commands. Keep this table explicit so every command has a reviewable contract. */
export async function runSolveaCommand(session: Session, command: string, args: string[]): Promise<unknown> {
  const client = new SolveaClient(session);
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
    case "delete-plugin": return client.deletePlugin(id());
    case "chat": return client.chat({ message: option(args, "--message", true), botId: option(args, "--bot-id"), chatId: option(args, "--chat-id"), touchPoint: option(args, "--touch-point") ?? "LIVE_CHAT", ...(await optionalData(args)) });
    case "chat-async": return client.chatAsync({ message: option(args, "--message", true), botId: option(args, "--bot-id"), chatId: option(args, "--chat-id"), touchPoint: option(args, "--touch-point") ?? "LIVE_CHAT", ...(await optionalData(args)) });
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
    case "get-transcript": return client.transcript(option(args, "--chat-id", true)!);
    case "list-transcripts": return client.listTranscripts(await data(args));
    case "get-chat-context": return client.chatContext(option(args, "--bot-id", true)!, await data(args));
    default: throw new Error(`TypeScript command not migrated yet: ${command}`);
  }
}

async function optionalData(args: string[]) {
  if (!option(args, "--data") && !option(args, "--data-file")) return {};
  return data(args);
}

export function isNativeSolveaCommand(command: string) {
  return new Set([
    "get-project", "list-agents", "get-agent", "get-chatflow-graph", "create-agent", "update-agent",
    "list-plugins", "get-plugin", "create-plugin", "update-plugin", "delete-plugin", "chat", "chat-async",
    "get-async-result", "list-intents", "get-intent", "create-intent", "update-intent", "toggle-intent",
    "list-entities", "list-strategies", "create-strategy", "update-strategy", "toggle-strategy",
    "get-transcript", "list-transcripts", "get-chat-context",
  ]).has(command);
}
