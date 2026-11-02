# CXClaw 仓库说明

## 项目边界

- 本仓库同时维护 Codex 插件和 `@shulex/cxclawctl` CLI。业务逻辑使用 TypeScript，Skills 只负责任务说明和调用 CLI。
- Codex 插件通过 Git Marketplace 分发，CLI 通过 npm 分发。两者必须使用同一个版本号。
- `main` 是开发分支，不直接代表员工正在使用的版本；员工通道由 `marketplace/stable`、`marketplace/canary` 和 `marketplace/dev` 指向。
- 修改子命令或 Skill 后，必须同步检查 `capabilities.lock.json`；优先运行 `bun run check:capabilities -- --write` 生成，不要手工维护可生成内容。

## CLI 命令规范

- 已迁移的业务命令统一使用 `cxclawctl <resource> <action>`，例如 `cxclawctl analytics messages`、`cxclawctl agent list`。
- `resource`、`action` 和内部兼容命令名只能使用小写 kebab-case；禁止使用驼峰、下划线和通配符。
- 新能力必须直接在对应资源 handler 中实现并显式注册。禁止先新增 `api analytics-messages`、`api chat-report-*` 一类旧式扁平命令，再从新命令转发过去。
- `api <command>` 只用于尚未迁移的兼容能力。命令迁入资源注册表后，必须拒绝继续从 `api` 入口调用。
- 禁止使用 `startsWith()` 或其他前缀匹配，把一组未登记的命令兜底到同一个实现。每个公开 action 必须有明确映射和请求级测试。
- 新增或修改命令后，必须运行 CLI 命名校验、相关测试和 `bun run check:capabilities`，并确认 `capabilities.lock.json` 不包含旧式别名或通配符命令。

## 项目编码 Agent 规范

这里的 Agent 指负责修改本项目代码的编码 Agent，不是业务运行时的 Agent。编码 Agent 必须遵守以下协作和交付规则：

- **先读指令，再动手**：开始任务前读取当前目录及父目录的 `AGENTS.md`，确认项目结构、验证命令、环境边界和禁止操作；不要用个人习惯覆盖仓库约定。
- **先看现场，再定范围**：先执行 `git status`、查看相关文件和已有 diff，区分用户未提交改动与本次任务改动。不得用重置、强制 checkout、覆盖写入等方式清理或隐藏用户现场。
- **小步修改，保持可审查**：优先使用 `apply_patch` 做最小范围修改；不要顺手重命名、重排无关文件或引入无关依赖。格式化必须有明确范围，生成物、缓存和临时文件不得进入提交。
- **代码可读优先**：函数保持单一职责，相关常量、类型、纯逻辑和副作用逻辑分组；逻辑段之间保留适当空行。注释解释业务原因、兼容性约束、时序和安全边界，不逐行复述代码。
- **验证与改动匹配**：先跑受影响模块的定向检查，再跑项目要求的完整检查；格式、类型、测试、构建或打包任一失败都必须明确报告，不能把“执行过”写成“通过”。
- **安全边界清晰**：不把凭据、个人数据或完整敏感报文写入代码、测试、日志和提交；涉及生产、发布、推送、删除、外部消息或权限变化时，必须确认授权和目标范围。
- **协作透明**：需要拆分任务时说明子任务边界和汇合方式；工具执行较慢时持续汇报关键进展；遇到阻塞先给出证据和可选路径，不绕过检查。
- **提交可追溯**：提交前检查 `git diff --check`、工作区状态和提交内容；提交消息使用 Conventional Commit 结构并用中文准确描述实际改动。未得到请求时不自动 push、建 PR、合并或发布。

代码排版统一使用 Prettier：提交前运行 `bun run format:check`；重构时保留清晰的文件层次和逻辑分段，避免用超长表达式压缩多个业务步骤。

## 开发检查

提交代码或创建 PR 前至少运行：

```bash
bun install --frozen-lockfile
bun run format:check
bun run typecheck
bun test
bun run build
bun run test:package
bun run check:capabilities
bun run check:release
```

每次完成本仓库的代码、Skill、manifest、MCP 或文档改动，并完成相应验证后，必须执行 `bun run dev:plugin`，重新构建并同步本地 `cxclaw-dev` 开发插件。不得只报告源码已修改而遗漏开发插件重载。若修改了 `src/mcp/server.ts`、MCP tool metadata、manifest 或 MCP 配置，还必须明确提醒用户完全退出并重新打开 ChatGPT desktop app；当前宿主没有可依赖的 MCP server 热重载能力。

不要提交 `dist/`、`node_modules/` 或 `_tmp_/` 中的文件。不要把 token、AK/SK、钉钉 Secret、测试账号或其他凭据写入源码、测试、文档和日志。

## 稳定版发布规则

收到“发版”“发一个新版本”“发布 stable”等要求时，先完整阅读 [`docs/releasing.md`](docs/releasing.md)，再执行发布操作。

- 首选命令是 `bun run release:create patch`。只有用户明确要求新增功能版本、破坏性版本或指定版本时，才改用 `minor`、`major` 或明确的 `X.Y.Z`。
- 不要手工逐个修改 `package.json`、`plugin.json`、`.codex-plugin/plugin.json` 和 `capabilities.lock.json` 的版本号。
- 不要直接创建或推送稳定版 tag，不要直接运行 `npm publish`，不要直接推进 `marketplace/stable`。
- 不要跳过脚本内的检查。不要为了绕过失败而使用 `--no-verify`、强制覆盖分支或破坏性 Git 命令。
- `release:create` 会真实创建分支、提交、推送和 PR。只做检查时，不得用它作为测试命令；可以无参数运行并确认它安全失败。
- 发布 PR 创建后，只能报告“发布 PR 已创建，等待合并”，不能报告“已经发布”。
- 发布 PR 合入 `main` 后，必须按 `docs/releasing.md` 验证 Publish workflow、npm 包及 dist-tag、GitHub Release、`marketplace/stable` 和安装版版本一致，全部通过后才能报告“发布完成”。
- 脚本失败时保留当前分支和工作区，记录失败命令及输出并报告。未经用户明确要求，不自动删分支、不回滚提交、不覆盖现场。

## 预发布规则

- `vX.Y.Z-canary.N` 进入 `canary`，`vX.Y.Z-dev.N` 进入 `dev`。
- 预发布 tag 只能指向已经通过 CI 的已提交 Git commit。
- 不得把预发布版本推进到 `stable`，也不得把 `main` 当作发布通道。

