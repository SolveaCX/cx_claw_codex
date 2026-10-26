import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const agents = readFileSync("AGENTS.md", "utf8");
const guide = readFileSync("docs/releasing.md", "utf8");
const readme = readFileSync("README.md", "utf8");

describe("release documentation", () => {
  test("tells agents to use the stable release PR command", () => {
    expect(agents).toContain("bun run release:create patch");
    expect(agents).toContain("docs/releasing.md");
    expect(guide).toContain("release/vX.Y.Z");
  });

  test("forbids bypassing the reviewed stable release flow", () => {
    expect(agents).toContain("不要直接创建或推送稳定版 tag");
    expect(agents).toContain("不要直接运行 `npm publish`");
    expect(guide).toContain("不手工强推 `marketplace/stable`");
  });

  test("requires post-merge verification before reporting success", () => {
    for (const required of [
      "Publish workflow",
      "npm",
      "GitHub Release",
      "marketplace/stable",
      "cliVersion",
      "pluginVersion",
    ]) {
      expect(guide).toContain(required);
    }
    expect(agents).toContain("不能报告“已经发布”");
  });

  test("links the concise README entry to the complete guide", () => {
    expect(readme).toContain("[发布手册](./docs/releasing.md)");
    expect(readme).toContain("[`AGENTS.md`](./AGENTS.md)");
  });
});
