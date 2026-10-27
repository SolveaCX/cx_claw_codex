# CXClaw

CXClaw 是 Solvea 内部使用的 Codex 插件。它把原 CXClaw 的业务能力带到本地 Codex：Codex 负责理解任务和编排步骤，`cxclaw` CLI 负责登录、选择租户、调用业务接口、执行本地工作流和直查 SLS。所有业务代码统一使用 TypeScript，Skills 只描述流程并调用 CLI。

插件包含一个只读本地 MCP server，用于在 Codex 会话右侧面板展示当前租户；它不承担业务调用。`shulex-cloud` 只提供钉钉授权、租户授权、服务配置和短期凭据；具体业务操作仍由本机 CLI 执行，插件也不依赖 `solvea-kit`。

## 能力

- Agent 分析、配置、测试和交付
- 知识库构建、迁移和导入
- POC 交付与报告生成
- Solvea Desk 工单查询和报告
- badcase 排查与 SLS 客户端直查
- 测试、生产环境和跨租户切换
- Codex 会话右侧面板显示全局当前租户
- 写操作的预览、确认、提交和结果核验

完整能力映射见 [`capabilities.lock.json`](./capabilities.lock.json)。`runtime-inspector` 只在 `dev` 和 `canary` 通道使用。

## 运行要求

- Codex CLI
- Node.js 22 或更高版本，包含 `npm` 和 `npx`
- 可用的系统安全凭据库：macOS Keychain、Windows Credential Manager 或 Linux Secret Service

Linux 没有 Secret Service 时会拒绝保存登录信息，不会把凭据写入明文文件。

## 安装

推荐使用稳定通道：

```bash
codex plugin marketplace add SolveaCX/cx_claw_codex --ref marketplace/stable
codex plugin add cxclaw@cxclaw
```

CXClaw 采用和 DWS CLI 相同的显式登录流程。业务命令发现未登录时，会立即返回结构化的 `not_authenticated` 错误，不会自行打开浏览器。Codex 随后执行一次 `auth login`；该命令会打开钉钉授权页并持续运行到成功、失败或过期。授权成功后，Codex 重试原业务命令，不需要用户回复“已授权”。插件不使用 Codex hooks。

CLI 固定连接生产授权服务 `https://ai.solvea.cx/api_v2/ticket`，不接受用户指定服务地址或登录环境。一次登录即可访问获准的测试和生产租户。需要人工诊断授权时，可以执行：

```bash
npx --yes @shulex/cxclawctl@latest auth login
npx --yes @shulex/cxclawctl@latest auth status
npx --yes @shulex/cxclawctl@latest doctor
```

也可以用一条命令完成插件安装、登录和自动更新任务注册：

```bash
npx --yes @shulex/cxclawctl@latest setup \
  --channel stable
```

可用通道为 `stable`、`canary` 和 `dev`。内部日常使用请选择 `stable`。

安装后的 Skills 不直接调用 npm `latest`。插件内的 `plugin-cli.mjs` 会读取插件清单版本，并调用完全相同版本的 `@shulex/cxclawctl`，避免新 CLI 与旧 Skills 混用。README 中的 `@latest` 命令只用于首次安装、人工诊断和更新入口。

## 选择环境和租户

测试环境使用 `--env test`，生产环境使用 `--env prod`。环境由每次租户选择明确指定，不从租户名称推断。

```bash
# 搜索测试环境租户
npx --yes @shulex/cxclawctl@latest tenant search "租户名称" --env test

# 选择测试环境租户
npx --yes @shulex/cxclawctl@latest tenant use <accountId> \
  --env test \
  --purpose "badcase 排查"

# 查看或清除当前租户
npx --yes @shulex/cxclawctl@latest tenant current
npx --yes @shulex/cxclawctl@latest tenant clear
```

切换到生产环境时，重新执行 `tenant search` 和 `tenant use`，并把 `--env` 改为 `prod`。

Codex 桌面端可从会话右侧面板打开“CXClaw 当前租户”。面板读取与 CLI 相同的系统安全凭据库，只展示 `accountId`、`accountCode`、`accountName`、环境、用途和到期时间，不展示任何 token。当前租户是本机全局状态；在一个会话中切换后，其他会话的面板也会同步变化。

## 常用命令

```bash
# 查看版本和能力清单
npx --yes @shulex/cxclawctl@latest version
npx --yes @shulex/cxclawctl@latest version --json
npx --yes @shulex/cxclawctl@latest capabilities

# 调用只读业务命令；业务命令统一使用“资源 + 动作”两层结构
npx --yes @shulex/cxclawctl@latest agent get --id 456 --pretty
npx --yes @shulex/cxclawctl@latest intent list --pretty

# 使用 TypeScript CLI 执行本地工作流
npx --yes @shulex/cxclawctl@latest poc plan --init
npx --yes @shulex/cxclawctl@latest kb-builder crawl --url https://docs.example.com
npx --yes @shulex/cxclawctl@latest solvea-desk fetch-tickets --task-id demo

# 直接从本机查询 SLS；from/to 使用 Unix 秒级时间戳
npx --yes @shulex/cxclawctl@latest sls query \
  --from <开始时间> \
  --to <结束时间> \
  --query '<查询语句>' \
  --line 50

# 刷新登录或退出
npx --yes @shulex/cxclawctl@latest auth refresh
npx --yes @shulex/cxclawctl@latest auth logout
```

