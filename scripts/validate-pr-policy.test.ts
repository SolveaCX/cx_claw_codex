import { describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";

function validate(head: string, base = "main", title = "fix: update guidance") {
  return spawnSync(process.execPath, ["scripts/validate-pr-policy.ts"], {
    encoding: "utf8",
    env: { ...process.env, PR_HEAD_REF: head, PR_BASE_REF: base, PR_TITLE: title },
  });
}

describe("PR branch policy", () => {
  test("accepts development branches without a personal prefix or date", () => {
    for (const branch of [
      "fix/kb-qa-batch-guidance",
      "feat/batch-analysis",
      "docs-update",
      "cxj/261112/topic",
    ]) {
      expect(validate(branch).status).toBe(0);
    }
  });

  test("requires main as the target", () => {
    const result = validate("fix/topic", "staging");
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("pull requests must target main");
  });

  test("reserves release branches and titles for the release workflow", () => {
    expect(validate("release/invalid").stderr).toContain("must match release/vX.Y.Z");
    expect(validate("release/v1.2.3").stderr).toContain("requires PR title");
    expect(validate("fix/topic", "main", "chore(release): 发布1.2.3").stderr).toContain(
      "release PR title is only allowed",
    );
  });
});
