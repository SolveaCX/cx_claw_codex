# CXClaw Codex Plugin

内部员工使用的 CXClaw Codex 插件。Codex 通过 skills 直接执行本地 `npx --yes cxclaw@latest`；CLI 提供 CXClaw 业务 command、租户切换、SLS 直查和自动更新，不启动本地 MCP，也不访问 `solvea-kit`。

运行要求：Node.js 22+、Python 3.12 和已安装的 Codex CLI。

首次安装可直接使用公开 GitHub Marketplace：

```bash
codex plugin marketplace add SolveaCX/cx_claw_codex --ref marketplace/stable
codex plugin add cxclaw@cxclaw
```

普通员工不需要下载平台专用安装器，直接使用 Node.js 22 的 `npx` 即可。Codex 安装后的 skill 通过 `npx --yes cxclaw@latest` 执行 CLI。

```bash
npx --yes cxclaw@latest auth login --server https://cloud.example.com
npx --yes cxclaw@latest tenant search acme --env test
npx --yes cxclaw@latest tenant use 123 --env test --purpose "badcase investigation"
npx --yes cxclaw@latest api get-agent --id 456 --pretty
npx --yes cxclaw@latest api update-agent --data-file update.json --phase preview --pretty
# 用户确认后，把 preview 返回的 confirmationToken 从 stdin 传入：
printf '%s' "$CONFIRMATION_TOKEN" | npx --yes cxclaw@latest api update-agent \
  --data-file update.json --phase commit --confirmation-token-stdin \
  --idempotency-key "$IDEMPOTENCY_KEY" --pretty
npx --yes cxclaw@latest doctor
```

`shulex-cloud` 仅负责钉钉授权、租户授权、服务配置和短期凭据。版本下载来自公开 GitHub Release，不再调用 `shulex-cloud /releases/check`。业务 command 在本机执行并直接调用现有业务 API；业务 token 只保存在系统安全凭据库，并只通过子进程环境副本传递。

凭据只保存在 macOS Keychain、Windows Credential Manager 或 Linux Secret Service。Linux 缺少 Secret Service 时登录会失败，不会写明文文件。业务命令要求 Python 3.12 和 `requirements-cli.txt` 中的锁定依赖，正式包不会回退到其他 Python 大版本；`doctor` 会校验运行环境。

npm CLI 通过 npm registry 更新，Skills 通过 Git Marketplace 更新。GitHub Release 只保存插件 ZIP、版本元数据和校验文件。
