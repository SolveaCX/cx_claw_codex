import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { option, options } from "../args.js";

export type JsonObject = Record<string, unknown>;

export const workspaceRoot = () => resolve(process.env.CXCLAW_WORKSPACE ?? join(homedir(), ".cxclaw", "workspace"));
export const stateRoot = (domain: string) => resolve(process.env.CXCLAW_STATE_DIR ?? join(workspaceRoot(), "state"), domain);
export const outputRoot = (domain: string) => resolve(process.env.CXCLAW_OUTPUT_DIR ?? join(workspaceRoot(), "outputs"), domain);

export async function ensureParent(file: string) { await mkdir(dirname(file), { recursive: true }); }
export async function ensureDir(directory: string) { await mkdir(directory, { recursive: true }); }

export async function readJson<T = unknown>(file: string): Promise<T> {
  return JSON.parse(await readFile(file, "utf8")) as T;
}

export async function writeJson(file: string, value: unknown) {
  await ensureParent(file);
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function readJsonOption<T extends JsonObject = JsonObject>(args: string[], required = true): Promise<T> {
  const file = option(args, "--data-file");
  const inline = option(args, "--data");
  if (!file && !inline) {
    if (!required) return {} as T;
    throw new Error("--data or --data-file is required");
  }
  const value = JSON.parse(file ? await readFile(file, "utf8") : inline!) as unknown;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("data must be a JSON object");
  return value as T;
}

export async function readJsonValue(args: string[], required = true): Promise<unknown> {
  const file = option(args, "--data-file") ?? option(args, "--input");
  const inline = option(args, "--data");
  if (!file && !inline) {
    if (!required) return undefined;
    throw new Error("--data, --data-file, or --input is required");
  }
  return JSON.parse(file ? await readFile(file, "utf8") : inline!);
}

export function intOption(args: string[], name: string, fallback: number) {
  const raw = option(args, name);
  if (raw === undefined) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${name} must be a number`);
  return value;
}

export function boolOption(args: string[], enable: string, disable: string, fallback = true) {
  const on = args.includes(enable), off = args.includes(disable);
  if (on && off) throw new Error(`${enable} and ${disable} cannot be used together`);
  return on ? true : off ? false : fallback;
}

export function repeated(args: string[], name: string) { return options(args, name); }

export function safeJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function htmlEscape(value: unknown) {
  return String(value ?? "").replace(/[&<>\"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[char]!));
}

export async function writeHtml(file: string, title: string, body: string) {
  await ensureParent(file);
  await writeFile(file, `<!doctype html><html><head><meta charset="utf-8"><title>${htmlEscape(title)}</title><style>body{font-family:system-ui,sans-serif;margin:2rem;line-height:1.5}pre{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px}.card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}</style></head><body><h1>${htmlEscape(title)}</h1>${body}</body></html>`, "utf8");
}

export function asRows(value: unknown): JsonObject[] {
  if (Array.isArray(value)) return value.filter(item => item && typeof item === "object") as JsonObject[];
  if (value && typeof value === "object") {
    const object = value as JsonObject;
    for (const key of ["list", "rows", "items", "data", "records", "result"]) {
      if (Array.isArray(object[key])) return object[key]!.filter(item => item && typeof item === "object") as JsonObject[];
    }
  }
  return [];
}

export function pickString(row: JsonObject, keys: string[], fallback = "") {
  for (const key of keys) if (row[key] !== undefined && row[key] !== null) return String(row[key]);
  return fallback;
}
