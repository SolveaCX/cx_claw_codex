import * as Dialog from "@radix-ui/react-dialog";
import * as Progress from "@radix-ui/react-progress";
import * as Tooltip from "@radix-ui/react-tooltip";
import { useCallback, useEffect, useMemo, useState } from "react";
import { app, callTool, useBridgeState } from "../shared/bridge.js";

type Turn = {
  index: number;
  user: string;
  assistant: string;
  status: string;
  error?: string;
  startedAt?: number;
  completedAt?: number;
};
type Snapshot = {
  testRunId: string;
  contextId: string;
  status: string;
  revision: number;
  agentName?: string;
  agentId: number;
  chatId?: string;
  error?: string;
  turns: Turn[];
};
const terminal = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export function LiveTestApp() {
  const bridge = useBridgeState();
  const initial = (bridge.output?.snapshot ?? bridge.output) as Snapshot | undefined;
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [error, setError] = useState<string>();
  const [transcript, setTranscript] = useState<unknown>();
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
  const progress = useMemo(
    () =>
      snapshot
        ? Math.round(
            (snapshot.turns.filter(
              (turn) => terminal.has(turn.status) || turn.status === "succeeded",
            ).length /
              snapshot.turns.length) *
              100,
          )
        : 0,
    [snapshot],
  );
  if (!snapshot)
    return <main className="font-app-sans text-app-muted p-5">正在连接 LiveTest…</main>;
  const cancel = async () => {
    const output = await callTool("live_test.cancel", {
      contextId: snapshot.contextId,
      testRunId: snapshot.testRunId,
    });
    if (output?.snapshot) setSnapshot(output.snapshot as Snapshot);
  };
  const loadTranscript = async () => {
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
      <main className="bg-app-background text-app-foreground font-app-sans p-4">
        <header className="flex items-start justify-between gap-3">
          <div>
            <p className="text-app-muted text-xs font-semibold uppercase">Agent LiveTest</p>
            <h1 className="mt-1 text-lg font-semibold">
              {snapshot.agentName ?? `Agent ${snapshot.agentId}`}
            </h1>
            <p className="text-app-muted mt-1 font-mono text-xs">{snapshot.testRunId}</p>
          </div>
          <span className="bg-app-surface border-app-border rounded-full border px-3 py-1 text-xs font-semibold">
            {snapshot.status}
          </span>
        </header>
        <Progress.Root
          className="bg-app-surface mt-4 h-2 overflow-hidden rounded-full"
          value={progress}
        >
          <Progress.Indicator
            className="bg-app-ring h-full transition-transform"
            style={{ transform: `translateX(-${100 - progress}%)` }}
          />
        </Progress.Root>
        {(snapshot.error || error || bridge.error) && (
          <p className="text-app-danger mt-3 text-sm">{snapshot.error ?? error ?? bridge.error}</p>
        )}
        <section className="mt-4 space-y-3">
          {snapshot.turns.map((turn) => (
            <article
              className="border-app-border bg-app-surface rounded-xl border p-3"
              key={turn.index}
            >
              <div className="text-app-muted flex justify-between text-xs">
                <span>第 {turn.index + 1} 轮</span>
                <span>{turn.status}</span>
              </div>
              <p className="mt-2 text-sm font-medium">{turn.user}</p>
              {turn.assistant && (
                <p className="mt-2 whitespace-pre-wrap text-sm">{turn.assistant}</p>
              )}
              {turn.error && <p className="text-app-danger mt-2 text-sm">{turn.error}</p>}
            </article>
          ))}
        </section>
        <footer className="mt-4 flex flex-wrap gap-2">
          <button
            className="border-app-border bg-app-surface rounded-lg border px-3 py-2 text-sm"
            onClick={() => void refresh().catch(() => undefined)}
          >
            刷新
          </button>
          {!terminal.has(snapshot.status) && (
            <button
              className="border-app-border bg-app-surface rounded-lg border px-3 py-2 text-sm"
              onClick={cancel}
            >
              取消
            </button>
          )}
          <Dialog.Root>
            <Dialog.Trigger asChild>
              <button
                className="border-app-border bg-app-surface rounded-lg border px-3 py-2 text-sm"
                disabled={!snapshot.chatId}
                onClick={loadTranscript}
              >
                执行详情
              </button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 bg-black/40" />
              <Dialog.Content className="bg-app-background text-app-foreground border-app-border fixed top-1/2 left-1/2 max-h-[80vh] w-[min(90vw,720px)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-xl border p-4 shadow-xl">
                <Dialog.Title className="font-semibold">LiveTest 执行详情</Dialog.Title>
                <pre className="mt-3 whitespace-pre-wrap font-mono text-xs">
                  {transcript ? JSON.stringify(transcript, null, 2) : "加载中…"}
                </pre>
                <Dialog.Close className="border-app-border bg-app-surface mt-4 rounded-lg border px-3 py-2 text-sm">
                  关闭
                </Dialog.Close>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button
                className="border-app-border bg-app-surface rounded-lg border px-3 py-2 text-sm"
                disabled={!snapshot.chatId}
                onClick={analyze}
              >
                让 Codex 分析
              </button>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content className="bg-app-foreground text-app-background rounded px-2 py-1 text-xs">
                把测试标识发送到当前对话
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </footer>
      </main>
    </Tooltip.Provider>
  );
}
