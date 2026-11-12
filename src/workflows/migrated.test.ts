import { describe, expect, test } from "bun:test";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { runAgentBuilder, validateGraph } from "./agent-builder.js";
import { compileChatflowSource } from "./chatflow-compiler.js";
import { runDelivery, runPoc } from "./delivery.js";
import { runKbBuilder } from "./kb-builder.js";
import { validateToolEdgeCompatibility, validateToolParameters } from "./chatflow-validator.js";

function toolRoutingGraph(enableActionStatus: boolean, sourceHandle: string): any {
  return {
    nodes: [
      { id: "start", data: { category: "START", title: "Start", config: {} } },
      {
        id: "tool",
        data: {
          category: "TOOL",
          title: "lookup",
          config: { tool: { id: 7, enableActionStatus } },
        },
      },
      { id: "finish", data: { category: "FINISH", title: "Finish", config: {} } },
    ],
    edges: [
      {
        id: "e1",
        source: "start",
        sourceHandle: "SOURCE",
        target: "tool",
        targetHandle: "TARGET",
        type: "default",
      },
      {
        id: "e2",
        source: "tool",
        sourceHandle,
        target: "finish",
        targetHandle: "TARGET",
        type: "default",
      },
    ],
    variables: [],
  };
}

describe("TypeScript workflow migrations", () => {
  test("validates graph structure without a tenant session", () => {
    expect(validateGraph({ nodes: [{ id: "start", type: "START" }], edges: [] }).valid).toBe(false);
    expect(validateGraph({ nodes: [{ id: "a" }, { id: "a" }], edges: [] }).valid).toBe(false);
  });

  test("ignores NOTE nodes and accepts legacy graphs without variables", () => {
    const graph = toolRoutingGraph(false, "SOURCE");
    delete graph.variables;
    graph.nodes.push({
      id: "note",
      type: "CUSTOM_NOTE",
      data: { category: "NOTE", title: "" },
    });

    expect(validateGraph(graph)).toMatchObject({ valid: true, errors: [] });
  });

  test("allows a terminal AGENT without a SOURCE edge", () => {
    const graph = {
      nodes: [
        { id: "start", data: { category: "START", config: {} } },
        {
          id: "agent",
          data: {
            category: "AGENT",
            title: "answer",
            config: {
              agentData: { prompt: "Answer", displayPrompt: "Answer", usedPlugins: [] },
            },
          },
        },
      ],
      edges: [
        {
          id: "e1",
          source: "start",
          sourceHandle: "SOURCE",
          target: "agent",
          targetHandle: "TARGET",
          type: "default",
        },
      ],
    };

    const result = validateGraph(graph);
    expect(result.valid).toBe(true);
    expect(result.warnings).toContain(
      "AGENT 'answer' has no SOURCE outbound edge — confirm it's a terminal node",
    );
  });

  test("accepts TOOL status edges and legacy empty SOURCE handles", () => {
    const graph = toolRoutingGraph(true, "OK");
    expect(validateGraph(graph)).toMatchObject({ valid: true });

    graph.nodes[1].data.config.tool.enableActionStatus = false;
    delete graph.edges[1].sourceHandle;
    expect(validateGraph(graph)).toMatchObject({ valid: true });
  });

  test("rejects TOOL edges that cannot match the configured routing mode", () => {
    const graph = toolRoutingGraph(true, "SOURCE");
    expect(validateGraph(graph).errors).toContain(
      "TOOL 'lookup' has no action-status outbound edge",
    );

    graph.nodes[1].data.config.tool.enableActionStatus = false;
    graph.edges[1].sourceHandle = "MADE_UP_STATUS";
    expect(validateGraph(graph).errors).toContain("TOOL 'lookup' missing SOURCE edge");
  });

  test("reports current plugin status drift as warnings for old graphs", () => {
    const graph = toolRoutingGraph(true, "OK");
    graph.edges.push({
      id: "e3",
      source: "tool",
      sourceHandle: "LEGACY_FAILURE",
      target: "finish",
      targetHandle: "TARGET",
      type: "default",
    });
    const plugin = {
      id: 7,
      meta: {
        externalHttpCallConfig: {
          actionStatuses: [{ name: "OK" }, { name: "FAILED" }],
        },
      },
    };
    expect(validateToolEdgeCompatibility(graph, [plugin])).toEqual({
      errors: [],
      warnings: [
        "TOOL 'lookup' has no edge for current action status(es): FAILED",
        "TOOL 'lookup' keeps legacy or unknown action status edge(s): LEGACY_FAILURE",
      ],
    });
  });

  test("requires HUMAN_REVIEW MESSAGE edge when midway messages are handled", () => {
    const graph = toolRoutingGraph(false, "SOURCE");
    graph.nodes[1].data.category = "HUMAN_REVIEW";
    graph.nodes[1].data.title = "review";
    graph.nodes[1].data.config = {
      humanReview: { method: "fill", description: "Review", midwayMessageStrategy: "handle" },
    };
    expect(validateGraph(graph).errors).toContain("HUMAN_REVIEW 'review' missing MESSAGE edge");
  });

  test("accepts fixed CUSTOMIZE tool parameters supplied by the plugin", () => {
    const graph: any = {
      nodes: [
        {
          id: "tool",
          data: {
            category: "TOOL",
            title: "Amazon_tracking",
            config: {
              tool: {
                id: 7,
                inputParams: [{ name: "order_ids", variableSelector: ["SYSTEM", "Order", 1] }],
              },
            },
          },
        },
      ],
    };
    const plugin = {
      id: 7,
      meta: {
        externalHttpCallConfig: {
          requestParam: {
            items: [
              {
                name: "client_id",
                required: true,
                source: "CUSTOMIZE",
                value: "configured-client-id",
              },
              {
                name: "client_secret",
                required: true,
                source: "CUSTOMIZE",
                value: "configured-client-secret",
              },
              { name: "order_ids", required: true, source: "LLM" },
            ],
          },
        },
      },
    };
    expect(validateToolParameters(graph, [plugin])).toEqual([]);

    graph.nodes[0].data.config.inputParams = graph.nodes[0].data.config.tool.inputParams;
    delete graph.nodes[0].data.config.tool.inputParams;
    expect(validateToolParameters(graph, [plugin])).toEqual([]);
  });

  test("reports missing fixed and nested required tool parameters", () => {
    const graph = {
      nodes: [
        {
          id: "tool",
          data: {
            category: "TOOL",
            title: "lookup",
            config: {
              tool: {
                id: 8,
                inputParams: [{ name: "address", children: [{ name: "city", text: "Seattle" }] }],
              },
            },
          },
        },
      ],
    };
    const plugin = {
      id: 8,
      meta: {
        externalHttpCallConfig: {
          requestParam: {
            items: [
              { name: "api_key", required: true, source: "CUSTOMIZE" },
              {
                name: "address",
                required: true,
                type: "object",
                objectItems: [{ name: "line1", required: true }],
              },
            ],
          },
        },
      },
    };
    expect(validateToolParameters(graph, [plugin])).toEqual([
      "TOOL 'lookup' required tool param 'api_key' is not configured",
      "TOOL 'lookup' required tool param 'address.line1' is not configured",
    ]);
  });

  test("compiles a new chatflow source without requiring a pre-existing graph", () => {
    const graph = compileChatflowSource({
      entry: "router",
      nodes: [
        {
          key: "router",
          type: "intent",
          intents: [{ id: "refund", name: "Refund_Request", desc: "refund request" }],
        },
        {
          key: "reject",
          type: "reply",
          reply_type: "DYNAMIC_TEMPLATE",
          template_content: "拒绝退款",
        },
      ],
      edges: [
        { from: "router", on: "refund", to: "reject" },
        { from: "router", on: "OTHER", to: "$finish" },
        { from: "reject", to: "$finish" },
      ],
    });
    expect(validateGraph(graph)).toMatchObject({ valid: true, nodeCount: 4, edgeCount: 4 });
    expect(graph.nodes.map((node) => (node.data as { category: string }).category)).toEqual([
      "INTENT",
      "REPLY",
      "START",
      "FINISH",
    ]);
    const intent = graph.nodes.find(
      (node) => (node.data as { category: string }).category === "INTENT",
    )!;
    expect((intent.data as any).config.intents[0]).toEqual({
      id: "refund",
      name: "Refund_Request",
      desc: "refund request",
      intentId: null,
      examples: [],
    });
  });

  test("rejects unsupported source nodes instead of writing a partial graph", () => {
    expect(() =>
      compileChatflowSource({ entry: "x", nodes: [{ key: "x", type: "unknown" }], edges: [] }),
    ).toThrow("unsupported source node type");
  });

  test("routes new AGENT handoff through a TRANSFER_TO_HUMAN next step", () => {
    const graph = compileChatflowSource({
      entry: "agent",
      nodes: [
        {
          key: "agent",
          type: "agent",
          prompt: "If the customer insists, use transfer_to_handoff_node.",
          next_steps: [
            {
              id: "HANDOFF",
              title: "handoff",
              prompt: "Use when human support is required.",
            },
          ],
        },
        { key: "handoff", type: "transfer", explain: "customer insists" },
      ],
      edges: [{ from: "agent", on: "HANDOFF", to: "handoff" }],
    });
    expect(validateGraph(graph)).toMatchObject({ valid: true });

    expect(() =>
      compileChatflowSource({
        entry: "agent",
        nodes: [
          { key: "agent", type: "agent", prompt: "Handle the request." },
          { key: "handoff", type: "transfer", explain: "customer insists" },
        ],
        edges: [{ from: "agent", to: "handoff" }],
      }),
    ).toThrow("must reach TRANSFER_TO_HUMAN through a declared handoff nextStep");
  });

  test("keeps legacy AGENT transferHuman tools compatible", () => {
    const graph = compileChatflowSource({
      entry: "agent",
      nodes: [
        {
          key: "agent",
          type: "agent",
          prompt:
            "Escalate with {#LibraryBlock tool_id=1790057523999 type=transferHuman name=need_specialist action=NOT_REPLY #}.",
          plugins: [-2],
        },
      ],
      edges: [{ from: "agent", to: "$finish" }],
    });
    const agent = graph.nodes.find(
      (node) => (node.data as { category: string }).category === "AGENT",
    )!;
    expect((agent.data as any).config.agentData.usedPlugins).toEqual([-2]);
    expect((agent.data as any).config.agentData.prompt).toContain(
      "Transfer_To_Agent (reason: need_specialist)",
    );
  });

  test("matches solvea-kit contracts for process, selector, code, and subgraph nodes", () => {
    const graph = compileChatflowSource({
      entry: "process",
      nodes: [
        {
          key: "process",
          type: "variable_process",
          use_chat_history: true,
          variables: [
            { alias: "order_no_value", name: "order_no", describe: "Order number", type: "string" },
          ],
          assignments: [
            {
              id: "assign-order",
              operation: "OVER_WRITE",
              source: ["SELF", "order_no_value"],
              target: [["SYSTEM", "Custom", 301]],
              forceOverride: true,
            },
          ],
          additional_data: [{ system: { category: "Custom", field_id: 301 } }],
        },
        {
          key: "code",
          type: "code",
          inputs: [
            {
              field_name: "order_no",
              variable_selector: { extract: "process", alias: "order_no_value" },
            },
          ],
          source_code: "return {'normalized': inputs.order_no}",
          outputs: [{ field_name: "normalized", field_type: "String" }],
        },
        { key: "child_flow", type: "sub_graph", target_agent_id: 2496, context_turn_limit: 3 },
      ],
      edges: [
        { from: "process", to: "code" },
        { from: "code", to: "child_flow" },
      ],
    });
    const process = graph.nodes.find((node) => (node.data as any).category === "VARIABLE_PROCESS")!;
    const code = graph.nodes.find((node) => (node.data as any).category === "CODE")!;
    const subgraph = graph.nodes.find((node) => (node.data as any).category === "SUB_GRAPH")!;
    const processConfig = (process.data as any).config.variableProcess;
    expect(processConfig.additionalData).toEqual([["SYSTEM", "Custom", 301]]);
    expect(processConfig.assignments[0].source).toEqual(["SELF", processConfig.extracts[0].id]);
    expect((code.data as any).config.code.inputs[0].variableSelector).toEqual([
      "EXTRACT",
      process.id,
      processConfig.extracts[0].id,
    ]);
    expect((subgraph.data as any).config.subGraph).toEqual({
      targetAgentId: 2496,
      contextTurnLimit: 3,
    });
  });

  test("enforces solvea-kit graph completeness and code safety", () => {
    expect(() =>
      compileChatflowSource({
        entry: "ask",
        nodes: [
          {
            key: "ask",
            type: "question",
            mode: "USER_REPLY",
            question: "Continue?",
            replies: ["Yes"],
          },
        ],
        edges: [{ from: "ask", on: "Yes", to: "$finish" }],
      }),
    ).toThrow("missing OTHER edge");
    expect(() =>
      compileChatflowSource({
        entry: "code",
        nodes: [
          {
            key: "code",
            type: "code",
            source_code: "import os\nreturn {}",
            outputs: [{ field_name: "result" }],
          },
        ],
        edges: [{ from: "code", to: "$finish" }],
      }),
    ).toThrow("forbidden Python operations");
  });

  test("compile creates the target graph file and deploy preview performs no request", async () => {
    await mkdir("_tmp_", { recursive: true });
    const prefix = `_tmp_/chatflow-${Date.now()}`;
    const sourceFile = `${prefix}-source.json`;
    const graphFile = `${prefix}-graph.json`;
    await writeFile(
      sourceFile,
      JSON.stringify({
        entry: "reply",
        nodes: [
          { key: "reply", type: "reply", reply_type: "DYNAMIC_TEMPLATE", template_content: "ok" },
        ],
        edges: [{ from: "reply", to: "$finish" }],
      }),
    );
    await rm(graphFile, { force: true });
    await runAgentBuilder(undefined, "chatflow", [
      "compile",
      "--source-file",
      sourceFile,
      "--graph-file",
      graphFile,
    ]);
    expect(JSON.parse(await readFile(graphFile, "utf8"))).toHaveProperty("nodes");

    const session = {
      accessToken: "access",
      refreshToken: "refresh",
      accessExpiry: Date.now() / 1000 + 300,
      employeeId: "employee",
      email: "user@example.test",
      channel: "dev" as const,
      tenant: {
        accountId: 12,
        accountCode: "R53308",
        accountName: "test",
        environment: "prod",
        purpose: "test",
        context: "tenant-context",
        businessToken: "business-token",
        businessUrl: "https://example.test",
        expiresAt: Date.now() + 300_000,
      },
      runtimeContext: { contextId: "ctx-preview", profileId: "tenant-12-prod" },
    };
    const preview = await runAgentBuilder(session, "chatflow", [
      "deploy",
      "--agent-name",
      "Refund",
      "--graph-file",
      graphFile,
      "--phase",
      "preview",
    ]);
    expect(preview).toMatchObject({
      phase: "preview",
      action: "deploy",
      environment: "prod",
      tenantId: 12,
      agentName: "Refund",
    });
    expect(preview).toHaveProperty("confirmationToken");
    const [tokenBody] = String((preview as { confirmationToken: string }).confirmationToken).split(
      ".",
    );
    const tokenPayload = JSON.parse(Buffer.from(tokenBody, "base64url").toString("utf8"));
    expect(tokenPayload).toMatchObject({
      contextId: "ctx-preview",
      profileId: "tenant-12-prod",
      tenantContext: "tenant-context",
    });
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
    await writeFile(
      input,
      JSON.stringify({
        pages: [{ title: "Help Center / Orders", url: "https://example.test/orders" }],
      }),
    );
    const result = await runKbBuilder(undefined, "directory-plan", [
      "--crawl-result",
      input,
      "--output",
      `${input}.plan.json`,
    ]);
    expect(result).toMatchObject({ directories: 1, pages: 1 });
  });
});
