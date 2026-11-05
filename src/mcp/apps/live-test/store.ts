import { randomUUID } from "node:crypto";
import { mkdir, readdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  LiveTestSnapshotSchema,
  TERMINAL_LIVE_TEST_STATUSES,
  type LiveTestSnapshot,
} from "./contract.js";

const RETENTION_MS = 24 * 60 * 60 * 1000;
const root = () =>
  process.env.CXCLAW_LIVE_TEST_STATE_DIR ??
  join(homedir(), ".cxclaw", "workspace", "state", "agent-tester", "live-test");
const safe = (value: string) => {
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) throw new Error("invalid state key");
  return value;
};

export class LiveTestStore {
  private updates = new Map<string, Promise<unknown>>();

  private path(profileId: string, testRunId: string) {
    return join(root(), safe(profileId), `${safe(testRunId)}.json`);
  }

  async create(
    identity: Pick<
      LiveTestSnapshot,
      "contextId" | "profileId" | "accountId" | "environment" | "agentId"
    >,
    turns: string[],
  ): Promise<LiveTestSnapshot> {
    const now = Date.now();
    const snapshot: LiveTestSnapshot = {
      ...identity,
      testRunId: `ltr_${randomUUID().replaceAll("-", "")}`,
      status: "queued",
      revision: 0,
      createdAt: now,
      updatedAt: now,
      truncated: false,
      turns: turns.map((user, index) => ({ index, user, assistant: "", status: "queued" })),
    };
    this.truncate(snapshot);
    await this.write(snapshot);
    return snapshot;
  }

  async read(profileId: string, testRunId: string): Promise<LiveTestSnapshot> {
    return LiveTestSnapshotSchema.parse(
      JSON.parse(await readFile(this.path(profileId, testRunId), "utf8")),
    );
  }

  async update(
    profileId: string,
    testRunId: string,
    mutate: (snapshot: LiveTestSnapshot) => void,
  ): Promise<LiveTestSnapshot> {
    const key = `${profileId}:${testRunId}`;
    const previous = this.updates.get(key) ?? Promise.resolve();
    const operation = previous.then(async () => {
      const snapshot = await this.read(profileId, testRunId);
      mutate(snapshot);
      snapshot.revision += 1;
      snapshot.updatedAt = Date.now();
      this.truncate(snapshot);
      await this.write(snapshot);
      return snapshot;
    });
    const settled = operation.catch(() => undefined);
    this.updates.set(key, settled);
    try {
      return await operation;
    } finally {
      if (this.updates.get(key) === settled) this.updates.delete(key);
    }
  }

  private truncate(snapshot: LiveTestSnapshot) {
    const size = () => Buffer.byteLength(JSON.stringify(snapshot));
    while (size() > 32 * 1024) {
      const candidates = snapshot.turns.flatMap((turn) => [
        { turn, field: "assistant" as const, length: turn.assistant.length },
        { turn, field: "user" as const, length: turn.user.length },
      ]);
      const longest = candidates.sort((a, b) => b.length - a.length)[0];
      if (!longest || longest.length <= 1) break;
      const current = longest.turn[longest.field];
      longest.turn[longest.field] = `${current.slice(0, Math.max(0, current.length - 1024))}…`;
      snapshot.truncated = true;
    }
  }

  private async write(snapshot: LiveTestSnapshot) {
    const path = this.path(snapshot.profileId, snapshot.testRunId);
    await mkdir(join(root(), safe(snapshot.profileId)), { recursive: true });
    const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
    await writeFile(temporary, `${JSON.stringify(snapshot)}\n`, { mode: 0o600 });
    await rename(temporary, path);
  }

  async recoverAndCleanup() {
    await mkdir(root(), { recursive: true });
    const now = Date.now();
    for (const profile of await readdir(root(), { withFileTypes: true })) {
      if (!profile.isDirectory()) continue;
      for (const file of await readdir(join(root(), profile.name))) {
        if (!file.endsWith(".json")) continue;
        const testRunId = file.slice(0, -5);
        try {
          const snapshot = await this.read(profile.name, testRunId);
          if (!TERMINAL_LIVE_TEST_STATUSES.has(snapshot.status))
            await this.update(profile.name, testRunId, (value) => {
              value.status = "interrupted";
              value.error = "MCP server restarted while the test was running";
              value.completedAt = Date.now();
            });
          else if (now - (snapshot.completedAt ?? snapshot.updatedAt) > RETENTION_MS)
            await unlink(this.path(profile.name, testRunId));
        } catch {
          // Ignore unreadable state here; a direct request still reports the error.
        }
      }
    }
  }
}
