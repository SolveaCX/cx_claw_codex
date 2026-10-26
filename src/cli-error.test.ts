import { describe, expect, test } from "bun:test";
import { errorOutput, notAuthenticated } from "./cli-error.js";

describe("CLI error protocol", () => {
  test("serializes authentication recovery without credentials", () => {
    const output = errorOutput(notAuthenticated());

    expect(output).toEqual({
      error: {
        code: 3,
        category: "auth",
        message: "CXClaw 尚未登录",
        reason: "not_authenticated",
        retryable: false,
        hint: "运行 cxclawctl auth login 完成钉钉授权",
        actions: ["cxclawctl auth login"],
      },
    });
    expect(JSON.stringify(output)).not.toContain("token");
  });

  test("uses a stable envelope for other failures", () => {
    expect(errorOutput(new Error("boom"))).toEqual({
      error: {
        code: 1,
        category: "internal",
        message: "boom",
        reason: "command_failed",
        retryable: false,
      },
    });
  });
});
