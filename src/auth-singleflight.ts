import { createHash } from "node:crypto";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

const userScope = createHash("sha256").update(homedir()).digest("hex").slice(0, 16);
const defaultLockPath = join(tmpdir(), `cxclaw-auth-login-${userScope}.lock`);
const defaultLockTtlMs = 15 * 60 * 1000;

interface LoginLockRuntime {
  lockPath: string;
  lockTtlMs: number;
  now: () => number;
  pid: number;
  isAlive: (pid: number) => boolean;
  sleep: (ms: number) => Promise<unknown>;
}

const defaultRuntime: LoginLockRuntime = {
  lockPath: defaultLockPath,
  lockTtlMs: defaultLockTtlMs,
  now: Date.now,
  pid: process.pid,
  isAlive: (pid) => {
    try {
      process.kill(pid, 0);
      return true;
    } catch (error) {
      return (error as NodeJS.ErrnoException).code === "EPERM";
    }
  },
  sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),
};

async function removeStaleLock(runtime: LoginLockRuntime): Promise<boolean> {
  try {
    const owner = JSON.parse(await readFile(join(runtime.lockPath, "owner.json"), "utf8")) as {
      pid?: number;
      expiresAt?: number;
    };
    if (Number.isInteger(owner.pid) && Number(owner.expiresAt) > runtime.now() && runtime.isAlive(owner.pid!)) {
      return false;
    }
  } catch {
    // A creator may still be writing owner.json. Only reap a directory that
    // has remained incomplete long enough to prove its creator disappeared.
    const directory = await stat(runtime.lockPath).catch(() => undefined);
    if (!directory || runtime.now() - directory.mtimeMs < 5_000) return false;
  }
  await rm(runtime.lockPath, { recursive: true, force: true });
  return true;
}

export async function singleFlightLogin<T>(
  operation: () => Promise<T>,
  readCompletedLogin: () => Promise<T>,
  overrides: Partial<LoginLockRuntime> = {},
): Promise<T> {
  const runtime = { ...defaultRuntime, ...overrides };
  const deadline = runtime.now() + runtime.lockTtlMs;
  let observedAnotherLogin = false;

  while (runtime.now() < deadline) {
    if (observedAnotherLogin) {
      try {
        return await readCompletedLogin();
      } catch {
        // The owner has not persisted the completed login yet.
      }
    }

    try {
      await mkdir(runtime.lockPath, { mode: 0o700 });
      await writeFile(join(runtime.lockPath, "owner.json"), JSON.stringify({
        pid: runtime.pid,
        expiresAt: runtime.now() + runtime.lockTtlMs,
      }), { mode: 0o600 });
      try {
        return await operation();
      } finally {
        await rm(runtime.lockPath, { recursive: true, force: true });
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      observedAnotherLogin = true;
      await removeStaleLock(runtime);
      await runtime.sleep(500);
    }
  }

  throw new Error("timed out waiting for another CXClaw authorization");
}
