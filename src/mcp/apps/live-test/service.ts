import { resolveRuntimeSession } from "../../../runtime/session.js";
import { SolveaClient } from "../../../solvea/client.js";
import {
  TERMINAL_LIVE_TEST_STATUSES,
  type LiveTestSnapshot,
  type LiveTestStartInput,
} from "./contract.js";
import { LiveTestRunner } from "./runner.js";
import { LiveTestStore } from "./store.js";

type ActiveRun = { promise: Promise<void>; abortController: AbortController };

export class LiveTestService {
  readonly store: LiveTestStore;
  readonly runner: LiveTestRunner;
  private activeRuns = new Map<string, ActiveRun>();
  private activeContexts = new Map<string, string>();
  private ready: Promise<void>;

  constructor(store = new LiveTestStore()) {
    this.store = store;
    this.runner = new LiveTestRunner(store);
    this.ready = store.recoverAndCleanup();
  }

  async start(input: LiveTestStartInput) {
    await this.ready;
    const session = await resolveRuntimeSession(input.contextId, { minValiditySeconds: 150 });
    if (!session.runtimeContext || !session.tenant)
      throw new Error("tenant session is unavailable");
    if (this.activeContexts.has(input.contextId))
      throw new Error(`context ${input.contextId} already has an active LiveTest`);
    const turns = input.case?.turns.map((turn) => turn.message) ?? [input.message!];
    const snapshot = await this.store.create(
      {
        contextId: input.contextId,
        profileId: session.runtimeContext.profileId,
        accountId: session.tenant.accountId,
        environment: session.tenant.environment,
        agentId: input.agentId,
      },
      turns,
    );
    const abortController = new AbortController();
    const promise = this.runner.run(snapshot, input, abortController.signal).finally(() => {
      this.activeRuns.delete(snapshot.testRunId);
      if (this.activeContexts.get(input.contextId) === snapshot.testRunId)
        this.activeContexts.delete(input.contextId);
    });
    this.activeRuns.set(snapshot.testRunId, { promise, abortController });
    this.activeContexts.set(input.contextId, snapshot.testRunId);
    return { testRunId: snapshot.testRunId, snapshot };
  }

  private async owned(contextId: string, testRunId: string) {
    const session = await resolveRuntimeSession(contextId);
    if (!session.runtimeContext || !session.tenant)
      throw new Error("tenant session is unavailable");
    const snapshot = await this.store.read(session.runtimeContext.profileId, testRunId);
    if (
      snapshot.contextId !== contextId ||
      snapshot.profileId !== session.runtimeContext.profileId ||
      snapshot.accountId !== session.tenant.accountId
    )
      throw new Error("LiveTest does not belong to the current tenant context");
    return { session, snapshot };
  }

  async status(contextId: string, testRunId: string, afterRevision?: number, waitMs = 0) {
    const deadline = Date.now() + waitMs;
    const owned = await this.owned(contextId, testRunId);
    let snapshot = owned.snapshot;
    while (true) {
      if (
        afterRevision === undefined ||
        snapshot.revision > afterRevision ||
        TERMINAL_LIVE_TEST_STATUSES.has(snapshot.status) ||
        Date.now() >= deadline
      )
        return { snapshot };
      await new Promise((resolve) => setTimeout(resolve, Math.min(100, deadline - Date.now())));
      snapshot = await this.store.read(snapshot.profileId, testRunId);
    }
  }

  async cancel(contextId: string, testRunId: string) {
    const { snapshot } = await this.owned(contextId, testRunId);
    this.activeRuns
      .get(testRunId)
      ?.abortController.abort(new DOMException("Cancelled", "AbortError"));
    if (!this.activeRuns.has(testRunId) && !TERMINAL_LIVE_TEST_STATUSES.has(snapshot.status))
      await this.store.update(snapshot.profileId, testRunId, (value) => {
        value.status = "cancelled";
        value.error = "Test cancelled";
        value.completedAt = Date.now();
      });
    return this.status(contextId, testRunId);
  }

  async transcript(contextId: string, testRunId: string) {
    const { session, snapshot } = await this.owned(contextId, testRunId);
    if (!snapshot.chatId) throw new Error("LiveTest has no chatId yet");
    return {
      testRunId,
      chatId: snapshot.chatId,
      transcript: await new SolveaClient(session).transcript(snapshot.chatId),
    };
  }
}
