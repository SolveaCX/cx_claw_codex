import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const markerRoot = join(tmpdir(), "cxclaw-auth-wait");
const markerTtlMs = 15 * 60 * 1000;

const markerName = (sessionId, pid) =>
  `${createHash("sha256").update(sessionId).digest("hex").slice(0, 24)}-${pid}.json`;

const isAlive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
};

export async function withAuthWaitMarker(operation, env = process.env) {
  const sessionId = env.CODEX_SESSION_ID ?? env.CODEX_THREAD_ID;
  if (!sessionId) return operation();

  await mkdir(markerRoot, { recursive: true, mode: 0o700 });
  const path = join(markerRoot, markerName(sessionId, process.pid));
  await writeFile(path, JSON.stringify({
    sessionId,
    threadId: env.CODEX_THREAD_ID ?? null,
    pid: process.pid,
    expiresAt: Date.now() + markerTtlMs,
  }), { mode: 0o600 });
  try {
    return await operation();
  } finally {
    await rm(path, { force: true }).catch(() => undefined);
  }
}

export async function hasActiveAuthWait(sessionId, now = Date.now()) {
  if (!sessionId) return false;
  const names = await readdir(markerRoot).catch(() => []);
  for (const name of names) {
    const path = join(markerRoot, name);
    try {
      const marker = JSON.parse(await readFile(path, "utf8"));
      const active = marker.sessionId === sessionId &&
        Number.isInteger(marker.pid) && marker.expiresAt > now && isAlive(marker.pid);
      if (active) return true;
      if (marker.expiresAt <= now || !isAlive(marker.pid)) await rm(path, { force: true });
    } catch {
      await rm(path, { force: true }).catch(() => undefined);
    }
  }
  return false;
}
