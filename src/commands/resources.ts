import type { Session } from "../types.js";
import { runApi } from "../business.js";

type ActionDefinition = {
  command: string;
  summary: string;
  usage: string;
};

const action = (command: string, summary: string, usage = ""): ActionDefinition => ({ command, summary, usage });

const resources = {
  agent: {
    list: action("list-agents", "List agents", "[--category text|voice]"),
    get: action("get-agent", "Get one agent", "--id <agent-id>"),
    create: action("create-agent", "Create an agent", "--data <json> | --data-file <path>"),
    update: action("update-agent", "Update an agent", "--data <json> | --data-file <path>"),
    "get-chatflow": action("get-chatflow-graph", "Get an agent chatflow", "--agent-id <agent-id>"),
  },
  intent: {
    list: action("list-intents", "List intents", "[--category <category>]"),
    get: action("get-intent", "Get one intent", "--id <intent-id>"),
    create: action("create-intent", "Create an intent", "--data <json> | --data-file <path>"),
    update: action("update-intent", "Update an intent", "--id <intent-id> (--data <json> | --data-file <path>)"),
    toggle: action("toggle-intent", "Enable or disable an intent", "--id <intent-id> [--enable | --disable] (default: --enable)"),
  },
  strategy: {
    list: action("list-strategies", "List strategies", "[--page-size <number>]"),
    entities: action("list-entities", "List strategy entities"),
    create: action("create-strategy", "Create a strategy", "--data <json> | --data-file <path>"),
    update: action("update-strategy", "Update a strategy", "--id <strategy-id> (--data <json> | --data-file <path>)"),
    toggle: action("toggle-strategy", "Enable or disable a strategy", "--id <strategy-id> [--enable | --disable] (default: --enable)"),
  },
  tool: {
    list: action("list-plugins", "List tools"),
    get: action("get-plugin", "Get one tool", "--id <tool-id>"),
    create: action("create-plugin", "Create a tool", "--data <json> | --data-file <path>"),
    update: action("update-plugin", "Update a tool", "--data <json> | --data-file <path>"),
    delete: action("delete-plugin", "Delete a tool", "--id <tool-id> --confirm-delete"),
  },
  knowledge: {
    list: action("list-knowledge", "List knowledge", "[--data <json> | --data-file <path>]"),
    get: action("get-knowledge", "Get one knowledge item", "--id <knowledge-id>"),
    update: action("update-knowledge", "Update a knowledge item", "--id <knowledge-id> (--data <json> | --data-file <path>)"),
    "upload-qa": action("upload-qa", "Upload QA items", "--data <json> | --data-file <path>"),
    tags: action("list-knowledge-tags", "List knowledge tags", "[--keyword <keyword>]"),
  },
  directory: {
    list: action("list-directories", "List knowledge directories"),
    create: action("create-folder", "Create a knowledge directory", "--name <name> [--parent-id <directory-id>]"),
    update: action("update-directory", "Update a knowledge directory", "--id <directory-id> (--name <name> | --data <json> | --data-file <path>)"),
    delete: action("delete-directory", "Delete a knowledge directory", "--id <directory-id> --confirm-delete"),
  },
  quality: {
    status: action("get-quality-status", "Get quality inspection status"),
    toggle: action("set-quality-status", "Enable or disable quality inspection", "--enable | --disable"),
    rules: action("list-quality-rules", "List quality rules", "[--begin-ts <milliseconds>] [--end-ts <milliseconds>]"),
    "get-rule": action("get-quality-rule", "Get one quality rule", "--inspection-key <key>"),
    "update-rule": action("update-quality-rule", "Update a quality rule", "--data <json> | --data-file <path>"),
    "get-custom-rule": action("get-custom-quality-rule", "Get one custom quality rule", "--inspection-key <key>"),
    "create-custom-rule": action("create-custom-quality-rule", "Create a custom quality rule", "--data <json> | --data-file <path>"),
    "update-custom-rule": action("update-custom-quality-rule", "Update a custom quality rule", "--data <json> | --data-file <path>"),
    "delete-custom-rule": action("delete-custom-quality-rule", "Delete a custom quality rule", "--inspection-key <key>"),
  },
  transcript: {
    list: action("list-transcripts", "List transcripts", "[--page <number>] [--page-size <number>] [--begin-ts <milliseconds>] [--end-ts <milliseconds>] [--data <json> | --data-file <path>]"),
    get: action("get-transcript", "Get one transcript", "--chat-id <chat-id>"),
    context: action("get-chat-context", "Get chat context", "--bot-id <bot-id> (--data <json> | --data-file <path>)"),
  },
  chat: {
    send: action("chat", "Send a synchronous chat message", "--message <text> [--bot-id <bot-id>] [--chat-id <chat-id>]"),
    async: action("chat-async", "Send an asynchronous chat message", "--message <text> [--bot-id <bot-id>] [--chat-id <chat-id>]"),
    result: action("get-async-result", "Get an asynchronous chat result", "--receipt <receipt> [--bot-id <bot-id>]"),
  },
} as const;

export type ResourceName = keyof typeof resources;

export function isResourceCommand(value: string): value is ResourceName {
  return value in resources;
}

export function resourceHelp(resource?: string, actionName?: string): string {
  if (!resource) return `Business resources:\n${Object.keys(resources).map(name => `  ${name}`).join("\n")}`;
  if (!isResourceCommand(resource)) throw new Error(`unknown resource: ${resource}`);
  const actions = resources[resource] as Record<string, ActionDefinition>;
  if (actionName) {
    const definition = actions[actionName];
    if (!definition) throw new Error(`unknown ${resource} action: ${actionName}\n${resourceHelp(resource)}`);
    return [
      definition.summary,
      `Usage: cxclawctl ${resource} ${actionName}${definition.usage ? ` ${definition.usage}` : ""}`,
    ].join("\n\n");
  }
  return [
    `${resource} actions:`,
    ...Object.entries(actions).map(([name, definition]) => `  ${name.padEnd(20)} ${definition.summary}`),
    `\nRun cxclawctl ${resource} <action> --help for action options.`,
  ].join("\n");
}

export function resolveResourceCommand(resource: ResourceName, action?: string): string {
  if (!action || action === "help") throw new Error(resourceHelp(resource));
  const definition = (resources[resource] as Record<string, ActionDefinition>)[action];
  if (!definition) throw new Error(`unknown ${resource} action: ${action}\n${resourceHelp(resource)}`);
  return definition.command;
}

export async function runResourceCommand(session: Session, resource: ResourceName, action: string | undefined, args: string[]) {
  await runApi(session, resolveResourceCommand(resource, action), args);
}
