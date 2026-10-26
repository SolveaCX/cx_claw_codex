export type CliErrorCategory = "auth" | "server" | "usage" | "internal";

export interface CliErrorBody {
  code: number;
  category: CliErrorCategory;
  message: string;
  reason: string;
  retryable: boolean;
  hint?: string;
  actions?: string[];
}

export class CliError extends Error {
  constructor(public readonly body: CliErrorBody) {
    super(body.message);
    this.name = "CliError";
  }
}

export function notAuthenticated(message = "CXClaw 尚未登录"): CliError {
  return new CliError({
    code: 3,
    category: "auth",
    message,
    reason: "not_authenticated",
    retryable: false,
    hint: "运行 cxclawctl auth login 完成钉钉授权",
    actions: ["cxclawctl auth login"],
  });
}

export function errorOutput(error: unknown): { error: CliErrorBody } {
  if (error instanceof CliError) return { error: error.body };
  return {
    error: {
      code: 1,
      category: "internal",
      message: error instanceof Error ? error.message : String(error),
      reason: "command_failed",
      retryable: false,
    },
  };
}
