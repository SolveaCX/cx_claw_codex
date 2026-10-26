# CXClaw 发布手册

这份文档同时供维护者和 AI 使用。它描述从准备版本到验证员工安装版本的完整流程。稳定版发布的唯一标准入口是 `release:create`，不要手工拼接其中的步骤。

## 发布内容

一次 CXClaw 发布包含两部分，并且版本必须一致：

1. npm 上的 `@shulex/cxclawctl`，提供本地 CLI 运行代码。
2. Git Marketplace 中的 CXClaw 插件，提供 Skills、references、插件清单和固定 CLI 版本的启动入口。

GitHub Release 保存插件 ZIP 和校验文件。`marketplace/<channel>` 分支决定员工从哪个通道取得插件内容。

## 选择版本

默认使用 `patch`：

```bash
bun run release:create patch
```

只有发布内容符合下列条件时才选其他参数：

| 参数 | 使用条件 | 示例 |
| --- | --- | --- |
| `patch` | 修复、兼容性改进、小功能，默认选择 | `0.1.9 -> 0.1.10` |
| `minor` | 对外新增一组向后兼容的能力 | `0.1.9 -> 0.2.0` |
| `major` | 存在明确的破坏性变化 | `0.1.9 -> 1.0.0` |
| `X.Y.Z` | 用户已经指定准确版本 | `bun run release:create 0.3.0` |

不要因为提交数量多就提高版本级别。没有明确要求时，AI 应选择 `patch`。

## 稳定版流程

### 1. 发布前确认

在仓库根目录确认：

```bash
git status --short --branch
git fetch origin main --tags --prune
gh auth status
```

必须满足：

- 当前工作区没有未提交改动。
- 需要发布的代码已经合入 `origin/main`。
- `gh` 已登录并有创建分支和 PR 的权限。
- npm 发布所需的 `NPM_TOKEN` 已配置在 GitHub 的 `npm-publish` Environment；本地不需要也不应保存该 token。

### 2. 创建发布 PR

执行：

```bash
bun run release:create patch
```

脚本会自动：

1. 从最新 `origin/main` 计算新版本。
2. 创建 `release/vX.Y.Z` 分支。
3. 同步 `package.json`、`plugin.json`、`.codex-plugin/plugin.json` 和 `capabilities.lock.json`。
4. 安装锁定依赖并执行类型检查、测试、构建、安装包测试、能力检查和版本检查。
5. 从已提交内容生成两种插件包，并执行 npm 包 dry-run。
6. 检查发布提交只包含四个版本文件。
7. 创建提交、推送分支并创建合入 `main` 的 PR。

脚本成功后，应向用户提供 PR 地址，并明确说明“发布 PR 已创建，尚未发布”。等待评审和合并，不要自己推送稳定版 tag。

### 3. 合并后验证流水线

发布 PR 合入后，`.github/workflows/publish.yml` 会从合并提交创建 `vX.Y.Z` tag，然后按顺序执行：

1. 校验发布 commit 和通道。
2. 重新运行测试、构建和能力检查。
3. 发布 npm 包，并等待公共 registry 可以读取该版本。
4. 创建或更新 GitHub Release 并上传插件产物。
5. 最后推进 `marketplace/stable`。

查看并等待最近一次 Publish workflow：

```bash
gh run list --workflow Publish --limit 5
gh run watch <run-id> --exit-status
```

workflow 没有成功时，发布未完成。不要只凭 PR 已合并或 tag 已出现判断成功。

### 4. 验证所有发布面

把下面的 `<version>` 换成目标版本：

```bash
npm view @shulex/cxclawctl@<version> version
npm view @shulex/cxclawctl dist-tags --json
gh release view v<version>
git ls-remote --heads origin marketplace/stable
git ls-remote origin refs/tags/v<version>
```

再确认 `marketplace/stable` 和 tag 指向同一个 commit：

```bash
MARKETPLACE_SHA="$(git ls-remote --heads origin refs/heads/marketplace/stable | cut -f1)"
TAG_SHA="$(git ls-remote --tags origin refs/tags/v<version> | cut -f1)"
test -n "$MARKETPLACE_SHA" && test "$MARKETPLACE_SHA" = "$TAG_SHA"
```

命令退出状态为 0 才表示两个远端引用存在且指向同一个 commit。

最后从员工实际安装入口升级，并验证插件与 CLI 使用同一版本：

```bash
npx --yes @shulex/cxclawctl@latest update
npx --yes @shulex/cxclawctl@<version> version --json
```

新建 Codex 会话或重启 Codex 后，再检查 CXClaw Skills 能被发现，并完成至少一个只读命令。只有以下结果全部成立，才能报告发布完成：

- Publish workflow 成功。
- npm 精确版本存在，稳定版的 `latest` dist-tag 指向该版本。
- GitHub Release `v<version>` 存在且包含插件 ZIP 和校验文件。
- `marketplace/stable` 与发布 tag 指向同一 commit。
- 安装后的 `cliVersion` 与 `pluginVersion` 都是 `<version>`。

## 预发布流程

预发布版本格式固定为：

- `X.Y.Z-canary.N` 对应 `canary`。
- `X.Y.Z-dev.N` 对应 `dev`。

先在独立分支用底层命令同步版本，运行与稳定版相同的检查并提交四个版本文件：

```bash
bun run release:prepare X.Y.Z-canary.N
bun run typecheck
bun test
bun run build
bun run test:package
bun run check:capabilities
bun run check:release
git add package.json plugin.json .codex-plugin/plugin.json capabilities.lock.json
git commit -m "chore(release): 发布X.Y.Z-canary.N"
```

推送开发分支并让该 commit 通过 CI。确认无误后，用准确的 commit SHA 创建并推送 tag：

```bash
git tag --no-sign vX.Y.Z-canary.N <已通过CI的commit-sha>
git push origin refs/tags/vX.Y.Z-canary.N
```

`dev` 同理。预发布不使用稳定版 `release/vX.Y.Z` PR，也不能推进 `marketplace/stable`。禁止给未提交内容、未通过 CI 的 commit 或版本文件不一致的 commit 打 tag。

## 失败处理

### `release:create` 在创建分支前失败

修复错误后重新执行。常见原因包括工作区不干净、`gh` 未登录、目标版本没有递增，或同名发布分支已经存在。

### `release:create` 在创建分支后失败

保留现场并记录：

```bash
git status --short --branch
git diff --check
```

找到第一条失败命令并修复根因。不要自动执行 `git reset --hard`、强制切换分支或删除发布分支。是否继续当前分支或重新创建发布，由维护者根据现场决定。

### Publish workflow 失败

先读取失败 job：

```bash
gh run view <run-id> --log-failed
```

- npm 发布前失败：修复后重新运行 workflow，不要手工发布 npm。
- npm 已发布、后续步骤失败：流水线支持重复运行；它会识别已存在的精确 npm 版本，再继续 GitHub Release 和 Marketplace。
- `marketplace/stable` 未推进：仍视为发布未完成，不能让用户按稳定通道验收。

## 不能做的事

- 不手工分别修改四个版本文件。
- 不直接运行 `npm publish`。
- 不直接推送稳定版 tag。
- 不手工强推 `marketplace/stable` 来掩盖流水线失败。
- 不从未提交工作区打包；发布产物必须来自确定的 Git commit。
- 不把“PR 已创建”“PR 已合并”“npm 已发布”中的任一单项当作完整发布成功。

