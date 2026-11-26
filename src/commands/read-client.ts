import { readFile, mkdir, mkdtemp, open, link, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { SolveaClient } from "../solvea/client.js";
import type { Session } from "../types.js";

// 参数先按每个公开命令的契约校验，handler 只接收校验后的值。
export type ReadParams = Record<string, any>;
type Parameter = { type: string; required?: boolean; default?: unknown };
export type ReadCommand = {
  parameters: Record<string, Parameter>;
  run: (client: ReadClient, params: ReadParams) => Promise<unknown>;
};
type PageOptions = {
  params?: ReadParams;
  body?: unknown;
  items_key?: string;
  page_key?: string;
  size_key?: string;
  total_key?: string;
  cursor?: boolean;
};
export class ReadContractError extends Error {}
export function pathSegment(value: unknown) {
  const raw = String(value);
  if (!raw || [".", ".."].includes(raw) || /[/\\?#%]/.test(raw))
    throw new ReadContractError("invalid path parameter");
  return encodeURIComponent(raw);
}
export function sanitize(
  value: unknown,
  allowedFields?: string[],
  metadataFields?: string[],
): unknown {
  if (Array.isArray(value))
    return value.map((item) => sanitize(item, allowedFields, metadataFields));
  if (value && typeof value === "object") {
    const source = value as ReadParams;
    const result: ReadParams = {};
    if (metadataFields && source.metadata) {
      let metadata = source.metadata;
      if (typeof metadata === "string") {
        try {
          metadata = JSON.parse(metadata);
        } catch {
          metadata = null;
        }
      }
      if (metadata && typeof metadata === "object" && !Array.isArray(metadata))
        result.configuration = sanitize(metadata, metadataFields);
    }
    for (const [key, item] of Object.entries(source)) {
      if (allowedFields && !allowedFields.includes(key)) continue;
      const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "");
      if (
        [
          "metadata",
          "headers",
          "requestheaders",
          "responseheaders",
          "authorization",
          "cookie",
          "authcode",
          "authurl",
          "authorizationurl",
          "authconfig",
        ].includes(normalized) ||
        /token|secret|password|credential|apikey|privatekey|appkey|authheader|accesskey/.test(
          normalized,
        )
      )
        continue;
      result[key] = sanitize(item);
    }
    return result;
  }
  return typeof value === "string"
    ? value.replace(/https?:\/\/[^\s<>"']+/gi, "[redacted-url]")
    : value;
}
function compact(value: unknown): any {
  if (value && typeof value === "object" && !Array.isArray(value))
    return Object.fromEntries(Object.entries(value).filter(([, item]) => item != null));
  return value;
}
function queryPath(path: string, params?: ReadParams) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(compact(params) ?? {}))
    for (const item of Array.isArray(value) ? value : [value]) query.append(key, String(item));
  return path + (query.size ? `?${query}` : "");
}
export class ReadClient {
  private readonly client: SolveaClient;
  source: { method?: string; path?: string } = {};
  pagination?: { pagesFetched: number; truncated: boolean; next: unknown };
  pageMetadata: unknown[] = [];
  downloaded = false;
  constructor(
    private readonly session: Session,
    readonly allPages = false,
    readonly maxPages = 20,
    readonly output?: string,
  ) {
    if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > 1000)
      throw new ReadContractError("max-pages must be between 1 and 1000");
    this.client = new SolveaClient(session);
  }
  async request(
    method: string,
    path: string,
    options: { params?: ReadParams; body?: unknown } = {},
  ): Promise<any> {
    this.source = { method, path };
    try {
      const payload = await this.client.request<unknown>(
        method,
        queryPath(path, options.params),
        compact(options.body),
        undefined,
        undefined,
        1,
        "error",
      );
      // 登录页面或空响应不能作为成功的业务结果。
      if (
        payload == null ||
        (typeof payload === "object" && !Array.isArray(payload) && "raw" in payload)
      )
        throw new ReadContractError("expected a JSON business response");
      return payload && typeof payload === "object" && !Array.isArray(payload) && "data" in payload
        ? payload.data
        : payload;
    } catch (error) {
      if (error instanceof ReadContractError) throw error;
      throw new ReadContractError(
        "request failed; check authorization, parameters and service availability",
      );
    }
  }
  async get(path: string, options: { params?: ReadParams } = {}) {
    if (this.allPages) throw new ReadContractError("this command does not support --all");
    return this.request("GET", path, options);
  }
  async post(path: string, options: { body?: unknown } = {}) {
    if (this.allPages) throw new ReadContractError("this command does not support --all");
    return this.request("POST", path, options);
  }
  async pages(method: string, path: string, options: PageOptions) {
    const {
      items_key: itemsKey = "list",
      page_key: pageKey = "page",
      size_key: sizeKey = "pageSize",
      total_key: totalKey = "total",
      cursor = false,
    } = options;
    const current = structuredClone(options.params ?? options.body) as ReadParams;
    const records: unknown[] = [],
      metadata: unknown[] = [],
      seen = new Set<string>();
    let data: any,
      more = false,
      next: unknown,
      pageCount = 0;
    for (pageCount = 1; pageCount <= (this.allPages ? this.maxPages : 1); pageCount++) {
      data = await this.request(
        method,
        path,
        options.params != null ? { params: current } : { body: current },
      );
      const items = itemsKey === "$" ? data : data?.[itemsKey];
      if (!Array.isArray(items))
        throw new ReadContractError("unexpected pagination response; cannot prove completeness");
      records.push(...items);
      if (data && typeof data === "object" && !Array.isArray(data))
        metadata.push(Object.fromEntries(Object.entries(data).filter(([key]) => key !== itemsKey)));
      if (cursor) {
        if (typeof data.hasMore !== "boolean")
          throw new ReadContractError("missing hasMore in cursor response");
        more = data.hasMore;
        next = data.nextCursor;
      } else {
        more = Number.isInteger(data?.[totalKey])
          ? current[pageKey] * current[sizeKey] < data[totalKey]
          : items.length >= current[sizeKey];
        next = current[pageKey] + 1;
      }
      if (!more || !this.allPages || pageCount === this.maxPages) break;
      const marker = JSON.stringify(next);
      if (next == null || seen.has(marker) || !items.length)
        throw new ReadContractError(
          "pagination did not advance; refusing an incomplete full result",
        );
      seen.add(marker);
      current[pageKey] = next;
    }
    this.pagination = { pagesFetched: pageCount, truncated: more, next: more ? next : null };
    this.pageMetadata = this.allPages ? metadata : [];
    return this.allPages ? records : data;
  }
  async download(path: string, options: { params?: ReadParams } = {}) {
    if (!this.output || this.allPages)
      throw new ReadContractError("file commands require --output and do not accept --all");
    const target = resolve(this.output);
    await mkdir(dirname(target), { recursive: true });
    const temporary = await mkdtemp(join(dirname(target), ".ticket-download-"));
    try {
      const tenant = this.session.tenant!;
      const response = await fetch(
        tenant.businessUrl!.replace(/\/$/, "") + queryPath(path, options.params),
        {
          headers: {
            accept: "*/*",
            cookie: `${tenant.environment === "prod" ? "_token" : "_token_staging"}=${tenant.businessToken}`,
          },
          redirect: "error",
          signal: AbortSignal.timeout(60_000),
        },
      );
      if (!response.ok || /json|text\/html/i.test(response.headers.get("content-type") ?? ""))
        throw new ReadContractError("expected a file but received an error or login response");
      if (!response.body) throw new ReadContractError("empty download");
      const handle = await open(join(temporary, "file"), "wx");
      let size = 0;
      try {
        for await (const chunk of response.body) {
          size += chunk.byteLength;
          if (size > 100 * 1024 * 1024) throw new ReadContractError("download exceeds byte limit");
          await handle.writeFile(chunk);
        }
      } finally {
        await handle.close();
      }
      if (!size) throw new ReadContractError("empty download");
      await link(join(temporary, "file"), target);
      this.downloaded = true;
      return { path: target, bytes: size, source: path };
    } catch (error) {
      if (error instanceof ReadContractError) throw error;
      throw new ReadContractError(
        "download failed; check output path, authorization and service availability",
      );
    } finally {
      await rm(temporary, { recursive: true, force: true });
    }
  }
}
export function validateParameters(command: ReadCommand, input: unknown): ReadParams {
  if (!input || typeof input !== "object" || Array.isArray(input))
    throw new ReadContractError("params must be a JSON object");
  const params = input as ReadParams,
    result: ReadParams = {};
  for (const name of Object.keys(params))
    if (!Object.hasOwn(command.parameters, name))
      throw new ReadContractError(`unknown parameter: ${name}`);
  const valid = (type: string, value: unknown): boolean => {
    if (type.endsWith("[]"))
      return Array.isArray(value) && value.every((item) => valid(type.slice(0, -2), item));
    if (type === "integer") return Number.isSafeInteger(value);
    if (type === "object") return !!value && typeof value === "object" && !Array.isArray(value);
    if (type === "array") return Array.isArray(value);
    return typeof value === type;
  };
  for (const [name, spec] of Object.entries(command.parameters)) {
    const supplied = Object.hasOwn(params, name);
    const value = supplied ? params[name] : spec.default;
    if (supplied && value == null) throw new ReadContractError(`omit unused parameter: ${name}`);
    if (spec.required && (value == null || value === ""))
      throw new ReadContractError(`missing parameter: ${name}`);
    if (value != null && !valid(spec.type, value))
      throw new ReadContractError(`${name} must be ${spec.type}`);
    result[name] = value;
  }
  return result;
}
export async function executeRead(
  session: Session,
  commands: Record<string, ReadCommand>,
  action: string,
  args: string[],
) {
  const command = Object.hasOwn(commands, action) ? commands[action] : undefined;
  if (!command) throw new ReadContractError(`unknown read action: ${action}`);
  const values: Record<string, string | boolean> = {};
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (key === "--all") {
      values[key] = true;
      continue;
    }
    if (
      !["--params-json", "--params-file", "--max-pages", "--output"].includes(key) ||
      !args[i + 1] ||
      args[i + 1].startsWith("--")
    )
      throw new ReadContractError(`unknown or incomplete option: ${key}`);
    if (Object.hasOwn(values, key)) throw new ReadContractError(`duplicate option: ${key}`);
    values[key] = args[++i];
  }
  if (values["--params-json"] && values["--params-file"])
    throw new ReadContractError("choose --params-json or --params-file");
  const input = JSON.parse(
    values["--params-file"]
      ? await readFile(String(values["--params-file"]), "utf8")
      : String(values["--params-json"] ?? "{}"),
  );
  const params = validateParameters(command, input);
  const output = values["--output"] ? resolve(String(values["--output"])) : undefined;
  const client = new ReadClient(
    session,
    values["--all"] === true,
    Number(values["--max-pages"] ?? 20),
    output,
  );
  const data = await command.run(client, params);
  if (client.downloaded) return data;
  const result = {
    command: action,
    data,
    source: client.source,
    fetchedAt: new Date().toISOString(),
    pageMetadata: sanitize(client.pageMetadata),
    ...(client.pagination ? { pagination: client.pagination } : {}),
  };
  if (output) {
    await mkdir(dirname(output), { recursive: true });
    await writeFile(output, JSON.stringify(result, null, 2), { flag: "wx" });
    return { path: output, pagination: client.pagination };
  }
  return result;
}
export function readActionDefinitions(
  commands: Record<string, ReadCommand>,
): Record<string, { command?: string; summary: string; usage: string }> {
  return Object.fromEntries(
    Object.entries(commands).map(([name, command]) => [
      name,
      {
        summary: name,
        usage: `[--params-json <json> | --params-file <path>] [--all] [--max-pages <n>] [--output <new-path>]\nJSON parameters: ${
          Object.entries(command.parameters)
            .map(
              ([key, value]) =>
                `${key}: ${value.type}${value.required ? " (required)" : ""}${value.default === undefined ? "" : ` = ${JSON.stringify(value.default)}`}`,
            )
            .join(", ") || "none"
        }`,
      },
    ]),
  );
}
