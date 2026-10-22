import { readFile } from "node:fs/promises";
import { flag, option } from "../args.js";

export type JsonObject = Record<string, unknown>;

export async function jsonData(args: string[], required = true): Promise<JsonObject> {
  const file = option(args, "--data-file");
  const raw = file ? await readFile(file, "utf8") : option(args, "--data");
  if (!raw) {
    if (required) throw new Error("--data or --data-file is required");
    return {};
  }
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("request data must be a JSON object");
  return parsed as JsonObject;
}

export async function jsonValue(args: string[]): Promise<unknown> {
  const file = option(args, "--data-file");
  const raw = file ? await readFile(file, "utf8") : option(args, "--data", true)!;
  return JSON.parse(raw) as unknown;
}

export function requireFlag(args: string[], name: string, command: string) {
  if (!flag(args, name)) throw new Error(`${command} requires ${name} after explicit user acknowledgement`);
}

export function requireId(args: string[]) { return option(args, "--id", true)!; }

export function enabled(args: string[], command: string) {
  const enable = flag(args, "--enable");
  const disable = flag(args, "--disable");
  if (enable === disable) throw new Error(`${command} requires exactly one of --enable or --disable`);
  return enable;
}
