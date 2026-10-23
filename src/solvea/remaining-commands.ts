import { flag, option, optionList } from "../args.js";
import type { SolveaClient } from "./client.js";
import { jsonData, jsonValue, requireFlag, requireId } from "./input.js";

type Handler = (client: SolveaClient, args: string[]) => Promise<unknown>;
const data = async (args: string[]) => jsonData(args, false);
const project = async (client: SolveaClient) => client.projectId();
const page = (args: string[]) => Number(option(args, "--page") ?? 1);
const pageSize = (args: string[]) => Number(option(args, "--page-size") ?? 50);
const reportBody = async (args: string[]) => ({
  beginTimestamp: Number(option(args, "--begin-ts", true)), endTimestamp: Number(option(args, "--end-ts", true)),
  timeOffset: Number(option(args, "--time-offset") ?? 8), ...(await data(args)),
});

const handlers: Record<string, Handler> = {
  "chat-stream": async (c, a) => c.chatStream({ message: option(a, "--message", true), botId: Number(option(a, "--bot-id") ?? await c.botId()), touchPoint: option(a, "--touch-point") ?? "LIVE_CHAT", ...(await data(a)) }),
  "update-chatflow": async (c, a) => c.updateChatflow(option(a, "--agent-id", true)!, await jsonData(a), flag(a, "--publish")),
  "get-conversations-by-intent": (c, a) => c.getConversationsByIntent(option(a, "--intent", true)!, Number(option(a, "--limit") ?? 50)),
  "resolve-transcript-chat-id": async (c, a) => c.resolveTranscriptChatId(option(a, "--external-id", true)!, Number(option(a, "--page-size") ?? 10)),
  "list-isolation-keywords": async (c, a) => c.rawCall("GET", `${c.qamPath}/project/${await project(c)}/isolation_keywords`, undefined, { keyword: option(a, "--keyword") ?? "", pageIndex: page(a), pageSize: pageSize(a) }),
  "create-isolation-keyword": async (c, a) => c.rawCall("POST", `${c.qamPath}/project/${await project(c)}/isolation_keyword`, { keyword: option(a, "--keyword", true) }),
  "update-isolation-keyword": async (c, a) => c.rawCall("POST", `${c.qamPath}/project/${await project(c)}/isolation_keyword/${requireId(a)}`, { keyword: option(a, "--keyword", true) }),
  "delete-isolation-keyword": async (c, a) => { requireFlag(a, "--confirm-delete", "delete-isolation-keyword"); return c.rawCall("DELETE", `${c.qamPath}/project/${await project(c)}/isolation_keyword/${requireId(a)}`); },
  "get-knowledge-isolation-keywords": (c, a) => c.getKnowledgeIsolationKeywords(requireId(a), option(a, "--type", true)!),
  "batch-update-isolation-keyword-bindings": async (c, a) => c.applyIsolationKeywordBindings(await data(a)),
  "edit-knowledge-tags": async (c, a) => c.editKnowledgeTags(await data(a)),
  "move-directory": (c, a) => c.moveDirectory(requireId(a), option(a, "--parent-id", true)!),
  "operate-knowledge": async (c, a) => c.operateKnowledge(await jsonValue(a), flag(a, "--confirm-delete")),
  "batch-update-knowledge": async (c, a) => c.updateKus(await jsonValue(a)),
  "update-document-content": async (c, a) => c.updateDocumentContent(requireId(a), option(a, "--type", true)!, await data(a)),
  "create-product-knowledge": async (c, a) => c.createProductKnowledge(await data(a)),
  "update-product-knowledge": async (c, a) => c.updateProductKnowledge(requireId(a), await data(a)),
  "batch-update-products": async (c, a) => c.updateKuProducts(await jsonValue(a)),
  "upload-web": async (c, a) => c.rawCall("POST", `${c.qamPath}/project/${await project(c)}/documents`, { documents: optionList(a, "--url").map(filePath => ({ filePath, docType: "TC", fileType: "website" })), taskType: "WEB", published: true, isVisible: true, metadata: { tags: [] }, directoryId: option(a, "--directory-id") ?? "" }),
  "list-label-groups": async (c, a) => c.rawCall("GET", `/api_v2/gpt/label/project/${await project(c)}/getTreeInfo`, undefined, option(a, "--name") ? { treeName: option(a, "--name")! } : undefined),
  "create-label-group": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/updateTreeInfo`, { ...(await data(a)), treeName: option(a, "--name", true), operateType: "CREATE" }),
  "update-label-group": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/updateTreeInfo`, { ...(await data(a)), id: Number(requireId(a)), operateType: "UPDATE" }),
  "delete-label-group": async (c, a) => { requireFlag(a, "--confirm-delete", "delete-label-group"); return c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/updateTreeInfo`, { id: Number(requireId(a)), operateType: "DELETE" }); },
  "get-label-tree": async (c, a) => c.rawCall("GET", `/api_v2/gpt/label/project/${await project(c)}/getTagTree`, undefined, { treeId: requireId(a), ...(option(a, "--keyword") ? { name: option(a, "--keyword")! } : {}) }),
  "get-label-detail-tree": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/getDetailTree`, { treeId: Number(requireId(a)), ...(await data(a)) }),
  "create-label-node": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/updateNode`, { treeId: Number(option(a, "--tree-id", true)), operateType: "CREATE", nodes: [await data(a)] }),
  "update-label-node": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/updateNode`, { treeId: Number(option(a, "--tree-id", true)), operateType: "UPDATE", nodes: [{ id: Number(requireId(a)), ...(await data(a)) }] }),
  "delete-label-node": async (c, a) => { requireFlag(a, "--confirm-delete", "delete-label-node"); return c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/updateNode`, { treeId: Number(option(a, "--tree-id", true)), operateType: "DELETE", nodes: [{ id: Number(requireId(a)) }] }); },
  "download-label-template": async (c, a) => ({ file: await c.downloadLabelTemplate(option(a, "--template-type") === "init" ? "VOC_LABEL_INIT" : "VOC_LABEL", option(a, "--output") ?? `${option(a, "--template-type") ?? "label"}_template.xlsx`) }),
  "download-labels": async (c, a) => ({ file: await c.downloadLabels(option(a, "--tree-id", true)!, option(a, "--output") ?? `labels_${option(a, "--tree-id", true)}.xlsx`) }),
  "upload-labels": (c, a) => c.uploadLabelFile(option(a, "--tree-id", true)!, option(a, "--file", true)!, flag(a, "--init")),
  "export-transcripts": async (c, a) => c.rawCall("POST", `/api_v2/gpt/project/${await project(c)}/transcripts/export/async`, { pageSize: pageSize(a), pageIndex: page(a), timeOffset: Number(option(a, "--time-offset") ?? 8), ...(await data(a)) }),
  "get-export-tasks": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/getLabelTask`, { page: page(a), pageSize: pageSize(a) }),
  "upload-batch-test-file": async (c, a) => ({ file: await c.uploadTempFile(option(a, "--file", true)!) }),
  "submit-batch-test": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/uploadMessage`, { file: option(a, "--file", true), type: option(a, "--type", true), ...(option(a, "--bot-id") ? { botId: Number(option(a, "--bot-id")) } : {}), ...(await data(a)) }),
  "get-batch-test-tasks": async (c, a) => c.rawCall("POST", `/api_v2/gpt/label/project/${await project(c)}/getLabelTask`, { page: page(a), pageSize: pageSize(a), ...(option(a, "--type") ? { taskType: option(a, "--type")! } : {}) }),
  "list-voice-agents": c => c.listAgents("voice"),
  "list-voice-transcripts": async (c, a) => c.rawCall("POST", "/api_v2/as_bot/voice-report/transcript-page", { pageNum: page(a), pageSize: pageSize(a), beginTimestamp: Number(option(a, "--begin-ts") ?? 0), endTimestamp: Number(option(a, "--end-ts") ?? 0) }),
  "get-voice-transcript": async (c, a) => c.rawCall("GET", `/api_v2/gpt/voice/transcript/projectId/${await project(c)}/history/${requireId(a)}`),
};

const reportPaths: Record<string, string> = {
  "report-transcript": "/api_v2/as_bot/statement/transcript", "report-message": "/api_v2/as_bot/statement/message", "report-agent": "/api_v2/as_bot/statement/agent", "report-intent": "/api_v2/as_bot/statement/transcript/intent", "report-satisfaction": "/api_v2/as_bot/statement/satisfaction/feedback", "report-satisfaction-list": "/api_v2/as_bot/statement/satisfaction/message", "report-knowledge": "/api_v2/as_bot/statement/knowledge", "report-escalation": "/api_v2/as_bot/statement/transcript/reason2", "report-livechat": "/api_v2/as_bot/livechat/report/summary", "report-livechat-table": "/api_v2/as_bot/livechat/report/table", "report-inspection": "/api_v2/intelli/inspection/ticket/count", "report-self-learning": "/api_v2/as_bot/statement/self-learning",
};
for (const [name, path] of Object.entries(reportPaths)) handlers[name] = async (c, a) => c.rawCall("POST", path, await reportBody(a));

export const REMAINING_COMMANDS = new Set(Object.keys(handlers));
export async function runRemainingCommand(client: SolveaClient, command: string, args: string[]) {
  const handler = handlers[command];
  if (!handler) throw new Error(`TypeScript command not migrated yet: ${command}`);
  return handler(client, args);
}
