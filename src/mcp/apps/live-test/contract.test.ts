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

test("attachment input accepts attachment-only turns and rejects metadata shortcuts", () => {
  const attachments = ["https://example.com/receipt.jpg"];
  for (const input of [{ attachments }, { case: { turns: [{ attachments }] } }]) {
    expect(LiveTestStartInputSchema.safeParse({ contextId: "ctx", ...input }).success).toBe(true);
  }
  for (const input of [
    { message: " " },
    { attachments: [" "] },
    { case: { turns: [{ message: "" }] } },
    { case: { turns: [{ message: "hi" }] }, attachments },
    { message: "hi", metadata: { attachments } },
    { message: "hi", metadata: { __attachments: attachments } },
  ]) {
    expect(LiveTestStartInputSchema.safeParse({ contextId: "ctx", ...input }).success).toBe(false);
  }
});
