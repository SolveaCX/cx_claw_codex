import { readFile, writeFile, mkdir, rename, rm, mkdtemp } from "node:fs/promises";
import { join, resolve } from "node:path";
import ExcelJS from "exceljs";
import { option } from "../args.js";
import { reportMarkdown } from "./report-markdown.js";

export const categoryPairs: Record<string, string[]> = {
  意图问题: ["意图分类器问题", "主意图问题"],
  知识召回: ["缺知识但召回到错误知识", "有正确知识但召回到错误知识", "AI 编造", "知识本身错误"],
  流程问题: [
    "重复索要信息",
    "AGENT节点没有跳转下一步",
    "AGENT节点没有执行完直接跳转下一步",
    "应转人工未转",
    "应回未回",
  ],
  模板问题: ["模板错误"],
};
export const repairStatuses = [
  "待处理",
  "处理中",
  "待补充信息",
  "已修改待验证",
  "已验证通过",
  "验证未通过",
  "无需修复",
];
export const treatments = ["业务配置优化", "产研处理", "无需处理"];
export const detailHeaders = [
  "chatId",
  "agentId",
  "agent名称",
  "问题描述",
  "一级分类",
  "二级分类",
  "问题定位",
  "处理方式",
  "修复建议",
  "状态",
];
export type Case = {
  caseId: string;
  source: string;
  chatId: string;
  agentId: string;
  agentName: string;
  flowVersion?: { historical: string; current: string };
  problem: string;
  primary: string;
  secondary: string;
  classificationGap: string;
  classificationReason: "" | "uncovered" | "insufficient" | "nonissue" | "unreviewed";
  suggestedCategory: string;
  diagnosis: string;
  recommendation: string;
  evidence: string;
  gaps: string;
  certainty: "confirmed" | "partial";
  priority: "P0" | "P1" | "P2" | "P3";
  treatment: string;
  status: string;
  fixId: string;
  conversationId: string;
  targetMessageId: string;
  technical: string;
};
export type Conversation = {
  conversationId: string;
  chatId: string;
  snapshotAt: string;
  completeness: string;
  messages: {
    id: string;
    role: "customer" | "ai" | "human" | "event" | "unknown";
    text: string;
    time: string;
    turn: string;
    attachments: string[];
  }[];
};
export type BadcaseReport = {
  schemaVersion: 1;
  batch: {
    tenantName: string;
    accountId: string;
    environment: string;
    scope: string;
    snapshotAt: string;
    generatedAt: string;
    notice: string;
    sourceCount: number;
    includedCount: number;
    excludedCount: number;
    findings: { title: string; summary: string; caseIds: string[] }[];
  };
  cases: Case[];
  conversations: Conversation[];
  fixes: { fixId: string; title: string; priority: "P0" | "P1" | "P2" | "P3"; ready: boolean }[];
};

