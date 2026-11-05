import { z } from "zod";

export const LiveTestStartInputSchema = z
  .object({
    contextId: z.string().min(1),
    agentId: z.number().int().positive(),
    botId: z.number().int().positive().optional(),
    flowVersion: z.number().int().optional(),
    touchPoint: z.string().default("LIVE_CHAT"),
    case: z
      .object({
        caseId: z.string().optional(),
        turns: z
          .array(z.object({ message: z.string().min(1).max(20_000) }))
          .min(1)
          .max(10),
      })
      .optional(),
    message: z.string().min(1).max(20_000).optional(),
    chatId: z.string().optional(),
    metadata: z.record(z.string(), z.unknown()).default({}),
    option: z.record(z.string(), z.unknown()).default({}),
  })
  .superRefine((value, context) => {
    if (Boolean(value.case) === Boolean(value.message))
      context.addIssue({
        code: "custom",
        message: "case.turns 和 message 必须且只能提供一个",
      });
    const messageChars =
      value.case?.turns.reduce((total, turn) => total + turn.message.length, 0) ??
      value.message?.length ??
      0;
    if (messageChars > 60_000)
      context.addIssue({ code: "custom", message: "测试问题总长度不能超过 60000 字符" });
    if (JSON.stringify({ metadata: value.metadata, option: value.option }).length > 32_000)
      context.addIssue({ code: "custom", message: "metadata 和 option 总长度不能超过 32000 字符" });
  });

export const LiveTestStatusInputSchema = z.object({
  contextId: z.string().min(1),
  testRunId: z.string().min(1),
  afterRevision: z.number().int().min(0).optional(),
  waitMs: z.number().int().min(0).max(20_000).default(0),
});

export const LiveTestRunInputSchema = z.object({
  contextId: z.string().min(1),
  testRunId: z.string().min(1),
});

export const LiveTestTurnSchema = z.object({
  index: z.number().int().min(0),
  user: z.string(),
  assistant: z.string().default(""),
  status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]),
  startedAt: z.number().optional(),
  completedAt: z.number().optional(),
  messageId: z.string().optional(),
  error: z.string().optional(),
  outcome: z
    .object({
      actionType: z.string().optional(),
      handoff: z.boolean().optional(),
      reason: z.string().optional(),
      reasonDesc: z.string().optional(),
      explain: z.string().optional(),
    })
    .optional(),
});

export const LiveTestSnapshotSchema = z.object({
  testRunId: z.string(),
  contextId: z.string(),
  profileId: z.string(),
  accountId: z.number().int(),
  environment: z.string(),
  agentId: z.number().int(),
  agentName: z.string().optional(),
  botId: z.number().int().optional(),
  flowVersion: z.number().int().optional(),
  chatId: z.string().optional(),
  status: z.enum([
    "queued",
    "resolving",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
  ]),
  revision: z.number().int().min(0),
  createdAt: z.number(),
  updatedAt: z.number(),
  completedAt: z.number().optional(),
  error: z.string().optional(),
  failedNodeId: z.string().optional(),
  failedNodeTitle: z.string().optional(),
  truncated: z.boolean().default(false),
  turns: z.array(LiveTestTurnSchema),
});

export const LiveTestStartOutputSchema = z.object({
  testRunId: z.string(),
  snapshot: LiveTestSnapshotSchema,
});
export const LiveTestSnapshotOutputSchema = z.object({ snapshot: LiveTestSnapshotSchema });
export const LiveTestTranscriptOutputSchema = z.object({
  testRunId: z.string(),
  chatId: z.string(),
  transcript: z.unknown(),
});

export type LiveTestStartInput = z.infer<typeof LiveTestStartInputSchema>;
export type LiveTestSnapshot = z.infer<typeof LiveTestSnapshotSchema>;
export type LiveTestTurn = z.infer<typeof LiveTestTurnSchema>;

export const TERMINAL_LIVE_TEST_STATUSES = new Set<LiveTestSnapshot["status"]>([
  "succeeded",
  "failed",
  "cancelled",
  "interrupted",
]);
