import { describe, expect, test } from "bun:test";
import { schedulerInvocation } from "./update.js";

describe("scheduled updater command", () => {
  test("uses absolute Node and npm paths", () => {
    const invocation = schedulerInvocation(
      { npm_execpath: "/opt/node/lib/node_modules/npm/bin/npm-cli.js" },
      "/opt/node/bin/node",
    );
    expect(invocation.command).toBe("/opt/node/bin/node");
    expect(invocation.args).toEqual([
      "/opt/node/lib/node_modules/npm/bin/npm-cli.js",
      "exec",
      "--yes",
      "--package=@shulex/cxclawctl@latest",
      "--",
      "cxclawctl",
      "update",
      "--scheduled",
    ]);
  });

  test("rejects a scheduler without an absolute npm entrypoint", () => {
    expect(() => schedulerInvocation({ npm_execpath: "npm" }, "/usr/bin/node")).toThrow(
      "npm_execpath",
    );
  });
});