// Reject malformed input before creating either deliverable. Content is already reviewed/redacted by the caller.
export function validateBadcaseReport(value: unknown): asserts value is BadcaseReport {
  const fail = (message: string): never => {
    throw new Error(`Invalid badcase data: ${message}`);
  };
  const object = (v: any, where: string) => {
    if (!v || typeof v !== "object" || Array.isArray(v)) fail(where + " must be an object");
  };
  const strings = (v: any, keys: string[], where: string) => {
    object(v, where);
    for (const k of keys) if (typeof v[k] !== "string") fail(`${where}.${k} must be a string`);
  };
  const d = value as any;
  object(d, "root");
  if (d.schemaVersion !== 1) fail("unsupported schemaVersion");
  strings(
    d.batch,
    ["tenantName", "accountId", "environment", "scope", "snapshotAt", "generatedAt", "notice"],
    "batch",
  );
  for (const k of ["sourceCount", "includedCount", "excludedCount"])
    if (!Number.isSafeInteger(d.batch[k]) || d.batch[k] < 0)
      fail(`batch.${k} must be a nonnegative integer`);
  if (d.batch.sourceCount !== d.batch.includedCount + d.batch.excludedCount)
    fail("source counts do not reconcile");
  for (const k of ["cases", "conversations", "fixes"])
    if (!Array.isArray(d[k])) fail(`${k} must be an array`);
  if (!Array.isArray(d.batch.findings)) fail("findings must be an array");
  const conversations = new Map<string, Conversation>();
  for (const c of d.conversations) {
    strings(c, ["conversationId", "chatId", "snapshotAt", "completeness"], "conversation");
    if (!c.conversationId || conversations.has(c.conversationId))
      fail("duplicate/empty conversationId");
    if (!Array.isArray(c.messages)) fail("messages must be an array");
    const ids = new Set();
    for (const m of c.messages) {
      strings(m, ["id", "role", "text", "time", "turn"], "message");
      if (!m.id || ids.has(m.id)) fail("duplicate/empty message id");
      ids.add(m.id);
      if (!["customer", "ai", "human", "event", "unknown"].includes(m.role))
        fail("invalid message role");
      if (
        !Array.isArray(m.attachments) ||
        m.attachments.some((a: unknown) => typeof a !== "string")
      )
        fail("attachments must be text descriptions");
    }
    conversations.set(c.conversationId, c);
  }
  const fixes = new Set<string>();
  for (const f of d.fixes) {
    strings(f, ["fixId", "title", "priority"], "fix");
    if (!f.fixId || fixes.has(f.fixId)) fail("duplicate/empty fixId");
    if (!["P0", "P1", "P2", "P3"].includes(f.priority) || typeof f.ready !== "boolean")
      fail("invalid fix priority/readiness");
    fixes.add(f.fixId);
  }
  const ids = new Set<string>();
  const sources = new Set<string>();
  for (const c of d.cases) {
    strings(
      c,
      [
        "caseId",
        "source",
        "chatId",
        "agentId",
        "agentName",
        "problem",
        "primary",
        "secondary",
        "classificationGap",
        "suggestedCategory",
        "diagnosis",
        "recommendation",
        "evidence",
        "gaps",
        "certainty",
        "priority",
        "treatment",
        "status",
        "fixId",
        "conversationId",
        "targetMessageId",
        "technical",
      ],
      "case",
    );
    if (c.flowVersion !== undefined) {
      strings(c.flowVersion, ["historical", "current"], "case.flowVersion");
      if (!c.agentId && (c.flowVersion.historical || c.flowVersion.current))
        fail("flow version requires agent identity");
    }
    if (!c.caseId || ids.has(c.caseId) || !c.source)
      fail("duplicate/empty caseId or missing source");
    ids.add(c.caseId);
    sources.add(c.source);
    if (c.primary && !categoryPairs[c.primary]) fail("invalid primary category");
    if (c.secondary && !categoryPairs[c.primary]?.includes(c.secondary))
      fail("invalid category pair");
    if (
      !["", "uncovered", "insufficient", "nonissue", "unreviewed"].includes(
        c.classificationReason,
      ) ||
      (!c.secondary && !c.classificationReason)
    )
      fail("invalid or missing classificationReason");
    if (c.classificationReason === "uncovered" && !c.suggestedCategory)
      fail("uncovered category requires model suggestion");
    if (!c.secondary && !c.classificationGap) fail("blank category requires explanation");
    if (
      (!c.agentId && c.agentName) ||
      !repairStatuses.includes(c.status) ||
      (c.treatment && !treatments.includes(c.treatment))
    )
      fail("invalid agent/treatment/status");
    if (
      !["P0", "P1", "P2", "P3"].includes(c.priority) ||
      !["confirmed", "partial"].includes(c.certainty)
    )
      fail("invalid priority/certainty");
    if (c.fixId && !fixes.has(c.fixId)) fail("missing fix reference");
    if (c.conversationId) {
      const conv = conversations.get(c.conversationId);
      if (!conv || conv.chatId !== c.chatId) fail("missing or wrong conversation reference");
      if (c.targetMessageId && !conv?.messages.some((m) => m.id === c.targetMessageId))
        fail("missing target message");
      if (!c.targetMessageId && !c.gaps) fail("missing target message requires gap");
    } else if (c.targetMessageId || !c.gaps)
      fail("unavailable conversation requires gap and no target");
  }
  if (sources.size !== d.batch.includedCount) fail("included source count does not match cases");
  for (const f of d.fixes) if (!d.cases.some((c: Case) => c.fixId === f.fixId)) fail("orphan fix");
  for (const f of d.batch.findings) {
    strings(f, ["title", "summary"], "finding");
    if (
      !Array.isArray(f.caseIds) ||
      f.caseIds.some((id: unknown) => typeof id !== "string" || !ids.has(id))
    )
      fail("invalid finding case reference");
  }
}

export function embeddedJson(value: unknown) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