### 写操作

写操作必须先预览，再由用户明确确认。确认凭证通过 stdin 传入，不能写进命令参数、文件或日志。

```bash
npx --yes @shulex/cxclawctl@latest agent update \
  --data-file update.json \
  --phase preview \
  --pretty

printf '%s' "$CONFIRMATION_TOKEN" | npx --yes @shulex/cxclawctl@latest agent update \
  --data-file update.json \
  --phase commit \
  --confirmation-token-stdin \
  --idempotency-key "$IDEMPOTENCY_KEY" \
  --pretty
```

## 更新

自动更新以 Git Marketplace 中的插件版本为准。更新任务先刷新当前配置的 `stable`、`canary` 或 `dev` Marketplace，再重新安装已启用的 CXClaw 插件；新版插件中的 `plugin-cli.mjs` 随后调用同版本 npm CLI：

```bash
npx --yes @shulex/cxclawctl@latest update
```

注册每 6 小时执行一次的系统更新任务：

```bash
npx --yes @shulex/cxclawctl@latest update --install-scheduler
```

更新任务使用安装时解析出的 Node.js 和 npm 绝对路径，避免 macOS LaunchAgent 等后台环境找不到 `npx`。更新后还会确认对应 npm CLI 版本已经公开可下载；检查失败时命令报错，不把不完整更新报告为成功。

更新完成后，新建 Codex 会话或重启 Codex，让新版 Skills 生效。已经运行中的会话继续使用启动时加载的旧版 Skills。

## 安全边界

- 登录信息只保存在操作系统安全凭据库。
- SLS 长期 AK/SK 不下发到客户端；CLI 每次查询只申请短期只读 STS，并直接连接阿里云 SLS。
- 客户端提供的 `tenantId`、`accountId` 和环境值不能直接作为授权依据，服务端签发的租户上下文才是最终权限边界。
- 业务 token 不输出到终端或日志，只在请求对象的生命周期内传给 CLI 的 HTTP client。
- `main` 分支只用于开发；员工使用由发布流程推进的 `marketplace/stable`、`marketplace/canary` 或 `marketplace/dev`。

## 本地开发

开发工具使用 Bun，运行时仍是 Node.js 22：

```bash
bun install --frozen-lockfile
bun run typecheck
bun test
bun run build
bun run check:capabilities
bun run check:release
```

### Codex 插件本地调试

不经过 npm 发版即可调试当前工作区：

```bash
bun run dev:plugin
bun run dev:plugin:watch
```

开发版使用独立的 `cxclaw-dev` 插件，并直接执行当前仓库的构建产物，不会覆盖稳定版。首次安装后只需重启一次 ChatGPT desktop app；后续构建完成后，从 Settings > MCP servers 重启 `tenant-panel-dev` 即可加载新代码。完整说明见 [`docs/plugin-development.md`](docs/plugin-development.md)。

本地执行 CLI：

```bash
bun run dev -- version
node bin/cxclawctl.mjs version
```

修改 Skills 或业务 command 后，重新生成并校验能力清单：

```bash
bun run check:capabilities -- --write
bun run check:capabilities
```

## 发布

稳定版使用一条命令创建发布 PR，日常修复默认使用 `patch`：

```bash
bun run release:create patch
```

也支持 `minor`、`major` 或明确版本号，例如 `bun run release:create 0.2.0`。命令会统一版本、执行完整检查并创建 `release/vX.Y.Z` PR。PR 合入后，发布流水线才会发布 npm、创建 GitHub Release 并推进 `marketplace/stable`；PR 创建成功不等于已经发布。

维护者和 AI 在操作前必须阅读完整的[发布手册](./docs/releasing.md)。手册包含版本选择、预发布、合并后验收、失败恢复和禁止操作。仓库根目录的 [`AGENTS.md`](./AGENTS.md) 记录了 AI 每次进入仓库都会读取的强制规则。

## 仓库结构

```text
.agents/plugins/marketplace.json  Git Marketplace 清单
.codex-plugin/plugin.json         Codex 插件清单
plugin-cli.mjs                    将插件固定到同版本 npm CLI
bin/cxclawctl.mjs                 npm CLI 入口
src/                              TypeScript CLI 和业务工作流实现
skills/                           Marketplace Skills、reference 和静态资源
capabilities.lock.json            Skills 与业务 command 能力映射
scripts/                          能力校验和发布打包脚本
```

npm 包只包含 CLI 运行时代码；`SKILL.md`、reference 文档和静态资源只通过 Git Marketplace 分发，不在 npm 中重复打包。
