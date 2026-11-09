import { describe, expect, test } from "bun:test";
import { batchTaskType, buildWorkbook } from "./tester.js";

describe("agent tester batch workbook", () => {
  test("maps public modes to system task types", () => {
    expect(batchTaskType("chatflow")).toBe("MULTI_TURN_REPLY");
    expect(batchTaskType("agent")).toBe("REPLY");
  });

  test("builds the system multi-turn Chatflow template", async () => {
    const workbook = await buildWorkbook(
      [
        {
          case_name: "refund-follow-up",
          turns: [
            { question: "我要退款", metadata: { order_number: "A-1001" } },
            { question: "订单号就是 A-1001" },
          ],
        },
      ],
      "chatflow",
    );
    const sheet = workbook.worksheets[0]!;
    expect(sheet.getRow(1).getCell(1).value).toContain("multi-turn case");
    expect(Array.from(sheet.getRow(2).values as unknown[]).slice(1)).toEqual([
      "case_name",
      "chat_id",
      "metadata_1",
      "question_1",
      "ai_answer_1",
      "metadata_2",
      "question_2",
      "ai_answer_2",
    ]);
    expect(Array.from(sheet.getRow(3).values as unknown[]).slice(1)).toEqual([
      "refund-follow-up",
      "",
      '{"order_number":"A-1001"}',
      "我要退款",
      "",
      "",
      "订单号就是 A-1001",
      "",
    ]);
  });

  test("builds the ordinary Agent REPLY template and renders metadata", async () => {
    const workbook = await buildWorkbook(
      [
        {
          question: "我的订单什么时候发货？",
          metadata: { touchPoint: "LIVE_CHAT", order_number: "A-1001" },
        },
      ],
      "agent",
    );
    const sheet = workbook.worksheets[0]!;
    expect(Array.from(sheet.getRow(2).values as unknown[]).slice(1)).toEqual([
      "question",
      "origin_answer",
      "ai_answer",
      "similarity",
      "judgement",
      "reason",
      "chat_id",
      "meta_data",
      "fail_reason",
    ]);
    expect(sheet.getRow(3).getCell(8).value).toBe("touchPoint: LIVE_CHAT; order_number: A-1001");
  });

  test("enforces system case limits", async () => {
    await expect(
      buildWorkbook(
        Array.from({ length: 201 }, () => ({ question: "hello" })),
        "agent",
      ),
    ).rejects.toThrow("at most 200");
    await expect(
      buildWorkbook(
        Array.from({ length: 601 }, () => ({ turns: [{ question: "hello" }] })),
        "chatflow",
      ),
    ).rejects.toThrow("at most 600");
  });
});
