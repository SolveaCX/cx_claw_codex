import type { Session } from "../types.js";
import { runApi } from "../business.js";
import { runAnalyticsAction } from "./analytics.js";
import { runReportAction } from "./report.js";

type ActionDefinition = {
  command?: string;
  summary: string;
  usage: string;
};

const action = (command: string, summary: string, usage = ""): ActionDefinition => ({
  command,
  summary,
  usage,
});
const directAction = (summary: string, usage = ""): ActionDefinition => ({ summary, usage });
const reportAction = (actionName: string, summary: string, usage = "") =>
  action(`report-${actionName}`, summary, usage);

export const resources = {
  agent: {
    list: action("list-agents", "List agents", "[--category text|voice]"),
    get: action("get-agent", "Get one agent", "--id <agent-id>"),
    create: action("create-agent", "Create an agent", "--data <json> | --data-file <path>"),
    update: action(
      "update-agent",
      "Update an agent",
      "--id <agent-id> (--data <json> | --data-file <path>)",
    ),
    "get-chatflow": action("get-chatflow-graph", "Get an agent chatflow", "--agent-id <agent-id>"),
  },
  intent: {
    list: action("list-intents", "List intents", "[--category <category>]"),
    get: action("get-intent", "Get one intent", "--id <intent-id>"),
    create: action("create-intent", "Create an intent", "--data <json> | --data-file <path>"),
    update: action(
      "update-intent",
      "Update an intent",
      "--id <intent-id> (--data <json> | --data-file <path>)",
    ),
    toggle: action(
      "toggle-intent",
      "Enable or disable an intent",
      "--id <intent-id> [--enable | --disable] (default: --enable)",
    ),
  },
  strategy: {
    list: action("list-strategies", "List strategies", "[--page-size <number>]"),
    entities: action("list-entities", "List strategy entities"),
    create: action("create-strategy", "Create a strategy", "--data <json> | --data-file <path>"),
    update: action(
      "update-strategy",
      "Update a strategy",
      "--id <strategy-id> (--data <json> | --data-file <path>)",
    ),
    toggle: action(
      "toggle-strategy",
      "Enable or disable a strategy",
      "--id <strategy-id> [--enable | --disable] (default: --enable)",
    ),
  },
  tool: {
    list: action("list-plugins", "List tools"),
    get: action("get-plugin", "Get one tool", "--id <tool-id>"),
    create: action("create-plugin", "Create a tool", "--data <json> | --data-file <path>"),
    update: action("update-plugin", "Update a tool", "--data <json> | --data-file <path>"),
    delete: action("delete-plugin", "Delete a tool", "--id <tool-id> --confirm-delete"),
    run: action(
      "run-plugin",
      "Run an HTTP tool without saving it",
      "--data <json> | --data-file <path>",
    ),
  },
  field: {
    canvas: action("list-ai-fields", "List CHAT_FLOW canvas fields"),
    "agent-range": action("list-agent-ai-fields", "List fields accepted by Agent validation"),
    guide: action("get-ai-field-guide", "Get AI Field initialization status"),
    initialize: action("initialize-ai-fields", "Initialize system AI Fields"),
    list: action(
      "list-managed-ai-fields",
      "List managed AI Fields",
      "[--page <number>] [--page-size <number>] [--keyword <name>]",
    ),
    get: action("get-managed-ai-field", "Get one managed AI Field", "--id <field-id>"),
    create: action(
      "create-managed-ai-field",
      "Create a managed AI Field",
      "--data <json> | --data-file <path>",
    ),
    update: action(
      "update-managed-ai-field",
      "Update a managed AI Field",
      "--data <json> | --data-file <path>",
    ),
    delete: action(
      "delete-managed-ai-field",
      "Delete a managed AI Field",
      "--id <field-id> --confirm-delete",
    ),
    toggle: action("toggle-managed-ai-field", "Toggle a managed AI Field", "--id <field-id>"),
  },
  template: {
    list: action(
      "list-templates",
      "List reply templates",
      "[--page <number>] [--page-size <number>] [--keyword <text>] [--scene <scene>] [--status <status>]",
    ),
    create: action(
      "create-template",
      "Create a reply template",
      "(--name <name> --content <content>) | --data-file <path>",
    ),
    update: action(
      "update-template",
      "Update a reply template",
      "--id <template-id> [--name <name>] [--content <content>] [--status <status>] [--data-file <path>]",
    ),
    delete: action(
      "delete-templates",
      "Delete reply templates",
      "--ids <id> [id...] --confirm-delete",
    ),
  },
  knowledge: {
    list: action(
      "list-knowledge",
      "List knowledge",
      "[--type <type>] [--page <number>] [--page-size <number>] [--keyword <text>] [--data <json> | --data-file <path>]",
    ),
    get: action(
      "get-knowledge",
      "Get one knowledge item",
      "--id <knowledge-id> --type <QA|LEARN_SELF|FILE|WEBSITE|PRODUCT>",
    ),
    update: action(
      "update-knowledge",
      "Update a knowledge item",
      "--id <knowledge-id> (--data <json> | --data-file <path>)",
    ),
    "upload-qa": action("upload-qa", "Upload QA items", "--data <json> | --data-file <path>"),
    tags: action("list-knowledge-tags", "List knowledge tags", "[--keyword <keyword>]"),
  },
  directory: {
    list: action("list-directories", "List knowledge directories"),
    create: action(
      "create-folder",
      "Create a knowledge directory",
      "--name <name> [--parent-id <directory-id>]",
    ),
    update: action(
      "update-directory",
      "Update a knowledge directory",
      "--id <directory-id> (--name <name> | --data <json> | --data-file <path>)",
    ),
    delete: action(
      "delete-directory",
      "Delete a knowledge directory",
      "--id <directory-id> --confirm-delete",
    ),
  },
  quality: {
    status: action("get-quality-status", "Get quality inspection status"),
    toggle: action(
      "set-quality-status",
      "Enable or disable quality inspection",
      "--enable | --disable",
    ),
    rules: action(
      "list-quality-rules",
      "List quality rules",
      "[--begin-ts <milliseconds>] [--end-ts <milliseconds>]",
    ),
    "get-rule": action("get-quality-rule", "Get one quality rule", "--inspection-key <key>"),
    "update-rule": action(
      "update-quality-rule",
      "Update a quality rule",
      "--data <json> | --data-file <path>",
    ),
    "get-custom-rule": action(
      "get-custom-quality-rule",
      "Get one custom quality rule",
      "--inspection-key <key>",
    ),
    "create-custom-rule": action(
      "create-custom-quality-rule",
      "Create a custom quality rule",
      "--data <json> | --data-file <path>",
    ),
    "update-custom-rule": action(
      "update-custom-quality-rule",
      "Update a custom quality rule",
      "--data <json> | --data-file <path>",
    ),
    "delete-custom-rule": action(
      "delete-custom-quality-rule",
      "Delete a custom quality rule",
      "--inspection-key <key>",
    ),
    alerts: action("list-quality-alert-rules", "List quality alert rules"),
    "get-alert": action("get-quality-alert-rule", "Get one quality alert rule", "--id <alert-id>"),
    "create-alert": action(
      "create-quality-alert-rule",
      "Create a quality alert rule",
      "--data <json> | --data-file <path>",
    ),
    "update-alert": action(
      "update-quality-alert-rule",
      "Update a quality alert rule",
      "--data <json> | --data-file <path>",
    ),
    "delete-alert": action(
      "delete-quality-alert-rule",
      "Delete a quality alert rule",
      "--id <alert-id> --confirm-delete",
    ),
    "alert-messages": action(
      "list-quality-alert-messages",
      "List quality alert messages",
      "--data <json> | --data-file <path>",
    ),
    "get-alert-message": action(
      "get-quality-alert-message",
      "Get one quality alert message",
      "--id <message-id>",
    ),
  },
  transcript: {
    list: action(
      "list-transcripts",
      "List transcripts",
      "[--page <number>] [--page-size <number>] [--begin-ts <milliseconds>] [--end-ts <milliseconds>] [--script <json>] [--chat-ids <id,id,...>] [--data <json> | --data-file <path>]",
    ),
    get: action("get-transcript", "Get one transcript", "--chat-id <chat-id>"),
    context: action(
      "get-chat-context",
      "Get chat context",
      "--bot-id <bot-id> (--data <json> | --data-file <path>)",
    ),
  },
  chat: {
    send: action(
      "chat",
      "Send a synchronous chat message",
      "--message <text> [--bot-id <bot-id>] [--chat-id <chat-id>]",
    ),
    async: action(
      "chat-async",
      "Send an asynchronous chat message",
      "--message <text> [--bot-id <bot-id>] [--chat-id <chat-id>]",
    ),
    result: action(
      "get-async-result",
      "Get an asynchronous chat result",
      "--receipt <receipt> [--bot-id <bot-id>]",
    ),
  },
  analytics: {
    tickets: directAction(
      "Query Agent ticket metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>]",
    ),
    messages: directAction(
      "Query Agent message metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>]",
    ),
    intents: directAction(
      "Query Agent intent metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>] [--intent-id <intent-id>]",
    ),
    agents: directAction(
      "Query Agent metrics by agent",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>] [--agent-id <agent-id>]",
    ),
    satisfaction: directAction(
      "Query Agent satisfaction metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "first-response": directAction(
      "Query first-response metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "return-retention": directAction(
      "Query retention metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "inspection-results": directAction(
      "Query inspection metrics",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "inspection-results-by-type": directAction(
      "Query inspection metrics grouped by result type",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD>",
    ),
    "intent-top": directAction(
      "Query top intents",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--top-n <number>] [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "agent-top": directAction(
      "Query top agents",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--top-n <number>] [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "api-calls": directAction(
      "Query tool/API call trends and drill-down scripts",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--tool-id <id>] [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "api-calls-summary": directAction(
      "Query tool/API call summary",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--top-n <number>] [--channel <channel>] [--bot-id <bot-id>]",
    ),
    "inbox-scripts": directAction("Get Agent inbox drill-down scripts"),
  },
  report: {
    transcript: reportAction(
      "transcript",
      "Query ticket detail metrics used by Agent Analytics",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>] [--date-unit <DAY|WEEK|TOTAL>]",
    ),
    message: reportAction(
      "message",
      "Query message detail metrics used by Agent Analytics",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>] [--date-unit <DAY|WEEK|TOTAL>]",
    ),
    agent: reportAction(
      "agent",
      "Query agent detail metrics used by Agent Analytics",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--agent-id <id>] [--channel <channel>] [--date-unit <DAY|WEEK|TOTAL>]",
    ),
    intent: reportAction(
      "intent",
      "Query intent detail metrics used by Agent Analytics",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--intent-id <id>] [--channel <channel>] [--date-unit <DAY|WEEK|TOTAL>]",
    ),
    satisfaction: reportAction(
      "satisfaction",
      "Query satisfaction summary",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>]",
    ),
    "satisfaction-list": reportAction(
      "satisfaction-list",
      "Query satisfaction details",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--page <number>] [--page-size <number>] [--assistant-role <ASSISTANT|HUMAN>] [--satisfied <true|false>]",
    ),
    feedback: reportAction(
      "feedback",
      "Query legacy report rating distribution",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>]",
    ),
    knowledge: reportAction(
      "knowledge",
      "Query knowledge usage details",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--page <number>] [--page-size <number>] [--sort-by <json>] [--source <source>]",
    ),
    "knowledge-export": reportAction(
      "knowledge-export",
      "Submit knowledge usage export",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>]",
    ),
    "satisfaction-export": reportAction(
      "satisfaction-export",
      "Submit satisfaction detail export",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>]",
    ),
    "tag-distribution": reportAction(
      "tag-distribution",
      "Query AI tag tree/list distribution and chatIds",
      "--begin-ts <ms> --end-ts <ms> [--tree-id <id>] [--task-id <id>] [--level <number>] [--tag <name>] [--page-size <number>]",
    ),
    escalation: reportAction(
      "escalation",
      "Query escalation reasons",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--date-unit <DAY|WEEK>] [--bot-id <id>] [--channel <channel>]",
    ),
    "escalation-drilldown": reportAction(
      "escalation-drilldown",
      "Query escalation reason drilldown",
      "--begin-ts <ms> --end-ts <ms> --reason <reason> [--time-offset <hours>] [--page <number>] [--page-size <number>]",
    ),
    "agent-weekly-graph": reportAction(
      "agent-weekly-graph",
      "Query legacy report agent weekly graph",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>]",
    ),
    "self-learning": reportAction(
      "self-learning",
      "Query self-learning metrics",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--bot-id <id>] [--channel <channel>]",
    ),
    livechat: reportAction(
      "livechat",
      "Query LiveChat report summary",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>]",
    ),
    "livechat-table": reportAction(
      "livechat-table",
      "Query LiveChat report details",
      "--begin-ts <ms> --end-ts <ms> [--time-offset <hours>] [--page <number>] [--page-size <number>]",
    ),
    inspection: reportAction(
      "inspection",
      "Query inspection report summary",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--dimension <dimension>]",
    ),
    "inspection-history": reportAction(
      "inspection-history",
      "Query inspection report history",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--dimension <dimension>]",
    ),
    "inspection-tags": reportAction(
      "inspection-tags",
      "Query inspection tag distribution and chatIds",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--dimension <dimension>]",
    ),
    "inspection-tags-history": reportAction(
      "inspection-tags-history",
      "Query inspection tag trend and chatIds",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--dimension <dimension>]",
    ),
    "inspection-export": reportAction(
      "inspection-export",
      "Submit inspection report export",
      "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--dimension <dimension>]",
    ),
  },
} as const;

