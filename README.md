# CXClaw Codex Plugin

内部员工使用的 CXClaw Codex 插件。Codex 通过 skills 直接执行本地 `${PLUGIN_ROOT}/bin/cxclaw-launcher`；CLI 提供 CXClaw 业务 command、租户切换、SLS 直查和自动更新，不启动本地 MCP，也不访问 `solvea-kit`。

首次安装使用公司下载域提供的 `cxclaw-bootstrap`。bootstrap 完成钉钉授权、验签下载并把插件注册到个人 marketplace；用户不需要 GitHub 账号。Codex 安装后的 skill 通过 `${PLUGIN_ROOT}/bin/cxclaw-launcher` 执行 CLI。

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher auth login --server https://cloud.example.com
${PLUGIN_ROOT}/bin/cxclaw-launcher tenant search acme --env test
${PLUGIN_ROOT}/bin/cxclaw-launcher tenant use 123 --env test --purpose "badcase investigation"
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-agent --id 456 --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-agent --data-file update.json --phase preview --pretty
# 用户确认后，把 preview 返回的 confirmationToken 从 stdin 传入：
printf '%s' "$CONFIRMATION_TOKEN" | ${PLUGIN_ROOT}/bin/cxclaw-launcher api update-agent \
  --data-file update.json --phase commit --confirmation-token-stdin \
  --idempotency-key "$IDEMPOTENCY_KEY" --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher doctor
```

`shulex-cloud` 仅负责钉钉授权、租户授权、服务配置、短期凭据和版本下发。业务 command 在本机执行并直接调用现有业务 API；业务 token 只保存在系统安全凭据库，并只通过子进程环境副本传递。

凭据只保存在 macOS Keychain、Windows Credential Manager 或 Linux Secret Service。Linux 缺少 Secret Service 时登录会失败，不会写明文文件。业务命令依赖 Python 3.9+；发布包自带锁定版本的 Python 依赖，`doctor` 会在切换版本前校验运行环境。

更新包由公司 Ed25519 密钥签名并从公司对象存储下载。更新先安装到独立版本目录，通过 `doctor` 后才原子切换；失败保持旧版本。
