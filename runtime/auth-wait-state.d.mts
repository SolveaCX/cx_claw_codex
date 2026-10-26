export function withAuthWaitMarker<T>(
  operation: () => Promise<T>,
  env?: NodeJS.ProcessEnv,
): Promise<T>;

export function hasActiveAuthWait(sessionId: string | undefined, now?: number): Promise<boolean>;
