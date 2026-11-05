# Codex 插件本地调试

本地调试使用独立的 `cxclaw-dev` 插件。`tenant-panel-dev` 始终由该插件声明，不会注册成全局独立 MCP，也不会替换或修改已安装的稳定版 `cxclaw`。

## 首次安装

在仓库根目录运行：

```bash
bun install --frozen-lockfile
bun run dev:plugin
```

该命令会：

1. 构建本地 `dist/cli.js` 和 `dist/mcp-apps/` 中的 MCP App 产物。
2. 在 `_tmp_/codex-plugin-dev/` 生成本地 marketplace 和开发插件。
3. 将开发插件同步到仓库根目录下的 `./playground/`，并写入项目级 marketplace、配置和 `AGENTS.md`。
4. 清理全局 `cxclaw-dev` 注册，确保开发插件只在该目录中启用。
5. 让开发插件直接执行当前仓库的 `dist/cli.js`，不经过 npm。

首次使用前，在仓库根目录创建 `playground` 目录：

```bash
mkdir playground
```

这些目录由 `.gitignore` 忽略，不会提交到 Git。

首次安装完成后重启一次 ChatGPT desktop app。右侧会话栏会同时出现开发版租户面板，标题为 `CXClaw Dev 当前租户`。

## 日常开发

启动持续构建：

```bash
bun run dev:plugin:watch
```

保存代码后，Node.js 端由 `tsup` 更新，MCP App 前端由 Vite 更新。刷新方式取决于修改内容：

- 修改 `mcp-apps/`：等待 Vite 生成新产物，完全退出并重新打开 ChatGPT desktop app，使 MCP server 用新内容 hash 注册 tool 和 resource，再重新调用入口 tool。
- 修改 `src/mcp/server.ts`、tool metadata 或其他 MCP server 逻辑：完全退出并重新打开 ChatGPT desktop app，让插件 MCP 进程重新加载 `dist/cli.js`。

插件内置 MCP 当前没有独立的 `Restart` 按钮。无需 npm 发版、Git Marketplace 更新或重新安装稳定插件。

修改 skills、manifest 或 MCP 配置后，运行一次：

```bash
bun run dev:plugin
```

它会重新生成并同步本地开发插件。修改 skills、manifest 或 MCP 配置后，完全退出并重新打开 ChatGPT desktop app，让宿主重新发现插件结构。

## MCP App 前端开发规范

### 统一技术栈

所有新增和重构的 MCP App 必须使用：

- Vite：浏览器端构建和 watch。
- React：组件、状态和生命周期。
- Radix UI：无样式交互原语和可访问性行为。
- Tailwind CSS：布局、排版、响应式和视觉样式。
- `@modelcontextprotocol/ext-apps`：MCP Apps bridge 和宿主上下文。

前端源码统一放在：

```text
mcp-apps/
├── vite.config.ts
├── src/shared/
├── src/<app-name>/main.tsx
└── tests/
```

MCP server 端只负责 tool、resource、业务逻辑和 Vite 产物加载。React 组件不得放入 `src/mcp/`。

所有 App 共享一份 Vite 配置、Tailwind 入口、host theme provider、MCP bridge hooks 和基础 UI 组件。每个 App 使用独立 `main.tsx` entry，并通过统一构建脚本逐 App 生成自包含 ES module，禁止产生跨 App 共享 chunk。

### 组件规则

- Dialog、Popover、Tooltip、Tabs、Progress、ScrollArea 等交互组件优先使用 Radix UI primitive。
- Radix UI 负责交互语义、键盘操作、focus 管理和 ARIA；Tailwind CSS 负责全部视觉样式。
- 公共组件放在 `mcp-apps/src/shared/ui/`，业务组件保留在各 App 目录。
- 组件输入必须来自经过 Zod 校验的 `structuredContent`，不能直接信任 tool result。
- 权威业务状态保存在 MCP server；React state 和 `widgetState` 只保存界面状态。
- 所有 tool call 通过 `App.callServerTool()` 发起，卡片不直接访问 Solvea API。
- 所有 bundle、CSS 和静态资源随插件本地发布，不从运行时 CDN 加载。

### Codex 光暗主题

所有 MCP App 必须跟随宿主主题，不维护独立主题开关。

