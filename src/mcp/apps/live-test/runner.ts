import { resolveRuntimeSession } from "../../../runtime/session.js";
import { SolveaClient, SolveaHttpError } from "../../../solvea/client.js";
import type { Session } from "../../../types.js";
import type { LiveTestSnapshot, LiveTestStartInput } from "./contract.js";
import { LiveTestStore } from "./store.js";

type JsonObject = Record<string, unknown>;
const protectedMetadata = new Set([
  "specified_agent_id",
  "specified_agent_data",
  "specified_flow_version",
  "active_flow_version",
  "resolved_sub_graph_versions",
  "draft_flow_update_time",
  "show_chat_flow",
]);
const protectedOptions = new Set(["debug", "verbose"]);
const filtered = (value: JsonObject, protectedKeys: Set<string>) =>
  Object.fromEntries(Object.entries(value).filter(([key]) => !protectedKeys.has(key)));
const object = (value: unknown): JsonObject | undefined =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : undefined;
const firstObject = (value: unknown) => (Array.isArray(value) ? object(value[0]) : object(value));
const stringValue = (...values: unknown[]) => {
  const value = values.find((candidate) => typeof candidate === "string" && candidate);
  return typeof value === "string" ? value : undefined;
};
const numberValue = (...values: unknown[]) => {
  const value = values.map(Number).find(Number.isSafeInteger);
  return value;
};

function failedNode(action: JsonObject) {
  const contexts = [object(action.contextComparison), object(action.context)];
  for (const context of contexts) {
    const chatContext = object(context?.chatContext) ?? context;
    const ext = object(chatContext?.ext);
    const rows = ext?.chatflow_run_info;
    if (!Array.isArray(rows)) continue;
    const row = rows.map(object).find((item) => object(item?.eventData)?.status === "failed");
    const eventData = object(row?.eventData);
    if (row && eventData)
      return {
        id: stringValue(eventData.nodeId, row.nodeId, row.id),
        title: stringValue(
          eventData.nodeTitle,
          eventData.title,
          row.nodeTitle,
          row.title,
          row.name,
        ),
        error:
          stringValue(
            eventData.errorMessage,
            eventData.message,
            eventData.error,
            row.errorMessage,
            row.message,
          ) ?? "Chatflow node failed",
      };
  }
}

function actionResult(action: JsonObject) {
  const data = object(action.data);
  const message = object(action.message);
  const reasonList = Array.isArray(action.reasonList) ? action.reasonList.map(String) : [];
  const node = failedNode(action);
  const actionType = stringValue(action.type, action.actionType, data?.type, data?.actionType);
  const failed =
    actionType?.toUpperCase() === "STOPPED" ||
    actionType?.toUpperCase() === "CONFUSED" ||
    action.reason === "SYSTEM_ERROR" ||
    reasonList.includes("SYSTEM_ERROR") ||
    Boolean(node);
  const contexts = [object(action.contextComparison), object(action.context)];
  const contextCandidates = [
    ...contexts.map((context) => object(context?.chatContext)),
    ...contexts,
  ];
  const routingKeys = new Set([
    "originIntent",
    "intents",
    "intent",
    "intentI18n",
    "strategyId",
    "strategyName",
  ]);
  const chatContext =
    contextCandidates.find(
      (context) => context && Object.keys(context).some((key) => routingKeys.has(key)),
    ) ??
    contextCandidates.find((context) => context && Object.keys(context).length > 0) ??
    {};
  const ext = object(chatContext.ext) ?? {};
  const strategyAction = object(chatContext.strategyAction) ?? {};
  const intents = Array.isArray(chatContext.intents)
    ? chatContext.intents.flatMap((item): { id?: unknown; name?: string }[] => {
        const value = object(item);
        if (!value) return item == null ? [] : [{ name: String(item) }];
        return [
          {
            id: value.id ?? value.intentId,
            name: stringValue(value.name, value.intentName),
          },
        ];
      })
    : [];
  const routing = {
    originIntent: stringValue(chatContext.originIntent),
    intents,
    intent: stringValue(chatContext.intentI18n, chatContext.intent),
    strategy: {
      id: chatContext.strategyId ?? action.strategyId,
      name: stringValue(chatContext.strategyName, action.strategyName),
      actionType: stringValue(strategyAction.type, action.strategyActionType, action.type),
    },
    agent: {
      id: strategyAction.agentId ?? chatContext.agentId ?? action.agentId,
      name: stringValue(ext.invoke_agent_name, chatContext.agentName, action.agentName),
      type: stringValue(chatContext.agentType, action.agentType),
    },
    flowVersion: numberValue(chatContext.activeFlowVersion, ext.flow_version),
  };
  return {
    chatId: stringValue(action.chatId, object(action.chat)?.id),
    messageId: stringValue(message?.id, action.messageId, action.id),
    content: stringValue(message?.content, action.content, data?.content) ?? "",
    outcome: {
      actionType,
      handoff:
        action.handoff === true ||
        data?.handoff === true ||
        ["TO_AGENT", "TRANSFER_TO_AGENT"].includes(actionType?.toUpperCase() ?? ""),
      reason: stringValue(action.reason, data?.reason),
      reasonDesc: stringValue(action.reasonDesc, data?.reasonDesc),
      explain: stringValue(action.explain, data?.explain),
    },
    routing,
    failed,
    node,
    error:
      node?.error ??
      (failed
        ? (stringValue(
            message?.content,
            action.error,
            action.explain,
            action.reasonDesc,
            action.reason,
          ) ?? "Agent execution failed")
        : undefined),
  };
}

