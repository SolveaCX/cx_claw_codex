import packageJson from "../package.json" with { type: "json" };
export const VERSION = packageJson.version;
export const TOOL_SCHEMA_VERSION = "1";
export const SERVER_API_VERSION = "1";
