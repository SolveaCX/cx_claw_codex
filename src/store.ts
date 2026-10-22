import { AsyncEntry } from "@napi-rs/keyring";
import type { Session } from "./types.js";

const options = process.platform === "linux" ? { linux: { store: "secret-service" as const } } : undefined;
const entry = () => new AsyncEntry("com.solvea.cxclaw", "session", options);

export async function loadSession(): Promise<Session> {
  const raw = await entry().getPassword();
  if (!raw) throw new Error("未登录，请先运行 npx --yes @shulex/cxclawctl@latest auth login");
  return JSON.parse(raw) as Session;
}
export async function saveSession(session: Session): Promise<void> {
  if (!session.refreshToken) throw new Error("refusing to persist an empty session");
  await entry().setPassword(JSON.stringify(session));
}
export async function deleteSession(): Promise<void> { await entry().deleteCredential(); }
