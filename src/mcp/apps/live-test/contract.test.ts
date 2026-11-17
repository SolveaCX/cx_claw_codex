import { describe, expect, test } from "bun:test";
import { LiveTestStartInputSchema, LiveTestStatusInputSchema } from "./contract.js";

describe("LiveTestStartInputSchema", () => {
  const caseInput = { turns: [{ message: "Where is my order?" }] };

  test("accepts END_TO_END without a fixed Agent", () => {
    expect(
      LiveTestStartInputSchema.safeParse({
        contextId: "ctx_current",
        testScope: "END_TO_END",
        case: caseInput,
      }).success,
    ).toBe(true);
  });

  test("rejects routing overrides in END_TO_END", () => {
    expect(
      LiveTestStartInputSchema.safeParse({
        contextId: "ctx_current",
        testScope: "END_TO_END",
        agentId: 9,
        flowVersion: 17,
        case: caseInput,
      }).success,
    ).toBe(false);
  });

  test("keeps legacy agent calls valid", () => {
    expect(
      LiveTestStartInputSchema.safeParse({
        contextId: "ctx_current",
        agentId: 9,
        case: caseInput,
      }).success,
    ).toBe(true);
  });
});

describe("LiveTestStatusInputSchema", () => {
  const baseInput = { contextId: "ctx_current", testRunId: "run_current" };

  test("accepts a 30 second long poll", () => {
    expect(LiveTestStatusInputSchema.safeParse({ ...baseInput, waitMs: 30_000 }).success).toBe(
      true,
    );
  });

  test("rejects a long poll above 30 seconds", () => {
    expect(LiveTestStatusInputSchema.safeParse({ ...baseInput, waitMs: 30_001 }).success).toBe(
      false,
    );
  });
});
