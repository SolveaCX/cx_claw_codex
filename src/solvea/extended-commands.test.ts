import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import type { Session } from "../types.js";
import { SolveaClient } from "./client.js";
import { runExtendedCommand } from "./extended-commands.js";

const originalFetch = globalThis.fetch;
const temporaryPaths: string[] = [];
afterEach(async () => {
  globalThis.fetch = originalFetch;
  await Promise.all(temporaryPaths.splice(0).map((path) => rm(path, { force: true })));
});

const session: Session = {
  accessToken: "access",
  refreshToken: "refresh",
  accessExpiry: Date.now() + 60_000,
  employeeId: "employee",
  email: "employee@example.com",
  channel: "dev",
  tenant: {
    accountId: 1,
    accountCode: "test",
    accountName: "Test",
    environment: "staging",
    purpose: "test",
    businessUrl: "https://apps-staging.example",
    businessToken: "tenant-token",
    expiresAt: Date.now() + 60_000,
  },
};

describe("extended TypeScript business commands", () => {
  test("calls the managed AI Field paging endpoint", async () => {
    let request: { url: string; init?: RequestInit } | undefined;
    globalThis.fetch = (async (input, init) => {
      request = { url: String(input), init };
      return new Response(JSON.stringify({ code: 0, data: [] }), { status: 200 });
    }) as typeof fetch;

    await runExtendedCommand(new SolveaClient(session), "list-managed-ai-fields", [
      "--page",
      "2",
      "--page-size",
      "20",
      "--keyword",
      "order",
    ]);

    expect(request?.url).toEndWith("/api_v2/tars/api/field/manage/page");
    expect(request?.init?.method).toBe("POST");
    expect(JSON.parse(String(request?.init?.body))).toEqual({
      pageIndex: 2,
      pageSize: 20,
      name: "order",
    });
  });

  test("blocks destructive template deletion without confirmation", async () => {
    await expect(
      runExtendedCommand(new SolveaClient(session), "delete-templates", ["--ids", "1", "2"]),
    ).rejects.toThrow("--confirm-delete");
  });

  test("sends the complete template filters with the backend field names", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (input, init) => {
      requests.push({ url: String(input), init });
      const value = String(input).endsWith("/api_v2/gpt/bots")
        ? [{ projectId: 302 }]
        : { code: 0, data: [] };
      return new Response(JSON.stringify(value), { status: 200 });
    }) as typeof fetch;

    await runExtendedCommand(new SolveaClient(session), "list-templates", [
      "--page",
      "2",
      "--page-size",
      "25",
      "--keyword",
      "refund",
      "--directory-id",
      "0",
      "--scene",
      "voice_sms",
      "--status",
      "ENABLED",
      "--status",
      "DISABLED",
      "--source",
      "MANUAL",
      "--created-by",
      "7",
      "--created-at-gte",
      "1000",
      "--created-at-lte",
      "2000",
    ]);

    const request = requests.at(-1)!;
    expect(request.url).toEndWith("/api_v2/gpt/project/302/templates/filter");
    expect(JSON.parse(String(request.init?.body))).toEqual({
      pageIndex: 2,
      pageSize: 25,
      keyword: "refund",
      directoryId: 0,
      scenes: ["voice_sms"],
      status: ["ENABLED", "DISABLED"],
      sources: ["MANUAL"],
      createdBys: [7],
      createdAtGte: 1000,
      createdAtLte: 2000,
    });
  });

  test("maps every template management command to its request contract", async () => {
    await mkdir("_tmp_", { recursive: true });
    const importFile = `_tmp_/template-import-${Date.now()}.xlsx`;
    const downloadFile = `_tmp_/template-download-${Date.now()}.xlsx`;
    temporaryPaths.push(importFile, downloadFile);
    await writeFile(importFile, "xlsx");

    const cases: Array<{
      command: string;
      args: string[];
      method: string;
      suffix: string;
      body?: unknown;
    }> = [
      { command: "get-template", args: ["--id", "9"], method: "GET", suffix: "/template/9" },
      {
        command: "list-template-options",
        args: [],
        method: "GET",
        suffix: "/templates/simple",
      },
      {
        command: "get-template-config",
        args: [],
        method: "GET",
        suffix: "/templates/config",
      },
      {
        command: "create-template",
        args: ["--name", "N", "--content", "C", "--directory-id", "8"],
        method: "POST",
        suffix: "/template",
        body: {
          name: "N",
          content: "C",
          status: "ENABLED",
          multiContent: { AUTO: "C" },
          directoryId: 8,
        },
      },
      {
        command: "update-template",
        args: ["--id", "9", "--status", "DISABLED", "--directory-id", "0"],
        method: "PUT",
        suffix: "/template/9",
        body: { status: "DISABLED", directoryId: 0 },
      },
      {
        command: "batch-update-templates",
        args: ["--data", '{"list":[{"id":9,"status":"ENABLED"}]}'],
        method: "PUT",
        suffix: "/templates",
        body: { list: [{ id: 9, status: "ENABLED" }] },
      },
      {
        command: "move-templates",
        args: ["--ids", "9", "10", "--directory-id", "8"],
        method: "PUT",
        suffix: "/templates/directory",
        body: { templateIds: [9, 10], directoryId: 8 },
      },
      {
        command: "delete-templates",
        args: ["--ids", "9", "--confirm-delete"],
        method: "DELETE",
        suffix: "/templates",
        body: { templateIds: [9] },
      },
      {
        command: "list-template-directories",
        args: [],
        method: "GET",
        suffix: "/template-directories/tree",
      },
      {
        command: "get-template-directory",
        args: ["--id", "8"],
        method: "GET",
        suffix: "/template-directory/8",
      },
      {
        command: "create-template-directory",
        args: ["--name", "FAQ", "--parent-id", "0"],
        method: "POST",
        suffix: "/template-directory",
        body: { name: "FAQ", parentId: 0 },
      },
      {
        command: "update-template-directory",
        args: ["--id", "8", "--name", "Support", "--parent-id", "3"],
        method: "PUT",
        suffix: "/template-directory/8",
        body: { name: "Support", parentId: 3 },
      },
      {
        command: "delete-template-directory",
        args: ["--id", "8", "--confirm-delete"],
        method: "DELETE",
        suffix: "/template-directory/8",
      },
      {
        command: "download-template-import-file",
        args: ["--output", downloadFile],
        method: "GET",
        suffix: "/templates/import-template",
      },
      {
        command: "import-templates-file",
        args: ["--file", importFile],
        method: "POST",
        suffix: "/templates/import",
      },
      {
        command: "export-templates",
        args: ["--directory-id", "8", "--status", "ENABLED"],
        method: "POST",
        suffix: "/templates/export/async",
        body: { directoryId: 8, status: ["ENABLED"] },
      },
      {
        command: "get-template-export-tasks",
        args: ["--page", "2", "--page-size", "10"],
        method: "POST",
        suffix: "/getLabelTask",
        body: { page: 2, pageSize: 10, taskType: "EXPORT_TEMPLATE" },
      },
      {
        command: "translate-template-contents",
        args: ["--target-language", "ENGLISH", "--data", '{"contents":["您好"]}'],
        method: "POST",
        suffix: "/templates/translate",
        body: { contents: ["您好"], targetLanguage: "ENGLISH" },
      },
    ];

    for (const item of cases) {
      const requests: Array<{ url: string; init?: RequestInit }> = [];
      globalThis.fetch = (async (input, init) => {
        requests.push({ url: String(input), init });
        const value = String(input).endsWith("/api_v2/gpt/bots")
          ? [{ projectId: 302 }]
          : { code: 0, data: [] };
        return new Response(JSON.stringify(value), { status: 200 });
      }) as typeof fetch;

      await runExtendedCommand(new SolveaClient(session), item.command, item.args);

      const request = requests.at(-1)!;
      expect(request.url).toEndWith(item.suffix);
      expect(request.init?.method ?? "GET").toBe(item.method);
      if (item.body !== undefined)
        expect(JSON.parse(String(request.init?.body))).toEqual(item.body);
      if (item.command === "import-templates-file")
        expect(request.init?.body).toBeInstanceOf(FormData);
    }
  });

  test("blocks recursive template directory deletion without confirmation", async () => {
    await expect(
      runExtendedCommand(new SolveaClient(session), "delete-template-directory", ["--id", "8"]),
    ).rejects.toThrow("--confirm-delete");
  });

  test("rejects unsafe mock data path segments before a request", async () => {
    await expect(
      runExtendedCommand(new SolveaClient(session), "query-mock-data", ["--name", "../secret"]),
    ).rejects.toThrow("safe non-empty path segment");
  });
});
