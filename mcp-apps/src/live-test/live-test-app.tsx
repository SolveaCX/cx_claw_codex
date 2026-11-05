import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { app, callTool, useBridgeState } from "../shared/bridge.js";
import { normalizeTrace, type TraceStep } from "./trace.js";

type Outcome = {
  actionType?: string;
  handoff?: boolean;
  reason?: string;
  reasonDesc?: string;
  explain?: string;
};
type Turn = {
  index: number;
  user: string;
  assistant: string;
  status: string;
  error?: string;
  startedAt?: number;
  completedAt?: number;
  messageId?: string;
  outcome?: Outcome;
};
type Snapshot = {
  testRunId: string;
  contextId: string;
  status: string;
  revision: number;
  agentName?: string;
  agentId: number;
  botId?: number;
  flowVersion?: number;
  chatId?: string;
  error?: string;
  failedNodeTitle?: string;
  truncated?: boolean;
  turns: Turn[];
};
const terminal = new Set(["succeeded", "failed", "cancelled", "interrupted"]);
const completedTurn = new Set(["succeeded", "failed", "cancelled"]);
const statusLabel: Record<string, string> = {
  queued: "准备中",
  resolving: "准备中",
  running: "运行中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

function ExperimentIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 3h6M10 3v5.2l-5.6 8.6A2.7 2.7 0 0 0 6.7 21h10.6a2.7 2.7 0 0 0 2.3-4.2L14 8.2V3M7.3 14h9.4" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg className={open ? "lt-chevron lt-chevron-open" : "lt-chevron"} viewBox="0 0 16 16">
      <path d="m6 3 5 5-5 5" />
    </svg>
  );
}

function CopyIcon({ checked }: { checked: boolean }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      {checked ? <path d="m3 8 3 3 7-7" /> : <path d="M6 5V3h7v7h-2M3 6h7v7H3z" />}
    </svg>
  );
}

function formatDuration(turn: Turn) {
  if (!turn.startedAt) return undefined;
  const end = turn.completedAt ?? Date.now();
  return `${Math.max(0, (end - turn.startedAt) / 1000).toFixed(1)}s`;
}

function terminalOutcome(outcome?: Outcome) {
  const actionType = outcome?.actionType?.toUpperCase();
  const detail = outcome?.reasonDesc ?? outcome?.explain ?? outcome?.reason;
  if (outcome?.handoff || actionType === "TO_AGENT" || actionType === "TRANSFER_TO_AGENT")
    return { title: "已转人工", detail: detail ?? "本轮不发送机器人回复", tone: "handoff" };
  if (actionType === "NO_REPLY") return { title: "无需回复", detail, tone: "terminal" };
  if (actionType === "NOTHING" || actionType === "DO_NOTHING")
    return { title: "无需执行操作", detail, tone: "terminal" };
  return undefined;
}