const CLI_NAME = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
for (const [resource, actions] of Object.entries(resources)) {
  if (!CLI_NAME.test(resource)) throw new Error(`invalid CLI resource name: ${resource}`);
  for (const [actionName, definition] of Object.entries(actions)) {
    if (!CLI_NAME.test(actionName))
      throw new Error(`invalid CLI action name: ${resource} ${actionName}`);
    if (definition.command && !CLI_NAME.test(definition.command))
      throw new Error(`invalid internal command name: ${definition.command}`);
  }
}

export function resourceCommandDefinitions() {
  return Object.entries(resources).flatMap(([resource, actions]) =>
    Object.entries(actions).map(([actionName, definition]) => ({
      resource,
      action: actionName,
      implementation: definition.command,
    })),
  );
}

export function resourceCommandForImplementation(command: string) {
  const definition = resourceCommandDefinitions().find((item) => item.implementation === command);
  return definition ? `${definition.resource} ${definition.action}` : undefined;
}

export type ResourceName = keyof typeof resources;

export function isResourceCommand(value: string): value is ResourceName {
  return value in resources;
}

export function resourceHelp(resource?: string, actionName?: string): string {
  if (!resource)
    return `Business resources:\n${Object.keys(resources)
      .map((name) => `  ${name}`)
      .join("\n")}`;
  if (!isResourceCommand(resource)) throw new Error(`unknown resource: ${resource}`);
  const actions = resources[resource] as Record<string, ActionDefinition>;
  if (actionName) {
    const definition = actions[actionName];
    if (!definition)
      throw new Error(`unknown ${resource} action: ${actionName}\n${resourceHelp(resource)}`);
    return [
      definition.summary,
      `Usage: cxclawctl ${resource} ${actionName}${definition.usage ? ` ${definition.usage}` : ""}`,
    ].join("\n\n");
  }
  return [
    `${resource} actions:`,
    ...Object.entries(actions).map(
      ([name, definition]) => `  ${name.padEnd(20)} ${definition.summary}`,
    ),
    `\nRun cxclawctl ${resource} <action> --help for action options.`,
  ].join("\n");
}

export function resolveResourceCommand(resource: ResourceName, action?: string): string {
  if (!action || action === "help") throw new Error(resourceHelp(resource));
  const definition = (resources[resource] as Record<string, ActionDefinition>)[action];
  if (!definition)
    throw new Error(`unknown ${resource} action: ${action}\n${resourceHelp(resource)}`);
  if (!definition.command) throw new Error(`${resource} ${action} is implemented directly`);
  return definition.command;
}

export async function runResourceCommand(
  session: Session,
  resource: ResourceName,
  action: string | undefined,
  args: string[],
) {
  if (!action || action === "help") throw new Error(resourceHelp(resource));
  const definition = (resources[resource] as Record<string, ActionDefinition>)[action];
  if (!definition)
    throw new Error(`unknown ${resource} action: ${action}\n${resourceHelp(resource)}`);
  if (resource === "analytics") return runAnalyticsAction(session, action, args);
  if (resource === "report") return runReportAction(session, action, args);
  if (!definition.command) throw new Error(`${resource} ${action} has no implementation`);
  await runApi(session, definition.command, args);
}
