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

## Agent 编码规范

这里的 Agent 代码包括 CLI workflow、ChatFlow compiler/validator、MCP handler 和业务 API
适配层。新增能力必须先明确输入、租户边界和副作用，再实现调用链；不要把参数解析、业务编排、HTTP 请求和输出拼装全部塞进一个函数。

- **先校验，后副作用**：输入校验、节点归一化和权限判断尽量保持为纯函数；通过校验后才允许调用外部 API、写文件或提交变更。校验失败时不得留下半成品 Agent、流程图或临时状态。
- **显式租户上下文**：每个需要业务数据的 workflow 必须显式接收并传递 `contextId`/`profileId`，禁止从全局变量、隐式默认租户或上一次会话状态推断租户。跨租户测试必须证明两个 context 互不影响。
- **图编译与写入分离**：ChatFlow 的 source 解析、节点类型映射、结构校验和最终 API 写入分层；未知节点、缺失必填字段、非法边和不支持的配置必须明确报错，不得静默降级。
- **外部调用可控**：HTTP/RPC/LLM 调用必须有超时、有限重试和结构化错误；重试只用于可重试故障，不能重复执行未做幂等保护的写操作。长耗时操作使用流式响应或异步 Job，不阻塞 Web 请求线程。
- **可观测但不泄密**：日志记录 `tenantId`、资源 ID、耗时和汇总结果；禁止输出 token、Cookie、完整 Prompt、用户原文、附件 base64 或完整响应报文。循环内不逐条刷 `info` 日志。
- **注释解释原因**：注释只补充业务约束、兼容性原因、租户/幂等边界和容易被误改的时序；不要给显而易见的代码逐行翻译。复杂分支前留空行，并用短注释标明“为什么这样做”。
- **测试跟随能力**：每个新增 action、节点类型或外部接口至少覆盖成功、参数拒绝、租户隔离和外部失败路径；涉及写操作时必须覆盖预览、确认、幂等和重复调用。

代码排版统一使用 Prettier：提交前运行 `bun run format:check`；重构时保持函数职责单一，相关常量、类型、纯函数和副作用函数按层次分组，并在逻辑段之间保留空行。

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