export async function renderBadcaseReport(data: unknown, outputDir: string) {
  validateBadcaseReport(data);
  const dir = resolve(outputDir);
  const [template, css, js] = await Promise.all(
    ["html", "css", "js"].map((ext) =>
      readFile(new URL(`./assets/badcase-workbench.${ext}`, import.meta.url), "utf8"),
    ),
  );
  const markdownFields = ["diagnosis", "recommendation", "evidence", "gaps"] as const;
  const caseMarkdown = Object.fromEntries(
    data.cases.map((c) => [
      c.caseId,
      Object.fromEntries(markdownFields.map((field) => [field, reportMarkdown(c[field])])),
    ]),
  );
  const messageMarkdown = Object.fromEntries(
    data.conversations.map((c) => [
      c.conversationId,
      Object.fromEntries(c.messages.map((m) => [m.id, reportMarkdown(m.text).html])),
    ]),
  );
  const html = template
    .replace("/*WORKBENCH_CSS*/", () => css)
    .replace("/*WORKBENCH_JS*/", () => js)
    .replace("__WORKBENCH_DATA__", () =>
      embeddedJson({ ...data, presentation: { cases: caseMarkdown, messages: messageMarkdown } }),
    );
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("诊断明细", {
    views: [{ state: "frozen", xSplit: 2, ySplit: 1, showGridLines: false, zoomScale: 85 }],
  });
  const columnWidths = [23, 13, 28, 48, 16, 30, 80, 20, 72, 20];
  sheet.columns = detailHeaders.map((header, i) => ({
    header,
    width: columnWidths[i],
  }));
  const lists = workbook.addWorksheet("候选项", { state: "veryHidden" });
  const enumLists = [
    Object.keys(categoryPairs),
    treatments,
    repairStatuses,
    ...Object.values(categoryPairs),
  ];
  enumLists.forEach((values, col) =>
    values.forEach((v, row) => {
      lists.getCell(row + 1, col + 1).value = v;
    }),
  );
  for (const c of data.cases) {
    const conversation = data.conversations.find((v) => v.conversationId === c.conversationId);
    const location = [
      c.flowVersion
        ? `Flow版本：会话运行 ${c.flowVersion.historical || "未取得"}；当前 ${c.flowVersion.current || "未取得"}`
        : "",
      caseMarkdown[c.caseId].diagnosis.text,
      c.suggestedCategory ? `模型建议分类：${c.suggestedCategory}` : "",
      c.classificationGap,
      `定位依据：${c.caseId}｜${c.source}｜目标消息 ${c.targetMessageId || "未取得"}`,
      caseMarkdown[c.caseId].evidence.text,
      c.technical,
      c.gaps ? `待补证：${caseMarkdown[c.caseId].gaps.text}` : "",
      conversation ? `会话快照：${conversation.snapshotAt}` : "",
    ]
      .filter(Boolean)
      .join("\n\n");
    const row = sheet.addRow([
      c.chatId,
      c.agentId,
      c.agentName,
      c.problem,
      c.primary,
      c.secondary,
      location,
      c.treatment,
      [c.fixId, caseMarkdown[c.caseId].recommendation.text].filter(Boolean).join("："),
      c.status,
    ]);
    // Estimate wrapped lines with CJK characters occupying two character units.
    // Cap very long evidence rows; the complete text remains available in the cell.
    let wrappedLines = 1;
    row.eachCell({ includeEmpty: true }, (cell, col) => {
      const lines = cell.text.split("\n").reduce((total, line) => {
        const units = [...line].reduce((n, char) => n + (char.codePointAt(0)! > 255 ? 2 : 1), 0);
        return total + Math.max(1, Math.ceil(units / (columnWidths[col - 1] - 3)));
      }, 0);
      wrappedLines = Math.max(wrappedLines, lines);
      cell.alignment = { vertical: "top", horizontal: "left", wrapText: true, indent: 1 };
      cell.font = {
        name: "Aptos",
        size: 11,
        color: { argb: col <= 2 ? "FF64748B" : "FF243B45" },
        bold: col === 3 || col === 8 || col === 10,
      };
      cell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: row.number % 2 === 0 ? "FFF3F7F8" : "FFFFFFFF" },
      };
      cell.border = {
        bottom: { style: "hair", color: { argb: "FFDCE5E9" } },
        ...([3, 6, 7].includes(col)
          ? { right: { style: "thin" as const, color: { argb: "FFDCE5E9" } } }
          : {}),
      };
      if (col <= 2) cell.numFmt = "@";
    });
    row.height = Math.min(300, Math.max(96, wrappedLines * 15 + 12));
    for (const [col, listCol, length] of [
      [5, "A", enumLists[0].length],
      [8, "B", treatments.length],
      [10, "C", repairStatuses.length],
    ] as const) {
      row.getCell(col).dataValidation = {
        type: "list",
        allowBlank: true,
        formulae: [`'候选项'!$${listCol}$1:$${listCol}$${length}`],
        showErrorMessage: true,
        errorStyle: "stop",
        error: "请选择候选项",
      };
    }
    // Dependent dropdown references primary category; users changing it must choose a matching secondary.
    row.getCell(6).dataValidation = {
      type: "list",
      allowBlank: true,
      formulae: [
        `INDIRECT(IFERROR(CHOOSE(MATCH(E${row.number},'候选项'!$A$1:$A$4,0),"'候选项'!$D$1:$D$2","'候选项'!$E$1:$E$4","'候选项'!$F$1:$F$5","'候选项'!$G$1:$G$1"),"'候选项'!$H$1"))`,
      ],
      showErrorMessage: true,
      errorStyle: "stop",
      error: "请选择与一级分类对应的二级分类",
    };
  }
  sheet.getRow(1).height = 36;
  sheet.getRow(1).eachCell((cell, col) => {
    cell.font = { name: "Aptos", bold: true, color: { argb: "FFFFFFFF" }, size: 11 };
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: col <= 3 ? "FF243D4B" : col <= 7 ? "FF225F64" : "FF385E4C" },
    };
    cell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    cell.border = { right: { style: "hair", color: { argb: "FFB7CBCB" } } };
  });
  // Conditional styles stay in sync when delivery staff edit dropdown values.
  if (data.cases.length) {
    const coloredValues: [string, string, string, string][] = [
      ["E", "意图问题", "FFECE9F7", "FF5C4C88"],
      ["E", "知识召回", "FFE6EFF9", "FF315F8A"],
      ["E", "流程问题", "FFE3F1EF", "FF28655E"],
      ["E", "模板问题", "FFF7EEDD", "FF81602E"],
      ["H", "业务配置优化", "FFE3F1EF", "FF28655E"],
      ["H", "产研处理", "FFECE9F7", "FF5C4C88"],
      ["H", "无需处理", "FFEDF0F3", "FF627080"],
      ["J", "待处理", "FFEDF0F3", "FF526171"],
      ["J", "处理中", "FFE6EFF9", "FF315F8A"],
      ["J", "待补充信息", "FFFFF1D8", "FF8B601B"],
      ["J", "已修改待验证", "FFECE9F7", "FF5C4C88"],
      ["J", "已验证通过", "FFE1F1E5", "FF2D6B42"],
      ["J", "验证未通过", "FFFBE7E5", "FF9A423A"],
      ["J", "无需修复", "FFEDF0F3", "FF627080"],
    ];
    coloredValues.forEach(([col, value, background, foreground], index) => {
      sheet.addConditionalFormatting({
        ref: `${col}2:${col === "E" ? "F" : col}${sheet.rowCount}`,
        rules: [
          {
            type: "expression",
            priority: index + 1,
            formulae: [`AND($${col}2="${value}",${col}2<>"")`],
            style: {
              fill: { type: "pattern", pattern: "solid", fgColor: { argb: background } },
              font: { color: { argb: foreground } },
            },
          },
        ],
      });
    });
  }
  sheet.autoFilter = { from: "A1", to: `J${sheet.rowCount}` };
  await mkdir(dir, { recursive: true });
  const tmp = await mkdtemp(join(dir, ".badcase-"));
  try {
    const xlsx = Buffer.from(await workbook.xlsx.writeBuffer());
    const standalone = html.replace(
      "__WORKBENCH_XLSX__",
      () =>
        `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${xlsx.toString("base64")}`,
    );
    await writeFile(join(tmp, "badcase-report.html"), standalone);
    await writeFile(join(tmp, "badcase-details.xlsx"), xlsx);
    for (const name of ["badcase-report.html", "badcase-details.xlsx"])
      await rename(join(tmp, name), join(dir, name));
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
  return {
    html: join(dir, "badcase-report.html"),
    xlsx: join(dir, "badcase-details.xlsx"),
    cases: data.cases.length,
    conversations: data.conversations.length,
  };
}

export const badcaseHelp =
  "cxclawctl badcase render --data-file <diagnosis.json> --output-dir <directory>\nRender local diagnosis data into an offline HTML workbench and fixed-column XLSX. No tenant login or customer writes.";
export async function runBadcase(action: string | undefined, args: string[]) {
  if (action !== "render") throw new Error(badcaseHelp);
  return renderBadcaseReport(
    JSON.parse(await readFile(option(args, "--data-file", true)!, "utf8")),
    option(args, "--output-dir", true)!,
  );
}
