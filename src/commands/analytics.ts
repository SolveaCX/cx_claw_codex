import { option } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { jsonData } from "../solvea/input.js";
import type { Session } from "../types.js";

const PATHS = {
  tickets: "tickets",
  messages: "messages",
  intents: "intents",
  agents: "agents",
  satisfaction: "satisfaction",
  "first-response": "first-response",
  "return-retention": "return-retention",
  "inspection-results": "inspection-results",
  "inspection-results-by-type": "inspection-results/by-type",
  "intent-top": "intents/top",
  "agent-top": "agents/top",
  "api-calls": "api-calls",
  "api-calls-summary": "api-calls/summary",
} as const;

export type AnalyticsAction = keyof typeof PATHS | "inbox-scripts";

export function isFlatAnalyticsCommand(value: string) {
  return value.startsWith("analytics-") || value.startsWith("chat-report-");
}

function isAnalyticsAction(value: string | undefined): value is AnalyticsAction {
  return value === "inbox-scripts" || (value !== undefined && value in PATHS);
}

async function requestBody(action: string, args: string[]) {
  const supplied = await jsonData(args, false);
  const startDate = option(args, "--start-date") ?? supplied.startDate;
  const endDate = option(args, "--end-date") ?? supplied.endDate;
  if (typeof startDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
    throw new Error(`analytics ${action} requires --start-date <YYYY-MM-DD>`);
  }
  if (typeof endDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    throw new Error(`analytics ${action} requires --end-date <YYYY-MM-DD>`);
  }
  if (startDate > endDate) throw new Error("--start-date must not be after --end-date");

  const body: Record<string, string | number> = { startDate, endDate };
  const numeric = (field: "botId" | "intentId" | "agentId" | "topN" | "toolId", name: string) => {
    const raw = option(args, name) ?? supplied[field];
    if (raw === undefined) return;
    const value = Number(raw);
    if (!Number.isSafeInteger(value) || value <= 0)
      throw new Error(`${name} must be a positive integer`);
    body[field] = value;
  };
  numeric("botId", "--bot-id");
  numeric("intentId", "--intent-id");
  numeric("agentId", "--agent-id");
  numeric("topN", "--top-n");
  numeric("toolId", "--tool-id");

  const touchPoint =
    option(args, "--channel") ?? option(args, "--touch-point") ?? supplied.touchPoint;
  if (touchPoint !== undefined) {
    if (typeof touchPoint !== "string" || !touchPoint.trim())
      throw new Error("--channel must be a non-empty string");
    body.touchPoint = touchPoint;
  }
  const timeType = option(args, "--time-type") ?? supplied.timeType;
  if (timeType !== undefined) {
    if (timeType !== "MESSAGE_CREATED_AT" && timeType !== "TICKET_CREATED_AT")
      throw new Error("--time-type must be MESSAGE_CREATED_AT or TICKET_CREATED_AT");
    body.timeType = timeType;
  }
  return body;
}

export async function runAnalyticsAction(
  session: Session,
  action: string | undefined,
  args: string[],
) {
  if (!isAnalyticsAction(action))
    throw new Error(`unknown analytics action: ${action ?? "<missing>"}`);
  const client = new SolveaClient(session);
  const result =
    action === "inbox-scripts"
      ? await client.rawCall("GET", "/api_v2/as_bot/chat-report/inbox-scripts")
      : await client.rawCall(
          "POST",
          `/api_v2/as_bot/chat-report/${PATHS[action]}`,
          await requestBody(action, args),
        );
  console.log(JSON.stringify(result, null, 2));
}
