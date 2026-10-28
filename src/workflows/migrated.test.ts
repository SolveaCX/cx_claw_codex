import { describe, expect, test } from "bun:test";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { runAgentBuilder, validateGraph } from "./agent-builder.js";
import { compileChatflowSource } from "./chatflow-compiler.js";
import { runDelivery, runPoc } from "./delivery.js";
import { runKbBuilder } from "./kb-builder.js";

describe("TypeScript workflow migrations", () => {
  test("validates graph structure without a tenant session", () => {
    expect(validateGraph({ nodes: [{ id: "start", type: "START" }], edges: [] }).valid).toBe(false);
    expect(validateGraph({ nodes: [{ id: "a" }, { id: "a" }], edges: [] }).valid).toBe(false);
  });

  test("compiles a new chatflow source without requiring a pre-existing graph", () => {
    const graph = compileChatflowSource({
      entry: "router",
      nodes: [
        { key: "router", type: "intent", intents: [{ id: "refund", name: "Refund_Request", desc: "refund request" }] },
        { key: "reject", type: "reply", reply_type: "DYNAMIC_TEMPLATE", template_content: "拒绝退款" },
      ],
      edges: [
        { from: "router", on: "refund", to: "reject" },
        { from: "router", on: "OTHER", to: "$finish" },
        { from: "reject", to: "$finish" },
      ],
    });
    expect(validateGraph(graph)).toMatchObject({ valid: true, nodeCount: 4, edgeCount: 4 });
    expect(graph.nodes.map(node => (node.data as { category: string }).category)).toEqual(["INTENT", "REPLY", "START", "FINISH"]);
    const intent = graph.nodes.find(node => (node.data as { category: string }).category === "INTENT")!;
    expect(((intent.data as any).config.intents)[0]).toEqual({ id: "refund", name: "Refund_Request", desc: "refund request", intentId: null, examples: [] });
  });

  test("rejects unsupported source nodes instead of writing a partial graph", () => {
    expect(() => compileChatflowSource({ entry: "x", nodes: [{ key: "x", type: "unknown" }], edges: [] })).toThrow("unsupported source node type");
  });

  test("matches solvea-kit contracts for process, selector, code, and subgraph nodes", () => {
    const graph = compileChatflowSource({
      entry: "process",
      nodes: [
        {
          key: "process", type: "variable_process", use_chat_history: true,
          variables: [{ alias: "order_no_value", name: "order_no", describe: "Order number", type: "string" }],
          assignments: [{ id: "assign-order", operation: "OVER_WRITE", source: ["SELF", "order_no_value"], target: [["SYSTEM", "Custom", 301]], forceOverride: true }],
          additional_data: [{ system: { category: "Custom", field_id: 301 } }],
        },
        { key: "code", type: "code", inputs: [{ field_name: "order_no", variable_selector: { extract: "process", alias: "order_no_value" } }], source_code: "return {'normalized': inputs.order_no}", outputs: [{ field_name: "normalized", field_type: "String" }] },
        { key: "child_flow", type: "sub_graph", target_agent_id: 2496, context_turn_limit: 3 },
      ],
      edges: [{ from: "process", to: "code" }, { from: "code", to: "child_flow" }],
    });
    const process = graph.nodes.find(node => (node.data as any).category === "VARIABLE_PROCESS")!;
    const code = graph.nodes.find(node => (node.data as any).category === "CODE")!;
    const subgraph = graph.nodes.find(node => (node.data as any).category === "SUB_GRAPH")!;
    const processConfig = (process.data as any).config.variableProcess;
    expect(processConfig.additionalData).toEqual([["SYSTEM", "Custom", 301]]);
    expect(processConfig.assignments[0].source).toEqual(["SELF", processConfig.extracts[0].id]);
    expect((code.data as any).config.code.inputs[0].variableSelector).toEqual(["EXTRACT", process.id, processConfig.extracts[0].id]);
    expect((subgraph.data as any).config.subGraph).toEqual({ targetAgentId: 2496, contextTurnLimit: 3 });
  });

  test("enforces solvea-kit graph completeness and code safety", () => {
    expect(() => compileChatflowSource({ entry: "ask", nodes: [{ key: "ask", type: "question", mode: "USER_REPLY", question: "Continue?", replies: ["Yes"] }], edges: [{ from: "ask", on: "Yes", to: "$finish" }] })).toThrow("missing OTHER edge");
    expect(() => compileChatflowSource({ entry: "code", nodes: [{ key: "code", type: "code", source_code: "import os\nreturn {}", outputs: [{ field_name: "result" }] }], edges: [{ from: "code", to: "$finish" }] })).toThrow("forbidden Python operations");
  });

  test("compile creates the target graph file and deploy preview performs no request", async () => {
    await mkdir("_tmp_", { recursive: true });
    const prefix = `_tmp_/chatflow-${Date.now()}`;
    const sourceFile = `${prefix}-source.json`;
    const graphFile = `${prefix}-graph.json`;
    await writeFile(sourceFile, JSON.stringify({
      entry: "reply",
      nodes: [{ key: "reply", type: "reply", reply_type: "DYNAMIC_TEMPLATE", template_content: "ok" }],
      edges: [{ from: "reply", to: "$finish" }],
    }));
    await rm(graphFile, { force: true });
    await runAgentBuilder(undefined, "chatflow", ["compile", "--source-file", sourceFile, "--graph-file", graphFile]);
    expect(JSON.parse(await readFile(graphFile, "utf8"))).toHaveProperty("nodes");

    const session = {
      accessToken: "access", refreshToken: "refresh", accessExpiry: Date.now() / 1000 + 300,
      employeeId: "employee", email: "user@example.test", channel: "dev" as const,
      tenant: {
        accountId: 12, accountCode: "R53308", accountName: "test", environment: "prod",
        purpose: "test", context: "tenant-context", businessToken: "business-token",
        businessUrl: "https://example.test", expiresAt: Date.now() + 300_000,
      },
    };
    const preview = await runAgentBuilder(session, "chatflow", ["deploy", "--agent-name", "Refund", "--graph-file", graphFile, "--phase", "preview"]);
    expect(preview).toMatchObject({ phase: "preview", action: "deploy", environment: "prod", tenantId: 12, agentName: "Refund" });
    expect(preview).toHaveProperty("confirmationToken");
  });

  test("keeps delivery and POC state workflows local", async () => {
    const delivery = await runDelivery(undefined, "plan", ["--init"]);
    const poc = await runPoc(undefined, "classify", ["--no-excel"]);
    expect(delivery).toHaveProperty("status");
    expect(poc).toMatchObject({ domain: "poc", total: 0 });
  });

  test("builds a directory plan without Python or a tenant", async () => {
    await mkdir("_tmp_", { recursive: true });
    const input = `_tmp_/migrated-kb-${Date.now()}.json`;
    await writeFile(input, JSON.stringify({ pages: [{ title: "Help Center / Orders", url: "https://example.test/orders" }] }));
    const result = await runKbBuilder(undefined, "directory-plan", ["--crawl-result", input, "--output", `${input}.plan.json`]);
    expect(result).toMatchObject({ directories: 1, pages: 1 });
  });
});
