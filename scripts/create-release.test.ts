import { describe, expect, test } from "bun:test";
import {
  releaseBranch,
  releasePullRequestBody,
  resolveReleaseVersion,
} from "./create-release.js";

describe("release creation", () => {
  test("calculates stable version bumps", () => {
    expect(resolveReleaseVersion("0.1.9", "patch")).toBe("0.1.10");
    expect(resolveReleaseVersion("0.1.9", "minor")).toBe("0.2.0");
    expect(resolveReleaseVersion("0.1.9", "major")).toBe("1.0.0");
  });

  test("accepts an explicit greater stable version", () => {
    expect(resolveReleaseVersion("0.1.9", "0.3.0")).toBe("0.3.0");
  });

  test("rejects invalid or non-increasing versions", () => {
    expect(() => resolveReleaseVersion("0.1.9", "canary")).toThrow();
    expect(() => resolveReleaseVersion("0.1.9", "0.1.9")).toThrow();
    expect(() => resolveReleaseVersion("0.1.9", "0.1.8")).toThrow();
    expect(() => resolveReleaseVersion("0.1.9-dev.1", "patch")).toThrow();
  });

  test("builds the reviewed stable release PR metadata", () => {
    expect(releaseBranch("0.1.10")).toBe("release/v0.1.10");
    const body = releasePullRequestBody("0.1.10");
    expect(body).toContain("@shulex/cxclawctl@0.1.10");
    expect(body).toContain("marketplace/stable");
  });
});