function displayJson(value: unknown) {
  if (value == null || value === "") return "—";
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function Modal({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="lt-dialog-overlay" />
        <Dialog.Content className="lt-dialog-content">
          <div className="lt-dialog-header">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="lt-icon-button" aria-label="关闭">
              ×
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function MessageRow({
  role,
  turn,
  failedNodeTitle,
  onExecution,
}: {
  role: "user" | "assistant";
  turn: Turn;
  failedNodeTitle?: string;
  onExecution: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const isUser = role === "user";
  const running = !isUser && turn.status === "running";
  const failed = !isUser && turn.status === "failed";
  const outcome = !isUser && !running && !failed ? terminalOutcome(turn.outcome) : undefined;
  const copy = async () => {
    await navigator.clipboard.writeText(turn.assistant);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className={isUser ? "lt-message-row lt-user-row" : "lt-message-row"}>
      <div className={isUser ? "lt-avatar lt-user-avatar" : "lt-avatar"}>{isUser ? "U" : "AI"}</div>
      <div className="lt-message-content">
        <div className="lt-message-stack">
          <div
            className={`lt-bubble ${
              isUser
                ? "lt-user-bubble"
                : failed
                  ? "lt-error-bubble"
                  : outcome
                    ? `lt-${outcome.tone}-bubble`
                    : "lt-assistant-bubble"
            }`}
          >
            {isUser ? (
              turn.user
            ) : running && !turn.assistant ? (
              <span className="lt-dots" aria-label="等待 Agent 回复">
                <span />
                <span />
                <span />
              </span>
            ) : failed ? (
              <span className="lt-message-state">
                <strong>本轮执行失败</strong>
                <span>{turn.error ?? "Agent 未返回有效回复"}</span>
                {failedNodeTitle ? <code>{failedNodeTitle}</code> : null}
              </span>
            ) : outcome && !turn.assistant ? (
              <span className="lt-message-state">
                <strong>{outcome.title}</strong>
                {outcome.detail ? <span>{outcome.detail}</span> : null}
              </span>
            ) : (
              <span className="lt-answer">{turn.assistant || " "}</span>
            )}
          </div>
          {!isUser ? (
            <div className="lt-message-actions">
              {turn.startedAt ? <span>{formatDuration(turn)}</span> : null}
              {turn.outcome?.handoff && turn.assistant ? (
                <span className="lt-handoff-label">已转人工</span>
              ) : null}
              {turn.messageId ? (
                <button className="lt-trace-button" type="button" onClick={onExecution}>
                  执行详情
                </button>
              ) : null}
              {turn.assistant ? (
                <button
                  className="lt-copy-button"
                  type="button"
                  aria-label={copied ? "已复制" : "复制回复"}
                  title={copied ? "已复制" : "复制回复"}
                  onClick={() => void copy()}
                >
                  <CopyIcon checked={copied} />
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function TraceStepView({ step }: { step: TraceStep }) {
  const [open, setOpen] = useState(step.status === "failed");
  const status = step.status === "failed" ? "失败" : step.status === "running" ? "运行中" : "完成";
  return (
    <div className={`lt-trace-step lt-trace-${step.status}`}>
      <button
        className="lt-trace-step-header"
        type="button"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="lt-trace-step-marker">
          {step.status === "failed" ? "!" : step.status === "running" ? "…" : "✓"}
        </span>
        <span className="lt-trace-step-title">{step.title}</span>
        {step.elapsed ? (
          <span className="lt-trace-step-time">{(step.elapsed / 1000).toFixed(1)}s</span>
        ) : null}
        <span className="lt-trace-step-status">{status}</span>
        <ChevronIcon open={open} />
      </button>
      {open ? (
        <div className="lt-trace-step-body">
          {step.input != null ? (
            <div>
              <span>输入</span>
              <pre>{displayJson(step.input)}</pre>
            </div>
          ) : null}
          {step.tools.map((tool, index) => (
            <div className="lt-trace-tool" key={`${tool.name}-${index}`}>
              <div className="lt-trace-tool-heading">
                <span>工具调用</span>
                <strong>{tool.name}</strong>
              </div>
              {tool.input != null ? <pre>{displayJson(tool.input)}</pre> : null}
              {tool.result != null ? (
                <>
                  <span>工具响应</span>
                  <pre>{displayJson(tool.result)}</pre>
                </>
              ) : null}
            </div>
          ))}
          {step.output != null ? (
            <div>
              <span>输出</span>
              <pre>{displayJson(step.output)}</pre>
            </div>
          ) : null}
          {step.error != null ? (
            <div className="lt-trace-error">
              <span>错误</span>
              <pre>{displayJson(step.error)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function LiveTestApp() {
  const bridge = useBridgeState();
  const initial = (bridge.output?.snapshot ?? bridge.output) as Snapshot | undefined;
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [error, setError] = useState<string>();
  const [transcript, setTranscript] = useState<unknown>();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [expanded, setExpanded] = useState(true);
  useEffect(() => {
    if (initial?.testRunId) setSnapshot(initial);
  }, [initial?.revision, initial?.testRunId]);

  const refresh = useCallback(async () => {
    if (!snapshot) return;
    try {
      const output = await callTool("live_test.status", {
        contextId: snapshot.contextId,
        testRunId: snapshot.testRunId,
        waitMs: 0,
      });
      if (output?.snapshot) setSnapshot(output.snapshot as Snapshot);
      setError(undefined);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    }
  }, [snapshot?.contextId, snapshot?.testRunId]);

  useEffect(() => {
    if (!snapshot || terminal.has(snapshot.status)) return;
    let stopped = false;
    let delay = 1000;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (stopped) return;
      if (document.hidden) {
        timer = setTimeout(poll, 1000);
        return;
      }
      try {
        await refresh();
        delay = 1000;
      } catch {
        delay = Math.min(delay * 2, 8000);
      }
      timer = setTimeout(poll, delay);
    };
    timer = setTimeout(poll, 1000);
    const visible = () => {
      if (!document.hidden) void refresh().catch(() => undefined);
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [snapshot?.status, snapshot?.testRunId, refresh]);

  const completed = useMemo(
    () => snapshot?.turns.filter((turn) => completedTurn.has(turn.status)).length ?? 0,
    [snapshot?.turns],
  );
  const traceSteps = useMemo(() => normalizeTrace(transcript), [transcript]);

  if (!snapshot)
    return (
      <main className="lt-shell">
        <div className="lt-card lt-loading-card">正在连接 LiveTest…</div>
      </main>
    );

  const total = snapshot.turns.length;
  const running = !terminal.has(snapshot.status);
  const failed = ["failed", "interrupted", "cancelled"].includes(snapshot.status);
  const preparing = ["queued", "resolving"].includes(snapshot.status);
  const touchPoint = String(bridge.input.touchPoint ?? "LIVE_CHAT")
    .replaceAll("_", "")
    .toUpperCase();
  const metadata = bridge.input.metadata ?? {};
  const version =
    snapshot.flowVersion == null
      ? "—"
      : snapshot.flowVersion < 0
        ? `草稿 v${snapshot.flowVersion}`
        : `发布 v${snapshot.flowVersion}`;
  const visibleTurns = snapshot.turns.filter((turn) => turn.status !== "queued");

  const cancel = async () => {
    const output = await callTool("live_test.cancel", {
      contextId: snapshot.contextId,
      testRunId: snapshot.testRunId,
    });
    if (output?.snapshot) setSnapshot(output.snapshot as Snapshot);
  };
  const loadTranscript = async () => {
    setDetailsOpen(true);
    if (transcript) return;
    const output = await callTool("live_test.transcript", {
      contextId: snapshot.contextId,
      testRunId: snapshot.testRunId,
    });
    setTranscript(output?.transcript);
  };
  const analyze = () =>
    app.sendMessage({
      role: "user",
      content: [
        {
          type: "text",
          text: `请读取并分析 LiveTest ${snapshot.testRunId}（chatId=${snapshot.chatId ?? "pending"}）的 AgentAction。`,
        },
      ],
    });

  return (
    <Tooltip.Provider>
      <main className="lt-shell">
        <section className="lt-card">
          <header className="lt-header">
            <div className="lt-heading">
              <span className="lt-title-icon">
                <ExperimentIcon />
              </span>
              <div>
                <h1>Live Test</h1>
                <p>{preparing ? "正在准备测试" : `已完成 ${completed}/${total} 轮`}</p>
              </div>
            </div>
            <div className="lt-header-actions">
              <span
                className={`lt-status lt-status-${running ? "running" : failed ? "failed" : "completed"}`}
              >
                {running ? <i className="lt-spinner" /> : null}
                {statusLabel[snapshot.status] ?? snapshot.status}
              </span>
              <button
                className="lt-collapse-button"
                type="button"
                aria-expanded={expanded}
                aria-label={expanded ? "收起" : "展开"}
                onClick={() => setExpanded((value) => !value)}
              >
                <ChevronIcon open={expanded} />
              </button>
            </div>
          </header>

          <div className={`lt-body-reveal ${expanded ? "lt-body-reveal-open" : ""}`}>
            <div className="lt-body-clip">
              <div className="lt-progress" aria-label={`已完成 ${completed}/${total} 轮`}>
                {snapshot.turns.map((turn) => (
                  <span
                    key={turn.index}
                    className={
                      turn.status === "failed" || turn.status === "cancelled"
                        ? "lt-progress-failed"
                        : turn.status === "succeeded"
                          ? "lt-progress-completed"
                          : turn.status === "running"
                            ? "lt-progress-running"
                            : ""
                    }
                  />
                ))}
              </div>

              <div className="lt-context">
                <div>
                  <span>Agent</span>
                  <strong>
                    #{snapshot.agentId} {snapshot.agentName}
                  </strong>
                  <small>{version}</small>
                </div>
                <div>
                  <span>Channel</span>
                  <strong>{touchPoint}</strong>
                </div>
                <div>
                  <span>Bot</span>
                  <strong>{snapshot.botId ? `#${snapshot.botId}` : "—"}</strong>
                </div>
                <div>
                  <span>Metadata</span>
                  <button type="button" onClick={() => setMetadataOpen(true)}>
                    查看
                  </button>
                </div>
              </div>

              {preparing ? (
                <div className="lt-preparing">
                  <span className="lt-preparing-orbit">
                    <ExperimentIcon />
                  </span>
                  <span>
                    <strong>正在准备测试</strong>
                    <small>正在解析 Agent、Bot 和 Chatflow 版本</small>
                  </span>
                </div>
              ) : null}

              <div className="lt-messages">
                {visibleTurns.map((turn) => (
                  <div className="lt-turn" key={turn.index}>
                    <MessageRow role="user" turn={turn} onExecution={() => undefined} />
                    <MessageRow
                      role="assistant"
                      turn={turn}
                      failedNodeTitle={snapshot.failedNodeTitle}
                      onExecution={() => void loadTranscript()}
                    />
                  </div>
                ))}
              </div>

              {(snapshot.error || error || bridge.error) && (
                <div className="lt-error-summary">{snapshot.error ?? error ?? bridge.error}</div>
              )}

              <footer className="lt-footer">
                <span>
                  {completed} / {total}
                </span>
                <div className="lt-footer-actions">
                  <button type="button" onClick={() => void refresh().catch(() => undefined)}>
                    刷新
                  </button>
                  {running ? (
                    <button type="button" onClick={() => void cancel()}>
                      取消
                    </button>
                  ) : null}
                  {snapshot.chatId ? (
                    <button type="button" onClick={() => void loadTranscript()}>
                      执行详情
                    </button>
                  ) : null}
                  {snapshot.chatId ? (
                    <button type="button" onClick={analyze}>
                      让 Codex 分析
                    </button>
                  ) : null}
                  {snapshot.chatId ? (
                    <span className="lt-chat-id">Chat ID · {snapshot.chatId}</span>
                  ) : null}
                </div>
              </footer>
              {snapshot.truncated ? <div className="lt-notice">部分长内容已截断</div> : null}
            </div>
          </div>
        </section>
      </main>

      <Modal open={metadataOpen} onOpenChange={setMetadataOpen} title="Metadata">
        <pre className="lt-json">{JSON.stringify(metadata, null, 2)}</pre>
      </Modal>
      <Modal open={detailsOpen} onOpenChange={setDetailsOpen} title="LiveTest 执行详情">
        {transcript ? (
          <div className="lt-trace-panel">
            <div className="lt-trace-summary">
              <strong>Agent 执行过程</strong>
              <span>
                {traceSteps.length ? `${traceSteps.length} 个执行步骤` : "未发现可视化执行节点"}
              </span>
            </div>
            {traceSteps.length ? (
              traceSteps.map((step) => <TraceStepView key={step.id} step={step} />)
            ) : (
              <div className="lt-trace-empty">当前 transcript 没有返回 Chatflow 节点事件。</div>
            )}
            <details className="lt-raw-details">
              <summary>查看原始 transcript JSON</summary>
              <pre className="lt-json">{JSON.stringify(transcript, null, 2)}</pre>
            </details>
          </div>
        ) : (
          <div className="lt-trace-loading">正在加载执行过程…</div>
        )}
      </Modal>
    </Tooltip.Provider>
  );
}
