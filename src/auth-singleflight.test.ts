import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { singleFlightLogin } from "./auth-singleflight.js";

describe("cross-process authorization single-flight", () => {
  test("only one caller starts authorization and the other reuses its result", async () => {
    const root = await mkdtemp(join(tmpdir(), "cxclaw-auth-test-"));
    const lockPath = join(root, "login.lock");
    let starts = 0;
    let completed: string | undefined;
    let releaseOwner!: () => void;
    let markOwnerStarted!: () => void;
    const ownerMayFinish = new Promise<void>(resolve => { releaseOwner = resolve; });
    const ownerStarted = new Promise<void>(resolve => { markOwnerStarted = resolve; });
    const runtime = { lockPath, sleep: async () => undefined };

    try {
      const owner = singleFlightLogin(async () => {
        starts += 1;
        markOwnerStarted();
        await ownerMayFinish;
        completed = "authorized-session";
        return completed;
      }, async () => {
        if (!completed) throw new Error("pending");
        return completed;
      }, runtime);

      await ownerStarted;
      const follower = singleFlightLogin(async () => {
        starts += 1;
        return "unexpected-second-login";
      }, async () => {
        if (!completed) throw new Error("pending");
        return completed;
      }, runtime);

      releaseOwner();
      expect(await owner).toBe("authorized-session");
      expect(await follower).toBe("authorized-session");
      expect(starts).toBe(1);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
