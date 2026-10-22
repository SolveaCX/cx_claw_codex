import { option, optionList, options } from "../args.js";
import type { SolveaClient } from "./client.js";
import { jsonData, jsonValue, requireFlag, requireId, type JsonObject } from "./input.js";

type Handler = (client: SolveaClient, args: string[]) => Promise<unknown>;

const handlers: Record<string, Handler> = {
  "replace-mock-data": async (client, args) => {
    const records = await jsonValue(args);
    if (!Array.isArray(records)) throw new Error("replace-mock-data requires a JSON array");
    return client.replaceMockData(option(args, "--name", true)!, records);
  },
  "query-mock-data": (client, args) => client.queryMockData(option(args, "--name", true)!),
  "run-plugin": async (client, args) => {
    const payload = await jsonData(args);
    const config = "externalHttpCallConfig" in payload ? payload.externalHttpCallConfig : payload;
    return client.runPlugin(config, payload.externalHttpCallRequestBody as JsonObject | undefined);
  },
  "list-ai-fields": client => client.listAiFields(),
  "list-agent-ai-fields": client => client.listAgentAiFields(),
  "get-ai-field-guide": client => client.aiFieldGuide(),
  "initialize-ai-fields": client => client.initializeAiFields(),
  "list-managed-ai-fields": (client, args) => client.listManagedAiFields(
    Number(option(args, "--page") ?? 1), Number(option(args, "--page-size") ?? 50), option(args, "--keyword") ?? "",
  ),
  "get-managed-ai-field": (client, args) => client.getManagedAiField(requireId(args)),
  "create-managed-ai-field": async (client, args) => client.createManagedAiField(await jsonData(args)),
  "update-managed-ai-field": async (client, args) => client.updateManagedAiField(await jsonData(args)),
  "delete-managed-ai-field": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-managed-ai-field");
    return client.deleteManagedAiField(requireId(args));
  },
  "toggle-managed-ai-field": (client, args) => client.toggleManagedAiField(requireId(args)),
  "list-quality-alert-rules": client => client.listQualityAlertRules(),
  "get-quality-alert-rule": (client, args) => client.getQualityAlertRule(requireId(args)),
  "create-quality-alert-rule": async (client, args) => client.createQualityAlertRule(await jsonData(args)),
  "update-quality-alert-rule": async (client, args) => client.updateQualityAlertRule(await jsonData(args)),
  "delete-quality-alert-rule": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-quality-alert-rule");
    return client.deleteQualityAlertRule(requireId(args));
  },
  "list-quality-alert-messages": async (client, args) => client.listQualityAlertMessages(await jsonData(args)),
  "get-quality-alert-message": (client, args) => client.getQualityAlertMessage(requireId(args)),
  "list-templates": (client, args) => client.listTemplates({
    pageIndex: Number(option(args, "--page") ?? 1),
    pagesize: Number(option(args, "--page-size") ?? 50),
    keyword: option(args, "--keyword") ?? "",
    ...(options(args, "--scene").length ? { scenes: options(args, "--scene") } : {}),
    ...(option(args, "--status") ? { status: [option(args, "--status")] } : {}),
  }),
  "create-template": async (client, args) => {
    const payload = await jsonData(args, false);
    if (option(args, "--name")) payload.name = option(args, "--name");
    if (option(args, "--content")) payload.content = option(args, "--content");
    if (option(args, "--status")) payload.status = option(args, "--status");
    if (options(args, "--scene")[0]) payload.scene = options(args, "--scene")[0];
    if (!payload.name || !payload.content) throw new Error("create-template requires name and content");
    return client.createTemplate(payload);
  },
  "update-template": async (client, args) => {
    const payload = await jsonData(args, false);
    for (const [field, name] of [["name", "--name"], ["content", "--content"], ["status", "--status"]] as const) {
      if (option(args, name)) payload[field] = option(args, name);
    }
    if (!Object.keys(payload).length) throw new Error("update-template requires at least one changed field");
    return client.updateTemplate(requireId(args), payload);
  },
  "delete-templates": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-templates");
    const ids = optionList(args, "--ids").map(Number);
    if (!ids.length || ids.some(id => !Number.isSafeInteger(id) || id <= 0)) throw new Error("delete-templates requires positive integer --ids");
    return client.deleteTemplates(ids);
  },
};

export const EXTENDED_COMMANDS = new Set(Object.keys(handlers));

export async function runExtendedCommand(client: SolveaClient, command: string, args: string[]) {
  const handler = handlers[command];
  if (!handler) throw new Error(`TypeScript command not migrated yet: ${command}`);
  return handler(client, args);
}
