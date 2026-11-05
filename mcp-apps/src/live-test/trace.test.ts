import { describe, expect, test } from "bun:test";
import { normalizeTrace } from "./trace.js";

describe("LiveTest trace presentation", () => {
  test("groups Chatflow start and finish events into readable steps", () => {
    const steps = normalizeTrace({
      messages: [
        {
          contextComparison: {
            chatContext: {
              ext: {
                chatflow_run_info: [
                  {
                    event: "node_started",
                    timestamp: 10,
                    eventData: {
                      node_id: "intent",
                      node_title: "意图识别",
                      inputs: { text: "hi" },
                    },
                  },
                  {
                    event: "node_finished",
                    timestamp: 20,
                    eventData: {
                      node_id: "intent",
                      node_title: "意图识别",
                      status: "success",
                      elapsed_time: 480,
                      outputs: { intent: "support" },
                      traces: [
                        {
                          trace_type: "tool",
                          tool_name: "classify",
                          input: { text: "hi" },
                          result: { intent: "support" },
                        },
                      ],
                    },
                  },
                ],
              },
            },
          },
        },
      ],
    });
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      title: "意图识别",
      status: "success",
      elapsed: 480,
      input: { text: "hi" },
      output: { intent: "support" },
      tools: [{ name: "classify" }],
    });
  });

  test("falls back to agent tool history when Chatflow events are absent", () => {
    expect(
      normalizeTrace({
        context: {
          ext: {
            ai_agent_history_msg: [
              { type: "function_call", content: { name: "search", arguments: { q: "order" } } },
              { type: "tool_response", content: { status: "ok" } },
            ],
          },
        },
      }).map((step) => step.title),
    ).toEqual(["工具调用 · search", "工具响应"]);
  });
});
