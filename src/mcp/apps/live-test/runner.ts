import { resolveRuntimeSession } from "../../../runtime/session.js";
import { SolveaClient, SolveaHttpError } from "../../../solvea/client.js";
import type { Session } from "../../../types.js";
import type { LiveTestSnapshot, LiveTestStartInput } from "./contract.js";
import { LiveTestStore } from "./store.js";

type JsonObject = Record<string, unknown>;
const protectedMetadata = new Set([
  "specified_agent_id",
  "specified_flow_version",
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
  const reasonList = Array.isArray(action.reasonList) ? action.reasonList.map(String) : [];
  const node = failedNode(action);
  const failed =
    action.reason === "SYSTEM_ERROR" || reasonList.includes("SYSTEM_ERROR") || Boolean(node);
  return {
    chatId: stringValue(action.chatId, object(action.chat)?.id),
    messageId: stringValue(action.messageId, action.id),
    content: stringValue(action.content, action.message, data?.content) ?? "",
    outcome: {
      actionType: stringValue(action.actionType, data?.actionType),
      handoff:
        action.handoff === true ||
        data?.handoff === true ||
        ["TO_AGENT", "TRANSFER_TO_AGENT"].includes(
          stringValue(action.actionType, data?.actionType)?.toUpperCase() ?? "",
        ),
      reason: stringValue(action.reason, data?.reason),
      reasonDesc: stringValue(action.reasonDesc, data?.reasonDesc),
      explain: stringValue(action.explain, data?.explain),
    },
    failed,
    node,
    error:
      node?.error ??
      (failed
        ? (stringValue(action.message, action.error) ?? "Agent execution failed")
        : undefined),
  };
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
      const agent = firstObject(await initialClient.getAgent(String(input.agentId)));
      if (!agent) throw new Error(`Agent ${input.agentId} not found`);
      const botId = input.botId ?? Number(await initialClient.botId());
      const flowVersion =
        input.flowVersion ??
        resolveFlowVersion(await initialClient.getChatflowGraph(String(input.agentId)), agent);
      if (!Number.isSafeInteger(flowVersion)) throw new Error("unable to resolve Chatflow version");
      await this.store.update(profileId, testRunId, (value) => {
        value.status = "running";
        value.agentName = stringValue(agent.name, agent.title);
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
        const payload: JsonObject = {
          botId,
          chatId,
          touchPoint: input.touchPoint,
          message: turn.user,
          metadata: {
            ...filtered(input.metadata, protectedMetadata),
            specified_agent_id: input.agentId,
            specified_flow_version: flowVersion,
            show_chat_flow: true,
          },
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
        chatId = result.chatId ?? chatId;
        const completed = await this.store.update(profileId, testRunId, (value) => {
          const current = value.turns[index]!;
          if (!current.assistant && result.content) current.assistant = result.content;
          current.messageId = result.messageId;
          current.outcome = result.outcome;
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
