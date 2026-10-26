import { AsyncEntry } from "@napi-rs/keyring";
import type { Session } from "./types.js";

const options = process.platform === "linux" ? { linux: { store: "secret-service" as const } } : undefined;
const entry = () => new AsyncEntry("com.solvea.cxclaw", "session", options);

export class SessionNotFoundError extends Error {
  constructor() {
    super("未登录");
    this.name = "SessionNotFoundError";
  }
}

export async function loadSession(): Promise<Session> {
  const raw = await entry().getPassword();
  if (!raw) throw new SessionNotFoundError();
  return JSON.parse(raw) as Session;
}
export async function saveSession(session: Session): Promise<void> {
  if (!session.refreshToken) throw new Error("refusing to persist an empty session");
  await entry().setPassword(JSON.stringify(session));
}
export async function deleteSession(): Promise<void> { await entry().deleteCredential(); }