初始化和宿主主题变化时统一执行：

```tsx
import {
  applyDocumentTheme,
  applyHostStyleVariables,
} from "@modelcontextprotocol/ext-apps";

const applyHostTheme = () => {
  const context = app.getHostContext();
  if (context?.theme) applyDocumentTheme(context.theme);
  if (context?.styles?.variables) {
    applyHostStyleVariables(context.styles.variables);
  }
};

applyHostTheme();
app.addEventListener("hostcontextchanged", applyHostTheme);
```

Tailwind dark variant 绑定 `document.documentElement[data-theme]`：

```css
@import "tailwindcss";

@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));
```

宿主 CSS variables 映射为项目语义 token：

```css
@theme inline {
  --color-app-background: var(--color-background-primary, Canvas);
  --color-app-surface: var(--color-background-secondary, ButtonFace);
  --color-app-foreground: var(--color-text-primary, CanvasText);
  --color-app-muted: var(--color-text-secondary, GrayText);
  --color-app-border: var(--color-border-secondary, ButtonBorder);
  --color-app-ring: var(--color-ring-primary, Highlight);
  --color-app-danger: var(--color-text-danger, LinkText);
  --font-app-sans: var(--font-sans, ui-sans-serif, system-ui, sans-serif);
  --font-app-mono: var(--font-mono, ui-monospace, monospace);
}
```

组件只使用语义 class，例如 `bg-app-background`、`bg-app-surface`、`text-app-foreground`、`text-app-muted`、`border-app-border`。业务状态色使用宿主提供的 `info`、`success`、`warning`、`danger` variables。

主题验收必须覆盖：

- light 首次渲染。
- dark 首次渲染。
- 卡片挂载期间从 light 切换到 dark。
- 卡片挂载期间从 dark 切换到 light。
- Radix UI portal 内容跟随当前主题。
- focus ring、disabled、error、loading 状态在两种主题下均清晰可见。

### 构建约束

- Node.js CLI 和 MCP server 使用 `tsup`。
- MCP App 浏览器代码使用 Vite，不在 `tsup.config.ts` 中增加 browser entry。
- Vite 输出统一写入 `dist/mcp-apps/`。
- 每个 App 的 Vite manifest 是对应 MCP resource 加载构建产物的唯一索引。
- 每个 App 必须独立生成自包含 bundle，不能引用其他 App 的输出文件或跨 App 共享 chunk。
- resource HTML 使用 `<script type="module">` 加载内联 bundle。
- UI resource MIME 固定为 `text/html;profile=mcp-app`。
- UI resource URI 固定使用 `ui://cxclaw/<app-name>/<content-hash>.html`，例如 `ui://cxclaw/live-test/4a16d8c390ef.html`。
- `content-hash` 取最终内联 HTML 的 SHA-256 前 12 位，覆盖 Vite 生成的 JavaScript、CSS 和 resource HTML 包装逻辑。
- 构建内容变化时必须生成新的 `content-hash`；内容不变时 URI 必须保持稳定。禁止使用 `v2`、日期或手工递增数字代替内容 hash。
- tool metadata、resource 注册 URI 和 resource contents URI 必须引用同一个带 hash URI。
- URI 由 MCP server 根据 `dist/mcp-apps/<app-name>/` 自动计算，开发者不得手工维护 hash。
- 生产构建不得依赖 Vite dev server。

### 验证命令

```bash
bun run typecheck
bun test
bun run build
bun run test:package
```

前端变更必须同时通过 React 组件测试、light/dark 主题测试和打包产物测试。

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

## CLI 命名规范

- 已迁移业务命令统一使用 `cxclawctl <resource> <action>`，例如 `analytics messages`、`agent list`。
- `resource` 和 `action` 只能使用小写 kebab-case（单词用 `-` 连接），不得使用驼峰、下划线或通配符。
- 新能力直接在资源 handler 中实现；不得新增 `api analytics-messages`、`api chat-report-*` 一类扁平别名再转发。
- `api <command>` 只保留给尚未迁移的兼容能力。已经进入资源注册表的命令会拒绝从 `api` 入口调用。
- 禁止用 `startsWith()` 将一组未知命令兜底到同一个实现；每个公开 action 必须显式注册并有请求级测试。
