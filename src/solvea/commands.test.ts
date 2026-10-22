import { describe, expect, test } from "bun:test";
import { isNativeSolveaCommand } from "./commands.js";

describe("native Solvea command registry", () => {
  test("keeps migrated API commands explicit", () => {
    expect(isNativeSolveaCommand("get-agent")).toBe(true);
    expect(isNativeSolveaCommand("update-intent")).toBe(true);
    expect(isNativeSolveaCommand("list-voice-agents")).toBe(false);
    expect(isNativeSolveaCommand("unknown-command")).toBe(false);
  });
});
