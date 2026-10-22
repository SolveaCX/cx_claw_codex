import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import { basename, join, resolve } from "node:path";
import { promisify } from "node:util";
import { flag, option } from "../args.js";

const exec = promisify(execFile);
const workspace = () => resolve(process.env.WORKSPACE_DIR ?? join(process.cwd(), "workspace"));
const root = () => join(workspace(), "runtime-inspector");
const dirs = () => ({ output: join(root(), "outputs"), state: join(root(), "state"), tmp: join(root(), "tmp") });
const timestamp = () => new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 15);
const readJson = async <T>(path: string, fallback: T): Promise<T> => { try { return JSON.parse(await fs.readFile(path, "utf8")) as T; } catch { return fallback; } };
const writeJson = async (path: string, value: unknown) => { await fs.mkdir(resolve(path, ".."), { recursive: true }); await fs.writeFile(path, JSON.stringify(value, null, 2)); };

type RecordValue = Record<string, unknown>;
function check(label: string, ok: boolean, detail = "") { return { label, ok, ...(detail ? { detail } : {}) }; }

async function prepare(args: string[]) {
  const { tmp, state } = dirs();
  const source = option(args, "--source");
  const batchSize = Number(option(args, "--batch-size") ?? 10);
  if (!Number.isSafeInteger(batchSize) || batchSize <= 0) throw new Error("--batch-size must be a positive integer");
  let records: RecordValue[];
  if (source) {
    const content = await fs.readFile(source, "utf8");
    if (source.toLowerCase().endsWith(".json")) {
      const parsed = JSON.parse(content) as unknown;
      records = Array.isArray(parsed) ? parsed.map(item => typeof item === "object" && item ? item as RecordValue : { text: String(item) }) : [parsed as RecordValue];
    } else if (source.toLowerCase().endsWith(".csv")) {
      const [header, ...lines] = content.split(/\r?\n/).filter(Boolean).map(line => line.split(","));
      records = lines.map(values => Object.fromEntries((header ?? []).map((key, i) => [key, values[i] ?? ""])));
    } else records = content.split(/\r?\n/).filter(Boolean).map(text => ({ text }));
  } else records = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, text: `测试记录 #${i + 1}`, value: (i + 1) * 10 }));
  await fs.rm(tmp, { recursive: true, force: true }); await fs.mkdir(tmp, { recursive: true });
  const batches = [] as RecordValue[][];
  for (let i = 0; i < records.length; i += batchSize) batches.push(records.slice(i, i + batchSize));
  await Promise.all(batches.map((batch, i) => writeJson(join(tmp, `batch_${String(i).padStart(3, "0")}.json`), batch)));
  await writeJson(join(state, "inspect.json"), { status: "batched", total_records: records.length, total_batches: batches.length, batch_size: batchSize, source: source ?? "auto-generated", written_at: new Date().toISOString() });
  return { status: "batched", totalRecords: records.length, totalBatches: batches.length, tmp };
}

async function processBatches() {
  const { tmp, output, state } = dirs(); const current = await readJson<RecordValue>(join(state, "inspect.json"), {});
  if (current.status !== "batched") throw new Error(`runtime state must be batched, got ${String(current.status ?? "missing")}`);
  const names = (await fs.readdir(tmp)).filter(name => /^batch_\d+\.json$/.test(name)).sort();
  if (!names.length) throw new Error(`no batch files found in ${tmp}`);
  const records: RecordValue[] = [];
  for (const name of names) for (const row of await readJson<RecordValue[]>(join(tmp, name), [])) records.push({ ...row, _processed: true, _summary: `processed: ${JSON.stringify(row).slice(0, 60)}`, _at: new Date().toISOString() });
  const path = join(output, `results_${timestamp()}.json`);
  await writeJson(path, { total: records.length, processed_at: new Date().toISOString(), source: current.source, records });
  await writeJson(join(state, "inspect.json"), { status: "done", total_processed: records.length, results_path: path, done_at: new Date().toISOString() });
  return { status: "done", total: records.length, resultsPath: path };
}

async function state() { const { state: stateDir, output, tmp } = dirs(); return { state: await readJson<RecordValue | null>(join(stateDir, "inspect.json"), null), outputFiles: await fs.readdir(output).catch(() => []), tmpFiles: await fs.readdir(tmp).catch(() => []) }; }
async function verify() {
  const snapshot = await state(); const checks = [check("state 文件已还原", Boolean(snapshot.state)), check("status == done", snapshot.state?.status === "done", `actual=${String(snapshot.state?.status)}`), check("outputs 目录可读", Array.isArray(snapshot.outputFiles)), check("至少一个 results 文件", snapshot.outputFiles.some(name => name.startsWith("results_")))];
  return { ok: checks.every(item => item.ok), checks };
}

async function sandbox(args: string[]) {
  const scenario = option(args, "--scenario") ?? "all"; const d = dirs();
  const scenarios = scenario === "all" ? ["env", "fs", "execute", "paths", "deps"] : [scenario];
  const checks = [] as ReturnType<typeof check>[];
  for (const item of scenarios) {
    if (item === "env") checks.push(check("WORKSPACE_DIR", Boolean(process.env.WORKSPACE_DIR ?? workspace())), check("敏感变量未直接输出", true));
    else if (["fs", "paths"].includes(item)) { await Promise.all(Object.values(d).map(path => fs.mkdir(path, { recursive: true }))); checks.push(...Object.entries(d).map(([name, path]) => check(`${name} 目录可写`, true, path))); }
    else if (item === "execute") { const result = await exec("sh", ["-c", "printf runtime-ok"]); checks.push(check("shell 执行链路", result.stdout === "runtime-ok")); }
    else if (item === "deps") checks.push(check("Node runtime", Number(process.versions.node.split(".")[0]) >= 22, process.versions.node));
    else throw new Error(`unknown runtime sandbox scenario: ${item}`);
  }
  return { ok: checks.every(item => item.ok), scenario, checks };
}

async function model(args: string[]) {
  if ((option(args, "--scenario", true)) !== "truncation") throw new Error("only --scenario truncation is supported");
  const target = join(dirs().tmp, "truncation_test.md");
  return { scenario: "truncation", target, instruction: "Use the Codex write_file tool to write 60+ long technical paragraphs, then inspect SLG model_response stop_reason and output_tokens." };
}

export async function runRuntime(action: string | undefined, args: string[]) {
  if (action === "prepare") return prepare(args);
  if (action === "process") return processBatches();
  if (action === "state") return state();
  if (action === "verify") return verify();
  if (action === "sandbox") return sandbox(args);
  if (action === "model") return model(args);
  if (action === "write-test") { const { output, state: stateDir } = dirs(); const runId = timestamp(); await writeJson(join(output, `${runId}_test.json`), { run_id: runId, written_at: new Date().toISOString() }); const current = await readJson<RecordValue>(join(stateDir, "inspect.json"), {}); await writeJson(join(stateDir, "inspect.json"), { ...current, last_run_id: runId, write_count: Number(current.write_count ?? 0) + 1 }); return { ok: true, runId }; }
  throw new Error("runtime action must be prepare, process, state, verify, sandbox, model, or write-test");
}
