import { describe, expect, test } from "bun:test";
import { SERVER_API_VERSION, TOOL_SCHEMA_VERSION, VERSION } from "./version.js";

describe("release metadata", () => {
  test("uses one semantic version", () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(TOOL_SCHEMA_VERSION).toBe("1");
    expect(SERVER_API_VERSION).toBe("1");
  });
});
