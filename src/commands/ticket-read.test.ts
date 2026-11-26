import { afterEach, describe, expect, spyOn, test } from "bun:test";
import * as fs from "node:fs/promises";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import fixtures from "./fixtures/ticket-read-parity.json" with { type: "json" };
import { ticketCommands } from "./ticket.js";
import { integrationCommands } from "./integration.js";
import { executeRead, ReadClient, validateParameters } from "./read-client.js";
import { resourceHelp } from "./resources.js";
import type { Session } from "../types.js";
const session = {
  tenant: {
    businessUrl: "https://example.test",
    businessToken: "test-secret",
    environment: "prod",
  },
} as Session;
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});
const response = (data: unknown) =>
  new Response(JSON.stringify({ code: 200, data }), {
    headers: { "content-type": "application/json" },
  });

describe("online read contract parity", () => {
  test("registers 113 ticket and 79 integration commands without writes", () => {
    expect(Object.keys(ticketCommands)).toHaveLength(113);
    expect(Object.keys(integrationCommands)).toHaveLength(79);
    for (const name of ["reply", "bind-tags", "delete", "whatsapp-test", "zendesk-auth-start"])
      expect(ticketCommands[name] ?? integrationCommands[name]).toBeUndefined();
    expect(resourceHelp("ticket", "get")).toContain("ticketNumber: string (required)");
  });
  for (const fixture of fixtures)
    test(`${fixture.domain} ${fixture.action}`, async () => {
      const commands = fixture.domain === "ticket" ? ticketCommands : integrationCommands;
      const expected = fixture.request as Record<string, any>;
      let called = false;
      const client = new ReadClient(session);
      globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        called = true;
        const url = new URL(String(input));
        expect(url.pathname).toBe(expected.path);
        expect(init?.method ?? "GET").toBe(expected.method);
        if (expected.params) {
          const query = new URLSearchParams();
          for (const [key, value] of Object.entries(expected.params))
            for (const item of Array.isArray(value) ? value : [value])
              query.append(key, String(item));
          expect([...url.searchParams]).toEqual([...query]);
        } else expect(url.search).toBe("");
        if (expected.body !== undefined)
          expect(JSON.parse(String(init?.body))).toEqual(expected.body);
        else expect(init?.body).toBeUndefined();
        expect(new Headers(init?.headers).get("cookie")).toBe("_token=test-secret");
        expect(init?.redirect).toBe("error");
        const key = expected.items_key ?? "list";
        return response(
          expected.kind === "pages"
            ? key === "$"
              ? []
              : { [key]: [], hasMore: false, total: 0 }
            : {},
        );
      }) as unknown as typeof fetch;
      if (expected.kind === "download") {
        client.download = async (path, options) => {
          called = true;
          expect(path).toBe(expected.path);
          expect(options?.params).toEqual(expected.params);
          return { path, bytes: 1, source: path };
        };
      }
      await commands[fixture.action].run(
        client,
        validateParameters(commands[fixture.action], fixture.params),
      );
      expect(called).toBe(true);
    });
});
test("rejects invalid inputs and unavailable mutations before HTTP", async () => {
  let calls = 0;
  globalThis.fetch = (async () => {
    calls++;
    return response({});
  }) as unknown as typeof fetch;
  for (const params of [
    { ticketNumber: "../delete" },
    { ticketNumber: "a", tenantId: 99 },
    { ticketNumber: null },
    { ticketNumber: 1 },
  ])
    await expect(
      executeRead(session, ticketCommands, "get", ["--params-json", JSON.stringify(params)]),
    ).rejects.toThrow();
  await expect(executeRead(session, ticketCommands, "reply", [])).rejects.toThrow();
  await expect(
    executeRead(session, ticketCommands, "list", ["--params-json", '{"pageSize":101}']),
  ).rejects.toThrow();
  expect(calls).toBe(0);
});
test("cursor pagination, truncation and repeated cursor failures", async () => {
  let page = 0;
  globalThis.fetch = (async () =>
    response(
      ++page === 1
        ? { items: [{ id: 1 }], hasMore: true, nextCursor: "next" }
        : { items: [{ id: 2 }], hasMore: false },
    )) as unknown as typeof fetch;
  const args = ["--params-json", '{"ticketNumber":"one"}', "--all"];
  const result = (await executeRead(session, ticketCommands, "messages", args)) as any;
  expect(result.data).toEqual([{ id: 1 }, { id: 2 }]);
  expect(result.pagination.truncated).toBe(false);
  page = 0;
  const bounded = (await executeRead(session, ticketCommands, "messages", [
    ...args,
    "--max-pages",
    "1",
  ])) as any;
  expect(bounded.pagination).toEqual({ pagesFetched: 1, truncated: true, next: "next" });
  globalThis.fetch = (async () =>
    response({ items: [{ id: 1 }], hasMore: true, nextCursor: "same" })) as unknown as typeof fetch;
  await expect(executeRead(session, ticketCommands, "messages", args)).rejects.toThrow(
    "did not advance",
  );
});
for (const mode of [[], ["--all"], ["--all", "--max-pages", "1"]]) {
  for (const [command, params] of [
    ["messages", { ticketNumber: "one", before: "X" }],
    ["admin-trigger-executions", { ticketId: "1", before: 0 }],
  ] as const) {
    test(`rejects unchanged initial cursor for ${command} ${mode.join(" ")}`, async () => {
      const cursors: string[] = [];
      globalThis.fetch = (async (input: RequestInfo | URL) => {
        cursors.push(new URL(String(input)).searchParams.get("before")!);
        return response({ items: [{ id: 1 }], hasMore: true, nextCursor: params.before });
      }) as unknown as typeof fetch;
      await expect(
        executeRead(session, ticketCommands, command, [
          "--params-json",
          JSON.stringify(params),
          ...mode,
        ]),
      ).rejects.toThrow("did not advance");
      expect(cursors).toEqual([String(params.before)]);
    });
  }
}
for (const initial of [undefined, "X"]) {
  test(`rejects cursor cycle at page limit from ${initial}`, async () => {
    const cursors: (string | null)[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      cursors.push(new URL(String(input)).searchParams.get("before"));
      return response({
        items: [{ id: cursors.length }],
        hasMore: true,
        nextCursor: cursors.length === 1 ? "Y" : (initial ?? "Y"),
      });
    }) as unknown as typeof fetch;
    await expect(
      executeRead(session, ticketCommands, "messages", [
        "--params-json",
        JSON.stringify({ ticketNumber: "one", before: initial }),
        "--all",
        "--max-pages",
        "2",
      ]),
    ).rejects.toThrow("did not advance");
    expect(cursors).toEqual([initial ?? null, "Y"]);
  });
}
for (const allPages of [false, true]) {
  for (const more of [false, true]) {
    test(`preserves valid continuation and terminal page: all=${allPages}, more=${more}`, async () => {
      const cursors: string[] = [];
      globalThis.fetch = (async (input: RequestInfo | URL) => {
        cursors.push(new URL(String(input)).searchParams.get("before")!);
        return response({ items: [{ id: 1 }], hasMore: more, nextCursor: more ? "Y" : "X" });
      }) as unknown as typeof fetch;
      const result = (await executeRead(session, ticketCommands, "messages", [
        "--params-json",
        '{"ticketNumber":"one","before":"X"}',
        ...(allPages ? ["--all"] : []),
        "--max-pages",
        "1",
      ])) as any;
      expect(cursors).toEqual(["X"]);
      expect(result.pagination).toEqual({
        pagesFetched: 1,
        truncated: more,
        next: more ? "Y" : null,
      });
      expect(allPages ? result.data : result.data.items).toEqual([{ id: 1 }]);
    });
  }
}
test("projects metadata and removes nested secrets and signed URLs", async () => {
  globalThis.fetch = (async () =>
    response([
      {
        id: 1,
        unknownSecret: "secret",
        metadata: JSON.stringify({ botId: 2, apiKey: "secret", replyTimeoutMs: 10 }),
        authUrl: "https://secret.test",
        other: "secret",
      },
    ])) as unknown as typeof fetch;
  const result = (await executeRead(session, integrationCommands, "custom-ticket-list", [])) as any;
  expect(result.data).toEqual([{ id: 1, configuration: { botId: 2, replyTimeoutMs: 10 } }]);
});
test("rejects non-JSON and business error responses without echoing secrets", async () => {
  for (const value of [
    new Response("<html>login</html>"),
    new Response(JSON.stringify({ code: 403, message: "private-token" })),
  ]) {
    globalThis.fetch = (async () => value) as unknown as typeof fetch;
    try {
      await executeRead(session, ticketCommands, "get", [
        "--params-json",
        '{"ticketNumber":"one"}',
      ]);
      throw Error("unexpected success");
    } catch (error) {
      expect(String(error)).not.toContain("private-token");
      expect(String(error)).not.toContain("unexpected success");
    }
  }
});
for (const mode of ["success", "write-failure", "collision"] as const) {
  test(`publishes JSON snapshots atomically: ${mode}`, async () => {
    const dir = await mkdtemp(join(tmpdir(), "ticket-snapshot-test-"));
    const target = join(dir, "snapshot.json");
    const args = ["--params-json", '{"ticketNumber":"one"}', "--output", target];
    const originalWrite = fs.writeFile;
    const write = spyOn(fs, "writeFile").mockImplementationOnce(async (path, data, options) => {
      expect(String(path)).not.toBe(target);
      expect(existsSync(target)).toBe(false);
      if (mode === "write-failure") {
        await originalWrite(path, '{"data":', options);
        throw new Error("simulated full disk");
      }
      await originalWrite(path, data, options);
      expect(existsSync(target)).toBe(false);
      if (mode === "collision") await originalWrite(target, "existing snapshot");
    });
    globalThis.fetch = (async () => response({ subject: "客服工单" })) as unknown as typeof fetch;
    try {
      if (mode === "success") {
        expect(await executeRead(session, ticketCommands, "get", args)).toEqual({
          path: target,
          pagination: undefined,
        });
        expect(JSON.parse(await readFile(target, "utf8")).data).toEqual({ subject: "客服工单" });
      } else {
        await expect(executeRead(session, ticketCommands, "get", args)).rejects.toThrow();
      }
      expect(write).toHaveBeenCalledTimes(1);
      write.mockRestore();
      if (mode === "write-failure") {
        expect(await fs.readdir(dir)).toEqual([]);
        await executeRead(session, ticketCommands, "get", args);
        expect(JSON.parse(await readFile(target, "utf8")).data).toEqual({ subject: "客服工单" });
      } else if (mode === "collision") {
        expect(await readFile(target, "utf8")).toBe("existing snapshot");
      }
      expect(await fs.readdir(dir)).toEqual(["snapshot.json"]);
      const saved = await readFile(target, "utf8");
      await expect(executeRead(session, ticketCommands, "get", args)).rejects.toThrow();
      expect(await readFile(target, "utf8")).toBe(saved);
      expect(await fs.readdir(dir)).toEqual(["snapshot.json"]);
    } finally {
      write.mockRestore();
      await rm(dir, { recursive: true, force: true });
    }
  });
}
test("downloads files atomically without overwriting or accepting login pages", async () => {
  const dir = await mkdtemp(join(tmpdir(), "ticket-read-"));
  const path = join(dir, "export.xlsx");
  try {
    globalThis.fetch = (async () =>
      new Response("binary-file", {
        headers: { "content-type": "application/octet-stream" },
      })) as unknown as typeof fetch;
    const client = new ReadClient(session, false, 20, path);
    await client.download("/export");
    expect(await readFile(path, "utf8")).toBe("binary-file");
    await expect(client.download("/export")).rejects.toThrow();
    expect(await readFile(path, "utf8")).toBe("binary-file");
    globalThis.fetch = (async () =>
      new Response("login", {
        headers: { "content-type": "text/html" },
      })) as unknown as typeof fetch;
    await expect(
      new ReadClient(session, false, 20, join(dir, "bad")).download("/export"),
    ).rejects.toThrow("expected a file");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
