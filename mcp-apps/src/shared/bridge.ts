import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import { useEffect, useState } from "react";

type BridgeState = {
  connected: boolean;
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
};

export const app = new App({ name: "CXClaw MCP Apps", version: "1.0.0" });
let state: BridgeState = { connected: false, input: {} };
const listeners = new Set<() => void>();
const publish = (update: Partial<BridgeState>) => {
  state = { ...state, ...update };
  for (const listener of listeners) listener();
};
const applyTheme = () => {
  const context = app.getHostContext();
  if (context?.theme) applyDocumentTheme(context.theme);
  if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
};

app.ontoolinput = ({ arguments: input }) =>
  publish({ input: (input ?? {}) as Record<string, unknown> });
app.ontoolresult = (toolResult) =>
  publish({ output: toolResult.structuredContent as Record<string, unknown> | undefined });
app.onhostcontextchanged = () => applyTheme();

void app
  .connect()
  .then(() => {
    applyTheme();
    publish({ connected: true });
  })
  .catch((error) => publish({ error: error instanceof Error ? error.message : String(error) }));

export function useBridgeState() {
  const [, render] = useState(0);
  useEffect(() => {
    const listener = () => render((value) => value + 1);
    listeners.add(listener);
    return () => void listeners.delete(listener);
  }, []);
  return state;
}

export async function callTool(name: string, args: Record<string, unknown>) {
  const response = await app.callServerTool({ name, arguments: args });
  if (response.isError)
    throw new Error(
      response.content?.map((item) => ("text" in item ? item.text : "")).join("\n") ||
        `${name} failed`,
    );
  return response.structuredContent as Record<string, unknown> | undefined;
}
