import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { runTicketAnalytics, ticketTimeWindow } from "./ticket-analytics.js";
import { ticketReportHtml, validateTicketReport } from "./ticket-report.js";
const session = {
  tenant: {
    accountId: 123,
    environment: "prod",
    businessUrl: "https://example.test",
    businessToken: "test-secret",
  },
} as Session;
const originalFetch = globalThis.fetch;
const originalEnv = {
  workspace: process.env.CXCLAW_WORKSPACE,
  state: process.env.CXCLAW_STATE_DIR,
  output: process.env.CXCLAW_OUTPUT_DIR,
};
let dir: string;
beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), "ticket-analysis-"));
  process.env.CXCLAW_WORKSPACE = dir;
  delete process.env.CXCLAW_STATE_DIR;
  delete process.env.CXCLAW_OUTPUT_DIR;
});
afterEach(async () => {
  globalThis.fetch = originalFetch;
  for (const [key, value] of Object.entries({
    CXCLAW_WORKSPACE: originalEnv.workspace,
    CXCLAW_STATE_DIR: originalEnv.state,
    CXCLAW_OUTPUT_DIR: originalEnv.output,
  })) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  await rm(dir, { recursive: true, force: true });
});
const response = (data: unknown) => new Response(JSON.stringify({ code: 200, data }));
test("calendar windows use inclusive Shanghai dates and reject invalid/partial/oversize ranges", () => {
  expect(ticketTimeWindow("2026-01-01", "2026-01-02")).toEqual({
    start: "2026-01-01T00:00:00",
    end: "2026-01-02T23:59:59",
    timezone: "Asia/Shanghai",
  });
  expect(ticketTimeWindow("2025-12-31T16:00:00Z", "2026-01-01T16:00:00Z").start).toBe(
    "2026-01-01T00:00:00",
  );
  for (const [start, end, zone] of [
    ["2026-02-30", "2026-03-01"],
    ["2026-02-30T00:00:00+08:00", "2026-03-01"],
    ["2026-01-01T01:00:00", "2026-01-02"],
    ["2026-01-02", "2026-01-01"],
    ["2026-01-01", "2026-04-01"],
    ["2026-01-01", "2026-01-02", "UTC"],
  ])
    expect(() => ticketTimeWindow(start, end, zone)).toThrow();
});
test("historical snapshots use report facts, export multi-sheet XLSX and record completeness", async () => {
  let calls = 0;
  globalThis.fetch = (async (input, init) => {
    calls++;
    expect(new URL(String(input)).pathname).toBe("/api_v2/tars/api/ticket/report/raw/page");
    const body = JSON.parse(String(init?.body));
    expect(body).toEqual({
      startTime: "2026-01-01T00:00:00",
      endTime: "2026-01-02T23:59:59",
      page: calls,
      pageSize: 200,
    });
    return response({
      replies: [{ id: calls, assignee: "actual-replier", nested: { ok: true } }],
      resolutions: [{ id: 10 + calls }],
      hasMore: calls < 2,
    });
  }) as typeof fetch;
  const result = (await runTicketAnalytics(session, "fetch-sources", [
    "--start",
    "2026-01-01",
    "--end",
    "2026-01-02",
    "--task-id",
    "history",
  ])) as any;
  expect(result).toMatchObject({ count: 4, truncated: false, pagesFetched: 2 });
  const manifest = JSON.parse(await readFile(result.manifest, "utf8"));
  expect(manifest).toMatchObject({
    source_type: "ticket_report_snapshot",
    snapshot_semantics: "historical_facts",
    tenant: { accountId: 123, environment: "prod" },
    row_counts: { replies: 2, resolutions: 2 },
  });
  expect(JSON.stringify(manifest)).not.toContain("test-secret");
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(result.output);
  expect(workbook.worksheets.map((s) => s.name)).toEqual(["replies", "resolutions"]);
  expect(workbook.getWorksheet("replies")?.getRow(2).getCell(3).value).toBe('{"ok":true}');
  const latest = JSON.parse(
    await readFile(join(dir, "state/ticket-analytics/latest_task.json"), "utf8"),
  );
  expect(latest.task_id).toBe("history");
});
test("current snapshot pushes filters and marks capped results, preserving source identity", async () => {
  let calls = 0;
  globalThis.fetch = (async (input, init) => {
    calls++;
    expect(new URL(String(input)).pathname).toBe("/api_v2/tars/api/ticket/list");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      viewId: 7,
      agentIdList: [42],
      page: calls,
      pageSize: 2,
      sort: "last_update_time",
      order: "DESC",
    });
    return response({ list: [{ id: calls * 2 }, { id: calls * 2 + 1 }], total: 8 });
  }) as typeof fetch;
  const result = (await runTicketAnalytics(session, "fetch-tickets", [
    "--task-id",
    "current",
    "--view-id",
    "7",
    "--page-size",
    "2",
    "--max-rows",
    "3",
    "--filters-json",
    '{"agentIdList":[42]}',
  ])) as any;
  expect(result).toMatchObject({ count: 3, truncated: true, pagesFetched: 2 });
  const manifest = JSON.parse(await readFile(result.manifest, "utf8"));
  expect(manifest).toMatchObject({
    source_type: "ticket_list_snapshot",
    snapshot_semantics: "current_state",
    view_id: 7,
    filters: { agentIdList: [42] },
  });
});
test("rejects unsupported filters/options and refuses non-advancing or unproven history pages", async () => {
  let calls = 0;
  globalThis.fetch = (async () => {
    calls++;
    return response({ list: [{ id: 1 }], hasMore: true });
  }) as unknown as typeof fetch;
  await expect(
    runTicketAnalytics(session, "fetch-tickets", ["--filters-json", '{"tenantId":99}']),
  ).rejects.toThrow("unknown parameter");
  await expect(
    runTicketAnalytics(session, "fetch-tickets", ["--filters-json", '{"page":9}']),
  ).rejects.toThrow("dedicated");
  await expect(
    runTicketAnalytics(session, "fetch-tickets", ["--start", "2026-01-01"]),
  ).rejects.toThrow("unknown");
  expect(calls).toBe(0);
  const args = ["--start", "2026-01-01", "--end", "2026-01-02"];
  await expect(runTicketAnalytics(session, "fetch-sources", args)).rejects.toThrow(
    "repeated a page",
  );
  globalThis.fetch = (async () => response({ list: [] })) as unknown as typeof fetch;
  await expect(runTicketAnalytics(session, "fetch-sources", args)).rejects.toThrow(
    "pagination metadata",
  );
});
test("report validates schema, renders four charts with escaped values and defaults to tables", () => {
  for (const type of ["bar", "line", "pie", "scatter"]) {
    const html = ticketReportHtml({
      title: "<script>alert(1)</script>",
      sections: [
        {
          title: "Trend",
          columns: [{ key: "x" }, { key: "y", numeric: true }],
          rows: [
            { x: 1, y: 2 },
            { x: 2, y: 3 },
          ],
          chart: { chartType: type, xKey: "x", yKey: "y" },
        },
      ],
    });
    expect(html).toContain(`report-chart-${type}`);
    expect(html).toContain("<svg");
    expect(html).toContain('value="table" checked');
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("{{");
  }
  for (const value of [
    { overview: {} },
    { kpis: [{ label: "x" }] },
    { sections: [{ rows: [], columns: [{ key: "x" }] }] },
    { sections: [{ rows: [{}], columns: ["x"] }] },
    {
      sections: [
        {
          rows: [{}],
          columns: [{ key: "x" }],
          chart: { chartType: "radar", xKey: "x", yKey: "y" },
        },
      ],
    },
  ])
    expect(() => validateTicketReport(value)).toThrow();
});
test("offline reports inherit manifest count and truncation; aggregate-only reports need no snapshot", async () => {
  const state = join(dir, "state/ticket-analytics/report");
  await mkdir(state, { recursive: true });
  await writeFile(
    join(state, "report_data.json"),
    JSON.stringify({ kpis: [{ label: "tickets", value: 2 }], truncated: false }),
  );
  await writeFile(
    join(state, "manifest.json"),
    JSON.stringify({ row_counts: { data: 2 }, truncated: true }),
  );
  const result = (await runTicketAnalytics(undefined, "render-report", [
    "--task-id",
    "report",
    "--report-slug",
    "weekly_summary",
  ])) as any;
  const html = await readFile(result.report, "utf8");
  expect(html).toContain("已截断");
  expect(html).toContain("<strong>2</strong>");
  await expect(
    runTicketAnalytics(undefined, "render-report", [
      "--task-id",
      "report",
      "--report-slug",
      "../bad",
    ]),
  ).rejects.toThrow("snake_case");
  await rm(join(state, "manifest.json"));
  const aggregate = (await runTicketAnalytics(undefined, "render-report", [
    "--task-id",
    "report",
  ])) as any;
  expect(await readFile(aggregate.report, "utf8")).toContain("不适用（聚合统计）");
  expect(
    await runTicketAnalytics(undefined, "render-report", [
      "--task-id",
      "report",
      "--validate-only",
    ]),
  ).toMatchObject({ validated: true });
});
