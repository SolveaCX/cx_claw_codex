export type TraceStep = {
  id: string;
  nodeId?: string;
  title: string;
  status: "running" | "success" | "failed";
  elapsed?: number;
  input?: unknown;
  output?: unknown;
  error?: unknown;
  tools: { name: string; input?: unknown; result?: unknown }[];
};

export function hasTraceStepDetails(step: TraceStep): boolean {
  return step.input != null || step.output != null || step.error != null || step.tools.length > 0;
}

export function buildPortalUrl(environment: string, path: string): string {
  const origin = environment === "prod" ? "https://ai.solvea.cx" : "https://ai-staging.solvea.cx";
  return new URL(path, origin).toString();
}

export function buildAgentDetailUrl(
  environment: string,
  agentId: string | number,
  type = "CHAT_FLOW",
): string {
  const normalized = type.toUpperCase();
  const path =
    normalized === "MULTI_AGENT"
      ? "/multiAgent/detail"
      : normalized === "CHAT_FLOW"
        ? "/chatflow/detail"
        : "/agent/detail";
  const url = new URL(buildPortalUrl(environment, path));
  url.searchParams.set("id", String(agentId));
  return url.toString();
}
export type TracePresentation = {
  incoming: {
    intent?: string;
    content?: string;
    summary?: string;
    fields: { name: string; value: unknown; aiExtract: boolean }[];
  };
  execution: { strategyName?: string; actionType: string; agentId?: string };
  chatId?: string;
  metadata?: Record<string, unknown>;
  steps: TraceStep[];
  result: {
    handoff: boolean;
    type?: string;
    reasons: string[];
    explain?: string;
    content?: string;
    language?: string;
  };
};

const record = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

const array = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const parsedRecord = (value: unknown) => {
  if (typeof value !== "string") return record(value);
  try {
    return record(JSON.parse(value));
  } catch {
    return undefined;
  }
};
const text = (...values: unknown[]) => {
  const value = values.find((candidate) => typeof candidate === "string" && candidate.trim());
  return typeof value === "string" ? value : undefined;
};

function transcriptMessages(transcript: unknown): Record<string, unknown>[] {
  const root = record(transcript);
  const values = Array.isArray(transcript)
    ? transcript
    : array(root?.messages ?? root?.turns ?? root?.list);
  return values.map(record).filter((item): item is Record<string, unknown> => Boolean(item));
}

export function extractTracePresentation(
  transcript: unknown,
  messageId?: string,
): TracePresentation {
  const root = record(transcript) ?? {};
  const messages = transcriptMessages(transcript);
  const selectedIndex = messageId
    ? messages.findIndex((message) => String(message.id ?? message.messageId ?? "") === messageId)
    : -1;
  const selected = messages[selectedIndex >= 0 ? selectedIndex : messages.length - 1] ?? root;
  const comparison =
    record(selected.contextComparison) ??
    record(selected.context) ??
    record(selected.data) ??
    selected;
  const chatContext = record(comparison.chatContext) ?? record(selected.chatContext) ?? comparison;
  const mixedQuery = record(chatContext.mixedQuery);
  const context = record(selected.context);
  const contextMetadata = record(context?.metadata);
  const aiFields = array(contextMetadata?.ai_fields)
    .map(record)
    .filter((field): field is Record<string, unknown> => Boolean(field))
    .map((field) => ({
      name: String(field.name ?? field.key ?? "字段"),
      value: field.values ?? field.value,
      aiExtract: field.aiExtract === true,
    }));
  const previousUser = messages
    .slice(0, selectedIndex >= 0 ? selectedIndex : messages.length)
    .reverse()
    .find((message) => String(message.role ?? message.type ?? "").toUpperCase() === "USER");
  const strategyAction = record(chatContext.strategyAction) ?? {};
  const ext = record(chatContext.ext);
  const scopedTrace = {
    chatContext: {
      metadata: chatContext.metadata,
      ext: {
        chatflow_run_info: ext?.chatflow_run_info,
        ai_agent_history_msg: ext?.ai_agent_history_msg,
      },
    },
  };
  const reasons = array(selected.reasonsDescList ?? selected.reasonList)
    .map(String)
    .filter(Boolean);
  const metadata = record(chatContext.metadata);
  return {
    incoming: {
      intent: text(chatContext.intentI18n, chatContext.intent),
      content: text(mixedQuery?.content),
      summary: text(
        mixedQuery?.knowledgeQuery,
        chatContext.query,
        mixedQuery?.userQuery,
        previousUser?.content,
        previousUser?.message,
      ),
      fields: aiFields,
    },
    execution: {
      strategyName: text(chatContext.strategyName),
      actionType: text(strategyAction.type, selected.actionType, "AI_REPLY")!,
      agentId: strategyAction.agentId == null ? undefined : String(strategyAction.agentId),
    },
    chatId: text(metadata?.__chat_id, selected.chatId, root.chatId, root.id),
    metadata,
    steps: normalizeTrace(scopedTrace),
    result: {
      handoff: selected.handoff === true,
      type: text(selected.type, selected.actionType),
      reasons: reasons.length
        ? reasons
        : ([text(selected.reasonDesc, selected.reason)].filter(Boolean) as string[]),
      explain: text(selected.explain),
      content: text(selected.filteredContent, selected.content, selected.message),
      language: text(chatContext.language),
    },
  };
}

