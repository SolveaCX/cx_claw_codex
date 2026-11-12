import { option } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { jsonData } from "../solvea/input.js";
import type { Session } from "../types.js";

const PATHS = {
  transcript: "/api_v2/as_bot/statement/transcript",
  message: "/api_v2/as_bot/statement/message",
  agent: "/api_v2/as_bot/statement/agent",
  intent: "/api_v2/as_bot/statement/transcript/intent",
  satisfaction: "/api_v2/as_bot/statement/satisfaction/feedback",
  "satisfaction-list": "/api_v2/as_bot/statement/satisfaction/message",
  feedback: "/api_v2/as_bot/statement/feedback",
  knowledge: "/api_v2/as_bot/statement/knowledge",
  "knowledge-export": "/api_v2/gpt/label/project/{projectId}/download/knowledge",
  "satisfaction-export": "/api_v2/gpt/label/project/{projectId}/download/message/satisfaction",
  "tag-distribution": "/api_v2/qa_bot/label/project/{projectId}/report/distribution",
  escalation: "/api_v2/as_bot/statement/transcript/reason2",
  "escalation-drilldown": "/api_v2/as_bot/statement/transcript/reason/three/level",
  "agent-weekly-graph": "/api_v2/as_bot/statement/graph/agent",
  "self-learning": "/api_v2/as_bot/statement/self-learning",
  livechat: "/api_v2/as_bot/livechat/report/summary",
  "livechat-table": "/api_v2/as_bot/livechat/report/table",
  inspection: "/api_v2/intelli/inspection/ticket/count",
  "inspection-history": "/api_v2/intelli/inspection/ticket/history",
  "inspection-tags-history": "/api_v2/intelli/inspection/ticket/tagsHistory",
  "inspection-tags": "/api_v2/intelli/inspection/ticket/tagsList",
  "inspection-export": "/api_v2/gpt/{projectId}/export/async",
} as const;

export type ReportAction = keyof typeof PATHS;

function isReportAction(value: string | undefined): value is ReportAction {
  return value !== undefined && value in PATHS;
}

async function legacyBody(args: string[], action: ReportAction) {
  const supplied = await jsonData(args, false);
  const begin = option(args, "--begin-ts") ?? supplied.beginTimestamp;
  const end = option(args, "--end-ts") ?? supplied.endTimestamp;
  if (begin === undefined || end === undefined)
    throw new Error(
      `report ${action} requires --begin-ts <milliseconds> and --end-ts <milliseconds>`,
    );

  const body: Record<string, unknown> = {
    ...supplied,
    beginTimestamp: Number(begin),
    endTimestamp: Number(end),
    timeOffset: Number(option(args, "--time-offset") ?? supplied.timeOffset ?? 8),
  };
  if (!Number.isSafeInteger(body.beginTimestamp) || !Number.isSafeInteger(body.endTimestamp))
    throw new Error("--begin-ts and --end-ts must be integer milliseconds");
  const optionalNumbers: Array<[string, string]> = [
    ["botId", "--bot-id"],
    ["agentId", "--agent-id"],
    ["firstIntentId", "--intent-id"],
  ];
  for (const [field, name] of optionalNumbers) {
    const value = option(args, name);
    if (value !== undefined) body[field] = Number(value);
  }
  const touchPoint = option(args, "--channel") ?? option(args, "--touch-point");
  if (touchPoint !== undefined) body.touchPoint = touchPoint;
  const dateUnit = option(args, "--date-unit");
  if (dateUnit !== undefined) body.dateUnit = dateUnit;
  if (action === "satisfaction-list") {
    body.page = Number(option(args, "--page") ?? supplied.page ?? 1);
    body.size = Number(option(args, "--page-size") ?? supplied.size ?? 20);
    const role = option(args, "--assistant-role");
    if (role !== undefined) body.assistantRole = role;
    const satisfied = option(args, "--satisfied");
    if (satisfied !== undefined) body.satisfied = satisfied === "true";
  }
  if (action === "knowledge") {
    body.page = Number(option(args, "--page") ?? supplied.page ?? 1);
    body.size = Number(option(args, "--page-size") ?? supplied.size ?? 20);
    const sortBy = option(args, "--sort-by");
    if (sortBy !== undefined) body.sortBy = JSON.parse(sortBy);
    const source = option(args, "--source");
    if (source !== undefined) body.source = source;
  }
  if (action === "escalation") body.dateUnit = option(args, "--date-unit") ?? "DAY";
  if (action === "escalation-drilldown") {
    body.reason = option(args, "--reason", true);
    body.dateUnit = "DAY";
    body.pageIndex = Number(option(args, "--page") ?? 1);
    body.pageSize = Number(option(args, "--page-size") ?? 10);
  }
  if (action === "livechat-table")
    body.page = {
      page: Number(option(args, "--page") ?? 1),
      size: Number(option(args, "--page-size") ?? 10),
    };
  return body;
}

async function inspectionBody(args: string[], action: ReportAction) {
  const supplied = await jsonData(args, false);
  const startDate = option(args, "--start-date") ?? supplied.startTime;
  const endDate = option(args, "--end-date") ?? supplied.endTime;
  if (typeof startDate !== "string" || typeof endDate !== "string")
    throw new Error(
      `report ${action} requires --start-date <YYYY-MM-DD> and --end-date <YYYY-MM-DD>`,
    );
  return {
    startTime: startDate,
    endTime: endDate,
    dimension: option(args, "--dimension") ?? supplied.dimension ?? "ticket",
    ...supplied,
  };
}

async function tagDistributionBody(args: string[]) {
  const supplied = await jsonData(args, false);
  const begin = option(args, "--begin-ts") ?? supplied.beginTimestamp;
  const end = option(args, "--end-ts") ?? supplied.endTimestamp;
  if (begin === undefined || end === undefined)
    throw new Error(
      "report tag-distribution requires --begin-ts <milliseconds> and --end-ts <milliseconds>",
    );
  const body: Record<string, unknown> = {
    ...supplied,
    beginTimestamp: Number(begin),
    endTimestamp: Number(end),
  };
  const optionalNumbers: Array<[string, string]> = [
    ["treeId", "--tree-id"],
    ["taskId", "--task-id"],
    ["level", "--level"],
    ["size", "--page-size"],
  ];
  for (const [field, name] of optionalNumbers) {
    const value = option(args, name);
    if (value !== undefined) body[field] = Number(value);
  }
  const tag = option(args, "--tag");
  if (tag !== undefined) body.tag = tag;
  return body;
}

export async function runReportAction(
  session: Session,
  action: string | undefined,
  args: string[],
) {
  if (!isReportAction(action)) throw new Error(`unknown report action: ${action ?? "<missing>"}`);
  const client = new SolveaClient(session);
  const inspectionAction = action.startsWith("inspection");
  const body =
    action === "tag-distribution"
      ? await tagDistributionBody(args)
      : inspectionAction
        ? await inspectionBody(args, action)
        : await legacyBody(args, action);
  const pathTemplate = PATHS[action];
  const needsProject =
    pathTemplate.includes("{projectId}") || (!inspectionAction && action !== "tag-distribution");
  const projectId = needsProject ? Number(await client.projectId()) : undefined;
  const path = pathTemplate.replace("{projectId}", String(projectId));
  const result = await client.rawCall(
    "POST",
    path,
    inspectionAction || action === "tag-distribution"
      ? body
      : {
          projectId: projectId!,
          ...body,
        },
  );
  console.log(JSON.stringify(result, null, 2));
}
