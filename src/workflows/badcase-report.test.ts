import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import ExcelJS from "exceljs";
import {
  validateBadcaseReport,
  renderBadcaseReport,
  detailHeaders,
  type BadcaseReport,
} from "./badcase-report.js";
const sample = (): BadcaseReport => ({
  schemaVersion: 1,
  batch: {
    tenantName: "Test",
    accountId: "1",
    environment: "test",
    scope: "Sheet1",
    snapshotAt: "2026-11-27",
    generatedAt: "2026-11-27",
    notice: "",
    sourceCount: 1,
    includedCount: 1,
    excludedCount: 0,
    findings: [],
  },
  cases: [
    {
      caseId: "C1",
      source: "Sheet1!2",
      chatId: "000000123456789012345",
      agentId: "",
      agentName: "",
      problem: "=1+2",
      primary: "流程问题",
      secondary: "",
      classificationGap: "待补证",
      classificationReason: "insufficient",
      suggestedCategory: "",
      diagnosis: "<script>window.__unsafe=true</script>",
      recommendation: "核对原始记录",
      evidence: "",
      gaps: "缺配置",
      certainty: "partial",
      priority: "P1",
      treatment: "",
      status: "待补充信息",
      fixId: "",
      conversationId: "conv1",
      targetMessageId: "m2",
      technical: "",
    },
  ],
  conversations: [
    {
      conversationId: "conv1",
      chatId: "000000123456789012345",
      snapshotAt: "2026-11-27",
      completeness: "本次已取得消息",
      messages: [
        {
          id: "m1",
          role: "customer",
          text: '</script><img src=x onerror="window.__unsafe=true">',
          time: "",
          turn: "1",
          attachments: [],
        },
        { id: "m2", role: "ai", text: "原始回复", time: "", turn: "1", attachments: [] },
      ],
    },
  ],
  fixes: [],
});
test("validates references and preserves multiple complaints in one conversation", () => {
  const d = sample();
  d.cases.push({ ...d.cases[0], caseId: "C2", targetMessageId: "m1" });
  expect(() => validateBadcaseReport(d)).not.toThrow();
  for (const change of [
    (v: BadcaseReport) => (v.cases[0].targetMessageId = "missing"),
    (v: BadcaseReport) => (v.cases[0].chatId = "other"),
    (v: BadcaseReport) => (v.cases[0].secondary = "主意图问题"),
    (v: BadcaseReport) => (v.cases[0].fixId = "missing"),
    (v: BadcaseReport) => (v.batch.includedCount = 2),
  ]) {
    const v = sample();
    change(v);
    expect(() => validateBadcaseReport(v)).toThrow();
  }
});
test("renders offline artifacts with escaped data, text IDs, safe spreadsheet values and dropdowns", async () => {
  const dir = await mkdtemp(join(tmpdir(), "cx-badcase-test-"));
  try {
    const result = await renderBadcaseReport(sample(), dir);
    const html = await readFile(result.html, "utf8");
    expect(html).not.toContain("</script><img src=x");
    expect(html).not.toContain("__WORKBENCH_DATA__");
    expect(html).toContain("\\u003c/script\\u003e");
    const w = new ExcelJS.Workbook();
    await w.xlsx.readFile(result.xlsx);
    const s = w.getWorksheet("诊断明细")!;
    expect(s.getRow(1).values).toEqual([undefined, ...detailHeaders]);
    expect(s.rowCount).toBe(2);
    expect(s.getCell("A2").value).toBe("000000123456789012345");
    expect(s.getCell("D2").value).toBe("=1+2");
    expect(s.getCell("F2").dataValidation.type).toBe("list");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("preserves explicit flow versions and rejects ambiguous version metadata", async () => {
  const data = sample();
  data.cases[0].flowVersion = { historical: "v3", current: "v7" };
  expect(() => validateBadcaseReport(data)).toThrow("flow version requires agent identity");
  data.cases[0].agentId = "agent-1";
  data.cases[0].agentName = "售后服务";
  data.cases[0].diagnosis = "**节点「售后支持」**\n\n- 未执行下一步";
  data.cases[0].recommendation = "1. **核对分支**\n2. 回归原会话";
  expect(() => validateBadcaseReport(data)).not.toThrow();
  const dir = await mkdtemp(join(tmpdir(), "cx-badcase-version-"));
  try {
    const result = await renderBadcaseReport(data, dir);
    const w = new ExcelJS.Workbook();
    await w.xlsx.readFile(result.xlsx);
    const s = w.getWorksheet("诊断明细")!;
    expect(s.columnCount).toBe(10);
    expect(s.getCell("G2").text).toContain("Flow版本：会话运行 v3；当前 v7");
    expect(s.getCell("G2").text).toContain("节点「售后支持」\n\n• 未执行下一步");
    expect(s.getCell("I2").text).toBe("1. 核对分支\n2. 回归原会话");
    const html = await readFile(result.html, "utf8");
    expect(html).toContain('"flowVersion":{"historical":"v3","current":"v7"}');
    (data.cases[0].flowVersion as any).historical = 3;
    expect(() => validateBadcaseReport(data)).toThrow(
      "case.flowVersion.historical must be a string",
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
