import { describe, expect, test } from "bun:test";
import { validateReleaseChannel } from "./validate-release-channel.js";

const validate = (overrides: Partial<Parameters<typeof validateReleaseChannel>[0]> = {}) =>
  validateReleaseChannel({
    version: "1.2.3",
    channel: "stable",
    eventName: "pull_request",
    prHeadRef: "release/v1.2.3",
    manifestVersions: ["1.2.3", "1.2.3", "1.2.3"],
    ...overrides,
  });

describe("release channel validation", () => {
  test("accepts a stable release PR", () => expect(() => validate()).not.toThrow());
  test("rejects a stable tag push", () =>
    expect(() => validate({ eventName: "push", prHeadRef: "" })).toThrow("tag pushes"));
  test("accepts a canary tag push", () =>
    expect(() =>
      validate({
        version: "1.2.4-canary.1",
        channel: "canary",
        eventName: "push",
        prHeadRef: "",
        manifestVersions: ["1.2.4-canary.1", "1.2.4-canary.1", "1.2.4-canary.1"],
      }),
    ).not.toThrow());
  test("rejects mismatched manifests", () =>
    expect(() => validate({ manifestVersions: ["1.2.3", "1.2.2", "1.2.3"] })).toThrow(
      "does not match manifests",
    ));
});
