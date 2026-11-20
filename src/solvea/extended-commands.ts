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
  "list-ai-fields": (client) => client.listAiFields(),
  "list-agent-ai-fields": (client) => client.listAgentAiFields(),
  "get-ai-field-guide": (client) => client.aiFieldGuide(),
  "initialize-ai-fields": (client) => client.initializeAiFields(),
  "list-managed-ai-fields": (client, args) =>
    client.listManagedAiFields(
      Number(option(args, "--page") ?? 1),
      Number(option(args, "--page-size") ?? 50),
      option(args, "--keyword") ?? "",
    ),
  "get-managed-ai-field": (client, args) => client.getManagedAiField(requireId(args)),
  "create-managed-ai-field": async (client, args) =>
    client.createManagedAiField(await jsonData(args)),
  "update-managed-ai-field": async (client, args) =>
    client.updateManagedAiField(await jsonData(args)),
  "delete-managed-ai-field": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-managed-ai-field");
    return client.deleteManagedAiField(requireId(args));
  },
  "toggle-managed-ai-field": (client, args) => client.toggleManagedAiField(requireId(args)),
  "list-quality-alert-rules": (client) => client.listQualityAlertRules(),
  "get-quality-alert-rule": (client, args) => client.getQualityAlertRule(requireId(args)),
  "create-quality-alert-rule": async (client, args) =>
    client.createQualityAlertRule(await jsonData(args)),
  "update-quality-alert-rule": async (client, args) =>
    client.updateQualityAlertRule(await jsonData(args)),
  "delete-quality-alert-rule": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-quality-alert-rule");
    return client.deleteQualityAlertRule(requireId(args));
  },
  "list-quality-alert-messages": async (client, args) =>
    client.listQualityAlertMessages(await jsonData(args)),
  "get-quality-alert-message": (client, args) => client.getQualityAlertMessage(requireId(args)),
  "list-templates": (client, args) =>
    client.listTemplates({
      pageIndex: Number(option(args, "--page") ?? 1),
      pageSize: Number(option(args, "--page-size") ?? 50),
      keyword: option(args, "--keyword") ?? "",
      ...(options(args, "--scene").length ? { scenes: options(args, "--scene") } : {}),
      ...(options(args, "--status").length ? { status: options(args, "--status") } : {}),
      ...(options(args, "--source").length ? { sources: options(args, "--source") } : {}),
      ...(options(args, "--created-by").length
        ? { createdBys: options(args, "--created-by").map(Number) }
        : {}),
      ...(option(args, "--created-at-gte")
        ? { createdAtGte: Number(option(args, "--created-at-gte")) }
        : {}),
      ...(option(args, "--created-at-lte")
        ? { createdAtLte: Number(option(args, "--created-at-lte")) }
        : {}),
      ...(option(args, "--directory-id") !== undefined
        ? { directoryId: Number(option(args, "--directory-id")) }
        : {}),
    }),
  "get-template": (client, args) => client.getTemplate(requireId(args)),
  "list-template-options": (client) => client.listTemplateOptions(),
  "get-template-config": (client) => client.getTemplateConfig(),
  "create-template": async (client, args) => {
    const payload = await jsonData(args, false);
    if (option(args, "--name")) payload.name = option(args, "--name");
    if (option(args, "--content")) payload.content = option(args, "--content");
    if (option(args, "--status")) payload.status = option(args, "--status");
    if (options(args, "--scene")[0]) payload.scene = options(args, "--scene")[0];
    if (option(args, "--directory-id") !== undefined)
      payload.directoryId = Number(option(args, "--directory-id"));
    if (!payload.name || !payload.content)
      throw new Error("create-template requires name and content");
    return client.createTemplate(payload);
  },
  "update-template": async (client, args) => {
    const payload = await jsonData(args, false);
    for (const [field, name] of [
      ["name", "--name"],
      ["content", "--content"],
      ["status", "--status"],
    ] as const) {
      if (option(args, name)) payload[field] = option(args, name);
    }
    if (option(args, "--directory-id") !== undefined)
      payload.directoryId = Number(option(args, "--directory-id"));
    if (!Object.keys(payload).length)
      throw new Error("update-template requires at least one changed field");
    return client.updateTemplate(requireId(args), payload);
  },
  "batch-update-templates": async (client, args) => {
    const value = await jsonValue(args);
    const updates = Array.isArray(value) ? value : (value as JsonObject)?.list;
    if (
      !Array.isArray(updates) ||
      !updates.length ||
      updates.some((item) => !item || typeof item !== "object" || Array.isArray(item))
    )
      throw new Error(
        "batch-update-templates requires a non-empty JSON list or object containing list",
      );
    return client.batchUpdateTemplates(updates as JsonObject[]);
  },
  "move-templates": async (client, args) => {
    const payload = await jsonData(args, false);
    const rawIds = optionList(args, "--ids").length
      ? optionList(args, "--ids")
      : ((payload.templateIds ?? payload.ids) as unknown[] | undefined);
    const ids = Array.isArray(rawIds) ? rawIds.map(Number) : [];
    if (!ids.length || ids.some((id) => !Number.isSafeInteger(id) || id <= 0))
      throw new Error("move-templates requires positive integer --ids");
    const rawDirectoryId = option(args, "--directory-id") ?? payload.directoryId;
    const directoryId = Number(rawDirectoryId);
    if (!Number.isSafeInteger(directoryId) || directoryId < 0)
      throw new Error("move-templates requires a non-negative integer --directory-id");
    return client.moveTemplates(ids, directoryId);
  },
  "delete-templates": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-templates");
    const ids = optionList(args, "--ids").map(Number);
    if (!ids.length || ids.some((id) => !Number.isSafeInteger(id) || id <= 0))
      throw new Error("delete-templates requires positive integer --ids");
    return client.deleteTemplates(ids);
  },
  "list-template-directories": (client) => client.listTemplateDirectories(),
  "get-template-directory": (client, args) => client.getTemplateDirectory(requireId(args)),
  "create-template-directory": async (client, args) => {
    const payload = await jsonData(args, false);
    if (option(args, "--name")) payload.name = option(args, "--name");
    if (option(args, "--parent-id") !== undefined)
      payload.parentId = Number(option(args, "--parent-id"));
    if (!payload.name) throw new Error("create-template-directory requires --name");
    if (payload.parentId === undefined) payload.parentId = 0;
    return client.createTemplateDirectory(payload);
  },
  "update-template-directory": async (client, args) => {
    const payload = await jsonData(args, false);
    if (option(args, "--name")) payload.name = option(args, "--name");
    if (option(args, "--parent-id") !== undefined)
      payload.parentId = Number(option(args, "--parent-id"));
    if (!Object.keys(payload).length)
      throw new Error("update-template-directory requires --name or --parent-id");
    return client.updateTemplateDirectory(requireId(args), payload);
  },
  "delete-template-directory": async (client, args) => {
    requireFlag(args, "--confirm-delete", "delete-template-directory");
    return client.deleteTemplateDirectory(requireId(args));
  },
  "download-template-import-file": async (client, args) => ({
    file: await client.downloadTemplateImportFile(option(args, "--output", true)!),
  }),
  "import-templates-file": async (client, args) => ({
    imported: await client.importTemplatesFile(option(args, "--file", true)!),
  }),
  "export-templates": async (client, args) => {
    const payload = await jsonData(args, false);
    if (option(args, "--keyword") !== undefined) payload.keyword = option(args, "--keyword");
    if (options(args, "--status").length) payload.status = options(args, "--status");
    if (options(args, "--scene").length) payload.scenes = options(args, "--scene");
    if (options(args, "--source").length) payload.sources = options(args, "--source");
    if (options(args, "--created-by").length)
      payload.createdBys = options(args, "--created-by").map(Number);
    if (option(args, "--created-at-gte"))
      payload.createdAtGte = Number(option(args, "--created-at-gte"));
    if (option(args, "--created-at-lte"))
      payload.createdAtLte = Number(option(args, "--created-at-lte"));
    if (option(args, "--directory-id") !== undefined)
      payload.directoryId = Number(option(args, "--directory-id"));
    return client.exportTemplates(payload);
  },
  "get-template-export-tasks": async (client, args) =>
    client.rawCall("POST", `/api_v2/gpt/label/project/${await client.projectId()}/getLabelTask`, {
      page: Number(option(args, "--page") ?? 1),
      pageSize: Number(option(args, "--page-size") ?? 20),
      taskType: "EXPORT_TEMPLATE",
    }),
  "translate-template-contents": async (client, args) => {
    const payload = await jsonData(args);
    const contents = payload.contents;
    const targetLanguage = option(args, "--target-language") ?? payload.targetLanguage;
    if (!Array.isArray(contents)) throw new Error("translate-template-contents requires contents");
    return client.translateTemplateContents(contents, String(targetLanguage ?? ""));
  },
};

export const EXTENDED_COMMANDS = new Set(Object.keys(handlers));

export async function runExtendedCommand(client: SolveaClient, command: string, args: string[]) {
  const handler = handlers[command];
  if (!handler) throw new Error(`TypeScript command not migrated yet: ${command}`);
  return handler(client, args);
}
