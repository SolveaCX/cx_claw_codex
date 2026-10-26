import { describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";

const hook = new URL("../hooks/auth-status-continue.mjs", import.meta.url);

function runHook(command: string, output: unknown) {
  const result = spawnSync(process.execPath, [hook.pathname], {
    input: JSON.stringify({
      hook_event_name: "PostToolUse",
      tool_name: "Bash",
      tool_input: { command },
      tool_response: output,
    }),
    encoding: "utf8",
  });
  if (result.status !== 0) throw new Error(result.stderr);
  return JSON.parse(result.stdout) as { decision?: string; reason?: string };
}

describe("authorization status PostToolUse hook", () => {
  test("continues into automatic authorization after a logged-out status", () => {
    const result = runHook(
      'node "/plugins/cxclaw/plugin-cli.mjs" auth status --pretty',
      { output: '{"ok":true,"loggedIn":false}' },
    );

    expect(result.decision).toBe("block");
    expect(result.reason).toContain("auth ensure");
    expect(result.reason).toContain("不要再次向用户申请");
  });

  test("does not affect logged-in or unrelated commands", () => {
    expect(runHook(
      'node "/plugins/cxclaw/plugin-cli.mjs" auth status --pretty',
      { output: '{"ok":true,"loggedIn":true}' },
    )).toEqual({});
    expect(runHook("git status", { output: "clean" })).toEqual({});
  });
});
