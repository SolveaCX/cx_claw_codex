import { join } from "node:path";
import ExcelJS from "exceljs";
import type { Session } from "../types.js";
import { option } from "../args.js";
import { SolveaClient } from "../solvea/client.js";
import { asRows, ensureParent, intOption, outputRoot, readJson } from "./common.js";

type JsonObject = Record<string, unknown>;

async function casesFrom(file: string) {
  if (file.endsWith(".json")) return asRows(await readJson(file));
  const workbook = new ExcelJS.Workbook(); await workbook.xlsx.readFile(file); const sheet = workbook.worksheets[0]; if (!sheet) throw new Error("cases workbook has no worksheet"); const headers = (sheet.getRow(1).values as unknown[]).slice(1).map(v => String(v ?? "")); const rows: JsonObject[] = []; sheet.eachRow((row, number) => { if (number === 1) return; const values = (row.values as unknown[]).slice(1), item: JsonObject = {}; headers.forEach((header, index) => { if (header) item[header] = values[index] ?? ""; }); rows.push(item); }); return rows;
}

async function createSheet(args: string[]) {
  const cases = option(args, "--cases-file") ? await casesFrom(option(args, "--cases-file")!) : []; const output = option(args, "--output") ?? join(outputRoot("agent-tester"), `cases_${Date.now()}.xlsx`); await ensureParent(output); const workbook = new ExcelJS.Workbook(); const sheet = workbook.addWorksheet("cases"); const headers = cases.length ? [...new Set(cases.flatMap(row => Object.keys(row)))] : ["question", "expected_answer"]; sheet.addRow(headers); cases.forEach(row => sheet.addRow(headers.map(header => row[header] ?? ""))); await workbook.xlsx.writeFile(output); return { output, count: cases.length, mode: option(args, "--mode") };
}

async function submit(client: SolveaClient, args: string[]) {
  const file = await client.uploadTempFile(option(args, "--file", true)!); const result = await client.rawCall("POST", `/api_v2/gpt/label/project/${await client.projectId()}/uploadMessage`, { file, type: option(args, "--mode", true), ...(option(args, "--agent-id") ? { agentId: Number(option(args, "--agent-id")) } : {}), ...(option(args, "--flow-version") ? { flowVersion: Number(option(args, "--flow-version")) } : {}) }); return { fileKey: file, result };
}

export async function runAgentTester(session: Session | undefined, action: string | undefined, args: string[]) {
  if (!action) throw new Error("agent-tester action is required"); if (action === "create-sheet") return createSheet(args); if (!session) throw new Error(`${action} requires an authenticated tenant`); const client = new SolveaClient(session); if (action === "submit") return submit(client, args); if (action === "get-tasks") return client.rawCall("POST", `/api_v2/gpt/label/project/${await client.projectId()}/getLabelTask`, { page: intOption(args, "--page", 1), pageSize: intOption(args, "--page-size", 20), taskType: option(args, "--mode") }); throw new Error(`unknown agent-tester action: ${action}`);
}