function evaluateRouting(
  expected: LiveTestSnapshot["turns"][number]["expected"],
  routing: ReturnType<typeof actionResult>["routing"],
) {
  if (!expected) return { verdict: "UNJUDGED" as const, checks: [] };
  const actual: Record<string, unknown> = {
    intentId: routing.intents[0]?.id,
    intent: routing.intent,
    strategyId: routing.strategy.id,
    strategyName: routing.strategy.name,
    agentId: routing.agent.id,
    actionType: routing.strategy.actionType,
  };
  const checks = Object.entries(expected).flatMap(([field, expectedValue]) => {
    if (expectedValue === undefined || expectedValue === "") return [];
    const actualValue = actual[field];
    const passed = ["intent", "strategyName", "actionType"].includes(field)
      ? String(actualValue ?? "")
          .trim()
          .toLocaleLowerCase() === String(expectedValue).trim().toLocaleLowerCase()
      : String(actualValue ?? "") === String(expectedValue);
    return [{ field, expected: expectedValue, actual: actualValue, passed }];
  });
  return {
    verdict:
      checks.length && checks.every((check) => check.passed)
        ? ("PASS" as const)
        : ("FAIL" as const),
    checks,
  };
}

function debugTranscript(value: unknown) {
  let candidates = [value];
  for (let depth = 0; depth < 3; depth += 1) {
    const nested: unknown[] = [];
    for (const item of candidates) {
      const record = object(item);
      if (record) {
        if (record.debug === true || record.isDebug === true) return true;
        nested.push(...Object.values(record));
      } else if (Array.isArray(item)) nested.push(...item);
    }
    candidates = nested;
  }
  return false;
}

function resolveFlowVersion(graph: unknown, agent: JsonObject): number | undefined {
  const value = firstObject(graph) ?? object(graph) ?? {};
  const data = object(value.data) ?? value;
  const meta = object(agent.meta);
  return numberValue(
    data.flowVersion,
    data.version,
    object(data.draft)?.flowVersion,
    object(data.published)?.flowVersion,
    meta?.chatFlowVersion,
  );
}

export class LiveTestRunner {
  constructor(
    private readonly store: LiveTestStore,
    private readonly resolveSession: (
      contextId: string,
      options?: { forceProfileRefresh?: boolean; minValiditySeconds?: number },
    ) => Promise<Session> = resolveRuntimeSession,
  ) {}

