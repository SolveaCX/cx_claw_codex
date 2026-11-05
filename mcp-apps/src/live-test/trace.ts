export type TraceStep = {
  id: string;
  title: string;
  status: "running" | "success" | "failed";
  elapsed?: number;
  input?: unknown;
  output?: unknown;
  error?: unknown;
  tools: { name: string; input?: unknown; result?: unknown }[];
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

export function normalizeTrace(transcript: unknown): TraceStep[] {
  const events: Record<string, unknown>[] = [];
  const histories: Record<string, unknown>[] = [];
  let runtimeMetadata: Record<string, unknown> | undefined;
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
    const chatContext = record(item.chatContext);
    runtimeMetadata ??= record(chatContext?.metadata);
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
    ...(runtimeMetadata
      ? [
          {
            id: "metadata",
            title: "Metadata",
            status: "success" as const,
            input: runtimeMetadata,
            tools: [],
          },
        ]
      : []),
    ...(chatStarted
      ? [
          {
            id: "prepare",
            title: "准备会话",
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
