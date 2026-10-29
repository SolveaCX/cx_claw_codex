import { describe, expect, test } from "bun:test";
import { isResourceCommand, resolveResourceCommand, resourceCommandForImplementation, resourceHelp } from "./resources.js";

describe("resource command hierarchy", () => {
  test("maps readable resource actions to internal commands", () => {
    expect(resolveResourceCommand("intent", "create")).toBe("create-intent");
    expect(resolveResourceCommand("intent", "update")).toBe("update-intent");
    expect(resolveResourceCommand("intent", "toggle")).toBe("toggle-intent");
    expect(resolveResourceCommand("agent", "get-chatflow")).toBe("get-chatflow-graph");
    expect(resolveResourceCommand("field", "create")).toBe("create-managed-ai-field");
    expect(resolveResourceCommand("template", "delete")).toBe("delete-templates");
    expect(resolveResourceCommand("quality", "alerts")).toBe("list-quality-alert-rules");
    expect(() => resolveResourceCommand("analytics", "messages")).toThrow("implemented directly");
  });

  test("rejects unknown actions with discoverable help", () => {
    expect(() => resolveResourceCommand("intent", "remove")).toThrow("intent actions");
    expect(resourceHelp("intent")).toContain("create");
    expect(resourceHelp("intent")).toContain("toggle");
    expect(isResourceCommand("intent")).toBe(true);
    expect(isResourceCommand("api")).toBe(false);
  });

  test("documents action-specific arguments", () => {
    expect(resourceHelp("intent", "create")).toContain("cxclawctl intent create");
    expect(resourceHelp("intent", "create")).toContain("--data-file <path>");
    expect(resourceHelp("intent", "toggle")).toContain("--enable | --disable");
    expect(resourceHelp("analytics", "messages")).toContain("--start-date <YYYY-MM-DD>");
    expect(() => resourceHelp("intent", "remove")).toThrow("unknown intent action");
  });

  test("keeps migrated implementations behind resource-action command names", () => {
    expect(resourceCommandForImplementation("analytics-messages")).toBeUndefined();
    expect(resourceCommandForImplementation("get-agent")).toBe("agent get");
    expect(resourceCommandForImplementation("report-message")).toBeUndefined();
  });
});
