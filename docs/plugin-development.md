# Codex 插件本地调试

本地调试使用独立的 `cxclaw-dev` 插件和 `tenant-panel-dev` MCP server，不会替换或修改已安装的稳定版 `cxclaw`。

## 首次安装

在仓库根目录运行：

```bash
bun install --frozen-lockfile
bun run dev:plugin
```

该命令会：

1. 构建本地 `dist/cli.js` 和 `dist/tenant-panel.js`。
2. 在 `_tmp_/codex-plugin-dev/` 生成本地 marketplace 和开发插件。
3. 注册 `cxclaw-dev` marketplace，并安装 `cxclaw-dev@cxclaw-dev`。
4. 让开发插件直接执行当前仓库的 `dist/cli.js`，不经过 npm。

首次安装完成后重启一次 ChatGPT desktop app。右侧会话栏会同时出现开发版租户面板，标题为 `CXClaw Dev 当前租户`。

## 日常开发

启动持续构建：

```bash
bun run dev:plugin:watch
```

保存 TypeScript 文件后，`tsup` 会更新 `dist/`。打开 Settings > MCP servers，找到 `tenant-panel-dev` 并选择 Restart，即可让 MCP server 重新加载本地代码。`/mcp` 可用于确认连接状态。无需 npm 发版、Git Marketplace 更新或重新安装稳定插件。

修改 skills、manifest 或 MCP 配置后，运行一次：

```bash
bun run dev:plugin
```

它会重新生成并同步本地开发插件；随后从 Settings > MCP servers 重启 `tenant-panel-dev`。如果 Codex 没有发现插件结构变化，再重启 ChatGPT desktop app。

## 检查与清理

查看插件和 marketplace 状态：

```bash
bun run dev:plugin:status
```

移除开发版，不影响稳定版：

```bash
bun run dev:plugin:remove
```

本地开发产物都在 `_tmp_/codex-plugin-dev/`，不会提交到 Git。
