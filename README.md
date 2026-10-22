# CXClaw

CXClaw 是 Solvea 内部使用的 Codex 插件。它把原 CXClaw 的业务能力带到本地 Codex：Codex 负责理解任务和编排步骤，`cxclaw` CLI 负责登录、选择租户、调用业务接口、执行现有 Python 脚本和直查 SLS。

插件不启动本地 MCP，也不依赖 `solvea-kit`。`shulex-cloud` 只提供钉钉授权、租户授权、服务配置和短期凭据；具体业务操作由本机 CLI 执行。

## 能力

- Agent 分析、配置、测试和交付
- 知识库构建、迁移和导入
- POC 交付与报告生成
- Solvea Desk 工单查询和报告
- badcase 排查与 SLS 客户端直查
- 测试、生产环境和跨租户切换
- 写操作的预览、确认、提交和结果核验

完整能力映射见 [`capabilities.lock.json`](./capabilities.lock.json)。`runtime-inspector` 只在 `dev` 和 `canary` 通道使用。

## 运行要求

- Codex CLI
- Node.js 22 或更高版本，包含 `npm` 和 `npx`
- Python 3.12
- `requirements-cli.txt` 中锁定的 Python 依赖
- 可用的系统安全凭据库：macOS Keychain、Windows Credential Manager 或 Linux Secret Service

安装 Python 依赖：

```bash
python3.12 -m pip install -r requirements-cli.txt
```

CXClaw 不会回退使用其他 Python 大版本。Linux 没有 Secret Service 时会拒绝保存登录信息，不会把凭据写入明文文件。

## 安装

推荐使用稳定通道：

```bash
codex plugin marketplace add SolveaCX/cx_claw_codex --ref marketplace/stable
codex plugin add cxclaw@cxclaw
```

然后登录公司提供的授权服务：

```bash
npx --yes @shulex/cxclawctl@latest auth login --server <shulex-cloud 授权地址>
```

CLI 会打开钉钉授权页。授权完成后，检查登录状态和本地版本：

```bash
npx --yes @shulex/cxclawctl@latest auth status
npx --yes @shulex/cxclawctl@latest doctor
```

也可以用一条命令完成插件安装、登录和自动更新任务注册：

```bash
npx --yes @shulex/cxclawctl@latest setup \
  --server <shulex-cloud 授权地址> \
  --channel stable
```

可用通道为 `stable`、`canary` 和 `dev`。内部日常使用请选择 `stable`。

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

## 常用命令

```bash
# 查看版本和能力清单
npx --yes @shulex/cxclawctl@latest version
npx --yes @shulex/cxclawctl@latest capabilities

# 调用只读业务命令
npx --yes @shulex/cxclawctl@latest api get-agent --id 456 --pretty

# 执行插件内 Python 脚本
npx --yes @shulex/cxclawctl@latest script skills/poc/scripts/plan.py --init

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
npx --yes @shulex/cxclawctl@latest api update-agent \
  --data-file update.json \
  --phase preview \
  --pretty

printf '%s' "$CONFIRMATION_TOKEN" | npx --yes @shulex/cxclawctl@latest api update-agent \
  --data-file update.json \
  --phase commit \
  --confirmation-token-stdin \
  --idempotency-key "$IDEMPOTENCY_KEY" \
  --pretty
```

## 更新

CLI 使用 `npx --yes @shulex/cxclawctl@latest` 运行，每次启动都会使用 npm 上的最新稳定版本。Skills 由 Codex Git Marketplace 更新：

```bash
npx --yes @shulex/cxclawctl@latest update
```

注册每 6 小时执行一次的系统更新任务：

```bash
npx --yes @shulex/cxclawctl@latest update --install-scheduler
```

更新完成后，新建 Codex 会话或重启 Codex，让新版 Skills 生效。

## 安全边界

- 登录信息只保存在操作系统安全凭据库。
- SLS 长期 AK/SK 不下发到客户端；CLI 每次查询只申请短期只读 STS，并直接连接阿里云 SLS。
- 客户端提供的 `tenantId`、`accountId` 和环境值不能直接作为授权依据，服务端签发的租户上下文才是最终权限边界。
- 业务 token 不输出到终端或日志，只通过受控的子进程环境传给本地业务脚本。
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

本地执行 CLI：

```bash
bun run dev -- version
node bin/cxclawctl.mjs version
```

修改 Skills 或业务 command 后，重新生成并校验能力清单：

```bash
python3 scripts/check_capabilities.py --write
bun run check:capabilities
```

## 发布

使用版本准备脚本同步修改 npm、插件清单和能力清单中的版本：

```bash
bun run release:prepare <版本号>
```

版本规则：

- `vX.Y.Z` 发布到 `stable`
- `vX.Y.Z-canary.N` 发布到 `canary`
- `vX.Y.Z-dev.N` 发布到 `dev`

稳定版必须在 `release/vX.Y.Z` 分支准备版本并创建 PR。PR 经过评审并合入 `main` 后，GitHub Actions 才会创建 tag 和发布。不要直接推送稳定版 tag。

`canary` 和 `dev` 预发布版在通过 CI 的提交上推送对应 tag 后发布：

```bash
git push origin vX.Y.Z-canary.N
git push origin vX.Y.Z-dev.N
```

发布流水线会固定到触发发布的 Git commit，并依次执行测试、构建、能力校验、npm 发布、GitHub Release 和 Marketplace 通道推进。只有前一步成功才会执行下一步；npm 包未发布时不会推进 `marketplace/<channel>`。

npm 发布需要在 GitHub 的 `npm-publish` Environment 或仓库中配置 Secret `NPM_TOKEN`。缺少凭据会让发布失败，不会跳过。

发布产物包括：

```text
cxclaw-agent-plugin.zip
cxclaw-agent-plugin.json
cxclaw-agent-plugin.sha256
cxclaw-codex-plugin.zip
```

插件 ZIP 只从已提交的 Git 快照生成，不会包含本地未提交文件。

## 仓库结构

```text
.agents/plugins/marketplace.json  Git Marketplace 清单
.codex-plugin/plugin.json         Codex 插件清单
bin/cxclawctl.mjs                 npm CLI 入口
src/                              TypeScript CLI 实现
skills/                           CXClaw Skills 和 Python 业务脚本
capabilities.lock.json            Skills 与业务 command 能力映射
scripts/                          能力校验和发布打包脚本
```
