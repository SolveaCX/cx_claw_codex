import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const workflow = readFileSync(".github/workflows/publish.yml", "utf8");

describe("publish workflow", () => {
  test("publishes stable releases only from release PRs", () => {
    expect(workflow).toContain("startsWith(github.event.pull_request.head.ref, 'release/v')");
    expect(workflow).toContain('tags:\n      - "v*-*"');
  });

  test("uses npm latest for the stable Marketplace channel", () => {
    expect(workflow).toContain('if [[ "$CHANNEL" == "stable" ]]');
    expect(workflow).toContain('echo "dist_tag=latest"');
  });

  test("fails closed when npm credentials are missing", () => {
    expect(workflow).toContain("::error::NPM_TOKEN is not configured");
    expect(workflow).toContain('echo "::error::NPM_TOKEN is not configured"\n            exit 1');
  });

  test("publishes the Shulex scoped CLI package", () => {
    expect(workflow).toContain('npm view "@shulex/cxclawctl@${VERSION}"');
    expect(workflow).toContain('npm dist-tag add "@shulex/cxclawctl@${VERSION}"');
  });

  test("advances Marketplace only after npm and GitHub Release", () => {
    const npm = workflow.indexOf("name: Publish npm package");
    const release = workflow.indexOf("name: Create or update GitHub Release");
    const marketplace = workflow.indexOf("name: Advance Marketplace channel");
    expect(npm).toBeGreaterThan(0);
    expect(release).toBeGreaterThan(npm);
    expect(marketplace).toBeGreaterThan(release);
  });

  test("waits for the npm package to become publicly readable", () => {
    const polling = workflow.indexOf('npm view "@shulex/cxclawctl@${VERSION}" version');
    const release = workflow.indexOf("name: Create or update GitHub Release");
    expect(polling).toBeGreaterThan(0);
    expect(workflow).toContain("still unavailable from the public registry");
    expect(release).toBeGreaterThan(polling);
  });
});
