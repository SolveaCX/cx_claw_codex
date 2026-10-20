# CXClaw Codex Plugin

内部员工使用的 CXClaw Codex 插件。它通过钉钉设备授权登录，在本地合并文件、Git、SLS 工具与 `solvea-kit` 远程 MCP 能力。

```bash
cxclawctl login --server https://kit.example.com/api_v2/solvea-kit
cxclawctl tenant search acme --env prod
cxclawctl tenant use 123 --env prod --purpose "badcase investigation"
cxclawctl doctor
```

凭据只保存在 macOS Keychain、Windows Credential Manager 或 Linux Secret Service。Linux 缺少 Secret Service 时登录会失败，不会写明文文件。

更新包由公司 Ed25519 密钥签名并从公司对象存储下载。更新先安装到独立版本目录，通过 `doctor` 后才原子切换；失败保持旧版本。
