import { describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { withAuthWaitMarker } from "../runtime/auth-wait-state.mjs";

const hook = new URL("../hooks/auth-wait-guard.mjs", import.meta.url);

function runHook(sessionId: string) {
  const result = spawnSync(process.execPath, [hook.pathname], {
    input: JSON.stringify({ session_id: sessionId, hook_event_name: "Stop" }),
    encoding: "utf8",
  });
  if (result.status !== 0) throw new Error(result.stderr);
  return JSON.parse(result.stdout) as { decision?: string; reason?: string };
}

describe("authorization wait Stop hook", () => {
  test("continues the turn only while this Codex session is authorizing", async () => {
    const sessionId = `test-${randomUUID()}`;
    const otherSessionId = `test-${randomUUID()}`;

    await withAuthWaitMarker(async () => {
      expect(runHook(sessionId).decision).toBe("block");
      expect(runHook(sessionId).reason).toContain("继续读取");
      expect(runHook(otherSessionId)).toEqual({});
    }, { CODEX_SESSION_ID: sessionId });

    expect(runHook(sessionId)).toEqual({});
  });
});
