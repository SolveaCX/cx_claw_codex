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

## 开发检查

提交代码或创建 PR 前至少运行：

```bash
bun install --frozen-lockfile
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