export function normalizeTrace(transcript: unknown): TraceStep[] {
  const events: Record<string, unknown>[] = [];
  const histories: Record<string, unknown>[] = [];
  const visit = (value: unknown, depth = 0) => {
    if (depth > 12) return;
    if (Array.isArray(value)) {
      for (const item of value) visit(item, depth + 1);
      return;
    }
    const item = record(value);
    if (!item) return;
    if (["chat_started", "node_started", "node_finished"].includes(String(item.event)))
      events.push(item);
    if (["function_call", "tool_response"].includes(String(item.type))) histories.push(item);
    for (const [key, child] of Object.entries(item)) {
      if (key === "content" && typeof child === "string") continue;
      visit(child, depth + 1);
    }
  };
  visit(transcript);
  const uniqueEvents = [
    ...new Map(
      events.map((event) => [
        `${event.event}:${record(event.eventData)?.node_id ?? event.nodeId}:${event.timestamp}`,
        event,
      ]),
    ).values(),
  ];
  const starts = uniqueEvents.filter((event) => event.event === "node_started");
  const finishes = uniqueEvents.filter((event) => event.event === "node_finished");
  const chatStarted = uniqueEvents.find((event) => event.event === "chat_started");
  const chatStartedData = record(chatStarted?.eventData);
  const leading: TraceStep[] = [
    ...(chatStarted
      ? [
          {
            id: "prepare",
            title: "预处理",
            status: "success" as const,
            elapsed: Number(chatStartedData?.prepareTimeMillis ?? 0) || undefined,
            tools: [],
          },
        ]
      : []),
  ];
  const steps: TraceStep[] = starts.map((start, index) => {
    const data = record(start.eventData) ?? {};
    const nodeId = String(data.node_id ?? start.nodeId ?? index);
    const finish = finishes.find((candidate) => {
      const finishData = record(candidate.eventData);
      return (
        String(finishData?.node_id ?? candidate.nodeId ?? "") === nodeId &&
        Number(candidate.timestamp ?? 0) >= Number(start.timestamp ?? 0)
      );
    });
    const finishData = record(finish?.eventData) ?? {};
    return {
      id: `${nodeId}-${start.timestamp ?? index}`,
      nodeId,
      title: String(finishData.node_title ?? data.node_title ?? `Node ${nodeId}`),
      status: finishData.status === "failed" ? "failed" : finish ? "success" : "running",
      elapsed: Number(finishData.elapsed_time ?? finishData.total_elapsed_time ?? 0) || undefined,
      input: data.inputs,
      output: finishData.outputs,
      error: finishData.error,
      tools: array(finishData.traces ?? data.traces)
        .map((trace) => record(trace))
        .filter((trace): trace is Record<string, unknown> => Boolean(trace))
        .map((trace) => ({
          name: String(trace.tool_name ?? trace.query ?? "执行步骤"),
          input: trace.input,
          result: trace.result,
        })),
    };
  });
  if (steps.length) return [...leading, ...steps];
  const historySteps: TraceStep[] = histories.map((item, index) => {
    const content = parsedRecord(item.content);
    return {
      id: `history-${index}`,
      title:
        item.type === "function_call"
          ? `工具调用 · ${String(content?.name ?? "Agent Tool")}`
          : "工具响应",
      status: "success" as const,
      input: item.metadata ?? content?.arguments,
      output: item.type === "tool_response" ? (content ?? item.content) : undefined,
      tools: [],
    };
  });
  return [...leading, ...historySteps];
}
