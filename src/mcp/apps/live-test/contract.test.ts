import { describe, expect, test } from "bun:test";
import { LiveTestStatusInputSchema } from "./contract.js";

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
