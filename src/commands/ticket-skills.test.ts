import { expect, test } from "bun:test";
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { ticketCommands } from "./ticket.js";
import { integrationCommands } from "./integration.js";
import { resources } from "./resources.js";
const root = join(import.meta.dirname, "../..");
const walk = (path: string): string[] =>
  readdirSync(path, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? walk(join(path, d.name)) : [join(path, d.name)],
  );
test("four skills document every registered read capability and use executable plugin paths", () => {
  let combined = "";
  for (const name of ["ticket-helper", "ticket-analytics", "ticket-admin", "integrations"]) {
    const skill = readFileSync(join(root, "skills", name, "SKILL.md"), "utf8");
    expect(skill).toContain(`name: ${name}`);
    expect(skill).toContain("../cxclawctl/SKILL.md");
    expect(skill).toContain("--context <contextId>");
    for (const path of walk(join(root, "skills", name)).filter((p) => p.endsWith(".md"))) {
      const text = readFileSync(path, "utf8");
      combined += text;
      for (const legacy of [
        "/skill-lib/",
        "python3 /skills/",
        "/workspace/",
        "solvea-desk",
        "requires:",
      ])
        expect(text).not.toContain(legacy);
      for (const match of text.matchAll(/<PLUGIN_ROOT>\/(skills\/[^`\s]+\.md)/g))
        expect(existsSync(join(root, match[1]))).toBe(true);
      for (const match of text.matchAll(
        /`(?:node "<PLUGIN_ROOT>\/plugin-cli.mjs" )?(ticket|integration) ([a-z][a-z0-9-]+)/g,
      )) {
        const commands = match[1] === "ticket" ? ticketCommands : integrationCommands;
        expect(Object.hasOwn(commands, match[2])).toBe(true);
      }
    }
  }
  for (const [domain, commands] of [
    ["ticket", ticketCommands],
    ["integration", integrationCommands],
  ] as const)
    for (const name of Object.keys(commands)) expect(combined).toContain(`${domain} ${name}`);
  expect(existsSync(join(root, "skills/solvea-desk"))).toBe(false);
  expect(Object.hasOwn(resources, "ticket")).toBe(true);
  expect(Object.hasOwn(resources, "integration")).toBe(true);
});
test("user-facing descriptions match the agreed product vocabulary", () => {
  const description = (name: string) =>
    readFileSync(join(root, "skills", name, "SKILL.md"), "utf8")
      .split("\n")
      .find((l) => l.startsWith("description:"))!;
  expect(description("agent-analytics")).toContain("Inbox（Agent 会话记录）");
  expect(description("agent-analytics")).not.toContain("由 shulex-support 主责");
  expect(description("shulex-support")).toContain("售后工单（产品支持工单）");
  expect(description("shulex-support")).not.toContain("走 agent-analytics");
  expect(description("integrations")).not.toContain("Agent 域集成助手");
  expect(description("integrations")).not.toContain("首期不执行");
  for (const name of ["ticket-helper", "ticket-analytics", "ticket-admin"]) {
    expect(description(name)).toMatch(/客服工单|工单系统/);
    expect(description(name)).not.toMatch(/Tars|Desk/);
  }
});
