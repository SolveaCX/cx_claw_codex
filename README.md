# CXClaw Codex Plugin

内部员工使用的 CXClaw Codex 插件。Codex 通过 skills 直接执行本地 `$HOME/.codex/cxclaw/bin/cxclaw-launcher`；CLI 提供 CXClaw 业务 command、租户切换、SLS 直查和自动更新，不启动本地 MCP，也不访问 `solvea-kit`。

首次安装可直接使用公开 GitHub Marketplace：

```bash
codex plugin marketplace add SolveaCX/cx_claw_codex --ref marketplace/stable
codex plugin add cxclaw@cxclaw
```

普通员工也可以运行对应平台的 `cxclaw-bootstrap`。bootstrap 会从 GitHub Release 下载已签名的运行包，执行钉钉授权，并完成上述 Marketplace 注册；用户不需要 GitHub 登录。Codex 安装后的 skill 通过 `$HOME/.codex/cxclaw/bin/cxclaw-launcher` 执行 CLI。

```bash
$HOME/.codex/cxclaw/bin/cxclaw-launcher auth login --server https://cloud.example.com
$HOME/.codex/cxclaw/bin/cxclaw-launcher tenant search acme --env test
$HOME/.codex/cxclaw/bin/cxclaw-launcher tenant use 123 --env test --purpose "badcase investigation"
$HOME/.codex/cxclaw/bin/cxclaw-launcher api get-agent --id 456 --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher api update-agent --data-file update.json --phase preview --pretty
# 用户确认后，把 preview 返回的 confirmationToken 从 stdin 传入：
printf '%s' "$CONFIRMATION_TOKEN" | $HOME/.codex/cxclaw/bin/cxclaw-launcher api update-agent \
  --data-file update.json --phase commit --confirmation-token-stdin \
  --idempotency-key "$IDEMPOTENCY_KEY" --pretty
$HOME/.codex/cxclaw/bin/cxclaw-launcher doctor
```

`shulex-cloud` 仅负责钉钉授权、租户授权、服务配置和短期凭据。版本下载来自公开 GitHub Release，不再调用 `shulex-cloud /releases/check`。业务 command 在本机执行并直接调用现有业务 API；业务 token 只保存在系统安全凭据库，并只通过子进程环境副本传递。

凭据只保存在 macOS Keychain、Windows Credential Manager 或 Linux Secret Service。Linux 缺少 Secret Service 时登录会失败，不会写明文文件。业务命令使用发布包内置的 CPython 3.12.12 和锁定版本依赖，正式包不会回退到系统 Python；`doctor` 会在切换版本前校验运行环境。

更新包由公司 Ed25519 密钥签名并从 GitHub Release 下载。更新先安装到独立版本目录，通过 `doctor` 后才原子切换；失败保持旧版本。