  async run(snapshot: LiveTestSnapshot, input: LiveTestStartInput, signal: AbortSignal) {
    const { profileId, testRunId } = snapshot;
    try {
      await this.store.update(profileId, testRunId, (value) => {
        value.status = "resolving";
      });
      const initialSession = await this.resolveSession(input.contextId, {
        minValiditySeconds: 150,
      });
      this.assertIdentity(snapshot, initialSession);
      const initialClient = new SolveaClient(initialSession);
      const testScope = snapshot.testScope;
      let agentName: string | undefined;
      let agentType: "CHAT_FLOW" | "SINGLE_AGENT" | undefined;
      const botId = input.botId ?? Number(await initialClient.botId());
      let flowVersion: number | undefined;
      if (testScope === "AGENT") {
        const agent = firstObject(await initialClient.getAgent(String(input.agentId)));
        if (!agent) throw new Error(`Agent ${input.agentId} not found`);
        const resolvedType = stringValue(agent.type)?.toUpperCase();
        if (resolvedType !== "CHAT_FLOW" && resolvedType !== "SINGLE_AGENT")
          throw new Error(`LiveTest does not support Agent type: ${resolvedType ?? "UNKNOWN"}`);
        agentType = resolvedType;
        agentName = stringValue(agent.name, agent.title);
        if (agentType === "CHAT_FLOW") {
          flowVersion =
            input.flowVersion ??
            resolveFlowVersion(await initialClient.getChatflowGraph(String(input.agentId)), agent);
          if (!Number.isSafeInteger(flowVersion))
            throw new Error("unable to resolve Chatflow version");
        } else if (input.flowVersion !== undefined) {
          throw new Error("SINGLE_AGENT does not support flowVersion; remove this parameter");
        }
      } else if (input.chatId && !debugTranscript(await initialClient.transcript(input.chatId))) {
        throw new Error("END_TO_END 续测只能复用 debug=true 的测试会话 chatId");
      }
      await this.store.update(profileId, testRunId, (value) => {
        value.status = "running";
        value.agentName = agentName;
        value.agentType = agentType;
        value.botId = botId;
        value.flowVersion = flowVersion;
      });

      let chatId = input.chatId;
      for (const turn of snapshot.turns) {
        if (signal.aborted) throw signal.reason ?? new DOMException("Cancelled", "AbortError");
        const index = turn.index;
        await this.store.update(profileId, testRunId, (value) => {
          value.turns[index]!.status = "running";
          value.turns[index]!.startedAt = Date.now();
        });
        const metadata: JsonObject = filtered(input.metadata, protectedMetadata);
        if (testScope === "AGENT") metadata.specified_agent_id = input.agentId;
        if (testScope === "AGENT" && agentType === "CHAT_FLOW") {
          metadata.specified_flow_version = flowVersion;
          metadata.show_chat_flow = true;
        } else if (testScope === "END_TO_END") {
          metadata.show_chat_flow = true;
        }
        const payload: JsonObject = {
          botId,
          chatId,
          touchPoint: input.touchPoint,
          message: turn.user,
          ...(turn.attachments?.length ? { attachments: turn.attachments } : {}),
          metadata,
          option: { ...filtered(input.option, protectedOptions), debug: true, verbose: true },
        };
        let pending = "";
        let lastFlush = 0;
        const flush = async (force = false) => {
          if (!pending || (!force && Date.now() - lastFlush < 200)) return;
          const delta = pending;
          pending = "";
          lastFlush = Date.now();
          await this.store.update(profileId, testRunId, (value) => {
            value.turns[index]!.assistant += delta;
          });
        };
        const execute = async (forceRefresh = false) => {
          const session = await this.resolveSession(input.contextId, {
            forceProfileRefresh: forceRefresh,
            minValiditySeconds: 150,
          });
          this.assertIdentity(snapshot, session);
          const client = new SolveaClient(session);
          if (input.touchPoint !== "LIVE_CHAT") return object(await client.chat(payload)) ?? {};
          return client.chatStreamTrace(
            payload,
            {
              onDelta: async (delta) => {
                pending += delta;
                await flush();
              },
            },
            signal,
          );
        };
        let action: JsonObject;
        try {
          action = await execute();
        } catch (error) {
          if (
            error instanceof SolveaHttpError &&
            [401, 403].includes(error.status) &&
            !pending &&
            (await this.store.read(profileId, testRunId)).turns[index]!.assistant === ""
          )
            action = await execute(true);
          else throw error;
        }
        await flush(true);
        const result = actionResult(action);
        const evaluation = evaluateRouting(turn.expected, result.routing);
        chatId = result.chatId ?? chatId;
        const completed = await this.store.update(profileId, testRunId, (value) => {
          const current = value.turns[index]!;
          if (!current.assistant && result.content) current.assistant = result.content;
          current.messageId = result.messageId;
          current.outcome = result.outcome;
          current.routing = result.routing;
          current.evaluation = evaluation;
          current.completedAt = Date.now();
          current.status = result.failed ? "failed" : "succeeded";
          current.error = result.error;
          value.chatId = chatId;
          if (result.node) {
            value.failedNodeId = result.node.id;
            value.failedNodeTitle = result.node.title;
          }
        });
        if (result.failed) {
          await this.fail(completed, result.error ?? "Agent execution failed");
          return;
        }
      }
      await this.store.update(profileId, testRunId, (value) => {
        value.status = "succeeded";
        const verdicts = value.turns.map((turn) => turn.evaluation?.verdict);
        value.verdict = verdicts.includes("FAIL")
          ? "FAIL"
          : verdicts.includes("PASS")
            ? "PASS"
            : "UNJUDGED";
        value.completedAt = Date.now();
      });
    } catch (error) {
      const cancelled =
        signal.aborted || (error instanceof DOMException && error.name === "AbortError");
      const latest = await this.store.read(profileId, testRunId);
      await this.store.update(profileId, testRunId, (value) => {
        value.status = cancelled ? "cancelled" : "failed";
        value.error = cancelled
          ? "Test cancelled"
          : error instanceof Error
            ? error.message
            : String(error);
        value.completedAt = Date.now();
        const running = value.turns.find((turn) => turn.status === "running");
        if (running) {
          running.status = cancelled ? "cancelled" : "failed";
          running.error = value.error;
          running.completedAt = Date.now();
        }
      });
      if (latest.status === "succeeded") return;
    }
  }

  private assertIdentity(snapshot: LiveTestSnapshot, session: Session) {
    if (
      session.runtimeContext?.contextId !== snapshot.contextId ||
      session.runtimeContext.profileId !== snapshot.profileId ||
      session.tenant?.accountId !== snapshot.accountId
    )
      throw new Error("tenant context changed while LiveTest was running");
  }

  private async fail(snapshot: LiveTestSnapshot, error: string) {
    await this.store.update(snapshot.profileId, snapshot.testRunId, (value) => {
      value.status = "failed";
      value.error = error;
      value.completedAt = Date.now();
    });
  }
}
